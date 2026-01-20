# TinyScheduler Architecture

You're on a very solid architectural trajectory already. What you've described is essentially a filesystem-backed, MCP-aware, role-segmented workflow scheduler with Goose as the execution engine. The missing piece is coordination + lifecycle management, not core logic.

Below is a practical evolution path that stays aligned with your constraints:

- **Simple**
- **Observable**
- **File-based first**
- **MCP-friendly**
- **Incrementally more robust** (no premature Kubernetes 😄)

## 1. Reframe the Problem: You Need a Scheduler + Lease Manager

What you're describing breaks into four responsibilities:

### Discovery
- What tasks exist?
- What agent queues are non-empty?
- What tasks are eligible to run?

### Dispatch
- Which Goose recipes should be run?
- How many concurrent processes per agent?
- Which task IDs are "claimed"?

### Execution Tracking
- What process is handling which task?
- Is it still alive?
- Has it stalled?

### Recovery
- Detect orphaned processes
- Detect abandoned tasks
- Requeue or fail tasks safely

Your intuition about file-based tracking with shared conventions is exactly right for v1.

## 2. Introduce a First-Class Concept: Task Lease

Right now you have:

- **Task state** → tinytask-mcp
- **Task files** → filesystem
- **Execution** → goose subprocess

What's missing is a lease that answers: **"Who owns this task right now?"**

### Lease Model (Simple, File-Based)

For each running task:

```
{{base_path}}/running/
  task_{id}.json
```

Example contents:

```json
{
  "task_id": "1234",
  "agent": "architect",
  "pid": 48291,
  "recipe": "architect.yaml",
  "started_at": "2025-01-28T14:32:11Z",
  "heartbeat": "2025-01-28T14:34:02Z",
  "host": "calypso-dev-01"
}
```

### Rules

- Only the scheduler creates lease files
- The agent process updates heartbeat
- Lease is authoritative for "running"

This is more powerful than a `.pid` file but still dead simple.

## 3. Scheduler Loop (Cron-Friendly, Idempotent)

Your Python script becomes a single responsibility scheduler.

### High-Level Flow

1. Scan `running/` leases
2. Validate leases (PID alive?)
3. Reclaim orphaned tasks
4. Query tinytask for idle tasks per agent
5. Apply concurrency limits
6. Spawn goose processes
7. Create leases

### Key Principle

**Never spawn based solely on filesystem OR tinytask alone. Always reconcile both.**

## 4. Concurrency Model: Per-Agent, Not Per-Task

You already hinted at the right idea.

### Example Config

```yaml
agents:
  dispatcher: 1
  architect: 2
  product: 2
  devops: 1
  coder: 4
```

### Scheduler Logic

```python
for agent in agents:
    idle_tasks = tinytask.get_idle(agent)
    running = leases.count(agent)

    slots = max_concurrency[agent] - running
    if slots <= 0:
        continue

    tasks_to_start = idle_tasks[:slots]
    spawn(agent, tasks_to_start)
```

Each spawned Goose process can:

- Process one task
- Or loop until queue empty (your choice)

I recommend **one task per Goose run initially**—simplifies recovery.

## 5. Goose Execution Wrapper (Important)

Don't spawn Goose directly. Spawn a thin Python wrapper.

```bash
python run_agent.py \
  --agent architect \
  --task-id 1234 \
  --base-path /home/user/workspace/calypso
```

### Why?

The wrapper can:

- Update heartbeat
- Trap SIGTERM / SIGINT
- Mark task failed if Goose crashes
- Write structured logs
- Clean up lease on exit

### Wrapper Flow

```
1. Load task info from tinytask
2. exec goose run ...
3. While running:
     - every N seconds update lease heartbeat
4. On exit:
     - remove lease
     - update tinytask status
```

This is critical for observability.

## 6. Orphan Detection (This Is Where File-Based Shines)

Scheduler does this every run:

```python
for lease in running/:
    if not process_alive(lease.pid):
        mark_task_failed_or_requeue(lease.task_id)
        delete_lease(lease)
```

### Optional Heuristics

- Heartbeat older than N minutes → suspect hang
- Max runtime exceeded → kill & requeue

This gives you crash recovery for free.

## 7. State Authority: Who Owns What?

| Concern | Authority |
|---------|-----------|
| Task lifecycle | tinytask-mcp |
| Task files | filesystem |
| Execution | scheduler + lease |
| Process health | OS |
| Agent logic | Goose recipes |

This separation is clean and scales.

## 8. Where MCP Fits (And Why This Is Good)

### Your Scheduler

- Uses tinytask-mcp to query / update task states
- Does not need filesystem MCP (it's local)
- Remains stateless between runs

### Your Agents

- Only care about their task folder
- Do not need to coordinate with each other
- Never spawn subprocesses themselves

This keeps MCP usage orthogonal and composable.

## 9. Near-Future Enhancements (Natural Evolution)

Once this works, the next steps are obvious and incremental:

### A. Lease → tinytask

Eventually move leases into tinytask itself:

```python
task.execution = { agent, pid, host, started_at }
```

Filesystem leases remain as cache.

### B. Agent-Level Heartbeats

Allow agents to push heartbeats via MCP instead of filesystem.

### C. Watchdog Agent

A Goose recipe whose only job is:

- Detect stuck tasks
- Analyze logs
- Decide requeue vs fail

### D. Event-Driven Scheduler

Replace cron with:

- Filesystem watcher
- Tinytask pub/sub
- Or MCP streaming

## 10. Why This Approach Is Right for Your System

- Matches Goose's batch execution model
- Aligns with MCP's stateless philosophy
- Avoids premature queue infrastructure
- Human-inspectable (folders + JSON)
- Debuggable with `ps`, `cat`, and logs
- Evolves cleanly toward a daemon or service later

**You're not missing a tool—you're designing a control plane.**

## Next Steps

If you want, next we can:

- Sketch the actual Python scheduler code
- Define the lease schema formally
- Design the tinytask state machine
- Or map this cleanly to a future "agent supervisor" MCP server

This is good architecture work.

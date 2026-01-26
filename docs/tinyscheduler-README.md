# TinyScheduler

A lightweight, file-backed task scheduler for coordinating Goose agent execution based on tinytask queues.

## Quick Start

```bash
# 1. Set up configuration
cp .env.tinyscheduler.example tinyscheduler.env
nano tinyscheduler.env  # Edit configuration

# 2. Validate configuration
./tinyscheduler --env-file tinyscheduler.env validate-config --fix

# 3. Test with dry run
./tinyscheduler --env-file tinyscheduler.env run --once --dry-run

# 4. Run scheduler once
./tinyscheduler --env-file tinyscheduler.env run --once

# 5. Run in daemon mode
./tinyscheduler --env-file tinyscheduler.env run --daemon
```

**Note**: The `--env-file` option must come **before** the subcommand. If omitted, TinyScheduler will auto-discover `.env` in the current directory.

## What is TinyScheduler?

TinyScheduler provides operational control over Goose-based agent execution by implementing:

- **File-backed leases** - Authoritative tracking of in-flight tasks via JSON files
- **Reconciliation loop** - Periodically scans tinytask queues and spawns Goose agents
- **Heartbeat monitoring** - Detects and recovers from stale/orphaned tasks
- **Task blocking awareness** - Respects TinyTask blocking relationships for efficient execution
- **Concurrency control** - Enforces per-agent slot limits
- **Lock file protection** - Prevents overlapping scheduler runs

## Queue Integration

TinyScheduler now features **queue-based task assignment**, allowing intelligent distribution of tasks across agent pools based on queue types (dev, qa, product, etc.). This enables:

- **Automatic task distribution** - Unassigned tasks in queues automatically assigned to available agents
- **Agent pooling** - Multiple agents can service the same queue type
- **Load balancing** - Tasks distributed based on agent capacity
- **Queue isolation** - Dev, QA, and other teams work independently
- **Backward compatibility** - Legacy agent_limits still supported

### How Queue Integration Works

1. **Agent Registry** - Define which agents belong to which queue types
2. **Unassigned Tasks** - TinyScheduler queries tinytask for unassigned tasks by queue
3. **Agent Selection** - Tasks assigned to agents with most available capacity
4. **Automatic Assignment** - Scheduler assigns tasks to agents and spawns wrappers
5. **Already-Assigned Tasks** - Existing assigned tasks continue to work as before

**See**: [Migration Guide](./technical/tinyscheduler-migration-guide.md) for upgrading from legacy mode.

### Task Blocking Support

TinyScheduler respects task blocking relationships from TinyTask, ensuring blocked tasks are not spawned prematurely and blocker tasks are prioritized:

- **Blocked Task Filtering** - Tasks with `is_currently_blocked=true` are automatically skipped
- **Blocker Task Prioritization** - Tasks that block other tasks are spawned first
- **Intelligent Sorting** - Multi-level task sorting: blocker count > priority > creation time
- **Backward Compatible** - Works automatically when TinyTask has blocking enabled, gracefully handles older TinyTask instances
- **Configurable** - Can be disabled via `TINYSCHEDULER_DISABLE_BLOCKING=1` for rollback scenarios

**How It Works**:
1. TinyScheduler queries tasks from TinyTask (which includes blocking metadata)
2. Tasks marked as `is_currently_blocked` are filtered out
3. Remaining tasks are analyzed for blocking relationships
4. Tasks that block others are prioritized for spawning
5. Within each group, tasks are sorted by priority and creation time

**Example**:
```
Tasks:
- Task 1: priority=0, blocks Tasks 2 & 3
- Task 2: priority=10, blocked by Task 1
- Task 3: priority=5, unblocked

Spawn Order:
1. Task 1 (blocker, despite low priority)
2. Task 3 (unblocked, ready to run)
3. Task 2 (skipped - currently blocked)
```

This ensures maximum throughput by completing blocker tasks first, unblocking downstream dependencies faster.

## Architecture

```
┌─────────────────┐
│  Cron/Systemd   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│      Scheduler CLI                      │
│  (src/scheduler/scheduler.py)           │
└────────┬───────────┬──────────┬─────────┘
         │           │          │
         ▼           ▼          ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│ Lease Store │  │Tinytask Client│  │Agent Registry│
│ (filesystem)│  │  (MCP API)   │  │ (JSON file)  │
└────────┬────┘  └──────┬───────┘  └──────┬───────┘
         │              │                 │
         ▼              ▼                 ▼
┌─────────────────────────────────────────────────┐
│     Goose Wrapper                               │
│   (scripts/run_agent.py)                        │
│  - Heartbeat thread                             │
│  - Goose subprocess                             │
│  - Completion tracking                          │
└─────────────────────────────────────────────────┘
```

## Components

### 1. Configuration ([`src/scheduler/config.py`](../src/scheduler/config.py))

Manages environment variables and CLI overrides for all scheduler settings.

### 2. Lease Store ([`src/scheduler/lease.py`](../src/scheduler/lease.py))

CRUD operations on lease files (`state/running/task_*.json`):
- Atomic writes (temp + rename)
- PID liveness checks
- Heartbeat staleness detection
- Automatic reclamation

### 3. Tinytask Client ([`src/scheduler/tinytask_client.py`](../src/scheduler/tinytask_client.py))

HTTP client for tinytask MCP server with:
- Retry logic with exponential backoff
- Task querying by agent
- State updates (running, completed, failed)
- Connection health checks

### 4. Scheduler ([`src/scheduler/scheduler.py`](../src/scheduler/scheduler.py))

Main reconciliation engine:
1. Scan existing leases
2. Reclaim stale leases (dead PID, expired heartbeat)
3. Query tinytask for idle tasks
4. Calculate available slots per agent
5. Spawn Goose wrappers for new tasks

### 5. Goose Wrapper ([`scripts/run_agent.py`](../scripts/run_agent.py))

Manages individual Goose agent lifecycle:
- Creates initial lease
- Spawns Goose subprocess
- Updates heartbeat on background thread
- Captures stdout/stderr
- Updates tinytask with result
- Cleans up lease on exit

## Configuration

### Environment Variables

Key settings (see [`.env.tinyscheduler.example`](../.env.tinyscheduler.example) for complete list):

```bash
# Base path
TINYSCHEDULER_BASE_PATH=/home/user/workspace/calypso

# Agent control file (defines agent registry for queue-based processing)
TINYSCHEDULER_AGENT_CONTROL_FILE=docs/technical/agent-control.json

# Agent limits (JSON or simple format)
TINYSCHEDULER_AGENT_LIMITS='{"dispatcher": 1, "architect": 1}'

# Goose binary
TINYSCHEDULER_GOOSE_BIN=/root/.local/bin/goose

# Tinytask endpoint
TINYSCHEDULER_MCP_ENDPOINT=http://localhost:3000

# Timing (seconds)
TINYSCHEDULER_LOOP_INTERVAL_SEC=60
TINYSCHEDULER_HEARTBEAT_SEC=15
TINYSCHEDULER_MAX_RUNTIME_SEC=3600

# Disable task blocking behavior (for rollback)
TINYSCHEDULER_DISABLE_BLOCKING=false
```

### Agent Control File

The agent control file (`agent-control.json`) defines which agents are available for queue-based task processing. It maps agent names to agent types (queues) for tinytask integration.

**Location**: Defaults to `docs/technical/agent-control.json`, configurable via `TINYSCHEDULER_AGENT_CONTROL_FILE`

**Format**: JSON array of agent objects

```json
[
  {
    "agentName": "vaela",
    "agentType": "dev"
  },
  {
    "agentName": "damien",
    "agentType": "dev"
  },
  {
    "agentName": "oscar",
    "agentType": "qa"
  }
]
```

**Required Fields**:
- `agentName` (string): Unique identifier for the agent
- `agentType` (string): Queue/type name for grouping agents

**Agent Pools**: Multiple agents with the same `agentType` form a pool. Tasks in that queue are distributed across all pool members based on available capacity.

**Validation**: The `validate-config` command checks that:
- File exists and is readable
- Valid JSON syntax
- Array structure with proper objects
- Required fields present in each entry
- No empty values

**Auto-Fix**: Use `validate-config --fix` to automatically create a default agent control file if missing:

```bash
./tinyscheduler validate-config --fix
```

This creates a default file with `dispatcher` (orchestrator) and `architect` (architect) agents.

### Queue-Based Task Assignment

When the agent control file is present, TinyScheduler operates in **queue mode**:

1. **Unassigned Tasks**: For each queue type (dev, qa, etc.):
   - Query tinytask for unassigned tasks in that queue
   - Calculate total available capacity across agent pool
   - Assign tasks to agents with most available slots
   - Spawn wrappers for newly assigned tasks

2. **Already-Assigned Tasks**: For each agent:
   - Query tasks already assigned to that agent
   - Spawn wrappers up to agent's available capacity

3. **Load Balancing**: Tasks distributed to agents with most available capacity, ensuring even workload distribution

**Example Workflow**:
```
Queue: dev (agents: vaela, damien)
- vaela: 1/3 slots used (2 available)
- damien: 0/2 slots used (2 available)
- Unassigned tasks: 5

Result:
- damien gets 2 tasks (reaches capacity)
- vaela gets 2 tasks (3 total, at capacity)
- 1 task remains unassigned (no capacity)
```

### Example Agent Control Configurations

**Small Team** (2-3 agents):
```json
[
  {"agentName": "vaela", "agentType": "dev"},
  {"agentName": "remy", "agentType": "dev"},
  {"agentName": "oscar", "agentType": "qa"}
]
```

**Medium Team** (5-10 agents with multiple queues):
```json
[
  {"agentName": "vaela", "agentType": "dev"},
  {"agentName": "damien", "agentType": "dev"},
  {"agentName": "remy", "agentType": "dev"},
  {"agentName": "oscar", "agentType": "qa"},
  {"agentName": "kalis", "agentType": "qa"},
  {"agentName": "sage", "agentType": "product"}
]
```

**Multi-Queue** (specialized queues):
```json
[
  {"agentName": "vaela", "agentType": "dev"},
  {"agentName": "remy", "agentType": "frontend"},
  {"agentName": "oscar", "agentType": "qa"},
  {"agentName": "blade", "agentType": "infra"},
  {"agentName": "atlas", "agentType": "docs"}
]
```

**See**: [`examples/agent-control-examples/`](../examples/agent-control-examples/) for production-ready examples.

### Legacy Mode (No Agent Control File)

If the agent control file doesn't exist or can't be loaded, TinyScheduler falls back to **legacy mode**:

- Uses only `TINYSCHEDULER_AGENT_LIMITS` configuration
- Queries idle tasks directly by agent name
- No queue-based distribution
- Backward compatible with original implementation

### CLI Overrides

Every environment variable can be overridden via CLI:

```bash
./tinyscheduler run --once \
  --agent-limit dispatcher=2 \
  --agent-limit architect=3 \
  --mcp-endpoint http://localhost:8080 \
  --loop-interval 30 \
  --log-level DEBUG
```

## Usage

### Commands

#### Show Configuration

```bash
# Human-readable
./tinyscheduler config --show

# JSON format
./tinyscheduler config --show --json
```

#### Validate Configuration

```bash
# Check only
./tinyscheduler validate-config

# Check and fix (creates missing directories)
./tinyscheduler validate-config --fix
```

#### Run Scheduler

```bash
# One reconciliation pass (cron-friendly)
./tinyscheduler run --once

# Continuous daemon mode
./tinyscheduler run --daemon

# Dry run (no mutations)
./tinyscheduler run --once --dry-run
```

### Deployment Options

#### Option 1: Cron

```cron
# Every minute
* * * * * cd /home/user/workspace/calypso && ./tinyscheduler run --once
```

See [`docs/deployment/tinyscheduler-cron.example`](./deployment/tinyscheduler-cron.example) for more examples.

#### Option 2: Systemd Daemon

```bash
sudo cp docs/deployment/tinyscheduler.service /etc/systemd/system/
sudo systemctl enable tinyscheduler
sudo systemctl start tinyscheduler
```

#### Option 3: Systemd Timer

```bash
sudo cp docs/deployment/tinyscheduler.timer /etc/systemd/system/
sudo cp docs/deployment/tinyscheduler-oneshot.service /etc/systemd/system/
sudo systemctl enable tinyscheduler.timer
sudo systemctl start tinyscheduler.timer
```

## Monitoring

### Logs

```bash
# Scheduler logs (rotated daily)
tail -f state/logs/scheduler_$(date +%Y%m%d).log

# Systemd journal
sudo journalctl -u tinyscheduler -f

# Specific reconciliation pass
grep "Starting reconciliation" state/logs/scheduler_*.log
```

### Leases

```bash
# List active leases
ls -lh state/running/

# View lease details
cat state/running/task_1234.json

# Count by agent
ls state/running/ | wc -l
```

### Metrics

Key events logged per reconciliation pass:
- Leases scanned
- Leases reclaimed (with reason)
- Tasks spawned
- Blocked tasks skipped
- Errors encountered

Future: JSONL metrics stream for Prometheus scraping.

## Troubleshooting

### Scheduler Won't Start

```bash
# Check lock file
cat state/tinyscheduler.lock
ps aux | grep tinyscheduler

# Remove stale lock if needed
rm state/tinyscheduler.lock
```

### No Tasks Spawning

```bash
# Check configuration
./tinyscheduler config --show | grep -i limit

# Verify tinytask connectivity
curl ${TINYSCHEDULER_MCP_ENDPOINT}/health

# Check for available slots
./tinyscheduler run --once --dry-run
```

### Stale Leases

```bash
# Check for dead PIDs
for lease in state/running/task_*.json; do
  pid=$(jq -r .pid "$lease")
  if ! ps -p $pid > /dev/null; then
    echo "Dead: $lease (PID $pid)"
  fi
done

# Manually clean (use with caution)
rm state/running/task_*.json
```

### Queue Integration Issues

**Agent Control File Not Loading**:
```bash
# Check file exists and is valid JSON
cat $TINYSCHEDULER_AGENT_CONTROL_FILE
python3 -m json.tool $TINYSCHEDULER_AGENT_CONTROL_FILE

# Validate with scheduler
./tinyscheduler validate-config
```

**Tasks Not Being Assigned to Agents**:
```bash
# Check agent registry loaded
./tinyscheduler run --once --dry-run | grep "agent registry"

# Verify queue types match tinytask
# (e.g., if tasks in "dev" queue, ensure agents with agentType "dev")

# Check available capacity
./tinyscheduler run --once --dry-run | grep "available slots"
```

**Queue Type Mismatch**:
- Ensure `agentType` in agent control file matches queue names in tinytask
- Common queue names: `dev`, `qa`, `product`, `infra`, `docs`
- Queue names are case-sensitive

**Load Imbalance Across Agents**:
- Check agent limits configuration - agents may have different capacity
- Review logs for assignment decisions
- Verify no agents repeatedly failing (which would reduce their capacity)

**Blocked Tasks Not Spawning**:
```bash
# Check if tasks are being filtered
./tinyscheduler run --once | grep "Filtered out"

# View blocked task count in summary
./tinyscheduler run --once | grep "Blocked tasks skipped"

# Disable blocking temporarily to test
TINYSCHEDULER_DISABLE_BLOCKING=1 ./tinyscheduler run --once --dry-run
```

See [`docs/technical/tinyscheduler-operations.md`](./technical/tinyscheduler-operations.md) for comprehensive troubleshooting.

## Development

### Running Tests

```bash
# Unit tests (when implemented)
python -m pytest tests/scheduler/

# Integration test (dry run with fixtures)
./tinyscheduler run --once --dry-run
```

### Adding New Agents

1. Add agent limit to configuration:
   ```bash
   TINYSCHEDULER_AGENT_LIMITS='{"dispatcher": 1, "newagent": 2}'
   ```

2. Create recipe file:
   ```bash
   recipes/newagent.yaml
   ```

3. Validate and run:
   ```bash
   ./tinyscheduler validate-config
   ./tinyscheduler run --once --dry-run
   ```

## Design Principles

1. **File-backed state** - Leases are the source of truth, not memory
2. **Stateless scheduler** - No in-memory state between runs
3. **Lock file protection** - Safe for overlapping cron invocations
4. **Graceful degradation** - Continue on transient errors
5. **Observability** - Structured logs for all decisions

## Limitations (Current Implementation)

- **HTTP polling only** - No WebSocket push from tinytask
- **No watchdog** - Manual intervention required for hung tasks
- **Simple recipes** - No dynamic recipe generation
- **Local only** - Single host, no distributed coordination

See technical plan for future enhancements.

## References

- [Architecture](./prompts/tinyscheduler.md) - Design rationale and principles
- [Technical Plan](./technical/tinyscheduler-foundational-plan.md) - Implementation details
- [Operations Guide](./technical/tinyscheduler-operations.md) - Deployment and maintenance
- [Product Story](./product-stories/tinyscheduler-foundational-control-plane.md) - Requirements and acceptance criteria

## License

Part of the Calypso project.

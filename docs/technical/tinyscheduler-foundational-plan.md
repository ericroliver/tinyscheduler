# TinyScheduler Foundational Control Plane Plan

## 1. Scope & Alignment

- **Objective**: Implement the foundational TinyScheduler control plane as described in [`tinyscheduler.md`](workspace/calypso/docs/prompts/tinyscheduler.md:1), focusing on leases, scheduler loop, Goose execution wrapper, and configuration surfaces.
- **Out of Scope (for this slice)**: Watchdog agent, MCP-driven heartbeats, filesystem watchers, or tinytask-native leases (captured as follow-on considerations only).
- **Execution Environment**: All paths resolve relative to the project base path `/home/user/workspace/calypso`, surfaced via configuration so that deployments can override without code edits.

## 2. Base Path, Directories, and Naming

| Concern | Path (relative to base) | Notes |
| --- | --- | --- |
| Base path | `TINYSCHEDULER_BASE_PATH` (default `workspace/calypso`) | Normalized to absolute path at startup |
| Lease directory | `TINYSCHEDULER_RUNNING_DIR` → `${BASE}/state/running` | Scheduler owns lifecycle of `task_{id}.json` leases |
| Logs directory | `TINYSCHEDULER_LOG_DIR` → `${BASE}/state/logs` | Rotated logs for scheduler + wrapper |
| Recipes directory | `TINYSCHEDULER_RECIPES_DIR` → `${BASE}/recipes` | Home for Goose YAML recipes (e.g., [`recipes/product.yaml`](workspace/calypso/recipes/product.yaml:1)) |
| Wrapper scripts | `TINYSCHEDULER_BIN_DIR` → `${BASE}/scripts` | Houses `run_agent.py` and future helpers |
| Tinytask data | `TINYSCHEDULER_TASK_CACHE_DIR` → `${BASE}/state/tasks` | Optional cache for task manifests pulled via MCP |
| PID/lock files | `TINYSCHEDULER_LOCK_FILE` → `${BASE}/state/tinyscheduler.lock` | Prevent overlapping scheduler invocations |

## 3. Configuration Surfaces (Env → CLI Override)

| Setting | Env Var | CLI Flag | Default | Description |
| --- | --- | --- | --- | --- |
| Base path | `TINYSCHEDULER_BASE_PATH` | `--base-path` | `workspace/calypso` | Root used to resolve all relative directories |
| Lease dir | `TINYSCHEDULER_RUNNING_DIR` | `--running-dir` | `${BASE}/state/running` | Where scheduler places lease JSON files |
| Max concurrent per agent | `TINYSCHEDULER_AGENT_LIMITS` | `--agent-limit agent=slots` (repeatable) | YAML/JSON blob `dispatcher:1,...` | Governs simultaneous Goose runs per agent |
| Goose binary path | `TINYSCHEDULER_GOOSE_BIN` | `--goose-bin` | `.local/bin/goose` (seen in editor tabs) | Executable invoked by wrapper |
| Tinytask MCP endpoint | `TINYSCHEDULER_MCP_ENDPOINT` | `--mcp-endpoint` | `http://localhost:port` | REST/WebSocket endpoint for task queries |
| Scheduler interval | `TINYSCHEDULER_LOOP_INTERVAL_SEC` | `--loop-interval` | `60` | Sleep between reconciliation cycles when running as daemon |
| Heartbeat interval | `TINYSCHEDULER_HEARTBEAT_SEC` | `--heartbeat-interval` | `15` | Wrapper heartbeat cadence |
| Max runtime | `TINYSCHEDULER_MAX_RUNTIME_SEC` | `--max-runtime` | `3600` | Lease expiry threshold |
| Log level | `TINYSCHEDULER_LOG_LEVEL` | `--log-level` | `INFO` | Scheduler + wrapper logging level |
| Dry run mode | `TINYSCHEDULER_DRY_RUN` | `--dry-run` | `false` | Enables reconciliation without spawning Goose |

**Implementation Notes**
1. Configuration loader mirrors [`Config.from_env`](workspace/calypso/src/config.py:34) and CLI override pattern established in [`Config.from_cli`](workspace/calypso/src/config.py:88).
2. CLI parser accepts env-var defaults so ops teams can stick with `.env` while engineers override ad hoc.

## 4. Component Responsibilities

| Component | Responsibility | Ownership |
| --- | --- | --- |
| Scheduler CLI (`scheduler.py`) | One-shot reconciliation loop (cron/systemd friendly) | New module under `src/scheduler/` |
| Lease Store | CRUD leases under `running/`, validate PID/heartbeat, mark expirations | Reusable helper | 
| Tinytask client | Query/patch task states via tinytask-MCP API | Thin wrapper (requests + auth) |
| Goose wrapper (`run_agent.py`) | Spawn Goose, update heartbeat, clean lease, push completion status | Script referenced by scheduler |
| Metrics/logging | Structured logs per run, optional JSONL metrics for future Prometheus ingestion | Shared logger config |

## 5. Scheduler Flow

```mermaid
flowchart TD
    Cron[Cron / systemd timer] -->|invoke| Scheduler
    Scheduler --> ScanLeases[Scan running leases]
    ScanLeases --> Validate[Validate PID + heartbeat]
    Validate --> Reclaim[Requeue or fail orphaned tasks]
    Scheduler --> QueryTinytask[Query tinytask for idle tasks per agent]
    QueryTinytask --> SlotCalc[Calculate available slots from agent limits]
    SlotCalc --> Spawn[Spawn Goose wrapper processes]
    Spawn --> CreateLease[Create task_{id}.json lease]
    Spawn --> Monitor[Track subprocess handles]
    Monitor --> UpdateLease[Wrapper updates heartbeat]
    Monitor --> Complete[Wrapper removes lease + updates tinytask]
```

**Key Rules**
1. Never spawn work unless both tinytask status and filesystem lease state agree (per guidance in [`tinyscheduler.md`](workspace/calypso/docs/prompts/tinyscheduler.md:94)).
2. Scheduler remains stateless between runs; leases + tinytask hold truth.
3. All mutations (lease creation, task status updates) happen after successful subprocess spawn to avoid orphan tasks.

## 6. Lease Schema & Lifecycle

```json
{
  "task_id": "1234",
  "agent": "architect",
  "pid": 48291,
  "recipe": "architect.yaml",
  "started_at": "2025-01-28T14:32:11Z",
  "heartbeat": "2025-01-28T14:34:02Z",
  "host": "calypso-dev-01",
  "state": "running"
}
```

- **Create**: Scheduler writes file atomically (`temp + rename`) to avoid partial leases.
- **Update**: Wrapper touches heartbeat every `TINYSCHEDULER_HEARTBEAT_SEC` seconds.
- **Delete**: Wrapper removes lease after tinytask status update (success, failure, requeue).
- **Recovery**: Scheduler reclaims leases if PID not alive or heartbeat older than `max(max_runtime, heartbeat*3)`.

## 7. Goose Wrapper Responsibilities

1. Resolve recipe path under `${BASE}/recipes` and ensure it exists.
2. Fetch task metadata via tinytask client (ID provided by scheduler) to hydrate Goose environment.
3. Spawn Goose command, stream stdout/stderr into structured logs.
4. Heartbeat loop writes timestamp + optional progress metadata back into lease file.
5. Trap SIGTERM/SIGINT to perform best-effort Goose termination, lease cleanup, and tinytask state transition.

## 8. Observability & Safety Nets

- **Logging**: Reuse logger patterns from [`src/logger.py`](workspace/calypso/src/logger.py:1) with new namespaces (`tinyscheduler`, `tinyscheduler.wrapper`).
- **Metrics**: Emit JSON lines per run (`{timestamp, agent, task_id, event}`) for future ingestion.
- **Dry Run**: `--dry-run` surfaces planned spawns (with reasons if blocked) without touching leases or Goose.
- **Lock File**: Scheduler acquires non-blocking lock to prevent overlapping cron invocations.
- **Validation CLI**: `tinyscheduler validate-config` command checks directory existence, parseability of `AGENT_LIMITS`, and tinytask connectivity before enabling cron.

## 9. Implementation Plan (Foundational Slice)

1. **Config & CLI Surface**
   - Implement `TinyschedulerConfig` dataclass.
   - Support `.env` loading (mirroring [`Config.from_env`](workspace/calypso/src/config.py:34)), CLI overrides, and validation (paths, JSON/YAML agent limits, goose binary).
2. **Lease Module**
   - Provide CRUD helpers, PID liveness checks, and stale detection heuristics.
   - Unit tests covering creation, update, expiry, and concurrent access behavior.
3. **Tinytask Client**
   - Minimal wrapper for `list_idle_tasks(agent, limit)` and `update_task_state(task_id, status, metadata)`; resilient to transient HTTP failures with retries.
4. **Scheduler Loop**
   - Implement reconciliation logic, concurrency enforcement, dry-run path, and logging of decisions per agent.
   - Support both one-shot (`--once`) and daemonized loop (sleep between runs).
5. **Goose Wrapper Script**
   - CLI parameters: `--agent`, `--task-id`, `--recipe`, `--config-path`, `--heartbeat-file`.
   - Handles heartbeat updates, subprocess supervision, and result propagation to tinytask.
6. **Operationalization**
   - Provide example cron + systemd snippets referencing `TINYSCHEDULER_BASE_PATH`.
   - Add runbook section to `docs/technical` once implementation stabilizes.

## 10. Risks & Open Questions

| Risk / Question | Mitigation / Next Step |
| --- | --- |
| Tinytask MCP API surface still fluid | Encapsulate calls behind client; document assumptions so future MCP updates require touching one module |
| Goose recipes may need agent-specific env | Allow wrapper to read `TINYSCHEDULER_AGENT_ENV_PREFIX` for agent-specific overrides |
| File permission mismatches on shared hosts | Ensure directories inherit umask; document expectation in deployment guide |
| Future enhancements (watchdog, MCP heartbeats) | Keep lease schema extensible (`state`, `progress` fields) and log format stable |

---

**Next Action**: Review this plan, align on configuration names/defaults, and then author the corresponding product stories under `docs/product-stories/tinyscheduler/` for implementation tracking.

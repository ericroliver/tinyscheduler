# TinyScheduler - AI Agent Guide

## Project Identity

**TinyScheduler** is a lightweight, file-backed task scheduler implementing a **Kubernetes-style reconciliation control plane** for Goose agent execution.

**Mental Model**: Continuously reconcile desired state (tasks in tinytask queues) with actual state (running Goose processes tracked via leases).

**Core Functions**:
- Distribute tasks from tinytask queues to Goose agents
- Track in-flight tasks via file-based leases
- Detect/recover stale/orphaned tasks via heartbeat monitoring
- Enforce per-agent concurrency limits
- Load balance across agent pools

## Architecture

**Reconciliation Loop** (triggered by cron/systemd every ~60s):
1. Scan existing leases in `state/running/`
2. Reclaim stale leases (dead PIDs, expired heartbeats)
3. Query tinytask for idle/unassigned tasks
4. Calculate available agent slots
5. Spawn Goose wrappers for new tasks

## Key Components

**[`scheduler.py`](src/scheduler/scheduler.py)** - Main reconciliation engine with lock file management, lease scanning, and task spawning  
**[`lease.py`](src/scheduler/lease.py)** - File-based lease tracking (`state/running/task_*.json`) with atomic writes and PID checks  
**[`tinytask_client.py`](src/scheduler/tinytask_client.py)** - HTTP client for tinytask MCP server with retry logic  
**[`agent_registry.py`](src/scheduler/agent_registry.py)** - Agent/queue configuration from JSON file (supports agent pooling)  
**[`config.py`](src/scheduler/config.py)** - Environment-based config with CLI overrides

## Queue-Based Task Assignment

**Queue Mode** (when [`agent-control.json`](docs/technical/agent-control.json) exists):
- Agents grouped by type (`dev`, `qa`, `product`, etc.)
- Unassigned tasks distributed to agents with most available capacity
- Load balanced across agent pools

**Legacy Mode** (fallback): Direct agent-to-task mapping via `TINYSCHEDULER_AGENT_LIMITS`

**Agent Control Format**:
```json
[
  {"agentName": "vaela", "agentType": "dev"},
  {"agentName": "oscar", "agentType": "qa"}
]
```

## Design Principles

1. **File-backed state** - Leases are source of truth, not memory
2. **Reconciliation-based** - Idempotent, safe to rerun
3. **Crash-safe** - Atomic file operations (temp + rename)
4. **Observable** - Human-readable JSON, structured logs
5. **MCP-friendly** - HTTP REST, no tight coupling
6. **Simple deployment** - Cron, systemd timer, or daemon mode
7. **Zero external deps** - No Redis, no database

## Operational Modes

```bash
./tinyscheduler run --once         # Single pass (cron-friendly)
./tinyscheduler run --daemon       # Continuous loop
./tinyscheduler run --once --dry-run  # Test without mutations
```

## Critical Constraints

**Always Reconcile** - Never spawn based solely on tinytask OR filesystem; always reconcile both  
**Trust Leases** - File-based state is authoritative, not memory  
**Verify PIDs** - Always check process liveness before trusting lease data  
**Atomic Writes** - Use temp + rename pattern for all file modifications  
**Lock Protection** - Never run multiple scheduler instances simultaneously  
**Handle MCP Failures** - Retry with backoff, don't crash on tinytask unavailability  
**Respect Limits** - Strictly enforce configured concurrency per agent  
**Reclaim Stale** - Tasks without recent heartbeats must be reclaimed

## Key File Locations

- **Source**: [`src/scheduler/`](src/scheduler/) - Core scheduler components
- **Tests**: [`tests/scheduler/`](tests/scheduler/) - Unit and integration tests
- **Config**: [`docs/technical/agent-control.json`](docs/technical/agent-control.json) - Agent registry
- **Runtime State**: `state/running/` - Active leases, `state/logs/` - Scheduler logs
- **Docs**: [`docs/tinyscheduler-README.md`](docs/tinyscheduler-README.md) - Full documentation

## Quick Reference

```bash
./tinyscheduler validate-config --fix    # Check/fix config
./tinyscheduler run --once --dry-run     # Test without changes
./tinyscheduler run --once               # Single reconciliation
./tinyscheduler run --daemon             # Continuous mode
```

## Working with TinyScheduler

This is a **control plane**, not a traditional task queue. Think Kubernetes reconciliation loop:
- Leases are the source of truth (not memory, not database)
- Operations are idempotent and crash-safe
- Always reconcile both filesystem AND tinytask state
- Test with `--dry-run` before making changes
- Keep JSON files human-readable for observability

See [`docs/prompts/tinyscheduler.md`](docs/prompts/tinyscheduler.md) for architectural philosophy and [`docs/technical/tinyscheduler-operations.md`](docs/technical/tinyscheduler-operations.md) for operational details.

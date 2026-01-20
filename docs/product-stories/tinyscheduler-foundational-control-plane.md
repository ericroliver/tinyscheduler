# Product Story: TinyScheduler Foundational Control Plane

## Story Overview

- **Epic**: TinyScheduler
- **Story**: Deliver the foundational scheduler control plane (leases, scheduler loop, Goose wrapper, configuration surfaces)
- **Story Points**: 21
- **Priority**: Critical
- **Status**: Ready for Implementation

## Business Value

Provide operational control over Goose-based agent execution by codifying a lightweight, file-backed scheduler that reconciles tinytask state with on-disk leases. This enables reliable, observable task execution without introducing heavyweight queueing systems, while staying consistent with the architectural direction outlined in [`tinyscheduler.md`](workspace/calypso/docs/prompts/tinyscheduler.md).

## User Story

> As the Calypso operator, I need TinyScheduler to coordinate Goose agents based on tinytask queues with explicit leases and observability so that task execution is predictable, recoverable, and environment-configurable.

## Success Criteria

1. Scheduler loop reconciles tinytask-idle tasks with filesystem leases before spawning new Goose subprocesses.
2. Leases live under `${BASE}/state/running` with authoritative ownership of in-flight tasks.
3. Goose execution is mediated through a wrapper that handles heartbeats, stdout/stderr capture, and lease cleanup.
4. All runtime options default from environment variables but can be overridden via CLI switches.
5. Operators can run the scheduler once (cron) or in daemon mode with interval sleeps.

## Acceptance Criteria

### Configuration & CLI

- ✅ `TinyschedulerConfig` loads defaults from env vars (see [`tinyscheduler-foundational-plan.md`](workspace/calypso/docs/technical/tinyscheduler-foundational-plan.md)) and applies CLI overrides for every setting.
- ✅ `TINYSCHEDULER_BASE_PATH` resolves to `/home/user/workspace/calypso` when unspecified, and every other path is derived relative to this base.
- ✅ Invalid configuration (missing directories, bad agent limit syntax, goose binary not found) fails fast with actionable errors.
- ✅ `tinyscheduler validate-config` command reports success/failure without running the scheduler loop.

### Lease Management

- ✅ Lease files follow the documented schema, are written atomically, and include heartbeat timestamps updated by the wrapper.
- ✅ Scheduler detects orphaned leases when PID is dead or heartbeat exceeds configured thresholds and requeues or fails tasks as specified.
- ✅ Reclamation logic logs each action with task ID, agent, and reason.

### Scheduler Loop

- ✅ One reconciliation pass executes the sequence: scan leases → validate → reclaim → query tinytask per agent → enforce concurrency → spawn wrappers → create leases.
- ✅ `--dry-run` shows planned spawns and skips any mutations.
- ✅ `--daemon` (or interval option) keeps scheduler sleeping between passes while honoring lock-file protection against overlapping runs.

### Goose Wrapper

- ✅ Wrapper CLI accepts `--agent`, `--task-id`, `--recipe`, `--lease-path`, `--heartbeat-interval`, and `--goose-bin` arguments.
- ✅ Wrapper fetches task metadata via tinytask client before invoking Goose.
- ✅ Heartbeat updates occur at the configured cadence until Goose exits.
- ✅ Exit path updates tinytask with success/failure state and removes lease, even when Goose crashes (best-effort cleanup on SIGTERM/SIGINT).

### Observability & Ops

- ✅ Scheduler and wrapper emit structured logs (JSON or key=value) under `${BASE}/state/logs` with human-readable console output when run interactively.
- ✅ Example cron and systemd snippets are documented referencing the env/CLI settings.
- ✅ JSONL metrics stream captures task lifecycle events for future scraping.

## Non-Goals (Documented for Context)

- Watchdog agent, MCP-pushed heartbeats, filesystem watchers, or tinytask-native leases remain future work (tracked separately per plan).

## Implementation Tasks

### Phase 1: Configuration Surface & Validation

1. **Task**: Implement `TinyschedulerConfig` dataclass with env + CLI loaders.
   - Subtasks: `.env` parsing, CLI parser, validation (paths, agent limits, goose binary existence), serialization for logging.
   - Acceptance: `tinyscheduler config --show` prints resolved settings.
2. **Task**: Provide config validation command.
   - Subtasks: CLI entrypoint, exit codes, informative messaging.

### Phase 2: Lease Store Module

1. **Task**: Create `LeaseStore` helper.
   - Subtasks: create/update/delete lease JSON; atomic writes; PID liveness checks; stale detection.
2. **Task**: Unit tests covering create → heartbeat → reclaim flows.

### Phase 3: Tinytask Client Wrapper

1. **Task**: Implement REST/WebSocket client for `list_idle_tasks(agent, limit)` and `update_task_state`.
   - Subtasks: env-configurable endpoint, retries/backoff, structured error handling.
2. **Task**: Mock-based tests verifying success/error paths.

### Phase 4: Scheduler Loop

1. **Task**: Implement reconciliation logic.
   - Subtasks: gather leases, reclaim, query tinytask, slot calculation, spawn orchestration, dry-run guard, logging.
2. **Task**: Lock file & daemon mode support.
   - Subtasks: file locking, interval sleep, graceful shutdown.

### Phase 5: Goose Wrapper Script

1. **Task**: Implement wrapper CLI + heartbeat loop.
   - Subtasks: spawn Goose, stream logs, update lease heartbeat, signal handling, exit status propagation.
2. **Task**: Integrate with tinytask client for state updates.

### Phase 6: Operational Artifacts

1. **Task**: Document cron/systemd usage referencing env vars.
2. **Task**: Provide sample `.env` snippet covering all Tinyscheduler settings alongside CLI examples.

## Dependencies & External Interfaces

- Tinytask MCP server availability and API schema (document assumptions in code comments).
- Goose binary path (default `.local/bin/goose` present per open editor tab).
- Filesystem permissions for `${BASE}/state/**`.

## QA & Validation Strategy

- Unit tests for config parsing, lease lifecycle, and scheduler decision logic (using temp directories and mocked tinytask client).
- Integration smoke test: run scheduler in dry-run mode with seeded tinytask fixtures to ensure logging + decision reporting.
- End-to-end test plan: manually trigger scheduler with a sample agent queue, observe lease creation, Goose execution, and log output.

## Rollout Considerations

- Ship with feature flag (env `TINYSCHEDULER_ENABLED`) defaulting to false until tested in staging.
- Provide rollback instructions: disable cron/systemd unit, clear leases, fall back to manual Goose invocations.

## References

- Architecture guidance: [`tinyscheduler.md`](workspace/calypso/docs/prompts/tinyscheduler.md)
- Technical plan: [`tinyscheduler-foundational-plan.md`](workspace/calypso/docs/technical/tinyscheduler-foundational-plan.md)

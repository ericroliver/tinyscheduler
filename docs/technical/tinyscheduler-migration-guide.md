# TinyScheduler Queue Integration Migration Guide

This guide helps you migrate from legacy mode (simple agent_limits) to queue-based mode (agent registry with queue assignment).

## Overview

TinyScheduler now supports **queue-based task assignment**, which provides:

- Automatic distribution of unassigned tasks across agent pools
- Load balancing based on agent capacity
- Queue isolation (dev, qa, product, etc. operate independently)
- Backward compatibility with legacy mode

**Migration Impact**: LOW - Existing functionality continues to work. Queue integration is purely additive.

## Prerequisites

Before migrating, ensure you have:

- [ ] TinyScheduler installed and working in legacy mode
- [ ] Access to tinytask server with queue/subtask support
- [ ] Understanding of your team's queue structure (dev, qa, etc.)
- [ ] Ability to test in dry-run mode before deploying

## Should You Migrate?

**Migrate if**:
- You use tinytask queues and want automatic task distribution
- You have multiple agents serving the same queue type
- You want load balancing across agent pools
- You need queue isolation between teams

**Stay in legacy mode if**:
- You don't use tinytask queues
- Each agent has a dedicated task list (no pooling needed)
- Current setup meets all your needs

## Migration Steps

### Step 1: Understand Your Current Setup

```bash
# Review current agent limits
./tinyscheduler config --show | grep -A 10 "Agent Limits"

# Example output:
# Agent Limits:
#   dispatcher: 1
#   architect: 1
#   vaela: 3
#   oscar: 2
```

**Document** which agents you have and their capacity limits.

### Step 2: Map Agents to Queue Types

Determine which queue each agent should service. Common mappings:

| Agent Name | Queue Type | Rationale |
|------------|-----------|-----------|
| vaela | dev | Development work |
| damien | dev | Development work |
| oscar | qa | Quality assurance |
| kalis | qa | Quality assurance |
| sage | product | Product management |
| atlas | docs | Documentation |

**Important**: Queue types must match the queue names you use in tinytask.

### Step 3: Create Agent Control File

Create the agent control file at the configured location (default: `docs/technical/agent-control.json`):

```bash
# Check configured path
echo $TINYSCHEDULER_AGENT_CONTROL_FILE

# Create directory if needed
mkdir -p $(dirname $TINYSCHEDULER_AGENT_CONTROL_FILE)

# Create the file
nano $TINYSCHEDULER_AGENT_CONTROL_FILE
```

**Example agent-control.json** (based on your mapping):

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
    },
    {
        "agentName": "kalis",
        "agentType": "qa"
    }
]
```

**Tips**:
- Agent names must match those in `TINYSCHEDULER_AGENT_LIMITS`
- Agent types should match your tinytask queue names
- Multiple agents can have the same type (forming a pool)
- Comments are allowed but ignored by the scheduler

**See**: [`examples/agent-control-examples/`](../../examples/agent-control-examples/) for more examples.

### Step 4: Validate Configuration

```bash
# Run validation (checks syntax and structure)
./tinyscheduler validate-config

# Expected output:
# ✓ Agent control file exists
# ✓ Valid JSON syntax
# ✓ Valid agent registry structure
# ✓ All agents have required fields
```

If validation fails, review error messages and fix issues before proceeding.

### Step 5: Test in Dry Run Mode

Test queue integration without making actual changes:

```bash
# Run once in dry-run mode
./tinyscheduler run --once --dry-run

# Check logs for:
# - "Loaded agent registry from..."
# - "Registered agents: ..."
# - "Agent types (queues): ..."
# - "Processing unassigned tasks by queue..."
```

**Expected Log Output**:
```
INFO - Loaded agent registry from docs/technical/agent-control.json
INFO - Registered agents: vaela, damien, oscar, kalis
INFO - Agent types (queues): dev, qa
INFO - Starting reconciliation pass
INFO - Processing unassigned tasks by queue...
INFO - Processing queue 'dev'...
INFO - Processing queue 'qa'...
```

**Verify**:
- Agent registry loaded successfully
- All agents recognized
- Queue types correct
- No errors in reconciliation logic

### Step 6: Deploy to Production

Once dry-run testing looks good, deploy queue integration:

```bash
# Run once (production)
./tinyscheduler run --once

# Monitor logs for issues
tail -f state/logs/scheduler_$(date +%Y%m%d).log
```

**Watch For**:
- Tasks being assigned to correct agents
- Load distribution across pools
- No unexpected errors

### Step 7: Verify Queue-Based Assignment

Confirm queue integration is working:

```bash
# Check that unassigned tasks get assigned
# (requires tasks in tinytask queues)

# View recent assignments in logs
grep "Assigning task" state/logs/scheduler_*.log | tail -20

# Expected output:
# INFO - Assigning task 1234 to agent 'vaela'
# INFO - Assigning task 1235 to agent 'damien'
# INFO - Assigning task 1236 to agent 'oscar'
```

## Validation Checklist

After migration, verify:

- [ ] Agent registry loads without errors
- [ ] All agents from legacy config are in agent control file
- [ ] Agent limits still enforced correctly
- [ ] Tasks assigned to appropriate queue types
- [ ] Load balanced across agent pools
- [ ] No regression in task processing
- [ ] Dry run mode works
- [ ] Logs show queue-based processing

## Rollback Procedure

If issues arise, you can instantly roll back to legacy mode:

### Option 1: Remove Agent Control File

```bash
# Move agent control file out of the way
mv $TINYSCHEDULER_AGENT_CONTROL_FILE ${TINYSCHEDULER_AGENT_CONTROL_FILE}.backup

# Restart scheduler
# It will automatically fall back to legacy mode
./tinyscheduler run --once
```

**Result**: Scheduler falls back to legacy mode, using only `TINYSCHEDULER_AGENT_LIMITS`.

### Option 2: Use Different Config

```bash
# Run with different base path (no agent control file)
./tinyscheduler run --once --base-path /path/to/legacy/config
```

### Verification After Rollback

```bash
# Check logs for legacy mode message
./tinyscheduler run --once --dry-run 2>&1 | grep -i "agent control"

# Expected output:
# WARNING - Agent control file not found: ...
# WARNING - Queue-based processing will be disabled. Using legacy agent_limits only.
```

## Backward Compatibility

Queue integration is **100% backward compatible**:

### Legacy Mode Preserved

If agent control file is missing or can't be loaded:
- TinyScheduler automatically falls back to legacy mode
- Uses `TINYSCHEDULER_AGENT_LIMITS` as before
- Queries tasks directly by agent name
- No functional changes

### Gradual Migration Supported

You can migrate agents gradually:
- Start with subset of agents in agent control file
- Others continue using legacy mode
- Mix and match as needed during transition

### Configuration Flexibility

Both modes can coexist:
- `TINYSCHEDULER_AGENT_LIMITS` still required (defines capacity)
- Agent control file adds queue-based distribution
- Agent limits apply regardless of mode

## Before/After Examples

### Before Migration (Legacy Mode)

**Configuration**:
```bash
TINYSCHEDULER_AGENT_LIMITS='{"vaela": 3, "oscar": 2}'
```

**Behavior**:
- Scheduler queries tasks for "vaela" directly
- Scheduler queries tasks for "oscar" directly
- No queue-based distribution
- No agent pooling

### After Migration (Queue Mode)

**Configuration**:
```bash
TINYSCHEDULER_AGENT_LIMITS='{"vaela": 3, "damien": 2, "oscar": 2, "kalis": 1}'
TINYSCHEDULER_AGENT_CONTROL_FILE=docs/technical/agent-control.json
```

**agent-control.json**:
```json
[
    {"agentName": "vaela", "agentType": "dev"},
    {"agentName": "damien", "agentType": "dev"},
    {"agentName": "oscar", "agentType": "qa"},
    {"agentName": "kalis", "agentType": "qa"}
]
```

**Behavior**:
- Scheduler queries unassigned tasks in "dev" queue
- Distributes across vaela and damien (pool)
- Scheduler queries unassigned tasks in "qa" queue
- Distributes across oscar and kalis (pool)
- Load balanced within each pool
- Still processes already-assigned tasks

## Common Migration Issues

### Issue 1: Agent Control File Not Found

**Symptom**:
```
WARNING - Agent control file not found: docs/technical/agent-control.json
WARNING - Queue-based processing will be disabled.
```

**Solution**:
```bash
# Check file exists
ls -l $TINYSCHEDULER_AGENT_CONTROL_FILE

# If missing, create it
./tinyscheduler validate-config --fix
```

### Issue 2: JSON Syntax Error

**Symptom**:
```
ERROR - Failed to load agent registry: JSONDecodeError
```

**Solution**:
```bash
# Validate JSON syntax
python3 -m json.tool $TINYSCHEDULER_AGENT_CONTROL_FILE

# Common errors:
# - Missing commas between objects
# - Trailing comma after last object
# - Unquoted strings
# - Single quotes instead of double quotes
```

### Issue 3: Queue Type Mismatch

**Symptom**: Tasks not being assigned despite agent availability.

**Solution**:
- Verify queue names in tinytask match `agentType` in agent control file
- Queue names are case-sensitive ("dev" ≠ "Dev")
- Check tinytask logs for actual queue names

### Issue 4: Agent Name Mismatch

**Symptom**: Agent in agent control file not recognized.

**Solution**:
- Ensure `agentName` matches names in `TINYSCHEDULER_AGENT_LIMITS`
- Agent names are case-sensitive
- Check for typos

### Issue 5: No Load Balancing

**Symptom**: All tasks going to one agent despite multiple agents in pool.

**Solution**:
- Check agent limits - one agent may have much higher capacity
- Review logs for capacity calculation
- Ensure all agents have same `agentType` for the queue

## Testing Strategy

### 1. Unit Testing

```bash
# Run unit tests for agent registry
python -m pytest tests/scheduler/test_agent_registry.py -v

# Run unit tests for queue logic
python -m pytest tests/scheduler/test_scheduler_queue.py -v
```

### 2. Integration Testing

```bash
# Run integration tests
python -m pytest tests/scheduler/test_integration_queue.py -v
```

### 3. Dry Run Testing

```bash
# Test full reconciliation without mutations
./tinyscheduler run --once --dry-run --log-level DEBUG
```

### 4. Production Canary

- Start with one queue/agent pool
- Monitor for 1-2 reconciliation cycles
- Expand to other queues once stable

## Performance Considerations

### Query Optimization

Queue mode may increase tinytask API calls:
- Legacy: N calls (one per agent)
- Queue mode: M + N calls (M queues + N agents)

**Impact**: Minimal for typical deployments (< 10 agents).

### Capacity Calculation

Load balancing requires calculating capacity across all agents in a pool:
- O(n) complexity per queue (n = agents in pool)
- Negligible overhead for reasonable pool sizes

## Next Steps

After successful migration:

1. **Monitor** - Watch logs for assignment patterns
2. **Tune** - Adjust agent limits based on workload
3. **Optimize** - Add/remove agents from pools as needed
4. **Document** - Update team docs with new queue structure

## Additional Resources

- [TinyScheduler README](../tinyscheduler-README.md) - Full documentation
- [Operations Guide](./tinyscheduler-operations.md) - Day-to-day operations
- [Example Configurations](../../examples/agent-control-examples/) - Production-ready examples
- [Technical Plan](./tinyscheduler-queue-integration.md) - Implementation details

## Support

If you encounter issues during migration:

1. Check logs: `state/logs/scheduler_*.log`
2. Run validation: `./tinyscheduler validate-config`
3. Test in dry-run: `./tinyscheduler run --once --dry-run`
4. Review this guide's troubleshooting section
5. Consult [Operations Guide](./tinyscheduler-operations.md)

## Glossary

- **Queue**: Team/functional area in tinytask (dev, qa, product)
- **Agent Type**: Synonym for queue in agent control file
- **Agent Pool**: All agents with the same type/queue
- **Legacy Mode**: Original TinyScheduler behavior (no queue integration)
- **Queue Mode**: New behavior with agent registry and queue-based assignment
- **Unassigned Task**: Task in queue without an assigned agent
- **Load Balancing**: Distributing tasks across agents based on available capacity

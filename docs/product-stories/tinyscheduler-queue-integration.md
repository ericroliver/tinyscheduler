# Product Story: TinyScheduler Queue Integration

## Overview

Update TinyScheduler to work with tinytask's new queue and assignee model, enabling intelligent matching of unassigned tasks to available agents based on agent type/queue.

## Background

TinyTask has been updated with two key features:
1. **Queues** (team/functional areas): `dev`, `qa`, `product`, `architect`
2. **Assignee** (individual agents): `vaela`, `damien`, `oscar`, `kalis`, etc.

Tasks can now be:
- In a queue but unassigned (ready for any agent of that type)
- Assigned to a specific agent (for directed work)
- Both (assigned agent within a queue context)

**Key Concept**: `queue_name` in tinytask = `agentType` in agent control file

## Goals

1. Enable TinyScheduler to match unassigned tasks to available agents of the appropriate type
2. Introduce agent control file for centralized agent configuration
3. Maintain backward compatibility during migration
4. Improve resource utilization through intelligent task distribution

## Success Criteria

- ✅ TinyScheduler can process unassigned tasks from queues
- ✅ Tasks are assigned to agents based on availability and type
- ✅ Already-assigned tasks continue to work as before
- ✅ Agent control file provides single source of truth for agent configuration
- ✅ Backward compatibility maintained for existing deployments
- ✅ All existing tests pass
- ✅ New integration tests cover queue-based scenarios

## Technical Reference

See [TinyScheduler Queue Integration Technical Plan](../technical/tinyscheduler-queue-integration.md) for detailed architecture and implementation details.

---

## Story 1: Agent Registry Foundation

### Description
Create the `AgentRegistry` class to load and manage agent configurations from the agent control file. This provides the foundation for queue-based task assignment.

### Acceptance Criteria

#### AC1: AgentRegistry Class Implementation
- ✅ Create [`src/scheduler/agent_registry.py`](../../src/scheduler/agent_registry.py)
- ✅ Implement `AgentConfig` dataclass with `agent_name` and `agent_type` fields
- ✅ Implement `AgentRegistry` class with methods:
  - `get_agents_by_type(agent_type: str) -> List[str]`
  - `get_agent_type(agent_name: str) -> Optional[str]`
  - `get_all_types() -> List[str]`
  - `get_all_agent_names() -> List[str]`
  - `reload()`

#### AC2: Agent Control File Loading
- ✅ Load JSON array from agent control file
- ✅ Parse each entry into `AgentConfig` objects
- ✅ Build indexes by type and by name for fast lookup
- ✅ Raise `FileNotFoundError` if control file missing
- ✅ Raise appropriate error if JSON is malformed

#### AC3: Error Handling
- ✅ Handle missing file gracefully with clear error message
- ✅ Handle malformed JSON with descriptive error
- ✅ Handle missing required fields (agentName, agentType)
- ✅ Log warnings for unexpected fields (forward compatibility)

#### AC4: Unit Tests
- ✅ Test successful loading of valid control file
- ✅ Test error handling for missing file
- ✅ Test error handling for invalid JSON
- ✅ Test error handling for missing required fields
- ✅ Test index building (by type and by name)
- ✅ Test all query methods
- ✅ Test reload functionality

### Implementation Notes

**File Structure**:
```
src/scheduler/
  agent_registry.py    # NEW: Agent registry class
tests/scheduler/
  test_agent_registry.py    # NEW: Unit tests
```

**Example Usage**:
```python
from src.scheduler.agent_registry import AgentRegistry

registry = AgentRegistry(Path("docs/technical/agent-control.json"))

# Get all dev agents
dev_agents = registry.get_agents_by_type("dev")  # ["vaela", "damien"]

# Get agent type
agent_type = registry.get_agent_type("oscar")  # "qa"

# Get all queue types
queues = registry.get_all_types()  # ["dev", "qa", "architect"]
```

### Testing Scenarios

1. **Valid Control File**: Load sample control file, verify indexes
2. **Missing File**: Attempt to load non-existent file, verify error
3. **Malformed JSON**: Load file with syntax errors, verify error
4. **Missing Fields**: Load file with entries missing required fields
5. **Empty File**: Load file with empty array `[]`
6. **Single Agent**: Load file with one agent
7. **Multiple Types**: Load file with agents across multiple types
8. **Duplicate Agents**: Load file with duplicate agent names (should handle gracefully)

---

## Story 2: Enhanced Tinytask Client

### Description
Extend the `TinytaskClient` class with new methods to support queue-based queries and task assignment operations needed for the queue integration.

### Acceptance Criteria

#### AC1: get_queue_tasks() Method
- ✅ Implement `get_queue_tasks(queue_name, assigned_to=None, status=None, limit=100)`
- ✅ Call tinytask MCP tool `get_queue_tasks` with appropriate filters
- ✅ Parse response into list of `Task` objects
- ✅ Return empty list on error (with warning log)
- ✅ Support optional assignee filter
- ✅ Support optional status filter

#### AC2: get_unassigned_in_queue() Method
- ✅ Implement `get_unassigned_in_queue(queue_name, limit=100)`
- ✅ Call tinytask MCP tool `get_unassigned_in_queue`
- ✅ Parse response into list of `Task` objects
- ✅ Return empty list on error (with warning log)
- ✅ Respect limit parameter

#### AC3: assign_task() Method
- ✅ Implement `assign_task(task_id, agent)`
- ✅ Call tinytask MCP tool `update_task` with `assigned_to` parameter
- ✅ Return `True` on success, `False` on failure
- ✅ Log warning on failure

#### AC4: Error Handling
- ✅ Handle connection errors gracefully
- ✅ Handle API errors gracefully
- ✅ Return empty lists/False rather than raising exceptions
- ✅ Log warnings for all failures

#### AC5: Unit Tests
- ✅ Test `get_queue_tasks()` with valid response
- ✅ Test `get_queue_tasks()` with filters
- ✅ Test `get_queue_tasks()` with connection error
- ✅ Test `get_unassigned_in_queue()` with valid response
- ✅ Test `get_unassigned_in_queue()` with error
- ✅ Test `assign_task()` success case
- ✅ Test `assign_task()` failure case

### Implementation Notes

**File Updates**:
```
src/scheduler/
  tinytask_client.py    # UPDATE: Add new methods
tests/scheduler/
  test_tinytask_client.py    # UPDATE: Add tests for new methods
```

**Method Signatures**:
```python
def get_queue_tasks(
    self,
    queue_name: str,
    assigned_to: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
) -> List[Task]:
    """Get tasks in a queue with optional filters."""
    pass

def get_unassigned_in_queue(
    self,
    queue_name: str,
    limit: int = 100
) -> List[Task]:
    """Get unassigned tasks in a queue."""
    pass

def assign_task(
    self,
    task_id: str,
    agent: str
) -> bool:
    """Assign a task to an agent."""
    pass
```

### Testing Scenarios

1. **Queue Tasks - Success**: Query queue with tasks, verify parsing
2. **Queue Tasks - Empty**: Query queue with no tasks
3. **Queue Tasks - With Filters**: Query with assignee/status filters
4. **Queue Tasks - Error**: Simulate connection error
5. **Unassigned Tasks - Success**: Query unassigned tasks
6. **Unassigned Tasks - Empty**: Query queue with all tasks assigned
7. **Assign Task - Success**: Assign task to agent
8. **Assign Task - Failure**: Simulate API error during assignment

### Dependencies
- Requires tinytask MCP server to implement:
  - `get_queue_tasks` tool
  - `get_unassigned_in_queue` tool
  - `update_task` tool with `assigned_to` parameter

---

## Story 3: Queue-Based Scheduler Logic

### Description
Update the scheduler's reconciliation logic to use queue-based queries, intelligently matching unassigned tasks to available agents while maintaining support for already-assigned tasks.

### Acceptance Criteria

#### AC1: Initialize Agent Registry
- ✅ Load `AgentRegistry` in `Scheduler.__init__()`
- ✅ Use configurable path with sensible default
- ✅ Log agent configuration on startup
- ✅ Handle missing agent control file gracefully

#### AC2: Process Unassigned Tasks by Queue
- ✅ Implement `_process_unassigned_tasks(stats)` method
- ✅ Iterate through all queue types from agent registry
- ✅ For each queue:
  - Calculate total available slots across agent pool
  - Query unassigned tasks in queue
  - Assign tasks to agents with most available capacity
  - Spawn Goose wrappers for assigned tasks
  - Update stats (unassigned_matched, tasks_spawned, errors)

#### AC3: Process Already-Assigned Tasks
- ✅ Implement `_process_assigned_tasks(stats)` method
- ✅ Iterate through all agents from registry
- ✅ For each agent:
  - Calculate available slots
  - Query idle tasks assigned to agent
  - Spawn Goose wrappers up to available slots
  - Update stats (assigned_spawned, tasks_spawned, errors)

#### AC4: Update reconcile_once()
- ✅ Modify `reconcile_once()` to call new methods
- ✅ Maintain existing lease scanning and reclamation
- ✅ Add queue-based processing steps
- ✅ Update stats tracking with new metrics
- ✅ Log summary with new metrics

#### AC5: Agent Selection Strategy
- ✅ Select agent with most available capacity for each task
- ✅ Update capacity tracking as tasks are assigned
- ✅ Handle edge cases (all agents full, no agents in pool)

#### AC6: Dry Run Support
- ✅ Respect `config.dry_run` flag
- ✅ Log intended actions without mutations
- ✅ Show which agent would be selected for each task

#### AC7: Error Handling
- ✅ Continue processing on individual task failures
- ✅ Log errors clearly
- ✅ Track error count in stats
- ✅ Don't crash entire reconciliation on errors

#### AC8: Unit Tests
- ✅ Test `_process_unassigned_tasks()` with multiple queues
- ✅ Test `_process_assigned_tasks()` with multiple agents
- ✅ Test agent selection strategy (least-loaded first)
- ✅ Test capacity tracking and slot management
- ✅ Test dry run mode
- ✅ Test error handling
- ✅ Test empty queues and unavailable agents

### Implementation Notes

**File Updates**:
```
src/scheduler/
  scheduler.py    # UPDATE: Major changes to reconciliation logic
tests/scheduler/
  test_scheduler_queue.py    # NEW: Tests for queue-based logic
```

**Key Algorithm**:
```python
def _process_unassigned_tasks(self, stats):
    for queue_name in self.agent_registry.get_all_types():
        agent_pool = self.agent_registry.get_agents_by_type(queue_name)
        
        # Calculate total slots
        available_by_agent = {}
        for agent in agent_pool:
            slots = self._calculate_available_slots(agent)
            available_by_agent[agent] = slots
        
        total_slots = sum(available_by_agent.values())
        
        if total_slots > 0:
            tasks = self.tinytask_client.get_unassigned_in_queue(queue_name, total_slots)
            
            for task in tasks:
                best_agent = self._select_best_agent(available_by_agent)
                
                if self.tinytask_client.assign_task(task.task_id, best_agent):
                    if self._spawn_wrapper(task.task_id, best_agent, recipe):
                        available_by_agent[best_agent] -= 1
                        stats['tasks_spawned'] += 1
                        stats['unassigned_matched'] += 1
```

### Testing Scenarios

1. **Single Queue**: One queue with multiple unassigned tasks
2. **Multiple Queues**: Multiple queues with different agent pools
3. **Mixed Capacity**: Some agents full, some available
4. **No Capacity**: All agents at max capacity
5. **Assigned Tasks Only**: No unassigned tasks, only assigned
6. **Mixed Tasks**: Both unassigned and assigned tasks
7. **Empty Queues**: Queues with no tasks
8. **Spawn Failures**: Handle wrapper spawn failures gracefully
9. **Assignment Failures**: Handle tinytask assignment failures

### Dependencies
- Story 1: Agent Registry Foundation
- Story 2: Enhanced Tinytask Client

---

## Story 4: Configuration and Validation

### Description
Add configuration support for agent control file path and implement validation to ensure the file exists and is valid before scheduler starts.

### Acceptance Criteria

#### AC1: Configuration
- ✅ Add `agent_control_file` property to `TinySchedulerConfig`
- ✅ Support `TINYSCHEDULER_AGENT_CONTROL_FILE` environment variable
- ✅ Support both absolute and relative paths (relative to base_path)
- ✅ Priority: env var → `{base_path}/config/agent-control.json` → `{base_path}/agent-control.json`
- ✅ Document in `.env.tinyscheduler.example`

#### AC2: Validation Function
- ✅ Create `validate_agent_control_file(config, fix=False)` function
- ✅ Check if file exists
- ✅ Validate JSON syntax
- ✅ Validate structure (array of objects)
- ✅ Validate required fields (agentName, agentType)
- ✅ Return list of validation messages

#### AC3: Auto-Fix Support
- ✅ If `fix=True` and file missing, create default file
- ✅ Default file includes at least dispatcher and architect agents
- ✅ Log creation message

#### AC4: Integrate into validate-config Command
- ✅ Add agent control file validation to existing validation flow
- ✅ Run validation on `./tinyscheduler validate-config`
- ✅ Support `--fix` flag to create missing file
- ✅ Display validation results clearly

#### AC5: Documentation
- ✅ Update README with agent control file section
- ✅ Update `.env.tinyscheduler.example` with new variable
- ✅ Document validation command usage
- ✅ Provide example agent control file

#### AC6: Tests
- ✅ Test config property with env variable
- ✅ Test config property with default
- ✅ Test validation with valid file
- ✅ Test validation with missing file
- ✅ Test validation with invalid JSON
- ✅ Test validation with missing fields
- ✅ Test auto-fix creates valid file

### Implementation Notes

**File Updates**:
```
src/scheduler/
  config.py    # UPDATE: Add agent_control_file property
  cli.py    # UPDATE: Integrate validation into validate-config
docs/
  tinyscheduler-README.md    # UPDATE: Document agent control file
.env.tinyscheduler.example    # UPDATE: Add new variable
tests/scheduler/
  test_config.py    # UPDATE: Add tests for new property
  test_validation.py    # NEW or UPDATE: Validation tests
```

**Default Agent Control File**:
```json
[
  {
    "agentName": "dispatcher",
    "agentType": "orchestrator"
  },
  {
    "agentName": "architect",
    "agentType": "architect"
  }
]
```

### Testing Scenarios

1. **Config - Env Variable**: Set env var, verify path
2. **Config - Default**: No env var, verify default path
3. **Validation - Valid File**: Validate correct file
4. **Validation - Missing File**: Missing file, no fix
5. **Validation - Missing File with Fix**: Missing file, auto-create
6. **Validation - Invalid JSON**: File with syntax error
7. **Validation - Missing Fields**: Valid JSON, missing agentName
8. **Validation - Empty Array**: Valid JSON, empty array

### Dependencies
- Story 1: Agent Registry Foundation

---

## Story 5: Integration Testing and Documentation

### Description
Create comprehensive integration tests for queue-based scenarios and update all documentation to reflect the new queue integration capabilities.

### Acceptance Criteria

#### AC1: Integration Tests
- ✅ Create end-to-end test suite for queue scenarios
- ✅ Test scenarios:
  - Unassigned tasks distributed across agent pool
  - Already-assigned tasks processed correctly
  - Mixed scenarios (some assigned, some unassigned)
  - Multiple queues processed in sequence
  - Capacity limits respected
  - Dry run mode works correctly

#### AC2: Mock Tinytask Server
- ✅ Create mock MCP server for testing (if not exists)
- ✅ Implement `get_queue_tasks` tool
- ✅ Implement `get_unassigned_in_queue` tool
- ✅ Implement `update_task` with `assigned_to` support
- ✅ Maintain state for test assertions

#### AC3: README Updates
- ✅ Add "Queue Integration" section to [`tinyscheduler-README.md`](../../docs/tinyscheduler-README.md)
- ✅ Document agent control file format and location
- ✅ Update architecture diagram to show agent registry
- ✅ Add example configurations
- ✅ Update troubleshooting section

#### AC4: Migration Guide
- ✅ Create migration guide document
- ✅ Document how to create agent control file
- ✅ Provide migration checklist
- ✅ Include before/after examples
- ✅ Document rollback procedure

#### AC5: Example Configurations
- ✅ Provide example agent control files for common scenarios
- ✅ Small team (2-3 agents)
- ✅ Medium team (5-10 agents)
- ✅ Multiple queues with specialized agents

#### AC6: Operations Guide Updates
- ✅ Update [`tinyscheduler-operations.md`](../../docs/technical/tinyscheduler-operations.md)
- ✅ Add queue monitoring section
- ✅ Add agent pool management
- ✅ Update troubleshooting for queue scenarios
- ✅ Document common issues and solutions

### Implementation Notes

**New/Updated Files**:
```
tests/scheduler/
  test_integration_queue.py    # NEW: Integration tests
  fixtures/
    agent-control-small.json    # NEW: Example config
    agent-control-medium.json    # NEW: Example config
docs/
  tinyscheduler-README.md    # UPDATE: Add queue integration docs
  technical/
    tinyscheduler-migration-guide.md    # NEW: Migration guide
    tinyscheduler-operations.md    # UPDATE: Queue operations
examples/
  agent-control-examples/    # NEW: Example configurations
    small-team.json
    medium-team.json
    multi-queue.json
```

**Integration Test Example**:
```python
def test_unassigned_task_distribution():
    """Test that unassigned tasks are distributed to available agents."""
    # Setup: Create unassigned tasks in dev queue
    # Setup: Configure 2 dev agents with available capacity
    # Execute: Run reconciliation
    # Assert: Tasks assigned to both agents
    # Assert: Load balanced based on capacity
```

### Testing Scenarios

1. **Basic Queue Processing**: Single queue, multiple unassigned tasks
2. **Multi-Queue**: Multiple queues processed in sequence
3. **Capacity Limits**: Verify slots respected across pool
4. **No Available Agents**: All agents at capacity
5. **Partial Capacity**: Some agents available, some full
6. **Assignment Priority**: Already-assigned tasks processed
7. **Error Recovery**: Handle tinytask errors gracefully
8. **Dry Run End-to-End**: Verify no mutations in dry run

### Documentation Checklist

- ✅ README updated with queue integration section
- ✅ Migration guide created
- ✅ Operations guide updated
- ✅ Example configurations provided
- ✅ Troubleshooting guide updated
- ✅ Technical plan linked from README
- ✅ API documentation updated (if applicable)

### Dependencies
- Story 1: Agent Registry Foundation
- Story 2: Enhanced Tinytask Client
- Story 3: Queue-Based Scheduler Logic
- Story 4: Configuration and Validation

---

## Rollout Plan

### Phase 1: Foundation (Stories 1-2)
- **Duration**: 3-5 days
- **Goal**: Build core components without touching scheduler logic
- **Deliverables**: Agent registry, enhanced client
- **Risk**: Low - isolated changes

### Phase 2: Core Logic (Story 3)
- **Duration**: 5-7 days
- **Goal**: Implement queue-based reconciliation
- **Deliverables**: Updated scheduler with queue support
- **Risk**: Medium - core logic changes

### Phase 3: Integration (Stories 4-5)
- **Duration**: 3-5 days
- **Goal**: Complete integration with configuration and docs
- **Deliverables**: Full queue integration with docs
- **Risk**: Low - polish and documentation

### Total Estimated Duration: 11-17 days

## Success Metrics

### Functional Metrics
- ✅ All unassigned tasks assigned to appropriate agents
- ✅ Task distribution balanced across agent pool
- ✅ Zero task assignment conflicts
- ✅ Already-assigned tasks continue to work

### Performance Metrics
- ✅ Reconciliation time < 10 seconds for 100 tasks
- ✅ Agent selection algorithm O(n) complexity
- ✅ No performance regression vs. old implementation

### Reliability Metrics
- ✅ 100% backward compatibility (old configs still work)
- ✅ Zero crashes during migration
- ✅ All existing tests pass
- ✅ 90%+ test coverage on new code

## Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Tinytask MCP tools not ready | High | Medium | Implement mock server; staged rollout |
| Agent control file sync issues | Medium | Low | Validation on startup; reload command |
| Performance degradation | Medium | Low | Benchmark tests; optimize queries |
| Task assignment conflicts | High | Low | Use atomic operations; add detection |
| Breaking changes to existing deployments | High | Low | Maintain backward compatibility |

## Future Enhancements

### Post-MVP Features
1. **Hot Reload**: Detect agent control file changes without restart
2. **Queue Priority**: Priority ordering for queue processing
3. **Advanced Selection**: Weighted agent selection based on performance
4. **Agent Capabilities**: Match tasks to agents based on skills/tags
5. **Metrics Dashboard**: Real-time queue and agent metrics
6. **Auto-Scaling**: Dynamic agent limit adjustment based on queue depth

### Data Model Extensions
```json
{
  "agentName": "vaela",
  "agentType": "dev",
  "maxConcurrency": 3,
  "enabled": true,
  "priority": 10,
  "capabilities": ["typescript", "python"],
  "workingHours": {
    "timezone": "America/New_York",
    "start": "09:00",
    "end": "17:00"
  }
}
```

## Appendix

### Related Documents
- [Technical Plan](../technical/tinyscheduler-queue-integration.md)
- [Tinytask Subtasks Spec](../technical/tinytask-subtasks.md)
- [TinyScheduler README](../tinyscheduler-README.md)
- [Agent Control File](../technical/agent-control.json)

### Glossary
- **Queue**: Team/functional area in tinytask (dev, qa, product)
- **Agent Type**: Synonym for queue in agent control file
- **Agent**: Individual worker (vaela, damien, oscar)
- **Assignee**: Individual agent assigned to a task
- **Agent Pool**: All agents of a specific type
- **Slot**: Available concurrency slot for an agent
- **Reconciliation**: One pass of the scheduler loop

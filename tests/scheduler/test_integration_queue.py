"""Integration tests for queue-based TinyScheduler functionality.

This module tests end-to-end scenarios for the queue integration, including:
- Unassigned task distribution across agent pools
- Already-assigned task processing
- Mixed assignment scenarios
- Multiple queue processing
- Capacity limit enforcement
- Dry run mode
- Error handling in full reconciliation flow
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from typing import Dict, List

from src.scheduler.scheduler import Scheduler
from src.scheduler.config import TinySchedulerConfig
from src.scheduler.tinytask_client import Task, TinytaskClientError
from src.scheduler.agent_registry import AgentRegistry


@pytest.fixture
def base_config(tmp_path):
    """Create a base scheduler configuration for integration tests."""
    base_path = tmp_path / "scheduler"
    base_path.mkdir()
    
    # Create required directories
    (base_path / "state" / "running").mkdir(parents=True)
    (base_path / "state" / "logs").mkdir(parents=True)
    (base_path / "state" / "tasks").mkdir(parents=True)
    (base_path / "recipes").mkdir(parents=True)
    (base_path / "scripts").mkdir(parents=True)
    
    # Create a mock goose binary
    goose_bin = base_path / "goose"
    goose_bin.touch()
    goose_bin.chmod(0o755)
    
    # Create agent control file
    agent_control_file = base_path / "agent-control.json"
    
    config = TinySchedulerConfig(
        base_path=base_path,
        running_dir=base_path / "state" / "running",
        log_dir=base_path / "state" / "logs",
        recipes_dir=base_path / "recipes",
        bin_dir=base_path / "scripts",
        task_cache_dir=base_path / "state" / "tasks",
        lock_file=base_path / "state" / "tinyscheduler.lock",
        agent_control_file=agent_control_file,
        agent_limits={"vaela": 3, "damien": 2, "oscar": 2, "kalis": 1},
        goose_bin=goose_bin,
        mcp_endpoint="http://localhost:3000",
        loop_interval_sec=60,
        heartbeat_interval_sec=15,
        max_runtime_sec=3600,
        dry_run=False,
        log_level="INFO",
        enabled=True,
        hostname="test-host"
    )
    
    # Create recipe files for all agents
    for agent in ["vaela", "damien", "oscar", "kalis"]:
        recipe_file = config.recipes_dir / f"{agent}.yaml"
        recipe_file.write_text(f"# Recipe for {agent}")
    
    return config


@pytest.fixture
def agent_control_file(base_config):
    """Create and populate agent control file."""
    import json
    
    agents = [
        {"agentName": "vaela", "agentType": "dev"},
        {"agentName": "damien", "agentType": "dev"},
        {"agentName": "oscar", "agentType": "qa"},
        {"agentName": "kalis", "agentType": "qa"}
    ]
    
    base_config.agent_control_file.write_text(json.dumps(agents, indent=2))
    return base_config.agent_control_file


class TestUnassignedTaskDistribution:
    """Test scenarios for distributing unassigned tasks across agent pools."""
    
    def test_unassigned_tasks_distributed_across_pool(self, base_config, agent_control_file):
        """Test that unassigned tasks are distributed across available agents in a pool."""
        with patch('src.scheduler.scheduler.TinytaskClient') as MockClient:
            # Setup scheduler
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: No existing leases
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: 3 unassigned tasks in dev queue
            dev_tasks = [
                Task(task_id="task-1", agent="", status="idle", recipe="vaela.yaml"),
                Task(task_id="task-2", agent="", status="idle", recipe="damien.yaml"),
                Task(task_id="task-3", agent="", status="idle", recipe="vaela.yaml")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks,
                "qa": []
            }.get(q, []))
            
            # Track assignments
            assignments = []
            def track_assignment(task_id, agent):
                assignments.append((task_id, agent))
                return True
            
            mock_client.assign_task = Mock(side_effect=track_assignment)
            mock_client.list_idle_tasks = Mock(return_value=[])
            
            # Mock spawn wrapper
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute reconciliation
            stats = scheduler.reconcile()
            
            # Verify: All tasks were matched and assigned
            assert stats['unassigned_matched'] == 3
            assert stats['tasks_spawned'] == 3
            assert stats['errors'] == 0
            
            # Verify: Tasks distributed across both dev agents
            assigned_agents = [agent for _, agent in assignments]
            assert 'vaela' in assigned_agents
            assert 'damien' in assigned_agents
            
            # Verify: Assignments were made
            assert mock_client.assign_task.call_count == 3
    
    def test_load_balancing_across_agents(self, base_config, agent_control_file):
        """Test that tasks are load balanced based on available capacity."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: One agent has 1 active task, the other has none
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={
                "vaela": 1,  # 2 slots available (limit 3)
                "damien": 0   # 2 slots available (limit 2)
            })
            
            # Mock: 4 unassigned tasks
            dev_tasks = [
                Task(task_id=f"task-{i}", agent="", status="idle") 
                for i in range(1, 5)
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks,
                "qa": []
            }.get(q, []))
            
            assignments = []
            def track_assignment(task_id, agent):
                assignments.append((task_id, agent))
                # Update active counts after assignment
                if agent == "vaela":
                    scheduler.lease_store.count_active_by_agent.return_value["vaela"] += 1
                elif agent == "damien":
                    scheduler.lease_store.count_active_by_agent.return_value["damien"] += 1
                return True
            
            mock_client.assign_task = Mock(side_effect=track_assignment)
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: 4 tasks assigned
            assert stats['unassigned_matched'] == 4
            
            # Verify: Load balanced - vaela gets 2 (to reach capacity of 3),
            # damien gets 2 (to reach capacity of 2)
            agent_counts = {}
            for _, agent in assignments:
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
            
            assert agent_counts.get('vaela', 0) == 2
            assert agent_counts.get('damien', 0) == 2


class TestAlreadyAssignedTasks:
    """Test scenarios for processing already-assigned tasks."""
    
    def test_already_assigned_tasks_processed_correctly(self, base_config, agent_control_file):
        """Test that already-assigned tasks are spawned for the correct agent only."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: No active leases
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: No unassigned tasks
            mock_client.get_unassigned_in_queue = Mock(return_value=[])
            
            # Mock: Idle tasks already assigned to specific agents
            def get_idle_tasks(agent, limit):
                tasks_by_agent = {
                    "vaela": [
                        Task(task_id="task-v1", agent="vaela", status="idle"),
                        Task(task_id="task-v2", agent="vaela", status="idle")
                    ],
                    "oscar": [
                        Task(task_id="task-o1", agent="oscar", status="idle")
                    ]
                }
                return tasks_by_agent.get(agent, [])[:limit]
            
            mock_client.list_idle_tasks = Mock(side_effect=get_idle_tasks)
            
            # Track spawns
            spawns = []
            def track_spawn(task_id, agent, recipe):
                spawns.append((task_id, agent))
                return True
            
            scheduler._spawn_wrapper = Mock(side_effect=track_spawn)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Correct number of tasks spawned
            assert stats['assigned_spawned'] == 3
            assert stats['tasks_spawned'] == 3
            
            # Verify: Tasks spawned for correct agents only
            assert ('task-v1', 'vaela') in spawns
            assert ('task-v2', 'vaela') in spawns
            assert ('task-o1', 'oscar') in spawns
    
    def test_respects_agent_capacity_for_assigned_tasks(self, base_config, agent_control_file):
        """Test that assigned tasks respect agent capacity limits."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Oscar at capacity (2/2)
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={
                "oscar": 2  # At capacity
            })
            
            mock_client.get_unassigned_in_queue = Mock(return_value=[])
            
            # Mock: Oscar has 3 idle tasks waiting (but capacity for 0 more)
            def get_idle_tasks(agent, limit):
                if agent == "oscar":
                    return [
                        Task(task_id=f"task-o{i}", agent="oscar", status="idle")
                        for i in range(1, 4)
                    ]
                return []
            
            mock_client.list_idle_tasks = Mock(side_effect=get_idle_tasks)
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: No tasks spawned (oscar at capacity)
            assert stats['assigned_spawned'] == 0
            assert scheduler._spawn_wrapper.call_count == 0


class TestMixedAssignmentScenarios:
    """Test scenarios with both assigned and unassigned tasks."""
    
    def test_mixed_assigned_and_unassigned_tasks(self, base_config, agent_control_file):
        """Test processing of both assigned and unassigned tasks in same reconciliation."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean slate
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: Unassigned tasks in dev queue
            dev_unassigned = [
                Task(task_id="unassigned-1", agent="", status="idle"),
                Task(task_id="unassigned-2", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_unassigned,
                "qa": []
            }.get(q, []))
            
            # Mock: Already assigned tasks
            def get_idle_tasks(agent, limit):
                if agent == "vaela":
                    return [Task(task_id="assigned-v1", agent="vaela", status="idle")]
                return []
            
            mock_client.list_idle_tasks = Mock(side_effect=get_idle_tasks)
            mock_client.assign_task = Mock(return_value=True)
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Both types processed
            assert stats['unassigned_matched'] == 2  # 2 unassigned tasks matched
            assert stats['assigned_spawned'] == 1    # 1 already-assigned task spawned
            assert stats['tasks_spawned'] == 3       # Total spawned


class TestMultipleQueues:
    """Test scenarios with multiple queues being processed."""
    
    def test_multiple_queues_processed_independently(self, base_config, agent_control_file):
        """Test that dev and qa queues are processed independently."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean state
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: Unassigned tasks in both queues
            dev_tasks = [
                Task(task_id="dev-1", agent="", status="idle"),
                Task(task_id="dev-2", agent="", status="idle")
            ]
            qa_tasks = [
                Task(task_id="qa-1", agent="", status="idle"),
                Task(task_id="qa-2", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks,
                "qa": qa_tasks
            }.get(q, []))
            
            # Track assignments by queue
            assignments = []
            def track_assignment(task_id, agent):
                assignments.append((task_id, agent))
                return True
            
            mock_client.assign_task = Mock(side_effect=track_assignment)
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: All tasks processed
            assert stats['unassigned_matched'] == 4
            
            # Verify: Dev tasks assigned to dev agents
            dev_assignments = [(tid, agent) for tid, agent in assignments if tid.startswith('dev-')]
            assert all(agent in ['vaela', 'damien'] for _, agent in dev_assignments)
            
            # Verify: QA tasks assigned to QA agents
            qa_assignments = [(tid, agent) for tid, agent in assignments if tid.startswith('qa-')]
            assert all(agent in ['oscar', 'kalis'] for _, agent in qa_assignments)
    
    def test_queue_isolation_with_capacity_constraints(self, base_config, agent_control_file):
        """Test that queue capacity constraints don't affect other queues."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Dev agents at capacity, QA agents available
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={
                "vaela": 3,   # At capacity
                "damien": 2,  # At capacity
                "oscar": 0,   # Available
                "kalis": 0    # Available
            })
            
            # Mock: Tasks in both queues
            dev_tasks = [Task(task_id="dev-1", agent="", status="idle")]
            qa_tasks = [
                Task(task_id="qa-1", agent="", status="idle"),
                Task(task_id="qa-2", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks if l > 0 else [],  # Won't be queried (no capacity)
                "qa": qa_tasks
            }.get(q, []))
            
            mock_client.assign_task = Mock(return_value=True)
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Only QA tasks processed (dev at capacity)
            assert stats['unassigned_matched'] == 2


class TestCapacityLimits:
    """Test scenarios for enforcing capacity limits."""
    
    def test_respects_per_agent_capacity_limits(self, base_config, agent_control_file):
        """Test that per-agent capacity limits are enforced."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: vaela has 2 active (limit 3), damien has 0 active (limit 2)
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            
            active_counts = {"vaela": 2, "damien": 0}
            scheduler.lease_store.count_active_by_agent = Mock(return_value=active_counts)
            
            # Mock: 10 unassigned tasks (more than total capacity)
            dev_tasks = [
                Task(task_id=f"task-{i}", agent="", status="idle")
                for i in range(1, 11)
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks[:l],  # Respect limit
                "qa": []
            }.get(q, []))
            
            # Track assignments and update counts
            assignments = []
            def track_assignment(task_id, agent):
                assignments.append((task_id, agent))
                active_counts[agent] = active_counts.get(agent, 0) + 1
                return True
            
            mock_client.assign_task = Mock(side_effect=track_assignment)
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Only 3 tasks assigned (1 for vaela, 2 for damien)
            assert stats['unassigned_matched'] == 3
            
            # Verify: Capacity limits respected
            agent_counts = {}
            for _, agent in assignments:
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
            
            assert agent_counts.get('vaela', 0) <= 1  # Had 2, limit 3
            assert agent_counts.get('damien', 0) <= 2  # Had 0, limit 2
    
    def test_no_tasks_spawned_when_all_at_capacity(self, base_config, agent_control_file):
        """Test that no tasks are spawned when all agents are at capacity."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: All agents at capacity
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={
                "vaela": 3,
                "damien": 2,
                "oscar": 2,
                "kalis": 1
            })
            
            # Mock: Tasks available
            mock_client.get_unassigned_in_queue = Mock(return_value=[
                Task(task_id="task-1", agent="", status="idle")
            ])
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: No tasks assigned or spawned
            assert stats['unassigned_matched'] == 0
            assert stats['tasks_spawned'] == 0


class TestDryRunMode:
    """Test scenarios for dry run mode."""
    
    def test_dry_run_logs_actions_without_spawning(self, base_config, agent_control_file):
        """Test that dry run mode logs intended actions but doesn't spawn wrappers."""
        base_config.dry_run = True
        
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean state
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: Unassigned tasks
            dev_tasks = [
                Task(task_id="task-1", agent="", status="idle"),
                Task(task_id="task-2", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks,
                "qa": []
            }.get(q, []))
            
            mock_client.list_idle_tasks = Mock(return_value=[])
            
            # These should NOT be called in dry run
            mock_client.assign_task = Mock(return_value=True)
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Tasks tracked but not actually assigned/spawned
            assert stats['unassigned_matched'] == 2
            assert stats['tasks_spawned'] == 0  # Should be 0 in dry run
            
            # Verify: No actual mutations
            assert mock_client.assign_task.call_count == 0
            assert scheduler._spawn_wrapper.call_count == 0
    
    def test_dry_run_with_assigned_tasks(self, base_config, agent_control_file):
        """Test dry run mode with already-assigned tasks."""
        base_config.dry_run = True
        
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean state
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            mock_client.get_unassigned_in_queue = Mock(return_value=[])
            
            # Mock: Idle assigned tasks only for vaela
            def get_idle_tasks(agent, limit):
                if agent == "vaela":
                    return [Task(task_id="task-v1", agent="vaela", status="idle")]
                return []
            
            mock_client.list_idle_tasks = Mock(side_effect=get_idle_tasks)
            
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Tracked but not spawned
            assert stats['assigned_spawned'] == 1
            assert stats['tasks_spawned'] == 0
            assert scheduler._spawn_wrapper.call_count == 0


class TestErrorHandling:
    """Test scenarios for error handling in full reconciliation flow."""
    
    def test_continues_after_tinytask_query_error(self, base_config, agent_control_file):
        """Test that reconciliation continues after tinytask query errors."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean state
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: First queue fails, second succeeds
            call_count = [0]
            def get_unassigned_side_effect(queue, limit):
                call_count[0] += 1
                if queue == "dev":
                    raise TinytaskClientError("Connection failed")
                return [Task(task_id="qa-1", agent="", status="idle")]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=get_unassigned_side_effect)
            mock_client.assign_task = Mock(return_value=True)
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Error recorded but reconciliation continued
            assert stats['errors'] >= 1
            assert stats['unassigned_matched'] == 1  # QA task still processed
    
    def test_continues_after_spawn_failure(self, base_config, agent_control_file):
        """Test that reconciliation continues after spawn failures."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean state
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: Multiple unassigned tasks
            dev_tasks = [
                Task(task_id="task-1", agent="", status="idle"),
                Task(task_id="task-2", agent="", status="idle"),
                Task(task_id="task-3", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks,
                "qa": []
            }.get(q, []))
            
            mock_client.assign_task = Mock(return_value=True)
            mock_client.list_idle_tasks = Mock(return_value=[])
            
            # Mock: First spawn fails, others succeed
            spawn_count = [0]
            def spawn_side_effect(task_id, agent, recipe):
                spawn_count[0] += 1
                if spawn_count[0] == 1:
                    return False  # First spawn fails
                return True
            
            scheduler._spawn_wrapper = Mock(side_effect=spawn_side_effect)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Error recorded but other tasks still processed
            assert stats['errors'] >= 1
            assert stats['tasks_spawned'] == 2  # 2 succeeded
    
    def test_handles_assignment_failure_gracefully(self, base_config, agent_control_file):
        """Test graceful handling of task assignment failures."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Clean state
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={})
            
            # Mock: Multiple tasks
            dev_tasks = [
                Task(task_id="task-1", agent="", status="idle"),
                Task(task_id="task-2", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_tasks,
                "qa": []
            }.get(q, []))
            
            # Mock: First assignment fails, second succeeds
            assign_count = [0]
            def assign_side_effect(task_id, agent):
                assign_count[0] += 1
                if assign_count[0] == 1:
                    return False  # First fails
                return True
            
            mock_client.assign_task = Mock(side_effect=assign_side_effect)
            mock_client.list_idle_tasks = Mock(return_value=[])
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: Error recorded
            assert stats['errors'] >= 1
            # One task failed assignment, one succeeded
            assert stats['tasks_spawned'] == 1


class TestCompleteReconciliationFlow:
    """Test complete end-to-end reconciliation scenarios."""
    
    def test_full_reconciliation_with_all_features(self, base_config, agent_control_file):
        """Test a complete reconciliation with multiple queues, assignments, and tasks."""
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(base_config)
            mock_client = Mock()
            scheduler.tinytask_client = mock_client
            
            # Mock: Some agents with active tasks
            scheduler.lease_store.list_all = Mock(return_value=[])
            scheduler.lease_store.find_stale_leases = Mock(return_value=[])
            scheduler.lease_store.count_active_by_agent = Mock(return_value={
                "vaela": 1,  # 2 slots available
                "damien": 1  # 1 slot available
            })
            
            # Mock: Unassigned tasks in both queues
            dev_unassigned = [
                Task(task_id="dev-unassigned-1", agent="", status="idle"),
                Task(task_id="dev-unassigned-2", agent="", status="idle")
            ]
            qa_unassigned = [
                Task(task_id="qa-unassigned-1", agent="", status="idle")
            ]
            
            mock_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
                "dev": dev_unassigned[:l],
                "qa": qa_unassigned[:l]
            }.get(q, []))
            
            # Mock: Already-assigned idle tasks
            def get_idle_tasks(agent, limit):
                tasks_map = {
                    "vaela": [Task(task_id="vaela-assigned-1", agent="vaela", status="idle")],
                    "oscar": [Task(task_id="oscar-assigned-1", agent="oscar", status="idle")]
                }
                return tasks_map.get(agent, [])[:limit]
            
            mock_client.list_idle_tasks = Mock(side_effect=get_idle_tasks)
            mock_client.assign_task = Mock(return_value=True)
            scheduler._spawn_wrapper = Mock(return_value=True)
            
            # Execute
            stats = scheduler.reconcile()
            
            # Verify: All task types processed
            assert stats['unassigned_matched'] >= 2  # At least dev tasks
            assert stats['assigned_spawned'] >= 1    # At least some assigned tasks
            assert stats['errors'] == 0
            assert stats['tasks_spawned'] > 0

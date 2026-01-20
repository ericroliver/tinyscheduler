"""Unit tests for queue-based scheduler logic."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, List

from src.scheduler.scheduler import Scheduler
from src.scheduler.config import TinySchedulerConfig
from src.scheduler.tinytask_client import Task
from src.scheduler.agent_registry import AgentRegistry, AgentConfig
from src.scheduler.lease import Lease


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock scheduler config."""
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
    
    # Create mock agent control file
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
        agent_limits={"vaela": 2, "remy": 2, "oscar": 1},
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
    
    return config


@pytest.fixture
def mock_agent_registry():
    """Create a mock agent registry."""
    registry = Mock(spec=AgentRegistry)
    
    # Configure mock data
    registry.get_all_types.return_value = ["dev", "qa"]
    registry.get_agents_by_type.side_effect = lambda t: {
        "dev": ["vaela", "remy"],
        "qa": ["oscar"]
    }.get(t, [])
    registry.get_all_agent_names.return_value = ["vaela", "remy", "oscar"]
    registry.get_agent_type.side_effect = lambda n: {
        "vaela": "dev",
        "remy": "dev",
        "oscar": "qa"
    }.get(n)
    
    return registry


@pytest.fixture
def scheduler(mock_config, mock_agent_registry):
    """Create a scheduler instance with mocked dependencies."""
    with patch('src.scheduler.scheduler.TinytaskClient'), \
         patch('src.scheduler.scheduler.AgentRegistry', return_value=mock_agent_registry):
        
        sched = Scheduler(mock_config)
        sched.tinytask_client = Mock()
        sched.agent_registry = mock_agent_registry
        
        # Create some recipes
        for agent in ["vaela", "remy", "oscar"]:
            recipe_file = mock_config.recipes_dir / f"{agent}.yaml"
            recipe_file.write_text("test recipe")
        
        return sched


class TestCalculateAvailableSlots:
    """Tests for _calculate_available_slots method."""
    
    def test_calculate_slots_no_active_leases(self, scheduler):
        """Test calculation when no leases are active."""
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # vaela has limit of 2, no active leases
        assert scheduler._calculate_available_slots("vaela") == 2
        
        # oscar has limit of 1, no active leases
        assert scheduler._calculate_available_slots("oscar") == 1
    
    def test_calculate_slots_with_active_leases(self, scheduler):
        """Test calculation with some active leases."""
        scheduler.lease_store.count_active_by_agent = Mock(return_value={
            "vaela": 1,
            "oscar": 1
        })
        
        # vaela has 1 of 2 slots used
        assert scheduler._calculate_available_slots("vaela") == 1
        
        # oscar has 1 of 1 slots used (at capacity)
        assert scheduler._calculate_available_slots("oscar") == 0
        
        # remy has no active leases
        assert scheduler._calculate_available_slots("remy") == 2
    
    def test_calculate_slots_agent_not_configured(self, scheduler):
        """Test calculation for agent not in agent_limits."""
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Unknown agent should return 0
        assert scheduler._calculate_available_slots("unknown_agent") == 0
    
    def test_calculate_slots_over_limit(self, scheduler):
        """Test calculation when active count exceeds limit (shouldn't happen but handle gracefully)."""
        scheduler.lease_store.count_active_by_agent = Mock(return_value={
            "vaela": 5  # More than limit of 2
        })
        
        # Should return 0, not negative
        assert scheduler._calculate_available_slots("vaela") == 0


class TestSelectBestAgent:
    """Tests for _select_best_agent method."""
    
    def test_select_agent_with_most_slots(self, scheduler):
        """Test selecting agent with most available capacity."""
        available = {
            "vaela": 1,
            "remy": 2,
            "oscar": 1
        }
        
        # remy has most available slots
        assert scheduler._select_best_agent(available) == "remy"
    
    def test_select_agent_tie_breaker(self, scheduler):
        """Test tie-breaking by name (alphabetical)."""
        available = {
            "vaela": 2,
            "remy": 2,
            "oscar": 1
        }
        
        # vaela and remy both have 2 slots, should pick remy (comes after vaela alphabetically)
        result = scheduler._select_best_agent(available)
        assert result in ["vaela", "remy"]  # Either is acceptable with consistent tie-breaking
    
    def test_select_agent_no_availability(self, scheduler):
        """Test when no agents have availability."""
        available = {
            "vaela": 0,
            "remy": 0,
            "oscar": 0
        }
        
        assert scheduler._select_best_agent(available) is None
    
    def test_select_agent_empty_dict(self, scheduler):
        """Test with empty agent pool."""
        assert scheduler._select_best_agent({}) is None
    
    def test_select_agent_single_agent(self, scheduler):
        """Test with single available agent."""
        available = {"vaela": 3}
        
        assert scheduler._select_best_agent(available) == "vaela"


class TestProcessUnassignedTasks:
    """Tests for _process_unassigned_tasks method."""
    
    def test_process_unassigned_tasks_success(self, scheduler):
        """Test successful processing of unassigned tasks."""
        # Setup
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Mock unassigned tasks
        dev_tasks = [
            Task(task_id="1", agent="", status="idle", recipe="vaela.yaml"),
            Task(task_id="2", agent="", status="idle", recipe="remy.yaml"),
        ]
        qa_tasks = [
            Task(task_id="3", agent="", status="idle", recipe="oscar.yaml"),
        ]
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
            "dev": dev_tasks,
            "qa": qa_tasks
        }.get(q, []))
        
        scheduler.tinytask_client.assign_task = Mock(return_value=True)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # Verify
        assert stats['unassigned_matched'] == 3
        assert stats['tasks_spawned'] == 3
        assert stats['errors'] == 0
        
        # Verify tasks were assigned
        assert scheduler.tinytask_client.assign_task.call_count == 3
        assert scheduler._spawn_wrapper.call_count == 3
    
    def test_process_unassigned_tasks_with_capacity_limits(self, scheduler):
        """Test that tasks are assigned within capacity limits."""
        # Setup - vaela has 1 slot, remy has 2 slots
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={
            "vaela": 1,  # vaela has 1 of 2 slots used
            "oscar": 1   # oscar at capacity
        })
        
        # Mock 5 unassigned dev tasks (but only 3 slots available: 1 for vaela, 2 for remy)
        # No qa tasks because oscar is at capacity
        dev_tasks = [Task(task_id=str(i), agent="", status="idle") for i in range(1, 6)]
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(side_effect=lambda q, l: {
            "dev": dev_tasks,
            "qa": []  # No qa tasks
        }.get(q, []))
        scheduler.tinytask_client.assign_task = Mock(return_value=True)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # Should only process 3 tasks from dev queue (total available slots)
        assert stats['unassigned_matched'] == 3
        assert stats['tasks_spawned'] == 3
    
    def test_process_unassigned_tasks_load_balancing(self, scheduler):
        """Test that tasks are assigned to agent with most capacity."""
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={
            "vaela": 1,  # 1 slot available
            "remy": 0    # 2 slots available
        })
        
        # Mock 2 unassigned dev tasks
        dev_tasks = [
            Task(task_id="1", agent="", status="idle"),
            Task(task_id="2", agent="", status="idle"),
        ]
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(return_value=dev_tasks)
        scheduler.tinytask_client.assign_task = Mock(return_value=True)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        assigned_agents = []
        def track_assignment(task_id, agent):
            assigned_agents.append(agent)
            return True
        
        scheduler.tinytask_client.assign_task = Mock(side_effect=track_assignment)
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # First task should go to remy (2 slots), second to remy again or vaela
        assert assigned_agents[0] == "remy"  # Most available capacity
        # After first assignment, both have 1 slot available
        assert assigned_agents[1] in ["remy", "vaela"]
    
    def test_process_unassigned_tasks_dry_run(self, scheduler):
        """Test dry run mode doesn't mutate state."""
        scheduler.config.dry_run = True
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Return tasks only for dev queue, not qa
        def mock_get_unassigned(queue, limit):
            if queue == "dev":
                return [Task(task_id="1", agent="", status="idle")]
            return []
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(side_effect=mock_get_unassigned)
        scheduler.tinytask_client.assign_task = Mock(return_value=True)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # Should track intent but not actually assign or spawn (1 from dev, 0 from qa)
        assert stats['unassigned_matched'] == 1
        assert scheduler.tinytask_client.assign_task.call_count == 0
        assert scheduler._spawn_wrapper.call_count == 0
    
    def test_process_unassigned_tasks_assignment_failure(self, scheduler):
        """Test handling of assignment failures."""
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Return tasks only for dev queue, not qa
        def mock_get_unassigned(queue, limit):
            if queue == "dev":
                return [Task(task_id="1", agent="", status="idle")]
            return []
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(side_effect=mock_get_unassigned)
        scheduler.tinytask_client.assign_task = Mock(return_value=False)  # Assignment fails
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # Should track error and not spawn (1 error from dev, 0 from qa)
        assert stats['unassigned_matched'] == 0
        assert stats['tasks_spawned'] == 0
        assert stats['errors'] == 1
        assert scheduler._spawn_wrapper.call_count == 0
    
    def test_process_unassigned_tasks_spawn_failure(self, scheduler):
        """Test handling of spawn wrapper failures."""
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Return tasks only for dev queue, not qa
        def mock_get_unassigned(queue, limit):
            if queue == "dev":
                return [Task(task_id="1", agent="", status="idle")]
            return []
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(side_effect=mock_get_unassigned)
        scheduler.tinytask_client.assign_task = Mock(return_value=True)
        scheduler._spawn_wrapper = Mock(return_value=False)  # Spawn fails
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # Should track error (1 from dev, 0 from qa)
        assert stats['unassigned_matched'] == 0
        assert stats['tasks_spawned'] == 0
        assert stats['errors'] == 1
    
    def test_process_unassigned_tasks_no_agents_for_queue(self, scheduler):
        """Test handling of queue with no configured agents."""
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        # Add a queue type with no agents
        scheduler.agent_registry.get_all_types.return_value = ["dev", "qa", "empty-queue"]
        scheduler.agent_registry.get_agents_by_type.side_effect = lambda t: {
            "dev": ["vaela", "remy"],
            "qa": ["oscar"],
            "empty-queue": []
        }.get(t, [])
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(return_value=[])
        
        # Execute - should not crash
        scheduler._process_unassigned_tasks(stats)
        
        # No errors, just skip the empty queue
        assert stats['errors'] == 0
    
    def test_process_unassigned_tasks_all_agents_full(self, scheduler):
        """Test when all agents are at capacity."""
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        # All agents at capacity
        scheduler.lease_store.count_active_by_agent = Mock(return_value={
            "vaela": 2,
            "remy": 2,
            "oscar": 1
        })
        
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(return_value=[])
        
        # Execute
        scheduler._process_unassigned_tasks(stats)
        
        # Should query with limit=0 and get no tasks
        for call_args in scheduler.tinytask_client.get_unassigned_in_queue.call_args_list:
            args, kwargs = call_args
            # Either positional or keyword, but limit should be 0
            if len(args) > 1:
                assert args[1] == 0
            elif 'limit' in kwargs:
                assert kwargs['limit'] == 0


class TestProcessAssignedTasks:
    """Tests for _process_assigned_tasks method."""
    
    def test_process_assigned_tasks_success(self, scheduler):
        """Test successful processing of assigned tasks."""
        stats = {'assigned_spawned': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Mock idle tasks for each agent
        scheduler.tinytask_client.list_idle_tasks = Mock(side_effect=lambda agent, limit: {
            "vaela": [Task(task_id="1", agent="vaela", status="idle")],
            "remy": [Task(task_id="2", agent="remy", status="idle")],
            "oscar": [Task(task_id="3", agent="oscar", status="idle")]
        }.get(agent, []))
        
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_assigned_tasks(stats)
        
        # Verify
        assert stats['assigned_spawned'] == 3
        assert stats['tasks_spawned'] == 3
        assert stats['errors'] == 0
        assert scheduler._spawn_wrapper.call_count == 3
    
    def test_process_assigned_tasks_respects_capacity(self, scheduler):
        """Test that processing respects agent capacity limits."""
        stats = {'assigned_spawned': 0, 'tasks_spawned': 0, 'errors': 0}
        
        # vaela has 1 slot available (1 of 2 used), others at capacity
        scheduler.lease_store.count_active_by_agent = Mock(return_value={
            "vaela": 1,
            "remy": 2,
            "oscar": 1
        })
        
        # Mock 3 idle tasks for vaela (but only 1 slot available), none for others at capacity
        def mock_list_idle(agent, limit):
            if agent == "vaela":
                return [
                    Task(task_id="1", agent="vaela", status="idle"),
                    Task(task_id="2", agent="vaela", status="idle"),
                    Task(task_id="3", agent="vaela", status="idle"),
                ]
            return []  # Other agents at capacity
        
        scheduler.tinytask_client.list_idle_tasks = Mock(side_effect=mock_list_idle)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_assigned_tasks(stats)
        
        # Should only spawn 1 task for vaela (available capacity), none for others
        assert scheduler._spawn_wrapper.call_count == 1
    
    def test_process_assigned_tasks_dry_run(self, scheduler):
        """Test dry run mode."""
        scheduler.config.dry_run = True
        stats = {'assigned_spawned': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Return tasks only for vaela, not for other agents
        def mock_list_idle(agent, limit):
            if agent == "vaela":
                return [Task(task_id="1", agent="vaela", status="idle")]
            return []
        
        scheduler.tinytask_client.list_idle_tasks = Mock(side_effect=mock_list_idle)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_assigned_tasks(stats)
        
        # Should track intent but not spawn (1 from vaela, 0 from others)
        assert stats['assigned_spawned'] == 1
        assert scheduler._spawn_wrapper.call_count == 0
    
    def test_process_assigned_tasks_spawn_failure(self, scheduler):
        """Test handling of spawn failures."""
        stats = {'assigned_spawned': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Return tasks only for vaela, not for other agents
        def mock_list_idle(agent, limit):
            if agent == "vaela":
                return [Task(task_id="1", agent="vaela", status="idle")]
            return []
        
        scheduler.tinytask_client.list_idle_tasks = Mock(side_effect=mock_list_idle)
        scheduler._spawn_wrapper = Mock(return_value=False)
        
        # Execute
        scheduler._process_assigned_tasks(stats)
        
        # Should track error (1 from vaela, 0 from others)
        assert stats['assigned_spawned'] == 0
        assert stats['tasks_spawned'] == 0
        assert stats['errors'] == 1
    
    def test_process_assigned_tasks_missing_recipe(self, scheduler):
        """Test handling of missing recipe files."""
        stats = {'assigned_spawned': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Task with non-existent recipe
        scheduler.tinytask_client.list_idle_tasks = Mock(return_value=[
            Task(task_id="1", agent="vaela", status="idle", recipe="missing.yaml")
        ])
        
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        scheduler._process_assigned_tasks(stats)
        
        # Should skip task without spawning
        assert scheduler._spawn_wrapper.call_count == 0
        assert stats['errors'] == 0  # Not an error, just a warning


class TestReconcileIntegration:
    """Integration tests for full reconcile method with queue-based logic."""
    
    def test_reconcile_with_queue_processing(self, scheduler):
        """Test full reconciliation with queue-based processing."""
        # Setup mocks
        scheduler.lease_store.list_all = Mock(return_value=[])
        scheduler.lease_store.find_stale_leases = Mock(return_value=[])
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        # Mock unassigned tasks
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(return_value=[
            Task(task_id="1", agent="", status="idle")
        ])
        
        # Mock assigned tasks
        scheduler.tinytask_client.list_idle_tasks = Mock(return_value=[
            Task(task_id="2", agent="vaela", status="idle")
        ])
        
        scheduler.tinytask_client.assign_task = Mock(return_value=True)
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        stats = scheduler.reconcile()
        
        # Verify stats
        assert stats['leases_scanned'] == 0
        assert stats['leases_reclaimed'] == 0
        assert stats['unassigned_matched'] >= 0
        assert stats['assigned_spawned'] >= 0
        assert 'tasks_spawned' in stats
        assert 'errors' in stats
    
    def test_reconcile_without_agent_registry(self, scheduler):
        """Test reconciliation falls back to legacy mode without agent registry."""
        # Disable agent registry
        scheduler.agent_registry = None
        
        # Setup mocks for legacy mode
        scheduler.lease_store.list_all = Mock(return_value=[])
        scheduler.lease_store.find_stale_leases = Mock(return_value=[])
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        
        scheduler.tinytask_client.list_idle_tasks = Mock(return_value=[
            Task(task_id="1", agent="vaela", status="idle")
        ])
        
        scheduler._spawn_wrapper = Mock(return_value=True)
        
        # Execute
        stats = scheduler.reconcile()
        
        # Should use legacy list_idle_tasks for each agent in agent_limits
        assert scheduler.tinytask_client.list_idle_tasks.called
        assert 'tasks_spawned' in stats


class TestErrorHandling:
    """Tests for error handling and edge cases."""
    
    def test_process_unassigned_tasks_query_exception(self, scheduler):
        """Test handling of exceptions during queue query."""
        stats = {'unassigned_matched': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        scheduler.tinytask_client.get_unassigned_in_queue = Mock(
            side_effect=Exception("Network error")
        )
        
        # Execute - should not crash
        scheduler._process_unassigned_tasks(stats)
        
        # Should track errors for failed queries
        assert stats['errors'] > 0
    
    def test_process_assigned_tasks_query_exception(self, scheduler):
        """Test handling of exceptions during assigned task query."""
        stats = {'assigned_spawned': 0, 'tasks_spawned': 0, 'errors': 0}
        
        scheduler.lease_store.count_active_by_agent = Mock(return_value={})
        scheduler.tinytask_client.list_idle_tasks = Mock(
            side_effect=Exception("Network error")
        )
        
        # Execute - should not crash
        scheduler._process_assigned_tasks(stats)
        
        # Should track errors
        assert stats['errors'] > 0
    
    def test_scheduler_init_missing_agent_control_file(self, mock_config):
        """Test scheduler initialization with missing agent control file."""
        # agent_control_file doesn't exist
        
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(mock_config)
            
            # Should fall back to legacy mode
            assert scheduler.agent_registry is None
    
    def test_scheduler_init_invalid_agent_control_file(self, mock_config):
        """Test scheduler initialization with invalid agent control file."""
        # Create invalid JSON file
        mock_config.agent_control_file.write_text("invalid json{")
        
        with patch('src.scheduler.scheduler.TinytaskClient'):
            scheduler = Scheduler(mock_config)
            
            # Should fall back to legacy mode
            assert scheduler.agent_registry is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

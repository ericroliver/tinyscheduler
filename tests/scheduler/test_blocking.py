"""Unit tests for task blocking functionality."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from src.scheduler.tinytask_client import Task
from src.scheduler.scheduler import Scheduler
from src.scheduler.config import TinySchedulerConfig


class TestTaskDataModel:
    """Test Task dataclass with blocking fields."""
    
    def test_task_with_all_blocking_fields(self):
        """Task can be created with all blocking fields."""
        task = Task(
            task_id="1",
            agent="test-agent",
            status="idle",
            priority=10,
            blocked_by_task_id=5,
            is_currently_blocked=True
        )
        assert task.priority == 10
        assert task.blocked_by_task_id == 5
        assert task.is_currently_blocked is True
    
    def test_task_without_blocking_fields(self):
        """Task uses defaults when blocking fields missing."""
        task = Task(
            task_id="1",
            agent="test-agent",
            status="idle"
        )
        assert task.priority == 0
        assert task.blocked_by_task_id is None
        assert task.is_currently_blocked is False
    
    def test_task_from_dict_complete(self):
        """from_dict parses all blocking fields."""
        data = {
            'id': 1,
            'assigned_to': 'agent1',
            'status': 'idle',
            'priority': 5,
            'blocked_by_task_id': 10,
            'is_currently_blocked': True
        }
        task = Task.from_dict(data)
        assert task.priority == 5
        assert task.blocked_by_task_id == 10
        assert task.is_currently_blocked is True
    
    def test_task_from_dict_missing_fields(self):
        """from_dict handles missing blocking fields."""
        data = {
            'id': 1,
            'assigned_to': 'agent1',
            'status': 'idle'
        }
        task = Task.from_dict(data)
        assert task.priority == 0
        assert task.blocked_by_task_id is None
        assert task.is_currently_blocked is False


class TestFilterBlockedTasks:
    """Test _filter_blocked_tasks method."""
    
    def test_filter_empty_list(self, scheduler):
        """Filter empty list returns empty list."""
        unblocked, count = scheduler._filter_blocked_tasks([])
        assert unblocked == []
        assert count == 0
    
    def test_filter_all_unblocked(self, scheduler):
        """All unblocked tasks pass through."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", is_currently_blocked=False),
            Task(task_id="2", agent="a1", status="idle", is_currently_blocked=False),
        ]
        unblocked, count = scheduler._filter_blocked_tasks(tasks)
        assert len(unblocked) == 2
        assert count == 0
    
    def test_filter_mixed(self, scheduler):
        """Filters blocked tasks correctly."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", is_currently_blocked=False),
            Task(task_id="2", agent="a1", status="idle", is_currently_blocked=True),
            Task(task_id="3", agent="a1", status="idle", is_currently_blocked=False),
        ]
        unblocked, count = scheduler._filter_blocked_tasks(tasks)
        assert len(unblocked) == 2
        assert count == 1
        assert unblocked[0].task_id == "1"
        assert unblocked[1].task_id == "3"
    
    def test_filter_all_blocked(self, scheduler):
        """All blocked tasks filtered out."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", is_currently_blocked=True),
            Task(task_id="2", agent="a1", status="idle", is_currently_blocked=True),
        ]
        unblocked, count = scheduler._filter_blocked_tasks(tasks)
        assert len(unblocked) == 0
        assert count == 2
    
    def test_filter_with_blocking_disabled(self, scheduler_no_blocking):
        """When blocking is disabled, all tasks pass through."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", is_currently_blocked=False),
            Task(task_id="2", agent="a1", status="idle", is_currently_blocked=True),
            Task(task_id="3", agent="a1", status="idle", is_currently_blocked=True),
        ]
        unblocked, count = scheduler_no_blocking._filter_blocked_tasks(tasks)
        assert len(unblocked) == 3
        assert count == 0


class TestCountBlockingRelationships:
    """Test _count_blocking_relationships method."""
    
    def test_count_no_relationships(self, scheduler):
        """No blocking relationships returns empty dict."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle"),
            Task(task_id="2", agent="a1", status="idle"),
        ]
        counts = scheduler._count_blocking_relationships(tasks)
        assert counts == {}
    
    def test_count_single_blocker(self, scheduler):
        """Single blocker counted correctly."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", blocked_by_task_id=None),
            Task(task_id="2", agent="a1", status="idle", blocked_by_task_id=1),
        ]
        counts = scheduler._count_blocking_relationships(tasks)
        assert counts == {"1": 1}
    
    def test_count_multiple_blocked_by_same(self, scheduler):
        """Multiple tasks blocked by same task."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle"),
            Task(task_id="2", agent="a1", status="idle", blocked_by_task_id=1),
            Task(task_id="3", agent="a1", status="idle", blocked_by_task_id=1),
        ]
        counts = scheduler._count_blocking_relationships(tasks)
        assert counts == {"1": 2}
    
    def test_count_chain(self, scheduler):
        """Blocking chain counted correctly."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle"),
            Task(task_id="2", agent="a1", status="idle", blocked_by_task_id=1),
            Task(task_id="3", agent="a1", status="idle", blocked_by_task_id=2),
        ]
        counts = scheduler._count_blocking_relationships(tasks)
        assert counts == {"1": 1, "2": 1}
    
    def test_count_ignores_external_blockers(self, scheduler):
        """Blockers not in task list are ignored."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle"),
            Task(task_id="2", agent="a1", status="idle", blocked_by_task_id=999),
        ]
        counts = scheduler._count_blocking_relationships(tasks)
        assert counts == {}
    
    def test_count_handles_string_and_int_task_ids(self, scheduler):
        """Handles both string and int task IDs."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle"),
            Task(task_id="2", agent="a1", status="idle", blocked_by_task_id="1"),
            Task(task_id="3", agent="a1", status="idle", blocked_by_task_id=1),
        ]
        counts = scheduler._count_blocking_relationships(tasks)
        assert counts == {"1": 2}


class TestSortTasks:
    """Test _sort_tasks_for_spawning method."""
    
    def test_sort_by_blocker_count(self, scheduler):
        """Tasks sorted by blocker count (descending)."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", priority=0),
            Task(task_id="2", agent="a1", status="idle", priority=0),
            Task(task_id="3", agent="a1", status="idle", priority=0),
        ]
        blocker_counts = {"2": 3, "1": 1, "3": 2}
        sorted_tasks = scheduler._sort_tasks_for_spawning(tasks, blocker_counts)
        assert [t.task_id for t in sorted_tasks] == ["2", "3", "1"]
    
    def test_sort_by_priority(self, scheduler):
        """Tasks sorted by priority (descending) when no blockers."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", priority=1),
            Task(task_id="2", agent="a1", status="idle", priority=10),
            Task(task_id="3", agent="a1", status="idle", priority=5),
        ]
        sorted_tasks = scheduler._sort_tasks_for_spawning(tasks, {})
        assert [t.task_id for t in sorted_tasks] == ["2", "3", "1"]
    
    def test_sort_by_creation_time(self, scheduler):
        """Tasks sorted by creation time when same priority."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", 
                 priority=5, created_at="2026-01-26T12:00:00"),
            Task(task_id="2", agent="a1", status="idle", 
                 priority=5, created_at="2026-01-26T10:00:00"),
            Task(task_id="3", agent="a1", status="idle", 
                 priority=5, created_at="2026-01-26T11:00:00"),
        ]
        sorted_tasks = scheduler._sort_tasks_for_spawning(tasks, {})
        assert [t.task_id for t in sorted_tasks] == ["2", "3", "1"]
    
    def test_sort_multilevel(self, scheduler):
        """Multi-level sort: blocker > priority > time."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", 
                 priority=5, created_at="2026-01-26T12:00:00"),
            Task(task_id="2", agent="a1", status="idle", 
                 priority=10, created_at="2026-01-26T10:00:00"),
            Task(task_id="3", agent="a1", status="idle", 
                 priority=10, created_at="2026-01-26T09:00:00"),
            Task(task_id="4", agent="a1", status="idle", 
                 priority=5, created_at="2026-01-26T11:00:00"),
        ]
        blocker_counts = {"1": 2}  # Task 1 is a blocker
        sorted_tasks = scheduler._sort_tasks_for_spawning(tasks, blocker_counts)
        # Task 1 (blocker) first, then by priority (3,2), then by time within priority (4)
        assert [t.task_id for t in sorted_tasks] == ["1", "3", "2", "4"]
    
    def test_sort_handles_missing_created_at(self, scheduler):
        """Sort handles missing created_at field."""
        tasks = [
            Task(task_id="1", agent="a1", status="idle", priority=5),
            Task(task_id="2", agent="a1", status="idle", 
                 priority=5, created_at="2026-01-26T10:00:00"),
        ]
        sorted_tasks = scheduler._sort_tasks_for_spawning(tasks, {})
        # Task with created_at should come first (older)
        assert sorted_tasks[0].task_id == "2"
    
    def test_sort_empty_list(self, scheduler):
        """Sort handles empty task list."""
        sorted_tasks = scheduler._sort_tasks_for_spawning([], {})
        assert sorted_tasks == []
    
    def test_sort_single_task(self, scheduler):
        """Sort handles single task."""
        tasks = [Task(task_id="1", agent="a1", status="idle", priority=5)]
        sorted_tasks = scheduler._sort_tasks_for_spawning(tasks, {})
        assert len(sorted_tasks) == 1
        assert sorted_tasks[0].task_id == "1"


@pytest.fixture
def scheduler(tmp_path):
    """Create a scheduler instance for testing."""
    config = TinySchedulerConfig(
        base_path=tmp_path,
        running_dir=tmp_path / "state" / "running",
        log_dir=tmp_path / "state" / "logs",
        recipes_dir=tmp_path / "recipes",
        bin_dir=tmp_path / "scripts",
        task_cache_dir=tmp_path / "state" / "tasks",
        lock_file=tmp_path / "state" / "tinyscheduler.lock",
        agent_control_file=tmp_path / "agent-control.json",
        agent_limits={"agent1": 2},
        goose_bin=tmp_path / "goose",
        mcp_endpoint="http://localhost:3000",
        dry_run=True,
        disable_blocking=False,
    )
    
    # Create directories
    config.running_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.recipes_dir.mkdir(parents=True, exist_ok=True)
    
    # Create goose bin
    goose_bin = tmp_path / "goose"
    goose_bin.touch()
    goose_bin.chmod(0o755)
    
    # Mock TinytaskClient to avoid MCP dependency
    with patch('src.scheduler.scheduler.TinytaskClient'):
        sched = Scheduler(config)
        sched.tinytask_client = Mock()
        return sched


@pytest.fixture
def scheduler_no_blocking(tmp_path):
    """Create a scheduler instance with blocking disabled."""
    config = TinySchedulerConfig(
        base_path=tmp_path,
        running_dir=tmp_path / "state" / "running",
        log_dir=tmp_path / "state" / "logs",
        recipes_dir=tmp_path / "recipes",
        bin_dir=tmp_path / "scripts",
        task_cache_dir=tmp_path / "state" / "tasks",
        lock_file=tmp_path / "state" / "tinyscheduler.lock",
        agent_control_file=tmp_path / "agent-control.json",
        agent_limits={"agent1": 2},
        goose_bin=tmp_path / "goose",
        mcp_endpoint="http://localhost:3000",
        dry_run=True,
        disable_blocking=True,
    )
    
    # Create directories
    config.running_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.recipes_dir.mkdir(parents=True, exist_ok=True)
    
    # Create goose bin
    goose_bin = tmp_path / "goose"
    goose_bin.touch()
    goose_bin.chmod(0o755)
    
    # Mock TinytaskClient to avoid MCP dependency
    with patch('src.scheduler.scheduler.TinytaskClient'):
        sched = Scheduler(config)
        sched.tinytask_client = Mock()
        return sched

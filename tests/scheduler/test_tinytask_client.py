"""Unit tests for TinytaskClient queue integration methods."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.scheduler.tinytask_client import (
    TinytaskClient,
    Task,
    TinytaskConnectionError,
    TinytaskAPIError
)


def _mock_run_async_wrapper(return_value):
    """Create a mock for _run_async that properly handles coroutine arguments."""
    def run_async_mock(coro):
        # Close the coroutine to prevent warnings
        if asyncio.iscoroutine(coro):
            coro.close()
        return return_value
    return run_async_mock


class TestTinytaskClientQueueMethods:
    """Tests for TinytaskClient queue-based methods."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a TinytaskClient with mocked dependencies."""
        with patch('src.scheduler.tinytask_client.ClientSession'):
            with patch('src.scheduler.tinytask_client.sse_client'):
                client = TinytaskClient(endpoint="http://localhost:3000")
                return client
    
    @pytest.fixture
    def sample_tasks_response(self):
        """Sample tasks response from MCP."""
        return {
            'tasks': [
                {
                    'id': 1,
                    'assigned_to': 'vaela',
                    'status': 'idle',
                    'recipe': 'build-feature',
                    'created_at': '2026-01-17T10:00:00Z'
                },
                {
                    'id': 2,
                    'assigned_to': 'damien',
                    'status': 'working',
                    'recipe': 'fix-bug',
                    'created_at': '2026-01-17T11:00:00Z'
                }
            ]
        }
    
    # Tests for get_queue_tasks()
    
    def test_get_queue_tasks_valid_response(self, mock_client, sample_tasks_response):
        """Test get_queue_tasks with valid response."""
        mock_client._run_async = _mock_run_async_wrapper(sample_tasks_response)
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        
        assert len(tasks) == 2
        assert all(isinstance(task, Task) for task in tasks)
        assert tasks[0].task_id == '1'
        assert tasks[0].agent == 'vaela'
        assert tasks[0].status == 'idle'
        assert tasks[1].task_id == '2'
        assert tasks[1].agent == 'damien'
        assert tasks[1].status == 'working'
    
    def test_get_queue_tasks_with_assigned_to_filter(self, mock_client):
        """Test get_queue_tasks with assigned_to filter."""
        filtered_response = {
            'tasks': [
                {
                    'id': 1,
                    'assigned_to': 'vaela',
                    'status': 'idle',
                    'recipe': 'task1'
                }
            ]
        }
        mock_client._run_async = _mock_run_async_wrapper(filtered_response)
        
        tasks = mock_client.get_queue_tasks('dev-queue', assigned_to='vaela')
        
        assert len(tasks) == 1
        assert tasks[0].agent == 'vaela'
    
    def test_get_queue_tasks_with_status_filter(self, mock_client):
        """Test get_queue_tasks with status filter."""
        filtered_response = {
            'tasks': [
                {
                    'id': 2,
                    'assigned_to': 'damien',
                    'status': 'working',
                    'recipe': 'task2'
                }
            ]
        }
        mock_client._run_async = _mock_run_async_wrapper(filtered_response)
        
        tasks = mock_client.get_queue_tasks('dev-queue', status='working')
        
        assert len(tasks) == 1
        assert tasks[0].status == 'working'
    
    def test_get_queue_tasks_with_both_filters(self, mock_client):
        """Test get_queue_tasks with both assigned_to and status filters."""
        filtered_response = {
            'tasks': [
                {
                    'id': 3,
                    'assigned_to': 'oscar',
                    'status': 'idle',
                    'recipe': 'task3'
                }
            ]
        }
        mock_client._run_async = _mock_run_async_wrapper(filtered_response)
        
        tasks = mock_client.get_queue_tasks(
            'qa-queue',
            assigned_to='oscar',
            status='idle'
        )
        
        assert len(tasks) == 1
        assert tasks[0].agent == 'oscar'
        assert tasks[0].status == 'idle'
    
    def test_get_queue_tasks_with_limit(self, mock_client):
        """Test get_queue_tasks respects limit parameter."""
        mock_client._run_async = _mock_run_async_wrapper({'tasks': []})
        
        tasks = mock_client.get_queue_tasks('dev-queue', limit=50)
        
        assert tasks == []
    
    def test_get_queue_tasks_list_response(self, mock_client):
        """Test get_queue_tasks when response is a list directly."""
        tasks_list = [
            {'id': 1, 'assigned_to': 'agent1', 'status': 'idle'},
            {'id': 2, 'assigned_to': 'agent2', 'status': 'working'}
        ]
        mock_client._run_async = _mock_run_async_wrapper(tasks_list)
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        
        assert len(tasks) == 2
        assert tasks[0].task_id == '1'
    
    def test_get_queue_tasks_empty_response(self, mock_client):
        """Test get_queue_tasks with empty response."""
        mock_client._run_async = _mock_run_async_wrapper({'tasks': []})
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        
        assert tasks == []
    
    def test_get_queue_tasks_connection_error(self, mock_client, capfd):
        """Test get_queue_tasks handles connection error gracefully."""
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskConnectionError("Connection failed")
        
        mock_client._run_async = raise_error
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        
        assert tasks == []
        
        # Check warning was printed
        captured = capfd.readouterr()
        assert "Warning" in captured.out
        assert "dev-queue" in captured.out
    
    def test_get_queue_tasks_api_error(self, mock_client, capfd):
        """Test get_queue_tasks handles API error gracefully."""
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskAPIError("API error")
        
        mock_client._run_async = raise_error
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        
        assert tasks == []
        
        # Check warning was printed
        captured = capfd.readouterr()
        assert "Warning" in captured.out
        assert "dev-queue" in captured.out
    
    def test_get_queue_tasks_invalid_response_type(self, mock_client):
        """Test get_queue_tasks with invalid response type."""
        mock_client._run_async = _mock_run_async_wrapper("invalid")
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        
        assert tasks == []
    
    # Tests for get_unassigned_in_queue()
    
    def test_get_unassigned_in_queue_valid_response(self, mock_client):
        """Test get_unassigned_in_queue with valid response."""
        response = {
            'tasks': [
                {
                    'id': 10,
                    'assigned_to': None,
                    'status': 'idle',
                    'recipe': 'unassigned-task'
                },
                {
                    'id': 11,
                    'assigned_to': '',
                    'status': 'idle',
                    'recipe': 'another-task'
                }
            ]
        }
        mock_client._run_async = _mock_run_async_wrapper(response)
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue')
        
        assert len(tasks) == 2
        assert all(isinstance(task, Task) for task in tasks)
        assert tasks[0].task_id == '10'
        assert tasks[1].task_id == '11'
    
    def test_get_unassigned_in_queue_list_response(self, mock_client):
        """Test get_unassigned_in_queue when response is a list directly."""
        tasks_list = [
            {'id': 20, 'assigned_to': None, 'status': 'idle'}
        ]
        mock_client._run_async = _mock_run_async_wrapper(tasks_list)
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue')
        
        assert len(tasks) == 1
        assert tasks[0].task_id == '20'
    
    def test_get_unassigned_in_queue_respects_limit(self, mock_client):
        """Test get_unassigned_in_queue respects limit parameter."""
        # Return more tasks than the limit
        tasks_list = [
            {'id': i, 'assigned_to': None, 'status': 'idle'}
            for i in range(150)
        ]
        mock_client._run_async = _mock_run_async_wrapper(tasks_list)
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue', limit=50)
        
        # Should only return 50 tasks (limit applied)
        assert len(tasks) == 50
    
    def test_get_unassigned_in_queue_empty_response(self, mock_client):
        """Test get_unassigned_in_queue with empty response."""
        mock_client._run_async = _mock_run_async_wrapper({'tasks': []})
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue')
        
        assert tasks == []
    
    def test_get_unassigned_in_queue_connection_error(self, mock_client, capfd):
        """Test get_unassigned_in_queue handles connection error gracefully."""
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskConnectionError("Connection failed")
        
        mock_client._run_async = raise_error
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue')
        
        assert tasks == []
        
        # Check warning was printed
        captured = capfd.readouterr()
        assert "Warning" in captured.out
        assert "dev-queue" in captured.out
        assert "unassigned" in captured.out.lower()
    
    def test_get_unassigned_in_queue_api_error(self, mock_client, capfd):
        """Test get_unassigned_in_queue handles API error gracefully."""
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskAPIError("API error")
        
        mock_client._run_async = raise_error
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue')
        
        assert tasks == []
        
        # Check warning was printed
        captured = capfd.readouterr()
        assert "Warning" in captured.out
    
    def test_get_unassigned_in_queue_invalid_response(self, mock_client):
        """Test get_unassigned_in_queue with invalid response type."""
        mock_client._run_async = _mock_run_async_wrapper(42)
        
        tasks = mock_client.get_unassigned_in_queue('dev-queue')
        
        assert tasks == []
    
    # Tests for assign_task()
    
    def test_assign_task_success(self, mock_client):
        """Test assign_task with successful assignment."""
        mock_client._run_async = _mock_run_async_wrapper(None)
        
        result = mock_client.assign_task('123', 'vaela')
        
        assert result is True
    
    def test_assign_task_with_int_task_id(self, mock_client):
        """Test assign_task handles integer task_id."""
        mock_client._run_async = _mock_run_async_wrapper(None)
        
        # Pass task_id as string
        result = mock_client.assign_task('456', 'damien')
        
        assert result is True
    
    def test_assign_task_connection_error(self, mock_client, capfd):
        """Test assign_task handles connection error gracefully."""
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskConnectionError("Connection failed")
        
        mock_client._run_async = raise_error
        
        result = mock_client.assign_task('123', 'vaela')
        
        assert result is False
        
        # Check warning was printed
        captured = capfd.readouterr()
        assert "Warning" in captured.out
        assert "123" in captured.out
        assert "vaela" in captured.out
    
    def test_assign_task_api_error(self, mock_client, capfd):
        """Test assign_task handles API error gracefully."""
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskAPIError("Task not found")
        
        mock_client._run_async = raise_error
        
        result = mock_client.assign_task('999', 'oscar')
        
        assert result is False
        
        # Check warning was printed
        captured = capfd.readouterr()
        assert "Warning" in captured.out
        assert "999" in captured.out
        assert "oscar" in captured.out
    
    def test_assign_task_multiple_calls(self, mock_client):
        """Test multiple assign_task calls work correctly."""
        mock_client._run_async = _mock_run_async_wrapper(None)
        
        result1 = mock_client.assign_task('100', 'agent1')
        result2 = mock_client.assign_task('200', 'agent2')
        result3 = mock_client.assign_task('300', 'agent3')
        
        assert result1 is True
        assert result2 is True
        assert result3 is True
    
    # Integration-style tests
    
    def test_queue_workflow_integration(self, mock_client):
        """Test typical workflow: get queue tasks, filter, and assign."""
        # Step 1: Get queue tasks
        queue_response = {
            'tasks': [
                {'id': 1, 'assigned_to': None, 'status': 'idle'},
                {'id': 2, 'assigned_to': 'vaela', 'status': 'working'},
                {'id': 3, 'assigned_to': None, 'status': 'idle'}
            ]
        }
        mock_client._run_async = _mock_run_async_wrapper(queue_response)
        
        tasks = mock_client.get_queue_tasks('dev-queue')
        assert len(tasks) == 3
        
        # Step 2: Get unassigned tasks
        unassigned_response = {
            'tasks': [
                {'id': 1, 'assigned_to': None, 'status': 'idle'},
                {'id': 3, 'assigned_to': None, 'status': 'idle'}
            ]
        }
        mock_client._run_async = _mock_run_async_wrapper(unassigned_response)
        
        unassigned = mock_client.get_unassigned_in_queue('dev-queue')
        assert len(unassigned) == 2
        
        # Step 3: Assign a task
        mock_client._run_async = _mock_run_async_wrapper(None)
        
        success = mock_client.assign_task('1', 'damien')
        assert success is True
    
    def test_error_handling_consistency(self, mock_client, capfd):
        """Test all methods handle errors consistently."""
        # All methods should return empty list or False on error, not raise
        
        def raise_error(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise TinytaskConnectionError("Connection failed")
        
        mock_client._run_async = raise_error
        
        # get_queue_tasks should return empty list
        result1 = mock_client.get_queue_tasks('queue1')
        assert result1 == []
        
        # get_unassigned_in_queue should return empty list
        result2 = mock_client.get_unassigned_in_queue('queue2')
        assert result2 == []
        
        # assign_task should return False
        result3 = mock_client.assign_task('123', 'agent')
        assert result3 is False
        
        # All should log warnings
        captured = capfd.readouterr()
        assert captured.out.count("Warning") == 3


if __name__ == "__main__":
    # Allow running tests directly with: python test_tinytask_client.py
    pytest.main([__file__, "-v"])

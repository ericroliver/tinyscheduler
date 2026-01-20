"""Tinytask MCP client for TinyScheduler."""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None
    sse_client = None


@dataclass
class Task:
    """Represents a tinytask task."""
    
    task_id: str
    agent: str
    status: str
    recipe: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Task":
        """
        Create Task from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Task instance
        """
        return cls(
            task_id=str(data.get('id', data.get('task_id', ''))),
            agent=data.get('assigned_to', data.get('agent', '')),
            status=data.get('status', 'idle'),
            recipe=data.get('recipe'),
            created_at=data.get('created_at'),
            metadata=data.get('metadata', {}),
        )


class TinytaskClientError(Exception):
    """Base exception for Tinytask client errors."""
    pass


class TinytaskConnectionError(TinytaskClientError):
    """Raised when connection to Tinytask server fails."""
    pass


class TinytaskAPIError(TinytaskClientError):
    """Raised when Tinytask API returns an error."""
    pass


class TinytaskClient:
    """
    Client for interacting with Tinytask MCP server.
    
    Uses the MCP protocol over SSE transport to communicate with the tinytask server.
    """
    
    def __init__(
        self,
        endpoint: str,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0
    ):
        """
        Initialize Tinytask MCP client.
        
        Args:
            endpoint: Base URL for Tinytask MCP endpoint (e.g., http://localhost:3000)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            backoff_factor: Multiplier for retry delay on each attempt
        """
        if ClientSession is None or sse_client is None:
            raise TinytaskClientError("mcp library is required for TinytaskClient. Install with: pip install mcp")
        
        self.endpoint = endpoint.rstrip('/')
        self.mcp_url = f"{self.endpoint}/mcp"
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self._session = None
        self._read_stream = None
        self._write_stream = None
        self._streams_context = None
    
    async def _ensure_connected(self):
        """Ensure MCP session is connected."""
        if self._session is None:
            try:
                # Connect to SSE endpoint using async context manager
                streams = sse_client(self.mcp_url)
                self._read_stream, self._write_stream = await streams.__aenter__()
                self._session = ClientSession(self._read_stream, self._write_stream)
                await self._session.__aenter__()
                self._streams_context = streams  # Keep reference for cleanup
            except Exception as e:
                raise TinytaskConnectionError(f"Failed to connect to MCP server at {self.mcp_url}: {e}")
    
    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool with retry logic.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result
            
        Raises:
            TinytaskConnectionError: If connection fails after retries
            TinytaskAPIError: If tool call returns error
        """
        last_error = TinytaskConnectionError("Maximum retries exceeded")
        delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            try:
                await self._ensure_connected()
                
                # Call the tool
                result = await self._session.call_tool(tool_name, arguments)
                
                # Parse result
                if result.isError:
                    raise TinytaskAPIError(f"Tool error: {result.content}")
                
                # Extract text content from result
                if result.content:
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            try:
                                return json.loads(content_item.text)
                            except json.JSONDecodeError:
                                return content_item.text
                
                return None
            
            except TinytaskAPIError:
                # Don't retry API errors
                raise
            except Exception as e:
                last_error = TinytaskConnectionError(f"Tool call failed: {e}")
                # Close session on error to force reconnect
                await self._close_session()
            
            # Retry with exponential backoff
            if attempt < self.max_retries - 1:
                await asyncio.sleep(delay)
                delay *= self.backoff_factor
        
        # All retries exhausted
        raise last_error
    
    async def _close_session(self):
        """Close the MCP session."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass  # Ignore errors during session cleanup
            finally:
                self._session = None
                self._read_stream = None
                self._write_stream = None
    
    def _run_async(self, coro):
        """Run async coroutine in sync context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
    
    def list_idle_tasks(self, agent: str, limit: int = 10) -> List[Task]:
        """
        List idle tasks for an agent.
        
        Args:
            agent: Agent name to query tasks for
            limit: Maximum number of tasks to return
            
        Returns:
            List of Task objects in idle state
            
        Raises:
            TinytaskClientError: If request fails
        """
        try:
            # Call list_tasks tool with filters
            result = self._run_async(
                self._call_tool('list_tasks', {
                    'assigned_to': agent,
                    'status': 'idle',
                    'limit': limit
                })
            )
            
            # Parse response
            if isinstance(result, dict):
                tasks_data = result.get('tasks', [])
            elif isinstance(result, list):
                tasks_data = result
            else:
                tasks_data = []
            
            return [Task.from_dict(task_data) for task_data in tasks_data]
        
        except (TinytaskConnectionError, TinytaskAPIError) as e:
            # Log but don't crash - scheduler should continue
            print(f"Warning: Failed to list idle tasks for agent '{agent}': {e}")
            return []
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get task by ID.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task object if found, None otherwise
            
        Raises:
            TinytaskClientError: If request fails
        """
        try:
            result = self._run_async(
                self._call_tool('get_task', {'id': int(task_id)})
            )
            
            if not result:
                return None
            
            # Result might be the task directly or wrapped
            if isinstance(result, dict):
                task_data = result.get('task', result)
                return Task.from_dict(task_data)
            
            return None
        
        except TinytaskAPIError as e:
            # Task not found
            if 'not found' in str(e).lower():
                return None
            raise
    
    def update_task_state(
        self,
        task_id: str,
        status: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update task status and metadata.
        
        Args:
            task_id: Task identifier
            status: New status (e.g., 'idle', 'working', 'complete')
            metadata: Optional metadata to update
            
        Returns:
            True if update succeeded
            
        Raises:
            TinytaskClientError: If request fails
        """
        try:
            arguments = {
                'id': int(task_id),
                'status': status
            }
            
            # Note: MCP update_task may not support arbitrary metadata
            # This would need custom implementation in tinytask if needed
            
            self._run_async(self._call_tool('update_task', arguments))
            return True
        
        except (TinytaskConnectionError, TinytaskAPIError) as e:
            print(f"Warning: Failed to update task {task_id} to status '{status}': {e}")
            return False
    
    def claim_task(self, task_id: str, agent: str) -> bool:
        """
        Claim a task for execution (mark as working).
        
        Args:
            task_id: Task identifier
            agent: Agent claiming the task
            
        Returns:
            True if claim succeeded
        """
        return self.update_task_state(task_id, 'working')
    
    def complete_task(
        self,
        task_id: str,
        success: bool = True,
        result: Optional[Dict] = None
    ) -> bool:
        """
        Mark task as completed.
        
        Args:
            task_id: Task identifier
            success: Whether task completed successfully
            result: Optional result data
            
        Returns:
            True if update succeeded
        """
        status = 'complete' if success else 'idle'
        return self.update_task_state(task_id, status)
    
    def requeue_task(self, task_id: str, reason: Optional[str] = None) -> bool:
        """
        Requeue a task (return to idle state).
        
        Args:
            task_id: Task identifier
            reason: Optional reason for requeue
            
        Returns:
            True if requeue succeeded
        """
        return self.update_task_state(task_id, 'idle')
    
    def get_queue_tasks(
        self,
        queue_name: str,
        assigned_to: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        Get tasks in a queue with optional filters.
        
        Args:
            queue_name: Queue name to query
            assigned_to: Optional filter by assignee
            status: Optional filter by status
            limit: Maximum number of tasks
            
        Returns:
            List of Task objects
        """
        try:
            arguments = {
                'queue_name': queue_name,
                'limit': limit
            }
            if assigned_to:
                arguments['assigned_to'] = assigned_to
            if status:
                arguments['status'] = status
            
            result = self._run_async(
                self._call_tool('get_queue_tasks', arguments)
            )
            
            # Parse response
            if isinstance(result, dict):
                tasks_data = result.get('tasks', [])
            elif isinstance(result, list):
                tasks_data = result
            else:
                tasks_data = []
            
            return [Task.from_dict(task_data) for task_data in tasks_data]
        
        except (TinytaskConnectionError, TinytaskAPIError) as e:
            print(f"Warning: Failed to get queue tasks for '{queue_name}': {e}")
            return []
    
    def get_unassigned_in_queue(self, queue_name: str, limit: int = 100) -> List[Task]:
        """
        Get unassigned tasks in a queue.
        
        Args:
            queue_name: Queue name to query
            limit: Maximum number of tasks
            
        Returns:
            List of unassigned Task objects
        """
        try:
            result = self._run_async(
                self._call_tool('get_unassigned_in_queue', {
                    'queue_name': queue_name
                })
            )
            
            # Parse response
            if isinstance(result, dict):
                tasks_data = result.get('tasks', [])
            elif isinstance(result, list):
                tasks_data = result
            else:
                tasks_data = []
            
            return [Task.from_dict(task_data) for task_data in tasks_data][:limit]
        
        except (TinytaskConnectionError, TinytaskAPIError) as e:
            print(f"Warning: Failed to get unassigned tasks for queue '{queue_name}': {e}")
            return []
    
    def assign_task(self, task_id: str, agent: str) -> bool:
        """
        Assign a task to an agent.
        
        Args:
            task_id: Task identifier (string or int)
            agent: Agent name to assign to
            
        Returns:
            True if assignment succeeded, False otherwise
        """
        try:
            arguments = {
                'id': int(task_id),
                'assigned_to': agent
            }
            
            self._run_async(self._call_tool('update_task', arguments))
            return True
        
        except (TinytaskConnectionError, TinytaskAPIError) as e:
            print(f"Warning: Failed to assign task {task_id} to agent '{agent}': {e}")
            return False
    
    def health_check(self) -> bool:
        """
        Check if Tinytask server is accessible.
        
        Returns:
            True if server is healthy
        """
        try:
            # Try to connect to the MCP endpoint
            import httpx
            response = httpx.get(f"{self.endpoint}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def close(self):
        """Close the client session."""
        if self._session:
            self._run_async(self._close_session())
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

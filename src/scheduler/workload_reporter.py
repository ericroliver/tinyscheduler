"""Workload Reporter for TinyTask.

Generates comprehensive reports on task workload and status by querying the TinyTask MCP server.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .tinytask_client import TinytaskClient, TinytaskClientError


@dataclass
class TaskDetail:
    """Detailed task information."""
    id: int
    title: str
    description: Optional[str]
    status: str
    assigned_to: Optional[str]
    created_by: Optional[str]
    priority: int
    tags: List[str]
    created_at: str
    updated_at: str
    age_hours: float
    comment_count: int
    link_count: int


@dataclass
class AgentWorkload:
    """Per-agent workload breakdown."""
    agent_name: str
    total_tasks: int
    idle_tasks: int
    working_tasks: int
    task_ids: List[int]


@dataclass
class WorkloadSummary:
    """Overall workload summary."""
    total_open_tasks: int
    total_idle: int
    total_working: int
    total_agents: int
    agents_with_work: List[str]


@dataclass
class PriorityDistribution:
    """Task priority distribution."""
    by_priority: Dict[int, int]  # priority -> count
    highest_priority: int
    lowest_priority: int
    average_priority: float


@dataclass
class AgeMetrics:
    """Task age statistics."""
    oldest_task_age_hours: float
    newest_task_age_hours: float
    average_task_age_hours: float
    oldest_task_id: int
    newest_task_id: int


@dataclass
class WorkloadData:
    """Complete workload report data."""
    summary: WorkloadSummary
    agent_breakdown: Dict[str, AgentWorkload]
    priority_distribution: PriorityDistribution
    age_metrics: AgeMetrics
    tasks: List[TaskDetail]
    generated_at: str  # ISO 8601 timestamp


class WorkloadReporter:
    """Main workload reporter implementation."""
    
    def __init__(self, tinytask_client: TinytaskClient):
        """
        Initialize workload reporter.
        
        Args:
            tinytask_client: Initialized TinytaskClient instance
        """
        self.client = tinytask_client
    
    def collect_workload_data(
        self,
        status_filter: Optional[List[str]] = None,
        agent_filter: Optional[str] = None
    ) -> WorkloadData:
        """
        Collect and aggregate workload data from TinyTask.
        
        Args:
            status_filter: Filter by statuses (default: ['idle', 'working'])
            agent_filter: Filter by specific agent
            
        Returns:
            WorkloadData with complete report information
            
        Raises:
            TinytaskClientError: If data collection fails
        """
        if status_filter is None:
            status_filter = ['idle', 'working']
        
        # Collect all tasks matching filters
        all_tasks = []
        for status in status_filter:
            tasks = self._list_tasks_by_status(status, agent_filter)
            all_tasks.extend(tasks)
        
        if not all_tasks:
            # Return empty report
            return self._create_empty_report()
        
        # Enrich tasks with detailed information
        detailed_tasks = []
        for task_data in all_tasks:
            try:
                task_detail = self._enrich_task(task_data)
                detailed_tasks.append(task_detail)
            except Exception as e:
                # Log and skip tasks that fail to enrich
                print(f"Warning: Failed to enrich task {task_data.get('id')}: {e}")
                continue
        
        if not detailed_tasks:
            return self._create_empty_report()
        
        # Calculate all metrics
        summary = self._calculate_summary(detailed_tasks)
        agent_breakdown = self._calculate_agent_breakdown(detailed_tasks)
        priority_dist = self._calculate_priority_distribution(detailed_tasks)
        age_metrics = self._calculate_age_metrics(detailed_tasks)
        
        # Generate timestamp
        generated_at = datetime.now(timezone.utc).isoformat()
        
        return WorkloadData(
            summary=summary,
            agent_breakdown=agent_breakdown,
            priority_distribution=priority_dist,
            age_metrics=age_metrics,
            tasks=detailed_tasks,
            generated_at=generated_at
        )
    
    def _list_tasks_by_status(
        self,
        status: str,
        agent_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        List tasks by status from TinyTask.
        
        Args:
            status: Task status to filter by
            agent_filter: Optional agent filter
            
        Returns:
            List of task dictionaries
        """
        try:
            arguments = {
                'status': status,
                'limit': 1000,  # Get all tasks
                'include_archived': False
            }
            
            if agent_filter:
                arguments['assigned_to'] = agent_filter
            
            result = self.client._run_async(
                self.client._call_tool('list_tasks', arguments)
            )
            
            # Parse response
            if isinstance(result, dict):
                tasks_data = result.get('tasks', [])
            elif isinstance(result, list):
                tasks_data = result
            else:
                tasks_data = []
            
            return tasks_data
        
        except TinytaskClientError as e:
            print(f"Warning: Failed to list tasks with status '{status}': {e}")
            return []
    
    def _enrich_task(self, task_data: Dict) -> TaskDetail:
        """
        Enrich task data with comments and links count.
        
        Args:
            task_data: Basic task data dictionary
            
        Returns:
            TaskDetail with complete information
        """
        task_id = task_data.get('id')
        
        # Get full task details including comments and links
        try:
            full_task = self.client._run_async(
                self.client._call_tool('get_task', {'id': int(task_id)})
            )
            
            if full_task and isinstance(full_task, dict):
                task_info = full_task.get('task', full_task)
                comments = task_info.get('comments', [])
                links = task_info.get('links', [])
            else:
                comments = []
                links = []
        except Exception:
            # Fallback to basic data
            comments = []
            links = []
        
        # Calculate age
        created_at = task_data.get('created_at', '')
        if created_at:
            try:
                created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                age_hours = (datetime.now(timezone.utc) - created_time).total_seconds() / 3600
            except Exception:
                age_hours = 0.0
        else:
            age_hours = 0.0
        
        return TaskDetail(
            id=int(task_id),
            title=task_data.get('title', ''),
            description=task_data.get('description'),
            status=task_data.get('status', 'idle'),
            assigned_to=task_data.get('assigned_to'),
            created_by=task_data.get('created_by'),
            priority=task_data.get('priority', 0),
            tags=task_data.get('tags', []),
            created_at=created_at,
            updated_at=task_data.get('updated_at', ''),
            age_hours=round(age_hours, 2),
            comment_count=len(comments),
            link_count=len(links)
        )
    
    def _calculate_summary(self, tasks: List[TaskDetail]) -> WorkloadSummary:
        """Calculate overall workload summary."""
        total_idle = sum(1 for t in tasks if t.status == 'idle')
        total_working = sum(1 for t in tasks if t.status == 'working')
        
        # Get unique agents
        agents_with_work = sorted(set(t.assigned_to for t in tasks if t.assigned_to))
        
        return WorkloadSummary(
            total_open_tasks=len(tasks),
            total_idle=total_idle,
            total_working=total_working,
            total_agents=len(agents_with_work),
            agents_with_work=agents_with_work
        )
    
    def _calculate_agent_breakdown(
        self,
        tasks: List[TaskDetail]
    ) -> Dict[str, AgentWorkload]:
        """Calculate per-agent workload breakdown."""
        agent_tasks: Dict[str, List[TaskDetail]] = {}
        
        for task in tasks:
            agent = task.assigned_to or 'unassigned'
            if agent not in agent_tasks:
                agent_tasks[agent] = []
            agent_tasks[agent].append(task)
        
        breakdown = {}
        for agent_name, agent_task_list in agent_tasks.items():
            idle_count = sum(1 for t in agent_task_list if t.status == 'idle')
            working_count = sum(1 for t in agent_task_list if t.status == 'working')
            task_ids = [t.id for t in agent_task_list]
            
            breakdown[agent_name] = AgentWorkload(
                agent_name=agent_name,
                total_tasks=len(agent_task_list),
                idle_tasks=idle_count,
                working_tasks=working_count,
                task_ids=task_ids
            )
        
        return breakdown
    
    def _calculate_priority_distribution(
        self,
        tasks: List[TaskDetail]
    ) -> PriorityDistribution:
        """Calculate task priority distribution."""
        by_priority: Dict[int, int] = {}
        
        for task in tasks:
            priority = task.priority
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        if not by_priority:
            return PriorityDistribution(
                by_priority={},
                highest_priority=0,
                lowest_priority=0,
                average_priority=0.0
            )
        
        priorities = list(by_priority.keys())
        total_priority = sum(p * count for p, count in by_priority.items())
        
        return PriorityDistribution(
            by_priority=by_priority,
            highest_priority=max(priorities),
            lowest_priority=min(priorities),
            average_priority=round(total_priority / len(tasks), 2)
        )
    
    def _calculate_age_metrics(self, tasks: List[TaskDetail]) -> AgeMetrics:
        """Calculate task age statistics."""
        if not tasks:
            return AgeMetrics(
                oldest_task_age_hours=0.0,
                newest_task_age_hours=0.0,
                average_task_age_hours=0.0,
                oldest_task_id=0,
                newest_task_id=0
            )
        
        # Find oldest and newest
        oldest_task = max(tasks, key=lambda t: t.age_hours)
        newest_task = min(tasks, key=lambda t: t.age_hours)
        
        # Calculate average
        total_age = sum(t.age_hours for t in tasks)
        avg_age = total_age / len(tasks)
        
        return AgeMetrics(
            oldest_task_age_hours=oldest_task.age_hours,
            newest_task_age_hours=newest_task.age_hours,
            average_task_age_hours=round(avg_age, 2),
            oldest_task_id=oldest_task.id,
            newest_task_id=newest_task.id
        )
    
    def _create_empty_report(self) -> WorkloadData:
        """Create an empty report when no tasks are found."""
        return WorkloadData(
            summary=WorkloadSummary(
                total_open_tasks=0,
                total_idle=0,
                total_working=0,
                total_agents=0,
                agents_with_work=[]
            ),
            agent_breakdown={},
            priority_distribution=PriorityDistribution(
                by_priority={},
                highest_priority=0,
                lowest_priority=0,
                average_priority=0.0
            ),
            age_metrics=AgeMetrics(
                oldest_task_age_hours=0.0,
                newest_task_age_hours=0.0,
                average_task_age_hours=0.0,
                oldest_task_id=0,
                newest_task_id=0
            ),
            tasks=[],
            generated_at=datetime.now(timezone.utc).isoformat()
        )
    
    def to_json(self, data: WorkloadData, indent: int = 2) -> str:
        """
        Convert workload data to JSON string.
        
        Args:
            data: WorkloadData to serialize
            indent: JSON indentation level
            
        Returns:
            JSON string representation
        """
        def convert_to_dict(obj):
            """Recursively convert dataclasses to dicts."""
            if hasattr(obj, '__dataclass_fields__'):
                return asdict(obj)
            return obj
        
        data_dict = convert_to_dict(data)
        return json.dumps(data_dict, indent=indent)

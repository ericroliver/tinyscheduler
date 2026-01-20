"""Report formatters for TinyTask workload reporter.

Transforms JSON data into human-readable console output.
"""

from typing import Dict, List, Optional

from .workload_reporter import (
    WorkloadData, WorkloadSummary, AgentWorkload,
    PriorityDistribution, AgeMetrics, TaskDetail
)


class TableFormatter:
    """Utility for formatting tabular data."""
    
    @staticmethod
    def format_table(
        headers: List[str],
        rows: List[List[str]],
        alignments: Optional[List[str]] = None
    ) -> str:
        """
        Format data as aligned table.
        
        Args:
            headers: Column headers
            rows: Data rows
            alignments: List of 'left', 'right', 'center' per column (default: all left)
            
        Returns:
            Formatted table string
        """
        if not headers or not rows:
            return ""
        
        # Default to left alignment
        if alignments is None:
            alignments = ['left'] * len(headers)
        
        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Format header
        header_parts = []
        separator_parts = []
        for i, (header, width) in enumerate(zip(headers, col_widths)):
            alignment = alignments[i] if i < len(alignments) else 'left'
            header_parts.append(TableFormatter._align_cell(header, width, alignment))
            separator_parts.append('-' * width)
        
        lines = [
            '  '.join(header_parts),
            '  '.join(separator_parts)
        ]
        
        # Format rows
        for row in rows:
            row_parts = []
            for i, (cell, width) in enumerate(zip(row, col_widths)):
                alignment = alignments[i] if i < len(alignments) else 'left'
                row_parts.append(TableFormatter._align_cell(str(cell), width, alignment))
            lines.append('  '.join(row_parts))
        
        return '\n'.join(lines)
    
    @staticmethod
    def _align_cell(text: str, width: int, alignment: str) -> str:
        """Align text in a cell."""
        if alignment == 'right':
            return text.rjust(width)
        elif alignment == 'center':
            return text.center(width)
        else:  # left
            return text.ljust(width)


class ConsoleFormatter:
    """Format workload data for console output."""
    
    # ANSI color codes
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'cyan': '\033[36m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'red': '\033[31m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
    }
    
    def __init__(self, use_colors: bool = True):
        """
        Initialize console formatter.
        
        Args:
            use_colors: Whether to use ANSI color codes
        """
        self.use_colors = use_colors
    
    def _color(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if not self.use_colors:
            return text
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"
    
    def format_report(self, data: WorkloadData) -> str:
        """
        Generate formatted console report.
        
        Args:
            data: WorkloadData to format
            
        Returns:
            Multi-line formatted string ready for console output
        """
        sections = []
        
        # Header
        sections.append(self._format_header(data.generated_at))
        
        # Summary
        sections.append(self.format_summary(data.summary))
        
        # Agent breakdown
        if data.agent_breakdown:
            sections.append(self.format_agent_table(data.agent_breakdown))
        
        # Priority distribution
        if data.priority_distribution.by_priority:
            sections.append(self.format_priority_chart(data.priority_distribution))
        
        # Age metrics
        if data.tasks:
            sections.append(self.format_age_metrics(data.age_metrics))
        
        # Task table
        if data.tasks:
            sections.append(self.format_task_table(data.tasks))
        
        # Footer
        sections.append('=' * 60)
        
        return '\n\n'.join(sections)
    
    def _format_header(self, timestamp: str) -> str:
        """Format report header."""
        lines = [
            '=' * 60,
            self._color('       TinyTask Workload Report', 'bold'),
            '=' * 60,
            f"Generated: {timestamp}"
        ]
        return '\n'.join(lines)
    
    def format_summary(self, summary: WorkloadSummary) -> str:
        """Format summary section."""
        lines = [
            self._color('SUMMARY', 'bold'),
            '-' * 20,
            f"Total Open Tasks: {self._color(str(summary.total_open_tasks), 'cyan')}"
        ]
        
        if summary.total_open_tasks > 0:
            lines.extend([
                f"  • Idle:    {self._color(str(summary.total_idle), 'yellow')}",
                f"  • Working: {self._color(str(summary.total_working), 'green')}"
            ])
        
        if summary.agents_with_work:
            agent_list = ', '.join(summary.agents_with_work)
            lines.append(f"\nActive Agents: {summary.total_agents} ({agent_list})")
        else:
            lines.append(f"\nActive Agents: 0")
        
        return '\n'.join(lines)
    
    def format_agent_table(self, agent_breakdown: Dict[str, AgentWorkload]) -> str:
        """Format agent workload as table."""
        lines = [
            self._color('AGENT WORKLOAD', 'bold'),
            '-' * 30
        ]
        
        # Sort agents by total tasks (descending)
        sorted_agents = sorted(
            agent_breakdown.values(),
            key=lambda a: a.total_tasks,
            reverse=True
        )
        
        headers = ['Agent', 'Total', 'Idle', 'Working']
        rows = []
        
        for agent in sorted_agents:
            rows.append([
                agent.agent_name,
                str(agent.total_tasks),
                str(agent.idle_tasks),
                str(agent.working_tasks)
            ])
        
        alignments = ['left', 'right', 'right', 'right']
        table = TableFormatter.format_table(headers, rows, alignments)
        lines.append(table)
        
        return '\n'.join(lines)
    
    def format_priority_chart(self, priority_dist: PriorityDistribution) -> str:
        """Format priority distribution as text chart."""
        lines = [
            self._color('PRIORITY DISTRIBUTION', 'bold'),
            '-' * 40
        ]
        
        # Sort by priority (descending)
        sorted_priorities = sorted(priority_dist.by_priority.items(), reverse=True)
        
        total_tasks = sum(priority_dist.by_priority.values())
        max_count = max(priority_dist.by_priority.values())
        max_bar_length = 30
        
        headers = ['Priority', 'Count', 'Graph']
        rows = []
        
        for priority, count in sorted_priorities:
            percentage = (count / total_tasks * 100) if total_tasks > 0 else 0
            bar_length = int((count / max_count) * max_bar_length) if max_count > 0 else 0
            bar = '█' * bar_length
            graph = f"{bar} ({percentage:.0f}%)"
            
            rows.append([
                str(priority),
                str(count),
                graph
            ])
        
        alignments = ['right', 'right', 'left']
        table = TableFormatter.format_table(headers, rows, alignments)
        lines.append(table)
        
        lines.append(f"\nAverage Priority: {priority_dist.average_priority:.2f}")
        
        return '\n'.join(lines)
    
    def format_age_metrics(self, age_metrics: AgeMetrics) -> str:
        """Format age metrics section."""
        lines = [
            self._color('TASK AGE METRICS', 'bold'),
            '-' * 30,
            f"Oldest Task: {age_metrics.oldest_task_age_hours:.1f} hours (Task #{age_metrics.oldest_task_id})",
            f"Newest Task: {age_metrics.newest_task_age_hours:.1f} hours (Task #{age_metrics.newest_task_id})",
            f"Average Age: {age_metrics.average_task_age_hours:.1f} hours"
        ]
        
        return '\n'.join(lines)
    
    def format_task_table(self, tasks: List[TaskDetail]) -> str:
        """Format task list as table."""
        lines = [
            self._color(f'OPEN TASKS ({len(tasks)} total)', 'bold'),
            '-' * 60
        ]
        
        # Sort by priority (desc), then age (desc)
        sorted_tasks = sorted(tasks, key=lambda t: (-t.priority, -t.age_hours))
        
        # Limit to first 50 tasks for readability
        display_tasks = sorted_tasks[:50]
        
        headers = ['ID', 'Status', 'Agent', 'Pri', 'Age(h)', 'Title']
        rows = []
        
        for task in display_tasks:
            # Truncate title if too long
            title = task.title[:40] + '...' if len(task.title) > 40 else task.title
            agent = task.assigned_to or '-'
            
            rows.append([
                str(task.id),
                task.status,
                agent[:12],  # Truncate agent name
                str(task.priority),
                f"{task.age_hours:.1f}",
                title
            ])
        
        alignments = ['right', 'left', 'left', 'right', 'right', 'left']
        table = TableFormatter.format_table(headers, rows, alignments)
        lines.append(table)
        
        if len(tasks) > 50:
            lines.append(f"\n(Showing first 50 of {len(tasks)} tasks)")
        
        return '\n'.join(lines)

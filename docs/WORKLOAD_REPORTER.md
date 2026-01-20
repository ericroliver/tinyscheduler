# TinyTask Workload Reporter

A command-line tool for generating comprehensive reports on TinyTask workload and status.

## Overview

The Workload Reporter queries the TinyTask MCP server to provide detailed insights into task distribution, agent workload, priority distribution, and task age metrics. It supports both JSON and human-readable console output formats.

## Features

- **Real-time workload analysis** - Query current task status across all agents
- **Multiple output formats** - JSON for automation, console for human readability
- **Flexible filtering** - Filter by status, agent, or custom criteria
- **Rich metrics** - Summary stats, agent breakdown, priority distribution, age metrics
- **Colored console output** - Easy-to-read formatted tables with optional colors
- **File export** - Save reports to files for archiving or sharing

## Installation

The workload reporter is part of the Calypso project. Ensure you have the required dependencies:

```bash
cd workspace/calypso
pip install mcp
```

## Usage

### Basic Usage

Generate a console report of all open (idle and working) tasks:

```bash
cd workspace/calypso
./workload-reporter
```

Or using the full path:

```bash
python workspace/calypso/scripts/workload_reporter.py
```

### Command-Line Options

```
usage: workload-reporter [-h] [--format {json,console,both}] [--output OUTPUT]
                            [--status {idle,working,complete} [{idle,working,complete} ...]]
                            [--agent AGENT] [--mcp-endpoint MCP_ENDPOINT]
                            [--no-color] [--env-file ENV_FILE] [--verbose]

optional arguments:
  -h, --help            show this help message and exit
  --format {json,console,both}
                        Output format (default: console)
  --output OUTPUT, -o OUTPUT
                        Output file (default: stdout)
  --status {idle,working,complete} [{idle,working,complete} ...]
                        Filter by status (default: idle working)
  --agent AGENT         Filter by specific agent
  --mcp-endpoint MCP_ENDPOINT
                        TinyTask MCP endpoint (default: $TINYTASK_ENDPOINT or
                        http://localhost:3000)
  --no-color            Disable colored output
  --env-file ENV_FILE   Path to .env file for configuration
  --verbose, -v         Enable verbose output
```

### Examples

#### Generate JSON Report

```bash
./workload-reporter --format json
```

Output:
```json
{
  "summary": {
    "total_open_tasks": 15,
    "total_idle": 8,
    "total_working": 7,
    "total_agents": 3,
    "agents_with_work": ["dispatcher", "architect", "code"]
  },
  ...
}
```

#### Save Report to File

```bash
python scripts/workload_reporter.py --output workload-report.txt
```

#### Filter by Agent

```bash
python scripts/workload_reporter.py --agent dispatcher
```

#### Include Completed Tasks

```bash
python scripts/workload_reporter.py --status idle working complete
```

#### Generate Both Formats

```bash
python scripts/workload_reporter.py --format both --output reports/workload
```

This creates:
- `reports/workload.json` - JSON format
- `reports/workload.txt` - Console format
- Prints colored console output to stdout

#### Using Custom Endpoint

```bash
python scripts/workload_reporter.py --mcp-endpoint http://tinytask.example.com:3000
```

Or set environment variable:
```bash
export TINYTASK_ENDPOINT=http://tinytask.example.com:3000
python scripts/workload_reporter.py
```

#### Load from Environment File

```bash
python scripts/workload_reporter.py --env-file .env
```

## Console Output Format

The console format provides a human-readable report with the following sections:

### Header
```
============================================================
            TinyTask Workload Report
============================================================
Generated: 2025-12-28T23:00:00Z
```

### Summary
Overview of total tasks, status breakdown, and active agents:
```
SUMMARY
-------
Total Open Tasks: 15
  • Idle:     8
  • Working:  7

Active Agents: 3 (dispatcher, architect, code)
```

### Agent Workload
Tabular breakdown of tasks per agent:
```
AGENT WORKLOAD
--------------
Agent         Total  Idle  Working
-----------  ------  ----  -------
dispatcher        5     3        2
architect         6     4        2
code              4     1        3
```

### Priority Distribution
Visual chart of task priorities:
```
PRIORITY DISTRIBUTION
---------------------
Priority  Count  Graph
--------  -----  -------------------------
    2         2  ████ (13%)
    1         3  ██████ (20%)
    0        10  ████████████████████ (67%)

Average Priority: 0.47
```

### Task Age Metrics
Statistics about task age:
```
TASK AGE METRICS
----------------
Oldest Task:  48.5 hours (Task #1)
Newest Task:  0.25 hours (Task #15)
Average Age:  12.8 hours
```

### Task Table
Detailed list of all tasks (first 50 shown):
```
OPEN TASKS (15 total)
---------------------
ID  Status    Agent      Pri  Age(h)  Title
--  --------  ---------  ---  ------  --------------------------
 1  working   code         2    48.5  Implement user authentication
 2  idle      dispatcher   1    36.2  Create API documentation
 3  working   architect    1    32.0  Design database schema
...
```

## JSON Output Format

The JSON format provides structured data suitable for automation and integration:

```json
{
  "summary": {
    "total_open_tasks": 15,
    "total_idle": 8,
    "total_working": 7,
    "total_agents": 3,
    "agents_with_work": ["dispatcher", "architect", "code"]
  },
  "agent_breakdown": {
    "dispatcher": {
      "agent_name": "dispatcher",
      "total_tasks": 5,
      "idle_tasks": 3,
      "working_tasks": 2,
      "task_ids": [1, 2, 3, 4, 5]
    }
  },
  "priority_distribution": {
    "by_priority": {
      "0": 10,
      "1": 3,
      "2": 2
    },
    "highest_priority": 2,
    "lowest_priority": 0,
    "average_priority": 0.47
  },
  "age_metrics": {
    "oldest_task_age_hours": 48.5,
    "newest_task_age_hours": 0.25,
    "average_task_age_hours": 12.8,
    "oldest_task_id": 1,
    "newest_task_id": 15
  },
  "tasks": [
    {
      "id": 1,
      "title": "Implement user authentication",
      "description": "Add JWT-based authentication",
      "status": "working",
      "assigned_to": "code",
      "created_by": "product",
      "priority": 2,
      "tags": ["auth", "security"],
      "created_at": "2025-12-26T12:00:00Z",
      "updated_at": "2025-12-28T08:00:00Z",
      "age_hours": 48.5,
      "comment_count": 3,
      "link_count": 1
    }
  ],
  "generated_at": "2025-12-28T23:00:00Z"
}
```

## Integration Examples

### Shell Script Monitoring

```bash
#!/bin/bash
# Check if any agent has more than 10 idle tasks

REPORT=$(python scripts/workload_reporter.py --format json --agent dispatcher)
IDLE_COUNT=$(echo "$REPORT" | jq '.summary.total_idle')

if [ "$IDLE_COUNT" -gt 10 ]; then
    echo "Alert: Dispatcher has $IDLE_COUNT idle tasks!"
    # Send notification
fi
```

### Python Integration

```python
from src.scheduler.tinytask_client import TinytaskClient
from src.scheduler.workload_reporter import WorkloadReporter

# Initialize
client = TinytaskClient(endpoint='http://localhost:3000')
reporter = WorkloadReporter(client)

# Collect data
data = reporter.collect_workload_data(status_filter=['idle', 'working'])

# Access metrics
print(f"Total tasks: {data.summary.total_open_tasks}")
print(f"Average priority: {data.priority_distribution.average_priority}")

# Process agent data
for agent_name, workload in data.agent_breakdown.items():
    if workload.idle_tasks > 5:
        print(f"Agent {agent_name} has {workload.idle_tasks} idle tasks")

client.close()
```

### Cron Job for Daily Reports

```cron
# Generate daily workload report at 9 AM
0 9 * * * cd /path/to/calypso && python scripts/workload_reporter.py --format both --output reports/daily-$(date +\%Y\%m\%d)
```

## Troubleshooting

### Connection Errors

If you see connection errors:

```
Error: Failed to connect to MCP server at http://localhost:3000/mcp: ...
```

Check:
1. TinyTask server is running
2. MCP endpoint URL is correct
3. Network connectivity
4. Firewall settings

### No Tasks Found

If the report shows zero tasks:

```
Total Open Tasks: 0
Active Agents: 0
```

This could mean:
- No tasks exist in the specified statuses
- Your filters are too restrictive
- All tasks are archived

Try including all statuses:
```bash
python scripts/workload_reporter.py --status idle working complete
```

### Import Errors

If you see `ModuleNotFoundError: No module named 'mcp'`:

```bash
pip install mcp
```

### Slow Performance

For large task sets (>1000 tasks), the reporter may take time to:
1. Query all tasks
2. Enrich each task with comments/links count

Consider:
- Filtering by specific agents
- Using status filters to reduce scope
- Running during off-peak hours

## Architecture

The workload reporter follows a data-first architecture:

1. **Data Collection** - Query TinyTask MCP server for task data
2. **Enrichment** - Fetch detailed information (comments, links)
3. **Aggregation** - Calculate metrics and statistics
4. **Formatting** - Transform to JSON or console output

### Components

- [`workload_reporter.py`](../src/scheduler/workload_reporter.py) - Core data collection and aggregation
- [`report_formatters.py`](../src/scheduler/report_formatters.py) - Console output formatting
- [`tinytask_client.py`](../src/scheduler/tinytask_client.py) - TinyTask MCP client
- [`scripts/workload_reporter.py`](../scripts/workload_reporter.py) - CLI interface

## Future Enhancements

Potential improvements planned:

1. **Historical Analysis** - Track workload trends over time
2. **Watch Mode** - Auto-refresh reports in real-time
3. **Alerts** - Threshold-based notifications
4. **Export Formats** - CSV, HTML, Markdown
5. **Bottleneck Detection** - Identify workflow bottlenecks
6. **Performance Metrics** - Agent productivity statistics

## See Also

- [Technical Architecture](../../docs/technical/workload-reporter-architecture.md)
- [TinyTask MCP Server](https://github.com/tinytask-mcp)
- [Calypso Scheduler](../src/scheduler/README.md)

## License

Part of the Calypso project.

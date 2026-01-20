# TinyScheduler and Workload Reporter

This module provides TinyTask integration for the Calypso project, including a scheduler for task execution and a workload reporter for task analysis.

## Components

### TinyTask Client (`tinytask_client.py`)

MCP client for communicating with TinyTask server:

- Connect to TinyTask MCP server via SSE transport
- List, get, and update tasks
- Claim and complete tasks
- Automatic retry logic with exponential backoff

### Workload Reporter (`workload_reporter.py`)

Core workload analysis engine:

- Collect comprehensive task data from TinyTask
- Calculate workload metrics and statistics
- Generate structured data for reporting
- Filter by status and agent

### Report Formatters (`report_formatters.py`)

Console output formatting:

- Transform JSON data to human-readable tables
- Colored console output (optional)
- Priority distribution charts
- Age metrics visualization

### CLI Tools

#### Task Scheduler (`scripts/run_agent.py`)

Execute scheduled tasks using recipes.

#### Workload Reporter (`scripts/workload_reporter.py`)

Generate workload reports. See [WORKLOAD_REPORTER.md](../../docs/WORKLOAD_REPORTER.md) for full documentation.

## Quick Start

### Generate a Workload Report

```bash
python scripts/workload_reporter.py
```

### Use in Python Code

```python
from src.scheduler.tinytask_client import TinytaskClient
from src.scheduler.workload_reporter import WorkloadReporter

client = TinytaskClient(endpoint='http://localhost:3000')
reporter = WorkloadReporter(client)

data = reporter.collect_workload_data()
print(f"Total tasks: {data.summary.total_open_tasks}")

client.close()
```

## Configuration

Set the TinyTask endpoint:

```bash
export TINYTASK_ENDPOINT=http://localhost:3000
```

Or use command-line arguments:

```bash
python scripts/workload_reporter.py --mcp-endpoint http://localhost:3000
```

## Dependencies

- `mcp` - Model Context Protocol client library
- Python 3.7+ with `dataclasses` support

Install dependencies:

```bash
pip install mcp
```

## Documentation

- [Workload Reporter Documentation](../../docs/WORKLOAD_REPORTER.md)
- [Workload Reporter Architecture](../../../docs/technical/workload-reporter-architecture.md)

## Error Handling

The client includes robust error handling:

- **TinytaskConnectionError** - Connection failures (with retry)
- **TinytaskAPIError** - API-level errors
- **TinytaskClientError** - Base exception class

## Testing

Test the workload reporter with a live TinyTask server:

```bash
python scripts/workload_reporter.py --verbose
```

This will show detailed progress and any errors encountered.

## License

Part of the Calypso project.

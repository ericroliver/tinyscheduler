# 🕐 TinyScheduler

<div align="center">

**A Kubernetes-style reconciliation control plane for AI agent orchestration**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

[Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [Security](#-security) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---

## 🎯 What is TinyScheduler?

TinyScheduler is a **lightweight, file-backed task scheduler** that coordinates [Goose](https://github.com/square/goose) agent execution using a Kubernetes-inspired reconciliation loop. Think of it as a miniature Kubernetes control plane, but for AI agents instead of containers.

**Built for reliability**: File-based state, atomic operations, crash-safe recovery, and zero external dependencies.

### Why TinyScheduler?

- 🎯 **Declarative Agent Management** - Define desired state, let reconciliation handle the rest
- 🔄 **Automatic Recovery** - Detects and recovers stale/orphaned tasks via heartbeat monitoring
- 📊 **Queue-Based Load Balancing** - Intelligently distribute tasks across agent pools
- 🔒 **Concurrency Control** - Enforce per-agent slot limits and prevent resource exhaustion
- 📁 **File-Backed State** - No database required, human-readable JSON lease files
- 🚀 **Production Ready** - Lock file protection, atomic writes, comprehensive logging

## ✨ Features

### Core Capabilities

- **🔄 Reconciliation Loop** - Periodically scans task queues and reconciles with running agents
- **📋 File-Based Leases** - Authoritative tracking of in-flight tasks via JSON files
- **💓 Heartbeat Monitoring** - Automatic detection and recovery of stale/failed tasks
- **⚖️ Queue-Based Assignment** - Automatic task distribution across agent pools by type (dev, qa, product, etc.)
- **🎯 Agent Pooling** - Multiple agents can service the same queue with intelligent load balancing
- **🔗 Task Blocking Awareness** - Respects TinyTask blocking relationships, filtering blocked tasks and prioritizing blocker tasks
- **🔐 Lock File Protection** - Prevents overlapping scheduler runs
- **⏱️ Configurable Timeouts** - Max runtime, heartbeat intervals, loop timing
- **🔍 Observability** - Structured logging, lease inspection, dry-run mode

### Queue Integration

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  Tinytask   │◄────►│ TinyScheduler│◄────►│ Goose Agents│
│   Queues    │      │ Reconciliation│      │   (Pooled)  │
└─────────────┘      └──────────────┘      └─────────────┘
     │                      │                      │
  dev, qa,            Load Balancing          vaela, damien,
  product                   +                 oscar, remy...
                    Lease Tracking
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- [Goose](https://github.com/square/goose) installed
- [Tinytask](https://github.com/block/tinytask) MCP server running

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/tinyscheduler.git
cd tinyscheduler

# Make the CLI executable
chmod +x tinyscheduler

# Set up configuration
cp .env.tinyscheduler.example .env
nano .env  # Edit with your settings
```

### Basic Usage

```bash
# Validate configuration
./tinyscheduler validate-config --fix

# Test with dry run (no changes)
./tinyscheduler run --once --dry-run

# Run single reconciliation pass
./tinyscheduler run --once

# Run in continuous daemon mode
./tinyscheduler run --daemon
```

### Configuration Example

```bash
# Base path
TINYSCHEDULER_BASE_PATH=/home/user/workspace/calypso

# Agent control file (defines agent pools)
TINYSCHEDULER_AGENT_CONTROL_FILE=docs/technical/agent-control.json

# Agent limits
TINYSCHEDULER_AGENT_LIMITS='{"dispatcher": 1, "architect": 2, "vaela": 3}'

# Goose binary location
TINYSCHEDULER_GOOSE_BIN=/usr/local/bin/goose

# Tinytask MCP endpoint
TINYSCHEDULER_MCP_ENDPOINT=http://localhost:3000

# Timing (seconds)
TINYSCHEDULER_LOOP_INTERVAL_SEC=60
TINYSCHEDULER_HEARTBEAT_SEC=15
TINYSCHEDULER_MAX_RUNTIME_SEC=3600
```

### Agent Control File

Define agent pools in [`agent-control.json`](docs/technical/agent-control.json):

```json
[
  {"agentName": "vaela", "agentType": "dev"},
  {"agentName": "damien", "agentType": "dev"},
  {"agentName": "oscar", "agentType": "qa"},
  {"agentName": "sage", "agentType": "product"}
]
```

Tasks in the `dev` queue are automatically distributed between `vaela` and `damien` based on available capacity.

## 🏗 Architecture

### Reconciliation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    RECONCILIATION LOOP                       │
│                   (Every ~60 seconds)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  1. SCAN EXISTING LEASES                                    │
│     └─ Read all files from state/running/                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. RECLAIM STALE LEASES                                    │
│     ├─ Check PID liveness (is process still running?)      │
│     ├─ Check heartbeat age (last update < threshold?)      │
│     └─ Delete lease file if stale, update tinytask         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. QUERY TASKS FROM TINYTASK                               │
│     ├─ By Queue: Get unassigned tasks per queue type       │
│     └─ By Agent: Get already-assigned tasks per agent      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. CALCULATE AVAILABLE CAPACITY                            │
│     └─ For each agent: limit - current_leases = slots      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  5. ASSIGN & SPAWN AGENTS                                   │
│     ├─ Distribute unassigned tasks to agents with capacity │
│     ├─ Update task assignments in tinytask                 │
│     └─ Spawn Goose wrapper for each new task               │
└─────────────────────────────────────────────────────────────┘
```

### Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Scheduler** | Main reconciliation engine | [`src/scheduler/scheduler.py`](src/scheduler/scheduler.py) |
| **Lease Store** | CRUD operations on lease files | [`src/scheduler/lease.py`](src/scheduler/lease.py) |
| **Tinytask Client** | HTTP client for MCP API | [`src/scheduler/tinytask_client.py`](src/scheduler/tinytask_client.py) |
| **Agent Registry** | Agent pool configuration | [`src/scheduler/agent_registry.py`](src/scheduler/agent_registry.py) |
| **Config Manager** | Environment & CLI settings | [`src/scheduler/config.py`](src/scheduler/config.py) |
| **CLI** | Command-line interface | [`src/scheduler/cli.py`](src/scheduler/cli.py) |

### File-Based State

```
state/
├── running/               # Active task leases (source of truth)
│   ├── task_1001.json    # Each file represents one running task
│   ├── task_1002.json
│   └── task_1003.json
├── logs/                 # Scheduler logs (rotated daily)
│   └── scheduler_20260120.log
└── tinyscheduler.lock    # Prevents concurrent scheduler runs
```

**Lease File Example** (`state/running/task_1001.json`):
```json
{
  "task_id": 1001,
  "agent_name": "vaela",
  "pid": 42318,
  "start_time": "2026-01-20T04:00:00Z",
  "last_heartbeat": "2026-01-20T04:05:30Z",
  "max_runtime_sec": 3600
}
```

## 🔒 Security

TinyScheduler implements comprehensive security controls to prevent common vulnerabilities. **All critical security issues identified in pre-release audit have been resolved.**

### Security Features

- ✅ **Input Validation** - All user inputs validated against command injection and path traversal
- ✅ **Path Sanitization** - Recipe and lease paths confined to designated directories
- ✅ **File Permissions** - Lease files created with restrictive permissions (0600)
- ✅ **Size Limits** - JSON file size limits prevent DoS attacks
- ✅ **Atomic Operations** - Crash-safe file operations using temp + rename pattern
- ✅ **PID Validation** - Process liveness checks prevent lease hijacking

### Security Testing

```bash
# Run security test suite
python -m pytest tests/scheduler/test_security_validators.py -v

# Static security analysis
pip install bandit
bandit -r src/scheduler/ -ll
```

### Security Documentation

- **[Security Guide](docs/SECURITY.md)** - Comprehensive security documentation
- **[Security Audit Report](docs/audit-reports/SECURITY_AUDIT_REPORT-20260119.md)** - Pre-release security audit
- **Vulnerability Reporting** - See [SECURITY.md](docs/SECURITY.md) for incident response process

### Production Security Checklist

Before deploying to production:

- [ ] Use HTTPS for MCP endpoint (not HTTP)
- [ ] Set restrictive permissions on state directories (`chmod 700 state/`)
- [ ] Validate `agent-control.json` using `./tinyscheduler validate-config`
- [ ] Review environment variables for sensitive data
- [ ] Run security test suite
- [ ] Enable structured logging with field sanitization

See the [Security Guide](docs/SECURITY.md) for complete deployment security recommendations.

## 📚 Documentation

- **[Full Documentation](docs/tinyscheduler-README.md)** - Complete guide with all configuration options
- **[Operations Guide](docs/technical/tinyscheduler-operations.md)** - Deployment, monitoring, troubleshooting
- **[Migration Guide](docs/technical/tinyscheduler-migration-guide.md)** - Upgrading from legacy mode
- **[Queue Integration](docs/technical/tinyscheduler-queue-integration.md)** - How queue-based assignment works
- **[Agent Control Examples](examples/agent-control-examples/)** - Configuration templates for different team sizes

## 🎮 Usage Examples

### Show Current Configuration

```bash
# Human-readable output
./tinyscheduler config --show

# JSON format (machine-readable)
./tinyscheduler config --show --json
```

### Deployment Options

#### Option 1: Cron (Recommended for Simple Setups)

```bash
# Add to crontab (runs every minute)
* * * * * cd /path/to/tinyscheduler && ./tinyscheduler run --once
```

#### Option 2: Systemd Daemon (Continuous Monitoring)

```bash
sudo cp docs/deployment/tinyscheduler.service /etc/systemd/system/
sudo systemctl enable tinyscheduler
sudo systemctl start tinyscheduler
sudo systemctl status tinyscheduler
```

#### Option 3: Systemd Timer (Cron Alternative)

```bash
sudo cp docs/deployment/tinyscheduler.timer /etc/systemd/system/
sudo cp docs/deployment/tinyscheduler-oneshot.service /etc/systemd/system/
sudo systemctl enable tinyscheduler.timer
sudo systemctl start tinyscheduler.timer
```

### Monitoring

```bash
# View scheduler logs
tail -f state/logs/scheduler_$(date +%Y%m%d).log

# List active leases
ls -lh state/running/

# View specific lease
cat state/running/task_1001.json | jq .

# Check systemd status
sudo journalctl -u tinyscheduler -f
```

### CLI Reference

```bash
# Configuration commands
./tinyscheduler config --show [--json]
./tinyscheduler validate-config [--fix]

# Run commands
./tinyscheduler run --once              # Single pass
./tinyscheduler run --daemon            # Continuous mode
./tinyscheduler run --once --dry-run    # Test without changes

# Override settings
./tinyscheduler run --once \
  --agent-limit vaela=3 \
  --agent-limit damien=2 \
  --mcp-endpoint http://localhost:8080 \
  --loop-interval 30 \
  --log-level DEBUG
```

## 🔧 Development

### Running Tests

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
python -m pytest tests/scheduler/

# Run specific test file
python -m pytest tests/scheduler/test_scheduler_queue.py

# Run with coverage
python -m pytest --cov=src/scheduler tests/scheduler/
```

### Project Structure

```
tinyscheduler/
├── src/scheduler/          # Core scheduler implementation
│   ├── scheduler.py       # Main reconciliation loop
│   ├── lease.py           # Lease file management
│   ├── tinytask_client.py # Tinytask MCP client
│   ├── agent_registry.py  # Agent pool configuration
│   ├── config.py          # Configuration management
│   ├── cli.py             # CLI interface
│   └── validation.py      # Config validation
├── tests/scheduler/        # Test suite
├── docs/                   # Documentation
│   ├── technical/         # Technical specs & guides
│   ├── deployment/        # Deployment configs
│   └── product-stories/   # Feature stories
├── examples/               # Configuration examples
└── state/                  # Runtime state (gitignored)
```

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. **🐛 Report Issues** - Found a bug? [Open an issue](https://github.com/yourusername/tinyscheduler/issues)
2. **💡 Suggest Features** - Have an idea? Start a discussion
3. **📝 Improve Docs** - Documentation can always be better
4. **🔧 Submit PRs** - Code contributions are welcome!

### Contribution Guidelines

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`python -m pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Style

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use type hints where applicable
- Add docstrings to public functions
- Keep functions focused and testable
- Write descriptive commit messages

## 🛠 Troubleshooting

### Scheduler Won't Start

```bash
# Check for stale lock file
cat state/tinyscheduler.lock
ps aux | grep tinyscheduler

# Remove if process is dead
rm state/tinyscheduler.lock
```

### No Tasks Spawning

```bash
# Verify tinytask connectivity
curl $TINYSCHEDULER_MCP_ENDPOINT/health

# Check configuration
./tinyscheduler config --show

# Run dry-run to see what would happen
./tinyscheduler run --once --dry-run
```

### Stale Leases Accumulating

```bash
# Check for dead processes
for lease in state/running/task_*.json; do
  pid=$(jq -r .pid "$lease")
  if ! ps -p $pid > /dev/null; then
    echo "Dead: $lease (PID $pid)"
  fi
done

# Scheduler should auto-reclaim on next pass
./tinyscheduler run --once
```

See the [Operations Guide](docs/technical/tinyscheduler-operations.md) for comprehensive troubleshooting.

## 📜 Design Philosophy

TinyScheduler follows these core principles:

1. **File-Backed State** - Leases are the source of truth, not memory
2. **Reconciliation-Based** - Idempotent operations, safe to rerun
3. **Crash-Safe** - Atomic file operations (temp + rename)
4. **Observable** - Human-readable JSON, structured logging
5. **MCP-Friendly** - HTTP REST integration, no tight coupling
6. **Simple Deployment** - Works with cron, systemd, or as daemon
7. **Zero External Dependencies** - No Redis, no database, just files

**Think Kubernetes for agents**: Continuously reconcile desired state (tasks in queues) with actual state (running agents tracked via leases).

## 📊 Use Cases

- **🤖 AI Agent Orchestration** - Coordinate multiple Goose agents across tasks
- **🔄 Task Queue Processing** - Distribute work from tinytask queues
- **⚖️ Load Balancing** - Balance workload across agent pools
- **🏢 Team Organization** - Separate dev, qa, product agent pools
- **🔁 Fault Tolerance** - Automatic recovery from agent failures
- **📈 Horizontal Scaling** - Add agents dynamically to pools

## 🗺 Roadmap

- [ ] Prometheus metrics endpoint
- [ ] Web UI for lease monitoring
- [ ] Agent health checks beyond PID
- [ ] Priority queue support
- [ ] Task dependency graphs
- [ ] Webhook notifications
- [ ] Multi-scheduler leader election

## 📄 License

TinyScheduler is released under the [MIT License](LICENSE).

Copyright (c) 2026 Eric Oliver

## 🙏 Acknowledgments

- **[Goose](https://github.com/square/goose)** - The AI agent framework
- **[Tinytask](https://github.com/block/tinytask)** - Task queue MCP server
- **Kubernetes** - Inspiration for the reconciliation pattern

## 💬 Community & Support

- 📚 [Documentation](docs/tinyscheduler-README.md)
- 🐛 [Issue Tracker](https://github.com/yourusername/tinyscheduler/issues)
- 💬 [Discussions](https://github.com/yourusername/tinyscheduler/discussions)

---

<div align="center">

**Built with ❤️ for the open source community**

If TinyScheduler helps your project, please consider giving it a ⭐️!

</div>

# Agent Control File Examples

This directory contains example agent control files for different team configurations. These examples demonstrate best practices for configuring TinyScheduler's queue integration.

## Available Examples

### Small Team (`agent-control-small.json`)
**Use Case**: Small teams or proof-of-concept deployments

- 2 development agents (dev queue)
- 1 QA agent (qa queue)
- **Total**: 3 agents across 2 queues

**Best For**:
- Startups or small teams
- Testing queue integration for the first time
- Single-project deployments

---

### Medium Team (`agent-control-medium.json`)
**Use Case**: Growing teams with specialized roles

- 4 development agents (dev queue)
- 3 QA agents (qa queue)  
- 1 product agent (product queue)
- 1 documentation agent (docs queue)
- **Total**: 9 agents across 4 queues

**Best For**:
- Mid-sized development teams
- Teams with dedicated QA and product roles
- Multiple concurrent projects

---

### Multi-Queue (`agent-control-multi-queue.json`)
**Use Case**: Large teams with highly specialized queues

- 2 backend development agents (dev queue)
- 2 frontend agents (frontend queue)
- 3 QA agents (qa queue)
- 2 infrastructure agents (infra queue)
- 1 product agent (product queue)
- 2 documentation agents (docs queue)
- **Total**: 12 agents across 6 queues

**Best For**:
- Large engineering organizations
- Teams with distinct specializations
- Complex multi-component projects
- Organizations requiring separation between frontend, backend, infra, etc.

---

## Usage

1. **Copy** the appropriate example to your TinyScheduler installation
2. **Customize** agent names and types for your team
3. **Configure** the path in your environment:
   ```bash
   export TINYSCHEDULER_AGENT_CONTROL_FILE=/path/to/agent-control.json
   ```
4. **Set agent limits** in configuration to match your capacity needs
5. **Create recipes** for each agent (e.g., `vaela.yaml`, `oscar.yaml`)

## File Format

Each agent control file is a JSON array of agent objects:

```json
[
    {
        "agentName": "agent-name",
        "agentType": "queue-name",
        "comment": "Optional description (ignored by scheduler)"
    }
]
```

### Fields

- **agentName** (required): Unique identifier for the agent
- **agentType** (required): Queue/type this agent belongs to (dev, qa, product, etc.)
- **comment** (optional): Human-readable description (ignored by scheduler)

### Important Notes

1. **Agent names must be unique** across the entire file
2. **Agent types** define which queue the agent processes tasks from
3. **Multiple agents** can share the same type (creating an agent pool)
4. **Agent limits** must be configured separately in TinyScheduler config
5. **Recipe files** must exist for each agent in the recipes directory

## Validation

After creating your agent control file, validate it with:

```bash
python3 -c "
from pathlib import Path
from src.scheduler.agent_registry import AgentRegistry

registry = AgentRegistry(Path('your-agent-control.json'))
print(f'✓ Loaded {len(registry.agents)} agents')
print(f'✓ Types: {registry.get_all_types()}')
"
```

## See Also

- [TinyScheduler README](../../docs/tinyscheduler-README.md)
- [Migration Guide](../../docs/technical/tinyscheduler-migration-guide.md)
- [Operations Guide](../../docs/technical/tinyscheduler-operations.md)

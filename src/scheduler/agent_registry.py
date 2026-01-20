"""Agent registry for loading and managing agent configurations."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    
    agent_name: str
    agent_type: str
    # Future extensions:
    # max_concurrency: int = 1
    # enabled: bool = True
    # priority: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AgentConfig":
        """
        Create AgentConfig from dictionary.
        
        Args:
            data: Dictionary containing agent configuration
            
        Returns:
            AgentConfig instance
            
        Raises:
            KeyError: If required fields are missing
        """
        # Check for required fields
        if 'agentName' not in data:
            raise KeyError("Missing required field 'agentName' in agent configuration")
        if 'agentType' not in data:
            raise KeyError("Missing required field 'agentType' in agent configuration")
        
        # Log warnings for unexpected fields (forward compatibility)
        expected_fields = {'agentName', 'agentType'}
        unexpected_fields = set(data.keys()) - expected_fields
        if unexpected_fields:
            logger.warning(
                f"Agent '{data.get('agentName', 'unknown')}' has unexpected fields: "
                f"{', '.join(sorted(unexpected_fields))}"
            )
        
        return cls(
            agent_name=data['agentName'],
            agent_type=data['agentType']
        )


class AgentRegistry:
    """Registry of agents and their configurations."""
    
    def __init__(self, control_file_path: Path):
        """
        Initialize agent registry.
        
        Args:
            control_file_path: Path to agent control JSON file
            
        Raises:
            FileNotFoundError: If control file does not exist
            json.JSONDecodeError: If control file contains invalid JSON
            ValueError: If control file format is invalid
            KeyError: If required fields are missing from agent entries
        """
        self.control_file_path = control_file_path
        self.agents: List[AgentConfig] = []
        self._agents_by_type: Dict[str, List[str]] = {}
        self._agents_by_name: Dict[str, AgentConfig] = {}
        
        self._load()
    
    def _load(self):
        """
        Load agents from control file.
        
        Raises:
            FileNotFoundError: If control file does not exist
            json.JSONDecodeError: If control file contains invalid JSON
            ValueError: If control file format is invalid
            KeyError: If required fields are missing from agent entries
        """
        if not self.control_file_path.exists():
            raise FileNotFoundError(
                f"Agent control file not found: {self.control_file_path}"
            )
        
        try:
            with open(self.control_file_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in agent control file: {e.msg}",
                e.doc,
                e.pos
            )
        
        # Validate that data is a list
        if not isinstance(data, list):
            raise ValueError(
                f"Agent control file must contain a JSON array, got {type(data).__name__}"
            )
        
        # Parse agents
        self.agents = [AgentConfig.from_dict(item) for item in data]
        
        # Build indexes
        self._agents_by_type = {}
        self._agents_by_name = {}
        
        for agent in self.agents:
            # By type
            if agent.agent_type not in self._agents_by_type:
                self._agents_by_type[agent.agent_type] = []
            self._agents_by_type[agent.agent_type].append(agent.agent_name)
            
            # By name (handle duplicates by keeping the last one)
            if agent.agent_name in self._agents_by_name:
                logger.warning(
                    f"Duplicate agent name '{agent.agent_name}' found in control file. "
                    f"Using the last occurrence."
                )
            self._agents_by_name[agent.agent_name] = agent
    
    def get_agents_by_type(self, agent_type: str) -> List[str]:
        """
        Get list of agent names for a given type.
        
        Args:
            agent_type: The agent type (queue name) to query
            
        Returns:
            List of agent names for the given type, empty list if type not found
        """
        return self._agents_by_type.get(agent_type, [])
    
    def get_agent_type(self, agent_name: str) -> Optional[str]:
        """
        Get agent type for a given agent name.
        
        Args:
            agent_name: The agent name to query
            
        Returns:
            Agent type (queue name) if found, None otherwise
        """
        agent = self._agents_by_name.get(agent_name)
        return agent.agent_type if agent else None
    
    def get_all_types(self) -> List[str]:
        """
        Get list of all agent types (queues).
        
        Returns:
            List of all unique agent types
        """
        return list(self._agents_by_type.keys())
    
    def get_all_agent_names(self) -> List[str]:
        """
        Get list of all agent names.
        
        Returns:
            List of all agent names in the order they appear in the control file
        """
        return [agent.agent_name for agent in self.agents]
    
    def reload(self):
        """
        Reload agents from control file.
        
        This allows dynamic updates to the agent configuration without restarting
        the application.
        
        Raises:
            FileNotFoundError: If control file does not exist
            json.JSONDecodeError: If control file contains invalid JSON
            ValueError: If control file format is invalid
            KeyError: If required fields are missing from agent entries
        """
        self._load()

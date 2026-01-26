"""Configuration management for TinyScheduler."""

import json
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

try:
    from ..exceptions import ConfigurationError
except ImportError:
    from src.exceptions import ConfigurationError


@dataclass
class TinySchedulerConfig:
    """Configuration for TinyScheduler control plane."""
    
    # Base and derived paths
    base_path: Path
    running_dir: Path
    log_dir: Path
    recipes_dir: Path
    bin_dir: Path
    task_cache_dir: Path
    lock_file: Path
    agent_control_file: Path
    
    # Agent concurrency limits
    agent_limits: Dict[str, int]
    
    # External binaries and endpoints
    goose_bin: Path
    mcp_endpoint: str
    
    # Scheduler behavior
    loop_interval_sec: int = 60
    heartbeat_interval_sec: int = 15
    max_runtime_sec: int = 3600
    
    # Operational flags
    dry_run: bool = False
    log_level: str = "INFO"
    enabled: bool = False
    disable_blocking: bool = False
    
    # Runtime metadata
    hostname: str = field(default_factory=socket.gethostname)
    
    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "TinySchedulerConfig":
        """
        Load configuration from environment variables.
        
        Args:
            env_file: Path to .env file (optional)
            
        Returns:
            TinySchedulerConfig instance
            
        Raises:
            ConfigurationError: If required variables are missing or invalid
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        # Base path (defaults to workspace/calypso)
        base_path_str = os.getenv("TINYSCHEDULER_BASE_PATH", "/home/user/workspace/calypso")
        base_path = Path(base_path_str).resolve()
        
        # Derive directory paths relative to base
        running_dir_str = os.getenv("TINYSCHEDULER_RUNNING_DIR")
        if running_dir_str:
            running_dir = Path(running_dir_str)
            if not running_dir.is_absolute():
                running_dir = base_path / running_dir
        else:
            running_dir = base_path / "state" / "running"
        
        log_dir_str = os.getenv("TINYSCHEDULER_LOG_DIR")
        if log_dir_str:
            log_dir = Path(log_dir_str)
            if not log_dir.is_absolute():
                log_dir = base_path / log_dir
        else:
            log_dir = base_path / "state" / "logs"
        
        recipes_dir_str = os.getenv("TINYSCHEDULER_RECIPES_DIR")
        if recipes_dir_str:
            recipes_dir = Path(recipes_dir_str)
            if not recipes_dir.is_absolute():
                recipes_dir = base_path / recipes_dir
        else:
            recipes_dir = base_path / "recipes"
        
        bin_dir_str = os.getenv("TINYSCHEDULER_BIN_DIR")
        if bin_dir_str:
            bin_dir = Path(bin_dir_str)
            if not bin_dir.is_absolute():
                bin_dir = base_path / bin_dir
        else:
            bin_dir = base_path / "scripts"
        
        task_cache_dir_str = os.getenv("TINYSCHEDULER_TASK_CACHE_DIR")
        if task_cache_dir_str:
            task_cache_dir = Path(task_cache_dir_str)
            if not task_cache_dir.is_absolute():
                task_cache_dir = base_path / task_cache_dir
        else:
            task_cache_dir = base_path / "state" / "tasks"
        
        lock_file_str = os.getenv("TINYSCHEDULER_LOCK_FILE")
        if lock_file_str:
            lock_file = Path(lock_file_str)
            if not lock_file.is_absolute():
                lock_file = base_path / lock_file
        else:
            lock_file = base_path / "state" / "tinyscheduler.lock"
        
        # Agent control file
        agent_control_file_str = os.getenv("TINYSCHEDULER_AGENT_CONTROL_FILE")
        if agent_control_file_str:
            agent_control_file = Path(agent_control_file_str)
            if not agent_control_file.is_absolute():
                agent_control_file = base_path / agent_control_file
        else:
            agent_control_file = base_path / "docs" / "technical" / "agent-control.json"
        
        # Agent limits (JSON or simple format)
        agent_limits_str = os.getenv("TINYSCHEDULER_AGENT_LIMITS", '{"dispatcher": 1}')
        agent_limits = cls._parse_agent_limits(agent_limits_str)
        
        # Goose binary path
        goose_bin_str = os.getenv("TINYSCHEDULER_GOOSE_BIN", "/root/.local/bin/goose")
        goose_bin = Path(goose_bin_str)
        if not goose_bin.is_absolute():
            goose_bin = base_path / goose_bin
        
        # Tinytask MCP endpoint
        mcp_endpoint = os.getenv("TINYSCHEDULER_MCP_ENDPOINT", "http://localhost:3000")
        
        # Scheduler timing
        loop_interval = int(os.getenv("TINYSCHEDULER_LOOP_INTERVAL_SEC", "60"))
        heartbeat_interval = int(os.getenv("TINYSCHEDULER_HEARTBEAT_SEC", "15"))
        max_runtime = int(os.getenv("TINYSCHEDULER_MAX_RUNTIME_SEC", "3600"))
        
        # Operational settings
        log_level = os.getenv("TINYSCHEDULER_LOG_LEVEL", "INFO")
        dry_run = os.getenv("TINYSCHEDULER_DRY_RUN", "false").lower() in ("true", "1", "yes")
        enabled = os.getenv("TINYSCHEDULER_ENABLED", "false").lower() in ("true", "1", "yes")
        disable_blocking = os.getenv("TINYSCHEDULER_DISABLE_BLOCKING", "false").lower() in ("true", "1", "yes")
        
        return cls(
            base_path=base_path,
            running_dir=running_dir,
            log_dir=log_dir,
            recipes_dir=recipes_dir,
            bin_dir=bin_dir,
            task_cache_dir=task_cache_dir,
            lock_file=lock_file,
            agent_control_file=agent_control_file,
            agent_limits=agent_limits,
            goose_bin=goose_bin,
            mcp_endpoint=mcp_endpoint,
            loop_interval_sec=loop_interval,
            heartbeat_interval_sec=heartbeat_interval,
            max_runtime_sec=max_runtime,
            log_level=log_level,
            dry_run=dry_run,
            enabled=enabled,
            disable_blocking=disable_blocking,
        )
    
    @classmethod
    def from_cli(cls, args) -> "TinySchedulerConfig":
        """
        Load configuration from CLI arguments, with environment fallback.
        
        Args:
            args: Parsed argparse arguments
            
        Returns:
            TinySchedulerConfig instance
        """
        # Start with environment config
        config = cls.from_env(getattr(args, 'env_file', None))
        
        # Override with CLI arguments if provided
        if hasattr(args, 'base_path') and args.base_path:
            config.base_path = Path(args.base_path).resolve()
        
        if hasattr(args, 'running_dir') and args.running_dir:
            running_dir = Path(args.running_dir)
            config.running_dir = running_dir if running_dir.is_absolute() else config.base_path / running_dir
        
        if hasattr(args, 'log_dir') and args.log_dir:
            log_dir = Path(args.log_dir)
            config.log_dir = log_dir if log_dir.is_absolute() else config.base_path / log_dir
        
        if hasattr(args, 'recipes_dir') and args.recipes_dir:
            recipes_dir = Path(args.recipes_dir)
            config.recipes_dir = recipes_dir if recipes_dir.is_absolute() else config.base_path / recipes_dir
        
        if hasattr(args, 'goose_bin') and args.goose_bin:
            config.goose_bin = Path(args.goose_bin)
        
        if hasattr(args, 'mcp_endpoint') and args.mcp_endpoint:
            config.mcp_endpoint = args.mcp_endpoint
        
        if hasattr(args, 'agent_limit') and args.agent_limit:
            # CLI provides list of "agent=slots" strings
            for limit_spec in args.agent_limit:
                if '=' in limit_spec:
                    agent, slots_str = limit_spec.split('=', 1)
                    try:
                        config.agent_limits[agent.strip()] = int(slots_str.strip())
                    except ValueError:
                        raise ConfigurationError(f"Invalid agent limit specification: {limit_spec}")
        
        if hasattr(args, 'loop_interval') and args.loop_interval is not None:
            config.loop_interval_sec = args.loop_interval
        
        if hasattr(args, 'heartbeat_interval') and args.heartbeat_interval is not None:
            config.heartbeat_interval_sec = args.heartbeat_interval
        
        if hasattr(args, 'max_runtime') and args.max_runtime is not None:
            config.max_runtime_sec = args.max_runtime
        
        if hasattr(args, 'log_level') and args.log_level:
            config.log_level = args.log_level
        
        if hasattr(args, 'dry_run') and args.dry_run:
            config.dry_run = True
        
        if hasattr(args, 'enabled') and args.enabled is not None:
            config.enabled = args.enabled
        
        if hasattr(args, 'disable_blocking') and args.disable_blocking:
            config.disable_blocking = True
        
        return config
    
    @staticmethod
    def _parse_agent_limits(limits_str: str) -> Dict[str, int]:
        """
        Parse agent limits from string (JSON or simple format).
        
        Supports:
        - JSON: {"dispatcher": 1, "architect": 2}
        - Simple: dispatcher:1,architect:2
        
        Args:
            limits_str: Agent limits string
            
        Returns:
            Dictionary mapping agent names to slot counts
            
        Raises:
            ConfigurationError: If format is invalid
        """
        limits_str = limits_str.strip()
        
        # Try JSON first
        if limits_str.startswith('{'):
            try:
                limits = json.loads(limits_str)
                if not isinstance(limits, dict):
                    raise ConfigurationError("Agent limits JSON must be an object")
                # Validate values are integers
                for agent, slots in limits.items():
                    if not isinstance(slots, int) or slots < 0:
                        raise ConfigurationError(f"Invalid slot count for agent '{agent}': {slots}")
                return limits
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid JSON in agent limits: {e}")
        
        # Try simple format: agent1:slots1,agent2:slots2
        limits = {}
        if limits_str:
            for spec in limits_str.split(','):
                spec = spec.strip()
                if ':' not in spec:
                    raise ConfigurationError(f"Invalid agent limit format (expected 'agent:slots'): {spec}")
                agent, slots_str = spec.split(':', 1)
                agent = agent.strip()
                try:
                    slots = int(slots_str.strip())
                    if slots < 0:
                        raise ValueError("Negative slot count")
                    limits[agent] = slots
                except ValueError:
                    raise ConfigurationError(f"Invalid slot count for agent '{agent}': {slots_str}")
        
        return limits
    
    def validate(self) -> List[str]:
        """
        Validate configuration settings.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate base path exists
        if not self.base_path.exists():
            errors.append(f"Base path does not exist: {self.base_path}")
        elif not self.base_path.is_dir():
            errors.append(f"Base path is not a directory: {self.base_path}")
        
        # Validate recipes directory exists
        if not self.recipes_dir.exists():
            errors.append(f"Recipes directory does not exist: {self.recipes_dir}")
        elif not self.recipes_dir.is_dir():
            errors.append(f"Recipes path is not a directory: {self.recipes_dir}")
        
        # Validate goose binary exists and is executable
        if not self.goose_bin.exists():
            errors.append(f"Goose binary not found: {self.goose_bin}")
        elif not os.access(self.goose_bin, os.X_OK):
            errors.append(f"Goose binary is not executable: {self.goose_bin}")
        
        # Validate agent limits are non-empty
        if not self.agent_limits:
            errors.append("At least one agent limit must be configured")
        
        # Validate timing parameters
        if self.loop_interval_sec <= 0:
            errors.append(f"Loop interval must be positive: {self.loop_interval_sec}")
        
        if self.heartbeat_interval_sec <= 0:
            errors.append(f"Heartbeat interval must be positive: {self.heartbeat_interval_sec}")
        
        if self.max_runtime_sec <= 0:
            errors.append(f"Max runtime must be positive: {self.max_runtime_sec}")
        
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_levels:
            errors.append(f"Invalid log level: {self.log_level}. Must be one of: {', '.join(valid_levels)}")
        
        # Validate MCP endpoint format
        if not self.mcp_endpoint.startswith(('http://', 'https://', 'ws://', 'wss://')):
            errors.append(f"Invalid MCP endpoint (must start with http://, https://, ws://, or wss://): {self.mcp_endpoint}")
        
        return errors
    
    def ensure_directories(self) -> None:
        """
        Create required directories if they don't exist.
        
        Raises:
            ConfigurationError: If directories cannot be created
        """
        dirs_to_create = [
            self.running_dir,
            self.log_dir,
            self.task_cache_dir,
        ]
        
        for directory in dirs_to_create:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ConfigurationError(f"Failed to create directory {directory}: {e}")
        
        # Ensure lock file directory exists
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ConfigurationError(f"Failed to create lock file directory {self.lock_file.parent}: {e}")
    
    def to_dict(self) -> Dict:
        """
        Convert configuration to dictionary for serialization.
        
        Returns:
            Dictionary representation of configuration
        """
        return {
            "base_path": str(self.base_path),
            "running_dir": str(self.running_dir),
            "log_dir": str(self.log_dir),
            "recipes_dir": str(self.recipes_dir),
            "bin_dir": str(self.bin_dir),
            "task_cache_dir": str(self.task_cache_dir),
            "lock_file": str(self.lock_file),
            "agent_control_file": str(self.agent_control_file),
            "agent_limits": self.agent_limits,
            "goose_bin": str(self.goose_bin),
            "mcp_endpoint": self.mcp_endpoint,
            "loop_interval_sec": self.loop_interval_sec,
            "heartbeat_interval_sec": self.heartbeat_interval_sec,
            "max_runtime_sec": self.max_runtime_sec,
            "dry_run": self.dry_run,
            "log_level": self.log_level,
            "enabled": self.enabled,
            "disable_blocking": self.disable_blocking,
            "hostname": self.hostname,
        }
    
    def __str__(self) -> str:
        """String representation of configuration."""
        agent_limits_str = ", ".join(f"{agent}={slots}" for agent, slots in sorted(self.agent_limits.items()))
        return (
            f"TinyScheduler Configuration:\n"
            f"  Base Path: {self.base_path}\n"
            f"  Running Dir: {self.running_dir}\n"
            f"  Log Dir: {self.log_dir}\n"
            f"  Recipes Dir: {self.recipes_dir}\n"
            f"  Agent Control File: {self.agent_control_file}\n"
            f"  Goose Binary: {self.goose_bin}\n"
            f"  MCP Endpoint: {self.mcp_endpoint}\n"
            f"  Agent Limits: {agent_limits_str}\n"
            f"  Loop Interval: {self.loop_interval_sec}s\n"
            f"  Heartbeat Interval: {self.heartbeat_interval_sec}s\n"
            f"  Max Runtime: {self.max_runtime_sec}s\n"
            f"  Log Level: {self.log_level}\n"
            f"  Dry Run: {self.dry_run}\n"
            f"  Enabled: {self.enabled}\n"
            f"  Disable Blocking: {self.disable_blocking}\n"
            f"  Hostname: {self.hostname}"
        )

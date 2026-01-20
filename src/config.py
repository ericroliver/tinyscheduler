"""Configuration management for Calypso file processor."""

import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from dotenv import load_dotenv

from .exceptions import ConfigurationError


@dataclass
class Config:
    """Configuration for file processor."""
    
    # Input/Output directories
    inbound_dir: Path
    outbound_dir: Path
    logs_dir: Path
    failed_dir: Path
    
    # Processing options
    whisper_model: str = "base"
    whisper_timeout: int = 3600  # 1 hour default
    dry_run: bool = False
    verbose: bool = False
    
    # Logging options
    log_level: str = "INFO"
    log_file: Optional[Path] = None
    
    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """
        Load configuration from environment variables.
        
        Args:
            env_file: Path to .env file (optional)
            
        Returns:
            Config instance
            
        Raises:
            ConfigurationError: If required variables are missing
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        # Required directories
        inbound = os.getenv("CALYPSO_INBOUND_DIR")
        outbound = os.getenv("CALYPSO_OUTBOUND_DIR")
        logs = os.getenv("CALYPSO_LOGS_DIR")
        failed = os.getenv("CALYPSO_FAILED_DIR")
        
        if not all([inbound, outbound, logs, failed]):
            missing = []
            if not inbound:
                missing.append("CALYPSO_INBOUND_DIR")
            if not outbound:
                missing.append("CALYPSO_OUTBOUND_DIR")
            if not logs:
                missing.append("CALYPSO_LOGS_DIR")
            if not failed:
                missing.append("CALYPSO_FAILED_DIR")
            raise ConfigurationError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Optional settings
        whisper_model = os.getenv("CALYPSO_WHISPER_MODEL", "base")
        whisper_timeout = int(os.getenv("CALYPSO_WHISPER_TIMEOUT", "3600"))
        log_level = os.getenv("CALYPSO_LOG_LEVEL", "INFO")
        log_file = os.getenv("CALYPSO_LOG_FILE")
        
        return cls(
            inbound_dir=Path(inbound),
            outbound_dir=Path(outbound),
            logs_dir=Path(logs),
            failed_dir=Path(failed),
            whisper_model=whisper_model,
            whisper_timeout=whisper_timeout,
            log_level=log_level,
            log_file=Path(log_file) if log_file else None,
        )
    
    @classmethod
    def from_cli(cls, args) -> "Config":
        """
        Load configuration from CLI arguments, with environment fallback.
        
        Args:
            args: Parsed argparse arguments
            
        Returns:
            Config instance
        """
        # Start with environment config
        try:
            config = cls.from_env(getattr(args, 'env_file', None))
        except ConfigurationError:
            # If environment config fails, create from CLI args only
            config = cls(
                inbound_dir=Path(args.inbound) if hasattr(args, 'inbound') and args.inbound else Path("inbound"),
                outbound_dir=Path(args.outbound) if hasattr(args, 'outbound') and args.outbound else Path("processed"),
                logs_dir=Path(args.logs) if hasattr(args, 'logs') and args.logs else Path("logs"),
                failed_dir=Path(args.failed) if hasattr(args, 'failed') and args.failed else Path("failed"),
            )
        
        # Override with CLI arguments if provided
        if hasattr(args, 'inbound') and args.inbound:
            config.inbound_dir = Path(args.inbound)
        if hasattr(args, 'outbound') and args.outbound:
            config.outbound_dir = Path(args.outbound)
        if hasattr(args, 'logs') and args.logs:
            config.logs_dir = Path(args.logs)
        if hasattr(args, 'failed') and args.failed:
            config.failed_dir = Path(args.failed)
        if hasattr(args, 'whisper_model') and args.whisper_model:
            config.whisper_model = args.whisper_model
        if hasattr(args, 'whisper_timeout') and args.whisper_timeout:
            config.whisper_timeout = args.whisper_timeout
        if hasattr(args, 'dry_run') and args.dry_run:
            config.dry_run = args.dry_run
        if hasattr(args, 'verbose') and args.verbose:
            config.verbose = args.verbose
            config.log_level = "DEBUG"
        if hasattr(args, 'log_level') and args.log_level:
            config.log_level = args.log_level
        if hasattr(args, 'log_file') and args.log_file:
            config.log_file = Path(args.log_file)
        
        return config
    
    def validate(self) -> List[str]:
        """
        Validate configuration settings.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Validate inbound directory exists
        if not self.inbound_dir.exists():
            errors.append(f"Inbound directory does not exist: {self.inbound_dir}")
        elif not self.inbound_dir.is_dir():
            errors.append(f"Inbound path is not a directory: {self.inbound_dir}")
        
        # Validate whisper model
        valid_models = ["tiny", "base", "small", "medium", "large", "large-v1", "large-v2", "large-v3"]
        if self.whisper_model not in valid_models:
            errors.append(f"Invalid Whisper model: {self.whisper_model}. Must be one of: {', '.join(valid_models)}")
        
        # Validate timeout
        if self.whisper_timeout <= 0:
            errors.append(f"Whisper timeout must be positive: {self.whisper_timeout}")
        
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_levels:
            errors.append(f"Invalid log level: {self.log_level}. Must be one of: {', '.join(valid_levels)}")
        
        return errors
    
    def ensure_directories(self) -> None:
        """
        Create required directories if they don't exist.
        
        Raises:
            ConfigurationError: If directories cannot be created
        """
        dirs_to_create = [
            self.outbound_dir,
            self.logs_dir,
            self.failed_dir,
        ]
        
        for directory in dirs_to_create:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ConfigurationError(f"Failed to create directory {directory}: {e}")
        
        # Create log file directory if specified
        if self.log_file:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ConfigurationError(f"Failed to create log file directory {self.log_file.parent}: {e}")
    
    def __str__(self) -> str:
        """String representation of configuration."""
        return (
            f"Calypso Configuration:\n"
            f"  Inbound: {self.inbound_dir}\n"
            f"  Outbound: {self.outbound_dir}\n"
            f"  Logs: {self.logs_dir}\n"
            f"  Failed: {self.failed_dir}\n"
            f"  Whisper Model: {self.whisper_model}\n"
            f"  Whisper Timeout: {self.whisper_timeout}s\n"
            f"  Log Level: {self.log_level}\n"
            f"  Log File: {self.log_file or 'None'}\n"
            f"  Dry Run: {self.dry_run}\n"
            f"  Verbose: {self.verbose}"
        )
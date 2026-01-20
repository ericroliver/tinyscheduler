"""Validation utilities for TinyScheduler configuration."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    from .config import TinySchedulerConfig
except ImportError:
    from src.scheduler.config import TinySchedulerConfig


logger = logging.getLogger(__name__)


# Default agent control file content
DEFAULT_AGENT_CONTROL = [
    {
        "agentName": "dispatcher",
        "agentType": "orchestrator"
    },
    {
        "agentName": "architect",
        "agentType": "architect"
    }
]


@dataclass
class ValidationResult:
    """Result of a validation check."""
    success: bool
    message: str
    is_error: bool = True  # False for warnings/info messages
    
    def __str__(self) -> str:
        """String representation for display."""
        prefix = "✗" if self.is_error and not self.success else "✓"
        return f"{prefix} {self.message}"


def validate_agent_control_file(
    config: TinySchedulerConfig,
    fix: bool = False
) -> List[ValidationResult]:
    """
    Validate agent control file configuration.
    
    Checks:
    - File exists at config.agent_control_file
    - Valid JSON syntax
    - Array structure
    - Required fields (agentName, agentType) in each entry
    
    Args:
        config: TinyScheduler configuration
        fix: If True, attempt to create missing file with defaults
        
    Returns:
        List of ValidationResult objects describing validation status
    """
    results = []
    file_path = config.agent_control_file
    
    # Check if file exists
    if not file_path.exists():
        if fix:
            try:
                # Ensure directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create default file
                with open(file_path, 'w') as f:
                    json.dump(DEFAULT_AGENT_CONTROL, f, indent=2)
                
                logger.info(f"Created default agent control file: {file_path}")
                results.append(ValidationResult(
                    success=True,
                    message=f"Created default agent control file: {file_path}",
                    is_error=False
                ))
                
                # Continue validation with newly created file
            except Exception as e:
                results.append(ValidationResult(
                    success=False,
                    message=f"Failed to create agent control file: {e}",
                    is_error=True
                ))
                return results
        else:
            results.append(ValidationResult(
                success=False,
                message=f"Agent control file not found: {file_path}",
                is_error=True
            ))
            return results
    
    # Validate file is not a directory
    if not file_path.is_file():
        results.append(ValidationResult(
            success=False,
            message=f"Agent control file path is not a file: {file_path}",
            is_error=True
        ))
        return results
    
    # Validate JSON syntax
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        results.append(ValidationResult(
            success=False,
            message=f"Invalid JSON in agent control file: {e.msg} at line {e.lineno}, column {e.colno}",
            is_error=True
        ))
        return results
    except Exception as e:
        results.append(ValidationResult(
            success=False,
            message=f"Failed to read agent control file: {e}",
            is_error=True
        ))
        return results
    
    # Validate structure is array
    if not isinstance(data, list):
        results.append(ValidationResult(
            success=False,
            message=f"Agent control file must contain an array, got {type(data).__name__}",
            is_error=True
        ))
        return results
    
    # Validate array is not empty
    if len(data) == 0:
        results.append(ValidationResult(
            success=False,
            message="Agent control file contains an empty array (no agents defined)",
            is_error=True
        ))
        return results
    
    # Validate each entry
    agent_names_seen = set()
    for idx, entry in enumerate(data):
        # Validate entry is an object
        if not isinstance(entry, dict):
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx} is not an object, got {type(entry).__name__}",
                is_error=True
            ))
            continue
        
        # Validate required fields
        if 'agentName' not in entry:
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx} is missing required field 'agentName'",
                is_error=True
            ))
        elif not isinstance(entry['agentName'], str):
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx}: 'agentName' must be a string, got {type(entry['agentName']).__name__}",
                is_error=True
            ))
        elif not entry['agentName'].strip():
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx}: 'agentName' cannot be empty",
                is_error=True
            ))
        else:
            # Check for duplicate agent names
            agent_name = entry['agentName']
            if agent_name in agent_names_seen:
                results.append(ValidationResult(
                    success=True,
                    message=f"Warning: Duplicate agent name '{agent_name}' at entry {idx}",
                    is_error=False
                ))
            agent_names_seen.add(agent_name)
        
        if 'agentType' not in entry:
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx} is missing required field 'agentType'",
                is_error=True
            ))
        elif not isinstance(entry['agentType'], str):
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx}: 'agentType' must be a string, got {type(entry['agentType']).__name__}",
                is_error=True
            ))
        elif not entry['agentType'].strip():
            results.append(ValidationResult(
                success=False,
                message=f"Entry {idx}: 'agentType' cannot be empty",
                is_error=True
            ))
    
    # If no errors found, add success message
    if not any(r.is_error and not r.success for r in results):
        results.insert(0, ValidationResult(
            success=True,
            message=f"Agent control file is valid ({len(data)} agents configured)",
            is_error=False
        ))
    
    return results

"""
Input validation and sanitization for TinyScheduler.

This module provides security-critical validation functions to prevent:
- Command injection (CWE-78)
- Path traversal attacks (CWE-22)
- Improper input validation (CWE-20)

All functions raise ValueError with descriptive messages on validation failure.
"""

import re
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def validate_identifier(value: str, name: str, max_length: int = 64) -> str:
    """
    Validate alphanumeric identifiers with hyphens and underscores.
    
    Used for task_id, agent names, and other identifiers that will be:
    - Passed to subprocess commands
    - Used in file paths
    - Logged or displayed
    
    Args:
        value: The identifier to validate
        name: The parameter name (for error messages)
        max_length: Maximum allowed length (default: 64)
        
    Returns:
        The validated identifier (unchanged if valid)
        
    Raises:
        ValueError: If identifier contains invalid characters or is too long
        
    Examples:
        >>> validate_identifier("task_123", "task_id")
        'task_123'
        >>> validate_identifier("my-agent", "agent")
        'my-agent'
        >>> validate_identifier("../../etc/passwd", "task_id")
        ValueError: Invalid task_id: ../../etc/passwd
    """
    if not value:
        raise ValueError(f"Empty {name} not allowed")
    
    if len(value) > max_length:
        raise ValueError(f"{name} too long: {len(value)} > {max_length}")
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', value):
        raise ValueError(
            f"Invalid {name}: {value!r} - only alphanumeric, hyphens, and underscores allowed"
        )
    
    return value


def validate_task_id(task_id: str) -> str:
    """
    Validate task identifier for use in file paths and commands.
    
    Args:
        task_id: The task ID to validate
        
    Returns:
        The validated task_id
        
    Raises:
        ValueError: If task_id is invalid
    """
    return validate_identifier(task_id, "task_id")


def validate_agent_name(agent: str) -> str:
    """
    Validate agent name for use in file paths and commands.
    
    Args:
        agent: The agent name to validate
        
    Returns:
        The validated agent name
        
    Raises:
        ValueError: If agent name is invalid
    """
    return validate_identifier(agent, "agent")


def validate_recipe_path(recipe: str, recipes_dir: Path) -> Path:
    """
    Validate and resolve recipe path safely.
    
    Prevents path traversal attacks by:
    1. Rejecting absolute paths
    2. Rejecting parent directory references (..)
    3. Enforcing .yaml/.yml extension
    4. Ensuring resolved path is within recipes_dir
    
    Args:
        recipe: Recipe filename or relative path
        recipes_dir: Base directory for recipes
        
    Returns:
        Resolved Path object within recipes_dir
        
    Raises:
        ValueError: If path is invalid or outside recipes_dir
        
    Examples:
        >>> validate_recipe_path("dev.yaml", Path("/recipes"))
        Path('/recipes/dev.yaml')
        >>> validate_recipe_path("../../../etc/passwd", Path("/recipes"))
        ValueError: Invalid recipe path
    """
    # Convert to Path for analysis
    recipe_path_obj = Path(recipe)
    
    # Reject absolute paths
    if recipe_path_obj.is_absolute():
        raise ValueError(f"Absolute recipe paths not allowed: {recipe}")
    
    # Reject parent directory references
    if '..' in recipe_path_obj.parts:
        raise ValueError(f"Parent directory references not allowed in recipe: {recipe}")
    
    # Enforce file extension
    if not recipe.endswith(('.yaml', '.yml')):
        raise ValueError(f"Recipe must have .yaml or .yml extension: {recipe}")
    
    # Resolve full path
    try:
        recipe_full_path = (recipes_dir / recipe).resolve()
        recipes_dir_resolved = recipes_dir.resolve()
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Cannot resolve recipe path {recipe}: {e}")
    
    # Ensure path is within recipes_dir (prevent symlink attacks)
    try:
        recipe_full_path.relative_to(recipes_dir_resolved)
    except ValueError:
        raise ValueError(
            f"Recipe path outside recipes directory: {recipe} -> {recipe_full_path}"
        )
    
    return recipe_full_path


def validate_lease_path(task_id: str, lease_dir: Path) -> Path:
    """
    Validate and construct lease file path safely.
    
    Prevents path traversal by validating task_id and ensuring
    the resolved path is within lease_dir.
    
    Args:
        task_id: Task identifier
        lease_dir: Base directory for lease files
        
    Returns:
        Safe Path object for lease file
        
    Raises:
        ValueError: If task_id is invalid or path is unsafe
    """
    # Validate task_id first
    validated_task_id = validate_task_id(task_id)
    
    # Construct path
    lease_path = lease_dir / f"task_{validated_task_id}.json"
    
    # Ensure path is within lease_dir (prevent symlink/traversal)
    try:
        lease_path_resolved = lease_path.resolve()
        lease_dir_resolved = lease_dir.resolve()
        lease_path_resolved.relative_to(lease_dir_resolved)
    except ValueError:
        raise ValueError(f"Path traversal detected in task_id: {task_id}")
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Cannot resolve lease path for {task_id}: {e}")
    
    return lease_path


def validate_mcp_endpoint(endpoint: str, allow_localhost: bool = True) -> str:
    """
    Validate MCP endpoint URL.
    
    Args:
        endpoint: URL to validate
        allow_localhost: Whether to allow localhost/127.0.0.1 (default: True for dev)
        
    Returns:
        Validated endpoint URL
        
    Raises:
        ValueError: If URL is invalid or uses forbidden protocol
        
    Security Notes:
        - Only allows http/https protocols
        - Can optionally block localhost (for SSRF prevention in production)
    """
    try:
        parsed = urlparse(endpoint)
    except Exception as e:
        raise ValueError(f"Invalid MCP endpoint URL: {endpoint}: {e}")
    
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(
            f"Invalid MCP endpoint protocol: {parsed.scheme} - only http/https allowed"
        )
    
    # Optional: Block localhost in production to prevent SSRF
    if not allow_localhost and parsed.hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
        raise ValueError(f"Localhost MCP endpoints not allowed in production: {endpoint}")
    
    return endpoint


def validate_json_file_size(file_path: Path, max_size_mb: int = 10) -> None:
    """
    Validate JSON file size before parsing.
    
    Prevents denial-of-service attacks via large file uploads.
    
    Args:
        file_path: Path to JSON file
        max_size_mb: Maximum allowed size in megabytes
        
    Raises:
        ValueError: If file exceeds size limit
        FileNotFoundError: If file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    size_bytes = file_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb > max_size_mb:
        raise ValueError(
            f"JSON file too large: {file_path.name} is {size_mb:.2f}MB (max: {max_size_mb}MB)"
        )


def validate_hostname(hostname: str) -> str:
    """
    Validate hostname for use in logging and identification.
    
    Args:
        hostname: Hostname from socket.gethostname() or config
        
    Returns:
        Sanitized hostname
        
    Raises:
        ValueError: If hostname contains invalid characters
    """
    if not hostname:
        raise ValueError("Empty hostname not allowed")
    
    # Allow alphanumeric, dots, hyphens (RFC 1123)
    # Limit length to prevent log injection
    if len(hostname) > 253:
        raise ValueError(f"Hostname too long: {len(hostname)} > 253")
    
    if not re.match(r'^[a-zA-Z0-9.-]+$', hostname):
        raise ValueError(f"Invalid hostname: {hostname!r}")
    
    return hostname


def sanitize_path_for_log(path: Path, debug_mode: bool = False) -> str:
    """
    Sanitize file paths for logging to prevent information disclosure.
    
    Args:
        path: Path to sanitize
        debug_mode: If True, return full path; if False, return only filename
        
    Returns:
        Sanitized path string safe for logging
    """
    if debug_mode:
        return str(path)
    return path.name


# Export all validation functions
__all__ = [
    'validate_identifier',
    'validate_task_id',
    'validate_agent_name',
    'validate_recipe_path',
    'validate_lease_path',
    'validate_mcp_endpoint',
    'validate_json_file_size',
    'validate_hostname',
    'sanitize_path_for_log',
]

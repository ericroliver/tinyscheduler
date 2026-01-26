"""Command-line interface for TinyScheduler."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from .config import TinySchedulerConfig
    from .validation import validate_agent_control_file
    from ..exceptions import ConfigurationError
except ImportError:
    from src.scheduler.config import TinySchedulerConfig
    from src.scheduler.validation import validate_agent_control_file
    from src.exceptions import ConfigurationError


def create_parser() -> argparse.ArgumentParser:
    """
    Create argument parser for TinyScheduler CLI.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="tinyscheduler",
        description="TinyScheduler - Lightweight file-backed task scheduler for Goose agent coordination",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use custom .env file (--env-file must come before subcommand)
  tinyscheduler --env-file tinyscheduler.env validate-config
  tinyscheduler --env-file /path/to/custom.env run --once
  
  # Validate configuration
  tinyscheduler validate-config
  
  # Show current configuration
  tinyscheduler config --show
  
  # Run scheduler once (cron-friendly)
  tinyscheduler run --once
  
  # Run scheduler in daemon mode
  tinyscheduler run --daemon
  
  # Dry run to see what would be scheduled
  tinyscheduler run --once --dry-run
  
  # Override agent limits
  tinyscheduler run --once --agent-limit dispatcher=2 --agent-limit architect=1

Environment Variables:
  TINYSCHEDULER_BASE_PATH          Base directory (default: /home/user/workspace/calypso)
  TINYSCHEDULER_RUNNING_DIR        Lease directory (default: ${BASE}/state/running)
  TINYSCHEDULER_LOG_DIR            Log directory (default: ${BASE}/state/logs)
  TINYSCHEDULER_RECIPES_DIR        Recipes directory (default: ${BASE}/recipes)
  TINYSCHEDULER_GOOSE_BIN          Goose binary path (default: /root/.local/bin/goose)
  TINYSCHEDULER_MCP_ENDPOINT       Tinytask MCP endpoint (default: http://localhost:3000)
  TINYSCHEDULER_AGENT_LIMITS       Agent limits JSON or simple format
  TINYSCHEDULER_LOOP_INTERVAL_SEC  Daemon loop interval (default: 60)
  TINYSCHEDULER_HEARTBEAT_SEC      Heartbeat interval (default: 15)
  TINYSCHEDULER_MAX_RUNTIME_SEC    Max task runtime (default: 3600)
  TINYSCHEDULER_LOG_LEVEL          Log level (default: INFO)
  TINYSCHEDULER_DRY_RUN            Dry run mode (default: false)
  TINYSCHEDULER_DISABLE_BLOCKING   Disable task blocking (default: false)
  TINYSCHEDULER_ENABLED            Enable scheduler (default: false)
        """
    )
    
    # Global options
    parser.add_argument(
        '--env-file',
        type=str,
        help='Path to .env file (default: auto-discover)'
    )
    
    parser.add_argument(
        '--base-path',
        type=str,
        help='Base directory for all paths (default: from TINYSCHEDULER_BASE_PATH)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level (default: from TINYSCHEDULER_LOG_LEVEL or INFO)'
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Config command
    config_parser = subparsers.add_parser(
        'config',
        help='Show or validate configuration'
    )
    config_parser.add_argument(
        '--show',
        action='store_true',
        help='Display resolved configuration'
    )
    config_parser.add_argument(
        '--json',
        action='store_true',
        help='Output configuration as JSON'
    )
    
    # Validate config command
    validate_parser = subparsers.add_parser(
        'validate-config',
        help='Validate configuration without running scheduler'
    )
    validate_parser.add_argument(
        '--fix',
        action='store_true',
        help='Attempt to create missing directories'
    )
    
    # Run command
    run_parser = subparsers.add_parser(
        'run',
        help='Run the scheduler'
    )
    
    # Run mode
    run_mode = run_parser.add_mutually_exclusive_group()
    run_mode.add_argument(
        '--once',
        action='store_true',
        help='Run one reconciliation pass and exit (cron-friendly)'
    )
    run_mode.add_argument(
        '--daemon',
        action='store_true',
        help='Run continuously with interval sleeps'
    )
    
    # Path overrides
    run_parser.add_argument(
        '--running-dir',
        type=str,
        help='Lease directory (default: from TINYSCHEDULER_RUNNING_DIR)'
    )
    run_parser.add_argument(
        '--log-dir',
        type=str,
        help='Log directory (default: from TINYSCHEDULER_LOG_DIR)'
    )
    run_parser.add_argument(
        '--recipes-dir',
        type=str,
        help='Recipes directory (default: from TINYSCHEDULER_RECIPES_DIR)'
    )
    
    # External dependencies
    run_parser.add_argument(
        '--goose-bin',
        type=str,
        help='Path to Goose binary (default: from TINYSCHEDULER_GOOSE_BIN)'
    )
    run_parser.add_argument(
        '--mcp-endpoint',
        type=str,
        help='Tinytask MCP endpoint (default: from TINYSCHEDULER_MCP_ENDPOINT)'
    )
    
    # Agent limits
    run_parser.add_argument(
        '--agent-limit',
        action='append',
        metavar='AGENT=SLOTS',
        help='Set concurrency limit for an agent (repeatable, e.g., --agent-limit dispatcher=1)'
    )
    
    # Timing parameters
    run_parser.add_argument(
        '--loop-interval',
        type=int,
        metavar='SECONDS',
        help='Seconds between reconciliation passes in daemon mode (default: from TINYSCHEDULER_LOOP_INTERVAL_SEC)'
    )
    run_parser.add_argument(
        '--heartbeat-interval',
        type=int,
        metavar='SECONDS',
        help='Seconds between wrapper heartbeat updates (default: from TINYSCHEDULER_HEARTBEAT_SEC)'
    )
    run_parser.add_argument(
        '--max-runtime',
        type=int,
        metavar='SECONDS',
        help='Maximum task runtime before considering lease stale (default: from TINYSCHEDULER_MAX_RUNTIME_SEC)'
    )
    
    # Operational flags
    run_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show planned actions without making changes'
    )
    run_parser.add_argument(
        '--disable-blocking',
        action='store_true',
        help='Disable task blocking feature (rollback to legacy behavior)'
    )
    
    return parser


def validate_config_command(config: TinySchedulerConfig, fix: bool = False) -> int:
    """
    Execute validate-config command.
    
    Args:
        config: TinyScheduler configuration
        fix: Whether to attempt fixing issues by creating directories and creating agent control file
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("Validating TinyScheduler configuration...")
    print()
    
    has_errors = False
    
    # Validate standard configuration
    print("Configuration Settings:")
    errors = config.validate()
    
    if errors:
        print("  ❌ Configuration validation FAILED:")
        print()
        for error in errors:
            print(f"    • {error}")
        print()
        has_errors = True
        
        if fix:
            print("  Attempting to fix issues...")
            try:
                config.ensure_directories()
                print("  ✓ Created missing directories")
                print()
                
                # Re-validate
                errors = config.validate()
                if errors:
                    print("  Some issues remain:")
                    for error in errors:
                        print(f"    • {error}")
                    print()
                else:
                    print("  ✅ Configuration settings are now valid")
                    print()
                    has_errors = False
            except ConfigurationError as e:
                print(f"  ✗ Failed to fix issues: {e}")
                print()
        else:
            print("  Run with --fix to attempt automatic fixes")
            print()
    else:
        print("  ✅ Configuration settings are valid")
        print()
    
    # Validate agent control file
    print("Agent Control File:")
    agent_results = validate_agent_control_file(config, fix=fix)
    
    for result in agent_results:
        indent = "  "
        if result.is_error and not result.success:
            print(f"{indent}{result}")
            has_errors = True
        elif not result.is_error:
            # Info/warning messages
            print(f"{indent}{result}")
    
    print()
    
    # Summary
    if has_errors:
        print("❌ Validation FAILED")
        if not fix:
            print("Run with --fix to attempt automatic fixes")
        return 1
    else:
        print("✅ All validations passed")
        print()
        print(f"Base Path: {config.base_path}")
        print(f"Running Dir: {config.running_dir}")
        print(f"Log Dir: {config.log_dir}")
        print(f"Recipes Dir: {config.recipes_dir}")
        print(f"Agent Control File: {config.agent_control_file}")
        print(f"Goose Binary: {config.goose_bin}")
        print(f"MCP Endpoint: {config.mcp_endpoint}")
        print()
        agent_limits = ", ".join(f"{agent}={slots}" for agent, slots in sorted(config.agent_limits.items()))
        print(f"Agent Limits: {agent_limits}")
        return 0


def config_command(config: TinySchedulerConfig, show: bool = False, as_json: bool = False) -> int:
    """
    Execute config command.
    
    Args:
        config: TinyScheduler configuration
        show: Whether to display configuration
        as_json: Whether to output as JSON
        
    Returns:
        Exit code (0 for success)
    """
    if as_json:
        print(json.dumps(config.to_dict(), indent=2))
    else:
        print(config)
    
    return 0


def main(argv: Optional[list] = None) -> int:
    """
    Main entry point for TinyScheduler CLI.
    
    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])
        
    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)
    
    # Load configuration
    try:
        config = TinySchedulerConfig.from_cli(args)
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error loading configuration: {e}", file=sys.stderr)
        return 1
    
    # Execute command
    if args.command == 'config':
        return config_command(config, show=True, as_json=args.json)
    
    elif args.command == 'validate-config':
        return validate_config_command(config, fix=args.fix)
    
    elif args.command == 'run':
        # Import here to avoid circular dependencies
        try:
            from .scheduler import run_scheduler
        except ImportError:
            from src.scheduler.scheduler import run_scheduler
        
        # Determine run mode
        daemon_mode = args.daemon
        if not args.once and not args.daemon:
            # Default to once mode
            daemon_mode = False
        
        try:
            return run_scheduler(config, daemon=daemon_mode)
        except KeyboardInterrupt:
            print("\nScheduler interrupted by user", file=sys.stderr)
            return 130
        except Exception as e:
            print(f"Scheduler error: {e}", file=sys.stderr)
            return 1
    
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())

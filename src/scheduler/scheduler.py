"""Main scheduler module for TinyScheduler."""

import fcntl
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from .config import TinySchedulerConfig
    from .lease import Lease, LeaseStore
    from .tinytask_client import TinytaskClient, TinytaskClientError
    from .agent_registry import AgentRegistry
    from .validators import validate_task_id, validate_agent_name, validate_hostname, validate_recipe_path
except ImportError:
    from src.scheduler.config import TinySchedulerConfig
    from src.scheduler.lease import Lease, LeaseStore
    from src.scheduler.tinytask_client import TinytaskClient, TinytaskClientError
    from src.scheduler.agent_registry import AgentRegistry
    from src.scheduler.validators import validate_task_id, validate_agent_name, validate_hostname, validate_recipe_path


# Global flag for graceful shutdown
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global _shutdown_requested
    _shutdown_requested = True
    print("\nShutdown signal received, finishing current reconciliation pass...")


class LockFile:
    """Manages lock file to prevent overlapping scheduler runs."""
    
    def __init__(self, lock_path: Path):
        """
        Initialize lock file manager.
        
        Args:
            lock_path: Path to lock file
        """
        self.lock_path = lock_path
        self.lock_fd = None
    
    def acquire(self, blocking: bool = False) -> bool:
        """
        Acquire lock.
        
        Args:
            blocking: Whether to wait for lock
            
        Returns:
            True if lock acquired
        """
        # Ensure parent directory exists
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self.lock_fd = open(self.lock_path, 'w')
            
            # Try to acquire exclusive lock
            lock_flags = fcntl.LOCK_EX
            if not blocking:
                lock_flags |= fcntl.LOCK_NB
            
            fcntl.flock(self.lock_fd.fileno(), lock_flags)
            
            # Write PID to lock file
            self.lock_fd.write(f"{os.getpid()}\n")
            self.lock_fd.flush()
            
            return True
        
        except BlockingIOError:
            # Lock already held
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            return False
        
        except Exception as e:
            print(f"Error acquiring lock: {e}", file=sys.stderr)
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            return False
    
    def release(self):
        """Release lock."""
        if self.lock_fd:
            try:
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
            except Exception as e:
                print(f"Error releasing lock: {e}", file=sys.stderr)
            finally:
                self.lock_fd = None
        
        # Clean up lock file
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except Exception:
            pass  # Best effort cleanup - lock will be stale if file can't be removed
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError("Failed to acquire scheduler lock (another instance may be running)")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


class Scheduler:
    """TinyScheduler reconciliation engine."""
    
    def __init__(self, config: TinySchedulerConfig):
        """
        Initialize scheduler.
        
        Args:
            config: TinyScheduler configuration
        """
        self.config = config
        self.lease_store = LeaseStore(config.running_dir)
        self.tinytask_client = TinytaskClient(
            endpoint=config.mcp_endpoint,
            timeout=30,
            max_retries=3
        )
        self.logger = self._setup_logging()
        
        # Load agent registry
        try:
            self.agent_registry = AgentRegistry(config.agent_control_file)
            self.logger.info(f"Loaded agent registry from {config.agent_control_file}")
            self.logger.info(f"Registered agents: {', '.join(self.agent_registry.get_all_agent_names())}")
            self.logger.info(f"Agent types (queues): {', '.join(self.agent_registry.get_all_types())}")
        except FileNotFoundError:
            self.logger.warning(f"Agent control file not found: {config.agent_control_file}")
            self.logger.warning("Queue-based processing will be disabled. Using legacy agent_limits only.")
            self.agent_registry = None
        except Exception as e:
            self.logger.error(f"Failed to load agent registry: {e}")
            self.logger.warning("Queue-based processing will be disabled. Using legacy agent_limits only.")
            self.agent_registry = None
    
    def _setup_logging(self) -> logging.Logger:
        """
        Set up structured logging.
        
        Returns:
            Configured logger
        """
        logger = logging.getLogger('tinyscheduler')
        logger.setLevel(getattr(logging, self.config.log_level.upper()))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        
        # File handler if log directory exists
        if self.config.log_dir.exists():
            log_file = self.config.log_dir / f"scheduler_{datetime.now().strftime('%Y%m%d')}.log"
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                logger.warning(f"Failed to set up file logging: {e}")
        
        return logger
    
    def _calculate_available_slots(self, agent_name: str) -> int:
        """
        Calculate available task slots for an agent.
        
        Args:
            agent_name: Agent name to check
            
        Returns:
            Number of available slots (0 if agent at capacity or not configured)
        """
        # Get configured limit for agent
        limit = self.config.agent_limits.get(agent_name, 0)
        if limit <= 0:
            return 0
        
        # Get active lease count for agent
        active_counts = self.lease_store.count_active_by_agent()
        active = active_counts.get(agent_name, 0)
        
        # Calculate available slots
        available = max(0, limit - active)
        return available
    
    def _select_best_agent(self, available_by_agent: Dict[str, int]) -> Optional[str]:
        """
        Select agent with most available capacity.
        
        Args:
            available_by_agent: Dict mapping agent names to available slot counts
            
        Returns:
            Agent name with most available capacity, or None if no agents available
        """
        # Filter to agents with availability
        available_agents = {agent: slots for agent, slots in available_by_agent.items() if slots > 0}
        
        if not available_agents:
            return None
        
        # Return agent with most available slots (ties broken by name for determinism)
        best_agent = max(available_agents.items(), key=lambda x: (x[1], x[0]))
        return best_agent[0]
    
    def _process_unassigned_tasks(self, stats: Dict[str, int]) -> None:
        """
        Process unassigned tasks by queue, matching them to available agents.
        
        This method iterates through all queue types from the agent registry,
        queries unassigned tasks in each queue, and assigns them to agents
        with available capacity.
        
        Args:
            stats: Statistics dictionary to update with results
        """
        if not self.agent_registry:
            self.logger.debug("Agent registry not loaded, skipping unassigned task processing")
            return
        
        self.logger.info("Processing unassigned tasks by queue...")
        
        # Iterate through all queue types
        for queue_name in self.agent_registry.get_all_types():
            self.logger.debug(f"Processing queue '{queue_name}'...")
            
            # Get agent pool for this queue type
            agent_pool = self.agent_registry.get_agents_by_type(queue_name)
            
            if not agent_pool:
                self.logger.debug(f"No agents configured for queue '{queue_name}'")
                continue
            
            # Calculate available slots per agent
            available_by_agent = {}
            for agent in agent_pool:
                slots = self._calculate_available_slots(agent)
                available_by_agent[agent] = slots
                self.logger.debug(f"Agent '{agent}' has {slots} available slots")
            
            # Calculate total available slots
            total_slots = sum(available_by_agent.values())
            
            if total_slots <= 0:
                self.logger.debug(f"No available slots for queue '{queue_name}'")
                continue
            
            # Query unassigned tasks in this queue
            self.logger.info(f"Querying up to {total_slots} unassigned tasks from queue '{queue_name}'...")
            
            try:
                tasks = self.tinytask_client.get_unassigned_in_queue(queue_name, total_slots)
                self.logger.info(f"Found {len(tasks)} unassigned tasks in queue '{queue_name}'")
            except Exception as e:
                self.logger.error(f"Failed to query unassigned tasks for queue '{queue_name}': {e}")
                stats['errors'] += 1
                continue
            
            # Assign tasks to agents with most available capacity
            for task in tasks:
                # Select agent with most available capacity
                best_agent = self._select_best_agent(available_by_agent)
                
                if not best_agent:
                    self.logger.warning(f"No available agents for task {task.task_id} in queue '{queue_name}'")
                    break
                
                self.logger.info(f"Assigning task {task.task_id} to agent '{best_agent}'")
                
                # Assign task to agent
                if self.config.dry_run:
                    self.logger.info(f"[DRY RUN] Would assign task {task.task_id} to agent '{best_agent}'")
                    available_by_agent[best_agent] -= 1
                    stats['unassigned_matched'] += 1
                else:
                    try:
                        if self.tinytask_client.assign_task(task.task_id, best_agent):
                            # Spawn wrapper for assigned task
                            recipe = task.recipe or f"{best_agent}.yaml"
                            if self._spawn_wrapper(task.task_id, best_agent, recipe):
                                available_by_agent[best_agent] -= 1
                                stats['unassigned_matched'] += 1
                                stats['tasks_spawned'] += 1
                                self.logger.info(f"Successfully assigned and spawned task {task.task_id} for agent '{best_agent}'")
                            else:
                                stats['errors'] += 1
                                self.logger.error(f"Failed to spawn wrapper for task {task.task_id}")
                        else:
                            stats['errors'] += 1
                            self.logger.error(f"Failed to assign task {task.task_id} to agent '{best_agent}'")
                    except Exception as e:
                        stats['errors'] += 1
                        self.logger.error(f"Error processing task {task.task_id}: {e}")
    
    def _process_assigned_tasks(self, stats: Dict[str, int]) -> None:
        """
        Process already-assigned tasks, spawning wrappers for idle tasks.
        
        This method iterates through all agents from the registry and spawns
        wrappers for idle tasks that are already assigned to each agent,
        up to the agent's available capacity.
        
        Args:
            stats: Statistics dictionary to update with results
        """
        if not self.agent_registry:
            self.logger.debug("Agent registry not loaded, skipping assigned task processing")
            return
        
        self.logger.info("Processing already-assigned tasks...")
        
        # Iterate through all agents
        for agent_name in self.agent_registry.get_all_agent_names():
            # Calculate available slots for this agent
            available = self._calculate_available_slots(agent_name)
            
            if available <= 0:
                self.logger.debug(f"No available slots for agent '{agent_name}'")
                continue
            
            # Query idle tasks already assigned to this agent
            self.logger.debug(f"Querying up to {available} idle tasks for agent '{agent_name}'...")
            
            try:
                idle_tasks = self.tinytask_client.list_idle_tasks(agent_name, limit=available)
                self.logger.info(f"Found {len(idle_tasks)} idle tasks for agent '{agent_name}'")
            except Exception as e:
                self.logger.error(f"Failed to query idle tasks for agent '{agent_name}': {e}")
                stats['errors'] += 1
                continue
            
            # Spawn wrappers up to available slots
            for task in idle_tasks[:available]:
                recipe = task.recipe or f"{agent_name}.yaml"
                recipe_path = self.config.recipes_dir / recipe
                
                if not recipe_path.exists():
                    self.logger.warning(f"Recipe not found: {recipe_path}")
                    continue
                
                if self.config.dry_run:
                    self.logger.info(f"[DRY RUN] Would spawn task {task.task_id} for agent '{agent_name}' using recipe '{recipe}'")
                    stats['assigned_spawned'] += 1
                else:
                    try:
                        if self._spawn_wrapper(task.task_id, agent_name, recipe):
                            stats['assigned_spawned'] += 1
                            stats['tasks_spawned'] += 1
                            self.logger.info(f"Spawned task {task.task_id} for agent '{agent_name}'")
                        else:
                            stats['errors'] += 1
                    except Exception as e:
                        stats['errors'] += 1
                        self.logger.error(f"Error spawning task {task.task_id}: {e}")
    
    def reconcile(self) -> Dict[str, int]:
        """
        Perform one reconciliation pass.
        
        Returns:
            Dictionary with reconciliation statistics
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting reconciliation pass")
        self.logger.info(f"Hostname: {self.config.hostname}")
        self.logger.info(f"Dry run: {self.config.dry_run}")
        self.logger.info("=" * 60)
        
        stats = {
            'leases_scanned': 0,
            'leases_reclaimed': 0,
            'tasks_spawned': 0,
            'unassigned_matched': 0,
            'assigned_spawned': 0,
            'errors': 0
        }
        
        # Step 1: Scan and validate leases
        self.logger.info("Step 1: Scanning existing leases...")
        leases = self.lease_store.list_all()
        stats['leases_scanned'] = len(leases)
        self.logger.info(f"Found {len(leases)} active leases")
        
        # Step 2: Reclaim stale leases
        self.logger.info("Step 2: Checking for stale leases...")
        stale_leases = self.lease_store.find_stale_leases(
            max_runtime_sec=self.config.max_runtime_sec,
            check_pid=True
        )
        
        for lease, reason in stale_leases:
            self.logger.warning(f"Stale lease detected: task={lease.task_id}, agent={lease.agent}, reason={reason}")
            
            if not self.config.dry_run:
                # Attempt to requeue task
                try:
                    self.tinytask_client.requeue_task(lease.task_id, reason=reason)
                    self.logger.info(f"Requeued task {lease.task_id}")
                except TinytaskClientError as e:
                    self.logger.error(f"Failed to requeue task {lease.task_id}: {e}")
                    stats['errors'] += 1
                
                # Remove lease
                if self.lease_store.reclaim_lease(lease, reason):
                    stats['leases_reclaimed'] += 1
            else:
                self.logger.info(f"[DRY RUN] Would reclaim lease for task {lease.task_id}")
        
        # Step 3: Process unassigned tasks by queue (if agent registry available)
        if self.agent_registry:
            self.logger.info("Step 3: Processing unassigned tasks by queue...")
            self._process_unassigned_tasks(stats)
        
        # Step 4: Process already-assigned tasks (if agent registry available)
        if self.agent_registry:
            self.logger.info("Step 4: Processing already-assigned tasks...")
            self._process_assigned_tasks(stats)
        
        # Legacy Step: Process tasks using old agent_limits method (for backward compatibility)
        # This runs if agent registry is not available OR for agents not in the registry
        if not self.agent_registry:
            self.logger.info("Step 3: Querying idle tasks (legacy mode)...")
            
            # Calculate available slots per agent
            active_counts = self.lease_store.count_active_by_agent()
            available_slots = {}
            
            for agent, limit in self.config.agent_limits.items():
                active = active_counts.get(agent, 0)
                available = max(0, limit - active)
                available_slots[agent] = available
                self.logger.info(f"Agent '{agent}': {active}/{limit} slots used, {available} available")
            
            # Spawn new tasks
            self.logger.info("Step 4: Spawning new tasks (legacy mode)...")
            
            for agent, available in available_slots.items():
                if available <= 0:
                    self.logger.debug(f"No slots available for agent '{agent}'")
                    continue
                
                # Query idle tasks for this agent
                try:
                    idle_tasks = self.tinytask_client.list_idle_tasks(agent, limit=available)
                    self.logger.info(f"Found {len(idle_tasks)} idle tasks for agent '{agent}'")
                    
                    for task in idle_tasks[:available]:
                        # Determine recipe
                        recipe = task.recipe or f"{agent}.yaml"
                        recipe_path = self.config.recipes_dir / recipe
                        
                        if not recipe_path.exists():
                            self.logger.warning(f"Recipe not found: {recipe_path}")
                            continue
                        
                        # Spawn wrapper
                        if self.config.dry_run:
                            self.logger.info(f"[DRY RUN] Would spawn task {task.task_id} with agent '{agent}' using recipe '{recipe}'")
                        else:
                            success = self._spawn_wrapper(task.task_id, agent, recipe)
                            if success:
                                stats['tasks_spawned'] += 1
                                self.logger.info(f"Spawned task {task.task_id} for agent '{agent}'")
                            else:
                                stats['errors'] += 1
                
                except TinytaskClientError as e:
                    self.logger.error(f"Failed to query idle tasks for agent '{agent}': {e}")
                    stats['errors'] += 1
        
        # Summary
        self.logger.info("=" * 60)
        self.logger.info("Reconciliation pass complete")
        self.logger.info(f"Leases scanned: {stats['leases_scanned']}")
        self.logger.info(f"Leases reclaimed: {stats['leases_reclaimed']}")
        self.logger.info(f"Unassigned tasks matched: {stats['unassigned_matched']}")
        self.logger.info(f"Already-assigned tasks spawned: {stats['assigned_spawned']}")
        self.logger.info(f"Total tasks spawned: {stats['tasks_spawned']}")
        self.logger.info(f"Errors: {stats['errors']}")
        self.logger.info("=" * 60)
        
        return stats
    
    def _spawn_wrapper(self, task_id: str, agent: str, recipe: str) -> bool:
        """
        Spawn Goose wrapper for a task.
        
        Args:
            task_id: Task identifier
            agent: Agent name
            recipe: Recipe filename
            
        Returns:
            True if spawned successfully
        """
        # SECURITY: Validate all inputs before using in commands/paths (CWE-78, CWE-22)
        try:
            task_id = validate_task_id(task_id)
            agent = validate_agent_name(agent)
            # Recipe validation happens separately in calling code
        except ValueError as e:
            self.logger.error(f"Invalid input for task spawn: {e}")
            return False
        
        wrapper_script = self.config.bin_dir / "run_agent.py"
        
        if not wrapper_script.exists():
            self.logger.error(f"Wrapper script not found: {wrapper_script}")
            return False
        
        # Build command
        cmd = [
            sys.executable,
            str(wrapper_script),
            '--task-id', task_id,
            '--agent', agent,
            '--recipe', recipe,
            '--lease-dir', str(self.config.running_dir),
            '--goose-bin', str(self.config.goose_bin),
            '--mcp-endpoint', self.config.mcp_endpoint,
            '--heartbeat-interval', str(self.config.heartbeat_interval_sec),
            '--hostname', self.config.hostname,
        ]
        
        try:
            # Spawn as detached process
            process = subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.config.base_path
            )
            
            self.logger.debug(f"Spawned wrapper process {process.pid} for task {task_id}")
            
            # Create initial lease
            lease = Lease(
                task_id=task_id,
                agent=agent,
                pid=process.pid,
                recipe=recipe,
                started_at=datetime.now(timezone.utc),
                heartbeat=datetime.now(timezone.utc),
                host=self.config.hostname,
                state='running'
            )
            
            self.lease_store.create(lease)
            
            # Mark task as claimed in tinytask
            self.tinytask_client.claim_task(task_id, agent)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to spawn wrapper for task {task_id}: {e}")
            return False
    
    def run_once(self) -> int:
        """
        Run one reconciliation pass.
        
        Returns:
            Exit code (0 for success)
        """
        try:
            stats = self.reconcile()
            return 0 if stats['errors'] == 0 else 1
        except Exception as e:
            self.logger.error(f"Reconciliation failed: {e}", exc_info=True)
            return 1
    
    def run_daemon(self) -> int:
        """
        Run scheduler in daemon mode with interval sleeps.
        
        Returns:
            Exit code
        """
        global _shutdown_requested
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.logger.info(f"Starting scheduler daemon (interval: {self.config.loop_interval_sec}s)")
        
        while not _shutdown_requested:
            try:
                self.reconcile()
            except Exception as e:
                self.logger.error(f"Reconciliation error: {e}", exc_info=True)
            
            # Sleep with interruptible wait
            self.logger.info(f"Sleeping for {self.config.loop_interval_sec} seconds...")
            
            sleep_start = time.time()
            while time.time() - sleep_start < self.config.loop_interval_sec:
                if _shutdown_requested:
                    break
                time.sleep(1)
        
        self.logger.info("Scheduler daemon shutting down")
        return 0


def run_scheduler(config: TinySchedulerConfig, daemon: bool = False) -> int:
    """
    Run the scheduler with lock file protection.
    
    Args:
        config: TinyScheduler configuration
        daemon: Whether to run in daemon mode
        
    Returns:
        Exit code
    """
    # Validate and ensure directories
    errors = config.validate()
    if errors:
        print("Configuration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  • {error}", file=sys.stderr)
        return 1
    
    try:
        config.ensure_directories()
    except Exception as e:
        print(f"Failed to create directories: {e}", file=sys.stderr)
        return 1
    
    # Create scheduler
    scheduler = Scheduler(config)
    
    # Run with lock file protection
    lock = LockFile(config.lock_file)
    
    try:
        with lock:
            if daemon:
                return scheduler.run_daemon()
            else:
                return scheduler.run_once()
    
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Another scheduler instance may already be running.", file=sys.stderr)
        return 1
    
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1
    
    finally:
        scheduler.tinytask_client.close()

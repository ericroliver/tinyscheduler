"""Lease management for TinyScheduler."""

import json
import os
import signal
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ..exceptions import ConfigurationError
    from .validators import validate_lease_path, validate_json_file_size
except ImportError:
    from src.exceptions import ConfigurationError
    from src.scheduler.validators import validate_lease_path, validate_json_file_size


@dataclass
class Lease:
    """Represents a task execution lease."""
    
    task_id: str
    agent: str
    pid: int
    recipe: str
    started_at: datetime
    heartbeat: datetime
    host: str
    state: str = "running"
    metadata: Dict = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Lease":
        """
        Create Lease from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Lease instance
        """
        return cls(
            task_id=data['task_id'],
            agent=data['agent'],
            pid=data['pid'],
            recipe=data['recipe'],
            started_at=datetime.fromisoformat(data['started_at'].replace('Z', '+00:00')),
            heartbeat=datetime.fromisoformat(data['heartbeat'].replace('Z', '+00:00')),
            host=data['host'],
            state=data.get('state', 'running'),
            metadata=data.get('metadata', {}),
        )
    
    def to_dict(self) -> Dict:
        """
        Convert Lease to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            'task_id': self.task_id,
            'agent': self.agent,
            'pid': self.pid,
            'recipe': self.recipe,
            'started_at': self.started_at.isoformat().replace('+00:00', 'Z'),
            'heartbeat': self.heartbeat.isoformat().replace('+00:00', 'Z'),
            'host': self.host,
            'state': self.state,
            'metadata': self.metadata,
        }
    
    def is_stale(self, max_runtime_sec: int, heartbeat_threshold_multiplier: int = 3) -> bool:
        """
        Check if lease is stale based on heartbeat and runtime.
        
        Args:
            max_runtime_sec: Maximum allowed runtime in seconds
            heartbeat_threshold_multiplier: Multiplier for heartbeat interval to consider stale
            
        Returns:
            True if lease is stale
        """
        now = datetime.now(timezone.utc)
        
        # Check if max runtime exceeded
        runtime_sec = (now - self.started_at).total_seconds()
        if runtime_sec > max_runtime_sec:
            return True
        
        # Check if heartbeat is too old (using multiplier of heartbeat interval)
        # We don't have the heartbeat interval here, so we use a reasonable default
        # The caller should pass appropriate max_runtime_sec
        heartbeat_age_sec = (now - self.heartbeat).total_seconds()
        if heartbeat_age_sec > max_runtime_sec:
            return True
        
        return False
    
    def age_seconds(self) -> float:
        """
        Get age of lease in seconds since start.
        
        Returns:
            Age in seconds
        """
        now = datetime.now(timezone.utc)
        return (now - self.started_at).total_seconds()
    
    def heartbeat_age_seconds(self) -> float:
        """
        Get age of last heartbeat in seconds.
        
        Returns:
            Heartbeat age in seconds
        """
        now = datetime.now(timezone.utc)
        return (now - self.heartbeat).total_seconds()


class LeaseStore:
    """Manages lease files on disk."""
    
    def __init__(self, lease_dir: Path):
        """
        Initialize LeaseStore.
        
        Args:
            lease_dir: Directory for lease files
        """
        self.lease_dir = lease_dir
        self.lease_dir.mkdir(parents=True, exist_ok=True)
    
    def _lease_path(self, task_id: str) -> Path:
        """
        Get path to lease file for task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Path to lease file
        """
        return self.lease_dir / f"task_{task_id}.json"
    
    def create(self, lease: Lease) -> None:
        """
        Create a new lease file atomically.
        
        Args:
            lease: Lease to create
            
        Raises:
            FileExistsError: If lease already exists
            ConfigurationError: If write fails
        """
        lease_path = self._lease_path(lease.task_id)
        
        if lease_path.exists():
            raise FileExistsError(f"Lease already exists for task {lease.task_id}")
        
        # Write atomically using temp file + rename
        try:
            lease_data = json.dumps(lease.to_dict(), indent=2)
            
            # Create temp file in same directory to ensure same filesystem
            fd, temp_path = tempfile.mkstemp(
                dir=self.lease_dir,
                prefix=f"task_{lease.task_id}_",
                suffix=".tmp"
            )
            
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(lease_data)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic rename
                os.rename(temp_path, lease_path)
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            raise ConfigurationError(f"Failed to create lease for task {lease.task_id}: {e}")
    
    def read(self, task_id: str) -> Optional[Lease]:
        """
        Read lease for task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Lease if exists, None otherwise
        """
        lease_path = self._lease_path(task_id)
        
        if not lease_path.exists():
            return None
        
        try:
            with open(lease_path, 'r') as f:
                data = json.load(f)
            return Lease.from_dict(data)
        except Exception as e:
            # Log error but don't raise - corrupted leases should be recoverable
            print(f"Warning: Failed to read lease for task {task_id}: {e}")
            return None
    
    def update(self, lease: Lease) -> None:
        """
        Update an existing lease file atomically.
        
        Args:
            lease: Lease to update
            
        Raises:
            FileNotFoundError: If lease doesn't exist
            ConfigurationError: If write fails
        """
        lease_path = self._lease_path(lease.task_id)
        
        if not lease_path.exists():
            raise FileNotFoundError(f"Lease does not exist for task {lease.task_id}")
        
        # Write atomically using temp file + rename
        try:
            lease_data = json.dumps(lease.to_dict(), indent=2)
            
            # Create temp file in same directory
            fd, temp_path = tempfile.mkstemp(
                dir=self.lease_dir,
                prefix=f"task_{lease.task_id}_",
                suffix=".tmp"
            )
            
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(lease_data)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic rename
                os.rename(temp_path, lease_path)
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            raise ConfigurationError(f"Failed to update lease for task {lease.task_id}: {e}")
    
    def delete(self, task_id: str) -> bool:
        """
        Delete lease for task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if lease was deleted, False if it didn't exist
        """
        lease_path = self._lease_path(task_id)
        
        if not lease_path.exists():
            return False
        
        try:
            lease_path.unlink()
            return True
        except Exception as e:
            print(f"Warning: Failed to delete lease for task {task_id}: {e}")
            return False
    
    def list_all(self) -> List[Lease]:
        """
        List all leases.
        
        Returns:
            List of Lease objects
        """
        leases = []
        
        for lease_file in self.lease_dir.glob("task_*.json"):
            # Extract task ID from filename
            task_id = lease_file.stem.replace("task_", "")
            
            lease = self.read(task_id)
            if lease:
                leases.append(lease)
        
        return leases
    
    def list_by_agent(self, agent: str) -> List[Lease]:
        """
        List leases for specific agent.
        
        Args:
            agent: Agent name
            
        Returns:
            List of Lease objects for the agent
        """
        return [lease for lease in self.list_all() if lease.agent == agent]
    
    def update_heartbeat(self, task_id: str) -> bool:
        """
        Update heartbeat timestamp for a lease.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if updated, False if lease doesn't exist
        """
        lease = self.read(task_id)
        if not lease:
            return False
        
        lease.heartbeat = datetime.now(timezone.utc)
        
        try:
            self.update(lease)
            return True
        except Exception:
            return False
    
    @staticmethod
    def is_process_alive(pid: int) -> bool:
        """
        Check if process is alive.
        
        Args:
            pid: Process ID
            
        Returns:
            True if process is alive
        """
        if pid <= 0:
            return False
        
        try:
            # Send signal 0 to check if process exists
            # This doesn't actually send a signal, just checks permissions
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    
    def find_stale_leases(
        self,
        max_runtime_sec: int,
        check_pid: bool = True
    ) -> List[tuple[Lease, str]]:
        """
        Find stale leases that should be reclaimed.
        
        Args:
            max_runtime_sec: Maximum runtime in seconds
            check_pid: Whether to check if process is alive
            
        Returns:
            List of (Lease, reason) tuples for stale leases
        """
        stale_leases = []
        
        for lease in self.list_all():
            # Check if PID is dead
            if check_pid and not self.is_process_alive(lease.pid):
                stale_leases.append((lease, f"Process {lease.pid} is not alive"))
                continue
            
            # Check if lease is stale by time
            if lease.is_stale(max_runtime_sec):
                if lease.age_seconds() > max_runtime_sec:
                    stale_leases.append((
                        lease,
                        f"Runtime exceeded {max_runtime_sec}s (actual: {lease.age_seconds():.0f}s)"
                    ))
                else:
                    stale_leases.append((
                        lease,
                        f"Heartbeat stale (age: {lease.heartbeat_age_seconds():.0f}s)"
                    ))
                continue
        
        return stale_leases
    
    def reclaim_lease(self, lease: Lease, reason: str) -> bool:
        """
        Reclaim a stale lease by deleting it.
        
        Args:
            lease: Lease to reclaim
            reason: Reason for reclamation
            
        Returns:
            True if successfully reclaimed
        """
        print(f"Reclaiming lease for task {lease.task_id} (agent={lease.agent}): {reason}")
        return self.delete(lease.task_id)
    
    def count_active_by_agent(self) -> Dict[str, int]:
        """
        Count active leases by agent.
        
        Returns:
            Dictionary mapping agent names to active lease counts
        """
        counts: Dict[str, int] = {}
        
        for lease in self.list_all():
            if lease.state == "running":
                counts[lease.agent] = counts.get(lease.agent, 0) + 1
        
        return counts

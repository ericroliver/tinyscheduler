"""File management utilities for Calypso file processor."""

import shutil
from pathlib import Path
from typing import Optional

from .logger import get_logger


class FileManager:
    """Handles file operations with proper error handling and logging."""
    
    def __init__(self):
        """Initialize file manager."""
        self.logger = get_logger("FileManager")
    
    def move_file(self, source: Path, destination: Path, create_dirs: bool = True) -> bool:
        """
        Move a file from source to destination.
        
        Args:
            source: Source file path
            destination: Destination file path
            create_dirs: Whether to create destination directories
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not source.exists():
                self.logger.error(f"Source file does not exist: {source}")
                return False
            
            if create_dirs:
                destination.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.move(str(source), str(destination))
            self.logger.debug(f"Moved file: {source} -> {destination}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to move file {source} to {destination}: {e}")
            return False
    
    def copy_file(self, source: Path, destination: Path, create_dirs: bool = True) -> bool:
        """
        Copy a file from source to destination.
        
        Args:
            source: Source file path
            destination: Destination file path
            create_dirs: Whether to create destination directories
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not source.exists():
                self.logger.error(f"Source file does not exist: {source}")
                return False
            
            if create_dirs:
                destination.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(str(source), str(destination))
            self.logger.debug(f"Copied file: {source} -> {destination}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to copy file {source} to {destination}: {e}")
            return False
    
    def create_directory(self, directory: Path, parents: bool = True) -> bool:
        """
        Create a directory.
        
        Args:
            directory: Directory path to create
            parents: Whether to create parent directories
            
        Returns:
            True if successful, False otherwise
        """
        try:
            directory.mkdir(parents=parents, exist_ok=True)
            self.logger.debug(f"Created directory: {directory}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create directory {directory}: {e}")
            return False
    
    def ensure_directory(self, directory: Path) -> bool:
        """
        Ensure a directory exists, creating it if necessary.
        
        Args:
            directory: Directory path
            
        Returns:
            True if directory exists or was created, False otherwise
        """
        if directory.exists():
            if directory.is_dir():
                return True
            else:
                self.logger.error(f"Path exists but is not a directory: {directory}")
                return False
        
        return self.create_directory(directory, parents=True)
    
    def delete_file(self, file_path: Path) -> bool:
        """
        Delete a file.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not file_path.exists():
                self.logger.warning(f"File does not exist: {file_path}")
                return True
            
            file_path.unlink()
            self.logger.debug(f"Deleted file: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete file {file_path}: {e}")
            return False
    
    def get_file_size(self, file_path: Path) -> Optional[int]:
        """
        Get file size in bytes.
        
        Args:
            file_path: Path to file
            
        Returns:
            File size in bytes, or None if error
        """
        try:
            if not file_path.exists():
                return None
            return file_path.stat().st_size
        except Exception as e:
            self.logger.error(f"Failed to get file size for {file_path}: {e}")
            return None
    
    def move_to_failed(self, file_path: Path, failed_dir: Path, reason: str = "") -> bool:
        """
        Move a file to the failed directory with timestamp.
        
        Args:
            file_path: Path to file that failed processing
            failed_dir: Failed files directory
            reason: Reason for failure (optional)
            
        Returns:
            True if successful, False otherwise
        """
        from datetime import datetime
        
        try:
            if not file_path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False
            
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = file_path.stem
            suffix = file_path.suffix
            new_name = f"{stem}_{timestamp}{suffix}"
            
            destination = failed_dir / new_name
            
            # Ensure failed directory exists
            if not self.ensure_directory(failed_dir):
                return False
            
            # Move file
            success = self.move_file(file_path, destination, create_dirs=False)
            
            if success:
                self.logger.info(f"Moved failed file to: {destination}")
                if reason:
                    self.logger.info(f"Failure reason: {reason}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to move file to failed directory: {e}")
            return False
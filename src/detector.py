"""File type detection for Calypso file processor."""

from pathlib import Path
from typing import Optional

from .factory import ProcessorFactory
from .logger import get_logger


class FileTypeDetector:
    """Detects file types and determines if they are supported."""
    
    def __init__(self, factory: ProcessorFactory):
        """
        Initialize file type detector.
        
        Args:
            factory: ProcessorFactory instance
        """
        self.factory = factory
        self.logger = get_logger("FileTypeDetector")
    
    def detect_file_type(self, file_path: Path) -> str:
        """
        Detect the file type based on extension.
        
        Args:
            file_path: Path to file
            
        Returns:
            File extension (lowercase with dot)
        """
        extension = file_path.suffix.lower()
        return extension if extension else "unknown"
    
    def is_supported(self, file_path: Path) -> bool:
        """
        Check if a file type is supported.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if supported, False otherwise
        """
        extension = self.detect_file_type(file_path)
        return self.factory.is_supported(extension)
    
    def get_processor_type(self, file_path: Path) -> Optional[str]:
        """
        Get the processor type name for a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Processor type name, or None if not supported
        """
        processor = self.factory.get_processor_for_file(file_path)
        if processor:
            return processor.__class__.__name__
        return None
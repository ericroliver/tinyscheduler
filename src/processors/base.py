"""Base processor class for file processing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import time

from ..exceptions import ProcessingError
from ..logger import get_logger


@dataclass
class ProcessResult:
    """Result of file processing operation."""
    
    success: bool
    file_path: Path
    message: str
    processor_type: str
    processing_time: float
    output_files: List[Path] = None
    error: Optional[Exception] = None
    
    def __post_init__(self):
        """Initialize output_files if not provided."""
        if self.output_files is None:
            self.output_files = []


class FileProcessor(ABC):
    """Abstract base class for file processors."""
    
    def __init__(self):
        """Initialize processor."""
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    def process(self, file_path: Path, config) -> ProcessResult:
        """
        Process a file.
        
        Args:
            file_path: Path to file to process
            config: Configuration object
            
        Returns:
            ProcessResult with processing outcome
            
        Raises:
            ProcessingError: If processing fails
        """
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.
        
        Returns:
            List of extensions (e.g., ['.txt', '.log'])
        """
        pass
    
    def _validate_file(self, file_path: Path) -> None:
        """
        Validate that file exists and is readable.
        
        Args:
            file_path: Path to validate
            
        Raises:
            ProcessingError: If file is invalid
        """
        if not file_path.exists():
            raise ProcessingError(f"File does not exist: {file_path}")
        
        if not file_path.is_file():
            raise ProcessingError(f"Path is not a file: {file_path}")
        
        if not file_path.stat().st_size > 0:
            self.logger.warning(f"File is empty: {file_path}")
    
    def _create_result(
        self,
        success: bool,
        file_path: Path,
        message: str,
        start_time: float,
        output_files: List[Path] = None,
        error: Optional[Exception] = None
    ) -> ProcessResult:
        """
        Create a ProcessResult object.
        
        Args:
            success: Whether processing succeeded
            file_path: Path to processed file
            message: Result message
            start_time: Processing start time
            output_files: List of output files created
            error: Exception if processing failed
            
        Returns:
            ProcessResult object
        """
        processing_time = time.time() - start_time
        
        return ProcessResult(
            success=success,
            file_path=file_path,
            message=message,
            processor_type=self.__class__.__name__,
            processing_time=processing_time,
            output_files=output_files or [],
            error=error
        )
    
    def __str__(self) -> str:
        """String representation of processor."""
        extensions = ", ".join(self.get_supported_extensions())
        return f"{self.__class__.__name__}(extensions: {extensions})"
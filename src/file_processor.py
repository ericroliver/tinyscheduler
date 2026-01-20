"""Main file processor orchestrator."""

from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass

from .factory import ProcessorFactory
from .detector import FileTypeDetector
from .file_manager import FileManager
from .processors.text import TextProcessor
from .processors.audio import AudioProcessor
from .processors.spreadsheet import SpreadsheetProcessor
from .processors.document import DocumentProcessor
from .processors.base import ProcessResult
from .logger import get_logger


@dataclass
class ProcessingStats:
    """Statistics for file processing session."""
    
    total_files: int = 0
    successful: int = 0
    failed: int = 0
    unsupported: int = 0
    skipped: int = 0
    processing_time: float = 0.0
    
    def __str__(self) -> str:
        """String representation of statistics."""
        return (
            f"Processing Statistics:\n"
            f"  Total Files: {self.total_files}\n"
            f"  Successful: {self.successful}\n"
            f"  Failed: {self.failed}\n"
            f"  Unsupported: {self.unsupported}\n"
            f"  Skipped: {self.skipped}\n"
            f"  Total Time: {self.processing_time:.2f}s"
        )


class FileProcessorOrchestrator:
    """Orchestrates file processing workflow."""
    
    def __init__(self, config):
        """
        Initialize file processor orchestrator.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.logger = get_logger("FileProcessor")
        self.file_manager = FileManager()
        
        # Initialize factory and register processors
        self.factory = ProcessorFactory()
        self._register_processors()
        
        # Initialize detector
        self.detector = FileTypeDetector(self.factory)
        
        self.logger.info("File processor initialized")
        self.logger.debug(f"Registered processors: {self.factory.get_registered_processors()}")
        self.logger.debug(f"Supported extensions: {self.factory.get_all_supported_extensions()}")
    
    def _register_processors(self) -> None:
        """Register all available file processors."""
        self.factory.register(TextProcessor)
        self.factory.register(AudioProcessor)
        self.factory.register(SpreadsheetProcessor)
        self.factory.register(DocumentProcessor)
    
    def process_all(self) -> ProcessingStats:
        """
        Process all files in the inbound directory.
        
        Returns:
            ProcessingStats with processing results
        """
        import time
        start_time = time.time()
        
        stats = ProcessingStats()
        
        self.logger.info(f"Starting file processing from: {self.config.inbound_dir}")
        
        # Get all files from inbound directory
        files = self._get_inbound_files()
        stats.total_files = len(files)
        
        if not files:
            self.logger.info("No files found in inbound directory")
            return stats
        
        self.logger.info(f"Found {len(files)} files to process")
        
        # Process each file
        for file_path in files:
            try:
                result = self._process_single_file(file_path)
                
                if result.success:
                    stats.successful += 1
                    self.logger.info(f"✓ Successfully processed: {file_path.name}")
                else:
                    stats.failed += 1
                    self.logger.error(f"✗ Failed to process: {file_path.name} - {result.message}")
                    
                    # Move failed file
                    if file_path.exists():  # File may have been moved before failure
                        self.file_manager.move_to_failed(
                            file_path,
                            self.config.failed_dir,
                            reason=result.message
                        )
            
            except Exception as e:
                stats.failed += 1
                self.logger.error(f"✗ Unexpected error processing {file_path.name}: {e}", exc_info=True)
                
                # Move failed file
                if file_path.exists():
                    self.file_manager.move_to_failed(
                        file_path,
                        self.config.failed_dir,
                        reason=str(e)
                    )
        
        stats.processing_time = time.time() - start_time
        
        self.logger.info("=" * 60)
        self.logger.info(str(stats))
        self.logger.info("=" * 60)
        
        return stats
    
    def _get_inbound_files(self) -> List[Path]:
        """
        Get all files from inbound directory.
        
        Returns:
            List of file paths
        """
        if not self.config.inbound_dir.exists():
            self.logger.error(f"Inbound directory does not exist: {self.config.inbound_dir}")
            return []
        
        files = []
        for item in self.config.inbound_dir.iterdir():
            if item.is_file():
                files.append(item)
        
        return sorted(files)
    
    def _process_single_file(self, file_path: Path) -> ProcessResult:
        """
        Process a single file.
        
        Args:
            file_path: Path to file
            
        Returns:
            ProcessResult with processing outcome
        """
        self.logger.info(f"Processing: {file_path.name}")
        
        # Check if file type is supported
        if not self.detector.is_supported(file_path):
            file_type = self.detector.detect_file_type(file_path)
            self.logger.warning(f"Unsupported file type: {file_path.name} ({file_type})")
            
            # Move unsupported file to failed directory
            self.file_manager.move_to_failed(
                file_path,
                self.config.failed_dir,
                reason=f"Unsupported file type: {file_type}"
            )
            
            return ProcessResult(
                success=False,
                file_path=file_path,
                message=f"Unsupported file type: {file_type}",
                processor_type="None",
                processing_time=0.0
            )
        
        # Get appropriate processor
        processor = self.factory.get_processor_for_file(file_path)
        if not processor:
            self.logger.error(f"No processor found for: {file_path.name}")
            return ProcessResult(
                success=False,
                file_path=file_path,
                message="No processor found",
                processor_type="None",
                processing_time=0.0
            )
        
        self.logger.debug(f"Using processor: {processor.__class__.__name__}")
        
        # Process the file
        try:
            result = processor.process(file_path, self.config)
            return result
        except Exception as e:
            self.logger.error(f"Processor error for {file_path.name}: {e}", exc_info=True)
            return ProcessResult(
                success=False,
                file_path=file_path,
                message=f"Processor error: {str(e)}",
                processor_type=processor.__class__.__name__,
                processing_time=0.0,
                error=e
            )
    
    def process_file(self, file_path: Path) -> ProcessResult:
        """
        Process a specific file (for testing or manual processing).
        
        Args:
            file_path: Path to file to process
            
        Returns:
            ProcessResult with processing outcome
        """
        if not file_path.exists():
            self.logger.error(f"File does not exist: {file_path}")
            return ProcessResult(
                success=False,
                file_path=file_path,
                message="File does not exist",
                processor_type="None",
                processing_time=0.0
            )
        
        return self._process_single_file(file_path)
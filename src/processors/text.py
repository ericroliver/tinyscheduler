"""Text file processor."""

from pathlib import Path
from typing import List
import time

from .base import FileProcessor, ProcessResult
from ..file_manager import FileManager
from ..exceptions import ProcessingError


class TextProcessor(FileProcessor):
    """Processor for text-based files."""
    
    def __init__(self):
        """Initialize text processor."""
        super().__init__()
        self.file_manager = FileManager()
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.
        
        Returns:
            List of text file extensions
        """
        return [
            '.txt', '.log', '.html', '.md', '.json', 
            '.xml', '.csv', '.srt', '.vtt', '.tsv'
        ]
    
    def process(self, file_path: Path, config) -> ProcessResult:
        """
        Process a text file by moving it to the outbound directory.
        
        Args:
            file_path: Path to text file
            config: Configuration object
            
        Returns:
            ProcessResult with processing outcome
        """
        start_time = time.time()
        
        try:
            # Validate file
            self._validate_file(file_path)
            
            # Determine destination
            destination = config.outbound_dir / file_path.name
            
            self.logger.info(f"Processing text file: {file_path.name}")
            
            # Handle dry run
            if config.dry_run:
                self.logger.info(f"[DRY RUN] Would move {file_path} to {destination}")
                return self._create_result(
                    success=True,
                    file_path=file_path,
                    message=f"Dry run: Would move to {destination}",
                    start_time=start_time,
                    output_files=[destination]
                )
            
            # Move file to outbound
            success = self.file_manager.move_file(file_path, destination)
            
            if success:
                self.logger.info(f"Successfully processed text file: {file_path.name}")
                return self._create_result(
                    success=True,
                    file_path=file_path,
                    message=f"Moved to {destination}",
                    start_time=start_time,
                    output_files=[destination]
                )
            else:
                raise ProcessingError(f"Failed to move file to {destination}")
        
        except Exception as e:
            self.logger.error(f"Error processing text file {file_path}: {e}", exc_info=True)
            return self._create_result(
                success=False,
                file_path=file_path,
                message=f"Error: {str(e)}",
                start_time=start_time,
                error=e
            )
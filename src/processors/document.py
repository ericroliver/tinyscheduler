"""Document file processor."""

from pathlib import Path
from typing import List
import time

from .base import FileProcessor, ProcessResult
from ..file_manager import FileManager
from ..exceptions import ProcessingError


class DocumentProcessor(FileProcessor):
    """Processor for document files (PDF, Word, etc.)."""
    
    def __init__(self):
        """Initialize document processor."""
        super().__init__()
        self.file_manager = FileManager()
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.
        
        Returns:
            List of document file extensions
        """
        return ['.doc', '.docx', '.pdf', '.odt', '.rtf']
    
    def process(self, file_path: Path, config) -> ProcessResult:
        """
        Process a document file by moving it to the unprocessed directory.
        
        Documents and PDFs are not automatically processed, but are moved
        to a dedicated unprocessed folder for manual handling.
        
        Args:
            file_path: Path to document file
            config: Configuration object
            
        Returns:
            ProcessResult with processing outcome
        """
        start_time = time.time()
        
        try:
            # Validate file
            self._validate_file(file_path)
            
            self.logger.info(f"Processing document file: {file_path.name}")
            
            # Create unprocessed directory
            unprocessed_dir = config.logs_dir / "unprocessed"
            
            # Handle dry run
            if config.dry_run:
                destination = unprocessed_dir / file_path.name
                self.logger.info(f"[DRY RUN] Would move {file_path} to {destination}")
                return self._create_result(
                    success=True,
                    file_path=file_path,
                    message=f"Dry run: Would move to unprocessed folder",
                    start_time=start_time,
                    output_files=[destination]
                )
            
            # Ensure unprocessed directory exists
            if not self.file_manager.ensure_directory(unprocessed_dir):
                raise ProcessingError(f"Failed to create unprocessed directory: {unprocessed_dir}")
            
            # Move file to unprocessed folder
            destination = unprocessed_dir / file_path.name
            success = self.file_manager.move_file(file_path, destination, create_dirs=False)
            
            if success:
                self.logger.info(f"Moved document to unprocessed: {file_path.name}")
                return self._create_result(
                    success=True,
                    file_path=file_path,
                    message=f"Moved to unprocessed folder: {destination}",
                    start_time=start_time,
                    output_files=[destination]
                )
            else:
                raise ProcessingError(f"Failed to move file to {destination}")
        
        except Exception as e:
            self.logger.error(f"Error processing document {file_path}: {e}", exc_info=True)
            return self._create_result(
                success=False,
                file_path=file_path,
                message=f"Error: {str(e)}",
                start_time=start_time,
                error=e
            )
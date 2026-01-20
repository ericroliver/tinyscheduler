"""Spreadsheet file processor with CSV extraction."""

from pathlib import Path
from typing import List
import time
import tempfile

from .base import FileProcessor, ProcessResult
from ..file_manager import FileManager
from ..utils.excel_reader import ExcelReader
from ..exceptions import ProcessingError


class SpreadsheetProcessor(FileProcessor):
    """Processor for spreadsheet files (Excel)."""
    
    def __init__(self):
        """Initialize spreadsheet processor."""
        super().__init__()
        self.file_manager = FileManager()
        self.excel_reader = ExcelReader()
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.
        
        Returns:
            List of spreadsheet file extensions
        """
        return ['.xls', '.xlsx']
    
    def process(self, file_path: Path, config) -> ProcessResult:
        """
        Process a spreadsheet file by extracting all sheets to CSV.
        
        Processing steps:
        1. Validate spreadsheet file
        2. Get all sheet names
        3. Extract each sheet to CSV named {root_name}_{sheet_name}.csv
        4. Copy all CSVs to outbound
        5. Create logs/{root_name}/ directory
        6. Move CSVs to log directory
        7. Move original spreadsheet to log directory
        
        Args:
            file_path: Path to spreadsheet file
            config: Configuration object
            
        Returns:
            ProcessResult with processing outcome
        """
        start_time = time.time()
        output_files = []
        
        try:
            # Validate file
            self._validate_file(file_path)
            
            self.logger.info(f"Processing spreadsheet file: {file_path.name}")
            
            # Handle dry run
            if config.dry_run:
                sheet_names = self.excel_reader.get_sheet_names(file_path)
                if sheet_names:
                    self.logger.info(f"[DRY RUN] Would extract {len(sheet_names)} sheets: {', '.join(sheet_names)}")
                return self._create_result(
                    success=True,
                    file_path=file_path,
                    message="Dry run: Would extract sheets to CSV",
                    start_time=start_time
                )
            
            # Create temporary directory for CSV extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Extract all sheets to CSV
                root_name = file_path.stem
                csv_files = self.excel_reader.extract_all_sheets(
                    excel_file=file_path,
                    output_dir=temp_path,
                    base_name=root_name
                )
                
                if not csv_files:
                    raise ProcessingError("Failed to extract any sheets from spreadsheet")
                
                self.logger.info(f"Extracted {len(csv_files)} sheets to CSV")
                
                # Copy all CSVs to outbound
                for csv_file in csv_files:
                    csv_dest = config.outbound_dir / csv_file.name
                    if not self.file_manager.copy_file(csv_file, csv_dest):
                        self.logger.warning(f"Failed to copy CSV to outbound: {csv_file.name}")
                    else:
                        output_files.append(csv_dest)
                        self.logger.debug(f"Copied CSV to outbound: {csv_dest}")
                
                # Create logs directory for this file
                logs_subdir = config.logs_dir / root_name
                if not self.file_manager.ensure_directory(logs_subdir):
                    raise ProcessingError(f"Failed to create logs directory: {logs_subdir}")
                
                # Move all CSVs to logs directory
                for csv_file in csv_files:
                    if csv_file.exists():  # In case copy failed earlier
                        csv_log_dest = logs_subdir / csv_file.name
                        if self.file_manager.move_file(csv_file, csv_log_dest, create_dirs=False):
                            output_files.append(csv_log_dest)
                            self.logger.debug(f"Moved CSV to logs: {csv_log_dest}")
            
            # Move original spreadsheet to logs directory
            spreadsheet_dest = logs_subdir / file_path.name
            if not self.file_manager.move_file(file_path, spreadsheet_dest, create_dirs=False):
                raise ProcessingError(f"Failed to move spreadsheet to {spreadsheet_dest}")
            
            output_files.append(spreadsheet_dest)
            self.logger.info(f"Organized all files in: {logs_subdir}")
            
            return self._create_result(
                success=True,
                file_path=file_path,
                message=f"Extracted {len(csv_files)} sheets and organized in {logs_subdir}",
                start_time=start_time,
                output_files=output_files
            )
        
        except Exception as e:
            self.logger.error(f"Error processing spreadsheet {file_path}: {e}", exc_info=True)
            return self._create_result(
                success=False,
                file_path=file_path,
                message=f"Error: {str(e)}",
                start_time=start_time,
                error=e
            )
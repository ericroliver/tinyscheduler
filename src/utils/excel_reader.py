"""Excel file reader and CSV extractor."""

from pathlib import Path
from typing import List, Optional
import re

import pandas as pd

from ..logger import get_logger


class ExcelReader:
    """Reads Excel files and extracts sheets to CSV."""
    
    def __init__(self):
        """Initialize Excel reader."""
        self.logger = get_logger("ExcelReader")
    
    def get_sheet_names(self, excel_file: Path) -> Optional[List[str]]:
        """
        Get list of sheet names from Excel file.
        
        Args:
            excel_file: Path to Excel file
            
        Returns:
            List of sheet names, or None if error
        """
        try:
            # Read Excel file to get sheet names
            excel_data = pd.ExcelFile(excel_file)
            sheet_names = excel_data.sheet_names
            excel_data.close()
            
            self.logger.debug(f"Found {len(sheet_names)} sheets in {excel_file.name}")
            return sheet_names
        
        except Exception as e:
            self.logger.error(f"Failed to read sheet names from {excel_file}: {e}")
            return None
    
    def extract_sheet_to_csv(
        self,
        excel_file: Path,
        sheet_name: str,
        output_file: Path
    ) -> bool:
        """
        Extract a single sheet to CSV file.
        
        Args:
            excel_file: Path to Excel file
            sheet_name: Name of sheet to extract
            output_file: Path for output CSV file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Read the specific sheet
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to CSV
            df.to_csv(output_file, index=False)
            
            self.logger.debug(f"Extracted sheet '{sheet_name}' to {output_file}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to extract sheet '{sheet_name}' from {excel_file}: {e}")
            return False
    
    def extract_all_sheets(
        self,
        excel_file: Path,
        output_dir: Path,
        base_name: Optional[str] = None
    ) -> List[Path]:
        """
        Extract all sheets from Excel file to CSV files.
        
        CSV files are named: {base_name}_{sanitized_sheet_name}.csv
        
        Args:
            excel_file: Path to Excel file
            output_dir: Directory for output CSV files
            base_name: Base name for output files (default: excel file stem)
            
        Returns:
            List of created CSV file paths
        """
        if base_name is None:
            base_name = excel_file.stem
        
        # Get all sheet names
        sheet_names = self.get_sheet_names(excel_file)
        if not sheet_names:
            self.logger.error(f"No sheets found in {excel_file}")
            return []
        
        # Extract each sheet
        csv_files = []
        for sheet_name in sheet_names:
            sanitized_name = self._sanitize_filename(sheet_name)
            csv_filename = f"{base_name}_{sanitized_name}.csv"
            csv_path = output_dir / csv_filename
            
            if self.extract_sheet_to_csv(excel_file, sheet_name, csv_path):
                csv_files.append(csv_path)
                self.logger.info(f"Created CSV: {csv_filename}")
            else:
                self.logger.warning(f"Failed to extract sheet: {sheet_name}")
        
        return csv_files
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a string to be safe for use as a filename.
        
        Args:
            filename: String to sanitize
            
        Returns:
            Sanitized string
        """
        # Replace invalid characters with underscore
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        
        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip('. ')
        
        # Replace multiple underscores with single underscore
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Ensure it's not empty
        if not sanitized:
            sanitized = "sheet"
        
        return sanitized
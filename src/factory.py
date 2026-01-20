"""Factory for creating file processors."""

from pathlib import Path
from typing import Dict, List, Optional, Type

from .processors.base import FileProcessor
from .logger import get_logger


class ProcessorFactory:
    """Factory for creating file processors based on file extension."""
    
    def __init__(self):
        """Initialize processor factory."""
        self.logger = get_logger("ProcessorFactory")
        self._processors: Dict[str, Type[FileProcessor]] = {}
        self._extension_map: Dict[str, Type[FileProcessor]] = {}
    
    def register(self, processor_class: Type[FileProcessor]) -> None:
        """
        Register a processor class.
        
        Args:
            processor_class: Processor class to register
        """
        # Instantiate to get supported extensions
        instance = processor_class()
        extensions = instance.get_supported_extensions()
        
        # Register each extension
        for ext in extensions:
            ext_lower = ext.lower()
            if ext_lower in self._extension_map:
                self.logger.warning(
                    f"Extension {ext} already registered to {self._extension_map[ext_lower].__name__}, "
                    f"overwriting with {processor_class.__name__}"
                )
            self._extension_map[ext_lower] = processor_class
        
        self._processors[processor_class.__name__] = processor_class
        self.logger.debug(f"Registered processor: {processor_class.__name__} for {extensions}")
    
    def get_processor(self, file_extension: str) -> Optional[FileProcessor]:
        """
        Get a processor instance for the given file extension.
        
        Args:
            file_extension: File extension (with or without leading dot)
            
        Returns:
            Processor instance, or None if not supported
        """
        # Normalize extension
        if not file_extension.startswith('.'):
            file_extension = f'.{file_extension}'
        
        ext_lower = file_extension.lower()
        
        processor_class = self._extension_map.get(ext_lower)
        if processor_class:
            return processor_class()
        
        return None
    
    def get_processor_for_file(self, file_path: Path) -> Optional[FileProcessor]:
        """
        Get a processor instance for the given file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Processor instance, or None if not supported
        """
        extension = file_path.suffix
        return self.get_processor(extension)
    
    def is_supported(self, file_extension: str) -> bool:
        """
        Check if a file extension is supported.
        
        Args:
            file_extension: File extension (with or without leading dot)
            
        Returns:
            True if supported, False otherwise
        """
        if not file_extension.startswith('.'):
            file_extension = f'.{file_extension}'
        
        return file_extension.lower() in self._extension_map
    
    def get_all_supported_extensions(self) -> List[str]:
        """
        Get list of all supported file extensions.
        
        Returns:
            List of supported extensions
        """
        return sorted(self._extension_map.keys())
    
    def get_registered_processors(self) -> List[str]:
        """
        Get list of registered processor names.
        
        Returns:
            List of processor class names
        """
        return sorted(self._processors.keys())
    
    def __str__(self) -> str:
        """String representation of factory."""
        return f"ProcessorFactory(processors: {len(self._processors)}, extensions: {len(self._extension_map)})"
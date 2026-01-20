"""Audio file processor with Whisper transcription."""

from pathlib import Path
from typing import List
import time
import tempfile

from .base import FileProcessor, ProcessResult
from ..file_manager import FileManager
from ..utils.whisper_wrapper import WhisperWrapper
from ..exceptions import ProcessingError


class AudioProcessor(FileProcessor):
    """Processor for audio files using Whisper transcription."""
    
    def __init__(self):
        """Initialize audio processor."""
        super().__init__()
        self.file_manager = FileManager()
        self.whisper = WhisperWrapper()
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.
        
        Returns:
            List of audio file extensions
        """
        return ['.m4a', '.mp3', '.wav', '.flac']
    
    def process(self, file_path: Path, config) -> ProcessResult:
        """
        Process an audio file by transcribing it with Whisper.
        
        Processing steps:
        1. Validate audio file
        2. Run Whisper transcription in temp directory
        3. Copy .txt file to outbound
        4. Create logs/{root_name}/ directory
        5. Move all artifacts to log directory
        6. Move original audio to log directory
        
        Args:
            file_path: Path to audio file
            config: Configuration object
            
        Returns:
            ProcessResult with processing outcome
        """
        start_time = time.time()
        output_files = []
        
        try:
            # Validate file
            self._validate_file(file_path)
            
            # Check if Whisper is installed
            if not self.whisper.is_installed():
                raise ProcessingError(
                    "Whisper is not installed. Install with: pip install openai-whisper"
                )
            
            self.logger.info(f"Processing audio file: {file_path.name}")
            
            # Handle dry run
            if config.dry_run:
                self.logger.info(f"[DRY RUN] Would transcribe {file_path}")
                return self._create_result(
                    success=True,
                    file_path=file_path,
                    message="Dry run: Would transcribe with Whisper",
                    start_time=start_time
                )
            
            # Create temporary directory for Whisper output
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Run Whisper transcription
                self.logger.info(f"Transcribing with Whisper (model: {config.whisper_model})...")
                whisper_result = self.whisper.transcribe(
                    audio_file=file_path,
                    output_dir=temp_path,
                    model=config.whisper_model,
                    timeout=config.whisper_timeout
                )
                
                if not whisper_result.success:
                    raise ProcessingError(f"Whisper transcription failed: {whisper_result.message}")
                
                # Get the .txt artifact
                txt_artifact = whisper_result.get_artifact('txt')
                if not txt_artifact:
                    raise ProcessingError("Whisper did not generate .txt file")
                
                # Copy .txt file to outbound
                txt_dest = config.outbound_dir / txt_artifact.name
                if not self.file_manager.copy_file(txt_artifact, txt_dest):
                    raise ProcessingError(f"Failed to copy transcript to {txt_dest}")
                
                output_files.append(txt_dest)
                self.logger.info(f"Copied transcript to: {txt_dest}")
                
                # Create logs directory for this file
                root_name = file_path.stem
                logs_subdir = config.logs_dir / root_name
                if not self.file_manager.ensure_directory(logs_subdir):
                    raise ProcessingError(f"Failed to create logs directory: {logs_subdir}")
                
                # Move all artifacts to logs directory
                for ext, artifact_path in whisper_result.artifacts.items():
                    if artifact_path and artifact_path.exists():
                        dest = logs_subdir / artifact_path.name
                        if self.file_manager.move_file(artifact_path, dest, create_dirs=False):
                            output_files.append(dest)
                            self.logger.debug(f"Moved artifact to logs: {dest}")
                
                # Move original audio file to logs directory
                audio_dest = logs_subdir / file_path.name
                if not self.file_manager.move_file(file_path, audio_dest, create_dirs=False):
                    raise ProcessingError(f"Failed to move audio to {audio_dest}")
                
                output_files.append(audio_dest)
                self.logger.info(f"Organized all files in: {logs_subdir}")
            
            return self._create_result(
                success=True,
                file_path=file_path,
                message=f"Transcribed and organized in {logs_subdir}",
                start_time=start_time,
                output_files=output_files
            )
        
        except Exception as e:
            self.logger.error(f"Error processing audio file {file_path}: {e}", exc_info=True)
            return self._create_result(
                success=False,
                file_path=file_path,
                message=f"Error: {str(e)}",
                start_time=start_time,
                error=e
            )
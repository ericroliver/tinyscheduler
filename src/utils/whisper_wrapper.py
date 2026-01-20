"""Wrapper for OpenAI Whisper CLI tool."""

import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from ..exceptions import WhisperError
from ..logger import get_logger


@dataclass
class WhisperResult:
    """Result of Whisper transcription."""
    
    success: bool
    audio_file: Path
    output_dir: Path
    artifacts: Dict[str, Optional[Path]]
    message: str
    error: Optional[Exception] = None
    
    def get_artifact(self, ext: str) -> Optional[Path]:
        """
        Get artifact by extension.
        
        Args:
            ext: File extension (e.g., 'txt', 'json')
            
        Returns:
            Path to artifact, or None if not found
        """
        return self.artifacts.get(ext)


class WhisperWrapper:
    """Wrapper for Whisper CLI transcription tool."""
    
    ARTIFACT_EXTENSIONS = ['.txt', '.json', '.srt', '.vtt', '.tsv']
    
    def __init__(self):
        """Initialize Whisper wrapper."""
        self.logger = get_logger("WhisperWrapper")
    
    def is_installed(self) -> bool:
        """
        Check if Whisper is installed and available.
        
        Returns:
            True if Whisper is installed, False otherwise
        """
        return shutil.which("whisper") is not None
    
    def transcribe(
        self,
        audio_file: Path,
        output_dir: Path,
        model: str = "base",
        timeout: int = 3600
    ) -> WhisperResult:
        """
        Transcribe an audio file using Whisper.
        
        Args:
            audio_file: Path to audio file
            output_dir: Directory for output files
            model: Whisper model to use (tiny, base, small, medium, large)
            timeout: Timeout in seconds
            
        Returns:
            WhisperResult with transcription outcome
        """
        if not audio_file.exists():
            error = WhisperError(f"Audio file not found: {audio_file}")
            return WhisperResult(
                success=False,
                audio_file=audio_file,
                output_dir=output_dir,
                artifacts={},
                message=str(error),
                error=error
            )
        
        if not self.is_installed():
            error = WhisperError("Whisper is not installed. Install with: pip install openai-whisper")
            return WhisperResult(
                success=False,
                audio_file=audio_file,
                output_dir=output_dir,
                artifacts={},
                message=str(error),
                error=error
            )
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build Whisper command
        command = [
            "whisper",
            str(audio_file),
            "--model", model,
            "--output_dir", str(output_dir),
            "--output_format", "all",  # Generate all output formats
        ]
        
        self.logger.info(f"Running Whisper transcription: {audio_file.name}")
        self.logger.debug(f"Command: {' '.join(command)}")
        
        try:
            # Run Whisper
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            
            self.logger.debug(f"Whisper stdout: {result.stdout}")
            if result.stderr:
                self.logger.debug(f"Whisper stderr: {result.stderr}")
            
            # Find generated artifacts
            artifacts = self._find_artifacts(audio_file, output_dir)
            
            if not artifacts:
                self.logger.warning("No artifacts found after transcription")
            
            return WhisperResult(
                success=True,
                audio_file=audio_file,
                output_dir=output_dir,
                artifacts=artifacts,
                message="Transcription completed successfully"
            )
        
        except subprocess.TimeoutExpired as e:
            error = WhisperError(f"Whisper transcription timed out after {timeout}s")
            self.logger.error(str(error))
            return WhisperResult(
                success=False,
                audio_file=audio_file,
                output_dir=output_dir,
                artifacts={},
                message=str(error),
                error=error
            )
        
        except subprocess.CalledProcessError as e:
            error = WhisperError(f"Whisper failed: {e.stderr}")
            self.logger.error(f"Whisper error: {e.stderr}")
            return WhisperResult(
                success=False,
                audio_file=audio_file,
                output_dir=output_dir,
                artifacts={},
                message=str(error),
                error=error
            )
        
        except Exception as e:
            error = WhisperError(f"Unexpected error during transcription: {e}")
            self.logger.error(str(error), exc_info=True)
            return WhisperResult(
                success=False,
                audio_file=audio_file,
                output_dir=output_dir,
                artifacts={},
                message=str(error),
                error=error
            )
    
    def _find_artifacts(self, audio_file: Path, output_dir: Path) -> Dict[str, Optional[Path]]:
        """
        Find all Whisper output artifacts.
        
        Whisper generates files with the same base name as the input audio file.
        
        Args:
            audio_file: Original audio file
            output_dir: Directory where artifacts were generated
            
        Returns:
            Dictionary mapping extension to artifact path
        """
        artifacts = {}
        base_name = audio_file.stem
        
        for ext in self.ARTIFACT_EXTENSIONS:
            artifact_path = output_dir / f"{base_name}{ext}"
            if artifact_path.exists():
                artifacts[ext.lstrip('.')] = artifact_path
                self.logger.debug(f"Found artifact: {artifact_path}")
            else:
                artifacts[ext.lstrip('.')] = None
                self.logger.debug(f"Artifact not found: {artifact_path}")
        
        return artifacts
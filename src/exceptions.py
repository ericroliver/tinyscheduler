"""Custom exceptions for Calypso file processor."""


class CalypsoError(Exception):
    """Base exception for Calypso errors."""
    pass


class ConfigurationError(CalypsoError):
    """Configuration related errors."""
    pass


class ProcessingError(CalypsoError):
    """File processing errors."""
    pass


class WhisperError(ProcessingError):
    """Whisper transcription errors."""
    pass
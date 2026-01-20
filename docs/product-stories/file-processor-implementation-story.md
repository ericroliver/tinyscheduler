# Product Story: Calypso File Processor Implementation

## Story Overview

**Epic**: Automated File Processing System  
**Story**: Implement scheduled Python-based file processor with SOLID architecture  
**Story Points**: 13  
**Priority**: High  
**Status**: Ready for Implementation

## Business Value

Automate the processing of various file types (text, audio, spreadsheets, documents) to save time and ensure consistent handling. The system will transcribe audio files, extract spreadsheet data, and organize all processed files with comprehensive logging.

## User Story

As a user, I want an automated system that monitors a folder and processes files based on their type, so that I can automatically transcribe audio recordings, extract spreadsheet data, and organize my files without manual intervention.

## Acceptance Criteria

### Core Functionality
- ✅ System processes files from designated inbound folder
- ✅ Text files are moved directly to outbound folder
- ✅ Audio files are transcribed using Whisper and organized appropriately
- ✅ Spreadsheet files have all sheets extracted to CSV files
- ✅ Document/PDF files are moved to unprocessed folder
- ✅ Failed files are moved to dedicated failed folder with timestamps
- ✅ All operations are logged with appropriate detail levels

### Configuration
- ✅ Supports environment variables for folder paths (`.env` file)
- ✅ Supports CLI arguments that override environment variables
- ✅ Validates configuration before processing

### Error Handling
- ✅ Gracefully handles missing files
- ✅ Handles Whisper failures without crashing
- ✅ Handles corrupted Excel files
- ✅ Logs all errors with stack traces
- ✅ Moves failed files to appropriate locations

### Extensibility
- ✅ Easy to add new file type processors
- ✅ Factory pattern for processor selection
- ✅ SOLID principles implemented throughout

## Technical Requirements

### Architecture
- Follow SOLID principles as defined in [`kb/file-processor-architecture.md`](../../kb/file-processor-architecture.md)
- Implement all classes from [`kb/file-processor-technical-spec.md`](../../kb/file-processor-technical-spec.md)
- Use factory pattern for processor creation
- Abstract base class for all processors

### Dependencies
- Python 3.9+
- openai-whisper
- openpyxl, xlrd, pandas
- python-dotenv
- colorlog
- FFmpeg (external)

### File Structure
```
calypso/
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── file_processor.py
│   ├── factory.py
│   ├── detector.py
│   ├── file_manager.py
│   ├── logger.py
│   ├── exceptions.py
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── text.py
│   │   ├── audio.py
│   │   ├── spreadsheet.py
│   │   └── document.py
│   └── utils/
│       ├── __init__.py
│       ├── whisper_wrapper.py
│       └── excel_reader.py
├── scripts/
│   └── file_processor.py
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_processors.py
│   ├── test_factory.py
│   └── fixtures/
├── .env.example
├── requirements.txt
└── README.md
```

## Implementation Tasks

### Phase 1: Foundation (Priority: Highest)

#### Task 1.1: Project Structure Setup
**Description**: Create the complete folder structure and configuration files.

**Subtasks**:
- [ ] Create `src/` directory structure
- [ ] Create `tests/` directory with test fixtures folder
- [ ] Create `.env.example` file
- [ ] Create `requirements.txt` with all dependencies
- [ ] Create basic `README.md`

**Acceptance Criteria**:
- All directories created
- `.env.example` contains all required variables
- `requirements.txt` includes all dependencies from technical spec

**Dependencies**: None

**Estimated Time**: 30 minutes

---

#### Task 1.2: Exception Classes
**Description**: Implement custom exception classes.

**File**: [`src/exceptions.py`](../../src/exceptions.py)

**Implementation**:
```python
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
```

**Acceptance Criteria**:
- All exception classes defined
- Proper inheritance hierarchy
- Docstrings included

**Dependencies**: None

**Estimated Time**: 15 minutes

---

#### Task 1.3: Configuration Management
**Description**: Implement [`Config`](../../src/config.py) class for managing configuration.

**File**: [`src/config.py`](../../src/config.py)

**Key Features**:
- Load from environment variables
- Load from CLI arguments
- Validation of paths and settings
- Default values for optional settings

**Acceptance Criteria**:
- `from_env()` class method works
- `from_cli()` class method works
- `validate()` returns list of errors
- Creates missing directories
- CLI args override environment variables

**Dependencies**: Task 1.2

**Estimated Time**: 1 hour

---

#### Task 1.4: Logging Setup
**Description**: Implement logging configuration.

**File**: [`src/logger.py`](../../src/logger.py)

**Key Features**:
- Colored console output
- File logging with rotation
- Configurable log levels
- Consistent format

**Acceptance Criteria**:
- Logs to file and console
- Daily rotation with 30-day retention
- Colored output for console
- DEBUG, INFO, WARNING, ERROR levels work

**Dependencies**: None

**Estimated Time**: 45 minutes

---

### Phase 2: Core Classes (Priority: High)

#### Task 2.1: Base File Processor
**Description**: Implement abstract base class for all processors.

**File**: [`src/processors/base.py`](../../src/processors/base.py)

**Key Features**:
- Abstract `process()` method
- Abstract `get_supported_extensions()` method
- `_validate_file()` helper method
- `ProcessResult` dataclass

**Acceptance Criteria**:
- Cannot instantiate directly (abstract)
- `_validate_file()` checks existence and readability
- `ProcessResult` captures all necessary information

**Dependencies**: Task 1.2

**Estimated Time**: 45 minutes

---

#### Task 2.2: File Manager
**Description**: Implement file operations utility.

**File**: [`src/file_manager.py`](../../src/file_manager.py)

**Key Features**:
- Move files
- Copy files
- Create directories
- Ensure directories exist

**Acceptance Criteria**:
- All operations handle errors gracefully
- Creates parent directories as needed
- Returns boolean success indicators
- Logs operations

**Dependencies**: Task 1.4

**Estimated Time**: 1 hour

---

#### Task 2.3: Processor Factory
**Description**: Implement factory pattern for processor creation.

**File**: [`src/factory.py`](../../src/factory.py)

**Key Features**:
- Register processors
- Get processor by extension
- List all supported extensions
- Check if extension is supported

**Acceptance Criteria**:
- Can register multiple processors
- Returns correct processor for extension
- Case-insensitive extension matching
- Returns None for unsupported extensions

**Dependencies**: Task 2.1

**Estimated Time**: 45 minutes

---

#### Task 2.4: File Type Detector
**Description**: Implement file type detection.

**File**: [`src/detector.py`](../../src/detector.py)

**Key Features**:
- Detect file type by extension
- Check if supported
- Use factory for extension lookup

**Acceptance Criteria**:
- Correctly identifies file types
- Works with factory
- Case-insensitive

**Dependencies**: Task 2.3

**Estimated Time**: 30 minutes

---

### Phase 3: File Processors (Priority: High)

#### Task 3.1: Text File Processor
**Description**: Implement processor for text-based files.

**File**: [`src/processors/text.py`](../../src/processors/text.py)

**Supported Extensions**: `.txt`, `.log`, `.html`, `.md`, `.json`, `.xml`, `.csv`, `.srt`, `.vtt`, `.tsv`

**Processing Logic**:
1. Validate file exists
2. Move to outbound folder
3. Log success

**Acceptance Criteria**:
- Moves file to outbound preserving name
- Returns success result
- Handles errors gracefully
- All supported extensions listed

**Dependencies**: Task 2.1, Task 2.2

**Estimated Time**: 45 minutes

---

#### Task 3.2: Whisper Wrapper
**Description**: Implement wrapper for Whisper CLI.

**File**: [`src/utils/whisper_wrapper.py`](../../src/utils/whisper_wrapper.py)

**Key Features**:
- Execute Whisper command
- Find generated artifacts
- Handle timeouts
- Check Whisper installation

**Acceptance Criteria**:
- Runs Whisper successfully
- Finds all output files (.txt, .json, .srt, .vtt, .tsv)
- Respects timeout setting
- Returns structured result

**Dependencies**: Task 1.2

**Estimated Time**: 1.5 hours

---

#### Task 3.3: Audio File Processor
**Description**: Implement processor for audio files.

**File**: [`src/processors/audio.py`](../../src/processors/audio.py)

**Supported Extensions**: `.m4a`, `.mp3`, `.wav`, `.flac`

**Processing Logic**:
1. Validate audio file
2. Run Whisper transcription
3. Find all artifacts
4. Copy `.txt` file to outbound
5. Create `logs/{root_name}/` directory
6. Move all artifacts to log directory
7. Move original audio to log directory

**Acceptance Criteria**:
- Transcribes audio successfully
- Copies .txt to outbound
- Organizes all artifacts in logs folder
- Returns detailed result with processing time
- Handles Whisper failures

**Dependencies**: Task 2.1, Task 2.2, Task 3.2

**Estimated Time**: 2 hours

---

#### Task 3.4: Excel Reader
**Description**: Implement Excel file reading and CSV extraction.

**File**: [`src/utils/excel_reader.py`](../../src/utils/excel_reader.py)

**Key Features**:
- Get sheet names from workbook
- Extract sheet to CSV
- Sanitize sheet names for filenames
- Support both `.xls` and `.xlsx`

**Acceptance Criteria**:
- Reads both Excel formats
- Extracts all sheets
- Sanitizes invalid filename characters
- Returns success/failure for each operation

**Dependencies**: None

**Estimated Time**: 1 hour

---

#### Task 3.5: Spreadsheet Processor
**Description**: Implement processor for spreadsheet files.

**File**: [`src/processors/spreadsheet.py`](../../src/processors/spreadsheet.py)

**Supported Extensions**: `.xls`, `.xlsx`

**Processing Logic**:
1. Validate spreadsheet file
2. Get all sheet names
3. Extract each sheet to CSV named `{root_name}_{sheet_name}.csv`
4. Copy all CSVs to outbound
5. Create `logs/{root_name}/` directory
6. Move CSVs to log directory
7. Move original spreadsheet to log directory

**Acceptance Criteria**:
- Extracts all sheets
- Creates properly named CSVs
- Copies CSVs to outbound
- Organizes artifacts in logs folder
- Handles corrupted files
- Handles password-protected files

**Dependencies**: Task 2.1, Task 2.2, Task 3.4

**Estimated Time**: 1.5 hours

---

#### Task 3.6: Document Processor
**Description**: Implement processor for documents and PDFs.

**File**: [`src/processors/document.py`](../../src/processors/document.py)

**Supported Extensions**: `.doc`, `.docx`, `.pdf`, `.odt`, `.rtf`

**Processing Logic**:
1. Validate document exists
2. Create `logs/unprocessed/` directory
3. Move file to unprocessed folder
4. Log as unprocessed

**Acceptance Criteria**:
- Moves to unprocessed folder
- Preserves filename
- Logs appropriately
- Returns success result

**Dependencies**: Task 2.1, Task 2.2

**Estimated Time**: 30 minutes

---

### Phase 4: Main Orchestration (Priority: High)

#### Task 4.1: File Processor Orchestrator
**Description**: Implement main file processing orchestrator.

**File**: [`src/file_processor.py`](../../src/file_processor.py)

**Key Features**:
- Scan inbound folder
- Process each file
- Handle errors
- Track statistics
- Move failed files

**Acceptance Criteria**:
- Processes all files in inbound
- Uses correct processor for each file
- Handles unsupported files
- Handles errors without crashing
- Returns processing statistics
- Logs all operations

**Dependencies**: Tasks 2.2, 2.3, 2.4, all processors

**Estimated Time**: 2 hours

---

#### Task 4.2: CLI Entry Point
**Description**: Implement command-line interface.

**File**: [`scripts/file_processor.py`](../../scripts/file_processor.py)

**Key Features**:
- Parse CLI arguments
- Load configuration
- Initialize all components
- Run file processor
- Exit with appropriate code

**Acceptance Criteria**:
- `--help` shows usage
- CLI args override environment
- Validates configuration
- Handles errors gracefully
- Returns 0 on success, non-zero on failure
- Supports `--dry-run` flag
- Supports `--verbose` flag

**Dependencies**: Tasks 1.3, 1.4, 4.1

**Estimated Time**: 1.5 hours

---

### Phase 5: Testing (Priority: Medium)

#### Task 5.1: Unit Tests - Core Classes
**Description**: Write unit tests for core classes.

**Files**:
- `tests/test_config.py`
- `tests/test_factory.py`
- `tests/test_detector.py`
- `tests/test_file_manager.py`

**Acceptance Criteria**:
- All classes have >80% coverage
- Tests pass independently
- Mock external dependencies
- Test error conditions

**Dependencies**: All Phase 2 tasks

**Estimated Time**: 3 hours

---

#### Task 5.2: Unit Tests - Processors
**Description**: Write unit tests for all processors.

**Files**:
- `tests/test_text_processor.py`
- `tests/test_audio_processor.py`
- `tests/test_spreadsheet_processor.py`
- `tests/test_document_processor.py`

**Acceptance Criteria**:
- Each processor has >80% coverage
- Mock file operations
- Mock Whisper calls
- Test error handling
- Test all supported extensions

**Dependencies**: All Phase 3 tasks

**Estimated Time**: 4 hours

---

#### Task 5.3: Integration Tests
**Description**: Write integration tests for complete workflows.

**File**: `tests/test_integration.py`

**Test Cases**:
- Complete text file processing
- Complete audio file processing (mocked Whisper)
- Complete spreadsheet processing
- Complete document processing
- Error recovery
- Unsupported files

**Acceptance Criteria**:
- Tests use real file fixtures
- Tests verify file movements
- Tests check log output
- All workflows tested end-to-end

**Dependencies**: All implementation tasks

**Estimated Time**: 3 hours

---

#### Task 5.4: Test Fixtures
**Description**: Create test fixture files.

**Directory**: `tests/fixtures/`

**Files Needed**:
- Sample text files (txt, log, md, html, json)
- Sample audio files (small mp3/wav)
- Sample spreadsheets (xlsx with multiple sheets)
- Sample documents (small PDF)
- Corrupted files
- Empty files

**Acceptance Criteria**:
- Fixtures for all file types
- Small file sizes for quick tests
- Includes edge cases

**Dependencies**: None

**Estimated Time**: 1 hour

---

### Phase 6: Documentation and Deployment (Priority: Low)

#### Task 6.1: README Documentation
**Description**: Create comprehensive README.

**File**: `README.md`

**Content**:
- Project overview
- Quick start guide
- Installation instructions
- Configuration guide
- Usage examples
- Troubleshooting

**Acceptance Criteria**:
- Clear and complete
- Includes examples
- Links to detailed docs
- Installation steps tested

**Dependencies**: All implementation complete

**Estimated Time**: 2 hours

---

#### Task 6.2: Requirements Files
**Description**: Finalize dependency lists.

**Files**:
- `requirements.txt`
- `requirements-dev.txt`
- `.env.example`

**Acceptance Criteria**:
- All dependencies listed with versions
- Dev dependencies separated
- `.env.example` documented

**Dependencies**: All implementation complete

**Estimated Time**: 30 minutes

---

#### Task 6.3: Deployment Scripts
**Description**: Create deployment helpers.

**Files**:
- `setup.sh` (Linux/macOS setup script)
- Systemd service/timer examples
- Cron examples in README

**Acceptance Criteria**:
- Scripts work on fresh system
- Examples are tested
- Documentation clear

**Dependencies**: Task 6.1

**Estimated Time**: 1 hour

---

## Implementation Order

### Sprint 1: Foundation (Days 1-2)
1. Task 1.1 - Project Structure
2. Task 1.2 - Exceptions
3. Task 1.3 - Configuration
4. Task 1.4 - Logging
5. Task 5.4 - Test Fixtures

### Sprint 2: Core Framework (Days 3-4)
1. Task 2.1 - Base Processor
2. Task 2.2 - File Manager
3. Task 2.3 - Factory
4. Task 2.4 - Detector
5. Task 5.1 - Core Tests

### Sprint 3: Processors (Days 5-7)
1. Task 3.1 - Text Processor
2. Task 3.2 - Whisper Wrapper
3. Task 3.3 - Audio Processor
4. Task 3.4 - Excel Reader
5. Task 3.5 - Spreadsheet Processor
6. Task 3.6 - Document Processor
7. Task 5.2 - Processor Tests

### Sprint 4: Orchestration (Days 8-9)
1. Task 4.1 - File Processor
2. Task 4.2 - CLI Entry Point
3. Task 5.3 - Integration Tests

### Sprint 5: Polish (Days 10)
1. Task 6.1 - README
2. Task 6.2 - Requirements
3. Task 6.3 - Deployment Scripts
4. Bug fixes and refinements

## Definition of Done

- [ ] All code written and reviewed
- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Code coverage >80%
- [ ] Documentation complete
- [ ] Manual testing completed
- [ ] Can process all file types successfully
- [ ] Error handling tested
- [ ] Deployment tested on clean system
- [ ] README reviewed and accurate

## Testing Strategy

### Unit Testing
- Mock all file I/O
- Mock Whisper calls
- Test error conditions
- Test edge cases
- Use pytest fixtures

### Integration Testing
- Use real test files
- Test complete workflows
- Verify file movements
- Check log output
- Test error recovery

### Manual Testing
- Test with real audio files
- Test with real spreadsheets
- Test with various file sizes
- Test error scenarios
- Test on target system

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Whisper installation issues | Medium | High | Detailed setup docs, version pinning |
| Large file timeout | Medium | Medium | Configurable timeout, progress logging |
| Corrupted file handling | High | Low | Comprehensive error handling |
| Disk space issues | Low | High | Size validation, disk space checks |
| Excel compatibility | Medium | Medium | Support both .xls and .xlsx |

## Success Metrics

- **Reliability**: >99% processing success rate
- **Performance**: Text files <1s, Audio files <file_length*0.5
- **Maintainability**: Code coverage >80%, SOLID principles followed
- **Usability**: Setup time <30 minutes
- **Extensibility**: New processor can be added in <2 hours

## References

- [Architecture Design](../../kb/file-processor-architecture.md)
- [Technical Specification](../../kb/file-processor-technical-spec.md)
- [Environment Setup](../../kb/environment-setup.md)

## Notes for Implementation

### Code Style
- Follow PEP 8
- Use type hints
- Comprehensive docstrings
- Meaningful variable names

### Testing Best Practices
- Arrange-Act-Assert pattern
- One assertion per test (when practical)
- Clear test names
- Use pytest fixtures

### Git Workflow
- Feature branches for each task
- Commit after each logical change
- Clear commit messages
- Reference task numbers

### Code Review Checklist
- Tests pass
- Documentation updated
- Error handling appropriate
- Logging appropriate
- SOLID principles followed
- No code duplication

---

**Story Created**: 2023-12-13  
**Last Updated**: 2023-12-13  
**Ready for Implementation**: Yes  
**Approved By**: Product Owner  
**Assigned To**: Development Team
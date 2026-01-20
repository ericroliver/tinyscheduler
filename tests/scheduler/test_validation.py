"""Tests for TinyScheduler validation functionality."""

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.scheduler.config import TinySchedulerConfig
from src.scheduler.validation import validate_agent_control_file, DEFAULT_AGENT_CONTROL


class TestAgentControlFileValidation:
    """Tests for agent control file validation."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def valid_control_data(self):
        """Valid agent control file data."""
        return [
            {
                "agentName": "dispatcher",
                "agentType": "orchestrator"
            },
            {
                "agentName": "architect",
                "agentType": "architect"
            }
        ]
    
    @pytest.fixture
    def mock_config(self, temp_dir):
        """Create a mock config for testing."""
        config = mock.Mock(spec=TinySchedulerConfig)
        config.agent_control_file = temp_dir / "agent-control.json"
        config.base_path = temp_dir
        return config
    
    def test_config_with_env_variable(self, temp_dir):
        """Test config loads agent_control_file from environment variable."""
        custom_path = temp_dir / "custom-agents.json"
        
        with mock.patch.dict(os.environ, {
            'TINYSCHEDULER_BASE_PATH': str(temp_dir),
            'TINYSCHEDULER_AGENT_CONTROL_FILE': str(custom_path)
        }):
            config = TinySchedulerConfig.from_env()
            assert config.agent_control_file == custom_path
    
    def test_config_with_default_value(self, temp_dir):
        """Test config uses default path when env variable not set."""
        with mock.patch.dict(os.environ, {
            'TINYSCHEDULER_BASE_PATH': str(temp_dir)
        }, clear=True):
            config = TinySchedulerConfig.from_env()
            expected_path = temp_dir / "docs" / "technical" / "agent-control.json"
            assert config.agent_control_file == expected_path
    
    def test_validation_with_valid_file(self, mock_config, valid_control_data):
        """Test validation passes with valid file."""
        # Create valid file
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(valid_control_data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have success message and no errors
        assert len(results) > 0
        error_results = [r for r in results if r.is_error and not r.success]
        assert len(error_results) == 0
        
        # Check success message
        success_results = [r for r in results if not r.is_error and r.success]
        assert len(success_results) > 0
        assert "valid" in success_results[0].message.lower()
    
    def test_validation_with_missing_file(self, mock_config):
        """Test validation fails when file is missing."""
        results = validate_agent_control_file(mock_config, fix=False)
        
        # Should have error about missing file
        assert len(results) > 0
        assert any("not found" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_invalid_json(self, mock_config):
        """Test validation fails with invalid JSON syntax."""
        # Create file with invalid JSON
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.agent_control_file, 'w') as f:
            f.write('{ invalid json }')
        
        results = validate_agent_control_file(mock_config)
        
        # Should have JSON error
        assert any("invalid json" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_wrong_structure(self, mock_config):
        """Test validation fails when file is not an array."""
        # Create file with object instead of array
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump({"agentName": "test"}, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have structure error
        assert any("array" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_empty_array(self, mock_config):
        """Test validation fails with empty array."""
        # Create file with empty array
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump([], f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have error about empty array
        assert any("empty" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_missing_agent_name(self, mock_config):
        """Test validation fails when agentName is missing."""
        # Create file missing agentName
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        data = [{"agentType": "orchestrator"}]
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have error about missing agentName
        assert any("agentname" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_missing_agent_type(self, mock_config):
        """Test validation fails when agentType is missing."""
        # Create file missing agentType
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        data = [{"agentName": "dispatcher"}]
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have error about missing agentType
        assert any("agenttype" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_empty_agent_name(self, mock_config):
        """Test validation fails when agentName is empty."""
        # Create file with empty agentName
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        data = [{"agentName": "", "agentType": "orchestrator"}]
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have error about empty agentName
        assert any("cannot be empty" in r.message.lower() or "empty" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_empty_agent_type(self, mock_config):
        """Test validation fails when agentType is empty."""
        # Create file with empty agentType
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        data = [{"agentName": "dispatcher", "agentType": ""}]
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have error about empty agentType
        assert any("cannot be empty" in r.message.lower() or "empty" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_invalid_field_type(self, mock_config):
        """Test validation fails when fields have wrong type."""
        # Create file with numeric agentName
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        data = [{"agentName": 123, "agentType": "orchestrator"}]
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have type error
        assert any("string" in r.message.lower() for r in results)
        assert any(r.is_error and not r.success for r in results)
    
    def test_validation_with_duplicate_agent_names(self, mock_config):
        """Test validation warns about duplicate agent names."""
        # Create file with duplicate names
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {"agentName": "dispatcher", "agentType": "orchestrator"},
            {"agentName": "dispatcher", "agentType": "architect"}
        ]
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # Should have warning about duplicates
        assert any("duplicate" in r.message.lower() for r in results)
    
    def test_auto_fix_creates_file(self, mock_config):
        """Test auto-fix creates default file when missing."""
        results = validate_agent_control_file(mock_config, fix=True)
        
        # File should be created
        assert mock_config.agent_control_file.exists()
        
        # Should have success message
        assert any("created" in r.message.lower() for r in results)
        
        # File should contain default data
        with open(mock_config.agent_control_file) as f:
            data = json.load(f)
        assert data == DEFAULT_AGENT_CONTROL
    
    def test_auto_fix_doesnt_overwrite_existing(self, mock_config, valid_control_data):
        """Test auto-fix doesn't overwrite existing valid file."""
        # Create valid file
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(valid_control_data, f)
        
        # Get original modification time
        original_mtime = mock_config.agent_control_file.stat().st_mtime
        
        # Run validation with fix
        results = validate_agent_control_file(mock_config, fix=True)
        
        # File should not be modified
        new_mtime = mock_config.agent_control_file.stat().st_mtime
        assert new_mtime == original_mtime
        
        # Should not have "created" message
        assert not any("created" in r.message.lower() and r.success for r in results if "default" in r.message.lower())
    
    def test_auto_fix_creates_parent_directories(self, mock_config):
        """Test auto-fix creates parent directories if needed."""
        # Set path with non-existent parent
        mock_config.agent_control_file = mock_config.base_path / "deep" / "nested" / "agent-control.json"
        
        results = validate_agent_control_file(mock_config, fix=True)
        
        # Parent directories should be created
        assert mock_config.agent_control_file.parent.exists()
        assert mock_config.agent_control_file.exists()
    
    def test_validation_result_string_representation(self, mock_config, valid_control_data):
        """Test ValidationResult string representation."""
        # Create valid file
        mock_config.agent_control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.agent_control_file, 'w') as f:
            json.dump(valid_control_data, f)
        
        results = validate_agent_control_file(mock_config)
        
        # All results should have string representation
        for result in results:
            result_str = str(result)
            assert len(result_str) > 0
            # Should start with ✓ or ✗
            assert result_str[0] in ['✓', '✗']


class TestConfigIntegration:
    """Integration tests for config with agent control file."""
    
    def test_config_to_dict_includes_agent_control_file(self):
        """Test config.to_dict() includes agent_control_file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {
                'TINYSCHEDULER_BASE_PATH': tmpdir
            }):
                config = TinySchedulerConfig.from_env()
                config_dict = config.to_dict()
                
                assert 'agent_control_file' in config_dict
                assert config_dict['agent_control_file'] == str(config.agent_control_file)
    
    def test_config_str_includes_agent_control_file(self):
        """Test str(config) includes agent_control_file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {
                'TINYSCHEDULER_BASE_PATH': tmpdir
            }):
                config = TinySchedulerConfig.from_env()
                config_str = str(config)
                
                assert 'Agent Control File' in config_str
                assert str(config.agent_control_file) in config_str

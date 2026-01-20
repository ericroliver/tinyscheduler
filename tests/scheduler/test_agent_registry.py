"""Unit tests for AgentRegistry class."""

import json
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.scheduler.agent_registry import AgentConfig, AgentRegistry


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""
    
    def test_from_dict_valid(self):
        """Test creating AgentConfig from valid dictionary."""
        data = {"agentName": "vaela", "agentType": "dev"}
        config = AgentConfig.from_dict(data)
        
        assert config.agent_name == "vaela"
        assert config.agent_type == "dev"
    
    def test_from_dict_missing_agent_name(self):
        """Test creating AgentConfig with missing agentName field."""
        data = {"agentType": "dev"}
        
        with pytest.raises(KeyError) as exc_info:
            AgentConfig.from_dict(data)
        
        assert "agentName" in str(exc_info.value)
    
    def test_from_dict_missing_agent_type(self):
        """Test creating AgentConfig with missing agentType field."""
        data = {"agentName": "vaela"}
        
        with pytest.raises(KeyError) as exc_info:
            AgentConfig.from_dict(data)
        
        assert "agentType" in str(exc_info.value)
    
    def test_from_dict_unexpected_fields(self, caplog):
        """Test creating AgentConfig with unexpected fields logs warning."""
        data = {
            "agentName": "vaela",
            "agentType": "dev",
            "unexpectedField": "value",
            "anotherField": 123
        }
        
        config = AgentConfig.from_dict(data)
        
        # Should still create the config
        assert config.agent_name == "vaela"
        assert config.agent_type == "dev"
        
        # Should log warning about unexpected fields
        assert "unexpected fields" in caplog.text.lower()


class TestAgentRegistry:
    """Tests for AgentRegistry class."""
    
    @pytest.fixture
    def valid_control_file(self, tmp_path):
        """Create a valid agent control file for testing."""
        control_file = tmp_path / "agent-control.json"
        data = [
            {"agentName": "vaela", "agentType": "dev"},
            {"agentName": "damien", "agentType": "dev"},
            {"agentName": "oscar", "agentType": "qa"},
            {"agentName": "kalis", "agentType": "qa"},
        ]
        control_file.write_text(json.dumps(data, indent=2))
        return control_file
    
    @pytest.fixture
    def empty_control_file(self, tmp_path):
        """Create an empty agent control file (empty array)."""
        control_file = tmp_path / "empty-control.json"
        control_file.write_text("[]")
        return control_file
    
    @pytest.fixture
    def single_agent_file(self, tmp_path):
        """Create a control file with a single agent."""
        control_file = tmp_path / "single-agent.json"
        data = [{"agentName": "solo", "agentType": "special"}]
        control_file.write_text(json.dumps(data))
        return control_file
    
    @pytest.fixture
    def duplicate_agents_file(self, tmp_path):
        """Create a control file with duplicate agent names."""
        control_file = tmp_path / "duplicate-agents.json"
        data = [
            {"agentName": "agent1", "agentType": "type1"},
            {"agentName": "agent1", "agentType": "type2"},  # Duplicate name
            {"agentName": "agent2", "agentType": "type1"},
        ]
        control_file.write_text(json.dumps(data))
        return control_file
    
    @pytest.fixture
    def malformed_json_file(self, tmp_path):
        """Create a file with invalid JSON."""
        control_file = tmp_path / "malformed.json"
        control_file.write_text('{"invalid": json, missing quotes}')
        return control_file
    
    @pytest.fixture
    def not_array_file(self, tmp_path):
        """Create a file with valid JSON but not an array."""
        control_file = tmp_path / "not-array.json"
        control_file.write_text('{"agentName": "test", "agentType": "dev"}')
        return control_file
    
    @pytest.fixture
    def missing_fields_file(self, tmp_path):
        """Create a file with entries missing required fields."""
        control_file = tmp_path / "missing-fields.json"
        data = [
            {"agentName": "valid", "agentType": "dev"},
            {"agentName": "missing-type"},  # Missing agentType
        ]
        control_file.write_text(json.dumps(data))
        return control_file
    
    # Tests for successful loading
    
    def test_load_valid_control_file(self, valid_control_file):
        """Test loading a valid control file."""
        registry = AgentRegistry(valid_control_file)
        
        assert len(registry.agents) == 4
        assert len(registry.get_all_agent_names()) == 4
        assert len(registry.get_all_types()) == 2
    
    def test_load_empty_control_file(self, empty_control_file):
        """Test loading an empty control file (empty array)."""
        registry = AgentRegistry(empty_control_file)
        
        assert len(registry.agents) == 0
        assert len(registry.get_all_agent_names()) == 0
        assert len(registry.get_all_types()) == 0
    
    def test_load_single_agent(self, single_agent_file):
        """Test loading a control file with a single agent."""
        registry = AgentRegistry(single_agent_file)
        
        assert len(registry.agents) == 1
        assert registry.agents[0].agent_name == "solo"
        assert registry.agents[0].agent_type == "special"
    
    def test_load_duplicate_agents(self, duplicate_agents_file, caplog):
        """Test loading a control file with duplicate agent names."""
        registry = AgentRegistry(duplicate_agents_file)
        
        # Should load all entries but warn about duplicates
        assert len(registry.agents) == 3
        assert "duplicate" in caplog.text.lower()
        
        # Last occurrence should be kept
        assert registry.get_agent_type("agent1") == "type2"
    
    # Tests for error handling
    
    def test_missing_file(self, tmp_path):
        """Test error handling for missing control file."""
        non_existent = tmp_path / "does-not-exist.json"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            AgentRegistry(non_existent)
        
        assert str(non_existent) in str(exc_info.value)
    
    def test_malformed_json(self, malformed_json_file):
        """Test error handling for malformed JSON."""
        with pytest.raises(json.JSONDecodeError):
            AgentRegistry(malformed_json_file)
    
    def test_not_array(self, not_array_file):
        """Test error handling when JSON is not an array."""
        with pytest.raises(ValueError) as exc_info:
            AgentRegistry(not_array_file)
        
        assert "array" in str(exc_info.value).lower()
    
    def test_missing_required_fields(self, missing_fields_file):
        """Test error handling for entries missing required fields."""
        with pytest.raises(KeyError) as exc_info:
            AgentRegistry(missing_fields_file)
        
        assert "agentType" in str(exc_info.value)
    
    # Tests for index building
    
    def test_index_by_type(self, valid_control_file):
        """Test that agents are correctly indexed by type."""
        registry = AgentRegistry(valid_control_file)
        
        dev_agents = registry.get_agents_by_type("dev")
        qa_agents = registry.get_agents_by_type("qa")
        
        assert set(dev_agents) == {"vaela", "damien"}
        assert set(qa_agents) == {"oscar", "kalis"}
    
    def test_index_by_name(self, valid_control_file):
        """Test that agents are correctly indexed by name."""
        registry = AgentRegistry(valid_control_file)
        
        assert registry.get_agent_type("vaela") == "dev"
        assert registry.get_agent_type("damien") == "dev"
        assert registry.get_agent_type("oscar") == "qa"
        assert registry.get_agent_type("kalis") == "qa"
    
    # Tests for query methods
    
    def test_get_agents_by_type_valid(self, valid_control_file):
        """Test get_agents_by_type with valid type."""
        registry = AgentRegistry(valid_control_file)
        
        dev_agents = registry.get_agents_by_type("dev")
        
        assert len(dev_agents) == 2
        assert "vaela" in dev_agents
        assert "damien" in dev_agents
    
    def test_get_agents_by_type_unknown(self, valid_control_file):
        """Test get_agents_by_type with unknown type."""
        registry = AgentRegistry(valid_control_file)
        
        agents = registry.get_agents_by_type("unknown")
        
        assert agents == []
    
    def test_get_agents_by_type_empty_registry(self, empty_control_file):
        """Test get_agents_by_type on empty registry."""
        registry = AgentRegistry(empty_control_file)
        
        agents = registry.get_agents_by_type("any")
        
        assert agents == []
    
    def test_get_agent_type_valid(self, valid_control_file):
        """Test get_agent_type with valid agent name."""
        registry = AgentRegistry(valid_control_file)
        
        agent_type = registry.get_agent_type("vaela")
        
        assert agent_type == "dev"
    
    def test_get_agent_type_unknown(self, valid_control_file):
        """Test get_agent_type with unknown agent name."""
        registry = AgentRegistry(valid_control_file)
        
        agent_type = registry.get_agent_type("unknown")
        
        assert agent_type is None
    
    def test_get_agent_type_empty_registry(self, empty_control_file):
        """Test get_agent_type on empty registry."""
        registry = AgentRegistry(empty_control_file)
        
        agent_type = registry.get_agent_type("any")
        
        assert agent_type is None
    
    def test_get_all_types(self, valid_control_file):
        """Test get_all_types returns all unique types."""
        registry = AgentRegistry(valid_control_file)
        
        types = registry.get_all_types()
        
        assert len(types) == 2
        assert set(types) == {"dev", "qa"}
    
    def test_get_all_types_empty_registry(self, empty_control_file):
        """Test get_all_types on empty registry."""
        registry = AgentRegistry(empty_control_file)
        
        types = registry.get_all_types()
        
        assert types == []
    
    def test_get_all_agent_names(self, valid_control_file):
        """Test get_all_agent_names returns all agent names."""
        registry = AgentRegistry(valid_control_file)
        
        names = registry.get_all_agent_names()
        
        assert len(names) == 4
        assert set(names) == {"vaela", "damien", "oscar", "kalis"}
    
    def test_get_all_agent_names_preserves_order(self, valid_control_file):
        """Test get_all_agent_names preserves file order."""
        registry = AgentRegistry(valid_control_file)
        
        names = registry.get_all_agent_names()
        
        # Should match the order in the fixture
        assert names == ["vaela", "damien", "oscar", "kalis"]
    
    def test_get_all_agent_names_empty_registry(self, empty_control_file):
        """Test get_all_agent_names on empty registry."""
        registry = AgentRegistry(empty_control_file)
        
        names = registry.get_all_agent_names()
        
        assert names == []
    
    # Tests for reload functionality
    
    def test_reload_updates_registry(self, tmp_path):
        """Test that reload() updates the registry with new data."""
        control_file = tmp_path / "reload-test.json"
        
        # Initial data
        initial_data = [
            {"agentName": "agent1", "agentType": "type1"}
        ]
        control_file.write_text(json.dumps(initial_data))
        
        registry = AgentRegistry(control_file)
        assert len(registry.agents) == 1
        assert registry.get_agent_type("agent1") == "type1"
        
        # Update the file
        updated_data = [
            {"agentName": "agent1", "agentType": "type2"},  # Changed type
            {"agentName": "agent2", "agentType": "type1"}   # Added agent
        ]
        control_file.write_text(json.dumps(updated_data))
        
        # Reload
        registry.reload()
        
        # Verify updates
        assert len(registry.agents) == 2
        assert registry.get_agent_type("agent1") == "type2"
        assert registry.get_agent_type("agent2") == "type1"
        assert len(registry.get_all_types()) == 2
    
    def test_reload_handles_errors(self, tmp_path):
        """Test that reload() raises appropriate errors."""
        control_file = tmp_path / "reload-error-test.json"
        
        # Initial valid data
        initial_data = [{"agentName": "agent1", "agentType": "type1"}]
        control_file.write_text(json.dumps(initial_data))
        
        registry = AgentRegistry(control_file)
        assert len(registry.agents) == 1
        
        # Corrupt the file
        control_file.write_text("invalid json")
        
        # Reload should raise error
        with pytest.raises(json.JSONDecodeError):
            registry.reload()
        
        # Original data should still be intact
        assert len(registry.agents) == 1
    
    def test_reload_after_file_deletion(self, tmp_path):
        """Test reload() when control file is deleted."""
        control_file = tmp_path / "delete-test.json"
        
        # Initial data
        initial_data = [{"agentName": "agent1", "agentType": "type1"}]
        control_file.write_text(json.dumps(initial_data))
        
        registry = AgentRegistry(control_file)
        assert len(registry.agents) == 1
        
        # Delete the file
        control_file.unlink()
        
        # Reload should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            registry.reload()
        
        # Original data should still be intact
        assert len(registry.agents) == 1
    
    # Integration tests
    
    def test_multiple_types_integration(self, tmp_path):
        """Test registry with agents across multiple types."""
        control_file = tmp_path / "multi-type.json"
        data = [
            {"agentName": "dev1", "agentType": "developer"},
            {"agentName": "dev2", "agentType": "developer"},
            {"agentName": "qa1", "agentType": "qa"},
            {"agentName": "qa2", "agentType": "qa"},
            {"agentName": "arch1", "agentType": "architect"},
        ]
        control_file.write_text(json.dumps(data))
        
        registry = AgentRegistry(control_file)
        
        # Verify all types
        assert len(registry.get_all_types()) == 3
        assert set(registry.get_all_types()) == {"developer", "qa", "architect"}
        
        # Verify agents by type
        assert len(registry.get_agents_by_type("developer")) == 2
        assert len(registry.get_agents_by_type("qa")) == 2
        assert len(registry.get_agents_by_type("architect")) == 1
        
        # Verify total count
        assert len(registry.get_all_agent_names()) == 5
    
    def test_real_world_agent_control_file(self):
        """Test with the actual agent-control.json file if it exists."""
        # This test uses the real control file from the docs
        control_file = Path("workspace/calypso/docs/technical/agent-control.json")
        
        if not control_file.exists():
            pytest.skip("Real agent-control.json file not found")
        
        registry = AgentRegistry(control_file)
        
        # Verify it loads successfully
        assert len(registry.agents) > 0
        assert len(registry.get_all_types()) > 0
        
        # Verify expected agents based on the file we saw earlier
        assert "vaela" in registry.get_all_agent_names()
        assert "damien" in registry.get_all_agent_names()
        assert registry.get_agent_type("vaela") == "dev"
        assert registry.get_agent_type("oscar") == "qa"


if __name__ == "__main__":
    # Allow running tests directly with: python test_agent_registry.py
    pytest.main([__file__, "-v"])

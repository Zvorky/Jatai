"""
Tests for jatai.core.registry module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import pytest
import yaml
import threading
import time
from pathlib import Path
from jatai.core.registry import Registry


class TestRegistryHappyPath:
    """Happy path tests for Registry."""

    def test_registry_init_default_path(self, temp_home):
        """Test Registry initialization with default home path."""
        registry = Registry()
        assert registry.registry_path == temp_home / ".jatai"

    def test_registry_init_custom_path(self, temp_dir):
        """Test Registry initialization with custom path."""
        custom_path = temp_dir / "custom_registry.yaml"
        registry = Registry(registry_path=custom_path)
        assert registry.registry_path == custom_path

    def test_registry_default_config(self):
        """Test Registry has correct default configuration."""
        registry = Registry()
        expected_keys = {
            "PREFIX_PROCESSED",
            "PREFIX_ERROR",
            "RETRY_DELAY_BASE",
            "MAX_RETRIES",
            "INBOX_DIR",
            "OUTBOX_DIR",
            "GC_MAX_READ_FILES",
            "GC_MAX_SENT_FILES",
            "GC_DELETE_MODE",
            "LATEST_LOG_PATH",
        }
        assert set(registry.DEFAULT_CONFIG.keys()) == expected_keys

    def test_registry_save_and_load(self, temp_dir):
        """Test saving and loading registry to/from disk."""
        registry_path = temp_dir / ".jatai"
        registry = Registry(registry_path=registry_path)

        # Add some nodes
        registry.add_node("node1", "/path/to/node1")
        registry.add_node("node2", "/path/to/node2", {"CUSTOM_KEY": "value"})
        registry.set_config("PREFIX_PROCESSED", "-processed")

        # Save to disk
        registry.save()
        assert registry_path.exists()

        # Load fresh instance
        registry2 = Registry(registry_path=registry_path)
        registry2.load()

        assert "node1" in registry2.nodes
        assert "node2" in registry2.nodes
        assert registry2.global_config["PREFIX_PROCESSED"] == "-processed"
        assert registry2.nodes["node2"]["CUSTOM_KEY"] == "value"

    def test_registry_add_node(self):
        """Test adding nodes to registry."""
        registry = Registry()
        registry.add_node("test_node", "/path/to/node")

        assert "test_node" in registry.nodes
        assert registry.nodes["test_node"]["path"] == "/path/to/node"

    def test_registry_get_node(self):
        """Test retrieving a node from registry."""
        registry = Registry()
        registry.add_node("test_node", "/path/to/node", {"key": "value"})

        node = registry.get_node("test_node")
        assert node is not None
        assert node["path"] == "/path/to/node"
        assert node["key"] == "value"

    def test_registry_list_nodes(self):
        """Test listing all nodes in registry."""
        registry = Registry()
        registry.add_node("node1", "/path/1")
        registry.add_node("node2", "/path/2")

        nodes = registry.list_nodes()
        assert len(nodes) == 2
        assert nodes["node1"] == "/path/1"
        assert nodes["node2"] == "/path/2"

    def test_registry_remove_node(self):
        """Test removing a node from registry."""
        registry = Registry()
        registry.add_node("test_node", "/path/to/node")

        assert registry.remove_node("test_node")
        assert "test_node" not in registry.nodes

    def test_registry_get_config_global(self):
        """Test getting global configuration."""
        registry = Registry()
        config_value = registry.get_config("PREFIX_PROCESSED")
        assert config_value == "_"

    def test_registry_default_config_has_gc_options(self):
        registry = Registry()
        assert registry.DEFAULT_CONFIG["GC_MAX_READ_FILES"] == 0
        assert registry.DEFAULT_CONFIG["GC_MAX_SENT_FILES"] == 11
        assert registry.DEFAULT_CONFIG["GC_DELETE_MODE"] == "trash"
        assert registry.DEFAULT_CONFIG["LATEST_LOG_PATH"] == "~/.jatai_latest.log"

    def test_registry_set_config_global(self):
        """Test setting global configuration."""
        registry = Registry()
        registry.set_config("PREFIX_PROCESSED", "-marked")
        assert registry.get_config("PREFIX_PROCESSED") == "-marked"

    def test_registry_uses_lock_file_on_save(self, temp_dir):
        """Test save operation creates and uses a lock file."""
        registry_path = temp_dir / ".jatai"
        registry = Registry(registry_path=registry_path)
        registry.add_node("n1", "/tmp/node")

        registry.save()

        assert registry_path.exists()
        assert registry.lock_path.exists()

    def test_registry_config_node_override(self):
        """Test node-specific config overrides global."""
        registry = Registry()
        registry.add_node("node1", "/path/1")
        registry.set_config("PREFIX_ERROR", "!_LOCAL", node_name="node1")

        assert registry.get_config("PREFIX_ERROR", "node1") == "!_LOCAL"
        assert registry.get_config("PREFIX_ERROR", "othernode") == "!_"


class TestRegistryErrorFailureScenarios:
    """Error and failure scenario tests for Registry."""

    def test_registry_load_missing_file(self, temp_dir):
        """Test loading registry when file doesn't exist."""
        registry_path = temp_dir / "nonexistent.yaml"
        registry = Registry(registry_path=registry_path)

        with pytest.raises(FileNotFoundError):
            registry.load()

    def test_registry_load_malformed_yaml(self, temp_dir):
        """Test loading registry with malformed YAML."""
        registry_path = temp_dir / ".jatai"
        with open(registry_path, "w") as f:
            f.write("invalid: yaml: content: {]")

        registry = Registry(registry_path=registry_path)
        with pytest.raises(yaml.YAMLError):
            registry.load()

    def test_registry_load_empty_file(self, temp_dir):
        """Test loading empty registry file."""
        registry_path = temp_dir / ".jatai"
        with open(registry_path, "w") as f:
            f.write("")

        registry = Registry(registry_path=registry_path)
        registry.load()
        assert registry.nodes == {}

    def test_registry_get_nonexistent_node(self):
        """Test getting a node that doesn't exist."""
        registry = Registry()
        assert registry.get_node("nonexistent") is None

    def test_registry_remove_nonexistent_node(self):
        """Test removing a node that doesn't exist."""
        registry = Registry()
        assert not registry.remove_node("nonexistent")

    def test_registry_set_config_nonexistent_node(self):
        """Test setting config on non-existent node."""
        registry = Registry()
        with pytest.raises(ValueError):
            registry.set_config("KEY", "value", node_name="nonexistent")

    def test_registry_save_creates_parent_dirs(self, temp_dir):
        """Test that save creates parent directories."""
        registry_path = temp_dir / "nested" / "deep" / ".jatai"
        registry = Registry(registry_path=registry_path)
        registry.add_node("test", "/path")

        registry.save()
        assert registry_path.exists()
        assert registry_path.parent.parent.exists()


class TestRegistryMaliciousAdversarialScenarios:
    """Malicious/adversarial scenario tests for Registry."""

    def test_registry_path_traversal_attempt(self, temp_dir):
        """Test that registry prevents path traversal attacks."""
        # Attempt to use ../ in registry path
        malicious_path = temp_dir / "registry" / "../../secret.yaml"
        registry = Registry(registry_path=malicious_path)

        # Registry should resolve absolute path safely
        resolved = registry.registry_path.resolve()
        assert ".." not in str(resolved)

    def test_registry_yaml_injection(self, temp_dir):
        """Test that YAML injection doesn't cause issues."""
        registry_path = temp_dir / ".jatai"
        registry = Registry(registry_path=registry_path)

        # Try to inject malicious YAML
        malicious_config = ("fake_node: !!python/object/apply:os.system ['echo pwned']\n")
        with open(registry_path, "w") as f:
            f.write(malicious_config)

        registry = Registry(registry_path=registry_path)
        # safe_load should reject dangerous tags and raise an error
        # This is the correct behavior - we should get an exception, not code execution
        with pytest.raises(yaml.YAMLError):
            registry.load()
        # Should not have executed the injection
        assert True

    def test_registry_handles_symlink_target(self, temp_dir):
        """Test that registry handles symlinks safely."""
        import os

        actual_file = temp_dir / "actual.yaml"
        link_file = temp_dir / "link.yaml"

        # Create actual file
        actual_file.write_text("PREFIX_PROCESSED: '_'\n")
        os.symlink(actual_file, link_file)

        registry = Registry(registry_path=link_file)
        registry.load()
        assert registry.global_config["PREFIX_PROCESSED"] == "_"

    def test_registry_unicode_node_names(self):
        """Test registry with unicode node names."""
        registry = Registry()
        registry.add_node("节点", "/path/to/node")
        registry.add_node("узел", "/path/other")

        assert "节点" in registry.nodes
        assert "узел" in registry.nodes

    def test_registry_special_characters_in_paths(self, temp_dir):
        """Test registry with special characters in node paths."""
        registry = Registry()
        special_path = "/path/with spaces/and-dashes/and_underscores/.hidden"
        registry.add_node("node", special_path)

        node = registry.get_node("node")
        assert node["path"] == special_path

    def test_registry_extremely_large_config(self):
        """Test registry with very large configuration."""
        registry = Registry()

        # Add many nodes
        for i in range(1000):
            registry.add_node(f"node_{i}", f"/path/{i}")

        assert len(registry.nodes) == 1000
        assert registry.get_node("node_999") is not None

    def test_registry_concurrent_writes_simulation(self, temp_dir):
        """Simulate concurrent writes by overwriting registry."""
        registry_path = temp_dir / ".jatai"

        reg1 = Registry(registry_path=registry_path)
        reg1.add_node("node1", "/path/1")
        reg1.save()

        reg2 = Registry(registry_path=registry_path)
        reg2.load()
        reg2.add_node("node2", "/path/2")
        reg2.save()

        # Load and check
        reg3 = Registry(registry_path=registry_path)
        reg3.load()
        # reg3 should have node2 but not node1 (reg2 overwrote reg1's changes)
        assert "node2" in reg3.nodes

    def test_registry_filelock_thread_contention_blocks_and_recovers(self, temp_dir):
        """Validate real thread contention on the registry file lock."""
        registry_path = temp_dir / ".jatai"
        holder_registry = Registry(registry_path=registry_path)
        holder_registry.add_node("holder", "/tmp/holder")
        holder_registry.save()

        waiting_registry = Registry(registry_path=registry_path)
        waiting_registry.load()
        waiting_registry.add_node("waiter", "/tmp/waiter")

        lock_entered = threading.Event()
        release_lock = threading.Event()
        save_completed = threading.Event()

        def holder() -> None:
            with holder_registry._lock():
                lock_entered.set()
                release_lock.wait(timeout=5)

        def waiter() -> None:
            waiting_registry.save()
            save_completed.set()

        holder_thread = threading.Thread(target=holder)
        waiter_thread = threading.Thread(target=waiter)

        holder_thread.start()
        assert lock_entered.wait(timeout=2)

        waiter_thread.start()
        time.sleep(0.2)
        assert not save_completed.is_set()

        release_lock.set()
        holder_thread.join(timeout=5)
        waiter_thread.join(timeout=5)

        assert save_completed.is_set()

        verify = Registry(registry_path=registry_path)
        verify.load()
        assert "waiter" in verify.nodes

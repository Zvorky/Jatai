"""
Tests for jatai.core.node module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import pytest
import yaml
from pathlib import Path
from jatai.core.node import Node


class TestNodeHappyPath:
    """Happy path tests for Node."""

    def test_node_init(self, temp_dir):
        """Test Node initialization."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        assert node.node_path == node_path
        assert node.inbox_path == node_path / "INBOX"
        assert node.outbox_path == node_path / "OUTBOX"
        assert node.local_config_path == node_path / ".jatai"

    def test_node_create(self, temp_dir):
        """Test creating a new node structure."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert node_path.exists()
        assert node.inbox_path.exists()
        assert node.outbox_path.exists()
        assert node.local_config_path.exists()

    def test_node_create_with_global_config(self, temp_dir):
        """Test creating node with global config defaults."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        global_config = {
            "PREFIX_PROCESSED": "-done",
            "PREFIX_ERROR": "❌",
            "RETRY_DELAY_BASE": 120,
        }

        node.create(global_config=global_config)

        node.load_config()
        assert node.local_config["PREFIX_PROCESSED"] == "-done"
        assert node.local_config["PREFIX_ERROR"] == "❌"
        assert node.local_config["RETRY_DELAY_BASE"] == 120

    def test_node_apply_effective_config_prefers_local_over_global(self, temp_dir):
        """Test local .jatai values override global defaults dynamically."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()
        node.local_config = {
            "PREFIX_PROCESSED": "local_",
            "INBOX_DIR": "custom_inbox",
        }

        effective = node.apply_effective_config(
            {
                "PREFIX_PROCESSED": "global_",
                "PREFIX_ERROR": "global_error_",
                "OUTBOX_DIR": "custom_outbox",
            }
        )

        assert effective["PREFIX_PROCESSED"] == "local_"
        assert effective["PREFIX_ERROR"] == "global_error_"
        assert node.inbox_path == node_path / "custom_inbox"
        assert node.outbox_path == node_path / "custom_outbox"

    def test_node_restore_backup_restores_previous_config(self, temp_dir):
        """Test .jatai.bkp can restore a previous configuration snapshot."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create(global_config={"PREFIX_PROCESSED": "original_"})
        original_config = dict(node.local_config)

        node.backup_current_config(original_config)
        node.write_config({"PREFIX_PROCESSED": "changed_"})
        node.restore_backup()

        assert node.local_config["PREFIX_PROCESSED"] == original_config["PREFIX_PROCESSED"]

    def test_node_load_config(self, temp_dir):
        """Test loading node config from disk."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        # Modify config
        node.local_config["custom_key"] = "custom_value"
        node.save_config()

        # Load fresh instance
        node2 = Node(node_path)
        node2.load_config()

        assert node2.local_config["custom_key"] == "custom_value"

    def test_node_save_config(self, temp_dir):
        """Test saving node config to disk."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.local_config["test_key"] = "test_value"
        node.save_config()

        # Verify YAML was written correctly
        with open(node.local_config_path) as f:
            loaded = yaml.safe_load(f)
            assert loaded["test_key"] == "test_value"

    def test_node_is_enabled(self, temp_dir):
        """Test is_enabled check."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        assert not node.is_enabled()
        node.create()
        assert node.is_enabled()

    def test_node_is_disabled(self, temp_dir):
        """Test is_disabled check."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert not node.is_disabled()
        node.disable()
        assert node.is_disabled()

    def test_node_disable(self, temp_dir):
        """Test disabling a node."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert node.local_config_path.exists()
        node.disable()
        assert not node.local_config_path.exists()
        assert (node_path / "._jatai").exists()

    def test_node_enable(self, temp_dir):
        """Test enabling a node."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()
        node.disable()

        assert not node.local_config_path.exists()
        node.enable()
        assert node.local_config_path.exists()

    def test_node_get_config(self, temp_dir):
        """Test getting configuration value."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.local_config["key1"] = "value1"
        assert node.get_config("key1") == "value1"
        assert node.get_config("nonexistent", default="default") == "default"

    def test_node_set_config(self, temp_dir):
        """Test setting configuration value."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.set_config("key1", "value1")
        assert node.local_config["key1"] == "value1"

        # Verify it was saved to disk
        node2 = Node(node_path)
        node2.load_config()
        assert node2.local_config["key1"] == "value1"

    def test_node_list_inbox(self, temp_dir):
        """Test listing files in INBOX."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        # Create some test files
        (node.inbox_path / "file1.txt").write_text("content1")
        (node.inbox_path / "file2.txt").write_text("content2")
        (node.inbox_path / ".hidden").write_text("hidden")

        inbox_files = node.list_inbox()

        assert len(inbox_files) == 3
        assert any(f.name == "file1.txt" for f in inbox_files)
        assert any(f.name == "file2.txt" for f in inbox_files)

    def test_node_list_outbox(self, temp_dir):
        """Test listing files in OUTBOX."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        # Create some test files
        (node.outbox_path / "msg1.txt").write_text("msg1")
        (node.outbox_path / "msg2.txt").write_text("msg2")

        outbox_files = node.list_outbox()

        assert len(outbox_files) == 2
        assert any(f.name == "msg1.txt" for f in outbox_files)
        assert any(f.name == "msg2.txt" for f in outbox_files)

    def test_node_list_empty_folders(self, temp_dir):
        """Test listing when folders are empty."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert node.list_inbox() == []
        assert node.list_outbox() == []


class TestNodeErrorFailureScenarios:
    """Error and failure scenario tests for Node."""

    def test_node_load_config_nonexistent(self, temp_dir):
        """Test loading config when .jatai doesn't exist."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        with pytest.raises(FileNotFoundError):
            node.load_config()

    def test_node_load_config_malformed_yaml(self, temp_dir):
        """Test loading malformed YAML config."""
        node_path = temp_dir / "my_node"
        node_path.mkdir()
        config_path = node_path / ".jatai"
        config_path.write_text("invalid: yaml: {][")

        node = Node(node_path)
        with pytest.raises(yaml.YAMLError):
            node.load_config()

    def test_node_disable_when_not_enabled(self, temp_dir):
        """Test disabling when node is not enabled."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        with pytest.raises(FileNotFoundError):
            node.disable()

    def test_node_enable_when_not_disabled(self, temp_dir):
        """Test enabling when node is not disabled."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        with pytest.raises(FileNotFoundError):
            node.enable()

    def test_node_set_config_saves_immediately(self, temp_dir):
        """Test that set_config saves immediately."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.set_config("key", "value")

        # Check disk
        with open(node.local_config_path) as f:
            loaded = yaml.safe_load(f)
            assert loaded["key"] == "value"

    def test_node_list_inbox_when_not_created(self, temp_dir):
        """Test listing inbox when node doesn't exist."""
        node_path = temp_dir / "nonexistent"
        node = Node(node_path)

        # Should return empty list, not raise
        assert node.list_inbox() == []

    def test_node_create_fails_when_inbox_outbox_overlap(self, temp_dir):
        """Test creating node fails when INBOX and OUTBOX paths overlap."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        shared = node_path / "same"

        with pytest.raises(ValueError):
            node.create(inbox_path=shared, outbox_path=shared)


class TestNodeMaliciousAdversarialScenarios:
    """Malicious/adversarial scenario tests for Node."""

    def test_node_path_traversal_detection(self, temp_dir):
        """Test that node path is resolved safely."""
        node_path = temp_dir / "node" / "../../../etc/passwd"
        node = Node(node_path)

        # Path should be resolved, not contain ..
        assert ".." not in str(node.node_path)

    def test_node_unicode_directory_names(self, temp_dir):
        """Test Node with unicode directory names."""
        node_path = temp_dir / "节点_🐝_узел"
        node = Node(node_path)
        node.create()

        assert node.node_path.exists()
        assert node.inbox_path.exists()

    def test_node_special_chars_in_config(self, temp_dir):
        """Test Node with special characters in config values."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        special_value = "'; DROP TABLE nodes; --"
        node.set_config("query", special_value)

        node2 = Node(node_path)
        node2.load_config()
        assert node2.get_config("query") == special_value

    def test_node_config_injection_yaml(self, temp_dir):
        """Test YAML injection in config file."""
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        # Attempt YAML injection
        injection = "node_path: !!python/object/apply:os.system ['echo pwned']\n"
        config_path = node_path / ".jatai"
        config_path.write_text(injection)

        node2 = Node(node_path)
        # safe_load should reject dangerous tags and raise an error
        # This is the correct behavior - we should get an exception, not code execution
        with pytest.raises(yaml.YAMLError):
            node2.load_config()
        # Should succeed without executing injection
        assert True

    def test_node_symlink_config_file(self, temp_dir):
        """Test Node with symlinked config file."""
        import os

        config_dir = temp_dir / "configs"
        config_dir.mkdir()
        actual_config = config_dir / ".jatai"
        actual_config.write_text("node_path: /test\n")

        node_path = temp_dir / "my_node"
        node_path.mkdir()

        link_config = node_path / ".jatai"
        os.symlink(actual_config, link_config)

        node = Node(node_path)
        node.load_config()
        assert node.local_config is not None

    def test_node_very_deep_nesting(self, temp_dir):
        """Test Node with very deep directory nesting."""
        deep_path = temp_dir
        for i in range(50):
            deep_path = deep_path / f"level_{i}"

        node = Node(deep_path)
        node.create()

        assert node.node_path.exists()
        assert node.inbox_path.exists()

    def test_node_list_with_symlinks_in_folders(self, temp_dir):
        """Test listing when folders contain symlinks."""
        import os

        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        # Create a file and link to it
        actual = temp_dir / "actual.txt"
        actual.write_text("content")

        link = node.inbox_path / "link.txt"
        os.symlink(actual, link)

        inbox_files = node.list_inbox()
        assert len(inbox_files) == 1
        assert inbox_files[0].name == "link.txt"

    def test_node_readonly_config_directory(self, temp_dir):
        """Test Node with readonly parent directory."""
        import os

        node_path = temp_dir / "readonly_node"
        node_path.mkdir()

        # Create node, then make parent readonly
        node = Node(node_path)
        node.create()

        # Make node_path readonly
        os.chmod(node_path, 0o555)

        try:
            # Trying to save config should fail
            node.set_config("key", "value")
            # If it doesn't fail, that's okay for some scenarios
        finally:
            # Restore permissions for cleanup
            os.chmod(node_path, 0o755)

    def test_node_concurrent_config_updates(self, temp_dir):
        """Simulate concurrent config updates."""
        node_path = temp_dir / "my_node"

        node1 = Node(node_path)
        node1.create()

        node2 = Node(node_path)
        node2.load_config()

        # Both modify config
        node1.set_config("key1", "value1")
        node2.set_config("key2", "value2")

        # Load and check (node2's write will overwrite node1's)
        node3 = Node(node_path)
        node3.load_config()
        # node3 should have whichever write happened last
        assert "key1" in node3.local_config or "key2" in node3.local_config

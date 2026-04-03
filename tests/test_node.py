"""
Tests for jatai.core.node module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import pytest
import threading
import time
import yaml
from pathlib import Path
from filelock import Timeout
from jatai.core.node import Node


class TestNodeHappyPath:
    """Happy path tests for Node."""

    def test_node_init(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        assert node.node_path == node_path
        assert node.inbox_path == node_path / "INBOX"
        assert node.outbox_path == node_path / "OUTBOX"
        assert node.local_config_path == node_path / ".jatai"

    def test_node_create(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert node_path.exists()
        assert node.inbox_path.exists()
        assert node.outbox_path.exists()
        assert node.local_config_path.exists()

    def test_node_create_with_global_config(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        global_config = {
            "PREFIX_IGNORE": "-done",
            "PREFIX_ERROR": "❌",
            "RETRY_DELAY_BASE": 120,
            "GC_AUTO_DELETE_MODE": "permanent",
        }

        node.create(global_config=global_config)

        node.load_config()
        assert node.local_config["PREFIX_IGNORE"] == "-done"
        assert node.local_config["PREFIX_ERROR"] == "❌"
        assert node.local_config["RETRY_DELAY_BASE"] == 120
        assert node.local_config["GC_AUTO_DELETE_MODE"] == "permanent"

    def test_node_apply_effective_config_prefers_local_over_global(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()
        node.local_config = {
            "PREFIX_IGNORE": "local_",
            "INBOX_DIR": "custom_inbox",
        }

        effective = node.apply_effective_config(
            {
                "PREFIX_IGNORE": "global_",
                "PREFIX_ERROR": "global_error_",
                "OUTBOX_DIR": "custom_outbox",
            }
        )

        assert effective["PREFIX_IGNORE"] == "local_"
        assert effective["PREFIX_ERROR"] == "global_error_"
        assert node.inbox_path == node_path / "custom_inbox"
        assert node.outbox_path == node_path / "custom_outbox"

    def test_node_restore_backup_restores_previous_config(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create(global_config={"PREFIX_IGNORE": "original_"})
        original_config = dict(node.local_config)

        node.backup_current_config(original_config)
        node.write_config({"PREFIX_IGNORE": "changed_"})
        node.restore_backup()

        assert node.local_config["PREFIX_IGNORE"] == original_config["PREFIX_IGNORE"]

    def test_node_load_config(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.local_config["custom_key"] = "custom_value"
        node.save_config()

        node2 = Node(node_path)
        node2.load_config()

        assert node2.local_config["custom_key"] == "custom_value"

    def test_node_save_config(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.local_config["test_key"] = "test_value"
        node.save_config()

        with open(node.local_config_path) as f:
            loaded = yaml.safe_load(f)
            assert loaded["test_key"] == "test_value"

    def test_node_is_enabled(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)

        assert not node.is_enabled()
        node.create()
        assert node.is_enabled()

    def test_node_is_disabled(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert not node.is_disabled()
        node.disable()
        assert node.is_disabled()

    def test_node_disable(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert node.local_config_path.exists()
        node.disable()
        assert not node.local_config_path.exists()
        assert (node_path / "._jatai").exists()

    def test_node_enable(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()
        node.disable()

        assert not node.local_config_path.exists()
        node.enable()
        assert node.local_config_path.exists()

    def test_node_get_config(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.local_config["key1"] = "value1"
        assert node.get_config("key1") == "value1"
        assert node.get_config("nonexistent", default="default") == "default"

    def test_node_set_config(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        node.set_config("key1", "value1")
        assert node.local_config["key1"] == "value1"

        node2 = Node(node_path)
        node2.load_config()
        assert node2.local_config["key1"] == "value1"

    def test_node_list_inbox(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        (node.inbox_path / "file1.txt").write_text("content1")
        (node.inbox_path / "file2.txt").write_text("content2")
        (node.inbox_path / ".hidden").write_text("hidden")

        inbox_files = node.list_inbox()

        assert len(inbox_files) == 3
        assert any(f.name == "file1.txt" for f in inbox_files)
        assert any(f.name == "file2.txt" for f in inbox_files)

    def test_node_list_outbox(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        (node.outbox_path / "msg1.txt").write_text("msg1")
        (node.outbox_path / "msg2.txt").write_text("msg2")

        outbox_files = node.list_outbox()

        assert len(outbox_files) == 2
        assert any(f.name == "msg1.txt" for f in outbox_files)
        assert any(f.name == "msg2.txt" for f in outbox_files)

    def test_node_list_empty_folders(self, temp_dir):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        assert node.list_inbox() == []
        assert node.list_outbox() == []

    def test_node_save_config_uses_lock(self, temp_dir, monkeypatch):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        class DummyLock:
            def __enter__(self):
                raise Timeout("lock timeout")

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr("jatai.core.node.FileLock", lambda path, timeout: DummyLock())

        node.local_config["test_key"] = "test_value"
        with pytest.raises(Timeout):
            node.save_config()

    def test_node_load_config_uses_lock(self, temp_dir, monkeypatch):
        node_path = temp_dir / "my_node"
        node = Node(node_path)
        node.create()

        class DummyLock:
            def __enter__(self):
                raise Timeout("lock timeout")

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr("jatai.core.node.FileLock", lambda path, timeout: DummyLock())

        with pytest.raises(Timeout):
            node.load_config()

    def test_node_filelock_thread_contention_blocks_and_recovers(self, temp_dir):
        """Local .jatai access must serialize concurrent readers/writers via filelock."""
        node_path = temp_dir / "contention_node"
        node = Node(node_path)
        node.create()
        node.set_config("initial", "value")

        waiting_node = Node(node_path)

        lock_entered = threading.Event()
        release_lock = threading.Event()
        operation_completed = threading.Event()

        def holder() -> None:
            with node._lock():
                lock_entered.set()
                release_lock.wait(timeout=5)

        def waiter() -> None:
            waiting_node.load_config()
            waiting_node.local_config["thread_key"] = "thread_value"
            waiting_node.save_config()
            operation_completed.set()

        holder_thread = threading.Thread(target=holder)
        waiter_thread = threading.Thread(target=waiter)

        holder_thread.start()
        assert lock_entered.wait(timeout=2)

        waiter_thread.start()
        time.sleep(0.2)
        assert not operation_completed.is_set()

        release_lock.set()
        holder_thread.join(timeout=5)
        waiter_thread.join(timeout=5)

        assert operation_completed.is_set()

        verifier = Node(node_path)
        verifier.load_config()
        assert verifier.local_config["thread_key"] == "thread_value"

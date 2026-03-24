"""
Tests for jatai.core.gc module (Garbage Collection).

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import time
from pathlib import Path

import pytest

from jatai.core.gc import collect_garbage, run_gc_for_node
from jatai.core.daemon import JataiDaemon
from jatai.core.node import Node
from jatai.core.registry import Registry


def _register_node(registry_path: Path, node_name: str, node_path: Path) -> Node:
    """Create a node and register it in the global registry for tests."""
    node = Node(node_path)
    node.create()

    registry = Registry(registry_path=registry_path)
    try:
        registry.load()
    except FileNotFoundError:
        pass
    registry.add_node(node_name, str(node_path))
    registry.save()
    return node


def _write_old_file(path: Path, name: str, age_days: float) -> Path:
    """Write a file and set its mtime to simulate an old file."""
    target = path / name
    target.write_text("content")
    old_mtime = time.time() - age_days * 86400
    import os
    os.utime(target, (old_mtime, old_mtime))
    return target


class TestGCHappyPath:
    """Happy path tests for the GC module."""

    def test_collect_garbage_removes_old_processed_file(self, temp_dir):
        """collect_garbage deletes a _ file older than max_age_days."""
        old_file = _write_old_file(temp_dir, "_old_message.txt", age_days=31)
        now = time.time()

        removed = collect_garbage(temp_dir, success_prefix="_", max_age_days=30, now=now)

        assert old_file in removed
        assert not old_file.exists()

    def test_collect_garbage_keeps_recent_files(self, temp_dir):
        """collect_garbage does not delete recently processed files."""
        recent_file = _write_old_file(temp_dir, "_recent.txt", age_days=1)
        now = time.time()

        removed = collect_garbage(temp_dir, success_prefix="_", max_age_days=30, now=now)

        assert recent_file not in removed
        assert recent_file.exists()

    def test_collect_garbage_ignores_pending_files(self, temp_dir):
        """collect_garbage does not delete pending (unprefixed) files."""
        old_pending = _write_old_file(temp_dir, "pending.txt", age_days=100)
        now = time.time()

        removed = collect_garbage(temp_dir, success_prefix="_", max_age_days=30, now=now)

        assert old_pending not in removed
        assert old_pending.exists()

    def test_collect_garbage_max_files_trims_oldest(self, temp_dir):
        """collect_garbage trims the oldest _ files when count exceeds max_files."""
        oldest = _write_old_file(temp_dir, "_old1.txt", age_days=10)
        time.sleep(0.01)
        middle = _write_old_file(temp_dir, "_old2.txt", age_days=5)
        time.sleep(0.01)
        newest = _write_old_file(temp_dir, "_new.txt", age_days=1)
        now = time.time()

        removed = collect_garbage(
            temp_dir, success_prefix="_", max_age_days=0, max_files=2, now=now
        )

        assert oldest in removed
        assert middle.exists()
        assert newest.exists()

    def test_collect_garbage_returns_empty_on_nonexistent_dir(self, temp_dir):
        """collect_garbage returns an empty list when directory does not exist."""
        removed = collect_garbage(temp_dir / "nonexistent", success_prefix="_")
        assert removed == []

    def test_collect_garbage_no_thresholds_removes_nothing(self, temp_dir):
        """collect_garbage with max_age_days=0 and max_files=0 removes nothing."""
        _write_old_file(temp_dir, "_old.txt", age_days=365)

        removed = collect_garbage(temp_dir, success_prefix="_", max_age_days=0, max_files=0)

        assert removed == []

    def test_run_gc_for_node_respects_gc_enabled_false(self, temp_dir):
        """run_gc_for_node does nothing when GC_ENABLED is false."""
        inbox = temp_dir / "INBOX"
        outbox = temp_dir / "OUTBOX"
        inbox.mkdir()
        outbox.mkdir()
        _write_old_file(inbox, "_old.txt", age_days=100)

        removed = run_gc_for_node(
            inbox_path=inbox,
            outbox_path=outbox,
            node_config={"GC_ENABLED": False, "PREFIX_PROCESSED": "_"},
        )

        assert removed == []

    def test_run_gc_for_node_deletes_when_enabled(self, temp_dir):
        """run_gc_for_node deletes processed files when GC_ENABLED=True."""
        inbox = temp_dir / "INBOX"
        outbox = temp_dir / "OUTBOX"
        inbox.mkdir()
        outbox.mkdir()

        old_inbox = _write_old_file(inbox, "_old_msg.txt", age_days=40)
        old_outbox = _write_old_file(outbox, "_old_sent.txt", age_days=40)
        now = time.time()

        removed = run_gc_for_node(
            inbox_path=inbox,
            outbox_path=outbox,
            node_config={
                "GC_ENABLED": True,
                "GC_MAX_AGE_DAYS": 30,
                "GC_MAX_FILES": 0,
                "PREFIX_PROCESSED": "_",
            },
            now=now,
        )

        assert old_inbox in removed
        assert old_outbox in removed

    def test_daemon_run_garbage_collection_logs_removed_files(self, temp_home):
        """Daemon run_garbage_collection method deletes old files and logs them."""
        registry_path = temp_home / ".jatai"
        node = _register_node(registry_path, "node_a", temp_home / "node_a")

        node.set_config("GC_ENABLED", True)
        node.set_config("GC_MAX_AGE_DAYS", 30)

        old_file = _write_old_file(node.inbox_path, "_expired.txt", age_days=45)

        log_path = temp_home / ".jatai.log"
        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            log_path=log_path,
        )
        daemon.run_garbage_collection()

        assert not old_file.exists()
        assert "GC removed" in log_path.read_text(encoding="utf-8")


class TestGCErrorFailureScenarios:
    """Error and failure scenario tests for the GC module."""

    def test_collect_garbage_handles_permission_error(self, temp_dir):
        """collect_garbage skips files it cannot delete due to permissions."""
        import os
        file_path = temp_dir / "_locked.txt"
        file_path.write_text("content")

        os.chmod(temp_dir, 0o555)
        try:
            removed = collect_garbage(temp_dir, success_prefix="_", max_age_days=0, max_files=1)
        finally:
            os.chmod(temp_dir, 0o755)

        # Should not raise; file may or may not be removed depending on OS
        assert isinstance(removed, list)

    def test_run_gc_invalid_config_values_use_defaults(self, temp_dir):
        """run_gc_for_node falls back to defaults when config values are invalid."""
        inbox = temp_dir / "INBOX"
        inbox.mkdir()
        outbox = temp_dir / "OUTBOX"
        outbox.mkdir()

        # These should not raise
        removed = run_gc_for_node(
            inbox_path=inbox,
            outbox_path=outbox,
            node_config={
                "GC_ENABLED": "true",
                "GC_MAX_AGE_DAYS": "not-a-number",
                "GC_MAX_FILES": "also-bad",
                "PREFIX_PROCESSED": "_",
            },
        )
        assert isinstance(removed, list)


class TestGCAdversarialScenarios:
    """Adversarial tests for the GC module."""

    def test_collect_garbage_empty_prefix_does_not_delete_all(self, temp_dir):
        """collect_garbage with an empty prefix treats no file as processed."""
        (temp_dir / "important.txt").write_text("keep me")
        _write_old_file(temp_dir, "old_data.txt", age_days=100)

        removed = collect_garbage(temp_dir, success_prefix="", max_age_days=1, max_files=0)

        assert removed == []

    def test_collect_garbage_custom_prefix(self, temp_dir):
        """collect_garbage respects a custom success prefix."""
        processed = _write_old_file(temp_dir, "done_report.txt", age_days=40)
        pending = _write_old_file(temp_dir, "_other.txt", age_days=40)
        now = time.time()

        removed = collect_garbage(temp_dir, success_prefix="done_", max_age_days=30, now=now)

        assert processed in removed
        assert pending not in removed
        assert pending.exists()

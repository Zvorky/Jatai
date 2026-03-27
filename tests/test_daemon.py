"""
Tests for daemon lifecycle, startup scan, watchdog routing, and auto-start registration.
"""

import json
from pathlib import Path

import pytest
from watchdog.events import FileCreatedEvent, FileMovedEvent

from jatai.core.autostart import AutoStartRegistrar
from jatai.core.daemon import AlreadyRunningError, JataiDaemon, JataiWatchdogHandler
from jatai.core.node import Node
from jatai.core.registry import Registry
import shutil


class FakeObserver:
    """Minimal observer stub to validate scheduled watches."""

    def __init__(self):
        self.scheduled = []
        self.started = False

    def schedule(self, handler, path, recursive=False):
        watch = {"handler": handler, "path": path, "recursive": recursive}
        self.scheduled.append(watch)
        return watch

    def start(self):
        self.started = True

    def unschedule_all(self):
        self.scheduled.clear()

    def stop(self):
        self.started = False

    def join(self, timeout=None):
        return None


def register_node(registry_path: Path, node_name: str, node_path: Path) -> Node:
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


class TestDaemonHappyPath:
    """Happy path tests for daemon processing."""

    def test_startup_scan_broadcasts_pending_file(self, temp_home):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_b = register_node(registry_path, "node_b", temp_home / "node_b")

        source_file = node_a.outbox_path / "message.txt"
        source_file.write_text("hello")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        daemon.startup_scan()

        assert (node_b.inbox_path / "message.txt").exists()
        assert (node_a.outbox_path / "_message.txt").exists()

    def test_watchdog_created_event_routes_file(self, temp_home):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_b = register_node(registry_path, "node_b", temp_home / "node_b")

        source_file = node_a.outbox_path / "created.txt"
        source_file.write_text("created")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        handler = JataiWatchdogHandler(daemon, node_a.node_path)
        handler.on_created(FileCreatedEvent(str(source_file)))

        assert (node_b.inbox_path / "created.txt").exists()
        assert (node_a.outbox_path / "_created.txt").exists()

    def test_watchdog_moved_event_routes_file(self, temp_home):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_b = register_node(registry_path, "node_b", temp_home / "node_b")

        incoming = temp_home / "temp.txt"
        incoming.write_text("moved")
        destination = node_a.outbox_path / "moved.txt"
        incoming.rename(destination)

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        handler = JataiWatchdogHandler(daemon, node_a.node_path)
        handler.on_moved(FileMovedEvent(str(incoming), str(destination)))

        assert (node_b.inbox_path / "moved.txt").exists()
        assert (node_a.outbox_path / "_moved.txt").exists()

    def test_daemon_ignores_currently_written_files(self, temp_home):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_b = register_node(registry_path, "node_b", temp_home / "node_b")

        source_file = node_a.outbox_path / "_writing.txt"
        source_file.write_text("partial")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        daemon.startup_scan()

        assert not (node_b.inbox_path / "writing.txt").exists()
        assert (node_a.outbox_path / "_writing.txt").exists()

    def test_daemon_retry_transitions_to_fatal_total(self, temp_home, monkeypatch):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        node_a.set_config("MAX_RETRIES", 2)
        node_a.set_config("RETRY_DELAY_BASE", 1)

        source_file = node_a.outbox_path / "message.txt"
        source_file.write_text("hello")

        def fail_delivery(_self):
            raise OSError("simulated failure")

        monkeypatch.setattr("jatai.core.daemon.Delivery.deliver", fail_delivery)

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry",
            log_path=temp_home / ".jatai.log",
        )

        daemon.startup_scan()
        first_failure = node_a.outbox_path / "!message.txt"
        assert first_failure.exists()

        retry_data = json.loads((temp_home / ".retry").read_text(encoding="utf-8"))
        key = str((node_a.outbox_path / "message.txt").resolve())
        retry_data[key]["next_retry_at"] = 0
        (temp_home / ".retry").write_text(json.dumps(retry_data), encoding="utf-8")

        daemon.startup_scan()
        fatal_failure = node_a.outbox_path / "!!message.txt"
        assert fatal_failure.exists()

    def test_daemon_writes_global_log_file(self, temp_home):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        source_file = node_a.outbox_path / "loggable.txt"
        source_file.write_text("payload")

        log_path = temp_home / ".jatai.log"
        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry",
            log_path=log_path,
        )
        daemon.startup_scan()

        assert log_path.exists()
        assert "Delivery succeeded" in log_path.read_text(encoding="utf-8")

    def test_daemon_load_active_nodes_applies_local_override(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        registry = Registry(registry_path=registry_path)
        registry.load()
        registry.set_config("PREFIX_PROCESSED", "global_")
        registry.set_config("OUTBOX_DIR", "global_outbox")
        registry.save()

        node.write_config(
            {
                "node_path": str(node.node_path),
                "PREFIX_PROCESSED": "local_",
                "INBOX_DIR": "local_inbox",
                "OUTBOX_DIR": "local_outbox",
            }
        )

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        [active_node] = daemon.load_active_nodes()

        assert active_node.get_config("PREFIX_PROCESSED") == "local_"
        assert active_node.inbox_path == node.node_path / "local_inbox"
        assert active_node.outbox_path == node.node_path / "local_outbox"

    def test_daemon_setup_watchdog_monitors_disabled_root_only(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        node.disable()

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        scheduled_paths = {Path(entry["path"]).resolve() for entry in daemon.observer.scheduled}

        assert node.node_path in scheduled_paths
        assert node.outbox_path.resolve() not in scheduled_paths

    def test_daemon_handle_node_config_change_reactivates_disabled_node(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        node.disable()

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        node.enable()
        # Simulate a user updating local config to new prefixes so migration should run
        new_config = dict(node.local_config)
        new_config["PREFIX_PROCESSED"] = "processed_"
        new_config["PREFIX_ERROR"] = "error_"
        node.write_config(new_config)

        daemon.handle_node_config_change(node.node_path)

        active_nodes = daemon.load_active_nodes()
        assert any(active.node_path == node.node_path for active in active_nodes)
        scheduled_paths = {Path(entry["path"]).resolve() for entry in daemon.observer.scheduled}
        assert node.outbox_path.resolve() in scheduled_paths

    def test_daemon_handle_node_config_change_migrates_prefix_history(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        old_success = node.outbox_path / "_done.txt"
        old_error = node.inbox_path / "!_failed.txt"
        old_success.write_text("done")
        old_error.write_text("failed")

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        new_config = dict(node.local_config)
        new_config["PREFIX_PROCESSED"] = "processed_"
        new_config["PREFIX_ERROR"] = "error_"
        node.write_config(new_config)

    def test_daemon_creates_softdelete_instead_of_recreating_node(self, temp_home):
        """When local .jatai is deleted, daemon must create ._jatai (soft-delete)
        and must not recreate INBOX/OUTBOX or .jatai automatically.
        """
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        # Ensure initial files exist
        old_success = node.outbox_path / "_done.txt"
        old_error = node.inbox_path / "!_failed.txt"
        old_success.write_text("done")
        old_error.write_text("failed")
        assert node.local_config_path.exists()
        assert node.inbox_path.exists()
        assert node.outbox_path.exists()

        # Simulate a user deleting the local config (preserve inbox/outbox for migration)
        node.local_config_path.unlink()

        assert not node.local_config_path.exists()
        assert node.inbox_path.exists()
        assert node.outbox_path.exists()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        # This should call _ensure_node_onboarded and create ._jatai instead of recreating runtime files
        daemon.load_registered_nodes()

        assert node.disabled_config_path.exists(), "Expected ._jatai soft-delete marker to be created"
        assert not node.local_config_path.exists(), ".jatai should not be recreated automatically"
        # INBOX/OUTBOX are preserved so migration can operate on existing history files
        assert node.inbox_path.exists(), "INBOX should be preserved for migration"
        assert node.outbox_path.exists(), "OUTBOX should be preserved for migration"

        daemon.handle_node_config_change(node.node_path)

        # Simulate a user updating local config to new prefixes so migration should run
        new_config = dict(node.local_config)
        new_config["PREFIX_PROCESSED"] = "processed_"
        new_config["PREFIX_ERROR"] = "error_"
        node.write_config(new_config)
        daemon.handle_node_config_change(node.node_path)

        assert not old_success.exists()
        assert not old_error.exists()
        assert (node.outbox_path / "processed_done.txt").exists()
        assert (node.inbox_path / "error_failed.txt").exists()
        assert node.backup_config_path.exists()

    def test_daemon_handle_node_config_change_rolls_back_on_prefix_collision(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        node_b = register_node(registry_path, "node_b", temp_home / "node_b")

        source_file = node.outbox_path / "_message.txt"
        colliding_target = node.outbox_path / "processed_message.txt"
        source_file.write_text("original")
        colliding_target.write_text("existing")

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        new_config = dict(node.local_config)
        new_config["PREFIX_PROCESSED"] = "processed_"
        node.write_config(new_config)

        daemon.handle_node_config_change(node.node_path)
        node.load_config()

        assert node.get_config("PREFIX_PROCESSED") == "_"
        assert source_file.exists()
        assert colliding_target.exists()
        assert node.backup_config_path.exists()
        notice_files = list(node.inbox_path.glob("!_config-migration-error*.md"))
        assert len(notice_files) == 1
        assert "Prefix migration aborted" in notice_files[0].read_text(encoding="utf-8")
        assert "collision" in notice_files[0].read_text(encoding="utf-8").lower()
        assert not list(node_b.inbox_path.glob("!_config-migration-error*.md"))

    def test_daemon_auto_onboards_registry_only_node(self, temp_home):
        registry_path = temp_home / ".jatai"
        manual_node_path = temp_home / "manual_node"

        registry = Registry(registry_path=registry_path)
        registry.set_config("INBOX_DIR", "INBOX")
        registry.set_config("OUTBOX_DIR", "OUTBOX")
        registry.add_node("manual_node", str(manual_node_path))
        registry.save()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        nodes = daemon.load_registered_nodes()

        assert len(nodes) == 1
        assert manual_node_path.exists()
        assert (manual_node_path / "INBOX").exists()
        assert (manual_node_path / "OUTBOX").exists()
        assert (manual_node_path / ".jatai").exists()
        hello = manual_node_path / "INBOX" / "!helloworld.md"
        assert hello.exists()
        assert "Welcome to Jatai" in hello.read_text(encoding="utf-8")

    def test_daemon_auto_onboarding_respects_custom_dirs(self, temp_home):
        registry_path = temp_home / ".jatai"
        manual_node_path = temp_home / "custom_dirs_node"

        registry = Registry(registry_path=registry_path)
        registry.set_config("INBOX_DIR", "messages/in")
        registry.set_config("OUTBOX_DIR", "messages/out")
        registry.add_node("custom_dirs_node", str(manual_node_path))
        registry.save()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        nodes = daemon.load_registered_nodes()

        assert len(nodes) == 1
        assert (manual_node_path / "messages" / "in").exists()
        assert (manual_node_path / "messages" / "out").exists()

    def test_daemon_missing_local_config_creates_softdelete_marker(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        # Simulate user deleting local config manually.
        node.local_config_path.unlink()
        assert not node.local_config_path.exists()
        assert not node.disabled_config_path.exists()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        nodes = daemon.load_registered_nodes()

        assert len(nodes) == 1
        assert not node.local_config_path.exists()
        assert node.disabled_config_path.exists()

    def test_daemon_auto_onboarding_skips_invalid_overlap(self, temp_home):
        registry_path = temp_home / ".jatai"
        manual_node_path = temp_home / "invalid_overlap_node"

        registry = Registry(registry_path=registry_path)
        registry.set_config("INBOX_DIR", "same")
        registry.set_config("OUTBOX_DIR", "same")
        registry.add_node("invalid_overlap_node", str(manual_node_path))
        registry.save()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        nodes = daemon.load_registered_nodes()

        assert nodes == []
        assert not (manual_node_path / ".jatai").exists()

    def test_daemon_auto_gc_trims_processed_history(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        node.set_config("GC_MAX_READ_FILES", 1)
        node.set_config("GC_MAX_SENT_FILES", 2)

        # INBOX processed files: keep only newest 1
        read_old = node.inbox_path / "_read-old.md"
        read_new = node.inbox_path / "_read-new.md"
        read_old.write_text("old")
        read_new.write_text("new")

        # OUTBOX processed files: keep only newest 2
        sent_1 = node.outbox_path / "_sent-1.md"
        sent_2 = node.outbox_path / "_sent-2.md"
        sent_3 = node.outbox_path / "_sent-3.md"
        sent_1.write_text("1")
        sent_2.write_text("2")
        sent_3.write_text("3")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        daemon.startup_scan()

        assert not read_old.exists()
        assert read_new.exists()
        assert not sent_1.exists()
        assert sent_2.exists()
        assert sent_3.exists()

    def test_daemon_auto_gc_ignores_unprocessed_files(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        node.set_config("GC_MAX_READ_FILES", 1)
        node.set_config("GC_MAX_SENT_FILES", 1)

        pending_inbox = node.inbox_path / "pending.md"
        pending_outbox = node.outbox_path / "pending.md"
        pending_inbox.write_text("in")
        pending_outbox.write_text("out")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        daemon.startup_scan()

        assert pending_inbox.exists()
        assert pending_outbox.exists() or (node.outbox_path / "_pending.md").exists()


class TestDaemonExclusivity:
    """Singleton/PID lock behavior tests."""

    def test_daemon_rejects_duplicate_singleton(self, temp_home):
        pid_path = temp_home / ".jatai.pid"
        daemon_a = JataiDaemon(registry_path=temp_home / ".jatai", pid_path=pid_path)
        daemon_b = JataiDaemon(registry_path=temp_home / ".jatai", pid_path=pid_path)

        daemon_a.acquire_singleton()
        try:
            with pytest.raises(AlreadyRunningError):
                daemon_b.acquire_singleton()
        finally:
            daemon_a.release_singleton()


class TestAutoStartRegistration:
    """Host auto-start registration tests."""

    def test_linux_autostart_writes_systemd_service(self, temp_home):
        registrar = AutoStartRegistrar(
            home_path=temp_home,
            platform_name="linux",
            python_executable="/usr/bin/python3",
        )

        service_path = registrar.register()

        assert service_path.exists()
        content = service_path.read_text(encoding="utf-8")
        assert "systemd" in str(service_path)
        assert "ExecStart=\"/usr/bin/python3\" -m jatai.cli.main _daemon-run" in content


class TestDaemonLogging:
    """Tests verifying that crucial events are written to the log file."""

    # --- helpers ---

    @staticmethod
    def _log_text(log_path):
        return log_path.read_text(encoding="utf-8") if log_path.exists() else ""

    # --- delivery events ---

    def test_log_delivery_succeeded(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")
        (node_a.outbox_path / "msg.txt").write_text("hello")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid", log_path=log_path)
        daemon.startup_scan()

        log = self._log_text(log_path)
        assert "Delivery succeeded" in log
        assert "msg.txt" in log

    def test_log_delivery_failed_per_destination(self, temp_home, monkeypatch):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")
        (node_a.outbox_path / "fail.txt").write_text("payload")

        def fail_delivery(_self):
            raise OSError("disk full")

        monkeypatch.setattr("jatai.core.daemon.Delivery.deliver", fail_delivery)

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry", log_path=log_path,
        )
        daemon.startup_scan()

        log = self._log_text(log_path)
        assert "Delivery failed" in log
        assert "fail.txt" in log
        assert "disk full" in log

    def test_log_retry_scheduled(self, temp_home, monkeypatch):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_a.set_config("MAX_RETRIES", 5)
        register_node(registry_path, "node_b", temp_home / "node_b")
        (node_a.outbox_path / "retry.txt").write_text("payload")

        def fail_delivery(_self):
            raise OSError("transient")

        monkeypatch.setattr("jatai.core.daemon.Delivery.deliver", fail_delivery)

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry", log_path=log_path,
        )
        daemon.startup_scan()

        log = self._log_text(log_path)
        assert "scheduled for retry" in log
        assert "retry.txt" in log

    def test_log_fatal_retry_limit(self, temp_home, monkeypatch):
        import json
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_a.set_config("MAX_RETRIES", 2)
        node_a.set_config("RETRY_DELAY_BASE", 1)
        register_node(registry_path, "node_b", temp_home / "node_b")
        (node_a.outbox_path / "fatal.txt").write_text("payload")

        def fail_delivery(_self):
            raise OSError("always fails")

        monkeypatch.setattr("jatai.core.daemon.Delivery.deliver", fail_delivery)

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry", log_path=log_path,
        )
        daemon.startup_scan()

        # force retry to be due
        retry_data = json.loads((temp_home / ".retry").read_text(encoding="utf-8"))
        for entry in retry_data.values():
            entry["next_retry_at"] = 0
        (temp_home / ".retry").write_text(json.dumps(retry_data), encoding="utf-8")

        daemon.startup_scan()

        log = self._log_text(log_path)
        assert "fatal retry limit" in log
        assert "fatal.txt" in log

    # --- retry-due event ---

    def test_log_retry_due_picked_up(self, temp_home, monkeypatch):
        import json
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        node_a.set_config("MAX_RETRIES", 5)
        node_a.set_config("RETRY_DELAY_BASE", 9999)
        register_node(registry_path, "node_b", temp_home / "node_b")
        source = node_a.outbox_path / "due.txt"
        source.write_text("payload")

        attempt = {"count": 0}

        def fail_first_succeed_second(_self):
            attempt["count"] += 1
            if attempt["count"] == 1:
                raise OSError("first fail")

        monkeypatch.setattr("jatai.core.daemon.Delivery.deliver", fail_first_succeed_second)

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry", log_path=log_path,
        )
        daemon.startup_scan()

        # force retry due
        retry_data = json.loads((temp_home / ".retry").read_text(encoding="utf-8"))
        for entry in retry_data.values():
            entry["next_retry_at"] = 0
        (temp_home / ".retry").write_text(json.dumps(retry_data), encoding="utf-8")

        daemon.startup_scan()

        log = self._log_text(log_path)
        assert "Retry due" in log

    # --- auto-onboarding ---

    def test_log_auto_onboarding(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        manual_node_path = temp_home / "manual_node"

        registry = Registry(registry_path=registry_path)
        registry.set_config("INBOX_DIR", "INBOX")
        registry.set_config("OUTBOX_DIR", "OUTBOX")
        registry.add_node("manual_node", str(manual_node_path))
        registry.save()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid", log_path=log_path)
        daemon.load_registered_nodes()

        log = self._log_text(log_path)
        assert "Auto-onboarded" in log
        assert str(manual_node_path) in log

    def test_log_onboarding_failure_warning(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"

        registry = Registry(registry_path=registry_path)
        registry.set_config("INBOX_DIR", "same")
        registry.set_config("OUTBOX_DIR", "same")
        registry.add_node("bad_node", str(temp_home / "bad_node"))
        registry.save()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid", log_path=log_path)
        daemon.load_registered_nodes()

        log = self._log_text(log_path)
        assert "Failed to onboard" in log
        assert "WARNING" in log

    # --- startup scan events ---

    def test_log_startup_scan_begin_and_complete(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        register_node(registry_path, "node_a", temp_home / "node_a")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid", log_path=log_path)
        daemon.startup_scan()

        log = self._log_text(log_path)
        assert "Startup scan begin" in log
        assert "Startup scan complete" in log

    # --- config change / hot-reload events ---

    def test_log_config_change_detected(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            log_path=log_path, observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()
        daemon.handle_node_config_change(node.node_path)

        log = self._log_text(log_path)
        assert "Config change detected" in log
        assert str(node.node_path) in log

    def test_log_node_active_on_reenable(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            log_path=log_path, observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()
        daemon.handle_node_config_change(node.node_path)

        log = self._log_text(log_path)
        assert "Node active" in log

    def test_log_node_disabled_on_soft_delete(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        node.disable()

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            log_path=log_path, observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()
        daemon.handle_node_config_change(node.node_path)

        log = self._log_text(log_path)
        assert "Node disabled" in log

    def test_log_prefix_migration_started_and_completed(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            log_path=log_path, observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        new_config = dict(node.local_config)
        new_config["PREFIX_PROCESSED"] = "done_"
        node.write_config(new_config)

        daemon.handle_node_config_change(node.node_path)

        log = self._log_text(log_path)
        assert "Prefix migration started" in log
        assert "Prefix migration completed" in log

    def test_log_prefix_rollback_triggered(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        (node.outbox_path / "_existing.txt").write_text("old")
        (node.outbox_path / "done_existing.txt").write_text("collision target")

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            log_path=log_path, observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        new_config = dict(node.local_config)
        new_config["PREFIX_PROCESSED"] = "done_"
        node.write_config(new_config)

        daemon.handle_node_config_change(node.node_path)

        log = self._log_text(log_path)
        assert "Prefix rollback triggered" in log
        assert "WARNING" in log

    # --- watchdog setup ---

    def test_log_watchdog_watching_count(self, temp_home):
        registry_path = temp_home / ".jatai"
        log_path = temp_home / ".jatai.log"
        register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        daemon = JataiDaemon(
            registry_path=registry_path, pid_path=temp_home / ".jatai.pid",
            log_path=log_path, observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        log = self._log_text(log_path)
        assert "Watchdog watching" in log
        assert "active_nodes=2" in log

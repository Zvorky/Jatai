"""
Tests for daemon lifecycle, startup scan, watchdog routing, and auto-start registration.
"""

from pathlib import Path

import pytest
from watchdog.events import FileCreatedEvent, FileMovedEvent

from jatai.core.autostart import AutoStartRegistrar
from jatai.core.daemon import AlreadyRunningError, JataiDaemon, JataiWatchdogHandler
from jatai.core.node import Node
from jatai.core.registry import Registry


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

        daemon.handle_node_config_change(node.node_path)

        assert not old_success.exists()
        assert not old_error.exists()
        assert (node.outbox_path / "processed_done.txt").exists()
        assert (node.inbox_path / "error_failed.txt").exists()
        assert node.backup_config_path.exists()

    def test_daemon_handle_node_config_change_rolls_back_on_prefix_collision(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

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

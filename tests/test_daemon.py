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
        node_b = register_node(registry_path, "node_b", temp_home / "node_b")

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

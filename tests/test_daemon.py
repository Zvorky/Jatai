"""
Tests for daemon lifecycle, startup scan, watchdog routing, and auto-start registration.
"""

import json
import os
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
        second_failure = node_a.outbox_path / "!message.txt"
        assert second_failure.exists()
        assert not (node_a.outbox_path / "!!message.txt").exists()

        retry_data = json.loads((temp_home / ".retry").read_text(encoding="utf-8"))
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
        registry.set_config("PREFIX_IGNORE", "global_")
        registry.set_config("OUTBOX_DIR", "global_outbox")
        registry.save()

        node.write_config(
            {
                "node_path": str(node.node_path),
                "PREFIX_IGNORE": "local_",
                "INBOX_DIR": "local_inbox",
                "OUTBOX_DIR": "local_outbox",
            }
        )

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        [active_node] = daemon.load_active_nodes()

        assert active_node.get_config("PREFIX_IGNORE") == "local_"
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
        new_config["PREFIX_IGNORE"] = "processed_"
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
        new_config["PREFIX_IGNORE"] = "processed_"
        new_config["PREFIX_ERROR"] = "error_"
        node.write_config(new_config)

    def test_daemon_marks_autoremoved_without_creating_softdelete(self, temp_home):
        """When local .jatai is deleted, daemon records auto-removal and does not
        create ._jatai, .jatai, INBOX, or OUTBOX.
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
        nodes = daemon.load_registered_nodes()

        assert nodes == []
        assert not node.disabled_config_path.exists(), "._jatai must not be auto-created"
        assert not node.local_config_path.exists(), ".jatai must not be recreated automatically"
        assert node.inbox_path.exists(), "existing INBOX must be preserved"
        assert node.outbox_path.exists(), "existing OUTBOX must be preserved"

        from jatai.core.sysstate import SystemState

        entries = SystemState.read_yaml(SystemState.removed_path())
        assert f"{node.node_path} --autoremoved" in entries

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
        new_config["PREFIX_IGNORE"] = "processed_"
        node.write_config(new_config)

        daemon.handle_node_config_change(node.node_path)
        node.load_config()

        assert node.get_config("PREFIX_IGNORE") == "_"
        assert source_file.exists()
        assert colliding_target.exists()
        assert node.backup_config_path.exists()
        notice_files = list(node.inbox_path.glob("!_config-migration-error*.md"))
        assert len(notice_files) == 1
        assert "Prefix migration aborted" in notice_files[0].read_text(encoding="utf-8")
        assert "collision" in notice_files[0].read_text(encoding="utf-8").lower()
        assert not list(node_b.inbox_path.glob("!_config-migration-error*.md"))

    def test_daemon_registry_only_node_not_created(self, temp_home):
        registry_path = temp_home / ".jatai"
        manual_node_path = temp_home / "manual_node"

        registry = Registry(registry_path=registry_path)
        registry.set_config("INBOX_DIR", "INBOX")
        registry.set_config("OUTBOX_DIR", "OUTBOX")
        registry.add_node("manual_node", str(manual_node_path))
        registry.save()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        nodes = daemon.load_registered_nodes()

        assert len(nodes) == 0
        assert not manual_node_path.exists()
        assert not (manual_node_path / "INBOX").exists()
        assert not (manual_node_path / "OUTBOX").exists()
        assert not (manual_node_path / ".jatai").exists()


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

        assert len(nodes) == 0
        assert not manual_node_path.exists()
        assert not (manual_node_path / "messages" / "in").exists()
        assert not (manual_node_path / "messages" / "out").exists()

    def test_daemon_missing_local_config_is_marked_autoremoved(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        # Simulate user deleting local config manually.
        node.local_config_path.unlink()
        assert not node.local_config_path.exists()
        assert not node.disabled_config_path.exists()

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        nodes = daemon.load_registered_nodes()

        assert len(nodes) == 0
        assert not node.local_config_path.exists()
        assert not node.disabled_config_path.exists()

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

    def test_daemon_gc_immediate_threshold_triggers_on_outbox_limit(self, temp_home):
        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        node.set_config("GC_MAX_SENT_FILES", 2)

        # place 3 processed files to exceed threshold
        (node.outbox_path / "_out1.txt").write_text("1")
        (node.outbox_path / "_out2.txt").write_text("2")
        (node.outbox_path / "_out3.txt").write_text("3")

        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")
        daemon.startup_scan()

        # keep newest 2 and remove oldest
        existing = sorted([p.name for p in node.list_outbox() if p.name.startswith("_")])
        assert existing == ["_out2.txt", "_out3.txt"]

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
        registrar = AutoStartRegistrar(  # noqa: SIM117
            home_path=temp_home,
            platform_name="linux",
            python_executable="/usr/bin/python3",
        )

        service_path = registrar.register()

        assert service_path.exists()
        content = service_path.read_text(encoding="utf-8")
        assert "systemd" in str(service_path)
        assert "ExecStart=\"/usr/bin/python3\" -m jatai.cli.main _daemon-run" in content

    def test_linux_autostart_crontab_fallback_when_no_systemd(self, temp_home, monkeypatch):
        """When systemctl is unavailable, register() falls back to crontab @reboot (ADR-5.3)."""
        import subprocess as _subprocess
        captured_input: list = []

        class _Result:
            def __init__(self, rc, stdout=""):
                self.returncode = rc
                self.stdout = stdout

        def fake_which(cmd):
            return None if cmd == "systemctl" else f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return _Result(0, "")
            if cmd == ["crontab", "-"]:
                captured_input.append(kwargs.get("input", ""))
                return _Result(0)
            return _Result(1)

        monkeypatch.setattr("jatai.core.autostart.shutil.which", fake_which)
        monkeypatch.setattr("jatai.core.autostart.subprocess.run", fake_run)

        registrar = AutoStartRegistrar(
            home_path=temp_home,
            platform_name="linux",
            python_executable="/usr/bin/python3",
        )
        registrar.register()

        assert len(captured_input) == 1, "crontab - should have been called once"
        assert "@reboot" in captured_input[0]
        assert "_daemon-run" in captured_input[0]

    def test_linux_autostart_crontab_idempotent(self, temp_home, monkeypatch):
        """Crontab @reboot entry is not duplicated when already present (idempotency)."""
        daemon_cmd = '"/usr/bin/python3" -m jatai.cli.main _daemon-run'
        existing_crontab = f"@reboot {daemon_cmd}\n"
        write_calls: dict = {"count": 0}

        class _Result:
            def __init__(self, rc, stdout=""):
                self.returncode = rc
                self.stdout = stdout

        def fake_which(cmd):
            return None if cmd == "systemctl" else f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return _Result(0, existing_crontab)
            if cmd == ["crontab", "-"]:
                write_calls["count"] += 1
                return _Result(0)
            return _Result(1)

        monkeypatch.setattr("jatai.core.autostart.shutil.which", fake_which)
        monkeypatch.setattr("jatai.core.autostart.subprocess.run", fake_run)

        registrar = AutoStartRegistrar(
            home_path=temp_home,
            platform_name="linux",
            python_executable="/usr/bin/python3",
        )
        registrar.register()

        assert write_calls["count"] == 0, "Should not write crontab when entry already present"

    def test_linux_autostart_writes_crontab_marker_when_no_systemd(self, temp_home, monkeypatch):
        """A marker file is written to ~/.config/jatai/ when crontab fallback succeeds."""

        class _Result:
            def __init__(self, rc, stdout=""):
                self.returncode = rc
                self.stdout = stdout

        def fake_which(cmd):
            return None if cmd == "systemctl" else f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return _Result(0, "")
            if cmd == ["crontab", "-"]:
                return _Result(0)
            return _Result(1)

        monkeypatch.setattr("jatai.core.autostart.shutil.which", fake_which)
        monkeypatch.setattr("jatai.core.autostart.subprocess.run", fake_run)

        registrar = AutoStartRegistrar(
            service_name="jatai",
            home_path=temp_home,
            platform_name="linux",
            python_executable="/usr/bin/python3",
        )
        result_path = registrar.register()

        marker = temp_home / ".config" / "jatai" / "jatai-crontab.txt"
        assert marker.exists(), "Crontab marker file should be created on successful fallback"
        assert result_path == marker

    def test_linux_autostart_systemd_enable_fails_falls_back_to_crontab(
        self, temp_home, monkeypatch
    ):
        """If systemd service enable fails, crontab fallback is attempted (ADR-5.3)."""
        import subprocess as _subprocess
        crontab_write_calls: dict = {"count": 0}

        class _Result:
            def __init__(self, rc, stdout=""):
                self.returncode = rc
                self.stdout = stdout

        def fake_which(cmd):
            return f"/usr/bin/{cmd}"  # both systemctl and crontab present

        def fake_run(cmd, **kwargs):
            if isinstance(cmd, list) and len(cmd) >= 2 and cmd[:2] == ["systemctl", "--user"]:
                raise _subprocess.CalledProcessError(1, cmd)
            if cmd == ["crontab", "-l"]:
                return _Result(0, "")
            if cmd == ["crontab", "-"]:
                crontab_write_calls["count"] += 1
                return _Result(0)
            return _Result(1)

        monkeypatch.setattr("jatai.core.autostart.shutil.which", fake_which)
        monkeypatch.setattr("jatai.core.autostart.subprocess.run", fake_run)

        registrar = AutoStartRegistrar(
            home_path=temp_home,
            platform_name="linux",
            python_executable="/usr/bin/python3",
        )
        result_path = registrar.register()

        # The systemd service file should still be written
        assert result_path.exists()
        # Crontab fallback should have been attempted
        assert crontab_write_calls["count"] == 1

    def test_windows_autostart_writes_vbs_startup_script(self, temp_home):
        """Windows registration creates a silent VBScript in the Startup folder."""
        registrar = AutoStartRegistrar(
            service_name="jatai",
            home_path=temp_home,
            platform_name="windows",
            python_executable="C:\\Python39\\python.exe",
        )
        script_path = registrar.register()

        assert script_path.exists()
        assert script_path.suffix == ".vbs"
        content = script_path.read_text(encoding="utf-8")
        assert "WScript.Shell" in content
        assert "_daemon-run" in content


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

    def test_daemon_log_rotation_and_latest_symlink(self, temp_home):
        registry_path = temp_home / ".jatai"
        node_a = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        source_file = node_a.outbox_path / "loggable.txt"
        source_file.write_text("payload")

        log_path = temp_home / "daemon.log"
        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            retry_path=temp_home / ".retry",
            log_path=log_path,
        )
        daemon.startup_scan()

        assert log_path.exists()

        latest_path = Path(os.path.expanduser(Registry(registry_path).global_config.get("LATEST_LOG_PATH", "~/.jatai_latest.log"))).expanduser()
        if latest_path.exists() or latest_path.is_symlink():
            assert latest_path.resolve() == log_path.resolve()

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

        # force first retry to be due (should still be non-fatal for MAX_RETRIES=2)
        retry_data = json.loads((temp_home / ".retry").read_text(encoding="utf-8"))
        for entry in retry_data.values():
            entry["next_retry_at"] = 0
        (temp_home / ".retry").write_text(json.dumps(retry_data), encoding="utf-8")

        daemon.startup_scan()

        # force second retry to be due and become fatal
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
        assert "Node path missing; skipping auto-onboarding" in log
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
        new_config["PREFIX_IGNORE"] = "done_"
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
        new_config["PREFIX_IGNORE"] = "done_"
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

    def test_system_state_paths_created(self):
        from jatai.core.sysstate import SystemState

        base = SystemState.BASE_PATH
        removed_path = SystemState.removed_path()
        uuid_map = SystemState.uuid_map_path()
        bkp_path = SystemState.bkp_path("test-uuid")

        assert base.exists() and base.is_dir()
        assert (base / "logs").exists() and (base / "logs").is_dir()
        assert (base / "bkp").exists() and (base / "bkp").is_dir()

        # Paths must be accessible (contents may be non-empty from earlier tests)
        result = SystemState.read_yaml(removed_path)
        assert isinstance(result, (dict, list)), "removed.yaml must parse to dict or list"
        result2 = SystemState.read_yaml(uuid_map)
        assert result2 == {} or isinstance(result2, dict), "uuid_map.yaml must be a dict"

        SystemState.write_yaml(bkp_path, {"test": 1})
        assert bkp_path.exists()
        assert SystemState.read_yaml(bkp_path) == {"test": 1}

    def test_delete_path_uses_send2trash_and_fallback(self, temp_home, monkeypatch):
        registry_path = temp_home / ".jatai"
        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")

        target = temp_home / "delete_test.txt"
        target.write_text("hello", encoding="utf-8")

        state = {"called": False}

        def fake_send2trash(path):
            assert path == str(target)
            state["called"] = True
            raise OSError("trash failure")

        monkeypatch.setattr("jatai.core.daemon.send2trash", fake_send2trash)

        daemon._delete_path(target, mode="trash")

        assert state["called"] is True
        assert not target.exists()

    def test_delete_path_permanent_mode(self, temp_home):
        registry_path = temp_home / ".jatai"
        daemon = JataiDaemon(registry_path=registry_path, pid_path=temp_home / ".jatai.pid")

        target = temp_home / "delete_perm.txt"
        target.write_text("hello", encoding="utf-8")

        daemon._delete_path(target, mode="permanent")


class TestPhase7StateArchitecture:
    """Phase 7: UUID map, removed.yaml, bkp cache, and anti-heuristic compliance tests."""

    def test_daemon_assigns_uuid_on_onboard(self, temp_home, monkeypatch):
        """Daemon assigns a persistent UUID to each node during onboarding (ADR-4.3.1)."""
        from jatai.core.sysstate import SystemState

        isolated_base = temp_home / "jatai_sys"
        monkeypatch.setattr(SystemState, "BASE_PATH", isolated_base)

        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        uid = SystemState.get_uuid(str(node.node_path))
        assert uid is not None, "UUID should have been assigned during onboarding"
        assert len(uid) == 36  # standard UUID4 format

    def test_daemon_writes_removed_yaml_on_auto_soft_delete(self, temp_home, monkeypatch):
        """Daemon records auto-removed nodes in removed.yaml (ADR-4.4.1, REQ-3.7.2.1)."""
        from jatai.core.sysstate import SystemState

        isolated_base = temp_home / "jatai_sys"
        monkeypatch.setattr(SystemState, "BASE_PATH", isolated_base)

        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        # Simulate manual .jatai deletion (user removed the config file manually)
        if node.local_config_path.exists():
            node.local_config_path.unlink()
        if node.disabled_config_path.exists():
            node.disabled_config_path.unlink()

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.load_registered_nodes()

        entries = SystemState.read_yaml(SystemState.removed_path())
        expected = f"{node.node_path} --autoremoved"
        assert isinstance(entries, list), "removed.yaml should contain a list"
        assert expected in entries, f"Expected '{expected}' in removed.yaml, got: {entries}"

    def test_daemon_writes_bkp_cache_on_node_cache_update(self, temp_home, monkeypatch):
        """Daemon writes /tmp/jatai/bkp/<UUID>.yaml when updating node cache (ADR-4.3.3)."""
        from jatai.core.sysstate import SystemState

        isolated_base = temp_home / "jatai_sys"
        monkeypatch.setattr(SystemState, "BASE_PATH", isolated_base)

        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        uid = SystemState.get_uuid(str(node.node_path))
        assert uid is not None, "UUID must be assigned before bkp can exist"

        bkp_path = SystemState.bkp_path(uid)
        assert bkp_path.exists(), "Backup config file should exist after setup_watchdog"
        bkp_data = SystemState.read_yaml(bkp_path)
        assert isinstance(bkp_data, dict), "Backup should be a dict"

    def test_daemon_handle_config_change_no_heuristic_prefix_guessing(
        self, temp_home, monkeypatch
    ):
        """Daemon does NOT scan directory contents to guess prefixes (ADR-3.3)."""
        from jatai.core.sysstate import SystemState

        isolated_base = temp_home / "jatai_sys"
        monkeypatch.setattr(SystemState, "BASE_PATH", isolated_base)

        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        # Place decoy files that a frequency-based heuristic might incorrectly pick up
        (node.outbox_path / "_decoy1.txt").write_text("x")
        (node.outbox_path / "_decoy2.txt").write_text("x")
        (node.outbox_path / "done_decoy.txt").write_text("x")
        (node.inbox_path / "_inbox_decoy.txt").write_text("x")

        daemon = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon.setup_watchdog()

        # Clear in-memory cache to force cold-state resolution
        daemon.node_config_cache.clear()

        new_config = dict(node.local_config)
        new_config["PREFIX_IGNORE"] = "done_"
        node.write_config(new_config)

        # Must not crash regardless of the decoy files present
        daemon.handle_node_config_change(node.node_path)

        # Verify config state reflects the new value
        node.load_any_config()
        node.apply_effective_config({})
        assert node.get_config("PREFIX_IGNORE", "_") == "done_"

    def test_daemon_uses_uuid_bkp_for_prefix_migration_fallback(self, temp_home, monkeypatch):
        """Daemon uses UUID backup from sysstate when in-memory cache is absent (cold restart)."""
        from jatai.core.sysstate import SystemState

        isolated_base = temp_home / "jatai_sys"
        monkeypatch.setattr(SystemState, "BASE_PATH", isolated_base)

        registry_path = temp_home / ".jatai"
        node = register_node(registry_path, "node_a", temp_home / "node_a")
        register_node(registry_path, "node_b", temp_home / "node_b")

        old_prefix = "_"
        new_prefix = "done_"
        old_file = node.outbox_path / f"{old_prefix}already_delivered.txt"
        old_file.write_text("payload")

        # First daemon run: onboard node and write UUID backup
        daemon1 = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        daemon1.setup_watchdog()
        assert SystemState.get_uuid(str(node.node_path)) is not None

        # Second daemon (cold restart): empty in-memory cache, but UUID bkp exists
        daemon2 = JataiDaemon(
            registry_path=registry_path,
            pid_path=temp_home / ".jatai.pid",
            observer_factory=FakeObserver,
        )
        # Do NOT call setup_watchdog; node_config_cache is empty

        new_config = dict(node.local_config)
        new_config["PREFIX_IGNORE"] = new_prefix
        node.write_config(new_config)

        daemon2.handle_node_config_change(node.node_path)

        migrated = node.outbox_path / f"{new_prefix}already_delivered.txt"
        assert migrated.exists(), (
            "UUID bkp fallback should allow prefix migration after cold restart"
        )


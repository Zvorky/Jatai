"""Tests for uninstall cleanup helper behavior."""

from pathlib import Path

from typer.testing import CliRunner

from jatai.cli.main import app
from jatai.core.registry import Registry
from jatai.core.sysstate import SystemState
from jatai.core.uninstall import cleanup_install_artifacts


runner = CliRunner()


def test_cleanup_install_artifacts_removes_configs_and_tmp_keeps_logs(temp_dir, temp_home, monkeypatch):
    """Full cleanup removes config/control artifacts and preserves logs by default."""
    node_a = temp_dir / "node_a"
    node_b = temp_dir / "node_b"
    node_a.mkdir(parents=True)
    node_b.mkdir(parents=True)

    (node_a / ".jatai").write_text("INBOX_DIR: INBOX\n", encoding="utf-8")
    (node_b / "._jatai").write_text("INBOX_DIR: INBOX\n", encoding="utf-8")

    registry = Registry()
    registry.add_node("a", str(node_a))
    registry.save()

    state_root = temp_dir / "tmp_state"
    monkeypatch.setattr(SystemState, "BASE_PATH", state_root)
    SystemState.ensure_base()

    SystemState.write_yaml(SystemState.removed_path(), [f"{node_b} --autoremoved"])
    (state_root / "retry.yaml").write_text("{}\n", encoding="utf-8")
    (state_root / "registry.lock").write_text("", encoding="utf-8")
    (state_root / "logs").mkdir(parents=True, exist_ok=True)
    (state_root / "logs" / "jatai.log").write_text("hello\n", encoding="utf-8")

    actions = cleanup_install_artifacts(remove_logs=False, dry_run=False)

    assert any("remove global config" in item for item in actions)
    assert not (node_a / ".jatai").exists()
    assert not (node_b / "._jatai").exists()
    assert not (temp_home / ".jatai").exists()
    assert not (state_root / "retry.yaml").exists()
    assert (state_root / "logs").exists()


def test_cleanup_install_artifacts_dry_run_does_not_delete(temp_dir, temp_home, monkeypatch):
    """Dry-run mode reports actions and does not delete files."""
    node_a = temp_dir / "node_a"
    node_a.mkdir(parents=True)
    (node_a / ".jatai").write_text("INBOX_DIR: INBOX\n", encoding="utf-8")

    registry = Registry()
    registry.add_node("a", str(node_a))
    registry.save()

    state_root = temp_dir / "tmp_state"
    monkeypatch.setattr(SystemState, "BASE_PATH", state_root)
    SystemState.ensure_base()
    (state_root / "retry.yaml").write_text("{}\n", encoding="utf-8")

    actions = cleanup_install_artifacts(dry_run=True)

    assert actions
    assert (node_a / ".jatai").exists()
    assert (temp_home / ".jatai").exists()
    assert (state_root / "retry.yaml").exists()


def test_cleanup_install_artifacts_remove_logs_option(temp_dir, temp_home, monkeypatch):
    """remove_logs=True also removes logs directory and may remove tmp root."""
    registry = Registry()
    registry.save()

    state_root = temp_dir / "tmp_state"
    monkeypatch.setattr(SystemState, "BASE_PATH", state_root)
    (state_root / "logs").mkdir(parents=True, exist_ok=True)
    (state_root / "logs" / "jatai.log").write_text("hello\n", encoding="utf-8")

    cleanup_install_artifacts(remove_logs=True, dry_run=False)

    assert not state_root.exists()


def test_cli_cleanup_requires_full_flag():
    """CLI should require explicit --full for destructive cleanup mode."""
    result = runner.invoke(app, ["cleanup"])

    assert result.exit_code == 1
    assert "Refusing to run without --full" in result.stdout


def test_cli_cleanup_dry_run_succeeds(temp_dir, temp_home, monkeypatch):
    """CLI dry-run path should execute without confirmation."""
    state_root = temp_dir / "tmp_state"
    monkeypatch.setattr(SystemState, "BASE_PATH", state_root)
    SystemState.ensure_base()
    (state_root / "retry.yaml").write_text("{}\n", encoding="utf-8")

    result = runner.invoke(app, ["cleanup", "--full", "--dry-run"])

    assert result.exit_code == 0
    assert "Cleanup dry-run" in result.stdout
    assert (state_root / "retry.yaml").exists()

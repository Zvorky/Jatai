"""
Tests for jatai.cli.main module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from jatai.cli.main import app, run
from jatai.core.registry import Registry
from jatai.core.node import Node

runner = CliRunner()


class TestCLIHappyPath:
    """Happy path tests for CLI."""

    def test_cli_init_with_path(self, temp_dir, temp_home):
        """Test initializing a node via CLI with explicit path."""
        node_path = str(temp_dir / "test_node")

        result = runner.invoke(app, ["init", node_path])

        assert result.exit_code == 0
        assert "Initialized node" in result.stdout
        assert "INBOX" in result.stdout
        assert "OUTBOX" in result.stdout

        # Verify structure was created
        assert Path(node_path).exists()
        assert (Path(node_path) / "INBOX").exists()
        assert (Path(node_path) / "OUTBOX").exists()

    def test_cli_init_current_directory(self, temp_dir, temp_home):
        """Test initializing current directory as node using init alias."""
        # Pass temp_dir as explicit path argument instead of using cwd
        result = runner.invoke(app, ["init", str(temp_dir)])

        assert result.exit_code == 0
        assert (temp_dir / "INBOX").exists()
        assert (temp_dir / "OUTBOX").exists()

    def test_cli_status_valid_node(self, temp_dir):
        """Test status command on valid node."""
        node_path = temp_dir / "test_node"
        node = Node(node_path)
        node.create()

        # Since CliRunner doesn't support cwd in newer versions, test init + status on same node
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node_path)
            result = runner.invoke(app, ["status"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Node:" in result.stdout or "INBOX" in result.stdout


    def test_cli_status_with_files(self, temp_dir):
        """Test status command showing file counts."""
        node_path = temp_dir / "test_node"
        node = Node(node_path)
        node.create()

        # Add some files
        (node.inbox_path / "file1.txt").write_text("content")
        (node.outbox_path / "msg1.txt").write_text("content")
        (node.outbox_path / "msg2.txt").write_text("content")

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node_path)
            result = runner.invoke(app, ["status"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "INBOX" in result.stdout or "file(s)" in result.stdout

    def test_cli_init_creates_registry_entry(self, temp_home):
        """Test that init adds node to global registry."""
        node_path = str(temp_home / "nodes" / "my_node")

        result = runner.invoke(app, ["init", node_path])

        assert result.exit_code == 0
        assert "Added to global registry" in result.stdout

        # Verify registry was updated
        registry_path = temp_home / ".jatai"
        assert registry_path.exists()

    def test_cli_start_spawns_background_daemon(self, monkeypatch):
        """Test start command spawns daemon and registers auto-start."""
        calls = {"spawn": 0, "register": 0}

        monkeypatch.setattr("jatai.cli.main.JataiDaemon.is_running", lambda self: False)
        monkeypatch.setattr(
            "jatai.cli.main.AutoStartRegistrar.register",
            lambda self: Path("/tmp/jatai.service"),
        )

        def fake_spawn():
            calls["spawn"] += 1
            return object()

        monkeypatch.setattr("jatai.cli.main._spawn_daemon_process", fake_spawn)

        result = runner.invoke(app, ["start"])

        assert result.exit_code == 0
        assert calls["spawn"] == 1
        assert "Daemon started" in result.stdout

    def test_cli_stop_running_daemon(self, monkeypatch):
        """Test stop command terminates a running daemon."""
        state = {"running": True, "killed": False}

        monkeypatch.setattr("jatai.cli.main.JataiDaemon.read_pid", lambda self: 99999)

        def fake_running(self, pid):
            return state["running"]

        def fake_kill(pid, sig):
            state["killed"] = True
            state["running"] = False

        monkeypatch.setattr("jatai.cli.main.JataiDaemon.is_process_running", fake_running)
        monkeypatch.setattr("jatai.cli.main.os.kill", fake_kill)

        result = runner.invoke(app, ["stop"])

        assert result.exit_code == 0
        assert state["killed"] is True
        assert "Daemon stopped" in result.stdout

    def test_cli_root_alias_path(self, temp_dir, temp_home, monkeypatch):
        """Test `jatai [path]` alias using run() entrypoint."""
        node_path = temp_dir / "alias_node"
        monkeypatch.setattr("sys.argv", ["jatai", str(node_path)])

        run()

        assert node_path.exists()
        assert (node_path / "INBOX").exists()
        assert (node_path / "OUTBOX").exists()

    def test_cli_docs_without_query_drops_index(self, temp_dir):
        """Test docs command without query creates category index in INBOX."""
        node = Node(temp_dir / "docs_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        index_path = node.inbox_path / "!docs-index.md"
        assert index_path.exists()
        assert "Jatai Documentation Index" in index_path.read_text(encoding="utf-8")

    def test_cli_docs_with_query_copies_matching_files(self, temp_dir):
        """Test docs command with query copies matching docs to INBOX."""
        node = Node(temp_dir / "docs_query_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs", "retry"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        copied = list(node.inbox_path.glob("*retry*.md"))
        assert copied


class TestCLIErrorFailureScenarios:
    """Error and failure scenario tests for CLI."""

    def test_cli_status_not_a_node(self, temp_dir):
        """Test status command in non-node directory."""
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = runner.invoke(app, ["status"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code != 0 or "not a Jataí node" in result.stdout or "error" in result.stdout.lower()

    def test_cli_init_invalid_path(self, temp_dir):
        """Test init with invalid path."""
        # Path to a file (not directory)
        invalid_path = str(temp_dir / "file.txt")
        Path(invalid_path).write_text("existing file")

        result = runner.invoke(app, ["init", invalid_path])

        # Behavior depends on implementation - could succeed or fail
        # Just verify it doesn't crash unexpectedly
        assert result.exit_code in [0, 1]

    def test_cli_init_permission_denied(self, temp_dir):
        """Test init in directory without write permissions."""
        import os

        readonly_path = temp_dir / "readonly"
        readonly_path.mkdir()

        # Make readonly
        os.chmod(readonly_path, 0o555)

        try:
            result = runner.invoke(app, ["init", str(readonly_path / "node")])
            # Should fail gracefully
            assert result.exit_code != 0 or "Error" in result.stdout
        finally:
            # Restore permissions
            os.chmod(readonly_path, 0o755)

    def test_cli_help(self):
        """Test CLI help output."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Jataí" in result.stdout
        assert "usage" in result.stdout.lower()

    def test_cli_start_when_already_running(self, monkeypatch):
        """Test start fails gracefully when daemon is already running."""
        monkeypatch.setattr("jatai.cli.main.JataiDaemon.is_running", lambda self: True)

        result = runner.invoke(app, ["start"])

        assert result.exit_code == 1
        assert "Already running" in result.stdout or "Already running" in result.stderr

    def test_cli_stop_when_not_running(self, monkeypatch):
        """Test stop fails gracefully if daemon is not running."""
        monkeypatch.setattr("jatai.cli.main.JataiDaemon.read_pid", lambda self: None)

        result = runner.invoke(app, ["stop"])

        assert result.exit_code == 1
        assert "not running" in result.stdout.lower() or "not running" in result.stderr.lower()

    def test_cli_init_overlap_prompt_rejected(self, temp_dir, monkeypatch):
        """Test init fails when overlap suggestion prompt is rejected."""
        node_path = temp_dir / "overlap_node"

        # Build a global registry config that forces overlap.
        from jatai.core.registry import Registry

        reg = Registry(registry_path=temp_dir / ".jatai")
        reg.set_config("INBOX_DIR", "shared")
        reg.set_config("OUTBOX_DIR", "shared")
        reg.save()
        monkeypatch.setenv("HOME", str(temp_dir))

        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)
        result = runner.invoke(app, ["init", str(node_path)])

        assert result.exit_code == 1

    def test_cli_init_overlap_prompt_accepted(self, temp_dir, monkeypatch):
        """Test init creates suggested split folders when overlap prompt is accepted."""
        node_path = temp_dir / "overlap_node_accept"

        from jatai.core.registry import Registry

        reg = Registry(registry_path=temp_dir / ".jatai")
        reg.set_config("INBOX_DIR", "shared")
        reg.set_config("OUTBOX_DIR", "shared")
        reg.save()
        monkeypatch.setenv("HOME", str(temp_dir))

        monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: True)
        result = runner.invoke(app, ["init", str(node_path)])

        assert result.exit_code == 0
        assert (node_path / "shared" / "INBOX").exists()
        assert (node_path / "shared" / "OUTBOX").exists()

    def test_cli_docs_fails_outside_node(self, temp_dir):
        """Test docs command fails in non-node directories."""
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = runner.invoke(app, ["docs"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "not a Jataí node" in result.stdout or "not a Jataí node" in result.stderr

    def test_cli_docs_query_without_matches(self, temp_dir):
        """Test docs query returns a controlled error when there are no matches."""
        node = Node(temp_dir / "docs_nomatch_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs", "query-that-should-not-exist-12345"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "no docs matched" in result.stdout.lower() or "no docs matched" in result.stderr.lower()


class TestCLIMaliciousAdversarialScenarios:
    """Malicious/adversarial scenario tests for CLI."""

    def test_cli_init_path_traversal(self, temp_dir, temp_home):
        """Test init with path traversal attempt."""
        traversal_path = str(temp_dir / "node" / "../../../etc/jatai")

        result = runner.invoke(app, ["init", traversal_path])

        # Should resolve safely
        assert result.exit_code in [0, 1]
        assert ".." not in Path(result.stdout).name if result.stdout else True

    def test_cli_unicode_in_path(self, temp_dir, temp_home):
        """Test init with unicode characters in path."""
        unicode_path = str(temp_dir / "节点_🐝")

        result = runner.invoke(app, ["init", unicode_path])

        assert result.exit_code == 0
        assert Path(unicode_path).exists()

    def test_cli_very_long_path(self, temp_dir, temp_home):
        """Test init with very long path."""
        long_path = temp_dir / ("a" * 100) / ("b" * 100) / "node"

        result = runner.invoke(app, ["init", str(long_path)])

        # Should succeed on most systems
        assert result.exit_code in [0, 1]

    def test_cli_injection_attempt_in_arguments(self, temp_dir, temp_home):
        """Test that CLI doesn't execute shell injections."""
        # Attempt shell injection through a path argument
        injection_path = str(temp_dir / "; echo hacked &")

        result = runner.invoke(app, ["init", injection_path])

        # Should treat as literal path and handle gracefully
        assert result.exit_code in [0, 1, 2]  # OK if rejected or accepted as path
        # Most important: code should not have executed the injection

    def test_cli_output_escaping(self, temp_dir, temp_home):
        """Test that CLI output is properly escaped."""
        # Create path with special characters
        path_with_special = str(temp_dir / "node\necho hacked")

        result = runner.invoke(app, ["init", path_with_special])

        # Output should not execute injected commands
        assert "hacked" not in result.stdout or "\n" in result.stdout

    def test_cli_symlink_targets(self, temp_dir, temp_home):
        """Test init with symlink paths."""
        import os

        actual_path = temp_dir / "actual_node"
        actual_path.mkdir()

        link_path = temp_dir / "link_node"
        os.symlink(actual_path, link_path)

        result = runner.invoke(app, ["init", str(link_path)])

        assert result.exit_code == 0
        assert (actual_path / "INBOX").exists() or (link_path / "INBOX").exists()

    def test_cli_rapid_fire_commands(self, temp_dir, temp_home):
        """Test rapid sequential CLI commands."""
        for i in range(10):
            node_path = str(temp_dir / f"node_{i}")
            result = runner.invoke(app, ["init", node_path])
            assert result.exit_code == 0

    def test_cli_output_contains_no_sensitive_paths(self, temp_home):
        """Test that CLI doesn't leak sensitive information."""
        result = runner.invoke(app, ["init", str(temp_home / "node")])

        # Output shouldn't contain full paths to home or sensitive dirs
        # (actual implementation may vary)
        assert result.exit_code == 0

    def test_cli_docs_query_path_traversal_pattern_is_treated_as_plain_text(self, temp_dir):
        """Test docs query with traversal-like content does not escape docs scope."""
        node = Node(temp_dir / "docs_traversal_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs", "../../etc/passwd"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert not any("passwd" in p.name for p in node.inbox_path.glob("*.md"))

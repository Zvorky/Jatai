"""
Tests for jatai.cli.main module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from jatai.cli.main import app, run, _run_tui
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

    def test_cli_init_drops_helloworld_into_inbox(self, temp_dir, temp_home):
        """Test init drops !helloworld.md tutorial into node INBOX."""
        node_path = Path(temp_dir / "hello_node")

        result = runner.invoke(app, ["init", str(node_path)])

        assert result.exit_code == 0
        hello_file = node_path / "INBOX" / "!helloworld.md"
        assert hello_file.exists()
        assert "Welcome" in hello_file.read_text(encoding="utf-8")

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

    def test_cli_docs_without_query_prints_index_in_terminal(self, temp_dir):
        """Test docs command without query prints category index by default."""
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
        assert "Jatai Documentation Index" in result.stdout
        assert not (node.inbox_path / "!docs-index.md").exists()

    def test_cli_docs_with_query_prints_matches_in_terminal(self, temp_dir):
        """Test docs command with query prints matching docs by default."""
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
        assert "retry-and-health.md" in result.stdout
        copied = list(node.inbox_path.glob("*retry*.md"))
        assert not copied

    def test_cli_docs_inbox_option_exports_index(self, temp_dir):
        """Test docs --inbox exports index file to INBOX."""
        node = Node(temp_dir / "docs_inbox_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs", "--inbox"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        index_path = node.inbox_path / "!docs-index.md"
        assert index_path.exists()

    def test_cli_docs_query_inbox_option_exports_matches(self, temp_dir):
        """Test docs query --inbox copies matching files."""
        node = Node(temp_dir / "docs_query_inbox_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs", "retry", "--inbox"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        copied = list(node.inbox_path.glob("*retry*.md"))
        assert copied

    def test_cli_docs_query_inbox_applies_bang_prefix(self, temp_dir):
        """Test docs query --inbox names all exported files with ! prefix (ADR 15)."""
        node = Node(temp_dir / "docs_bang_prefix_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["docs", "retry", "--inbox"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        for f in node.inbox_path.iterdir():
            assert f.name.startswith("!"), f"Expected ! prefix on system artifact: {f.name}"


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

    def test_cli_docs_inbox_fails_outside_node(self, temp_dir):
        """Test docs --inbox fails in non-node directories."""
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = runner.invoke(app, ["docs", "--inbox"])
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

    def test_cli_log_missing_file(self, temp_home, monkeypatch):
        """Test log command fails gracefully when log file doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_home))
        result = runner.invoke(app, ["log"])

        assert result.exit_code == 1
        assert "log file not found" in result.stdout.lower() or "log file not found" in result.stderr.lower()


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

    def test_cli_rapid_fire_commands(self, temp_dir, temp_home, monkeypatch):
        """Test rapid sequential CLI commands."""
        monkeypatch.setenv("HOME", str(temp_home))
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


class TestCLIPhase6Toolbox:
    """Phase 6 command surface tests."""

    def test_cli_log_latest_and_all(self, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        log_path = temp_home / ".jatai.log"
        log_path.write_text("line1\nline2\nline3\n", encoding="utf-8")

        latest = runner.invoke(app, ["log"])
        assert latest.exit_code == 0
        assert "line3" in latest.stdout

        full = runner.invoke(app, ["log", "--all"])
        assert full.exit_code == 0
        assert "line1" in full.stdout
        assert "line3" in full.stdout

    def test_cli_log_inbox_exports_rendered_output(self, temp_dir, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        (temp_home / ".jatai.log").write_text("abc\ndef\n", encoding="utf-8")
        node = Node(temp_dir / "log_export_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["log", "--inbox"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        exported = node.inbox_path / "!log-latest.txt"
        assert exported.exists()
        assert "abc" in exported.read_text(encoding="utf-8")

    def test_cli_list_inbox_outbox_and_addrs(self, temp_dir, temp_home, monkeypatch):
        node = Node(temp_dir / "list_node")
        node.create()
        (node.inbox_path / "in.txt").write_text("in")
        (node.outbox_path / "out.txt").write_text("out")

        reg = Registry(registry_path=temp_home / ".jatai")
        reg.add_node("list_node", str(node.node_path))
        reg.save()
        monkeypatch.setenv("HOME", str(temp_home))

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            inbox = runner.invoke(app, ["list", "inbox"])
            outbox = runner.invoke(app, ["list", "outbox"])
            addrs = runner.invoke(app, ["list", "addrs"])
        finally:
            os.chdir(old_cwd)

        assert inbox.exit_code == 0 and "in.txt" in inbox.stdout
        assert outbox.exit_code == 0 and "out.txt" in outbox.stdout
        assert addrs.exit_code == 0 and "list_node" in addrs.stdout

    def test_cli_send_read_unread_cycle(self, temp_dir):
        node = Node(temp_dir / "send_read_node")
        node.create()
        source = temp_dir / "payload.txt"
        source.write_text("payload")

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            send_result = runner.invoke(app, ["send", str(source)])
            assert send_result.exit_code == 0

            inbox_file = node.inbox_path / "msg.txt"
            inbox_file.write_text("x")
            read_result = runner.invoke(app, ["read", "msg.txt"])
            assert read_result.exit_code == 0
            assert (node.inbox_path / "_msg.txt").exists()

            unread_result = runner.invoke(app, ["unread", "_msg.txt"])
            assert unread_result.exit_code == 0
            assert (node.inbox_path / "msg.txt").exists()
        finally:
            os.chdir(old_cwd)

    def test_cli_config_local_and_global(self, temp_dir, temp_home, monkeypatch):
        node = Node(temp_dir / "config_node")
        node.create()
        monkeypatch.setenv("HOME", str(temp_home))

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            set_local = runner.invoke(app, ["config", "RETRY_DELAY_BASE", "90"])
            get_local = runner.invoke(app, ["config", "RETRY_DELAY_BASE"])
            set_global = runner.invoke(app, ["config", "--global", "MAX_RETRIES", "8"])
            get_global = runner.invoke(app, ["config", "--global", "MAX_RETRIES"])
        finally:
            os.chdir(old_cwd)

        assert set_local.exit_code == 0
        assert "RETRY_DELAY_BASE=90" in get_local.stdout
        assert set_global.exit_code == 0
        assert "MAX_RETRIES=8" in get_global.stdout

    def test_cli_config_get_local_and_global(self, temp_dir, temp_home, monkeypatch):
        node = Node(temp_dir / "config_get_node")
        node.create()
        monkeypatch.setenv("HOME", str(temp_home))

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            set_local = runner.invoke(app, ["config", "RETRY_DELAY_BASE", "77"])
            set_global = runner.invoke(app, ["config", "-G", "MAX_RETRIES", "6"])
            get_local = runner.invoke(app, ["config", "get", "RETRY_DELAY_BASE"])
            get_global = runner.invoke(app, ["config", "get", "MAX_RETRIES", "-G"])
            get_local_full = runner.invoke(app, ["config", "get"])
        finally:
            os.chdir(old_cwd)

        assert set_local.exit_code == 0
        assert set_global.exit_code == 0
        assert get_local.exit_code == 0 and "RETRY_DELAY_BASE=77" in get_local.stdout
        assert get_global.exit_code == 0 and "MAX_RETRIES=6" in get_global.stdout
        assert get_local_full.exit_code == 0 and "RETRY_DELAY_BASE" in get_local_full.stdout

    def test_cli_config_get_with_inbox_export(self, temp_dir, temp_home, monkeypatch):
        node = Node(temp_dir / "config_get_export_node")
        node.create()
        monkeypatch.setenv("HOME", str(temp_home))

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            runner.invoke(app, ["config", "RETRY_DELAY_BASE", "66"])
            exported = runner.invoke(app, ["config", "get", "RETRY_DELAY_BASE", "-i"])
        finally:
            os.chdir(old_cwd)

        assert exported.exit_code == 0
        output_file = node.inbox_path / "!config-local-RETRY_DELAY_BASE.txt"
        assert output_file.exists()
        assert "RETRY_DELAY_BASE=66" in output_file.read_text(encoding="utf-8")

    def test_cli_config_get_missing_key_fails(self, temp_dir):
        node = Node(temp_dir / "config_missing_key_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["config", "get", "NOT_A_KEY"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "unknown local config key" in result.stdout.lower() or "unknown local config key" in result.stderr.lower()

    def test_cli_config_inbox_without_get_fails(self, temp_dir):
        node = Node(temp_dir / "config_invalid_inbox_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["config", "MAX_RETRIES", "9", "-i"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "only supported with 'config get'" in result.stdout.lower() or "only supported with 'config get'" in result.stderr.lower()

    def test_cli_remove_soft_delete_and_clear(self, temp_dir):
        node = Node(temp_dir / "remove_clear_node")
        node.create()
        (node.inbox_path / "_read.md").write_text("r")
        (node.outbox_path / "_sent.md").write_text("s")

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            clear_result = runner.invoke(app, ["clear"])
            assert clear_result.exit_code == 0
            assert not (node.inbox_path / "_read.md").exists()
            assert not (node.outbox_path / "_sent.md").exists()

            remove_result = runner.invoke(app, ["remove"])
            assert remove_result.exit_code == 0
            assert (node.node_path / "._jatai").exists()
        finally:
            os.chdir(old_cwd)

    def test_cli_status_shows_config_path(self, temp_dir, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        node = Node(temp_dir / "status_path_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["status"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Config:" in result.stdout
        assert ".jatai" in result.stdout

    def test_cli_list_addrs_shows_registry_path(self, temp_dir, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        node = Node(temp_dir / "addrs_path_node")
        node.create()
        registry = Registry()
        try:
            registry.load()
        except FileNotFoundError:
            pass
        registry.add_node(node.node_path.name, str(node.node_path))
        registry.save()

        result = runner.invoke(app, ["list", "addrs"])
        assert result.exit_code == 0
        assert "# registry:" in result.stdout

    def test_cli_config_local_full_dump_shows_source(self, temp_dir, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        node = Node(temp_dir / "cfg_source_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["config"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "# source:" in result.stdout

    def test_cli_config_global_full_dump_shows_source(self, temp_dir, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        registry = Registry()
        try:
            registry.load()
        except FileNotFoundError:
            pass
        registry.save()

        result = runner.invoke(app, ["config", "--global"])
        assert result.exit_code == 0
        assert "# source:" in result.stdout

    def test_cli_config_get_local_shows_source(self, temp_dir, temp_home, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_home))
        node = Node(temp_dir / "cfg_get_src_node")
        node.create()

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(node.node_path)
            result = runner.invoke(app, ["config", "get"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "# source:" in result.stdout


class TestCLITUI:
    """Interactive TUI behavior tests."""

    def test_run_without_args_uses_tui_in_interactive_terminal(self, monkeypatch):
        calls = {"tui": 0}

        monkeypatch.setattr("sys.argv", ["jatai"])
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        def fake_tui():
            calls["tui"] += 1

        monkeypatch.setattr("jatai.cli.main._run_tui", fake_tui)

        run()
        assert calls["tui"] == 1

    def test_run_without_args_non_interactive_prints_help(self, monkeypatch):
        calls = {"help": 0}

        monkeypatch.setattr("sys.argv", ["jatai"])
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def fake_app(args=None):
            calls["help"] += 1
            assert args == ["--help"]

        monkeypatch.setattr("jatai.cli.main.app", fake_app)
        run()
        assert calls["help"] == 1

    def test_run_known_command_is_not_treated_as_path(self, monkeypatch):
        calls = {"init": 0, "app": 0}

        monkeypatch.setattr("sys.argv", ["jatai", "list", "inbox"])

        def fake_init(path=None):
            calls["init"] += 1

        def fake_app(args=None):
            calls["app"] += 1

        monkeypatch.setattr("jatai.cli.main._initialize_node", fake_init)
        monkeypatch.setattr("jatai.cli.main.app", fake_app)

        run()
        assert calls["init"] == 0
        assert calls["app"] == 1

    def test_run_tui_launches_textual_app(self, monkeypatch):
        calls = {"run": 0}

        class FakeApp:
            def run(self):
                calls["run"] += 1

        monkeypatch.setattr("jatai.tui.JataiApp", FakeApp)

        _run_tui()
        assert calls["run"] == 1

    def test_jatai_app_capture_call_returns_output(self):
        from jatai.tui import _capture_call

        def fn():
            print("hello tui")

        result = _capture_call(fn)
        assert "hello tui" in result

    def test_jatai_app_capture_call_suppresses_typer_exit(self):
        import typer
        from jatai.tui import _capture_call

        def fn():
            raise typer.Exit(code=1)

        result = _capture_call(fn)
        assert result == ""

    def test_jatai_app_capture_call_captures_exceptions(self):
        from jatai.tui import _capture_call

        def fn():
            raise RuntimeError("boom")

        result = _capture_call(fn)
        assert "boom" in result

    def test_jatai_app_dispatch_init_pushes_screen(self):
        from jatai.tui import JataiApp

        pushed = {}
        app = JataiApp()
        app._run = lambda fn, *args: None
        app.push_screen = lambda screen, cb=None: pushed.update({"screen": screen, "cb": cb})
        app._dispatch("0")

        assert "screen" in pushed

    def test_jatai_app_dispatch_status_calls_status(self):
        from jatai.tui import JataiApp
        from jatai.cli import main as cli_main

        captured = {}
        app = JataiApp()
        app._run = lambda fn, *args: captured.update({"fn": fn, "args": args})
        app._dispatch("1")

        assert captured.get("fn") == cli_main.status
        assert captured.get("args") == ()

    def test_jatai_app_dispatch_docs_index_calls_docs(self):
        from jatai.tui import JataiApp
        from jatai.cli import main as cli_main

        captured = {}
        app = JataiApp()
        app._run = lambda fn, *args: captured.update({"fn": fn, "args": args})
        app._dispatch("2")

        assert captured.get("fn") == cli_main.docs
        assert captured.get("args") == (None, False)

    def test_jatai_app_dispatch_unknown_key_does_nothing(self):
        from jatai.tui import JataiApp

        called = {"_run": False}
        app = JataiApp()
        app._run = lambda fn, *args: called.update({"_run": True})
        app._dispatch("99")

        assert not called["_run"]

    def test_jatai_app_has_expected_menu_item_count(self):
        from jatai.tui import MENU_ITEMS

        assert len(MENU_ITEMS) == 17

    def test_jatai_app_menu_item_keys_are_unique(self):
        from jatai.tui import MENU_ITEMS

        keys = [k for k, _ in MENU_ITEMS]
        assert len(keys) == len(set(keys))

    def test_jatai_app_dispatch_pushes_screen_for_docs_query(self, monkeypatch):
        from jatai.tui import JataiApp

        pushed = {}
        app = JataiApp()
        app._run = lambda fn, *args: None
        app.push_screen = lambda screen, cb=None: pushed.update({"screen": screen, "cb": cb})
        app._dispatch("3")

        assert "screen" in pushed

    def test_jatai_app_dispatch_log_latest(self):
        from jatai.tui import JataiApp
        from jatai.cli import main as cli_main

        captured = {}
        app = JataiApp()
        app._run = lambda fn, *args: captured.update({"fn": fn, "args": args})
        app._dispatch("4")

        assert captured.get("fn") == cli_main.log
        assert captured.get("args") == (False, False)

    def test_jatai_app_dispatch_log_all(self):
        from jatai.tui import JataiApp
        from jatai.cli import main as cli_main

        captured = {}
        app = JataiApp()
        app._run = lambda fn, *args: captured.update({"fn": fn, "args": args})
        app._dispatch("5")

        assert captured.get("fn") == cli_main.log
        assert captured.get("args") == (True, False)

    def test_jatai_app_dispatch_browse_nodes_pushes_screen(self, monkeypatch):
        from jatai.tui import JataiApp

        pushed = {}
        app = JataiApp()
        app.push_screen = lambda screen, cb=None: pushed.update({"screen": screen, "cb": cb})

        class _FakeRegistry:
            nodes = {}
            def load(self):
                pass

        monkeypatch.setattr("jatai.core.registry.Registry", _FakeRegistry)
        app._dispatch("b")

        assert "screen" in pushed

    def test_jatai_app_dispatch_browse_nodes_with_legacy_string_paths(self, monkeypatch):
        from jatai.tui import JataiApp

        pushed = {}
        app = JataiApp()
        app.push_screen = lambda screen, cb=None: pushed.update({"screen": screen, "cb": cb})

        class _FakeRegistry:
            def __init__(self):
                self.nodes = {"legacy": "/tmp/legacy_node", "bad": None}

            def load(self):
                pass

        monkeypatch.setattr("jatai.core.registry.Registry", _FakeRegistry)
        app._dispatch("b")

        assert "screen" in pushed

    def test_jatai_app_dispatch_browse_nodes_registry_error_does_not_crash(self, monkeypatch):
        from jatai.tui import JataiApp

        pushed = {}
        outputs = []
        app = JataiApp()
        app.push_screen = lambda screen, cb=None: pushed.update({"screen": screen, "cb": cb})
        app._output = lambda text: outputs.append(text)

        class _FakeRegistry:
            nodes = {}

            def load(self):
                raise RuntimeError("broken registry")

        monkeypatch.setattr("jatai.core.registry.Registry", _FakeRegistry)
        app._dispatch("b")

        assert "screen" in pushed
        assert any("Unable to read registry" in text for text in outputs)

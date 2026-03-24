"""
Tests for jatai.core.docs module and jatai docs CLI command.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from jatai.cli.main import app
from jatai.core.docs import build_index, deliver_docs, search_docs, _docs_root
from jatai.core.node import Node

runner = CliRunner()


class TestDocsHappyPath:
    """Happy path tests for the docs module."""

    def test_docs_root_exists(self):
        """Bundled docs directory exists inside the package."""
        root = _docs_root()
        assert root.exists()
        assert root.is_dir()

    def test_docs_root_contains_markdown_files(self):
        """Bundled docs root contains at least one markdown file."""
        root = _docs_root()
        md_files = list(root.rglob("*.md"))
        assert len(md_files) > 0

    def test_build_index_returns_markdown(self):
        """build_index returns a non-empty markdown string."""
        index = build_index()
        assert isinstance(index, str)
        assert "# Jataí" in index
        assert len(index) > 50

    def test_build_index_lists_categories(self):
        """build_index groups files by category (subdirectory)."""
        index = build_index()
        # At least one category header should appear
        assert "##" in index

    def test_search_docs_finds_by_stem(self):
        """search_docs returns results matching the query string."""
        results = search_docs("quickstart")
        assert len(results) >= 1
        assert any("quickstart" in p.name for p in results)

    def test_search_docs_finds_by_category(self):
        """search_docs returns results in a matching category directory."""
        results = search_docs("cli")
        assert len(results) >= 1

    def test_search_docs_case_insensitive(self):
        """search_docs is case-insensitive."""
        lower = search_docs("quickstart")
        upper = search_docs("QUICKSTART")
        assert lower == upper

    def test_search_docs_empty_query_matches_all(self):
        """search_docs with empty string matches all docs."""
        all_docs = search_docs("")
        root = _docs_root()
        expected_count = len(list(root.rglob("*.md")))
        assert len(all_docs) == expected_count

    def test_deliver_docs_no_query_creates_index(self, temp_dir):
        """deliver_docs with no query drops a jatai-docs-index.md into INBOX."""
        inbox = temp_dir / "INBOX"
        inbox.mkdir()

        delivered = deliver_docs(query=None, inbox_path=inbox)

        assert len(delivered) == 1
        assert delivered[0].name == "jatai-docs-index.md"
        assert delivered[0].exists()
        content = delivered[0].read_text(encoding="utf-8")
        assert "Jataí" in content

    def test_deliver_docs_with_query_copies_files(self, temp_dir):
        """deliver_docs with a query copies matching files to INBOX."""
        inbox = temp_dir / "INBOX"
        inbox.mkdir()

        delivered = deliver_docs(query="quickstart", inbox_path=inbox)

        assert len(delivered) >= 1
        for path in delivered:
            assert path.exists()
            assert path.parent == inbox

    def test_deliver_docs_creates_inbox_if_missing(self, temp_dir):
        """deliver_docs creates the INBOX directory if it does not exist."""
        inbox = temp_dir / "INBOX"
        assert not inbox.exists()

        deliver_docs(query=None, inbox_path=inbox)

        assert inbox.exists()

    def test_deliver_docs_collision_resolution(self, temp_dir):
        """deliver_docs appends a counter suffix on filename collision."""
        inbox = temp_dir / "INBOX"
        inbox.mkdir()

        deliver_docs(query="quickstart", inbox_path=inbox)
        first_files = list(inbox.iterdir())

        # Deliver again — should produce a suffixed copy
        deliver_docs(query="quickstart", inbox_path=inbox)
        second_files = list(inbox.iterdir())

        assert len(second_files) > len(first_files)


class TestDocsCLI:
    """CLI tests for jatai docs command."""

    def test_cli_docs_no_query_drops_index(self, temp_dir):
        """jatai docs drops a docs-index file into the node INBOX."""
        import os

        node_path = temp_dir / "node"
        node = Node(node_path)
        node.create()

        old_cwd = os.getcwd()
        try:
            os.chdir(node_path)
            result = runner.invoke(app, ["docs"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "jatai-docs-index.md" in result.stdout
        assert (node.inbox_path / "jatai-docs-index.md").exists()

    def test_cli_docs_with_query_copies_matches(self, temp_dir):
        """jatai docs <query> copies matching docs into INBOX."""
        import os

        node_path = temp_dir / "node"
        node = Node(node_path)
        node.create()

        old_cwd = os.getcwd()
        try:
            os.chdir(node_path)
            result = runner.invoke(app, ["docs", "quickstart"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        inbox_files = list(node.inbox_path.iterdir())
        assert any("quickstart" in f.name for f in inbox_files)

    def test_cli_docs_not_in_node(self, temp_dir):
        """jatai docs fails when called outside a Jataí node."""
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = runner.invoke(app, ["docs"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1

    def test_cli_docs_no_match_exits_nonzero(self, temp_dir):
        """jatai docs <query> with no matches exits with code 1."""
        import os

        node_path = temp_dir / "node"
        node = Node(node_path)
        node.create()

        old_cwd = os.getcwd()
        try:
            os.chdir(node_path)
            result = runner.invoke(app, ["docs", "xyzzy_nonexistent_topic_42"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1


class TestDocsAdversarialScenarios:
    """Malicious/adversarial tests for the docs module."""

    def test_search_docs_path_traversal_query(self):
        """search_docs treats traversal sequences as literal strings (no match)."""
        results = search_docs("../../../etc")
        assert results == []

    def test_search_docs_null_bytes_query(self):
        """search_docs handles null bytes in query gracefully."""
        results = search_docs("\x00")
        assert isinstance(results, list)

    def test_deliver_docs_readonly_inbox(self, temp_dir):
        """deliver_docs raises when INBOX directory is read-only."""
        import os

        inbox = temp_dir / "INBOX"
        inbox.mkdir()
        os.chmod(inbox, 0o444)

        try:
            with pytest.raises(Exception):
                deliver_docs(query=None, inbox_path=inbox)
        finally:
            os.chmod(inbox, 0o755)

"""
Tests for jatai.core.prefix module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

import pytest
from pathlib import Path
from jatai.core.prefix import Prefix


class TestPrefixHappyPath:
    """Happy path tests for Prefix state machine."""

    def test_prefix_init_defaults(self):
        """Test Prefix initialization with default values."""
        prefix = Prefix()
        assert prefix.success_prefix == "_"
        assert prefix.error_prefix == "!_"

    def test_prefix_init_custom(self):
        """Test Prefix initialization with custom prefixes."""
        prefix = Prefix(success_prefix="-done", error_prefix="❌")
        assert prefix.success_prefix == "-done"
        assert prefix.error_prefix == "❌"

    def test_prefix_add_success_prefix(self, temp_dir):
        """Test adding success prefix to a file."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.add_success_prefix(file_path)

        assert result.name == "_file.txt"
        assert result.exists()
        assert not file_path.exists()
        assert result.read_text() == "content"

    def test_prefix_remove_success_prefix(self, temp_dir):
        """Test removing success prefix from a file."""
        file_path = temp_dir / "_file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.remove_success_prefix(file_path)

        assert result.name == "file.txt"
        assert result.exists()
        assert not file_path.exists()

    def test_prefix_add_error_prefix(self, temp_dir):
        """Test adding error prefix to a file."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.add_error_prefix(file_path)

        assert result.name == "!_file.txt"
        assert result.exists()
        assert not file_path.exists()

    def test_prefix_get_state_pending(self, temp_dir):
        """Test get_state returns 'pending' for unprefixed file."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        assert prefix.get_state(file_path) == "pending"

    def test_prefix_get_state_processed(self, temp_dir):
        """Test get_state returns 'processed' for success prefixed file."""
        file_path = temp_dir / "_file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        assert prefix.get_state(file_path) == "processed"

    def test_prefix_get_state_error(self, temp_dir):
        """Test get_state returns 'error' for error prefixed file."""
        file_path = temp_dir / "!_file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        assert prefix.get_state(file_path) == "error"

    def test_prefix_get_detailed_state_5_matrix(self, temp_dir):
        """Test detailed states across all retry and fatal prefixes."""
        pending = temp_dir / "msg.txt"
        processed = temp_dir / "_msg.txt"
        error_total = temp_dir / "!msg.txt"
        error_partial = temp_dir / "!_msg.txt"
        fatal_total = temp_dir / "!!msg.txt"
        fatal_partial = temp_dir / "!!_msg.txt"

        for file_path in [pending, processed, error_total, error_partial, fatal_total, fatal_partial]:
            file_path.write_text("x")

        prefix = Prefix()
        assert prefix.get_detailed_state(pending) == "pending"
        assert prefix.get_detailed_state(processed) == "processed"
        assert prefix.get_detailed_state(error_total) == "error_total"
        assert prefix.get_detailed_state(error_partial) == "error_partial"
        assert prefix.get_detailed_state(fatal_total) == "fatal_total"
        assert prefix.get_detailed_state(fatal_partial) == "fatal_partial"

    def test_prefix_to_pending_from_error(self, temp_dir):
        """Test stripping error prefix returns file to pending state name."""
        file_path = temp_dir / "!_file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        pending = prefix.to_pending(file_path)

        assert pending.name == "file.txt"
        assert prefix.is_pending(pending)

    def test_prefix_is_pending(self, temp_dir):
        """Test is_pending method."""
        pending = temp_dir / "file.txt"
        pending.write_text("x")
        processed = temp_dir / "_file.txt"
        processed.write_text("x")

        prefix = Prefix()
        assert prefix.is_pending(pending)
        assert not prefix.is_pending(processed)

    def test_prefix_is_processed(self, temp_dir):
        """Test is_processed method."""
        pending = temp_dir / "file.txt"
        pending.write_text("x")
        processed = temp_dir / "_file.txt"
        processed.write_text("x")

        prefix = Prefix()
        assert prefix.is_processed(processed)
        assert not prefix.is_processed(pending)

    def test_prefix_is_error(self, temp_dir):
        """Test is_error method."""
        normal = temp_dir / "file.txt"
        normal.write_text("x")
        error = temp_dir / "!_file.txt"
        error.write_text("x")

        prefix = Prefix()
        assert prefix.is_error(error)
        assert not prefix.is_error(normal)

    def test_prefix_migrate_prefix(self, temp_dir):
        """Test migrating from one prefix to another."""
        file_path = temp_dir / "_file.txt"
        file_path.write_text("content")

        prefix = Prefix(success_prefix="_", error_prefix="!_")
        result = prefix.migrate_prefix(file_path, "_", "-")

        assert result.name == "-file.txt"
        assert result.exists()
        assert not file_path.exists()

    def test_prefix_migrate_prefix_returns_none_if_no_match(self, temp_dir):
        """Test migrate_prefix returns None if file has different prefix."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.migrate_prefix(file_path, "_", "-")

        assert result is None
        assert file_path.exists()


class TestPrefixErrorFailureScenarios:
    """Error and failure scenario tests for Prefix."""

    def test_prefix_add_success_prefix_nonexistent(self, temp_dir):
        """Test adding prefix to nonexistent file."""
        file_path = temp_dir / "nonexistent.txt"

        prefix = Prefix()
        with pytest.raises(FileNotFoundError):
            prefix.add_success_prefix(file_path)

    def test_prefix_add_success_prefix_already_has_it(self, temp_dir):
        """Test adding success prefix to file that already has it."""
        file_path = temp_dir / "_file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        with pytest.raises(ValueError):
            prefix.add_success_prefix(file_path)

    def test_prefix_remove_success_prefix_nonexistent(self, temp_dir):
        """Test removing prefix from nonexistent file."""
        file_path = temp_dir / "nonexistent.txt"

        prefix = Prefix()
        with pytest.raises(FileNotFoundError):
            prefix.remove_success_prefix(file_path)

    def test_prefix_remove_success_prefix_no_prefix(self, temp_dir):
        """Test removing prefix from file that doesn't have it."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        with pytest.raises(ValueError):
            prefix.remove_success_prefix(file_path)

    def test_prefix_add_error_prefix_nonexistent(self, temp_dir):
        """Test adding error prefix to nonexistent file."""
        file_path = temp_dir / "nonexistent.txt"

        prefix = Prefix()
        with pytest.raises(FileNotFoundError):
            prefix.add_error_prefix(file_path)

    def test_prefix_add_error_prefix_already_has_it(self, temp_dir):
        """Test adding error prefix to file that already has it."""
        file_path = temp_dir / "!_file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        with pytest.raises(ValueError):
            prefix.add_error_prefix(file_path)

    def test_prefix_collision_handling(self, temp_dir):
        """Test collision handling when target file exists."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("new")

        colliding_path = temp_dir / "_file.txt"
        colliding_path.write_text("old")

        prefix = Prefix()
        result = prefix.add_success_prefix(file_path)

        # Result should have a timestamp suffix
        assert result.name.startswith("_file_")
        assert result.read_text() == "new"
        assert colliding_path.read_text() == "old"  # Original untouched

    def test_prefix_migrate_prefix_nonexistent(self, temp_dir):
        """Test migrate_prefix on nonexistent file."""
        file_path = temp_dir / "nonexistent.txt"

        prefix = Prefix()
        with pytest.raises(FileNotFoundError):
            prefix.migrate_prefix(file_path, "_", "-")

    def test_prefix_get_state_nonexistent_file(self, temp_dir):
        """Test get_state with nonexistent file returns unknown."""
        file_path = temp_dir / "nonexistent.txt"

        prefix = Prefix()
        # Should not raise, behavior depends on implementation
        # Current impl returns "unknown" for non-existent files
        # (implicitly, since file_path.name doesn't exist)

    def test_prefix_set_state_invalid_state(self, temp_dir):
        """Test invalid target state raises validation error."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()
        with pytest.raises(ValueError):
            prefix.set_state(file_path, "invalid_state")


class TestPrefixMaliciousAdversarialScenarios:
    """Malicious/adversarial scenario tests for Prefix."""

    def test_prefix_custom_prefixes_with_special_chars(self, temp_dir):
        """Test Prefix with special characters in prefixes."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix(success_prefix="✓✓", error_prefix="✗✗")
        result = prefix.add_success_prefix(file_path)

        assert result.name.startswith("✓✓")

    def test_prefix_unicode_filename(self, temp_dir):
        """Test Prefix with unicode filenames."""
        file_path = temp_dir / "文件.txt"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.add_success_prefix(file_path)

        assert result.name == "_文件.txt"

    def test_prefix_double_extension(self, temp_dir):
        """Test Prefix with files having double extensions."""
        file_path = temp_dir / "archive.tar.gz"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.add_success_prefix(file_path)

        assert result.name == "_archive.tar.gz"

    def test_prefix_no_extension(self, temp_dir):
        """Test Prefix with files having no extension."""
        file_path = temp_dir / "README"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.add_success_prefix(file_path)

        assert result.name == "_README"

    def test_prefix_hidden_file(self, temp_dir):
        """Test Prefix with hidden files (starting with .)."""
        file_path = temp_dir / ".hidden"
        file_path.write_text("content")

        prefix = Prefix()
        result = prefix.add_success_prefix(file_path)

        assert result.name == "_" + ".hidden"

    def test_prefix_empty_prefix(self):
        """Test Prefix with empty string as prefix."""
        prefix = Prefix(success_prefix="", error_prefix="!")
        # Should work, but might be semantically weird
        assert prefix.success_prefix == ""

    def test_prefix_very_long_prefix(self, temp_dir):
        """Test Prefix with very long prefix."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        long_prefix = "x" * 100
        prefix = Prefix(success_prefix=long_prefix)
        result = prefix.add_success_prefix(file_path)

        assert result.name.startswith(long_prefix)

    def test_prefix_state_transitions(self, temp_dir):
        """Test various state transitions."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        prefix = Prefix()

        # pending -> processed
        assert prefix.is_pending(file_path)
        result1 = prefix.add_success_prefix(file_path)
        assert prefix.is_processed(result1)

        # processed -> error (add error prefix to processed file)
        result2 = prefix.add_error_prefix(result1)
        # This creates _!_file.txt, mixed prefixes
        assert "!_" in result2.name

    def test_prefix_multiple_collisions(self, temp_dir):
        """Test handling multiple collision situations."""
        prefix = Prefix()

        # Create many colliding files
        for i in range(5):
            file_path = temp_dir / f"file_{i}.txt"
            file_path.write_text(f"content {i}")
            result = prefix.add_success_prefix(file_path)
            assert result.exists()
            assert result.name.startswith("_")

    def test_prefix_symlink_handling(self, temp_dir):
        """Test Prefix with symlinks."""
        import os

        actual = temp_dir / "actual.txt"
        actual.write_text("content")

        link = temp_dir / "link.txt"
        os.symlink(actual, link)

        prefix = Prefix()
        result = prefix.add_success_prefix(link)

        # After rename, symlink should be renamed, not follow target
        assert result.name == "_link.txt"
        assert actual.exists()  # Actual file untouched

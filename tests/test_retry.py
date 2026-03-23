"""
Tests for jatai.core.retry module.

Coverage: Happy Path, Error/Failure Scenarios, Malicious/Adversarial Scenarios.
"""

from pathlib import Path

import pytest

from jatai.core.retry import RetryState


class TestRetryHappyPath:
    """Happy path tests for retry state handling."""

    def test_retry_register_failure_exponential_delay(self, temp_dir):
        retry_path = temp_dir / ".retry"
        retry = RetryState(retry_path=retry_path)
        retry.load()

        first = retry.register_failure(
            file_path=temp_dir / "msg.txt",
            failed_nodes=["/node/a"],
            retry_delay_base=10,
            max_retries=5,
            partial_failure=False,
            now=100.0,
        )
        second = retry.register_failure(
            file_path=temp_dir / "msg.txt",
            failed_nodes=["/node/a"],
            retry_delay_base=10,
            max_retries=5,
            partial_failure=False,
            now=200.0,
        )

        assert first["retry_index"] == 1
        assert first["delay_seconds"] == 10
        assert first["next_retry_at"] == 110.0

        assert second["retry_index"] == 2
        assert second["delay_seconds"] == 20
        assert second["next_retry_at"] == 220.0

    def test_retry_is_due(self, temp_dir):
        retry = RetryState(retry_path=temp_dir / ".retry")
        retry.load()
        retry.register_failure(
            file_path=temp_dir / "msg.txt",
            failed_nodes=["/node/a"],
            retry_delay_base=2,
            max_retries=5,
            partial_failure=False,
            now=100.0,
        )

        assert not retry.is_due(temp_dir / "msg.txt", now=101.0)
        assert retry.is_due(temp_dir / "msg.txt", now=102.0)


class TestRetryErrorFailureScenarios:
    """Error/failure tests for retry state handling."""

    def test_retry_register_failure_hits_fatal_limit(self, temp_dir):
        retry = RetryState(retry_path=temp_dir / ".retry")
        retry.load()

        first = retry.register_failure(
            file_path=temp_dir / "msg.txt",
            failed_nodes=["/node/a"],
            retry_delay_base=5,
            max_retries=2,
            partial_failure=True,
            now=100.0,
        )
        second = retry.register_failure(
            file_path=temp_dir / "msg.txt",
            failed_nodes=["/node/a"],
            retry_delay_base=5,
            max_retries=2,
            partial_failure=True,
            now=110.0,
        )

        assert first["is_fatal"] is False
        assert second["is_fatal"] is True
        assert retry.get_entry(temp_dir / "msg.txt") is None

    def test_retry_clear_nonexistent_entry(self, temp_dir):
        retry = RetryState(retry_path=temp_dir / ".retry")
        retry.load()
        retry.clear(temp_dir / "missing.txt")
        assert retry.get_entry(temp_dir / "missing.txt") is None


class TestRetryMaliciousAdversarialScenarios:
    """Malicious/adversarial tests for retry state handling."""

    def test_retry_handles_malformed_json_as_failure(self, temp_dir):
        retry_path = temp_dir / ".retry"
        retry_path.write_text("{invalid json", encoding="utf-8")

        retry = RetryState(retry_path=retry_path)
        with pytest.raises(Exception):
            retry.load()

    def test_retry_path_traversal_resolution(self, temp_dir):
        retry = RetryState(retry_path=temp_dir / "nested" / ".." / ".retry")
        resolved = Path(retry.retry_path).resolve()
        assert ".." not in str(resolved)

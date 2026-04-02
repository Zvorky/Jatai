"""
Retry state management for exponential backoff delivery retries.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from filelock import FileLock, Timeout
from jatai.core.sysstate import SystemState


class RetryState:
    """Manage the global retry state file and retry scheduling metadata."""

    LOCK_TIMEOUT_SECONDS = 10

    def __init__(self, retry_path: Optional[Path] = None) -> None:
        self.retry_path = Path(retry_path) if retry_path is not None else SystemState.BASE_PATH / "retry.yaml"
        self.data: Dict[str, Dict[str, Any]] = {}

    @property
    def lock_path(self) -> Path:
        return Path(f"{self.retry_path}.lock")

    def _lock(self) -> FileLock:
        self.retry_path.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self.lock_path), timeout=self.LOCK_TIMEOUT_SECONDS)

    def load(self) -> None:
        try:
            with self._lock():
                if not self.retry_path.exists():
                    self.data = {}
                    return
                content = self.retry_path.read_text(encoding="utf-8").strip()
                if not content:
                    self.data = {}
                    return
                parsed = json.loads(content)
                self.data = parsed if isinstance(parsed, dict) else {}
        except Timeout as exc:
            raise TimeoutError(f"Retry state lock timeout for {self.retry_path}: {exc}") from exc

    def save(self) -> None:
        try:
            with self._lock():
                self.retry_path.parent.mkdir(parents=True, exist_ok=True)
                self.retry_path.write_text(
                    json.dumps(self.data, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
        except Timeout as exc:
            raise TimeoutError(f"Retry state lock timeout for {self.retry_path}: {exc}") from exc

    @staticmethod
    def _key(file_path: Path) -> str:
        return str(Path(file_path).resolve())

    def get_entry(self, file_path: Path) -> Optional[Dict[str, Any]]:
        return self.data.get(self._key(file_path))

    def clear(self, file_path: Path) -> None:
        self.data.pop(self._key(file_path), None)

    def is_due(self, file_path: Path, now: Optional[float] = None) -> bool:
        entry = self.get_entry(file_path)
        if not entry:
            return False
        current_time = time.time() if now is None else now
        return current_time >= float(entry.get("next_retry_at", 0))

    def register_failure(
        self,
        file_path: Path,
        failed_nodes: List[str],
        retry_delay_base: int,
        max_retries: int,
        partial_failure: bool,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Register a failed attempt and return scheduling/result metadata."""
        current_time = time.time() if now is None else now
        key = self._key(file_path)
        previous = self.data.get(key, {})

        retry_index = int(previous.get("retry_index", 0))
        next_index = retry_index + 1
        # Retry semantics: 1 original attempt + MAX_RETRIES retries.
        # Fatal state is reached only after exceeding MAX_RETRIES.
        is_fatal = next_index > int(max_retries)

        result: Dict[str, Any] = {
            "retry_index": next_index,
            "failed_nodes": list(failed_nodes),
            "partial_failure": bool(partial_failure),
            "is_fatal": is_fatal,
        }

        if is_fatal:
            self.clear(file_path)
            return result

        delay_seconds = int(retry_delay_base) * (2 ** (next_index - 1))
        next_retry_at = float(current_time + delay_seconds)
        self.data[key] = {
            "retry_index": next_index,
            "failed_nodes": list(failed_nodes),
            "next_retry_at": next_retry_at,
            "delay_seconds": delay_seconds,
            "partial_failure": bool(partial_failure),
        }
        result["next_retry_at"] = next_retry_at
        result["delay_seconds"] = delay_seconds
        return result

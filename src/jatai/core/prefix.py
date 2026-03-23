"""
Prefix module: Implements the state machine using file name prefixes.

The prefix philosophy:
- No prefix: Pending file, Jataí acts immediately
- Success prefix (_): Processed/being written, Jataí ignores
- Error prefix (!_): Failed transfer, requires retry or manual intervention
"""

from pathlib import Path
from typing import Dict, Optional


class Prefix:
    """Manages file state using configurable name prefixes."""

    def __init__(
        self,
        success_prefix: str = "_",
        error_prefix: str = "!_",
    ):
        """
        Initialize Prefix state machine.

        Args:
            success_prefix: Prefix for processed/written files (default: _)
            error_prefix: Prefix for failed files (default: !_)
        """
        self.success_prefix = success_prefix
        self.error_prefix = error_prefix
        self.error_total_prefix = self._normalize_error_total_prefix(error_prefix)
        self.error_partial_prefix = f"{self.error_total_prefix}_"
        self.fatal_total_prefix = f"{self.error_total_prefix}{self.error_total_prefix}"
        self.fatal_partial_prefix = f"{self.fatal_total_prefix}_"

    @staticmethod
    def _normalize_error_total_prefix(error_prefix: str) -> str:
        """Normalize configured error prefix to the base total-error prefix."""
        if not error_prefix:
            return "!"
        normalized = error_prefix.rstrip("_")
        return normalized or "!"

    def state_prefixes(self) -> Dict[str, str]:
        """Return the complete 5-state prefix matrix."""
        return {
            "processed": self.success_prefix,
            "error_total": self.error_total_prefix,
            "error_partial": self.error_partial_prefix,
            "fatal_total": self.fatal_total_prefix,
            "fatal_partial": self.fatal_partial_prefix,
        }

    def get_detailed_state(self, file_path: Path) -> str:
        """Return detailed state among pending/processed/error/fatal states."""
        file_name = file_path.name

        if file_name.startswith(self.fatal_partial_prefix):
            return "fatal_partial"
        if file_name.startswith(self.fatal_total_prefix):
            return "fatal_total"
        if file_name.startswith(self.error_partial_prefix):
            return "error_partial"
        if file_name.startswith(self.error_total_prefix):
            return "error_total"
        if file_name.startswith(self.success_prefix):
            return "processed"
        return "pending"

    def _strip_known_prefix(self, file_name: str) -> str:
        for prefix in sorted(self.state_prefixes().values(), key=len, reverse=True):
            if prefix and file_name.startswith(prefix):
                return file_name[len(prefix) :]
        return file_name

    def canonical_retry_path(self, file_path: Path) -> Path:
        """Return retry key path normalized to the pending filename."""
        return file_path.parent / self._strip_known_prefix(file_path.name)

    def set_state(self, file_path: Path, state: str) -> Path:
        """Set the file to a specific state by replacing any known prefix."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        prefix_map = self.state_prefixes()
        if state == "pending":
            target_prefix = ""
        elif state in prefix_map:
            target_prefix = prefix_map[state]
        else:
            raise ValueError(f"Unknown state: {state}")

        base_name = self._strip_known_prefix(file_path.name)
        target_name = f"{target_prefix}{base_name}"
        target_path = file_path.parent / target_name

        if target_path.exists() and target_path != file_path:
            import time

            suffix = f"_{int(time.time() * 1000)}"
            base_path = Path(base_name)
            target_name = f"{target_prefix}{base_path.stem}{suffix}{''.join(base_path.suffixes)}"
            target_path = file_path.parent / target_name

        if target_path == file_path:
            return file_path

        file_path.rename(target_path)
        return target_path

    def to_pending(self, file_path: Path) -> Path:
        """Remove any state prefix and return file to pending state."""
        return self.set_state(file_path, "pending")

    def add_success_prefix(self, file_path: Path) -> Path:
        """
        Add success prefix to a file (mark as processed).

        Args:
            file_path: Path to the file

        Returns:
            New path with prefix added

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file already has success prefix
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.name.startswith(self.success_prefix):
            raise ValueError(f"File already has success prefix: {file_path}")
        return self.set_state(file_path, "processed")

    def remove_success_prefix(self, file_path: Path) -> Path:
        """
        Remove success prefix from a file (mark as unprocessed).

        Args:
            file_path: Path to the file

        Returns:
            New path with prefix removed

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file doesn't have success prefix
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.name.startswith(self.success_prefix):
            raise ValueError(f"File doesn't have success prefix: {file_path}")

        return self.to_pending(file_path)

    def add_error_prefix(self, file_path: Path) -> Path:
        """
        Add error prefix to a file (mark as failed).

        Args:
            file_path: Path to the file

        Returns:
            New path with error prefix added

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file already has error prefix
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.name.startswith(self.error_prefix):
            raise ValueError(f"File already has error prefix: {file_path}")
        # Compatibility path: keep semantics of the configured error prefix.
        target_state = "error_partial" if self.error_prefix.endswith("_") else "error_total"
        return self.set_state(file_path, target_state)

    def get_state(self, file_path: Path) -> str:
        """
        Get the state of a file based on its prefix.

        Args:
            file_path: Path to check

        Returns:
            "pending", "processed", "error", or "unknown"
        """
        state = self.get_detailed_state(file_path)
        if state == "processed":
            return "processed"
        if state == "pending":
            return "pending"
        return "error"

    def is_pending(self, file_path: Path) -> bool:
        """Check if file is pending (no prefix)."""
        return self.get_state(file_path) == "pending"

    def is_processed(self, file_path: Path) -> bool:
        """Check if file is processed (success prefix)."""
        return self.get_state(file_path) == "processed"

    def is_error(self, file_path: Path) -> bool:
        """Check if file has error state (error prefix)."""
        return self.get_state(file_path) == "error"

    def is_retryable_error(self, file_path: Path) -> bool:
        """Check if file is in a non-fatal error state eligible for retry."""
        return self.get_detailed_state(file_path) in {"error_total", "error_partial"}

    def is_fatal_error(self, file_path: Path) -> bool:
        """Check if file is in a fatal error state."""
        return self.get_detailed_state(file_path) in {"fatal_total", "fatal_partial"}

    def migrate_prefix(
        self,
        file_path: Path,
        old_prefix: str,
        new_prefix: str,
    ) -> Optional[Path]:
        """
        Migrate a file from old prefix to new prefix (hot-swap).

        Args:
            file_path: Path to the file
            old_prefix: The old prefix to replace
            new_prefix: The new prefix to use

        Returns:
            New path after migration, or None if file didn't have old prefix

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = file_path.name

        if not file_name.startswith(old_prefix):
            return None

        # Remove old prefix and add new one
        name_without_prefix = file_name[len(old_prefix) :]
        new_name = new_prefix + name_without_prefix
        new_path = file_path.parent / new_name

        # Handle collision
        if new_path.exists():
            import time
            suffix = f"_{int(time.time() * 1000)}"
            stem = Path(name_without_prefix).stem
            suffixes = "".join(Path(name_without_prefix).suffixes)
            new_name = new_prefix + stem + suffix + suffixes
            new_path = file_path.parent / new_name

        file_path.rename(new_path)
        return new_path

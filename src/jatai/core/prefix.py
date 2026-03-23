"""
Prefix module: Implements the state machine using file name prefixes.

The prefix philosophy:
- No prefix: Pending file, Jataí acts immediately
- Success prefix (_): Processed/being written, Jataí ignores
- Error prefix (!_): Failed transfer, requires retry or manual intervention
"""

from pathlib import Path
from typing import Optional, Tuple


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

        new_name = self.success_prefix + file_path.name
        new_path = file_path.parent / new_name

        # Handle collision: if new path exists, append timestamp or unique suffix
        if new_path.exists():
            import time
            suffix = f"_{int(time.time() * 1000)}"
            new_name = self.success_prefix + file_path.stem + suffix + "".join(file_path.suffixes)
            new_path = file_path.parent / new_name

        file_path.rename(new_path)
        return new_path

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

        new_name = file_path.name[len(self.success_prefix) :]
        new_path = file_path.parent / new_name

        file_path.rename(new_path)
        return new_path

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

        new_name = self.error_prefix + file_path.name
        new_path = file_path.parent / new_name

        # Handle collision with timestamp
        if new_path.exists():
            import time
            suffix = f"_{int(time.time() * 1000)}"
            new_name = (
                self.error_prefix
                + file_path.stem
                + suffix
                + "".join(file_path.suffixes)
            )
            new_path = file_path.parent / new_name

        file_path.rename(new_path)
        return new_path

    def get_state(self, file_path: Path) -> str:
        """
        Get the state of a file based on its prefix.

        Args:
            file_path: Path to check

        Returns:
            "pending", "processed", "error", or "unknown"
        """
        file_name = file_path.name

        if file_name.startswith(self.error_prefix):
            return "error"
        elif file_name.startswith(self.success_prefix):
            return "processed"
        else:
            return "pending"

    def is_pending(self, file_path: Path) -> bool:
        """Check if file is pending (no prefix)."""
        return self.get_state(file_path) == "pending"

    def is_processed(self, file_path: Path) -> bool:
        """Check if file is processed (success prefix)."""
        return self.get_state(file_path) == "processed"

    def is_error(self, file_path: Path) -> bool:
        """Check if file has error state (error prefix)."""
        return self.get_state(file_path) == "error"

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

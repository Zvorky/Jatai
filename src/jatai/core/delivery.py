"""
Delivery module: Handles physical file copying with atomic delivery using temporary extensions.
"""

import shutil
from pathlib import Path
from typing import Optional


class Delivery:
    """Handles atomic file delivery using temporary .tmp extensions."""

    TMP_EXTENSION = ".tmp"

    @staticmethod
    def _split_name_and_suffix(file_name: str) -> tuple[str, str]:
        """Split a filename into stem and full suffix string."""
        path = Path(file_name)
        suffix = "".join(path.suffixes)
        if suffix:
            stem = file_name[: -len(suffix)]
        else:
            stem = file_name
        return stem, suffix

    def _resolve_collision(self, target_path: Path) -> Path:
        """Return a non-conflicting destination by appending ` (n)` when needed."""
        if not target_path.exists():
            return target_path

        stem, suffix = self._split_name_and_suffix(target_path.name)
        index = 1
        while True:
            candidate = target_path.parent / f"{stem} ({index}){suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def __init__(self, source_path: Path, destination_path: Path):
        """
        Initialize Delivery handler.

        Args:
            source_path: Path to the source file
            destination_path: Path to the destination directory for the file
        """
        self.source_path = Path(source_path)
        self.destination_path = Path(destination_path)

        if not self.source_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_path}")

        if not self.destination_path.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {self.destination_path}")

    def deliver(self) -> Path:
        """
        Perform atomic delivery: copy file with .tmp extension, then rename to final name.

        This prevents race conditions where destination processes might read incomplete
        or partial files.

        Returns:
            Path to the delivered file

        Raises:
            IOError: If copy or rename operations fail
            shutil.SameFileError: If source and destination are the same file
        """
        # Build intermediate and final paths
        file_name = self.source_path.name
        final_file_path = self._resolve_collision(self.destination_path / file_name)
        tmp_file_path = final_file_path.parent / (final_file_path.name + self.TMP_EXTENSION)

        try:
            # Step 1: Copy to temporary file
            shutil.copy2(self.source_path, tmp_file_path)

            # Step 2: Atomic rename to final name
            # If destination exists, it will be replaced (on most systems)
            tmp_file_path.rename(final_file_path)

            return final_file_path

        except (IOError, OSError) as e:
            # Cleanup: remove temporary file if it exists
            if tmp_file_path.exists():
                try:
                    tmp_file_path.unlink()
                except Exception:
                    pass
            raise IOError(f"Delivery failed: {e}")

    @staticmethod
    def has_ignore_prefix(
        file_path: Path, ignore_prefix: str = "_", success_prefix: Optional[str] = None
    ) -> bool:
        """
        Check if a file has the ignore prefix (was processed or is being written).

        Args:
            file_path: Path to check
            ignore_prefix: Fallback prefix indicating file is ignored/processed
            success_prefix: Optional explicit prefix name (used by callers)

        Returns:
            True if file has the ignore prefix, False otherwise
        """
        if not file_path.exists():
            return False
        prefix = success_prefix if success_prefix is not None else ignore_prefix
        return file_path.name.startswith(prefix)

"""
Delivery module: Handles physical file copying with atomic delivery using temporary extensions.
"""

import shutil
from pathlib import Path
from typing import Optional


class Delivery:
    """Handles atomic file delivery using temporary .tmp extensions."""

    TMP_EXTENSION = ".tmp"

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
        tmp_file_path = self.destination_path / (file_name + self.TMP_EXTENSION)
        final_file_path = self.destination_path / file_name

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

    def deliver_copy_to_outbox(self, outbox_path: Path) -> Path:
        """
        Copy a file to OUTBOX (used when file needs to be broadcasted).

        Args:
            outbox_path: Path to the OUTBOX directory

        Returns:
            Path to the copied file in OUTBOX

        Raises:
            NotADirectoryError: If outbox_path is not a directory
        """
        if not outbox_path.is_dir():
            raise NotADirectoryError(f"OUTBOX is not a directory: {outbox_path}")

        self.destination_path = outbox_path
        return self.deliver()

    @staticmethod
    def is_being_written(file_path: Path, success_prefix: str = "_") -> bool:
        """
        Check if a file is currently being written (has success prefix).

        Args:
            file_path: Path to check
            success_prefix: Prefix indicating file is being written

        Returns:
            True if file has the success prefix, False otherwise
        """
        if not file_path.exists():
            return False
        return file_path.name.startswith(success_prefix)

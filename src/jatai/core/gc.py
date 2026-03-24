"""
Garbage Collection module: Automatic cleanup of processed (_) files.

GC is triggered by the daemon at startup and on each watchdog cycle.
Configuration keys (per node, can be set globally or locally):
  GC_ENABLED       - bool, default False. Set to true to enable.
  GC_MAX_AGE_DAYS  - float, default 30. Delete _ files older than N days.
  GC_MAX_FILES     - int, default 0. Keep at most N _ files per folder (0 = unlimited).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List


_DEFAULT_GC_ENABLED = False
_DEFAULT_MAX_AGE_DAYS = 30.0
_DEFAULT_MAX_FILES = 0


def _is_processed(file_path: Path, success_prefix: str) -> bool:
    """Return True if the file has the success prefix."""
    return file_path.name.startswith(success_prefix) if success_prefix else False


def _file_age_days(file_path: Path, now: float) -> float:
    """Return the age of the file in days based on its modification time."""
    try:
        mtime = file_path.stat().st_mtime
        return (now - mtime) / 86400.0
    except OSError:
        return 0.0


def collect_garbage(
    directory: Path,
    success_prefix: str = "_",
    max_age_days: float = _DEFAULT_MAX_AGE_DAYS,
    max_files: int = _DEFAULT_MAX_FILES,
    now: float | None = None,
) -> List[Path]:
    """Delete processed files in *directory* that exceed the configured thresholds.

    Applies age-based deletion first, then count-based trimming (oldest first).

    Args:
        directory: INBOX or OUTBOX directory to clean.
        success_prefix: The prefix identifying processed files.
        max_age_days: Remove processed files older than this many days (0 = disabled).
        max_files: Keep at most this many processed files (0 = unlimited).
        now: Override current time (seconds since epoch) for testing.

    Returns:
        List of removed file paths.
    """
    if not directory.exists():
        return []

    current_time = time.time() if now is None else now
    removed: List[Path] = []

    processed_files = sorted(
        [f for f in directory.iterdir() if f.is_file() and _is_processed(f, success_prefix)],
        key=lambda f: f.stat().st_mtime,
    )

    # Age-based deletion
    if max_age_days > 0:
        for file_path in list(processed_files):
            if _file_age_days(file_path, current_time) > max_age_days:
                try:
                    file_path.unlink()
                    removed.append(file_path)
                    processed_files.remove(file_path)
                except OSError:
                    pass

    # Count-based trimming (remove oldest first)
    if max_files > 0:
        while len(processed_files) > max_files:
            oldest = processed_files.pop(0)
            if not oldest.exists():
                continue
            try:
                oldest.unlink()
                removed.append(oldest)
            except OSError:
                pass

    return removed


def run_gc_for_node(
    inbox_path: Path,
    outbox_path: Path,
    node_config: Dict[str, Any],
    now: float | None = None,
) -> List[Path]:
    """Run garbage collection for a single node based on its configuration.

    Returns the list of all removed paths.
    """
    gc_enabled = str(node_config.get("GC_ENABLED", _DEFAULT_GC_ENABLED)).lower()
    if gc_enabled not in ("true", "1", "yes"):
        return []

    success_prefix = str(node_config.get("PREFIX_PROCESSED", "_"))

    try:
        max_age_days = float(node_config.get("GC_MAX_AGE_DAYS", _DEFAULT_MAX_AGE_DAYS))
    except (TypeError, ValueError):
        max_age_days = _DEFAULT_MAX_AGE_DAYS

    try:
        max_files = int(node_config.get("GC_MAX_FILES", _DEFAULT_MAX_FILES))
    except (TypeError, ValueError):
        max_files = _DEFAULT_MAX_FILES

    removed: List[Path] = []
    for directory in (inbox_path, outbox_path):
        removed.extend(
            collect_garbage(
                directory=directory,
                success_prefix=success_prefix,
                max_age_days=max_age_days,
                max_files=max_files,
                now=now,
            )
        )
    return removed

"""Utilities for optional uninstall cleanup workflows."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Set

from jatai.core.registry import Registry
from jatai.core.sysstate import SystemState


def _normalize_removed_entry(entry: str) -> str:
    """Return the path part from removed.yaml entries."""
    return str(entry).split(" --autoremoved", 1)[0].strip()


def _collect_known_node_paths(registry: Registry) -> Set[Path]:
    """Collect node paths from global registry and removed.yaml."""
    node_paths: Set[Path] = set()

    for node_data in registry.nodes.values():
        node_path = node_data.get("path")
        if node_path:
            node_paths.add(Path(str(node_path)).resolve())

    removed_entries = SystemState.read_yaml(SystemState.removed_path())
    for entry in removed_entries if isinstance(removed_entries, list) else []:
        if not isinstance(entry, str):
            continue
        clean_path = _normalize_removed_entry(entry)
        if clean_path:
            node_paths.add(Path(clean_path).resolve())

    return node_paths


def cleanup_install_artifacts(remove_logs: bool = False, dry_run: bool = False) -> List[str]:
    """
    Remove Jatai configuration/control artifacts while preserving message data.

    The cleanup keeps INBOX/OUTBOX contents untouched and removes:
    - local .jatai and ._jatai files for known nodes
    - global ~/.jatai registry file
    - /tmp/jatai control state (optionally preserving logs)

    Args:
        remove_logs: If True, also remove /tmp/jatai/logs.
        dry_run: If True, only report actions without applying them.

    Returns:
        Human-readable list of actions taken/planned.
    """
    actions: List[str] = []
    registry = Registry()

    try:
        registry.load()
    except FileNotFoundError:
        actions.append(f"skip missing global config: {registry.registry_path}")

    node_paths = _collect_known_node_paths(registry)

    for node_path in sorted(node_paths):
        for local_name in (".jatai", "._jatai"):
            local_path = node_path / local_name
            if local_path.exists():
                actions.append(f"remove local config: {local_path}")
                if not dry_run:
                    local_path.unlink()

    if registry.registry_path.exists():
        actions.append(f"remove global config: {registry.registry_path}")
        if not dry_run:
            registry.registry_path.unlink()

    state_root = SystemState.BASE_PATH
    if state_root.exists():
        for child in sorted(state_root.iterdir()):
            if child.name == "logs" and not remove_logs:
                actions.append(f"keep logs directory: {child}")
                continue

            if child.is_dir() and not child.is_symlink():
                actions.append(f"remove tmp directory: {child}")
                if not dry_run:
                    shutil.rmtree(child, ignore_errors=True)
            else:
                actions.append(f"remove tmp file: {child}")
                if not dry_run:
                    child.unlink(missing_ok=True)

        if not dry_run:
            try:
                next(state_root.iterdir())
            except StopIteration:
                state_root.rmdir()
                actions.append(f"remove empty tmp root: {state_root}")

    return actions

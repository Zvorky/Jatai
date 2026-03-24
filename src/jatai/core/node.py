"""
Node module: Represents a single Jataí node with INBOX and OUTBOX folders.
"""

import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class Node:
    """Represents a Jataí node with INBOX and OUTBOX directories."""

    LOCAL_CONFIG_FILENAME = ".jatai"
    LOCAL_CONFIG_DISABLED = "._jatai"
    LOCAL_CONFIG_BACKUP = ".jatai.bkp"
    INBOX_DIRNAME = "INBOX"
    OUTBOX_DIRNAME = "OUTBOX"
    PREFIX_KEYS = ("PREFIX_PROCESSED", "PREFIX_ERROR")

    HELLOWORLD_FILENAME = "!helloworld.md"
    HELLOWORLD_CONTENT = """\
# Welcome to Jataí 🐝

This file was automatically dropped into your INBOX as part of onboarding.

## What is Jataí?

Jataí is a local file-system message bus. It connects scripts and AI agents
using standardized INBOX/OUTBOX folders, without complex APIs or sockets.

## How it works

- Drop a file into your **OUTBOX** and Jataí routes it to all other nodes.
- Files arrive in the **INBOX** folders of all registered nodes.
- File prefixes indicate message state:
  - `_file` = delivered / processed
  - `!file` or `!_file` = delivery error (retry pending)
  - `!!file` or `!!_file` = fatal error (max retries reached)

## Getting started

1. Initialize a node: `jatai init [path]`
2. Start the daemon:  `jatai start`
3. Check node status: `jatai status`
4. Browse docs:       `jatai docs`
5. See all commands:  `jatai --help`

Happy messaging! 🐝
"""

    def __init__(self, node_path: Path):
        """
        Initialize a Node instance.

        Args:
            node_path: Path to the node directory
        """
        self.node_path = Path(node_path).resolve()
        self.inbox_path = self.node_path / self.INBOX_DIRNAME
        self.outbox_path = self.node_path / self.OUTBOX_DIRNAME
        self.local_config_path = self.node_path / self.LOCAL_CONFIG_FILENAME
        self.disabled_config_path = self.node_path / self.LOCAL_CONFIG_DISABLED
        self.backup_config_path = self.node_path / self.LOCAL_CONFIG_BACKUP
        self.local_config: Dict[str, Any] = {}

    @staticmethod
    def validate_inbox_outbox_overlap(inbox_path: Path, outbox_path: Path) -> None:
        """Ensure INBOX and OUTBOX paths are different to avoid loops."""
        if inbox_path.resolve() == outbox_path.resolve():
            raise ValueError(
                "INBOX and OUTBOX cannot point to the same directory. "
                "Use separate paths to avoid broadcast loops."
            )

    def create(
        self,
        global_config: Optional[Dict[str, Any]] = None,
        inbox_path: Optional[Path] = None,
        outbox_path: Optional[Path] = None,
    ) -> None:
        """
        Create the node structure (node dir, INBOX, OUTBOX, .jatai config).

        Args:
            global_config: Global config to copy into local .jatai
        """
        # Create node directory
        self.node_path.mkdir(parents=True, exist_ok=True)

        if inbox_path is None:
            inbox_path = self.inbox_path
        else:
            inbox_path = Path(inbox_path)

        if outbox_path is None:
            outbox_path = self.outbox_path
        else:
            outbox_path = Path(outbox_path)

        self.validate_inbox_outbox_overlap(inbox_path, outbox_path)

        self.inbox_path = inbox_path
        self.outbox_path = outbox_path

        # Create INBOX and OUTBOX
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.outbox_path.mkdir(parents=True, exist_ok=True)

        # Create local config file
        local_config = {
            "node_path": str(self.node_path),
            "INBOX_DIR": str(self.inbox_path),
            "OUTBOX_DIR": str(self.outbox_path),
        }

        if global_config:
            # Copy relevant global config to local (allow override)
            for key in [
                "PREFIX_PROCESSED",
                "PREFIX_ERROR",
                "RETRY_DELAY_BASE",
            ]:
                if key in global_config:
                    local_config[key] = global_config[key]

        self.local_config = local_config
        self.save_config()

    def load_config(self) -> None:
        """
        Load local .jatai configuration from disk.

        Raises:
            FileNotFoundError: If .jatai doesn't exist
            yaml.YAMLError: If .jatai is malformed
        """
        if not self.local_config_path.exists():
            raise FileNotFoundError(f"Local config not found: {self.local_config_path}")

        try:
            with open(self.local_config_path, "r") as f:
                self.local_config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse local config: {e}")

    def load_any_config(self) -> None:
        """Load either enabled or disabled local configuration from disk."""
        config_path = self.local_config_path
        if not config_path.exists():
            config_path = self.disabled_config_path
        if not config_path.exists():
            raise FileNotFoundError(
                f"Local config not found: {self.local_config_path} or {self.disabled_config_path}"
            )

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.local_config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse local config: {e}")

    def apply_effective_config(self, global_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge global defaults with local overrides and update resolved paths."""
        effective_config = dict(global_config or {})
        effective_config.update(self.local_config)
        self.local_config = effective_config

        inbox_value = effective_config.get("INBOX_DIR", self.INBOX_DIRNAME)
        outbox_value = effective_config.get("OUTBOX_DIR", self.OUTBOX_DIRNAME)

        self.inbox_path = self._resolve_configured_path(inbox_value, self.node_path / self.INBOX_DIRNAME)
        self.outbox_path = self._resolve_configured_path(outbox_value, self.node_path / self.OUTBOX_DIRNAME)
        self.validate_inbox_outbox_overlap(self.inbox_path, self.outbox_path)
        return self.local_config

    def _resolve_configured_path(self, value: Any, default_path: Path) -> Path:
        if not value:
            return default_path
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return self.node_path / candidate

    def save_config(self) -> None:
        """Save local configuration to .jatai file."""
        with open(self.local_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.local_config, f, default_flow_style=False)

    def write_config(self, config: Dict[str, Any], target_path: Optional[Path] = None) -> None:
        """Write a configuration mapping to the target path."""
        destination = target_path or self.local_config_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False)

    def backup_current_config(self, previous_config: Optional[Dict[str, Any]] = None) -> Path:
        """Persist the current or provided config into .jatai.bkp."""
        if previous_config is None:
            if self.local_config_path.exists():
                shutil.copy2(self.local_config_path, self.backup_config_path)
            elif self.disabled_config_path.exists():
                shutil.copy2(self.disabled_config_path, self.backup_config_path)
            else:
                raise FileNotFoundError("Cannot create backup without an existing config")
        else:
            self.write_config(previous_config, self.backup_config_path)
        return self.backup_config_path

    def restore_backup(self) -> None:
        """Restore .jatai from .jatai.bkp."""
        if not self.backup_config_path.exists():
            raise FileNotFoundError(f"Backup config not found: {self.backup_config_path}")

        shutil.copy2(self.backup_config_path, self.local_config_path)
        self.load_config()

    def is_enabled(self) -> bool:
        """
        Check if node is enabled (i.e., .jatai exists and not .jatai -> ._jatai).

        Returns:
            True if node is enabled, False otherwise
        """
        return self.local_config_path.exists()

    def is_disabled(self) -> bool:
        """
        Check if node is disabled (i.e., ._jatai exists).

        Returns:
            True if node is disabled, False otherwise
        """
        return self.disabled_config_path.exists()

    def disable(self) -> None:
        """
        Disable the node by renaming .jatai to ._jatai (soft-delete).

        Raises:
            FileNotFoundError: If .jatai doesn't exist
        """
        if not self.local_config_path.exists():
            raise FileNotFoundError(f"Cannot disable: {self.local_config_path} not found")

        self.local_config_path.rename(self.disabled_config_path)

    def enable(self) -> None:
        """
        Enable the node by renaming ._jatai back to .jatai (reactivation).

        Raises:
            FileNotFoundError: If ._jatai doesn't exist
        """
        if not self.disabled_config_path.exists():
            raise FileNotFoundError(f"Cannot enable: {self.disabled_config_path} not found")

        self.disabled_config_path.rename(self.local_config_path)
        self.load_config()

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value from local config.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.local_config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """
        Set configuration value in local config and save to disk.

        Args:
            key: Configuration key
            value: Configuration value
        """
        self.local_config[key] = value
        self.save_config()

    def list_inbox(self) -> list[Path]:
        """
        List all files in INBOX.

        Returns:
            List of file paths in INBOX
        """
        if not self.inbox_path.exists():
            return []
        return [f for f in self.inbox_path.iterdir() if f.is_file()]

    def list_outbox(self) -> list[Path]:
        """
        List all files in OUTBOX.

        Returns:
            List of file paths in OUTBOX
        """
        if not self.outbox_path.exists():
            return []
        return [f for f in self.outbox_path.iterdir() if f.is_file()]

    def migrate_prefix_history(
        self,
        previous_config: Dict[str, Any],
        current_config: Dict[str, Any],
    ) -> bool:
        """Rename local historical files when prefix values change."""
        rename_plan: list[tuple[Path, Path]] = []
        processed_keys = []

        for key in self.PREFIX_KEYS:
            old_prefix = str(previous_config.get(key, ""))
            new_prefix = str(current_config.get(key, ""))
            if not old_prefix or old_prefix == new_prefix:
                continue
            processed_keys.append((old_prefix, new_prefix))

        if not processed_keys:
            return False

        for directory in (self.inbox_path, self.outbox_path):
            if not directory.exists():
                continue
            for file_path in sorted(directory.iterdir()):
                if not file_path.is_file():
                    continue
                target_name = file_path.name
                for old_prefix, new_prefix in sorted(processed_keys, key=lambda item: len(item[0]), reverse=True):
                    if target_name.startswith(old_prefix):
                        target_name = new_prefix + target_name[len(old_prefix) :]
                        break
                if target_name == file_path.name:
                    continue
                target_path = file_path.parent / target_name
                if target_path.exists() and target_path != file_path:
                    raise FileExistsError(f"Prefix migration collision for {target_path}")
                rename_plan.append((file_path, target_path))

        completed: list[tuple[Path, Path]] = []
        try:
            for source_path, target_path in rename_plan:
                source_path.rename(target_path)
                completed.append((source_path, target_path))
        except Exception:
            for source_path, target_path in reversed(completed):
                if target_path.exists():
                    target_path.rename(source_path)
            raise

        return bool(rename_plan)

    def drop_helloworld(self) -> Optional[Path]:
        """Drop the !helloworld.md tutorial file into the INBOX if not already present."""
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        target = self.inbox_path / self.HELLOWORLD_FILENAME
        if target.exists():
            return None
        target.write_text(self.HELLOWORLD_CONTENT, encoding="utf-8")
        return target

    def onboard(
        self,
        global_config: Optional[Dict[str, Any]] = None,
        inbox_path: Optional[Path] = None,
        outbox_path: Optional[Path] = None,
    ) -> bool:
        """Create missing node structure (INBOX, OUTBOX, .jatai) and drop helloworld.

        Returns True if the node was newly created/onboarded, False if it already existed.
        """
        if self.is_enabled() or self.is_disabled():
            return False

        self.create(
            global_config=global_config,
            inbox_path=inbox_path,
            outbox_path=outbox_path,
        )
        self.drop_helloworld()
        return True

    def drop_error_notice(self, message: str, error_prefix: Optional[str] = None) -> Path:
        """Write an error notice into the INBOX for manual inspection."""
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        prefix = error_prefix if error_prefix is not None else str(self.local_config.get("PREFIX_ERROR", "!_"))
        notice_path = self.inbox_path / f"{prefix}config-migration-error.md"
        suffix = 1
        while notice_path.exists():
            notice_path = self.inbox_path / f"{prefix}config-migration-error ({suffix}).md"
            suffix += 1
        notice_path.write_text(message, encoding="utf-8")
        return notice_path

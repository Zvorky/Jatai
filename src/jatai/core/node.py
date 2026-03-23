"""
Node module: Represents a single Jataí node with INBOX and OUTBOX folders.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Node:
    """Represents a Jataí node with INBOX and OUTBOX directories."""

    LOCAL_CONFIG_FILENAME = ".jatai"
    LOCAL_CONFIG_DISABLED = "._jatai"
    INBOX_DIRNAME = "INBOX"
    OUTBOX_DIRNAME = "OUTBOX"

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

    def save_config(self) -> None:
        """Save local configuration to .jatai file."""
        with open(self.local_config_path, "w") as f:
            yaml.safe_dump(self.local_config, f, default_flow_style=False)

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
        disabled_config_path = self.node_path / self.LOCAL_CONFIG_DISABLED
        return disabled_config_path.exists()

    def disable(self) -> None:
        """
        Disable the node by renaming .jatai to ._jatai (soft-delete).

        Raises:
            FileNotFoundError: If .jatai doesn't exist
        """
        if not self.local_config_path.exists():
            raise FileNotFoundError(f"Cannot disable: {self.local_config_path} not found")

        disabled_path = self.node_path / self.LOCAL_CONFIG_DISABLED
        self.local_config_path.rename(disabled_path)

    def enable(self) -> None:
        """
        Enable the node by renaming ._jatai back to .jatai (reactivation).

        Raises:
            FileNotFoundError: If ._jatai doesn't exist
        """
        disabled_path = self.node_path / self.LOCAL_CONFIG_DISABLED
        if not disabled_path.exists():
            raise FileNotFoundError(f"Cannot enable: {disabled_path} not found")

        disabled_path.rename(self.local_config_path)
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

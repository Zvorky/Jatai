"""
Registry module: Manages the global ~/.jatai file containing all registered node paths.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any


class Registry:
    """Manages global registry of all Jataí nodes and configurations."""

    DEFAULT_CONFIG = {
        "PREFIX_PROCESSED": "_",
        "PREFIX_ERROR": "!_",
        "RETRY_DELAY_BASE": 60,
    }

    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize Registry with custom or default location.

        Args:
            registry_path: Path to global registry file. Defaults to ~/.jatai
        """
        if registry_path is None:
            self.registry_path = Path.home() / ".jatai"
        else:
            self.registry_path = Path(registry_path)

        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.global_config: Dict[str, Any] = self.DEFAULT_CONFIG.copy()

    def load(self) -> None:
        """
        Load registry from disk.

        Raises:
            FileNotFoundError: If registry file does not exist.
            yaml.YAMLError: If registry file is malformed YAML.
        """
        if not self.registry_path.exists():
            raise FileNotFoundError(f"Registry file not found: {self.registry_path}")

        try:
            with open(self.registry_path, "r") as f:
                data = yaml.safe_load(f)

            if data is None:
                self.nodes = {}
                self.global_config = self.DEFAULT_CONFIG.copy()
            else:
                # Extract global config and nodes
                self.global_config = {
                    k: v
                    for k, v in data.items()
                    if k in self.DEFAULT_CONFIG
                }
                # Merge with defaults
                config = self.DEFAULT_CONFIG.copy()
                config.update(self.global_config)
                self.global_config = config

                # Extract nodes (entries that are dicts with path key)
                self.nodes = {
                    k: v for k, v in data.items() if isinstance(v, dict) and "path" in v
                }

        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse registry YAML: {e}")

    def save(self) -> None:
        """
        Save registry to disk in YAML format.

        Creates parent directories if they don't exist.
        """
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Build output dict: global config + nodes
        output = self.global_config.copy()
        output.update(self.nodes)

        with open(self.registry_path, "w") as f:
            yaml.safe_dump(output, f, default_flow_style=False, sort_keys=False)

    def add_node(self, node_name: str, node_path: str, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a node to the registry.

        Args:
            node_name: Name identifier for the node
            node_path: Absolute path to the node directory
            config: Optional node-specific configuration
        """
        node_config: Dict[str, Any] = {"path": str(Path(node_path).resolve())}
        if config:
            node_config.update(config)
        self.nodes[node_name] = node_config

    def get_node(self, node_name: str) -> Optional[Dict[str, Any]]:
        """
        Get node configuration by name.

        Args:
            node_name: Name of the node

        Returns:
            Node configuration dict or None if not found
        """
        return self.nodes.get(node_name)

    def list_nodes(self) -> Dict[str, str]:
        """
        List all registered nodes with their paths.

        Returns:
            Dictionary mapping node names to their paths
        """
        return {name: node["path"] for name, node in self.nodes.items()}

    def remove_node(self, node_name: str) -> bool:
        """
        Remove a node from registry.

        Args:
            node_name: Name of the node to remove

        Returns:
            True if node was removed, False if it didn't exist
        """
        if node_name in self.nodes:
            del self.nodes[node_name]
            return True
        return False

    def get_config(self, key: str, node_name: Optional[str] = None) -> Any:
        """
        Get configuration value (respects local > global priority).

        Args:
            key: Configuration key
            node_name: Optional node name for local config lookup

        Returns:
            Configuration value or None if not found
        """
        if node_name and node_name in self.nodes:
            node_config = self.nodes[node_name]
            if key in node_config:
                return node_config[key]

        return self.global_config.get(key)

    def set_config(self, key: str, value: Any, node_name: Optional[str] = None) -> None:
        """
        Set configuration value (globally or for a specific node).

        Args:
            key: Configuration key
            value: Configuration value
            node_name: Optional node name for local config
        """
        if node_name:
            if node_name not in self.nodes:
                raise ValueError(f"Node '{node_name}' not found")
            self.nodes[node_name][key] = value
        else:
            self.global_config[key] = value

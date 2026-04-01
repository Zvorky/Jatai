"""System state storage for Jataí (Path, DB, and migration metadata)."""
import uuid as _uuid_module
from pathlib import Path
from typing import Optional
import tempfile
import yaml


class SystemState:
    BASE_PATH = Path(tempfile.gettempdir()) / "jatai"

    @classmethod
    def ensure_base(cls):
        cls.BASE_PATH.mkdir(parents=True, exist_ok=True)
        (cls.BASE_PATH / "logs").mkdir(parents=True, exist_ok=True)
        (cls.BASE_PATH / "bkp").mkdir(parents=True, exist_ok=True)

    @classmethod
    def uuid_map_path(cls) -> Path:
        cls.ensure_base()
        return cls.BASE_PATH / "uuid_map.yaml"

    @classmethod
    def removed_path(cls) -> Path:
        cls.ensure_base()
        return cls.BASE_PATH / "removed.yaml"

    @classmethod
    def bkp_path(cls, node_uuid: str) -> Path:
        cls.ensure_base()
        return cls.BASE_PATH / "bkp" / f"{node_uuid}.yaml"

    @classmethod
    def read_yaml(cls, path: Path):
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    @classmethod
    def write_yaml(cls, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")

    @classmethod
    def assign_uuid(cls, node_path: str) -> str:
        """Get an existing UUID for *node_path* or create and persist a new one.

        UUIDs are reused if the same path is removed and added back, preserving
        the migration-cache identity across node lifecycle events per ADR-4.3.1.
        """
        uuid_map = cls.read_yaml(cls.uuid_map_path()) or {}
        if node_path in uuid_map:
            return str(uuid_map[node_path])
        new_uuid = str(_uuid_module.uuid4())
        uuid_map[node_path] = new_uuid
        cls.write_yaml(cls.uuid_map_path(), uuid_map)
        return new_uuid

    @classmethod
    def get_uuid(cls, node_path: str) -> Optional[str]:
        """Return the UUID for *node_path* or ``None`` if not yet registered."""
        uuid_map = cls.read_yaml(cls.uuid_map_path()) or {}
        value = uuid_map.get(node_path)
        return str(value) if value is not None else None

    @classmethod
    def mark_autoremoved(cls, node_path: str) -> None:
        """Append *node_path* to removed.yaml with the ``--autoremoved`` marker.

        Per ADR-4.4.1 and REQ-3.7.2.1, entries written by the daemon carry the
        ``--autoremoved`` suffix so they can be distinguished from paths that
        were commented-out or disabled manually by the user.
        """
        removed_data = cls.read_yaml(cls.removed_path())
        entries: list = removed_data if isinstance(removed_data, list) else []
        entry = f"{node_path} --autoremoved"
        if entry not in entries:
            entries.append(entry)
        cls.write_yaml(cls.removed_path(), entries)

    @classmethod
    def write_bkp_config(cls, node_path: str, config: dict) -> Optional[Path]:
        """Write *config* to the system-level UUID backup for *node_path*.

        Creates or overwrites ``/tmp/jatai/bkp/<UUID>.yaml``.  Returns the path
        written, or ``None`` if the UUID could not be determined.
        """
        try:
            node_uuid = cls.assign_uuid(node_path)
            bkp = cls.bkp_path(node_uuid)
            cls.write_yaml(bkp, config)
            return bkp
        except Exception:
            return None

    @classmethod
    def read_bkp_config(cls, node_path: str) -> Optional[dict]:
        """Read the system-level UUID backup config for *node_path*, or ``None``."""
        try:
            node_uuid = cls.get_uuid(node_path)
            if node_uuid is None:
                return None
            data = cls.read_yaml(cls.bkp_path(node_uuid))
            return data if data else None
        except Exception:
            return None

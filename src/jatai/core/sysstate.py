"""System state storage for Jataí (Path, DB, and migration metadata)."""
from pathlib import Path
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
    def bkp_path(cls, uuid: str) -> Path:
        cls.ensure_base()
        return cls.BASE_PATH / "bkp" / f"{uuid}.yaml"

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

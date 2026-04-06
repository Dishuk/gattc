"""
Snapshot storage and loading for schema change tracking.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import Schema


DEFAULT_SNAPSHOT_PATH = "gattc/snapshots"


def get_snapshot_dir(config: Optional[Any] = None, root_dir: Optional[Path] = None) -> Path:
    """Get snapshot directory from config or default.

    Args:
        config: Optional Config object with snapshots.path setting.
        root_dir: Root directory to resolve relative paths against.
                  Defaults to current working directory.

    Returns:
        Absolute path to snapshot directory.
    """
    if root_dir is None:
        root_dir = Path.cwd()

    # Check config for custom path
    if config is not None:
        snapshots_config = getattr(config, 'snapshots', None)
        if snapshots_config is not None:
            custom_path = getattr(snapshots_config, 'path', None)
            if custom_path is not None:
                if custom_path.is_absolute():
                    return custom_path
                return root_dir / custom_path

    return root_dir / DEFAULT_SNAPSHOT_PATH


def get_snapshot_path(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> Path:
    """Get path to snapshot file for a service.

    Args:
        service_name: Name of the service.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        Path to the service's snapshot JSON file.
    """
    return get_snapshot_dir(config, root_dir) / f"{service_name}.json"


def snapshot_exists(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> bool:
    """Check if snapshot exists for service.

    Args:
        service_name: Name of the service.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        True if snapshot file exists.
    """
    return get_snapshot_path(service_name, config, root_dir).exists()


def _schema_to_dict(schema: Schema) -> Dict[str, Any]:
    """Convert schema to a serializable dictionary.

    Converts dataclass instances recursively, handling nested structures
    and custom types like TypeInfo.
    """
    def convert(obj: Any, key_name: str = None) -> Any:
        if hasattr(obj, '__dataclass_fields__'):
            return {k: convert(v, k) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [convert(item) for item in obj]
        elif isinstance(obj, dict):
            # Normalize dict keys to strings for 'bits' field (bitfield definitions)
            # This ensures consistent comparison after JSON roundtrip
            if key_name == 'bits':
                return {str(k): convert(v) for k, v in obj.items()}
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, Path):
            return str(obj)
        return obj

    return convert(schema)


def save_snapshot(
    service_name: str,
    schema: Schema,
    config: Optional[Any] = None,
    root_dir: Optional[Path] = None
) -> Path:
    """Save current schema as snapshot.

    Args:
        service_name: Name of the service.
        schema: Schema object to save.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        Path to the saved snapshot file.
    """
    snapshot_path = get_snapshot_path(service_name, config, root_dir)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    data = _schema_to_dict(schema)

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)

    return snapshot_path


def load_snapshot(
    service_name: str,
    config: Optional[Any] = None,
    root_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Load existing snapshot, return None if not exists.

    Args:
        service_name: Name of the service.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        Snapshot data as dictionary, or None if not found.
    """
    snapshot_path = get_snapshot_path(service_name, config, root_dir)

    if not snapshot_path.exists():
        return None

    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)

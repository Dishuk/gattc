"""
Configuration file loading for gattc.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ._util import warn_unknown_keys as _warn_unknown_keys

CONFIG_FILENAME = "gattc.yaml"


@dataclass
class ZephyrOutputConfig:
    """Zephyr output configuration with header/source paths."""
    header: Path | None = None  # Header files path
    source: Path | None = None  # Source files path
    per_service: bool = True  # True = each service gets own .h/.c pair, False = all combined

    def get_header_path(self) -> Path | None:
        """Get header output path."""
        return self.header

    def get_source_path(self) -> Path | None:
        """Get source output path (falls back to header path)."""
        return self.source or self.header

    def is_combined(self) -> bool:
        """Check if all services should be combined into single file pair."""
        return not self.per_service


@dataclass
class DocsOutputConfig:
    """Documentation output configuration."""
    path: Path | None = None
    per_service: bool = True  # True = one file per service, False = all combined
    format: str = "md"  # "md" (default) or "html"

    def is_combined(self) -> bool:
        """Check if all services should be combined into single file."""
        return not self.per_service


@dataclass
class SnapshotsConfig:
    """Snapshots configuration for change tracking."""
    path: Path | None = None  # Path to snapshots directory


@dataclass
class OutputConfig:
    zephyr: ZephyrOutputConfig = field(default_factory=ZephyrOutputConfig)
    docs: DocsOutputConfig = field(default_factory=DocsOutputConfig)


@dataclass
class ServiceConfig:
    """Per-service configuration override."""
    output: OutputConfig = field(default_factory=OutputConfig)


@dataclass
class Config:
    schemas: list[Path] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)
    services: dict[str, ServiceConfig] = field(default_factory=dict)
    snapshots: SnapshotsConfig = field(default_factory=SnapshotsConfig)
    config_path: Path | None = None

    @property
    def root_dir(self) -> Path:
        if self.config_path:
            return self.config_path.parent
        return Path.cwd()

    def get_service_config(self, service_name: str) -> ServiceConfig:
        """Get config for a specific service, or empty config if not defined."""
        return self.services.get(service_name, ServiceConfig())


def find_config(start_dir: Path | None = None) -> Path | None:
    """Find gattc.yaml in start_dir or parent directories."""
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    while True:
        config_file = current / CONFIG_FILENAME
        if config_file.exists():
            return config_file

        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def _parse_zephyr_output(zephyr_raw: dict[str, Any], root_dir: Path) -> ZephyrOutputConfig:
    """Parse zephyr output configuration.

    Supports dict with:
        - 'header': path for header files
        - 'source': path for source files (defaults to header path if not specified)
        - 'per_service': control combined vs per-service output
    """
    if not isinstance(zephyr_raw, dict):
        raise ValueError(f"'zephyr' must be a dict with 'header' and/or 'source' keys, got {type(zephyr_raw).__name__}")

    _warn_unknown_keys(zephyr_raw, {"header", "source", "per_service"}, "output.zephyr")
    zephyr_config = ZephyrOutputConfig()

    if "header" in zephyr_raw:
        zephyr_config.header = root_dir / zephyr_raw["header"]
    if "source" in zephyr_raw:
        zephyr_config.source = root_dir / zephyr_raw["source"]
    if "per_service" in zephyr_raw:
        zephyr_config.per_service = bool(zephyr_raw["per_service"])

    # If only header specified, use it for source too
    if zephyr_config.header and not zephyr_config.source:
        zephyr_config.source = zephyr_config.header
    # If only source specified, use it for header too
    if zephyr_config.source and not zephyr_config.header:
        zephyr_config.header = zephyr_config.source

    return zephyr_config


def _parse_docs_output(docs_raw: str | dict[str, Any], root_dir: Path) -> DocsOutputConfig:
    """Parse docs output configuration.

    Supports:
        - String: "path/" -> docs path with default (per_service=True, format='md')
        - Dict with 'path', 'per_service', and/or 'format': full configuration
    """
    docs_config = DocsOutputConfig()

    if isinstance(docs_raw, str):
        docs_config.path = root_dir / docs_raw
    elif isinstance(docs_raw, dict):
        _warn_unknown_keys(docs_raw, {"path", "per_service", "format"}, "output.docs")
        if "path" in docs_raw:
            docs_config.path = root_dir / docs_raw["path"]
        if "per_service" in docs_raw:
            docs_config.per_service = bool(docs_raw["per_service"])
        if "format" in docs_raw:
            fmt = str(docs_raw["format"]).lower()
            if fmt not in ("md", "html"):
                raise ValueError(f"'output.docs.format' must be 'md' or 'html', got {fmt!r}")
            docs_config.format = fmt
    else:
        raise ValueError(f"'docs' must be a string or dict, got {type(docs_raw).__name__}")

    return docs_config


def _parse_output_config(output_raw: dict[str, Any], root_dir: Path) -> OutputConfig:
    """Parse output configuration section."""
    if not isinstance(output_raw, dict):
        raise ValueError(f"'output' must be a dict, got {type(output_raw).__name__}")

    _warn_unknown_keys(output_raw, {"zephyr", "docs"}, "output")
    output_config = OutputConfig()

    if "zephyr" in output_raw:
        output_config.zephyr = _parse_zephyr_output(output_raw["zephyr"], root_dir)
    if "docs" in output_raw:
        output_config.docs = _parse_docs_output(output_raw["docs"], root_dir)

    return output_config


def _parse_service_config(service_name: str, service_raw: dict[str, Any], root_dir: Path) -> ServiceConfig:
    """Parse per-service configuration."""
    _warn_unknown_keys(service_raw, {"output"}, f"services.{service_name}")
    service_config = ServiceConfig()

    if "output" in service_raw:
        service_config.output = _parse_output_config(service_raw["output"], root_dir)

    return service_config


def load_config(config_path: Path | None = None) -> Config | None:
    """Load configuration from gattc.yaml.

    Args:
        config_path: Explicit path to config file. If None, searches
                     current and parent directories.

    Returns:
        Config object if found and valid, None if no config file.

    Raises:
        ValueError: If config file exists but is invalid.
    """
    if config_path is None:
        config_path = find_config()

    if config_path is None:
        return None

    config_path = Path(config_path).resolve()

    if not config_path.exists():
        return None

    root_dir = config_path.parent

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return Config(config_path=config_path)

    if isinstance(data, dict):
        _warn_unknown_keys(data, {"schemas", "output", "docs", "services", "snapshots"}, "config")

    config = Config(config_path=config_path)

    # Parse schemas
    schemas_raw = data.get("schemas")
    if schemas_raw:
        if isinstance(schemas_raw, str):
            config.schemas = [root_dir / schemas_raw]
        elif isinstance(schemas_raw, list):
            config.schemas = [root_dir / s for s in schemas_raw]
        else:
            raise ValueError(f"'schemas' must be a string or list, got {type(schemas_raw).__name__}")

    # Parse output configuration
    output_raw = data.get("output")
    if output_raw:
        config.output = _parse_output_config(output_raw, root_dir)

    # Legacy docs support (simple string at root level)
    docs_raw = data.get("docs")
    if docs_raw:
        if isinstance(docs_raw, str):
            config.output.docs.path = root_dir / docs_raw
        elif isinstance(docs_raw, dict):
            config.output.docs = _parse_docs_output(docs_raw, root_dir)

    # Parse per-service configurations
    services_raw = data.get("services")
    if services_raw:
        if not isinstance(services_raw, dict):
            raise ValueError(f"'services' must be a dict, got {type(services_raw).__name__}")
        for service_name, service_data in services_raw.items():
            if isinstance(service_data, dict):
                config.services[service_name] = _parse_service_config(service_name, service_data, root_dir)

    # Parse snapshots configuration
    snapshots_raw = data.get("snapshots")
    if snapshots_raw:
        if isinstance(snapshots_raw, str):
            config.snapshots.path = root_dir / snapshots_raw
        elif isinstance(snapshots_raw, dict):
            _warn_unknown_keys(snapshots_raw, {"path"}, "snapshots")
            if "path" in snapshots_raw:
                config.snapshots.path = root_dir / snapshots_raw["path"]
        else:
            raise ValueError(f"'snapshots' must be a string or dict, got {type(snapshots_raw).__name__}")

    return config


def find_schemas(config: Config) -> list[Path]:
    """Find all schema files based on config."""
    schemas = []

    for schema_dir in config.schemas:
        if not schema_dir.exists():
            continue

        if schema_dir.is_file() and schema_dir.suffix == ".yaml":
            schemas.append(schema_dir)
        elif schema_dir.is_dir():
            for yaml_file in schema_dir.glob("*.yaml"):
                if yaml_file.name != CONFIG_FILENAME:
                    schemas.append(yaml_file)

    return sorted(schemas)


def validate_service_configs(config: Config, found_services: set[str]) -> list[str]:
    """Validate that all per-service configs reference existing services.

    Args:
        config: The loaded configuration.
        found_services: Set of service names found in schema files.

    Returns:
        List of error messages for invalid service configs.
    """
    errors = []
    for service_name in config.services.keys():
        if service_name not in found_services:
            errors.append(
                f"Service '{service_name}' defined in config but not found in any schema file"
            )
    return errors

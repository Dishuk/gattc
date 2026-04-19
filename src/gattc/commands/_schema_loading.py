"""Schema discovery, loading, and diff helpers shared across commands."""

from pathlib import Path

import click
import yaml

from ..config import Config, OutputConfig, find_schemas
from ..diff import SchemaDiff, diff_schemas
from ..schema import Schema, load_and_validate_schema, load_schema
from ..snapshot import load_snapshot

NO_SCHEMA_OR_CONFIG_MSG = (
    "No schema specified and no gattc.yaml found.\n"
    "Either provide a schema path or create gattc.yaml with 'gattc init'."
)


def resolve_schema_paths(
    schema_arg: Path | None,
    config: Config | None,
) -> tuple[list[Path], Path]:
    """Resolve schema paths from CLI argument or project config.

    Returns (schema_paths, root_dir). Raises ClickException on missing
    config or empty schema directories when no schema_arg is given.
    """
    if schema_arg:
        root = config.root_dir if config else Path.cwd()
        return [schema_arg], root
    if not config:
        raise click.ClickException(NO_SCHEMA_OR_CONFIG_MSG)
    schema_paths = find_schemas(config)
    if not schema_paths:
        raise click.ClickException("No .yaml files found in configured directories")
    return schema_paths, config.root_dir


def collect_service_names(schema_paths: list[Path]) -> dict[str, Path]:
    """Load schemas and collect service names."""
    service_names = {}
    for schema_path in schema_paths:
        try:
            s = load_schema(schema_path)
            service_names[s.service.name] = schema_path
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            click.echo(f"Warning: Could not load {schema_path}: {e}", err=True)
    return service_names


def resolve_combined_mode(
    combined: bool | None,
    per_service: bool | None,
    config_is_combined: bool,
) -> bool:
    """Resolve whether to use combined output mode."""
    if combined and per_service:
        raise click.ClickException("Cannot specify both --combined and --per-service")

    if combined:
        return True
    if per_service:
        return False
    return config_is_combined


def get_output_config_for_service(config: Config | None, service_name: str) -> OutputConfig:
    """Get output configuration for a specific service."""
    if not config:
        return OutputConfig()

    service_config = config.get_service_config(service_name)
    if service_config.output.zephyr.get_header_path() or service_config.output.zephyr.get_source_path():
        return service_config.output

    return config.output


def load_diff(
    service_name: str,
    schema: Schema,
    config: Config | None,
    root_dir: Path,
) -> tuple[bool, SchemaDiff | None]:
    """Load snapshot and compute diff. Returns (snapshot_existed, diff_or_None)."""
    snapshot = load_snapshot(service_name, config, root_dir)
    if snapshot is None:
        return False, None
    return True, diff_schemas(snapshot, schema)


def load_schemas_with_errors(schema_paths: list[Path]) -> tuple[list[Schema], int]:
    """Load and validate multiple schemas, reporting errors."""
    loaded_schemas = []
    error_count = 0

    for schema_path in schema_paths:
        s, errors = load_and_validate_schema(schema_path)
        if errors:
            click.echo(f"Schema validation failed for {schema_path}:", err=True)
            for e in errors:
                click.echo(f"  - {e}", err=True)
            error_count += 1
            continue
        assert s is not None  # load_and_validate_schema: empty errors => schema present
        loaded_schemas.append(s)

    return loaded_schemas, error_count

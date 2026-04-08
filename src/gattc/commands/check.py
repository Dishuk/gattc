"""Check command — validate GATT schema files."""

from pathlib import Path
from typing import Optional

import click

from ..config import find_schemas, load_config
from ..schema import load_and_validate_schema


@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
def check(schema: Optional[Path]):
    """Validate GATT schema file(s).

    With gattc.yaml: validates all schemas from configured directories.
    Without: requires SCHEMA path argument.
    """
    if schema:
        schemas = [schema]
    else:
        config = load_config()
        if not config:
            raise click.ClickException(
                "No schema specified and no gattc.yaml found."
            )
        schemas = find_schemas(config)
        if not schemas:
            raise click.ClickException("No .yaml files found in configured directories")

    error_count = 0
    for schema_path in schemas:
        s, errors = load_and_validate_schema(schema_path)
        if s is None:
            # Load failure
            click.echo(f"{schema_path}: ERROR - {errors[0]}", err=True)
            error_count += 1
        elif errors:
            # Validation failure
            click.echo(f"{schema_path}: INVALID", err=True)
            for error in errors:
                click.echo(f"  - {error}", err=True)
            error_count += 1
        else:
            click.echo(f"{schema_path}: OK")

    if error_count > 0:
        raise SystemExit(1)

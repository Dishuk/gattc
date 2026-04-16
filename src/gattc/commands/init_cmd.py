"""Init command — initialize gattc in current directory."""

from pathlib import Path

import click


@click.command("init")
def init():
    """Initialize gattc in current directory.

    Creates gattc.yaml, schema folder, and example schema.
    Edit gattc.yaml to customize paths if needed.
    """
    config_path = Path.cwd() / "gattc.yaml"

    if config_path.exists():
        raise click.ClickException(f"{config_path} already exists")

    config_content = '''# gattc configuration

# Schema locations - folders or individual .yaml files
# Multiple entries supported
schemas:
  - "gattc/"
#   - "services/custom_service.yaml"

# Output paths
output:
  zephyr:
    header: "src/generated/"          # Header files (.h) location
    source: "src/generated/"          # Source files (.c) location
    per_service: true                 # true = one .h/.c pair per service (default)
                                      # false = all services in single gatt_services.h/.c

  # Documentation output
  docs:
    path: "docs/ble/"
    per_service: false                # true = one file per service
                                      # false = all services in single gatt_services.<ext>
    format: md                        # "md" (default) or "html"

# Per-service output overrides (only applies when per_service: true)
# Use service name (from service.name in schema) as key
# services:
#   echo_service:
#     output:
#       zephyr:
#         header: "include/echo_service/"
#         source: "src/echo_service/"
#       # docs:
#       #   path: "docs/echo_service/"
'''
    config_path.write_text(config_content)
    click.echo(f"Created: {config_path}")

    schema_path = Path.cwd() / "gattc"
    schema_path.mkdir(parents=True, exist_ok=True)

    example_schema = schema_path / "echo_service.yaml"
    example_content = '''schema_version: "1.0"

service:
  name: echo_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  echo:
    uuid: "12345678-1234-1234-1234-000000000001"
    properties: [read, write]
    permissions: [read, write]
    payload:
      data: bytes[20]
'''
    example_schema.write_text(example_content)
    click.echo(f"Created: {example_schema}")

    click.echo("\nNext steps:")
    click.echo("  1. Edit gattc/echo_service.yaml or create new schemas")
    click.echo("  2. Run 'gattc compile'")

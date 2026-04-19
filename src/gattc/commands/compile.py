"""Compile command — compile GATT schemas to Zephyr C code."""

from pathlib import Path

import click
import yaml
from jinja2 import TemplateError

from .._errors import handle_error
from ..config import find_schemas, load_config, validate_service_configs
from ..schema import load_schema
from ._compile_modes import (
    compile_combined_mode,
    compile_per_service_mode,
    compile_single_schema_mode,
)
from ._output_management import clear_output_files
from ._schema_loading import (
    NO_SCHEMA_OR_CONFIG_MSG,
    collect_service_names,
    resolve_combined_mode,
)


@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output directory or file path")
@click.option("--header", type=click.Path(path_type=Path), help="Output directory for header files")
@click.option("--source", type=click.Path(path_type=Path), help="Output directory for source files")
@click.option("--combined", is_flag=True, default=None, help="Generate all services in a single .h/.c file pair")
@click.option("--per-service", "per_service", is_flag=True, default=None, help="Generate separate .h/.c files per service")
@click.option("--docs/--no-docs", default=None, help="Generate documentation (Markdown or HTML)")
@click.option("--no-diff", is_flag=True, default=False, help="Skip change detection against snapshots")
def compile(
    schema: Path | None,
    output: Path | None,
    header: Path | None,
    source: Path | None,
    combined: bool | None,
    per_service: bool | None,
    docs: bool | None,
    no_diff: bool,
) -> None:
    """Compile GATT schema(s) to Zephyr C code.

    With gattc.yaml: compiles all schemas from configured directories.
    Without: requires SCHEMA path argument.

    Output paths can be configured:
      - Single path: -o/--output sets both header and source location
      - Separate paths: --header and --source for different locations
      - Combined output: --combined to merge all services into one file pair
      - Config file: output.zephyr with header/source/per_service options

    Change detection:
      - Compares current schemas against stored snapshots
      - Shows changes in CLI and highlights them in generated docs
      - Does NOT update snapshots or changelog (use 'gattc release' for that)
      - Use --no-diff to skip change detection
    """
    config = load_config()

    # Single schema mode - compile directly without config
    if schema:
        try:
            compile_single_schema_mode(schema, output, header, source, docs, config, enable_diff=not no_diff)
        except (yaml.YAMLError, ValueError, FileNotFoundError, TemplateError) as e:
            raise click.ClickException(str(e))
        except Exception as e:
            handle_error(e, "Compilation failed")
        return

    # Project mode - requires config
    if not config:
        raise click.ClickException(NO_SCHEMA_OR_CONFIG_MSG)

    if not config.schemas:
        raise click.ClickException(
            "gattc.yaml found but 'schemas' not configured.\n"
            "Add 'schemas: <folder>' to your gattc.yaml"
        )

    schema_paths = find_schemas(config)
    if not schema_paths:
        raise click.ClickException(
            f"No .yaml files found in configured schema directories: {config.schemas}"
        )

    # Validate per-service configs reference existing services
    if config.services:
        service_map = collect_service_names(schema_paths)
        config_errors = validate_service_configs(config, set(service_map.keys()))
        if config_errors:
            raise click.ClickException(
                "Invalid service configuration:\n" +
                "\n".join(f"  - {e}" for e in config_errors)
            )

    # Resolve output paths (CLI args override config)
    use_combined = resolve_combined_mode(
        combined, per_service, config.output.zephyr.is_combined()
    )
    output_dir = output
    header_dir = header or (config.output.zephyr.get_header_path() if not output_dir else None)
    source_dir = source or (config.output.zephyr.get_source_path() if not output_dir else None)
    generate_docs = docs if docs is not None else (config.output.docs.path is not None)
    docs_dir = config.output.docs.path
    docs_combined = config.output.docs.is_combined()

    if use_combined:
        output_names = ["gatt_services"]
    else:
        output_names = []
        for sp in schema_paths:
            try:
                s_preview = load_schema(sp)
                output_names.append(s_preview.service.name)
            except (FileNotFoundError, KeyError, yaml.YAMLError):
                output_names.append(sp.stem)

    clear_output_files(
        output_names,
        header_dir or output_dir,
        source_dir or output_dir,
        docs_dir,
        generate_docs,
        config.output.docs.format,
    )

    try:
        if use_combined:
            compile_combined_mode(schema_paths, output_dir, header_dir, source_dir, docs_dir, generate_docs, config, enable_diff=not no_diff)
        else:
            compile_per_service_mode(schema_paths, output_dir, header_dir, source_dir, docs_dir, generate_docs, docs_combined, config, enable_diff=not no_diff)
    except click.ClickException:
        raise
    except (yaml.YAMLError, ValueError, FileNotFoundError, TemplateError) as e:
        raise click.ClickException(f"Compilation failed: {e}")
    except Exception as e:
        handle_error(e, "Compilation failed")

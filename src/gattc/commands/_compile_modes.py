"""Compilation orchestrators (single / combined / per-service) and their helpers."""

from pathlib import Path
from typing import Any

import click
import yaml
from jinja2 import TemplateError

from .._errors import is_debug
from ..changelog import load_changelog
from ..config import Config
from ..diff import SchemaDiff
from ..generators import docs as docs_gen
from ..generators import zephyr
from ..schema import Schema, load_and_validate_schema, load_schema
from ._output_management import clear_output_files
from ._schema_loading import (
    get_output_config_for_service,
    load_diff,
    load_schemas_with_errors,
)


def collect_diffs_and_changelogs(
    loaded_schemas: list[Schema],
    config: Config | None,
    root_dir: Path,
) -> tuple[dict[str, SchemaDiff], dict[str, list[dict[str, Any]]], bool]:
    """Load diffs and changelogs for all schemas.

    Returns:
        (diffs, changelogs, changes_detected)
    """
    diffs: dict[str, SchemaDiff] = {}
    changelogs: dict[str, list[dict[str, Any]]] = {}
    changes_detected = False

    for s in loaded_schemas:
        service_name = s.service.name
        has_snapshot, diff = load_diff(service_name, s, config, root_dir)
        if diff is not None:
            diffs[service_name] = diff
            if diff.has_changes:
                changes_detected = True
                click.echo(f"\n{service_name}: Changes detected")
                click.echo(diff.to_changelog_text())
        elif not has_snapshot:
            changes_detected = True  # no snapshot = never released
        changelogs[service_name] = load_changelog(service_name, config, root_dir)

    return diffs, changelogs, changes_detected


def generate_combined_docs(
    loaded_schemas: list[Schema],
    docs_dir: Path,
    diffs: dict[str, SchemaDiff] | None,
    changelogs: dict[str, list[dict[str, Any]]] | None,
    unreleased: bool,
    fmt: str = "md",
) -> Path:
    """Generate combined docs for all schemas."""
    return docs_gen.generate_combined(
        loaded_schemas,
        docs_dir / f"gatt_services.{fmt}",
        diffs=diffs,
        changelogs=changelogs,
        unreleased=unreleased,
        fmt=fmt,
    )


def compile_schema(
    schema_path: Path,
    output_dir: Path | None,
    generate_docs: bool,
    docs_dir: Path | None,
    config: Config | None = None,
    header_dir: Path | None = None,
    source_dir: Path | None = None,
    enable_diff: bool = True,
) -> tuple[list[Path], SchemaDiff | None, Schema]:
    """Compile a single schema file. Returns (generated_files, diff, schema)."""
    generated = []
    diff = None

    s, errors = load_and_validate_schema(schema_path)
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    assert s is not None

    service_name = s.service.name
    effective_output = get_output_config_for_service(config, service_name)

    root_dir = config.root_dir if config else Path.cwd()

    changelog_history = []
    has_snapshot = False
    if enable_diff:
        has_snapshot, diff = load_diff(service_name, s, config, root_dir)
        changelog_history = load_changelog(service_name, config, root_dir)

    final_header_dir = header_dir or effective_output.zephyr.get_header_path()
    final_source_dir = source_dir or effective_output.zephyr.get_source_path()

    if final_header_dir or final_source_dir:
        header, source = zephyr.generate(
            s,
            header_path=final_header_dir,
            source_path=final_source_dir or final_header_dir,
        )
    elif output_dir:
        output_path = output_dir / schema_path.stem
        header, source = zephyr.generate(s, output_path=output_path)
    else:
        output_path = schema_path.with_suffix(".h")
        header, source = zephyr.generate(s, output_path=output_path)

    generated.extend([header, source])

    effective_docs_dir = docs_dir
    if not effective_docs_dir and effective_output.docs.path:
        effective_docs_dir = effective_output.docs.path

    if generate_docs and effective_docs_dir:
        fmt = effective_output.docs.format
        docs_output = effective_docs_dir / f"{schema_path.stem}.{fmt}"
        unreleased = enable_diff and (not has_snapshot or (diff is not None and diff.has_changes))
        doc_path = docs_gen.generate(s, docs_output, diff=diff, changelog=changelog_history, unreleased=unreleased, fmt=fmt)
        generated.append(doc_path)

    return generated, diff, s


def compile_single_schema_mode(
    schema: Path,
    output: Path | None,
    header: Path | None,
    source: Path | None,
    docs: bool | None,
    config: Config | None,
    enable_diff: bool = True,
) -> None:
    """Compile a single schema file (direct mode)."""
    output_dir: Path | None
    if output and output.suffix in (".h", ".c"):
        output_dir = output.parent
    else:
        output_dir = output

    generate_docs = docs if docs is not None else False
    docs_dir = config.output.docs.path if config else None
    docs_fmt = config.output.docs.format if config else "md"

    s_preview = load_schema(schema)
    clear_output_files(
        [s_preview.service.name],
        header or output_dir,
        source or output_dir,
        docs_dir,
        generate_docs,
        docs_fmt,
    )

    generated, diff, s = compile_schema(
        schema,
        output_dir,
        generate_docs,
        docs_dir,
        config=config,
        header_dir=header,
        source_dir=source,
        enable_diff=enable_diff,
    )

    if diff and diff.has_changes:
        click.echo(f"\n{s.service.name}: Changes detected")
        click.echo(diff.to_changelog_text())
        click.echo()

    for f in generated:
        click.echo(f"Generated: {f}")


def compile_combined_mode(
    schemas: list[Path],
    output_dir: Path | None,
    header_dir: Path | None,
    source_dir: Path | None,
    docs_dir: Path | None,
    generate_docs: bool,
    config: Config | None = None,
    enable_diff: bool = True,
) -> None:
    """Compile multiple schemas into combined output files."""
    loaded_schemas, _ = load_schemas_with_errors(schemas)

    if not loaded_schemas:
        raise click.ClickException("No schemas loaded successfully")

    root_dir = config.root_dir if config else Path.cwd()

    diffs: dict[str, SchemaDiff] = {}
    changelogs: dict[str, list[dict[str, Any]]] = {}
    changes_detected = False
    if enable_diff:
        diffs, changelogs, changes_detected = collect_diffs_and_changelogs(
            loaded_schemas, config, root_dir
        )

    header_path, source_path = zephyr.generate_combined(
        loaded_schemas,
        output_path=output_dir,
        header_path=header_dir,
        source_path=source_dir,
    )
    click.echo(f"Generated: {header_path}")
    click.echo(f"Generated: {source_path}")

    if generate_docs and docs_dir:
        fmt = config.output.docs.format if config else "md"
        docs_path = generate_combined_docs(
            loaded_schemas, docs_dir,
            diffs if enable_diff else None,
            changelogs if enable_diff else None,
            changes_detected,
            fmt=fmt,
        )
        click.echo(f"Generated: {docs_path}")

    click.echo(f"\nCompiled {len(loaded_schemas)} service(s) into combined output")


def compile_per_service_mode(
    schemas: list[Path],
    output_dir: Path | None,
    header_dir: Path | None,
    source_dir: Path | None,
    docs_dir: Path | None,
    generate_docs: bool,
    docs_combined: bool,
    config: Config | None,
    enable_diff: bool = True,
) -> None:
    """Compile schemas into separate per-service output files."""
    success_count = 0
    changes_detected = False

    loaded_schemas: list[Schema] = []
    diffs: dict[str, SchemaDiff] = {}
    changelogs: dict[str, list[dict[str, Any]]] = {}

    per_service_docs = generate_docs and not docs_combined

    for schema_path in schemas:
        try:
            generated, diff, schema_obj = compile_schema(
                schema_path,
                output_dir,
                per_service_docs,
                docs_dir,
                config=config,
                header_dir=header_dir,
                source_dir=source_dir,
                enable_diff=enable_diff,
            )

            if diff and diff.has_changes:
                changes_detected = True
                click.echo(f"\n{diff.service_name}: Changes detected since last snapshot")
                click.echo(diff.to_changelog_text())
            elif diff is None and enable_diff:
                changes_detected = True

            if docs_combined and generate_docs:
                loaded_schemas.append(schema_obj)
                if diff:
                    diffs[schema_obj.service.name] = diff
                root_dir = config.root_dir if config else Path.cwd()
                changelogs[schema_obj.service.name] = load_changelog(
                    schema_obj.service.name, config, root_dir
                )

            for f in generated:
                click.echo(f"Generated: {f}")
            success_count += 1
        except (yaml.YAMLError, ValueError, FileNotFoundError, TemplateError) as e:
            click.echo(f"Error compiling {schema_path}: {e}", err=True)
        except Exception as e:
            if is_debug():
                raise
            click.echo(f"Error compiling {schema_path}: {e}", err=True)
            click.echo("  Use --debug for full traceback.", err=True)

    if success_count == 0:
        raise click.ClickException("No schemas compiled successfully")

    if docs_combined and generate_docs and docs_dir and loaded_schemas:
        fmt = config.output.docs.format if config else "md"
        docs_path = generate_combined_docs(
            loaded_schemas, docs_dir,
            diffs if enable_diff else None,
            changelogs if enable_diff else None,
            changes_detected,
            fmt=fmt,
        )
        click.echo(f"Generated: {docs_path}")

    click.echo(f"\nCompiled {success_count}/{len(schemas)} schema(s)")

"""Compile command — compile GATT schemas to Zephyr C code."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import yaml
from jinja2 import TemplateError

from ..cli import _handle_error, _is_debug
from ..config import Config, OutputConfig, find_schemas, load_config, validate_service_configs
from ..schema import load_and_validate_schema, load_schema, Schema
from ..generators import zephyr
from ..snapshot import load_snapshot
from ..diff import diff_schemas, SchemaDiff
from ..changelog import load_changelog


# ---------------------------------------------------------------------------
# Helpers — output clearing
# ---------------------------------------------------------------------------

def _clear_files(files: List[Path]) -> int:
    """Delete specific files. Returns the number of files deleted."""
    deleted = 0
    for file_path in files:
        if file_path.is_file():
            file_path.unlink()
            deleted += 1
    return deleted


def _collect_output_files(
    names: List[str],
    header_dir: Optional[Path],
    source_dir: Optional[Path],
    docs_dir: Optional[Path],
    generate_docs: bool,
) -> List[Path]:
    """Build the list of files that will be generated, so only those get cleared."""
    files: List[Path] = []
    for name in names:
        if header_dir:
            files.append(header_dir / f"{name}.h")
        if source_dir:
            files.append(source_dir / f"{name}.c")
            if header_dir is None:
                files.append(source_dir / f"{name}.h")
        if generate_docs and docs_dir:
            files.append(docs_dir / f"{name}.html")
    return files


def _clear_output_files(
    names: List[str],
    header_dir: Optional[Path],
    source_dir: Optional[Path],
    docs_dir: Optional[Path],
    generate_docs: bool,
) -> None:
    """Clear only the files that will be regenerated."""
    files = _collect_output_files(names, header_dir, source_dir, docs_dir, generate_docs)
    cleared = _clear_files(files)
    if cleared:
        click.echo(f"Cleared {cleared} previously generated file(s)")


# ---------------------------------------------------------------------------
# Helpers — config and schema
# ---------------------------------------------------------------------------

def _collect_service_names(schema_paths: List[Path]) -> Dict[str, Path]:
    """Load schemas and collect service names."""
    service_names = {}
    for schema_path in schema_paths:
        try:
            s = load_schema(schema_path)
            service_names[s.service.name] = schema_path
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            click.echo(f"Warning: Could not load {schema_path}: {e}", err=True)
    return service_names


def _resolve_combined_mode(
    combined: Optional[bool],
    per_service: Optional[bool],
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


def _get_output_config_for_service(config: Optional[Config], service_name: str) -> OutputConfig:
    """Get output configuration for a specific service."""
    if not config:
        return OutputConfig()

    service_config = config.get_service_config(service_name)
    if service_config.output.zephyr.get_header_path() or service_config.output.zephyr.get_source_path():
        return service_config.output

    return config.output


# ---------------------------------------------------------------------------
# Helpers — diff, changelog, docs (shared by both compile modes)
# ---------------------------------------------------------------------------

def _load_diff(
    service_name: str,
    schema: Schema,
    config: Optional[Config],
    root_dir: Path,
) -> Tuple[bool, Optional[SchemaDiff]]:
    """Load snapshot and compute diff. Returns (snapshot_existed, diff_or_None)."""
    snapshot = load_snapshot(service_name, config, root_dir)
    if snapshot is None:
        return False, None
    return True, diff_schemas(snapshot, schema)


def _collect_diffs_and_changelogs(
    loaded_schemas: List[Schema],
    config: Optional[Config],
    root_dir: Path,
) -> Tuple[Dict[str, SchemaDiff], Dict[str, List[Dict[str, Any]]], bool]:
    """Load diffs and changelogs for all schemas.

    Returns:
        (diffs, changelogs, changes_detected)
    """
    diffs: Dict[str, SchemaDiff] = {}
    changelogs: Dict[str, List[Dict[str, Any]]] = {}
    changes_detected = False

    for s in loaded_schemas:
        service_name = s.service.name
        has_snapshot, diff = _load_diff(service_name, s, config, root_dir)
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


def _generate_combined_docs(
    loaded_schemas: List[Schema],
    docs_dir: Path,
    diffs: Optional[Dict[str, SchemaDiff]],
    changelogs: Optional[Dict[str, List[Dict[str, Any]]]],
    unreleased: bool,
) -> Path:
    """Generate combined HTML docs for all schemas."""
    from ..generators import docs as docs_gen
    return docs_gen.generate_combined(
        loaded_schemas,
        docs_dir / "gatt_services.html",
        diffs=diffs,
        changelogs=changelogs,
        unreleased=unreleased,
    )


def _load_schemas_with_errors(schema_paths: List[Path]) -> Tuple[List[Schema], int]:
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
        loaded_schemas.append(s)

    return loaded_schemas, error_count


# ---------------------------------------------------------------------------
# Compilation modes
# ---------------------------------------------------------------------------

def _compile_schema(
    schema_path: Path,
    output_dir: Optional[Path],
    generate_docs: bool,
    docs_dir: Optional[Path],
    config: Optional[Config] = None,
    header_dir: Optional[Path] = None,
    source_dir: Optional[Path] = None,
    enable_diff: bool = True,
) -> Tuple[List[Path], Optional[SchemaDiff], Schema]:
    """Compile a single schema file. Returns (generated_files, diff, schema)."""
    generated = []
    diff = None

    s, errors = load_and_validate_schema(schema_path)
    if errors:
        raise ValueError(f"Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    service_name = s.service.name
    effective_output = _get_output_config_for_service(config, service_name)

    root_dir = config.root_dir if config else Path.cwd()

    changelog_history = []
    has_snapshot = False
    if enable_diff:
        has_snapshot, diff = _load_diff(service_name, s, config, root_dir)
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
        from ..generators import docs as docs_gen
        docs_output = effective_docs_dir / f"{schema_path.stem}.html"
        unreleased = enable_diff and (not has_snapshot or (diff is not None and diff.has_changes))
        html_path = docs_gen.generate(s, docs_output, diff=diff, changelog=changelog_history, unreleased=unreleased)
        generated.append(html_path)

    return generated, diff, s


def _compile_single_schema_mode(
    schema: Path,
    output: Optional[Path],
    header: Optional[Path],
    source: Optional[Path],
    docs: Optional[bool],
    config: Optional[Config],
    enable_diff: bool = True,
) -> None:
    """Compile a single schema file (direct mode)."""
    if output and output.suffix in (".h", ".c"):
        output_dir = output.parent
    else:
        output_dir = output

    generate_docs = docs if docs is not None else False
    docs_dir = config.output.docs.path if config else None

    s_preview = load_schema(schema)
    _clear_output_files(
        [s_preview.service.name],
        header or output_dir,
        source or output_dir,
        docs_dir,
        generate_docs,
    )

    generated, diff, s = _compile_schema(
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


def _compile_combined_mode(
    schemas: List[Path],
    output_dir: Optional[Path],
    header_dir: Optional[Path],
    source_dir: Optional[Path],
    docs_dir: Optional[Path],
    generate_docs: bool,
    config: Optional[Config] = None,
    enable_diff: bool = True,
) -> None:
    """Compile multiple schemas into combined output files."""
    loaded_schemas, _ = _load_schemas_with_errors(schemas)

    if not loaded_schemas:
        raise click.ClickException("No schemas loaded successfully")

    root_dir = config.root_dir if config else Path.cwd()

    diffs, changelogs, changes_detected = {}, {}, False
    if enable_diff:
        diffs, changelogs, changes_detected = _collect_diffs_and_changelogs(
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
        docs_path = _generate_combined_docs(
            loaded_schemas, docs_dir,
            diffs if enable_diff else None,
            changelogs if enable_diff else None,
            changes_detected,
        )
        click.echo(f"Generated: {docs_path}")

    click.echo(f"\nCompiled {len(loaded_schemas)} service(s) into combined output")


def _compile_per_service_mode(
    schemas: List[Path],
    output_dir: Optional[Path],
    header_dir: Optional[Path],
    source_dir: Optional[Path],
    docs_dir: Optional[Path],
    generate_docs: bool,
    docs_combined: bool,
    config: Optional[Config],
    enable_diff: bool = True,
) -> None:
    """Compile schemas into separate per-service output files."""
    success_count = 0
    changes_detected = False

    loaded_schemas: List[Schema] = []
    diffs: Dict[str, SchemaDiff] = {}
    changelogs: Dict[str, List[Dict[str, Any]]] = {}

    per_service_docs = generate_docs and not docs_combined

    for schema_path in schemas:
        try:
            generated, diff, schema_obj = _compile_schema(
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
            if _is_debug():
                raise
            click.echo(f"Error compiling {schema_path}: {e}", err=True)
            click.echo("  Use --debug for full traceback.", err=True)

    if success_count == 0:
        raise click.ClickException("No schemas compiled successfully")

    if docs_combined and generate_docs and docs_dir and loaded_schemas:
        docs_path = _generate_combined_docs(
            loaded_schemas, docs_dir,
            diffs if enable_diff else None,
            changelogs if enable_diff else None,
            changes_detected,
        )
        click.echo(f"Generated: {docs_path}")

    click.echo(f"\nCompiled {success_count}/{len(schemas)} schema(s)")


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output directory or file path")
@click.option("--header", type=click.Path(path_type=Path), help="Output directory for header files")
@click.option("--source", type=click.Path(path_type=Path), help="Output directory for source files")
@click.option("--combined", is_flag=True, default=None, help="Generate all services in a single .h/.c file pair")
@click.option("--per-service", "per_service", is_flag=True, default=None, help="Generate separate .h/.c files per service")
@click.option("--docs/--no-docs", default=None, help="Generate HTML documentation")
@click.option("--no-diff", is_flag=True, default=False, help="Skip change detection against snapshots")
def compile(
    schema: Optional[Path],
    output: Optional[Path],
    header: Optional[Path],
    source: Optional[Path],
    combined: Optional[bool],
    per_service: Optional[bool],
    docs: Optional[bool],
    no_diff: bool,
):
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
            _compile_single_schema_mode(schema, output, header, source, docs, config, enable_diff=not no_diff)
        except (yaml.YAMLError, ValueError, FileNotFoundError, TemplateError) as e:
            raise click.ClickException(str(e))
        except Exception as e:
            _handle_error(e, "Compilation failed")
        return

    # Project mode - requires config
    if not config:
        raise click.ClickException(
            "No schema specified and no gattc.yaml found.\n"
            "Either provide a schema path or create gattc.yaml in your project."
        )

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
        service_map = _collect_service_names(schema_paths)
        config_errors = validate_service_configs(config, set(service_map.keys()))
        if config_errors:
            raise click.ClickException(
                "Invalid service configuration:\n" +
                "\n".join(f"  - {e}" for e in config_errors)
            )

    # Resolve output paths (CLI args override config)
    use_combined = _resolve_combined_mode(
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
            except Exception:
                output_names.append(sp.stem)

    _clear_output_files(
        output_names,
        header_dir or output_dir,
        source_dir or output_dir,
        docs_dir,
        generate_docs,
    )

    try:
        if use_combined:
            _compile_combined_mode(schema_paths, output_dir, header_dir, source_dir, docs_dir, generate_docs, config, enable_diff=not no_diff)
        else:
            _compile_per_service_mode(schema_paths, output_dir, header_dir, source_dir, docs_dir, generate_docs, docs_combined, config, enable_diff=not no_diff)
    except click.ClickException:
        raise
    except (yaml.YAMLError, ValueError, FileNotFoundError, TemplateError) as e:
        raise click.ClickException(f"Compilation failed: {e}")
    except Exception as e:
        _handle_error(e, "Compilation failed")

"""
Command-line interface for gattc.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

import click
import yaml

from . import __version__
from .config import Config, find_schemas, load_config, OutputConfig
from .schema import load_and_validate_schema, load_schema, Schema
from .generators import zephyr
from .snapshot import get_snapshot_dir, load_snapshot, save_snapshot, snapshot_exists
from .diff import diff_schemas, SchemaDiff
from .changelog import add_changelog_entry, load_changelog


@click.group()
@click.version_option(version=__version__, prog_name="gattc")
def main():
    """gattc - BLE GATT schema compiler for Zephyr.

    Compiles YAML-based GATT service definitions into Zephyr C code.

    If gattc.yaml exists in current directory, runs in project mode.
    Otherwise, requires explicit schema path.
    """
    pass


def _clear_directory(directory: Path, extensions: List[str]) -> int:
    """Clear files with specified extensions from a directory.

    Args:
        directory: Directory to clear.
        extensions: List of file extensions to delete (e.g., [".h", ".c"]).

    Returns:
        Number of files deleted.
    """
    if not directory or not directory.exists() or not directory.is_dir():
        return 0

    deleted = 0
    for ext in extensions:
        for file_path in directory.glob(f"*{ext}"):
            if file_path.is_file():
                file_path.unlink()
                deleted += 1

    return deleted


def _clear_zephyr_output(header_dir: Optional[Path], source_dir: Optional[Path]) -> int:
    """Clear generated C files from zephyr output directories.

    Args:
        header_dir: Directory containing header files.
        source_dir: Directory containing source files.

    Returns:
        Total number of files deleted.
    """
    deleted = 0

    # Get unique directories (header and source might be the same)
    dirs_to_clear: Set[Path] = set()
    if header_dir:
        dirs_to_clear.add(header_dir)
    if source_dir:
        dirs_to_clear.add(source_dir)

    for directory in dirs_to_clear:
        deleted += _clear_directory(directory, [".h", ".c"])

    return deleted


def _clear_docs_output(docs_dir: Optional[Path]) -> int:
    """Clear generated HTML files from docs output directory.

    Args:
        docs_dir: Directory containing documentation files.

    Returns:
        Number of files deleted.
    """
    return _clear_directory(docs_dir, [".html"])


def _collect_service_names(schema_paths: List[Path]) -> Dict[str, Path]:
    """Load schemas and collect service names.

    Returns:
        Dict mapping service name to schema path.
    """
    service_names = {}
    for schema_path in schema_paths:
        try:
            s = load_schema(schema_path)
            service_names[s.service.name] = schema_path
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            # Skip schemas that fail to load - they'll error during compile
            click.echo(f"Warning: Could not load {schema_path}: {e}", err=True)
    return service_names


def _validate_service_configs(config: Config, found_services: Set[str]) -> List[str]:
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


def _resolve_combined_mode(
    combined: Optional[bool],
    per_service: Optional[bool],
    config_is_combined: bool,
) -> bool:
    """Resolve whether to use combined output mode.

    Args:
        combined: --combined flag value (True if set).
        per_service: --per-service flag value (True if set).
        config_is_combined: Whether config specifies combined mode.

    Returns:
        True if combined mode should be used.

    Raises:
        click.ClickException: If both --combined and --per-service are set.
    """
    if combined and per_service:
        raise click.ClickException("Cannot specify both --combined and --per-service")

    if combined:
        return True
    if per_service:
        return False
    return config_is_combined


def _get_output_config_for_service(config: Optional[Config], service_name: str) -> OutputConfig:
    """Get output configuration for a specific service.

    Checks for per-service override, falls back to global config.
    """
    if not config:
        return OutputConfig()

    # Check for per-service override
    service_config = config.get_service_config(service_name)
    if service_config.output.zephyr.get_header_path() or service_config.output.zephyr.get_source_path():
        return service_config.output

    # Fall back to global config
    return config.output


def _compile_schema(
    schema_path: Path,
    output_dir: Optional[Path],
    generate_docs: bool,
    docs_dir: Optional[Path],
    config: Optional[Config] = None,
    header_dir: Optional[Path] = None,
    source_dir: Optional[Path] = None,
    enable_diff: bool = True,
) -> Tuple[List[Path], Optional[SchemaDiff]]:
    """Compile a single schema file. Returns list of generated files and optional diff.

    Args:
        schema_path: Path to the YAML schema file.
        output_dir: Legacy single output directory (used if header_dir/source_dir not set).
        generate_docs: Whether to generate HTML documentation.
        docs_dir: Directory for documentation output.
        config: Optional config object for per-service overrides.
        header_dir: Explicit directory for header files.
        source_dir: Explicit directory for source files.
        enable_diff: Whether to detect changes against snapshots.

    Returns:
        Tuple of (generated_files, diff) where diff may be None.
    """
    generated = []
    diff = None

    s, errors = load_and_validate_schema(schema_path)
    if errors:
        raise ValueError(f"Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    # Check for per-service configuration override
    service_name = s.service.name
    effective_output = _get_output_config_for_service(config, service_name)

    # Determine root directory for snapshots
    root_dir = config.root_dir if config else Path.cwd()

    # Perform diff if enabled
    changelog_history = []
    if enable_diff:
        snapshot = load_snapshot(service_name, config, root_dir)
        if snapshot is not None:
            diff = diff_schemas(snapshot, s)
            # Add to changelog history if changes detected
            if diff.has_changes:
                changelog_history = add_changelog_entry(service_name, s, diff, config, root_dir)
            else:
                changelog_history = load_changelog(service_name, config, root_dir)
        else:
            changelog_history = load_changelog(service_name, config, root_dir)
        # Always save current schema as snapshot for next comparison
        save_snapshot(service_name, s, config, root_dir)

    # Determine final paths (CLI args override config)
    final_header_dir = header_dir or effective_output.zephyr.get_header_path()
    final_source_dir = source_dir or effective_output.zephyr.get_source_path()

    # If separate paths specified, use them
    if final_header_dir or final_source_dir:
        header, source = zephyr.generate(
            s,
            header_path=final_header_dir,
            source_path=final_source_dir or final_header_dir,  # fallback to header dir if source not set
        )
    elif output_dir:
        output_path = output_dir / schema_path.stem
        header, source = zephyr.generate(s, output_path=output_path)
    else:
        output_path = schema_path.with_suffix(".h")
        header, source = zephyr.generate(s, output_path=output_path)

    generated.extend([header, source])

    # Handle docs with per-service override
    effective_docs_dir = docs_dir
    if not effective_docs_dir and effective_output.docs.path:
        effective_docs_dir = effective_output.docs.path

    if generate_docs and effective_docs_dir:
        from .generators import docs as docs_gen
        docs_output = effective_docs_dir / f"{schema_path.stem}.html"
        html_path = docs_gen.generate(s, docs_output, diff=diff, changelog=changelog_history)
        generated.append(html_path)

    return generated, diff


def _load_schemas_with_errors(schema_paths: List[Path]) -> Tuple[List[Schema], int]:
    """Load and validate multiple schemas, reporting errors.

    Args:
        schema_paths: List of schema file paths to load.

    Returns:
        Tuple of (loaded_schemas, error_count).
    """
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


def _clear_output_directories(
    header_dir: Optional[Path],
    source_dir: Optional[Path],
    docs_dir: Optional[Path],
    generate_docs: bool,
) -> None:
    """Clear generated files from output directories.

    Args:
        header_dir: Directory for header files.
        source_dir: Directory for source files.
        docs_dir: Directory for documentation files.
        generate_docs: Whether docs generation is enabled.
    """
    zephyr_cleared = _clear_zephyr_output(header_dir, source_dir)
    if zephyr_cleared:
        click.echo(f"Cleared {zephyr_cleared} file(s) from output directory")

    if generate_docs and docs_dir:
        docs_cleared = _clear_docs_output(docs_dir)
        if docs_cleared:
            click.echo(f"Cleared {docs_cleared} HTML file(s) from docs directory")


def _compile_single_schema_mode(
    schema: Path,
    output: Optional[Path],
    header: Optional[Path],
    source: Optional[Path],
    docs: Optional[bool],
    config: Optional[Config],
    enable_diff: bool = True,
) -> None:
    """Compile a single schema file (direct mode).

    Args:
        schema: Path to the schema file.
        output: Output directory or file path.
        header: Header output directory.
        source: Source output directory.
        docs: Whether to generate docs.
        config: Optional config for docs path.
        enable_diff: Whether to detect changes against snapshots.
    """
    if output and output.suffix in (".h", ".c"):
        output_dir = output.parent
    else:
        output_dir = output

    generate_docs = docs if docs is not None else False
    docs_dir = config.output.docs.path if config else None

    _clear_output_directories(
        header or output_dir,
        source or output_dir,
        docs_dir,
        generate_docs,
    )

    generated, diff = _compile_schema(
        schema,
        output_dir,
        generate_docs,
        docs_dir,
        config=config,
        header_dir=header,
        source_dir=source,
        enable_diff=enable_diff,
    )

    # Show diff if changes detected
    if diff and diff.has_changes:
        s = load_schema(schema)
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
    """Compile multiple schemas into combined output files.

    Args:
        schemas: List of schema paths.
        output_dir: Base output directory.
        header_dir: Header output directory.
        source_dir: Source output directory.
        docs_dir: Docs output directory.
        generate_docs: Whether to generate docs.
        config: Optional config object.
        enable_diff: Whether to detect changes against snapshots.
    """
    loaded_schemas, _ = _load_schemas_with_errors(schemas)

    if not loaded_schemas:
        raise click.ClickException("No schemas loaded successfully")

    # Determine root directory for snapshots
    root_dir = config.root_dir if config else Path.cwd()

    # Compute diffs for all schemas
    diffs: Dict[str, SchemaDiff] = {}
    changelogs: Dict[str, List[Dict[str, Any]]] = {}
    changes_detected = False

    if enable_diff:
        for s in loaded_schemas:
            service_name = s.service.name
            snapshot = load_snapshot(service_name, config, root_dir)
            if snapshot is not None:
                diff = diff_schemas(snapshot, s)
                if diff.has_changes:
                    changes_detected = True
                    click.echo(f"\n{service_name}: Changes detected")
                    click.echo(diff.to_changelog_text())
                    changelogs[service_name] = add_changelog_entry(service_name, s, diff, config, root_dir)
                else:
                    changelogs[service_name] = load_changelog(service_name, config, root_dir)
                diffs[service_name] = diff
            else:
                changelogs[service_name] = load_changelog(service_name, config, root_dir)
            # Always save current schema as snapshot for next comparison
            save_snapshot(service_name, s, config, root_dir)

    header_path, source_path = zephyr.generate_combined(
        loaded_schemas,
        output_path=output_dir,
        header_path=header_dir,
        source_path=source_dir,
    )
    click.echo(f"Generated: {header_path}")
    click.echo(f"Generated: {source_path}")

    if generate_docs and docs_dir:
        from .generators import docs as docs_gen
        docs_path = docs_gen.generate_combined(
            loaded_schemas,
            docs_dir / "gatt_services.html",
            diffs=diffs if enable_diff else None,
            changelogs=changelogs if enable_diff else None
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
    """Compile schemas into separate per-service output files.

    Args:
        schemas: List of schema paths.
        output_dir: Base output directory.
        header_dir: Header output directory.
        source_dir: Source output directory.
        docs_dir: Docs output directory.
        generate_docs: Whether to generate docs.
        docs_combined: Whether to generate combined docs (single file for all services).
        config: Config for per-service overrides.
        enable_diff: Whether to detect changes against snapshots.
    """
    success_count = 0
    changes_detected = False

    # For combined docs, collect schemas and diffs
    loaded_schemas: List[Schema] = []
    diffs: Dict[str, SchemaDiff] = {}
    changelogs: Dict[str, List[Dict[str, Any]]] = {}

    # When docs_combined, don't generate per-service docs in loop
    per_service_docs = generate_docs and not docs_combined

    for schema_path in schemas:
        try:
            generated, diff = _compile_schema(
                schema_path,
                output_dir,
                per_service_docs,
                docs_dir,
                config=config,
                header_dir=header_dir,
                source_dir=source_dir,
                enable_diff=enable_diff,
            )

            # Show diff if changes detected
            if diff and diff.has_changes:
                changes_detected = True
                click.echo(f"\n{diff.service_name}: Changes detected since last snapshot")
                click.echo(diff.to_changelog_text())

            # Collect for combined docs
            if docs_combined and generate_docs:
                s, _ = load_and_validate_schema(schema_path)
                if s:
                    loaded_schemas.append(s)
                    if diff:
                        diffs[s.service.name] = diff
                    # Load changelog for this service
                    root_dir = config.root_dir if config else Path.cwd()
                    changelogs[s.service.name] = load_changelog(s.service.name, config, root_dir)

            for f in generated:
                click.echo(f"Generated: {f}")
            success_count += 1
        except Exception as e:
            click.echo(f"Error compiling {schema_path}: {e}", err=True)

    if success_count == 0:
        raise click.ClickException("No schemas compiled successfully")

    # Generate combined docs if requested
    if docs_combined and generate_docs and docs_dir and loaded_schemas:
        from .generators import docs as docs_gen
        docs_path = docs_gen.generate_combined(
            loaded_schemas,
            docs_dir / "gatt_services.html",
            diffs=diffs if enable_diff else None,
            changelogs=changelogs if enable_diff else None
        )
        click.echo(f"Generated: {docs_path}")

    click.echo(f"\nCompiled {success_count}/{len(schemas)} schema(s)")


@main.command()
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
      - Snapshot auto-updates after each compile
      - Use --no-diff to skip change detection
    """
    config = load_config()

    # Single schema mode - compile directly without config
    if schema:
        try:
            _compile_single_schema_mode(schema, output, header, source, docs, config, enable_diff=not no_diff)
        except Exception as e:
            raise click.ClickException(str(e))
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

    schemas = find_schemas(config)
    if not schemas:
        raise click.ClickException(
            f"No .yaml files found in configured schema directories: {config.schemas}"
        )

    # Validate per-service configs reference existing services
    if config.services:
        service_map = _collect_service_names(schemas)
        config_errors = _validate_service_configs(config, set(service_map.keys()))
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

    # Clear and generate
    _clear_output_directories(header_dir or output_dir, source_dir or output_dir, docs_dir, generate_docs)

    try:
        if use_combined:
            _compile_combined_mode(schemas, output_dir, header_dir, source_dir, docs_dir, generate_docs, config, enable_diff=not no_diff)
        else:
            _compile_per_service_mode(schemas, output_dir, header_dir, source_dir, docs_dir, generate_docs, docs_combined, config, enable_diff=not no_diff)
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Compilation failed: {e}")


@main.command()
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


@main.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output directory or file path")
@click.option("--combined", is_flag=True, default=None, help="Generate all services in a single HTML file")
@click.option("--per-service", "per_service", is_flag=True, default=None, help="Generate separate HTML file per service")
def docs(schema: Optional[Path], output: Optional[Path], combined: Optional[bool], per_service: Optional[bool]):
    """Generate HTML documentation from GATT schema(s).

    With gattc.yaml: generates docs for all schemas.
    Without: requires SCHEMA path argument.

    By default, generates separate files per service. Use --combined to merge
    all services into one file, or configure in gattc.yaml:

      output:
        docs:
          path: "docs/ble/"
          per_service: false
    """
    from .generators import docs as docs_gen
    from .changelog import load_changelog

    config = load_config()

    # Determine mode from flags or config
    use_combined = _resolve_combined_mode(
        combined, per_service, config.output.docs.is_combined() if config else False
    )

    if schema:
        schema_paths = [schema]
        output_path = output
    else:
        if not config:
            raise click.ClickException(
                "No schema specified and no gattc.yaml found."
            )
        schema_paths = find_schemas(config)
        if not schema_paths:
            raise click.ClickException("No .yaml files found in configured directories")
        output_path = output or config.output.docs.path

    # Load and validate all schemas
    loaded_schemas = []
    for schema_path in schema_paths:
        s, errors = load_and_validate_schema(schema_path)
        if errors:
            click.echo(f"Schema validation failed for {schema_path}:", err=True)
            for e in errors:
                click.echo(f"  - {e}", err=True)
            continue
        loaded_schemas.append((schema_path, s))

    if not loaded_schemas:
        raise click.ClickException("No schemas loaded successfully")

    # Clear output directory before generating
    if output_path and output_path.suffix != ".html":
        # It's a directory, clear it
        docs_cleared = _clear_docs_output(output_path)
        if docs_cleared:
            click.echo(f"Cleared {docs_cleared} HTML file(s) from output directory")

    # Determine root directory for loading changelogs
    root_dir = config.root_dir if config else Path.cwd()

    if use_combined:
        # Generate combined documentation
        if output_path and output_path.suffix == ".html":
            out_path = output_path
        elif output_path:
            out_path = output_path / "gatt_services.html"
        else:
            out_path = Path("gatt_services.html")

        try:
            schemas_only = [s for _, s in loaded_schemas]
            # Load changelogs for all schemas
            changelogs = {s.service.name: load_changelog(s.service.name, config, root_dir) for s in schemas_only}
            html_path = docs_gen.generate_combined(schemas_only, out_path, changelogs=changelogs)
            click.echo(f"Generated: {html_path}")
        except Exception as e:
            raise click.ClickException(f"Error generating combined docs: {e}")
    else:
        # Generate separate documentation files
        for schema_path, s in loaded_schemas:
            try:
                if output_path:
                    out_path = output_path / f"{schema_path.stem}.html"
                else:
                    out_path = schema_path.with_suffix(".html")

                # Load changelog for this service
                changelog = load_changelog(s.service.name, config, root_dir)
                html_path = docs_gen.generate(s, out_path, changelog=changelog)
                click.echo(f"Generated: {html_path}")
            except Exception as e:
                click.echo(f"Error generating docs for {schema_path}: {e}", err=True)


@main.command()
@click.argument("services", nargs=-1)
@click.option("--all", "update_all", is_flag=True, default=True, help="Update all service snapshots (default)")
def snapshot(services: Tuple[str, ...], update_all: bool):
    """Manually update schema snapshots.

    Note: Snapshots are automatically updated after each 'gattc compile'.
    This command is useful for updating snapshots without compiling, or
    for updating specific service snapshots only.

    Examples:
        gattc snapshot              # Update all service snapshots
        gattc snapshot sensor_svc   # Update specific service snapshot

    Snapshots are stored in gattc/snapshots/ by default, configurable via:
        snapshots:
          path: "custom/path/"
    """
    config = load_config()

    if not config:
        raise click.ClickException(
            "No gattc.yaml found. Run 'gattc init' to create one."
        )

    schema_paths = find_schemas(config)
    if not schema_paths:
        raise click.ClickException("No .yaml files found in configured directories")

    root_dir = config.root_dir

    # Load all schemas
    loaded_schemas = []
    for schema_path in schema_paths:
        s, errors = load_and_validate_schema(schema_path)
        if errors:
            click.echo(f"Warning: Skipping {schema_path}: validation errors", err=True)
            continue
        loaded_schemas.append(s)

    if not loaded_schemas:
        raise click.ClickException("No valid schemas found")

    # Filter by service names if specified
    if services:
        service_set = set(services)
        loaded_schemas = [s for s in loaded_schemas if s.service.name in service_set]
        if not loaded_schemas:
            raise click.ClickException(f"No schemas found for services: {', '.join(services)}")

    # Save snapshots
    snapshot_dir = get_snapshot_dir(config, root_dir)
    updated_count = 0

    for s in loaded_schemas:
        service_name = s.service.name
        snapshot_path = save_snapshot(service_name, s, config, root_dir)
        click.echo(f"Snapshot saved: {snapshot_path}")
        updated_count += 1

    click.echo(f"\nUpdated {updated_count} snapshot(s) in {snapshot_dir}")


@main.command()
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

  # HTML documentation output
  docs:
    path: "docs/ble/"
    per_service: false                # true = one .html per service
                                      # false = all services in single gatt_services.html (default)

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


if __name__ == "__main__":
    main()

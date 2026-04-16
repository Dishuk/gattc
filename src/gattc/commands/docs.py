"""Docs command — generate Markdown or HTML documentation from GATT schemas."""

from pathlib import Path
from typing import Optional

import click
from jinja2 import TemplateError

from .._errors import _handle_error, _is_debug
from ..config import find_schemas, load_config
from ..generators import docs as docs_gen
from ..generators.docs import SUFFIX_TO_FORMAT
from ..schema import load_and_validate_schema
from ..changelog import load_changelog
from .compile import _clear_files, _resolve_combined_mode


@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output directory or file path")
@click.option("--combined", is_flag=True, default=None, help="Generate all services in a single file")
@click.option("--per-service", "per_service", is_flag=True, default=None, help="Generate a separate file per service")
@click.option("-f", "--format", "fmt", type=click.Choice(["md", "html"]), default=None,
              help="Output format; otherwise inferred from -o suffix, gattc.yaml, or 'md'")
def docs(schema: Optional[Path], output: Optional[Path], combined: Optional[bool], per_service: Optional[bool], fmt: Optional[str]):
    """Generate documentation from GATT schema(s) as Markdown (default) or HTML.

    With gattc.yaml: generates docs for all schemas.
    Without: requires SCHEMA path argument.

    By default, generates separate files per service in Markdown. Use --combined
    to merge all services into one file, or configure in gattc.yaml:

      output:
        docs:
          path: "docs/ble/"
          per_service: false
          format: md        # or 'html'

    If -o points to a file with .md or .html extension, the format is inferred
    from the extension unless -f overrides it.
    """
    config = load_config()
    inferred_fmt = SUFFIX_TO_FORMAT.get(output.suffix) if output else None
    if fmt and inferred_fmt and fmt != inferred_fmt:
        raise click.ClickException(
            f"-f {fmt} conflicts with -o {output} (suffix implies {inferred_fmt}); "
            "drop one or make them match."
        )
    if fmt is None:
        fmt = inferred_fmt or (config.output.docs.format if config else "md")
    suffix = f".{fmt}"

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

    output_is_file = bool(output_path and output_path.suffix in SUFFIX_TO_FORMAT)

    # Clear only the specific files that will be regenerated
    if output_path and not output_is_file:
        if use_combined:
            docs_to_clear = [output_path / f"gatt_services{suffix}"]
        else:
            docs_to_clear = [output_path / f"{sp.stem}{suffix}" for sp, _ in loaded_schemas]
        docs_cleared = _clear_files(docs_to_clear)
        if docs_cleared:
            click.echo(f"Cleared {docs_cleared} {fmt.upper()} file(s) from output directory")

    # Determine root directory for loading changelogs
    root_dir = config.root_dir if config else Path.cwd()

    if use_combined:
        # Generate combined documentation
        if output_is_file:
            out_path = output_path
        elif output_path:
            out_path = output_path / f"gatt_services{suffix}"
        else:
            out_path = Path(f"gatt_services{suffix}")

        try:
            schemas_only = [s for _, s in loaded_schemas]
            changelogs = {s.service.name: load_changelog(s.service.name, config, root_dir) for s in schemas_only}
            doc_path = docs_gen.generate_combined(schemas_only, out_path, changelogs=changelogs, fmt=fmt)
            click.echo(f"Generated: {doc_path}")
        except (TemplateError, FileNotFoundError, ValueError) as e:
            raise click.ClickException(f"Error generating combined docs: {e}")
        except Exception as e:
            _handle_error(e, "Error generating combined docs")
    else:
        # Generate separate documentation files
        if output_is_file and len(loaded_schemas) > 1:
            raise click.ClickException(
                f"-o {output_path} is a file path but {len(loaded_schemas)} schemas were loaded; "
                "use a directory, --combined, or pass a single schema."
            )
        for schema_path, s in loaded_schemas:
            try:
                if output_is_file:
                    out_path = output_path
                elif output_path:
                    out_path = output_path / f"{schema_path.stem}{suffix}"
                else:
                    out_path = schema_path.with_suffix(suffix)

                changelog = load_changelog(s.service.name, config, root_dir)
                doc_path = docs_gen.generate(s, out_path, changelog=changelog, fmt=fmt)
                click.echo(f"Generated: {doc_path}")
            except (TemplateError, FileNotFoundError, ValueError) as e:
                click.echo(f"Error generating docs for {schema_path}: {e}", err=True)
            except Exception as e:
                if _is_debug():
                    raise
                click.echo(f"Error generating docs for {schema_path}: {e}", err=True)
                click.echo("  Use --debug for full traceback.", err=True)

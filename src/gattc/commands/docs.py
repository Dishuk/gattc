"""Docs command — generate Markdown or HTML documentation from GATT schemas."""

from pathlib import Path

import click
from jinja2 import TemplateError

from .._errors import handle_error, is_debug
from ..changelog import load_changelog
from ..config import load_config
from ..generators import docs as docs_gen
from ..generators.docs import SUFFIX_TO_FORMAT
from ..schema import Schema, load_and_validate_schema
from ._output_management import clear_files
from ._schema_loading import resolve_combined_mode, resolve_schema_paths


@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output directory or file path")
@click.option("--combined", is_flag=True, default=None, help="Generate all services in a single file")
@click.option("--per-service", "per_service", is_flag=True, default=None, help="Generate a separate file per service")
@click.option("-f", "--format", "fmt", type=click.Choice(["md", "html"]), default=None,
              help="Output format; otherwise inferred from -o suffix, gattc.yaml, or 'md'")
def docs(schema: Path | None, output: Path | None, combined: bool | None, per_service: bool | None, fmt: str | None) -> None:
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
    use_combined = resolve_combined_mode(
        combined, per_service, config.output.docs.is_combined() if config else False
    )

    schema_paths, _ = resolve_schema_paths(schema, config)
    output_path = output
    if not schema and not output_path:
        # Project mode: resolve_schema_paths guarantees config is non-None here
        assert config is not None
        output_path = config.output.docs.path

    loaded_schemas: list[tuple[Path, Schema]] = []
    for schema_path in schema_paths:
        s, errors = load_and_validate_schema(schema_path)
        if errors:
            click.echo(f"Schema validation failed for {schema_path}:", err=True)
            for e in errors:
                click.echo(f"  - {e}", err=True)
            continue
        assert s is not None
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
        docs_cleared = clear_files(docs_to_clear)
        if docs_cleared:
            click.echo(f"Cleared {docs_cleared} {fmt.upper()} file(s) from output directory")

    # Determine root directory for loading changelogs
    root_dir = config.root_dir if config else Path.cwd()

    if use_combined:
        # Generate combined documentation
        if output_is_file:
            assert output_path is not None  # output_is_file implies output_path is set
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
            handle_error(e, "Error generating combined docs")
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
                    assert output_path is not None
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
                if is_debug():
                    raise
                click.echo(f"Error generating docs for {schema_path}: {e}", err=True)
                click.echo("  Use --debug for full traceback.", err=True)

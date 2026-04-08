"""Release command — record schema changes and regenerate documentation."""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from ..config import find_schemas, load_config
from ..schema import load_and_validate_schema
from ..snapshot import get_snapshot_path, save_snapshot
from ..diff import SchemaDiff
from ..changelog import add_changelog_entry, load_changelog, save_changelog
from .compile import _load_diff, compile


@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-m", "--message", default=None, help="Describe what changed and why")
@click.option("--revert", is_flag=True, default=False, help="Revert the last release")
def release(schema: Optional[Path], message: Optional[str], revert: bool):
    """Record schema changes and regenerate documentation.

    Compares current schemas against stored snapshots, records changes
    as a changelog entry with your message, updates snapshots, and
    regenerates HTML documentation.

    The -m message should describe WHY the change was made — the tool
    records the structural details automatically.

    Use --revert to undo the last release (restores previous snapshot,
    removes last changelog entry). Only one level of undo.

    Examples:
        gattc release -m "Add humidity field for v2.1 hardware"
        gattc release -m "Remove deprecated legacy fields"
        gattc release --revert
    """
    from ..generators import docs as docs_gen

    config = load_config()

    # --- Revert mode ---
    if revert:
        if not config:
            raise click.ClickException("No gattc.yaml found.")

        schema_paths = find_schemas(config)
        if not schema_paths:
            raise click.ClickException("No .yaml files found in configured directories")

        root_dir = config.root_dir
        reverted = 0

        for schema_path in schema_paths:
            s, errors = load_and_validate_schema(schema_path)
            if errors:
                continue

            service_name = s.service.name
            snapshot_path = get_snapshot_path(service_name, config, root_dir)
            prev_path = snapshot_path.with_suffix(".prev.json")

            if prev_path.exists():
                prev_path.replace(snapshot_path)
            elif snapshot_path.exists():
                snapshot_path.unlink()

            entries = load_changelog(service_name, config, root_dir)
            if entries:
                removed = entries.pop()
                save_changelog(service_name, entries, config, root_dir)
                click.echo(f"{service_name}: Reverted Rev {removed['revision']}")
                reverted += 1

        if reverted == 0:
            raise click.ClickException("No changelog entries found to revert")

        click.echo(f"\nReverted {reverted} service(s)")

        # Regenerate docs via compile (handles unreleased banner automatically)
        click.echo("\nRecompiling...")
        ctx = click.get_current_context()
        ctx.invoke(compile, docs=True)
        return

    # --- Release mode ---
    if not message:
        raise click.ClickException("Missing option '-m'. Use: gattc release -m \"...\"")

    def _backup_snapshot(service_name, config, root_dir):
        """Save a .prev.json backup before overwriting the snapshot."""
        path = get_snapshot_path(service_name, config, root_dir)
        if path.exists():
            shutil.copy2(path, path.with_suffix(".prev.json"))

    # Single schema mode
    if schema:
        s, errors = load_and_validate_schema(schema)
        if errors:
            raise click.ClickException(
                f"Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        root_dir = config.root_dir if config else Path.cwd()
        service_name = s.service.name

        has_snapshot, diff = _load_diff(service_name, s, config, root_dir)

        if diff and diff.has_changes:
            changelog = add_changelog_entry(service_name, s, diff, config, root_dir, message=message)
            click.echo(f"{service_name}: Changes recorded (Rev {changelog[-1]['revision']})")
            click.echo(diff.to_changelog_text())
        else:
            changelog = load_changelog(service_name, config, root_dir)
            if not has_snapshot:
                click.echo(f"{service_name}: Initial snapshot created")
            else:
                click.echo(f"{service_name}: No changes detected")

        _backup_snapshot(service_name, config, root_dir)
        save_snapshot(service_name, s, config, root_dir)

        # Regenerate docs if configured
        docs_dir = config.output.docs.path if config else None
        if docs_dir:
            docs_output = docs_dir / f"{schema.stem}.html"
            html_path = docs_gen.generate(s, docs_output, diff=diff, changelog=changelog)
            click.echo(f"Generated: {html_path}")

        return

    # Project mode
    if not config:
        raise click.ClickException(
            "No schema specified and no gattc.yaml found.\n"
            "Either provide a schema path or create gattc.yaml with 'gattc init'."
        )

    schema_paths = find_schemas(config)
    if not schema_paths:
        raise click.ClickException("No .yaml files found in configured directories")

    root_dir = config.root_dir
    released_count = 0
    loaded_schemas = []
    diffs: Dict[str, SchemaDiff] = {}
    changelogs: Dict[str, List[Dict[str, Any]]] = {}

    for schema_path in schema_paths:
        s, errors = load_and_validate_schema(schema_path)
        if errors:
            click.echo(f"Warning: Skipping {schema_path}: validation errors", err=True)
            continue

        service_name = s.service.name
        loaded_schemas.append(s)

        has_snapshot, diff = _load_diff(service_name, s, config, root_dir)

        if diff and diff.has_changes:
            changelogs[service_name] = add_changelog_entry(
                service_name, s, diff, config, root_dir, message=message
            )
            click.echo(f"\n{service_name}: Changes recorded (Rev {changelogs[service_name][-1]['revision']})")
            click.echo(diff.to_changelog_text())
            diffs[service_name] = diff
            released_count += 1
        else:
            changelogs[service_name] = load_changelog(service_name, config, root_dir)
            if not has_snapshot:
                click.echo(f"\n{service_name}: Initial snapshot created")
            else:
                click.echo(f"\n{service_name}: No changes")

        _backup_snapshot(service_name, config, root_dir)
        save_snapshot(service_name, s, config, root_dir)

    if not loaded_schemas:
        raise click.ClickException("No valid schemas found")

    # Regenerate docs
    docs_dir = config.output.docs.path
    if docs_dir and loaded_schemas:
        if config.output.docs.is_combined():
            html_path = docs_gen.generate_combined(
                loaded_schemas,
                docs_dir / "gatt_services.html",
                diffs=diffs or None,
                changelogs=changelogs or None,
            )
            click.echo(f"\nGenerated: {html_path}")
        else:
            for s in loaded_schemas:
                sname = s.service.name
                html_path = docs_gen.generate(
                    s,
                    docs_dir / f"{sname}.html",
                    diff=diffs.get(sname),
                    changelog=changelogs.get(sname, []),
                )
                click.echo(f"Generated: {html_path}")

    click.echo(f"\nReleased {released_count} service(s) with changes")

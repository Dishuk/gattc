"""Changelog command — list and edit release entries."""

from pathlib import Path
from typing import List, Optional

import click

from ..changelog import (
    get_changelog_dir,
    get_revision_path,
    load_changelog,
)
from ..config import find_schemas, load_config
from ..schema import load_and_validate_schema


def _discover_services(config) -> List[str]:
    """Return service names from the project's schemas."""
    if not config:
        return []
    services = []
    for path in find_schemas(config):
        s, errors = load_and_validate_schema(path)
        if errors:
            click.echo(f"Warning: Skipping {path}: validation errors", err=True)
            continue
        services.append(s.service.name)
    return services


def _resolve_service(service: Optional[str], config) -> str:
    """Pick a service name; auto-selects the sole service if only one exists."""
    if service:
        return service
    services = _discover_services(config)
    if len(services) == 1:
        return services[0]
    if not services:
        raise click.ClickException("No services found. Run from a project with gattc.yaml.")
    names = ", ".join(services)
    raise click.ClickException(f"Multiple services found ({names}); use --service to pick one.")


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


@click.group(invoke_without_command=True)
@click.option("--service", default=None, help="Service name (required if project has multiple services).")
@click.pass_context
def changelog(ctx, service):
    """List and edit changelog entries.

    With no subcommand, prints the list of revisions.
    """
    ctx.obj = service
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_cmd)


@changelog.command("list")
@click.pass_context
def list_cmd(ctx):
    """List all changelog revisions for a service."""
    config = load_config()
    root_dir = config.root_dir if config else Path.cwd()
    service = _resolve_service(ctx.obj, config)

    entries = load_changelog(service, config, root_dir)
    if not entries:
        click.echo(f"{service}: no changelog entries.")
        return

    changelog_dir = get_changelog_dir(service, config, root_dir)
    rel_dir = _format_rel(changelog_dir, root_dir)

    header = f"{'Rev':<5} {'File':<36} Message"
    click.echo(header)
    click.echo("-" * len(header))
    for entry in entries:
        rev = entry["revision"]
        fname = f"{rel_dir}/{rev:03d}.md"
        msg = _first_line(entry.get("message", ""))
        click.echo(f"{rev:<5} {fname:<36} {msg}")


@changelog.command("path")
@click.argument("revision", type=int, required=False)
@click.pass_context
def path_cmd(ctx, revision):
    """Print the absolute path to a revision file (latest if unspecified)."""
    config = load_config()
    root_dir = config.root_dir if config else Path.cwd()
    service = _resolve_service(ctx.obj, config)

    rev = _resolve_revision(service, revision, config, root_dir)
    click.echo(str(get_revision_path(service, rev, config, root_dir)))


@changelog.command("edit")
@click.argument("revision", type=int, required=False)
@click.pass_context
def edit_cmd(ctx, revision):
    """Open a revision file in $EDITOR (latest if unspecified)."""
    config = load_config()
    root_dir = config.root_dir if config else Path.cwd()
    service = _resolve_service(ctx.obj, config)

    rev = _resolve_revision(service, revision, config, root_dir)
    path = get_revision_path(service, rev, config, root_dir)

    click.edit(filename=str(path))
    click.echo(f"{service}: updated rev {rev}")


def _resolve_revision(service: str, revision: Optional[int], config, root_dir: Path) -> int:
    entries = load_changelog(service, config, root_dir)
    if not entries:
        raise click.ClickException(f"{service}: no changelog entries.")

    if revision is None:
        return entries[-1]["revision"]

    for entry in entries:
        if entry.get("revision") == revision:
            return revision
    raise click.ClickException(f"{service}: revision {revision} not found.")


def _format_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)

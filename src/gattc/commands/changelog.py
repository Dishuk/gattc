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
    """Pick a single service name; auto-selects the sole service if only one exists."""
    if service:
        return service
    services = _discover_services(config)
    if len(services) == 1:
        return services[0]
    if not services:
        raise click.ClickException("No services found. Run from a project with gattc.yaml.")
    names = ", ".join(services)
    raise click.ClickException(f"Multiple services found ({names}); use --service to pick one.")


def _resolve_services(service: Optional[str], config) -> List[str]:
    """Return all services to operate on: one if --service is set, otherwise every discovered service."""
    if service:
        return [service]
    services = _discover_services(config)
    if not services:
        raise click.ClickException("No services found. Run from a project with gattc.yaml.")
    return services


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


@click.group(invoke_without_command=True)
@click.option(
    "--service",
    default=None,
    help=(
        "Limit to a specific service. `list` shows every service when omitted; "
        "`path` and `edit` require a single service (so this is needed only if "
        "the project defines more than one)."
    ),
)
@click.pass_context
def changelog(ctx, service):
    """List and edit changelog entries.

    Each release is stored as one markdown file per revision at
    `gattc/changelog/<service>/NNN.md`, where NNN is the revision number.

    Subcommands:

    \b
      list           Print all revisions (default when no subcommand).
      path [REV]     Print the absolute path to revision REV's .md file.
      edit [REV]     Open revision REV's .md file in $EDITOR.

    REV is the integer revision number (e.g. `1`, `2`, ...) shown in the
    first column of `changelog list`. For `path` and `edit`, REV is
    optional — omit it to target the latest revision.
    """
    ctx.obj = service
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_cmd)


@changelog.command("list")
@click.pass_context
def list_cmd(ctx):
    """List changelog revisions. Shows every service unless --service is set."""
    config = load_config()
    root_dir = config.root_dir if config else Path.cwd()
    services = _resolve_services(ctx.obj, config)

    for i, service in enumerate(services):
        if i > 0:
            click.echo()
        if len(services) > 1:
            click.echo(click.style(f"{service}", bold=True, fg="cyan"))

        entries = load_changelog(service, config, root_dir)
        if not entries:
            click.echo(f"  (no changelog entries)")
            continue

        changelog_dir = get_changelog_dir(service, config, root_dir)
        rel_dir = _format_rel(changelog_dir, root_dir)

        rows = [
            (
                str(entry["revision"]),
                f"{rel_dir}/{entry['revision']:03d}.md",
                _first_line(entry.get("message", "")),
            )
            for entry in entries
        ]
        rev_w = max(3, max(len(r[0]) for r in rows))
        file_w = max(4, max(len(r[1]) for r in rows))
        gap = "   "

        header = f"{'Rev':<{rev_w}}{gap}{'File':<{file_w}}{gap}Message"
        click.echo(click.style(header, bold=True))
        click.echo(click.style("-" * len(header), dim=True))
        for rev, fname, msg in rows:
            click.echo(f"{rev:<{rev_w}}{gap}{fname:<{file_w}}{gap}{msg}")


@changelog.command("path")
@click.argument("revision", type=int, required=False)
@click.pass_context
def path_cmd(ctx, revision):
    """Print the absolute path to a revision file.

    REVISION is the integer revision number. If omitted, the latest revision
    is used.
    """
    config = load_config()
    root_dir = config.root_dir if config else Path.cwd()
    service = _resolve_service(ctx.obj, config)

    rev = _resolve_revision(service, revision, config, root_dir)
    click.echo(str(get_revision_path(service, rev, config, root_dir)))


@changelog.command("edit")
@click.argument("revision", type=int, required=False)
@click.pass_context
def edit_cmd(ctx, revision):
    """Open a revision file in $EDITOR.

    REVISION is the integer revision number. If omitted, the latest revision
    is opened.
    """
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

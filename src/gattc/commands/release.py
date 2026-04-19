"""Release command — record schema changes and regenerate documentation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from .._errors import handle_error
from ..config import load_config
from ..generators import docs as docs_gen
from ..schema import Schema, load_and_validate_schema
from ..snapshot import save_snapshot
from ..diff import SchemaDiff
from ..changelog import (
    build_frontmatter,
    get_changelog_dir,
    get_revision_path,
    load_changelog,
    next_revision,
    write_entry,
)
from ._schema_loading import load_diff, resolve_schema_paths


_COMMENT_LINE_RE = re.compile(r"^\s*<!--.*?-->\s*$", re.MULTILINE)


def _strip_template_markers(body: str) -> str:
    """Remove lines that are entirely HTML comments from an edited body."""
    return _COMMENT_LINE_RE.sub("", body)


def _build_template_block(service_name: str, revision: int) -> str:
    """Render the comment header shown in the editor."""
    return (
        f"<!-- {service_name} rev {revision} -->\n"
        "<!-- Lines starting with '<!--' are ignored. -->\n"
        "<!-- Write release notes below. Empty message aborts. -->\n\n"
    )


@click.command()
@click.argument("schema", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("-m", "--message", default=None, help="Describe what changed and why. If omitted, an editor opens.")
@click.option(
    "--allow-empty", is_flag=True, default=False,
    help="Record a changelog entry even if the schema is unchanged (for "
         "infrastructure or build-process notes).",
)
def release(schema: Optional[Path], message: Optional[str], allow_empty: bool):
    """Record schema changes and regenerate documentation.

    Compares current schemas against stored snapshots, records changes
    as a changelog entry (one markdown file per revision), updates
    snapshots, and regenerates documentation.

    The message should describe WHY the change was made — the tool
    records the structural details automatically.

    If -m is omitted, an editor opens (like `git commit`) with a
    template showing the auto-detected changes; write your message
    there and save to record the release.

    Use --allow-empty to record a release with no schema changes (e.g.
    for infrastructure, build-process, or hardware revision notes).

    Examples:
        gattc release -m "Add humidity field for v2.1 hardware"
        gattc release                         # opens $EDITOR
        gattc release --allow-empty -m "Build 2.3.1 re-tag"
    """
    try:
        _release_impl(schema, message, allow_empty)
    except click.ClickException:
        raise
    except Exception as e:
        handle_error(e, "Release failed")


def _release_impl(schema: Optional[Path], message: Optional[str], allow_empty: bool) -> None:
    """Implementation of the release command; wrapped by release() for error handling."""
    config = load_config()
    schema_paths, root_dir = resolve_schema_paths(schema, config)
    is_explicit = schema is not None

    schema_inputs: List[tuple[Schema, str]] = []
    for schema_path in schema_paths:
        s, errors = load_and_validate_schema(schema_path)
        if errors:
            if is_explicit:
                raise click.ClickException(
                    "Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
                )
            click.echo(f"Warning: Skipping {schema_path}: validation errors", err=True)
            continue
        schema_inputs.append((s, schema_path.stem))

    if not schema_inputs:
        raise click.ClickException("No valid schemas found")

    released: List[tuple[Schema, str, Optional[SchemaDiff]]] = []
    for s, stem in schema_inputs:
        recorded, diff = _release_one(s, message, config, root_dir, allow_empty=allow_empty)
        if recorded:
            released.append((s, stem, diff))

    docs_dir = config.output.docs.path if config else None
    if docs_dir and released:
        fmt = config.output.docs.format if config else "md"
        schemas = [s for s, _, _ in released]
        diffs = {s.service.name: d for s, _, d in released}
        changelogs = {
            s.service.name: load_changelog(s.service.name, config, root_dir)
            for s, _, _ in released
        }
        if config and config.output.docs.is_combined():
            doc_path = docs_gen.generate_combined(
                schemas,
                docs_dir / f"gatt_services.{fmt}",
                diffs=diffs,
                changelogs=changelogs,
                fmt=fmt,
            )
            click.echo(f"\nGenerated: {doc_path}")
        else:
            for s, stem, diff in released:
                doc_path = docs_gen.generate(
                    s,
                    docs_dir / f"{stem}.{fmt}",
                    diff=diff,
                    changelog=changelogs[s.service.name],
                    fmt=fmt,
                )
                click.echo(f"Generated: {doc_path}")

    if not is_explicit:
        click.echo(f"\nReleased {len(released)} service(s)")


def _release_one(
    s: Schema,
    message: Optional[str],
    config: Optional[Any],
    root_dir: Path,
    *,
    allow_empty: bool = False,
) -> tuple[bool, Optional[SchemaDiff]]:
    """Record a single service's release. Returns (recorded, diff)."""
    service_name = s.service.name
    has_snapshot, diff = load_diff(service_name, s, config, root_dir)
    existing = load_changelog(service_name, config, root_dir)

    if not has_snapshot and existing:
        raise click.ClickException(
            f"{service_name}: inconsistent state — {len(existing)} changelog entries "
            f"exist but no snapshot was found.\n"
            f"A previous release likely failed or the snapshot was deleted.\n"
            f"  To start fresh: delete gattc/changelog/{service_name}/\n"
            f"  To reconcile:   restore gattc/snapshots/{service_name}.json from git."
        )

    if diff and diff.has_changes:
        return _commit_release(s, message, diff, config, root_dir, is_initial=False)

    if not has_snapshot:
        return _commit_release(s, message, None, config, root_dir, is_initial=True)

    if allow_empty:
        return _commit_release(s, message, None, config, root_dir, is_initial=False)

    click.echo(f"\n{service_name}: No changes")
    return False, diff


def _commit_release(
    s: Schema,
    message: Optional[str],
    diff: Optional[SchemaDiff],
    config: Optional[Any],
    root_dir: Path,
    *,
    is_initial: bool,
) -> tuple[bool, Optional[SchemaDiff]]:
    """Collect body, write changelog, then save snapshot (rolling back the
    changelog file if the snapshot write fails).

    diff is None for metadata-only entries (initial release, or --allow-empty
    on an unchanged schema). is_initial only affects the default body and the
    output wording.
    """
    service_name = s.service.name
    revision = next_revision(service_name, config, root_dir)
    fm = build_frontmatter(diff, revision)
    default_body = "Initial schema" if is_initial else "Update schema"

    if message is None:
        body = _collect_message_via_editor(service_name, revision, default_body)
    else:
        body = message.strip() or None

    if body is None:
        click.echo(f"{service_name}: Aborted (empty release notes)")
        return False, diff

    write_entry(service_name, revision, fm, body, config, root_dir)
    try:
        save_snapshot(service_name, s, config, root_dir)
    except Exception:
        get_revision_path(service_name, revision, config, root_dir).unlink(missing_ok=True)
        _cleanup_empty_changelog_dir(service_name, config, root_dir)
        raise

    if is_initial:
        label = "Initial release recorded"
    elif diff is None:
        label = "Empty release recorded"
    else:
        label = "Changes recorded"
    click.echo(f"\n{service_name}: {label} (Rev {revision})")
    if diff is not None:
        click.echo(diff.to_changelog_text())
    return True, diff


def _collect_message_via_editor(
    service_name: str,
    revision: int,
    default_body: str = "",
) -> Optional[str]:
    """Open $EDITOR on a tempfile and return the cleaned body.

    Returns None if the editor aborted (non-zero exit) or the saved body is
    empty after stripping the comment lines.
    """
    header = _build_template_block(service_name, revision)
    prefill = f"{default_body}\n" if default_body else ""
    initial = header + prefill

    edited = click.edit(text=initial, require_save=True, extension=".md")
    if edited is None:
        return None

    return _strip_template_markers(edited).strip() or None


def _cleanup_empty_changelog_dir(
    service_name: str, config: Optional[Any], root_dir: Path
) -> None:
    """Remove gattc/changelog/<service>/ if it exists and is empty."""
    changelog_dir = get_changelog_dir(service_name, config, root_dir)
    if changelog_dir.exists() and not any(changelog_dir.iterdir()):
        changelog_dir.rmdir()

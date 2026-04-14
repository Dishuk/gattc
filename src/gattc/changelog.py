"""
Changelog storage: one markdown file per revision with YAML frontmatter.

Layout:
    gattc/changelog/<service>/001.md
    gattc/changelog/<service>/002.md

Each file:
    ---
    revision: 2
    timestamp: 2026-04-14 10:30
    characteristics:
      added: [...]
    ---
    Author-written release notes (markdown).
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import click
import yaml

from .diff import SchemaDiff
from .snapshot import get_snapshot_dir


def get_changelog_dir(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> Path:
    """Directory holding per-revision .md files for a service."""
    snapshots_dir = get_snapshot_dir(config, root_dir)
    return snapshots_dir.parent / "changelog" / service_name


def get_revision_path(service_name: str, revision: int, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> Path:
    """File path for a specific revision's markdown file."""
    return get_changelog_dir(service_name, config, root_dir) / f"{revision:03d}.md"


def _iter_revision_files(service_name: str, config: Optional[Any], root_dir: Optional[Path]) -> Iterator[Tuple[int, Path]]:
    """Yield (revision, path) for every valid revision file in the service's changelog dir."""
    changelog_dir = get_changelog_dir(service_name, config, root_dir)
    if not changelog_dir.exists():
        return
    for path in changelog_dir.glob("*.md"):
        try:
            yield int(path.stem), path
        except ValueError:
            continue


def _parse_entry(path: Path) -> Dict[str, Any]:
    """Parse a changelog .md file into a dict entry."""
    text = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    entry: Dict[str, Any] = yaml.safe_load(frontmatter) or {}
    entry["message"] = body.strip()
    return entry


def split_frontmatter(text: str) -> Tuple[str, str]:
    """Split a markdown file into (frontmatter_yaml, body).

    Raises ValueError if fences are missing or malformed.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("missing opening '---' frontmatter fence")
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            fm = "".join(lines[1:i]).strip("\n")
            body = "".join(lines[i + 1:]).lstrip("\n")
            return fm, body
    raise ValueError("missing closing '---' frontmatter fence")


def load_changelog(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all changelog entries for a service, sorted oldest-first."""
    entries: List[Tuple[int, Dict[str, Any]]] = []
    for rev, path in _iter_revision_files(service_name, config, root_dir):
        try:
            entry = _parse_entry(path)
        except (ValueError, yaml.YAMLError) as e:
            click.echo(f"warning: skipping malformed changelog file {path}: {e}", err=True)
            continue
        entries.append((rev, entry))

    entries.sort(key=lambda x: x[0])
    return [e for _, e in entries]


def next_revision(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> int:
    """Compute the next revision number based on existing files."""
    revisions = [rev for rev, _ in _iter_revision_files(service_name, config, root_dir)]
    return (max(revisions) + 1) if revisions else 1


def build_frontmatter(diff: Optional[SchemaDiff], revision: int) -> Dict[str, Any]:
    """Build the frontmatter dict from a SchemaDiff.

    Pass diff=None for metadata-only entries (initial release or --allow-empty
    on an unchanged schema).
    """
    fm: Dict[str, Any] = {
        "revision": revision,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    if diff is None:
        return fm

    if diff.service_changes:
        fm["service_changes"] = list(diff.service_changes)

    if diff.schema_revision_changed:
        fm["schema_revision"] = {
            "old": diff.old_schema_revision,
            "new": diff.new_schema_revision,
        }

    characteristics: Dict[str, Any] = {"added": [], "removed": [], "modified": {}}

    for char_change in diff.characteristic_changes:
        if char_change.change_type == "added":
            characteristics["added"].append(char_change.name)
        elif char_change.change_type == "removed":
            characteristics["removed"].append(char_change.name)
        elif char_change.change_type == "modified":
            mods: Dict[str, Any] = {}

            if char_change.uuid_change:
                mods["uuid"] = {
                    "old": char_change.uuid_change[0],
                    "new": char_change.uuid_change[1],
                }
            if char_change.description_changed:
                mods["description_changed"] = True
            if char_change.payload_config_changed:
                mods["payload_config_changed"] = True
            if char_change.properties_added:
                mods["properties_added"] = char_change.properties_added
            if char_change.properties_removed:
                mods["properties_removed"] = char_change.properties_removed
            if char_change.permissions_added:
                mods["permissions_added"] = char_change.permissions_added
            if char_change.permissions_removed:
                mods["permissions_removed"] = char_change.permissions_removed
            if char_change.offsets_changed:
                mods["offsets_changed"] = True

            fields_added, fields_removed, fields_modified = [], [], []
            for fc in char_change.field_changes:
                if fc.change_type == "added":
                    info: Dict[str, Any] = {"name": fc.name}
                    if fc.new_value:
                        info["type"] = fc.new_value
                    fields_added.append(info)
                elif fc.change_type == "removed":
                    fields_removed.append(fc.name)
                elif fc.change_type == "modified":
                    mod: Dict[str, Any] = {"name": fc.name}
                    if fc.details:
                        mod["detail"] = fc.details
                    fields_modified.append(mod)

            if fields_added:
                mods["fields_added"] = fields_added
            if fields_removed:
                mods["fields_removed"] = fields_removed
            if fields_modified:
                mods["fields_modified"] = fields_modified

            if mods:
                characteristics["modified"][char_change.name] = mods

    characteristics = {k: v for k, v in characteristics.items() if v}
    if characteristics:
        fm["characteristics"] = characteristics

    return fm


def dump_frontmatter(fm: Dict[str, Any]) -> str:
    """Render a frontmatter dict as a YAML fenced block."""
    body = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return f"---\n{body}---\n"


def write_entry(
    service_name: str,
    revision: int,
    frontmatter: Dict[str, Any],
    body: str,
    config: Optional[Any] = None,
    root_dir: Optional[Path] = None,
) -> Path:
    """Write a changelog revision file (frontmatter + body)."""
    path = get_revision_path(service_name, revision, config, root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_frontmatter(frontmatter) + body.rstrip() + "\n"
    path.write_text(content, encoding="utf-8")
    return path

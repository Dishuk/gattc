"""
Changelog history storage for tracking schema changes over time.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .diff import SchemaDiff
from .schema import Schema


def get_changelog_path(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> Path:
    """Get path to changelog file for a service.

    Args:
        service_name: Name of the service.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        Path to the service's changelog JSON file.
    """
    from .snapshot import get_snapshot_dir
    return get_snapshot_dir(config, root_dir) / f"{service_name}.changelog.json"


def load_changelog(service_name: str, config: Optional[Any] = None, root_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load changelog history for a service.

    Args:
        service_name: Name of the service.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        List of changelog entries (newest first), empty list if no history.
    """
    changelog_path = get_changelog_path(service_name, config, root_dir)

    if not changelog_path.exists():
        return []

    with open(changelog_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_changelog(
    service_name: str,
    entries: List[Dict[str, Any]],
    config: Optional[Any] = None,
    root_dir: Optional[Path] = None
) -> Path:
    """Save changelog history for a service.

    Args:
        service_name: Name of the service.
        entries: List of changelog entries.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        Path to the saved changelog file.
    """
    changelog_path = get_changelog_path(service_name, config, root_dir)
    changelog_path.parent.mkdir(parents=True, exist_ok=True)

    with open(changelog_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

    return changelog_path


def add_changelog_entry(
    service_name: str,
    schema: Schema,
    diff: SchemaDiff,
    config: Optional[Any] = None,
    root_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Add a new changelog entry if there are changes.

    Args:
        service_name: Name of the service.
        schema: Current schema (for version info).
        diff: The diff containing changes.
        config: Optional Config object.
        root_dir: Root directory for path resolution.

    Returns:
        Updated changelog entries list.
    """
    if not diff.has_changes:
        return load_changelog(service_name, config, root_dir)

    # Load existing changelog
    entries = load_changelog(service_name, config, root_dir)

    # Determine next revision number (auto-increment)
    if entries:
        last_revision = entries[-1].get("revision") or 0
        next_revision = last_revision + 1
    else:
        next_revision = 1

    # Build structured entry
    new_entry: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "revision": next_revision,
    }

    # Service-level changes
    if diff.service_changes:
        new_entry["service_changes"] = list(diff.service_changes)

    # Schema revision change
    if diff.schema_revision_changed:
        new_entry["schema_revision"] = {
            "old": diff.old_schema_revision,
            "new": diff.new_schema_revision
        }

    # Characteristics changes
    characteristics: Dict[str, Any] = {
        "added": [],
        "removed": [],
        "modified": {}
    }

    for char_change in diff.characteristic_changes:
        if char_change.change_type == 'added':
            characteristics["added"].append(char_change.name)
        elif char_change.change_type == 'removed':
            characteristics["removed"].append(char_change.name)
        elif char_change.change_type == 'modified':
            mods: Dict[str, Any] = {}

            if char_change.uuid_change:
                mods["uuid"] = {
                    "old": char_change.uuid_change[0],
                    "new": char_change.uuid_change[1]
                }

            if char_change.description_changed:
                mods["description_changed"] = True

            if char_change.payload_config_changed:
                mods["payload_config_changed"] = True

            if char_change.properties_added:
                mods["properties_added"] = char_change.properties_added

            if char_change.properties_removed:
                mods["properties_removed"] = char_change.properties_removed

            if char_change.offsets_changed:
                mods["offsets_changed"] = True

            # Process field changes
            fields_added = []
            fields_removed = []
            fields_modified = []

            for field_change in char_change.field_changes:
                if field_change.change_type == 'added':
                    field_info: Dict[str, Any] = {"name": field_change.name}
                    if field_change.new_value:
                        field_info["type"] = field_change.new_value
                    fields_added.append(field_info)
                elif field_change.change_type == 'removed':
                    fields_removed.append(field_change.name)
                elif field_change.change_type == 'modified':
                    field_mod: Dict[str, Any] = {"name": field_change.name}
                    if field_change.details:
                        field_mod["detail"] = field_change.details
                    fields_modified.append(field_mod)

            if fields_added:
                mods["fields_added"] = fields_added
            if fields_removed:
                mods["fields_removed"] = fields_removed
            if fields_modified:
                mods["fields_modified"] = fields_modified

            if mods:
                characteristics["modified"][char_change.name] = mods

    # Only include characteristics if there are changes
    if characteristics["added"] or characteristics["removed"] or characteristics["modified"]:
        # Remove empty lists/dicts for cleaner output
        if not characteristics["added"]:
            del characteristics["added"]
        if not characteristics["removed"]:
            del characteristics["removed"]
        if not characteristics["modified"]:
            del characteristics["modified"]
        new_entry["characteristics"] = characteristics

    # Append to end (oldest first, newest last)
    entries.append(new_entry)

    # Save updated changelog
    save_changelog(service_name, entries, config, root_dir)

    return entries

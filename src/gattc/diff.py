"""
Schema diffing and change detection for changelog generation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set

from .schema import PAYLOAD_TYPES, Schema
from .snapshot import _schema_to_dict

# Tags emitted in SchemaDiff.service_changes. Presentation layers look up
# display strings through the label tables below; unknown tags should
# surface as errors, not free text. Both label maps MUST share the same
# keyset — enforced by tests.
ServiceChangeTag = Literal["name", "uuid", "description"]

# Long form, used by the CLI changelog output and the HTML changelog cell.
SERVICE_CHANGE_LABELS: Dict[str, str] = {
    "name": "Service name changed",
    "uuid": "Service UUID changed",
    "description": "Service description changed",
}

# Short form, used as row labels in the Markdown "Modified service" table.
SERVICE_CHANGE_ROW_LABELS: Dict[str, str] = {
    "name": "Name changed",
    "uuid": "UUID changed",
    "description": "Description updated",
}


@dataclass
class FieldChange:
    """Represents a change to a single field."""
    name: str
    change_type: Literal['added', 'removed', 'modified']
    old_value: Any = None
    new_value: Any = None
    details: str = ""


@dataclass
class CharacteristicChange:
    """Represents changes to a characteristic."""
    name: str
    change_type: Literal['added', 'removed', 'modified']
    field_changes: List[FieldChange] = field(default_factory=list)
    uuid_change: Optional[tuple] = None  # (old_uuid, new_uuid)
    properties_added: List[str] = field(default_factory=list)
    properties_removed: List[str] = field(default_factory=list)
    permissions_added: List[str] = field(default_factory=list)
    permissions_removed: List[str] = field(default_factory=list)
    offsets_changed: bool = False
    description_changed: bool = False
    payload_config_changed: bool = False

    @property
    def has_changes(self) -> bool:
        """True if a 'modified' change carries any actual difference."""
        return bool(
            self.field_changes or self.uuid_change
            or self.properties_added or self.properties_removed
            or self.permissions_added or self.permissions_removed
            or self.offsets_changed or self.description_changed
            or self.payload_config_changed
        )


@dataclass
class SchemaDiff:
    """Represents the complete diff between two schema versions."""
    service_name: str
    has_changes: bool
    characteristic_changes: List[CharacteristicChange] = field(default_factory=list)
    service_changes: List[ServiceChangeTag] = field(default_factory=list)
    schema_version_changed: bool = False
    old_schema_version: Optional[str] = None
    new_schema_version: Optional[str] = None
    schema_revision_changed: bool = False
    old_schema_revision: Optional[int] = None
    new_schema_revision: Optional[int] = None

    def to_changelog_text(self) -> str:
        """Generate human-readable changelog.

        Returns:
            Formatted changelog text for CLI output.
        """
        if not self.has_changes:
            return "  No changes detected."

        lines = []

        if self.schema_version_changed:
            lines.append(f"  Schema version: {self.old_schema_version} -> {self.new_schema_version}")

        if self.schema_revision_changed:
            old_rev = self.old_schema_revision if self.old_schema_revision is not None else "none"
            new_rev = self.new_schema_revision if self.new_schema_revision is not None else "none"
            lines.append(f"  Schema revision: {old_rev} -> {new_rev}")

        for service_change in self.service_changes:
            lines.append(f"  {SERVICE_CHANGE_LABELS[service_change]}")

        for char_change in self.characteristic_changes:
            if char_change.change_type == 'added':
                lines.append(f"  + Added characteristic: {char_change.name}")
            elif char_change.change_type == 'removed':
                lines.append(f"  - Removed characteristic: {char_change.name}")
            elif char_change.change_type == 'modified':
                lines.append(f"  Modified: {char_change.name}")

                if char_change.description_changed:
                    lines.append(f"      Description changed")

                if char_change.payload_config_changed:
                    lines.append(f"      Payload config changed")

                if char_change.uuid_change:
                    old_uuid, new_uuid = char_change.uuid_change
                    lines.append(f"      UUID changed: {old_uuid} -> {new_uuid}")

                if char_change.properties_added:
                    lines.append(f"      + Properties: {', '.join(char_change.properties_added)}")
                if char_change.properties_removed:
                    lines.append(f"      - Properties: {', '.join(char_change.properties_removed)}")
                if char_change.permissions_added:
                    lines.append(f"      + Permissions: {', '.join(char_change.permissions_added)}")
                if char_change.permissions_removed:
                    lines.append(f"      - Permissions: {', '.join(char_change.permissions_removed)}")

                for field_change in char_change.field_changes:
                    if field_change.change_type == 'added':
                        detail = f" ({field_change.new_value})" if field_change.new_value else ""
                        lines.append(f"      + {field_change.name}{detail}")
                    elif field_change.change_type == 'removed':
                        lines.append(f"      - {field_change.name}")
                    elif field_change.change_type == 'modified':
                        if field_change.details:
                            lines.append(f"      ~ {field_change.name}: {field_change.details}")
                        else:
                            lines.append(f"      ~ {field_change.name}")

                if char_change.offsets_changed:
                    lines.append(f"      Payload offsets changed")

        return "\n".join(lines)

    def get_characteristic_status(self, char_name: str) -> Optional[Literal['added', 'removed', 'modified']]:
        """Get the change status for a specific characteristic.

        Args:
            char_name: Name of the characteristic.

        Returns:
            Change type or None if unchanged.
        """
        for change in self.characteristic_changes:
            if change.name == char_name:
                return change.change_type
        return None

    def get_field_status(self, char_name: str, field_name: str) -> Optional[Literal['added', 'removed', 'modified']]:
        """Get the change status for a specific field.

        Args:
            char_name: Name of the characteristic.
            field_name: Name of the field.

        Returns:
            Change type or None if unchanged.
        """
        for change in self.characteristic_changes:
            if change.name == char_name:
                for field_change in change.field_changes:
                    if field_change.name == field_name:
                        return field_change.change_type
        return None


def _compare_fields(
    old_fields: List[Dict[str, Any]],
    new_fields: List[Dict[str, Any]]
) -> tuple[List[FieldChange], bool]:
    """Compare two lists of fields and return changes.

    Args:
        old_fields: Fields from old snapshot.
        new_fields: Fields from new schema.

    Returns:
        Tuple of (field changes, offsets_changed flag).
    """
    changes = []
    offsets_changed = False

    old_by_name = {f['name']: f for f in old_fields}
    new_by_name = {f['name']: f for f in new_fields}

    old_names = set(old_by_name.keys())
    new_names = set(new_by_name.keys())

    # Added fields
    for name in new_names - old_names:
        field_data = new_by_name[name]
        type_info = field_data.get('type_info', {})
        type_str = _format_type_info(type_info)
        changes.append(FieldChange(
            name=name,
            change_type='added',
            new_value=type_str
        ))

    # Removed fields
    for name in old_names - new_names:
        changes.append(FieldChange(
            name=name,
            change_type='removed'
        ))

    # Check for modifications in common fields
    for name in old_names & new_names:
        old_field = old_by_name[name]
        new_field = new_by_name[name]

        # Track offset changes separately
        if old_field.get('offset') != new_field.get('offset'):
            offsets_changed = True

        # Check for other modifications (type, unit, etc.)
        differences = _compare_field_details(old_field, new_field)
        if differences:
            changes.append(FieldChange(
                name=name,
                change_type='modified',
                old_value=old_field,
                new_value=new_field,
                details=differences
            ))

    # Sort changes by offset (new offset for added/modified, old offset for removed)
    def get_sort_key(change: FieldChange) -> int:
        if change.change_type == 'added':
            return new_by_name[change.name].get('offset', 0)
        elif change.change_type == 'removed':
            return old_by_name[change.name].get('offset', 0)
        else:  # modified
            return change.new_value.get('offset', 0) if isinstance(change.new_value, dict) else 0

    changes.sort(key=get_sort_key)

    return changes, offsets_changed


def _format_type_info(type_info: Dict[str, Any]) -> str:
    """Format type_info dict into readable type string."""
    if not type_info:
        return "unknown"

    base = type_info.get('base', 'unknown')
    endian = type_info.get('endian', 'little')
    is_array = type_info.get('is_array', False)
    array_size = type_info.get('array_size')

    result = base
    if type_info.get('size', 1) > 1 and endian == 'big':
        result += '_be'

    if is_array:
        if array_size is None:
            result += '[]'
        else:
            result += f'[{array_size}]'

    return result


def _compare_field_details(old_field: Dict[str, Any], new_field: Dict[str, Any]) -> str:
    """Compare field details and return human-readable difference description.

    Note: Offset changes are tracked separately, not included here.
    """
    differences = []

    old_type = old_field.get('type_info', {})
    new_type = new_field.get('type_info', {})

    # Compare type
    old_type_str = _format_type_info(old_type)
    new_type_str = _format_type_info(new_type)
    if old_type_str != new_type_str:
        differences.append(f"type {old_type_str} -> {new_type_str}")

    # Compare description
    if old_field.get('description') != new_field.get('description'):
        if new_field.get('description'):
            differences.append("description changed")

    # Compare unit
    if old_field.get('unit') != new_field.get('unit'):
        old_unit = old_field.get('unit', 'none')
        new_unit = new_field.get('unit', 'none')
        differences.append(f"unit {old_unit} -> {new_unit}")

    # Compare values
    if old_field.get('values') != new_field.get('values'):
        differences.append("values changed")

    # Compare bits (normalize keys to strings for comparison since JSON converts int keys to strings)
    old_bits = old_field.get('bits')
    new_bits = new_field.get('bits')
    if old_bits is not None or new_bits is not None:
        old_bits_normalized = {str(k): v for k, v in (old_bits or {}).items()}
        new_bits_normalized = {str(k): v for k, v in (new_bits or {}).items()}
        if old_bits_normalized != new_bits_normalized:
            differences.append("bitfield changed")

    # Compare nested struct fields (for repeated structs)
    old_nested = old_field.get('fields')
    new_nested = new_field.get('fields')
    if old_nested is not None or new_nested is not None:
        if old_nested != new_nested:
            differences.append("struct fields changed")

    return ", ".join(differences)


def _compare_payloads(
    old_payload: Optional[Dict[str, Any]],
    new_payload: Optional[Dict[str, Any]],
    payload_name: str
) -> tuple[List[FieldChange], bool, bool]:
    """Compare two payloads and return field changes.

    Args:
        old_payload: Old payload dict or None.
        new_payload: New payload dict or None.
        payload_name: Name of the payload type (for context).

    Returns:
        Tuple of (field changes, offsets_changed flag, config_changed flag).
    """
    changes = []
    offsets_changed = False
    config_changed = False

    old_fields = (old_payload or {}).get('fields', [])
    new_fields = (new_payload or {}).get('fields', [])

    # Check payload config changes (mode, min_size, max_size)
    if old_payload and new_payload:
        if old_payload.get('mode') != new_payload.get('mode'):
            config_changed = True
        if old_payload.get('min_size') != new_payload.get('min_size'):
            config_changed = True
        if old_payload.get('max_size') != new_payload.get('max_size'):
            config_changed = True

    # If one has payload and other doesn't
    if old_payload and not new_payload:
        for field_data in old_fields:
            changes.append(FieldChange(
                name=field_data['name'],
                change_type='removed'
            ))
    elif new_payload and not old_payload:
        for field_data in new_fields:
            type_str = _format_type_info(field_data.get('type_info', {}))
            changes.append(FieldChange(
                name=field_data['name'],
                change_type='added',
                new_value=type_str
            ))
    else:
        field_changes, offsets_changed = _compare_fields(old_fields, new_fields)
        changes.extend(field_changes)

    return changes, offsets_changed, config_changed


def _compare_characteristics(
    old_char: Dict[str, Any],
    new_char: Dict[str, Any]
) -> CharacteristicChange:
    """Compare two characteristics and return detailed changes.

    Args:
        old_char: Characteristic data from old snapshot.
        new_char: Characteristic data from new schema.

    Returns:
        CharacteristicChange with all detected changes.
    """
    field_changes = []
    description_changed = False
    payload_config_changed = False
    uuid_change = None

    old_uuid = old_char.get('uuid')
    new_uuid = new_char.get('uuid')
    if old_uuid != new_uuid:
        uuid_change = (old_uuid, new_uuid)

    if old_char.get('description') != new_char.get('description'):
        description_changed = True

    old_props = set(old_char.get('properties', []))
    new_props = set(new_char.get('properties', []))
    properties_added = sorted(new_props - old_props)
    properties_removed = sorted(old_props - new_props)

    old_perms = set(old_char.get('permissions', []))
    new_perms = set(new_char.get('permissions', []))
    permissions_added = sorted(new_perms - old_perms)
    permissions_removed = sorted(old_perms - new_perms)

    # Compare all payload types
    offsets_changed = False
    for payload_type in PAYLOAD_TYPES:
        old_payload = old_char.get(payload_type)
        new_payload = new_char.get(payload_type)
        payload_field_changes, payload_offsets_changed, payload_cfg_changed = _compare_payloads(old_payload, new_payload, payload_type)
        field_changes.extend(payload_field_changes)
        if payload_offsets_changed:
            offsets_changed = True
        if payload_cfg_changed:
            payload_config_changed = True

    return CharacteristicChange(
        name=new_char['name'],
        change_type='modified',
        field_changes=field_changes,
        uuid_change=uuid_change,
        properties_added=properties_added,
        properties_removed=properties_removed,
        permissions_added=permissions_added,
        permissions_removed=permissions_removed,
        offsets_changed=offsets_changed,
        description_changed=description_changed,
        payload_config_changed=payload_config_changed
    )


def diff_schemas(old: Optional[Dict[str, Any]], new: Schema) -> SchemaDiff:
    """Compare old snapshot to new schema, return structured diff.

    Args:
        old: Old snapshot data as dictionary, or None for initial snapshot.
        new: New schema object.

    Returns:
        SchemaDiff containing all detected changes.
    """
    new_dict = _schema_to_dict(new)
    service_name = new.service.name

    # No previous snapshot - no changes to report
    if old is None:
        return SchemaDiff(
            service_name=service_name,
            has_changes=False
        )

    characteristic_changes = []
    service_changes = []
    has_changes = False

    # Check schema version change
    old_version = old.get('schema_version', '1.0')
    new_version = new_dict.get('schema_version', '1.0')
    schema_version_changed = old_version != new_version
    if schema_version_changed:
        has_changes = True

    # Check schema revision change (user-controlled revision number)
    old_revision = old.get('schema_revision')
    new_revision = new_dict.get('schema_revision')
    schema_revision_changed = old_revision != new_revision
    if schema_revision_changed:
        has_changes = True

    # Check service-level changes
    old_service = old.get('service', {})
    new_service = new_dict.get('service', {})

    if old_service.get('name') != new_service.get('name'):
        service_changes.append("name")
        has_changes = True

    if old_service.get('uuid') != new_service.get('uuid'):
        service_changes.append("uuid")
        has_changes = True

    if old_service.get('description') != new_service.get('description'):
        service_changes.append("description")
        has_changes = True

    # Build characteristic maps
    old_chars = {c['name']: c for c in old.get('characteristics', [])}
    new_chars = {c['name']: c for c in new_dict.get('characteristics', [])}

    old_names = set(old_chars.keys())
    new_names = set(new_chars.keys())

    # Added characteristics
    for name in sorted(new_names - old_names):
        has_changes = True
        characteristic_changes.append(CharacteristicChange(
            name=name,
            change_type='added'
        ))

    # Removed characteristics
    for name in sorted(old_names - new_names):
        has_changes = True
        characteristic_changes.append(CharacteristicChange(
            name=name,
            change_type='removed'
        ))

    # Modified characteristics
    for name in sorted(old_names & new_names):
        old_char = old_chars[name]
        new_char = new_chars[name]

        char_change = _compare_characteristics(old_char, new_char)

        if char_change.has_changes:
            has_changes = True
            characteristic_changes.append(char_change)

    return SchemaDiff(
        service_name=service_name,
        has_changes=has_changes,
        characteristic_changes=characteristic_changes,
        service_changes=service_changes,
        schema_version_changed=schema_version_changed,
        old_schema_version=old_version if schema_version_changed else None,
        new_schema_version=new_version if schema_version_changed else None,
        schema_revision_changed=schema_revision_changed,
        old_schema_revision=old_revision if schema_revision_changed else None,
        new_schema_revision=new_revision if schema_revision_changed else None
    )

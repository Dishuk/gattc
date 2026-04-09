"""
Schema loading and validation for GATT service definitions.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from ._util import warn_unknown_keys as _warn_unknown_keys


# Payload special keys (prefixed with _)
PAYLOAD_MODE_KEY = "_mode"
PAYLOAD_MIN_SIZE_KEY = "_min_size"
PAYLOAD_MAX_SIZE_KEY = "_max_size"

# Payload type names (field names on Characteristic dataclass)
PAYLOAD_TYPES = ('payload', 'read_payload', 'write_payload', 'notify_payload')

# C11 reserved keywords
C_KEYWORDS = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while",
    "_Alignas", "_Alignof", "_Atomic", "_Bool", "_Complex", "_Generic",
    "_Imaginary", "_Noreturn", "_Static_assert", "_Thread_local",
    "true", "false",
})

# Type size mapping (base types without endianness suffix)
BASE_TYPE_SIZES = {
    "uint8": 1,
    "int8": 1,
    "uint16": 2,
    "int16": 2,
    "uint32": 4,
    "int32": 4,
    "uint64": 8,
    "int64": 8,
    "bool": 1,
    "bytes": 1,  # alias for uint8, for raw data
}


@dataclass
class TypeInfo:
    """Parsed type information."""
    base: str               # e.g., "uint16", "bytes", "int"
    size: int               # size in bytes
    endian: str             # "little", "big", or "none"
    is_array: bool          # True if array type
    array_size: Optional[Union[int, str]] = None  # int for fixed, str for dynamic, None for MTU-fill
    is_repeated_struct: bool = False  # True if this is a repeated struct (name[]:)


def parse_type(type_str: str) -> TypeInfo:
    """Parse a type string into TypeInfo.

    Examples:
        uint16 -> TypeInfo(base="uint16", size=2, endian="little")
        uint16_be -> TypeInfo(base="uint16", size=2, endian="big")
        bytes[6] -> TypeInfo(base="bytes", size=1, is_array=True, array_size=6)
        uint16[10] -> TypeInfo(base="uint16", size=2, is_array=True, array_size=10)
        uint16[] -> TypeInfo(base="uint16", size=2, is_array=True, array_size=None)
    """
    original = type_str
    endian = "little"

    if type_str.endswith("_be"):
        endian = "big"
        type_str = type_str[:-3]

    array_match = re.match(r"^(.+?)\[([^\]]*)\]$", type_str)
    if array_match:
        base_type = array_match.group(1)
        array_spec = array_match.group(2)

        base_info = parse_type(base_type)
        if endian == "big":
            base_info = TypeInfo(
                base=base_info.base,
                size=base_info.size,
                endian="big",
                is_array=base_info.is_array,
                array_size=base_info.array_size,
            )

        if array_spec == "":
            array_size = None  # flexible (MTU-fill)
        elif array_spec.isdigit():
            array_size = int(array_spec)  # fixed size
        else:
            raise ValueError(f"Invalid array size '{array_spec}' in '{original}'. Use [N] for fixed or [] for flexible.")

        return TypeInfo(
            base=base_info.base,
            size=base_info.size,
            endian=base_info.endian,
            is_array=True,
            array_size=array_size,
        )

    if type_str in BASE_TYPE_SIZES:
        size = BASE_TYPE_SIZES[type_str]
        # Single-byte types have no endianness
        if size == 1:
            endian = "none"
        return TypeInfo(base=type_str, size=size, endian=endian, is_array=False)

    raise ValueError(f"Unknown type: {original}")


@dataclass
class Field:
    """Represents a field in a characteristic payload."""
    name: str
    type_info: TypeInfo
    offset: Optional[int] = None  # None means auto-compute
    description: str = ""
    unit: Optional[str] = None
    values: Optional[Union[List[int], List[Dict[str, str]], str]] = None  # range, named values, or text
    bits: Optional[Dict[str, str]] = None  # bitfield definitions
    fields: Optional[List["Field"]] = None  # for repeated structs


@dataclass
class Payload:
    """Represents the payload structure of a characteristic."""
    fields: List[Field] = field(default_factory=list)
    mode: Optional[str] = None  # "variable", "mtu_packed", etc.
    min_size: Optional[int] = None
    max_size: Optional[int] = None

    def compute_offsets(self) -> None:
        """Compute auto offsets for fields that don't have explicit offsets."""
        current_offset = 0
        for f in self.fields:
            if f.offset is None:
                f.offset = current_offset
            else:
                current_offset = f.offset

            # Calculate field size
            if f.type_info.is_array:
                if isinstance(f.type_info.array_size, int):
                    current_offset += f.type_info.size * f.type_info.array_size
                # Dynamic arrays don't advance offset (must be last)
            elif f.type_info.is_repeated_struct:
                pass  # Repeated structs don't advance offset (must be last)
            else:
                current_offset += f.type_info.size

    def compute_size(self) -> Optional[int]:
        """Compute total payload size (None if variable/MTU-dependent)."""
        if self.mode in ("variable", "mtu_packed"):
            return None

        total = 0
        for f in self.fields:
            if f.type_info.is_array:
                if isinstance(f.type_info.array_size, int):
                    end = f.offset + f.type_info.size * f.type_info.array_size
                else:
                    return None  # Dynamic array
            elif f.type_info.is_repeated_struct:
                return None  # Repeated struct
            else:
                end = f.offset + f.type_info.size
            total = max(total, end)
        return total


@dataclass
class Characteristic:
    """Represents a GATT characteristic."""
    name: str
    uuid: str
    properties: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    description: str = ""
    payload: Optional[Payload] = None
    read_payload: Optional[Payload] = None
    write_payload: Optional[Payload] = None
    notify_payload: Optional[Payload] = None


@dataclass
class Service:
    """Represents a GATT service."""
    name: str
    uuid: str
    description: str = ""


@dataclass
class Schema:
    """Represents a complete GATT schema."""
    schema_version: str
    service: Service
    characteristics: List[Characteristic] = field(default_factory=list)
    schema_revision: Optional[int] = None  # Optional user-controlled revision number



# Valid keys at each schema level
_VALID_ROOT_KEYS = {"schema_version", "service", "characteristics", "schema_revision"}
_VALID_SERVICE_KEYS = {"name", "uuid", "description"}
_VALID_CHAR_KEYS = {"uuid", "properties", "permissions", "description",
                     "payload", "read_payload", "write_payload", "notify_payload"}
_VALID_FIELD_KEYS = {"type", "offset", "description", "unit", "values", "bits"}


def _parse_field(name: str, data: Any) -> Field:
    """Parse a field from YAML data.

    Handles both simple syntax (name: type) and expanded syntax (name: {type: ..., unit: ...}).
    Also handles repeated structs (name[]: {field1: type1, ...}).

    Args:
        name: Field name
        data: YAML data for the field
    """
    is_repeated = name.endswith("[]")
    field_name_clean = name[:-2] if is_repeated else name

    # Simple syntax: field_name: uint16
    if isinstance(data, str):
        type_info = parse_type(data)
        return Field(name=field_name_clean, type_info=type_info)

    # Repeated struct syntax: name[]: {field1: type1, ...}
    if is_repeated and isinstance(data, dict):
        nested_fields = []
        for nested_name, field_data in data.items():
            if not nested_name.startswith("_"):
                nested_fields.append(_parse_field(nested_name, field_data))

        type_info = TypeInfo(
            base="struct",
            size=0,  # Will be computed from nested fields
            endian="none",
            is_array=True,
            array_size=None,  # MTU-fill
            is_repeated_struct=True,
        )

        struct_size = 0
        current_offset = 0
        for f in nested_fields:
            if f.offset is None:
                f.offset = current_offset
            current_offset = f.offset + f.type_info.size
            struct_size = current_offset
        type_info.size = struct_size

        return Field(name=field_name_clean, type_info=type_info, fields=nested_fields)

    # Expanded syntax: field_name: {type: uint16, unit: celsius, ...}
    if isinstance(data, dict):
        _warn_unknown_keys(data, _VALID_FIELD_KEYS, f"field '{field_name_clean}'")
        type_str = data.get("type", "uint8")
        type_info = parse_type(type_str)

        # Parse values field (can be list, dict, or string)
        values = data.get("values")
        if values is not None:
            if isinstance(values, list):
                # Range: [min, max]
                pass
            elif isinstance(values, dict):
                # Named values: {0: "success", 1: "error", "0xff": "unknown"}
                # Order preserved from YAML (Python 3.7+ dicts maintain insertion order)
                named_values = []
                for k, v in values.items():
                    named_values.append({"value": str(k), "name": str(v)})
                values = named_values
            elif isinstance(values, str):
                # Free text description
                pass
            else:
                raise ValueError(f"Invalid values format for '{field_name_clean}': expected list, dict, or string")

        return Field(
            name=field_name_clean,
            type_info=type_info,
            offset=data.get("offset"),
            description=data.get("description", ""),
            unit=data.get("unit"),
            values=values,
            bits=data.get("bits"),
        )

    raise ValueError(f"Invalid field definition for '{field_name_clean}': {data}")


def _parse_payload(data: Optional[Dict[str, Any]]) -> Optional[Payload]:
    """Parse payload definition from YAML data."""
    if not data:
        return None

    fields = []
    mode = None
    min_size = None
    max_size = None

    for key, value in data.items():
        # Handle special keys (prefixed with _)
        if key == PAYLOAD_MODE_KEY:
            mode = value
        elif key == PAYLOAD_MIN_SIZE_KEY:
            min_size = value
        elif key == PAYLOAD_MAX_SIZE_KEY:
            max_size = value
        elif key.startswith("_"):
            # Skip other special keys for now
            continue
        else:
            fields.append(_parse_field(key, value))

    payload = Payload(
        fields=fields,
        mode=mode,
        min_size=min_size,
        max_size=max_size,
    )
    payload.compute_offsets()

    return payload


def _parse_characteristic(name: str, data: Dict[str, Any]) -> Characteristic:
    """Parse a characteristic from YAML data."""
    _warn_unknown_keys(data, _VALID_CHAR_KEYS, f"characteristic '{name}'")
    char = Characteristic(
        name=name,
        uuid=data["uuid"],
        properties=data.get("properties", []),
        permissions=data.get("permissions", []),
        description=data.get("description", ""),
    )

    if "payload" in data:
        char.payload = _parse_payload(data["payload"])
    if "read_payload" in data:
        char.read_payload = _parse_payload(data["read_payload"])
    if "write_payload" in data:
        char.write_payload = _parse_payload(data["write_payload"])
    if "notify_payload" in data:
        char.notify_payload = _parse_payload(data["notify_payload"])

    return char


def load_schema(path: Union[Path, str]) -> Schema:
    """Load a GATT schema from a YAML file.

    Args:
        path: Path to the YAML schema file.

    Returns:
        Parsed Schema object.

    Raises:
        FileNotFoundError: If the schema file doesn't exist.
        ValueError: If the schema is invalid.
    """
    path = Path(path)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    _warn_unknown_keys(data, _VALID_ROOT_KEYS, f"schema '{path.name}'")

    service_data = data["service"]
    _warn_unknown_keys(service_data, _VALID_SERVICE_KEYS, f"service in '{path.name}'")
    service = Service(
        name=service_data["name"],
        uuid=service_data["uuid"],
        description=service_data.get("description", ""),
    )

    characteristics = []
    for name, char_data in data.get("characteristics", {}).items():
        characteristics.append(_parse_characteristic(name, char_data))

    # Parse optional schema_revision
    schema_revision = data.get("schema_revision")
    if schema_revision is not None:
        schema_revision = int(schema_revision)

    return Schema(
        schema_version=data.get("schema_version", "1.0"),
        service=service,
        characteristics=characteristics,
        schema_revision=schema_revision,
    )


def _is_valid_uuid(uuid: str) -> bool:
    """Check if string is a valid 128-bit UUID format."""
    pattern = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    return bool(re.match(pattern, uuid))


def _validate_c_identifier(name: str) -> Optional[str]:
    """Check if a name is a valid C identifier.

    Returns None if valid, or a reason string if invalid.
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
        return "must start with a letter or underscore and contain only letters, digits, underscores"
    if name in C_KEYWORDS:
        return "is a C reserved keyword"
    return None


def validate_schema(schema: Schema) -> List[str]:
    """Validate a GATT schema.

    Args:
        schema: The schema to validate.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors = []

    # Validate names are valid C identifiers
    reason = _validate_c_identifier(schema.service.name)
    if reason:
        errors.append(f"Service name '{schema.service.name}' is not a valid C identifier: {reason}")

    if not schema.service.uuid:
        errors.append("Service UUID is required")
    elif not _is_valid_uuid(schema.service.uuid):
        errors.append(f"Invalid service UUID format: '{schema.service.uuid}' (expected xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)")

    char_names = [char.name for char in schema.characteristics]
    seen = set()
    for name in char_names:
        if name in seen:
            errors.append(f"Duplicate characteristic name: '{name}'")
        seen.add(name)

    seen_uuids = set()
    for char in schema.characteristics:
        if char.uuid in seen_uuids:
            errors.append(f"Duplicate characteristic UUID: '{char.uuid}' (in '{char.name}')")
        seen_uuids.add(char.uuid)

    for char in schema.characteristics:
        reason = _validate_c_identifier(char.name)
        if reason:
            errors.append(f"Characteristic name '{char.name}' is not a valid C identifier: {reason}")

        if not char.uuid:
            errors.append(f"Characteristic '{char.name}' missing UUID")
        elif not _is_valid_uuid(char.uuid):
            errors.append(f"Invalid UUID format for '{char.name}': '{char.uuid}'")

        # Check property/permission consistency
        read_perms = {"read", "read_encrypt", "read_authen"}
        write_perms = {"write", "write_encrypt", "write_authen"}
        has_read_perm = bool(read_perms & set(char.permissions))
        has_write_perm = bool(write_perms & set(char.permissions))

        if "read" in char.properties and not has_read_perm:
            errors.append(f"Characteristic '{char.name}' has 'read' property but no read permission")
        if "write" in char.properties and not has_write_perm:
            errors.append(f"Characteristic '{char.name}' has 'write' property but no write permission")
        if "write_without_response" in char.properties and not has_write_perm:
            errors.append(f"Characteristic '{char.name}' has 'write_without_response' property but no write permission")

        # Validate payload field names are unique and bitfields are in range
        for payload in [getattr(char, pt) for pt in PAYLOAD_TYPES]:
            if payload:
                field_names = [f.name for f in payload.fields]
                seen_fields = set()
                for fname in field_names:
                    if fname in seen_fields:
                        errors.append(f"Duplicate field name '{fname}' in '{char.name}'")
                    seen_fields.add(fname)
                    reason = _validate_c_identifier(fname)
                    if reason:
                        errors.append(f"Field name '{fname}' in '{char.name}' is not a valid C identifier: {reason}")

                for field in payload.fields:
                    if field.fields:
                        for nested in field.fields:
                            reason = _validate_c_identifier(nested.name)
                            if reason:
                                errors.append(f"Field name '{nested.name}' in '{char.name}.{field.name}' is not a valid C identifier: {reason}")
                    if field.bits:
                        max_bit = field.type_info.size * 8 - 1
                        for bit_spec, bit_name in field.bits.items():
                            reason = _validate_c_identifier(bit_name)
                            if reason:
                                errors.append(f"Bit name '{bit_name}' in '{char.name}.{field.name}' is not a valid C identifier: {reason}")
                            bit_spec_str = str(bit_spec)
                            if "-" in bit_spec_str:
                                # Range like "3-5"
                                start, end = map(int, bit_spec_str.split("-"))
                                if start > max_bit or end > max_bit:
                                    errors.append(
                                        f"Bitfield '{bit_spec}' in '{char.name}.{field.name}' "
                                        f"exceeds type size (max bit: {max_bit})"
                                    )
                                if start > end:
                                    errors.append(
                                        f"Bitfield '{bit_spec}' in '{char.name}.{field.name}' "
                                        f"has invalid range (start > end)"
                                    )
                            else:
                                # Single bit like "9"
                                bit = int(bit_spec_str)
                                if bit > max_bit:
                                    errors.append(
                                        f"Bit {bit} in '{char.name}.{field.name}' "
                                        f"exceeds type size (max bit: {max_bit})"
                                    )

    return errors


def load_and_validate_schema(schema_path: Path) -> Tuple[Optional[Schema], List[str]]:
    """Load and validate a schema file.

    Combines load_schema and validate_schema into a single operation.

    Args:
        schema_path: Path to the schema YAML file.

    Returns:
        Tuple of (schema, errors):
        - Load failure: (None, [error_message])
        - Validation failure: (schema, [validation_errors...])
        - Valid: (schema, [])
    """
    try:
        schema = load_schema(schema_path)
    except Exception as e:
        return None, [str(e)]

    errors = validate_schema(schema)
    return schema, errors

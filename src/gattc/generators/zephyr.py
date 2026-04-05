"""
Zephyr RTOS BT_GATT_SERVICE_DEFINE code generator.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple, Union

from jinja2 import Environment, PackageLoader

from ..schema import Characteristic, Field, Payload, Schema, TypeInfo


# Map schema properties to Zephyr BT_GATT_CHRC_* flags
PROPERTY_MAP = {
    "read": "BT_GATT_CHRC_READ",
    "write": "BT_GATT_CHRC_WRITE",
    "write_without_response": "BT_GATT_CHRC_WRITE_WITHOUT_RESP",
    "notify": "BT_GATT_CHRC_NOTIFY",
    "indicate": "BT_GATT_CHRC_INDICATE",
}

# Map schema permissions to Zephyr BT_GATT_PERM_* flags
PERMISSION_MAP = {
    "read": "BT_GATT_PERM_READ",
    "write": "BT_GATT_PERM_WRITE",
    "read_encrypt": "BT_GATT_PERM_READ_ENCRYPT",
    "write_encrypt": "BT_GATT_PERM_WRITE_ENCRYPT",
    "read_authen": "BT_GATT_PERM_READ_AUTHEN",
    "write_authen": "BT_GATT_PERM_WRITE_AUTHEN",
}

# Map type base to C type
C_TYPE_MAP = {
    "uint8": "uint8_t",
    "int8": "int8_t",
    "uint16": "uint16_t",
    "int16": "int16_t",
    "uint32": "uint32_t",
    "int32": "int32_t",
    "uint64": "uint64_t",
    "int64": "int64_t",
    "bool": "uint8_t",
    "bytes": "uint8_t",  # raw bytes, will be array
}

def _format_uuid_128(uuid: str) -> str:
    """Convert UUID string to Zephyr BT_UUID_128_ENCODE format."""
    parts = uuid.split("-")
    time_low = parts[0]
    time_mid = parts[1]
    time_hi = parts[2]
    clock_seq = parts[3]
    node = parts[4]

    cs_hi = clock_seq[0:2]
    cs_lo = clock_seq[2:4]
    node_bytes = [node[i:i+2] for i in range(0, 12, 2)]

    return (
        f"BT_UUID_128_ENCODE(0x{time_low}, 0x{time_mid}, 0x{time_hi}, "
        f"0x{cs_hi}, 0x{cs_lo}, "
        f"0x{node_bytes[0]}, 0x{node_bytes[1]}, 0x{node_bytes[2]}, "
        f"0x{node_bytes[3]}, 0x{node_bytes[4]}, 0x{node_bytes[5]})"
    )


def _format_properties(props: List[str]) -> str:
    """Convert property list to Zephyr flags."""
    flags = [PROPERTY_MAP[p] for p in props if p in PROPERTY_MAP]
    return " | ".join(flags) if flags else "0"


def _format_permissions(perms: List[str]) -> str:
    """Convert permission list to Zephyr flags."""
    flags = [PERMISSION_MAP[p] for p in perms if p in PERMISSION_MAP]
    return " | ".join(flags) if flags else "0"


def _needs_read_cb(char: Characteristic) -> bool:
    """Check if characteristic needs a read callback."""
    return "read" in char.properties


def _needs_write_cb(char: Characteristic) -> bool:
    """Check if characteristic needs a write callback."""
    return "write" in char.properties or "write_without_response" in char.properties


def _needs_ccc(char: Characteristic) -> bool:
    """Check if characteristic needs a CCC descriptor (for notify/indicate)."""
    return "notify" in char.properties or "indicate" in char.properties


def _read_cb_name(service_name: str, char: Characteristic) -> str:
    """Generate read callback name from service and characteristic name."""
    return f"{service_name}_{char.name}_read_cb"


def _write_cb_name(service_name: str, char: Characteristic) -> str:
    """Generate write callback name from service and characteristic name."""
    return f"{service_name}_{char.name}_write_cb"


def _ccc_cb_name(service_name: str, char: Characteristic) -> str:
    """Generate CCC changed callback name."""
    return f"{service_name}_{char.name}_ccc_changed"


def _get_c_type(type_info: TypeInfo) -> str:
    """Get C type string for a TypeInfo."""
    return C_TYPE_MAP.get(type_info.base, "uint8_t")


def _get_endian_pack_func(type_info: TypeInfo) -> Optional[str]:
    """Get Zephyr endianness conversion function for packing (CPU to wire)."""
    if type_info.endian == "none" or type_info.size == 1:
        return None

    if type_info.endian == "little":
        return f"sys_cpu_to_le{type_info.size * 8}"
    else:
        return f"sys_cpu_to_be{type_info.size * 8}"


def _get_endian_unpack_func(type_info: TypeInfo) -> Optional[str]:
    """Get Zephyr endianness conversion function for unpacking (wire to CPU)."""
    if type_info.endian == "none" or type_info.size == 1:
        return None

    if type_info.endian == "little":
        return f"sys_le{type_info.size * 8}_to_cpu"
    else:
        return f"sys_be{type_info.size * 8}_to_cpu"


def _is_fixed_array(field: Field) -> bool:
    """Check if field is a fixed-size array (not dynamic/MTU-fill)."""
    return (field.type_info.is_array and
            isinstance(field.type_info.array_size, int) and
            not field.type_info.is_repeated_struct)


def _generate_struct(name: str, fields: List[Field], indent: str = "") -> str:
    """Generate a packed struct definition."""
    lines = []
    lines.append(f"{indent}typedef struct __attribute__((packed)) {{")

    for field in fields:
        c_type = _get_c_type(field.type_info)

        if field.type_info.is_repeated_struct:
            lines.append(f"{indent}    {name}_{field.name}_t {field.name}[];")
        elif field.type_info.is_array:
            if field.type_info.array_size is None:
                lines.append(f"{indent}    {c_type} {field.name}[];")
            elif isinstance(field.type_info.array_size, int):
                lines.append(f"{indent}    {c_type} {field.name}[{field.type_info.array_size}];")
            else:
                lines.append(f"{indent}    {c_type} {field.name}[];")
        elif field.type_info.base == "bytes":
            lines.append(f"{indent}    {c_type} {field.name}[{field.type_info.size}];")
        else:
            comment = ""
            if field.unit:
                comment = f"  /* unit: {field.unit} */"
            lines.append(f"{indent}    {c_type} {field.name};{comment}")

    lines.append(f"{indent}}} {name}_t;")
    return "\n".join(lines)


def _generate_nested_struct(parent_name: str, field: Field) -> str:
    """Generate a nested struct for repeated elements with pack/unpack item functions."""
    if not field.fields:
        return ""

    lines = []
    struct_name = f"{parent_name}_{field.name}"
    lines.append(_generate_struct(struct_name, field.fields))
    lines.append("")

    params = []
    for nested in field.fields:
        c_type = _get_c_type(nested.type_info)
        params.append(f"{c_type} {nested.name}")

    param_str = ", ".join(params)
    lines.append(f"static inline void {parent_name}_pack_item({struct_name}_t *item, {param_str})")
    lines.append("{")
    for nested in field.fields:
        endian_func = _get_endian_pack_func(nested.type_info)
        if endian_func:
            lines.append(f"    item->{nested.name} = {endian_func}({nested.name});")
        else:
            lines.append(f"    item->{nested.name} = {nested.name};")
    lines.append("}")
    lines.append("")

    params = []
    for nested in field.fields:
        c_type = _get_c_type(nested.type_info)
        params.append(f"{c_type} *{nested.name}")

    param_str = ", ".join(params)
    lines.append(f"static inline void {parent_name}_unpack_item(const {struct_name}_t *item, {param_str})")
    lines.append("{")
    for nested in field.fields:
        endian_func = _get_endian_unpack_func(nested.type_info)
        if endian_func:
            lines.append(f"    *{nested.name} = {endian_func}(item->{nested.name});")
        else:
            lines.append(f"    *{nested.name} = item->{nested.name};")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def _generate_pack_function(name: str, fields: List[Field]) -> str:
    """Generate a pack function for a payload."""
    params = []
    for field in fields:
        # Skip dynamic arrays and repeated structs (variable size)
        if field.type_info.is_repeated_struct:
            continue
        if field.type_info.is_array and not isinstance(field.type_info.array_size, int):
            continue

        c_type = _get_c_type(field.type_info)

        if _is_fixed_array(field):
            # Fixed array: const type name[SIZE] - size in signature for safety
            params.append(f"const {c_type} {field.name}[{field.type_info.array_size}]")
        elif field.type_info.base == "bytes":
            # Custom-sized type (bytes[N], uint[N])
            params.append(f"const uint8_t {field.name}[{field.type_info.size}]")
        else:
            # Scalar
            params.append(f"{c_type} {field.name}")

    if not params:
        return ""  # No packable fields

    lines = []
    param_str = ", ".join(params)
    lines.append(f"static inline void {name}_pack({name}_t *buf, {param_str})")
    lines.append("{")

    for field in fields:
        if field.type_info.is_repeated_struct:
            continue
        if field.type_info.is_array and not isinstance(field.type_info.array_size, int):
            continue

        if _is_fixed_array(field):
            array_size = field.type_info.array_size
            if field.type_info.size == 1:
                total_bytes = array_size * field.type_info.size
                lines.append(f"    memcpy(buf->{field.name}, {field.name}, {total_bytes});")
            else:
                endian_func = _get_endian_pack_func(field.type_info)
                lines.append(f"    for (size_t i = 0; i < {array_size}; i++) {{")
                if endian_func:
                    lines.append(f"        buf->{field.name}[i] = {endian_func}({field.name}[i]);")
                else:
                    lines.append(f"        buf->{field.name}[i] = {field.name}[i];")
                lines.append(f"    }}")
        elif field.type_info.base == "bytes":
            lines.append(f"    memcpy(buf->{field.name}, {field.name}, {field.type_info.size});")
        else:
            endian_func = _get_endian_pack_func(field.type_info)
            if endian_func:
                lines.append(f"    buf->{field.name} = {endian_func}({field.name});")
            else:
                lines.append(f"    buf->{field.name} = {field.name};")

    lines.append("}")
    return "\n".join(lines)


def _generate_unpack_function(name: str, fields: List[Field]) -> str:
    """Generate an unpack function for a payload."""
    params = []
    for field in fields:
        # Skip dynamic arrays and repeated structs (variable size)
        if field.type_info.is_repeated_struct:
            continue
        if field.type_info.is_array and not isinstance(field.type_info.array_size, int):
            continue

        c_type = _get_c_type(field.type_info)

        if _is_fixed_array(field):
            # Fixed array: type name[SIZE] - size in signature for safety
            params.append(f"{c_type} {field.name}[{field.type_info.array_size}]")
        elif field.type_info.base == "bytes":
            # Custom-sized type
            params.append(f"uint8_t {field.name}[{field.type_info.size}]")
        else:
            # Scalar (output pointer)
            params.append(f"{c_type} *{field.name}")

    if not params:
        return ""  # No unpackable fields

    lines = []
    param_str = ", ".join(params)
    lines.append(f"static inline void {name}_unpack(const {name}_t *buf, {param_str})")
    lines.append("{")

    for field in fields:
        if field.type_info.is_repeated_struct:
            continue
        if field.type_info.is_array and not isinstance(field.type_info.array_size, int):
            continue

        if _is_fixed_array(field):
            array_size = field.type_info.array_size
            if field.type_info.size == 1:
                total_bytes = array_size * field.type_info.size
                lines.append(f"    memcpy({field.name}, buf->{field.name}, {total_bytes});")
            else:
                endian_func = _get_endian_unpack_func(field.type_info)
                lines.append(f"    for (size_t i = 0; i < {array_size}; i++) {{")
                if endian_func:
                    lines.append(f"        {field.name}[i] = {endian_func}(buf->{field.name}[i]);")
                else:
                    lines.append(f"        {field.name}[i] = buf->{field.name}[i];")
                lines.append(f"    }}")
        elif field.type_info.base == "bytes":
            lines.append(f"    memcpy({field.name}, buf->{field.name}, {field.type_info.size});")
        else:
            endian_func = _get_endian_unpack_func(field.type_info)
            if endian_func:
                lines.append(f"    *{field.name} = {endian_func}(buf->{field.name});")
            else:
                lines.append(f"    *{field.name} = buf->{field.name};")

    lines.append("}")
    return "\n".join(lines)


def _generate_size_helpers(name: str, payload: Payload) -> str:
    """Generate size constants and helper functions."""
    lines = []
    fixed_size = 0
    has_flexible = False
    flexible_field = None

    for field in payload.fields:
        if field.type_info.is_array and not isinstance(field.type_info.array_size, int):
            has_flexible = True
            flexible_field = field
        elif field.type_info.is_repeated_struct:
            has_flexible = True
            flexible_field = field
        elif field.type_info.is_array and isinstance(field.type_info.array_size, int):
            fixed_size = field.offset + field.type_info.size * field.type_info.array_size
        else:
            fixed_size = field.offset + field.type_info.size

    lines.append(f"#define {name.upper()}_HEADER_SIZE {fixed_size}")

    if has_flexible and flexible_field:
        item_size = flexible_field.type_info.size
        lines.append(f"#define {name.upper()}_ITEM_SIZE {item_size}")
        lines.append("")
        lines.append(f"static inline size_t {name}_items_per_mtu(uint16_t mtu)")
        lines.append("{")
        lines.append(f"    return (mtu - GATTC_ATT_HEADER_SIZE - {name.upper()}_HEADER_SIZE) / {name.upper()}_ITEM_SIZE;")
        lines.append("}")
    else:
        lines.append(f"#define {name.upper()}_SIZE {fixed_size}")
        lines.append("")
        lines.append(f"_Static_assert(sizeof({name}_t) == {name.upper()}_SIZE, \"{name} size mismatch\");")

    return "\n".join(lines)


def _generate_bitfield_macros(name: str, field: Field) -> str:
    """Generate bitfield macros for a field with bits defined."""
    if not field.bits:
        return ""

    lines = []
    lines.append(f"/* {name}_{field.name} bit definitions */")
    for bit_spec, bit_name in field.bits.items():
        bit_spec_str = str(bit_spec)
        if "-" in bit_spec_str:
            # Multi-bit field: "3-5" -> bits 3,4,5
            start, end = map(int, bit_spec_str.split("-"))
            width = end - start + 1
            mask = ((1 << width) - 1) << start
            lines.append(f"#define {name.upper()}_{field.name.upper()}_{bit_name.upper()}_MASK 0x{mask:02X}")
            lines.append(f"#define {name.upper()}_{field.name.upper()}_{bit_name.upper()}_SHIFT {start}")
        else:
            bit = int(bit_spec_str)
            lines.append(f"#define {name.upper()}_{field.name.upper()}_{bit_name.upper()} (1 << {bit})")

    return "\n".join(lines)


def _generate_payload_types(service_name: str, char_name: str, payload: Payload, suffix: str = "") -> str:
    """Generate struct, pack/unpack functions for a payload."""
    parts = []
    name = f"{service_name}_{char_name}{suffix}"

    for field in payload.fields:
        if field.type_info.is_repeated_struct and field.fields:
            parts.append(_generate_nested_struct(name, field))

    parts.append(_generate_struct(name, payload.fields))
    parts.append("")

    for field in payload.fields:
        if field.bits:
            parts.append(_generate_bitfield_macros(name, field))
            parts.append("")

    parts.append(_generate_size_helpers(name, payload))
    parts.append("")

    pack_func = _generate_pack_function(name, payload.fields)
    if pack_func:
        parts.append(pack_func)
        parts.append("")
    unpack_func = _generate_unpack_function(name, payload.fields)
    if unpack_func:
        parts.append(unpack_func)
        parts.append("")

    return "\n".join(parts)


def _build_header_context(schema: Schema) -> dict:
    """Build context dictionary for header template."""
    service_name = schema.service.name
    service_upper = service_name.upper()

    characteristics = []
    for char in schema.characteristics:
        characteristics.append({
            "name": char.name,
            "name_upper": char.name.upper(),
            "uuid_encoded": _format_uuid_128(char.uuid),
        })

    payloads = []
    for char in schema.characteristics:
        if char.payload:
            payloads.append({
                "content": _generate_payload_types(service_name, char.name, char.payload)
            })
        if char.read_payload:
            payloads.append({
                "content": _generate_payload_types(service_name, char.name, char.read_payload, "_read")
            })
        if char.write_payload:
            payloads.append({
                "content": _generate_payload_types(service_name, char.name, char.write_payload, "_write")
            })
        if char.notify_payload:
            payloads.append({
                "content": _generate_payload_types(service_name, char.name, char.notify_payload, "_notify")
            })

    callbacks = []
    has_callbacks = any(
        _needs_read_cb(c) or _needs_write_cb(c) or _needs_ccc(c)
        for c in schema.characteristics
    )

    if has_callbacks:
        for char in schema.characteristics:
            if _needs_read_cb(char):
                cb = _read_cb_name(service_name, char)
                callbacks.append(
                    f"ssize_t {cb}(struct bt_conn *conn,\n"
                    f"    const struct bt_gatt_attr *attr, void *buf,\n"
                    f"    uint16_t len, uint16_t offset);\n"
                )
            if _needs_write_cb(char):
                cb = _write_cb_name(service_name, char)
                callbacks.append(
                    f"ssize_t {cb}(struct bt_conn *conn,\n"
                    f"    const struct bt_gatt_attr *attr, const void *buf,\n"
                    f"    uint16_t len, uint16_t offset, uint8_t flags);\n"
                )
            if _needs_ccc(char):
                cb = _ccc_cb_name(service_name, char)
                callbacks.append(f"void {cb}(const struct bt_gatt_attr *attr, uint16_t value);\n")

    return {
        "service_name": service_name,
        "service_upper": service_upper,
        "service_uuid_encoded": _format_uuid_128(schema.service.uuid),
        "characteristics": characteristics,
        "payloads": payloads,
        "has_callbacks": has_callbacks,
        "callbacks": callbacks,
    }


def _build_source_context(schema: Schema, header_name: str) -> dict:
    """Build context dictionary for source template."""
    service_name = schema.service.name
    service_upper = service_name.upper()

    characteristics = []
    for char in schema.characteristics:
        char_upper = char.name.upper()
        props = _format_properties(char.properties)
        perms = _format_permissions(char.permissions)

        read_cb = _read_cb_name(service_name, char) if _needs_read_cb(char) else "NULL"
        write_cb = _write_cb_name(service_name, char) if _needs_write_cb(char) else "NULL"
        ccc_cb = _ccc_cb_name(service_name, char) if _needs_ccc(char) else None

        characteristics.append({
            "name": char.name,
            "name_upper": char_upper,
            "props": props,
            "perms": perms,
            "read_cb": read_cb,
            "write_cb": write_cb,
            "needs_ccc": _needs_ccc(char),
            "ccc_cb": ccc_cb,
        })

    return {
        "header_name": header_name,
        "service_name": service_name,
        "service_upper": service_upper,
        "characteristics": characteristics,
    }


@lru_cache(maxsize=1)
def _get_jinja_env() -> Environment:
    """Get or create the Jinja2 environment (cached)."""
    return Environment(
        loader=PackageLoader("gattc", "templates/zephyr"),
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _resolve_output_path(
    path: Optional[Union[Path, str]],
    schema_name: str,
    extension: str,
    fallback_path: Optional[Union[Path, str]] = None,
) -> Path:
    """Resolve an output path for header or source file.

    Args:
        path: Explicit path (file or directory), or None.
        schema_name: Service name used to derive filename if path is a directory.
        extension: File extension including dot (e.g., ".h", ".c").
        fallback_path: Base path to use if path is None.

    Returns:
        Resolved Path object.

    Raises:
        ValueError: If neither path nor fallback_path is provided.
    """
    if path:
        resolved = Path(path)
        if resolved.suffix != extension:
            # It's a directory, add filename
            resolved = resolved / f"{schema_name}{extension}"
        return resolved

    if fallback_path:
        resolved = Path(fallback_path)
        if resolved.suffix in (".h", ".c"):
            resolved = resolved.with_suffix("")
        return resolved.with_suffix(extension)

    raise ValueError(f"Either path or fallback_path must be provided for {extension} file")


def generate(
    schema: Schema,
    output_path: Optional[Union[Path, str]] = None,
    header_path: Optional[Union[Path, str]] = None,
    source_path: Optional[Union[Path, str]] = None,
) -> Tuple[Path, Path]:
    """Generate Zephyr GATT service header and source files.

    Args:
        schema: The GATT schema to generate code from.
        output_path: Base path for output (without extension).
                     Will generate .h and .c files in the same directory.
                     Used when header_path and source_path are not specified.
        header_path: Explicit path for header file. Can be a directory
                     (filename derived from schema) or full file path.
        source_path: Explicit path for source file. Can be a directory
                     (filename derived from schema) or full file path.

    Returns:
        Tuple of (header_path, source_path).

    Note:
        If header_path or source_path is provided, it takes precedence
        over output_path for that file type.
    """
    schema_name = schema.service.name

    # Resolve paths
    resolved_header = _resolve_output_path(header_path, schema_name, ".h", output_path)
    resolved_source = _resolve_output_path(source_path, schema_name, ".c", output_path)

    # Create output directories
    resolved_header.parent.mkdir(parents=True, exist_ok=True)
    resolved_source.parent.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()

    # Generate header
    header_template = env.get_template("header.h.j2")
    header_context = _build_header_context(schema)
    header_content = header_template.render(**header_context)

    with open(resolved_header, "w", encoding="utf-8") as f:
        f.write(header_content)

    # Generate source (include path relative or just filename)
    source_template = env.get_template("source.c.j2")
    source_context = _build_source_context(schema, resolved_header.name)
    source_content = source_template.render(**source_context)

    with open(resolved_source, "w", encoding="utf-8") as f:
        f.write(source_content)

    return resolved_header, resolved_source


def generate_combined(
    schemas: List[Schema],
    output_path: Optional[Union[Path, str]] = None,
    header_path: Optional[Union[Path, str]] = None,
    source_path: Optional[Union[Path, str]] = None,
    output_name: str = "gatt_services",
) -> Tuple[Path, Path]:
    """Generate combined Zephyr GATT service header and source files for multiple services.

    Args:
        schemas: List of GATT schemas to generate code from.
        output_path: Base path for output (without extension).
        header_path: Explicit path for header file (directory or full path).
        source_path: Explicit path for source file (directory or full path).
        output_name: Base name for output files (default: "gatt_services").

    Returns:
        Tuple of (header_path, source_path).
    """
    # Resolve paths (use output_name as schema_name, with fallback to default path)
    if header_path or output_path:
        resolved_header = _resolve_output_path(header_path, output_name, ".h", output_path)
    else:
        resolved_header = Path(f"{output_name}.h")

    if source_path or output_path:
        resolved_source = _resolve_output_path(source_path, output_name, ".c", output_path)
    else:
        resolved_source = Path(f"{output_name}.c")

    # Create output directories
    resolved_header.parent.mkdir(parents=True, exist_ok=True)
    resolved_source.parent.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()

    # Build context for all services
    services_context = []
    for schema in schemas:
        svc_context = _build_header_context(schema)
        # Add source context data
        source_ctx = _build_source_context(schema, resolved_header.name)
        svc_context["characteristics"] = source_ctx["characteristics"]
        services_context.append(svc_context)

    header_guard = output_name.upper().replace("-", "_") + "_H"

    # Generate combined header
    header_template = env.get_template("combined_header.h.j2")
    header_content = header_template.render(
        services=services_context,
        header_guard=header_guard,
    )

    with open(resolved_header, "w", encoding="utf-8") as f:
        f.write(header_content)

    # Generate combined source
    source_template = env.get_template("combined_source.c.j2")
    source_content = source_template.render(
        services=services_context,
        header_name=resolved_header.name,
    )

    with open(resolved_source, "w", encoding="utf-8") as f:
        f.write(source_content)

    return resolved_header, resolved_source

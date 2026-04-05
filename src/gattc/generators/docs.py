"""
HTML documentation generator for GATT schemas.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, PackageLoader

from ..schema import Field, Payload, Schema


def _format_type(field: Field) -> str:
    """Format field type for display."""
    type_info = field.type_info

    if type_info.is_repeated_struct:
        return "struct[]"

    base = type_info.base

    if type_info.size > 1 and type_info.endian == "big":
        base += "_be"

    if type_info.is_array:
        if type_info.array_size is None:
            base += "[]"
        else:
            base += f"[{type_info.array_size}]"
    elif type_info.base == "bytes" and type_info.size > 1:
        base = f"bytes[{type_info.size}]"

    return base


def _format_bits(bits: Dict[str, str]) -> List[Dict[str, str]]:
    """Format bitfield definitions for display."""
    result = []
    for bit_spec, bit_name in bits.items():
        bit_spec_str = str(bit_spec)
        if "-" in bit_spec_str:
            start, end = bit_spec_str.split("-")
            range_str = f"[{start}:{end}]"
        else:
            range_str = f"[{bit_spec_str}]"
        result.append({"range": range_str, "name": bit_name})
    return result


def _compute_field_length(field: Field) -> str:
    """Compute the total length of a field in bytes."""
    type_info = field.type_info

    if type_info.is_repeated_struct:
        return f"{type_info.size}*N"

    if type_info.is_array:
        if type_info.array_size is None:
            return f"{type_info.size}*N"
        else:
            return str(type_info.size * type_info.array_size)

    return str(type_info.size)


def _format_values(values) -> Dict[str, Any]:
    """Format values field for display.

    Returns dict with:
        - type: "range", "named", or "text"
        - display: string for inline display in Value column
        - items: list of {value, name} for named values (None otherwise)
    """
    if values is None:
        return {"type": None, "display": "", "items": None}

    if isinstance(values, list) and len(values) >= 1 and isinstance(values[0], dict):
        # Named values as list of dicts [{value: "0", name: "success"}, ...]
        return {
            "type": "named",
            "display": "",  # Will be rendered as separate rows
            "items": values,
        }
    elif isinstance(values, list) and len(values) == 2:
        # Range: [min, max]
        min_val, max_val = values[0], values[1]
        display = f"{min_val}..{max_val}"
        return {
            "type": "range",
            "display": display,
            "items": None,
        }
    elif isinstance(values, str):
        # Free text
        return {
            "type": "text",
            "display": values,
            "items": None,
        }

    return {"type": None, "display": "", "items": None}


def _build_field_data(field: Field) -> Dict[str, Any]:
    """Build display data for a single field."""
    values_data = _format_values(field.values)

    data = {
        "name": field.name,
        "type": _format_type(field),
        "size": field.type_info.size,
        "length": _compute_field_length(field),
        "offset": field.offset,
        "description": field.description or "",
        "unit": field.unit or "",
        "values": values_data,
        "bits": _format_bits(field.bits) if field.bits else None,
        "nested_fields": None,
    }

    # Handle repeated struct with nested fields
    if field.fields:
        data["nested_fields"] = [_build_field_data(f) for f in field.fields]

    return data


def _build_payload_data(payload: Payload) -> Dict[str, Any]:
    """Build display data for a payload."""
    fields = [_build_field_data(f) for f in payload.fields]
    size = payload.compute_size()

    return {
        "fields": fields,
        "size": size,
        "is_variable": size is None,
    }


def _build_docs_context(schema: Schema) -> Dict[str, Any]:
    """Build context dictionary for documentation template."""
    characteristics = []

    for char in schema.characteristics:
        char_data = {
            "name": char.name,
            "uuid": char.uuid,
            "description": char.description,
            "properties": char.properties,
            "permissions": char.permissions,
            "payload": _build_payload_data(char.payload) if char.payload else None,
            "read_payload": _build_payload_data(char.read_payload) if char.read_payload else None,
            "write_payload": _build_payload_data(char.write_payload) if char.write_payload else None,
            "notify_payload": _build_payload_data(char.notify_payload) if char.notify_payload else None,
        }
        characteristics.append(char_data)

    return {
        "service": {
            "name": schema.service.name,
            "uuid": schema.service.uuid,
            "description": schema.service.description,
        },
        "characteristics": characteristics,
    }


@lru_cache(maxsize=1)
def _get_jinja_env() -> Environment:
    """Get or create the Jinja2 environment (cached)."""
    return Environment(
        loader=PackageLoader("gattc", "templates/docs"),
        keep_trailing_newline=True,
        autoescape=True,
    )


def generate(schema: Schema, output_path: Path) -> Path:
    """Generate HTML documentation for a GATT service.

    Args:
        schema: The GATT schema to generate documentation from.
        output_path: Path for output HTML file.

    Returns:
        Path to the generated HTML file.
    """
    output_path = Path(output_path)

    # Ensure .html extension
    if output_path.suffix != ".html":
        output_path = output_path.with_suffix(".html")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("service.html.j2")

    context = {
        "services": [_build_docs_context(schema)],
        "title": f"{schema.service.name} - GATT Service Documentation",
        "is_combined": False,
    }

    content = template.render(**context)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path


def generate_combined(schemas: List[Schema], output_path: Path) -> Path:
    """Generate combined HTML documentation for multiple GATT services.

    Args:
        schemas: List of GATT schemas to include in documentation.
        output_path: Path for output HTML file.

    Returns:
        Path to the generated HTML file.
    """
    output_path = Path(output_path)

    # Ensure .html extension
    if output_path.suffix != ".html":
        output_path = output_path.with_suffix(".html")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("service.html.j2")

    context = {
        "services": [_build_docs_context(schema) for schema in schemas],
        "title": "GATT Services Documentation",
        "is_combined": True,
    }

    content = template.render(**context)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path

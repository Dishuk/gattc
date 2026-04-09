"""
HTML documentation generator for GATT schemas.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, PackageLoader

from ..schema import Field, PAYLOAD_TYPES, Payload, Schema
from ..diff import SchemaDiff


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


def _build_docs_context(
    schema: Schema,
    diff: Optional[SchemaDiff] = None,
    changelog: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Build context dictionary for documentation template.

    Args:
        schema: The schema to build context for.
        diff: Optional diff object for change highlighting.
        changelog: Optional list of changelog history entries.
    """
    characteristics = []

    for char in schema.characteristics:
        # Get change status for this characteristic
        char_status = diff.get_characteristic_status(char.name) if diff else None

        # Build payload data with field change status
        def build_payload_with_diff(payload, payload_type: str):
            if not payload:
                return None
            data = _build_payload_data(payload)
            # Add field status from diff
            if diff and char_status == 'modified':
                for field_data in data['fields']:
                    field_status = diff.get_field_status(char.name, field_data['name'])
                    field_data['change_status'] = field_status
            return data

        char_data = {
            "name": char.name,
            "uuid": char.uuid,
            "description": char.description,
            "properties": char.properties,
            "permissions": char.permissions,
            **{pt: build_payload_with_diff(getattr(char, pt), pt) for pt in PAYLOAD_TYPES},
            "change_status": char_status,
        }
        characteristics.append(char_data)

    return {
        "service": {
            "name": schema.service.name,
            "uuid": schema.service.uuid,
            "description": schema.service.description,
            "schema_version": schema.schema_version,
            "schema_revision": schema.schema_revision,
        },
        "characteristics": characteristics,
        "has_changes": diff.has_changes if diff else False,
        "changelog": changelog or [],
    }


@lru_cache(maxsize=1)
def _get_jinja_env() -> Environment:
    """Get or create the Jinja2 environment (cached)."""
    return Environment(
        loader=PackageLoader("gattc", "templates/docs"),
        keep_trailing_newline=True,
        autoescape=True,
    )


def _render_to_file(output_path: Path, context: Dict[str, Any]) -> Path:
    """Render the service template to an HTML file."""
    output_path = Path(output_path)

    if output_path.suffix != ".html":
        output_path = output_path.with_suffix(".html")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("service.html.j2")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template.render(**context))

    return output_path


def generate(
    schema: Schema,
    output_path: Path,
    diff: Optional[SchemaDiff] = None,
    changelog: Optional[List[Dict[str, Any]]] = None,
    unreleased: bool = False,
) -> Path:
    """Generate HTML documentation for a GATT service."""
    return _render_to_file(output_path, {
        "services": [_build_docs_context(schema, diff, changelog)],
        "title": f"{schema.service.name} - GATT Service Documentation",
        "is_combined": False,
        "unreleased": unreleased,
    })


def generate_combined(
    schemas: List[Schema],
    output_path: Path,
    diffs: Optional[Dict[str, SchemaDiff]] = None,
    changelogs: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    unreleased: bool = False,
) -> Path:
    """Generate combined HTML documentation for multiple GATT services."""
    services = []
    for schema in schemas:
        diff = diffs.get(schema.service.name) if diffs else None
        changelog = changelogs.get(schema.service.name) if changelogs else None
        services.append(_build_docs_context(schema, diff, changelog))

    return _render_to_file(output_path, {
        "services": services,
        "title": "GATT Services Documentation",
        "is_combined": True,
        "unreleased": unreleased,
    })

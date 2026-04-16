"""Tests for the Markdown/HTML documentation generator."""

import pytest
from pathlib import Path

from gattc.schema import (
    Field, TypeInfo, Payload, Characteristic, Service, Schema, load_schema,
)
from gattc.diff import SchemaDiff, CharacteristicChange, FieldChange
from gattc.generators import docs
from gattc.generators.docs import (
    _format_type,
    _format_bits,
    _compute_field_length,
    _format_values,
    _build_field_data,
    _build_payload_data,
    _build_docs_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_field(name="value", base="uint16", size=2, endian="little",
                is_array=False, array_size=None, is_repeated_struct=False,
                offset=0, description="", unit=None, values=None, bits=None,
                fields=None):
    """Convenience builder for Field objects."""
    ti = TypeInfo(base=base, size=size, endian=endian, is_array=is_array,
                  array_size=array_size, is_repeated_struct=is_repeated_struct)
    return Field(name=name, type_info=ti, offset=offset,
                 description=description, unit=unit, values=values,
                 bits=bits, fields=fields)


def _make_schema(name="test_service", uuid="12345678-1234-1234-1234-123456789abc",
                 characteristics=None):
    """Convenience builder for Schema objects."""
    service = Service(name=name, uuid=uuid)
    return Schema(
        schema_version="1.0",
        service=service,
        characteristics=characteristics or [],
        schema_revision=1,
    )


def _simple_schema_yaml(service_name="test_service",
                        service_uuid="12345678-1234-1234-1234-123456789abc"):
    """Return minimal YAML schema string."""
    return f"""
schema_version: "1.0"

service:
  name: {service_name}
  uuid: "{service_uuid}"

characteristics:
  temperature:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, notify]
    permissions: [read]
    description: "Temperature reading"
    payload:
      value:
        type: int16
        unit: celsius_x100
        description: "Temperature value"
"""


# ---------------------------------------------------------------------------
# Unit tests: _format_type
# ---------------------------------------------------------------------------

class TestFormatType:
    def test_basic_type(self):
        f = _make_field(base="uint16", size=2)
        assert _format_type(f) == "uint16"

    def test_big_endian(self):
        f = _make_field(base="uint16", size=2, endian="big")
        assert _format_type(f) == "uint16_be"

    def test_single_byte_no_endian_suffix(self):
        f = _make_field(base="uint8", size=1, endian="none")
        assert _format_type(f) == "uint8"

    def test_fixed_array(self):
        f = _make_field(base="uint16", size=2, is_array=True, array_size=10)
        assert _format_type(f) == "uint16[10]"

    def test_dynamic_array(self):
        f = _make_field(base="uint16", size=2, is_array=True, array_size=None)
        assert _format_type(f) == "uint16[]"

    def test_bytes_multi(self):
        f = _make_field(base="bytes", size=6, is_array=False)
        assert _format_type(f) == "bytes[6]"

    def test_bytes_single(self):
        f = _make_field(base="bytes", size=1, is_array=False)
        assert _format_type(f) == "bytes"

    def test_repeated_struct(self):
        f = _make_field(base="struct", size=6, is_repeated_struct=True, is_array=True)
        assert _format_type(f) == "struct[]"


# ---------------------------------------------------------------------------
# Unit tests: _format_bits
# ---------------------------------------------------------------------------

class TestFormatBits:
    def test_single_bits(self):
        result = _format_bits({"0": "enabled", "1": "error"})
        assert result == [
            {"range": "[0]", "name": "enabled"},
            {"range": "[1]", "name": "error"},
        ]

    def test_range_bits(self):
        result = _format_bits({"2-4": "mode"})
        assert result == [{"range": "[2:4]", "name": "mode"}]

    def test_mixed(self):
        result = _format_bits({"0": "flag", "1-3": "level"})
        assert len(result) == 2
        assert result[0]["range"] == "[0]"
        assert result[1]["range"] == "[1:3]"


# ---------------------------------------------------------------------------
# Unit tests: _compute_field_length
# ---------------------------------------------------------------------------

class TestComputeFieldLength:
    def test_fixed_scalar(self):
        f = _make_field(size=4)
        assert _compute_field_length(f) == "4"

    def test_fixed_array(self):
        f = _make_field(size=2, is_array=True, array_size=10)
        assert _compute_field_length(f) == "20"

    def test_dynamic_array(self):
        f = _make_field(size=2, is_array=True, array_size=None)
        assert _compute_field_length(f) == "2*N"

    def test_repeated_struct(self):
        f = _make_field(size=6, is_repeated_struct=True)
        assert _compute_field_length(f) == "6*N"


# ---------------------------------------------------------------------------
# Unit tests: _format_values
# ---------------------------------------------------------------------------

class TestFormatValues:
    def test_none(self):
        result = _format_values(None)
        assert result["type"] is None
        assert result["display"] == ""
        assert result["items"] is None

    def test_range(self):
        result = _format_values([0, 100])
        assert result["type"] == "range"
        assert result["display"] == "0..100"

    def test_named_values(self):
        named = [{"value": "0", "name": "off"}, {"value": "1", "name": "on"}]
        result = _format_values(named)
        assert result["type"] == "named"
        assert result["items"] == named

    def test_text(self):
        result = _format_values("Free-form UTF-8")
        assert result["type"] == "text"
        assert result["display"] == "Free-form UTF-8"

    def test_unknown_returns_none_type(self):
        result = _format_values(42)
        assert result["type"] is None


# ---------------------------------------------------------------------------
# Unit tests: _build_field_data / _build_payload_data
# ---------------------------------------------------------------------------

class TestBuildFieldData:
    def test_basic(self):
        f = _make_field(name="temp", base="int16", size=2, offset=0,
                        description="Temperature", unit="C")
        data = _build_field_data(f)
        assert data["name"] == "temp"
        assert data["type"] == "int16"
        assert data["size"] == 2
        assert data["length"] == "2"
        assert data["offset"] == 0
        assert data["description"] == "Temperature"
        assert data["unit"] == "C"
        assert data["bits"] is None
        assert data["nested_fields"] is None

    def test_with_bits(self):
        f = _make_field(name="flags", base="uint8", size=1,
                        bits={"0": "enabled", "1-3": "mode"})
        data = _build_field_data(f)
        assert data["bits"] is not None
        assert len(data["bits"]) == 2

    def test_with_nested_fields(self):
        nested = [_make_field(name="x", base="uint16", size=2, offset=0),
                  _make_field(name="y", base="uint16", size=2, offset=2)]
        f = _make_field(name="samples", base="struct", size=4,
                        is_repeated_struct=True, is_array=True, fields=nested)
        data = _build_field_data(f)
        assert data["nested_fields"] is not None
        assert len(data["nested_fields"]) == 2
        assert data["nested_fields"][0]["name"] == "x"


class TestBuildPayloadData:
    def test_basic(self):
        fields = [
            _make_field(name="a", base="uint8", size=1, offset=0),
            _make_field(name="b", base="uint16", size=2, offset=1),
        ]
        payload = Payload(fields=fields)
        data = _build_payload_data(payload)
        assert len(data["fields"]) == 2
        assert data["size"] == 3
        assert data["is_variable"] is False

    def test_variable_size(self):
        fields = [
            _make_field(name="count", base="uint8", size=1, offset=0),
            _make_field(name="data", base="uint8", size=1, is_array=True,
                        array_size=None, offset=1),
        ]
        payload = Payload(fields=fields)
        data = _build_payload_data(payload)
        assert data["size"] is None
        assert data["is_variable"] is True


# ---------------------------------------------------------------------------
# Unit tests: _build_docs_context
# ---------------------------------------------------------------------------

class TestBuildDocsContext:
    def _make_char(self, name="temperature",
                   uuid="12345678-1234-1234-1234-123456789001"):
        field = _make_field(name="value", base="int16", size=2, offset=0)
        payload = Payload(fields=[field])
        return Characteristic(
            name=name, uuid=uuid,
            properties=["read", "notify"], permissions=["read"],
            description="Test char", payload=payload,
        )

    def test_basic_context(self):
        char = self._make_char()
        schema = _make_schema(characteristics=[char])
        ctx = _build_docs_context(schema)

        assert ctx["service"]["name"] == "test_service"
        assert ctx["service"]["schema_version"] == "1.0"
        assert ctx["has_changes"] is False
        assert ctx["changelog"] == []
        assert len(ctx["characteristics"]) == 1
        assert ctx["characteristics"][0]["name"] == "temperature"
        assert ctx["characteristics"][0]["change_status"] is None

    def test_with_changelog(self):
        schema = _make_schema(characteristics=[self._make_char()])
        changelog = [{"version": "1.0", "message": "Initial"}]
        ctx = _build_docs_context(schema, changelog=changelog)
        assert ctx["changelog"] == changelog

    def test_with_diff_modified_char(self):
        char = self._make_char()
        schema = _make_schema(characteristics=[char])

        field_change = FieldChange(name="value", change_type="modified",
                                   details="type changed")
        char_change = CharacteristicChange(
            name="temperature", change_type="modified",
            field_changes=[field_change],
        )
        diff = SchemaDiff(
            service_name="test_service", has_changes=True,
            characteristic_changes=[char_change],
        )

        ctx = _build_docs_context(schema, diff=diff)
        assert ctx["has_changes"] is True
        assert ctx["characteristics"][0]["change_status"] == "modified"
        # Field should have change_status set
        payload_data = ctx["characteristics"][0]["payload"]
        assert payload_data["fields"][0]["change_status"] == "modified"

    def test_with_diff_added_char(self):
        char = self._make_char()
        schema = _make_schema(characteristics=[char])
        char_change = CharacteristicChange(
            name="temperature", change_type="added",
        )
        diff = SchemaDiff(
            service_name="test_service", has_changes=True,
            characteristic_changes=[char_change],
        )
        ctx = _build_docs_context(schema, diff=diff)
        assert ctx["characteristics"][0]["change_status"] == "added"


# ---------------------------------------------------------------------------
# Integration tests: generate()
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_generate_simple(self, tmp_path):
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(_simple_schema_yaml())
        schema = load_schema(schema_file)

        output = tmp_path / "docs" / "test_service.html"
        result = docs.generate(schema, output)

        assert result.exists()
        assert result.suffix == ".html"
        html = result.read_text()
        assert "test_service" in html
        assert "temperature" in html
        assert "12345678-1234-1234-1234-123456789001" in html

    def test_generate_adds_html_extension(self, tmp_path):
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(_simple_schema_yaml())
        schema = load_schema(schema_file)

        output = tmp_path / "docs" / "test_service"
        result = docs.generate(schema, output, fmt="html")
        assert result.suffix == ".html"
        assert result.exists()

    def test_generate_creates_parent_dirs(self, tmp_path):
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(_simple_schema_yaml())
        schema = load_schema(schema_file)

        output = tmp_path / "deep" / "nested" / "dir" / "test.html"
        result = docs.generate(schema, output)
        assert result.exists()

    def test_generate_with_diff(self, tmp_path):
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(_simple_schema_yaml())
        schema = load_schema(schema_file)

        char_change = CharacteristicChange(
            name="temperature", change_type="added",
        )
        diff = SchemaDiff(
            service_name="test_service", has_changes=True,
            characteristic_changes=[char_change],
        )

        output = tmp_path / "docs" / "test_service.html"
        result = docs.generate(schema, output, diff=diff)
        html = result.read_text()
        assert "added" in html.lower()

    def test_generate_with_changelog(self, tmp_path):
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(_simple_schema_yaml())
        schema = load_schema(schema_file)

        changelog = [{"timestamp": "2026-01-15 10:00", "revision": 1,
                      "message": "Initial release",
                      "characteristics": {"added": ["temperature"],
                                          "removed": [], "modified": {}}}]
        output = tmp_path / "docs" / "test_service.html"
        result = docs.generate(schema, output, changelog=changelog)
        html = result.read_text()
        assert "Initial release" in html

    def test_generate_unreleased_flag(self, tmp_path):
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(_simple_schema_yaml())
        schema = load_schema(schema_file)

        output = tmp_path / "docs" / "test_service.html"
        result = docs.generate(schema, output, unreleased=True)
        html = result.read_text()
        assert "unreleased" in html.lower()

    def test_generate_with_bitfields(self, tmp_path):
        yaml_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  status:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read]
    permissions: [read]
    payload:
      flags:
        type: uint8
        bits:
          0: enabled
          1-3: mode
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(yaml_content)
        schema = load_schema(schema_file)

        output = tmp_path / "docs" / "test.html"
        result = docs.generate(schema, output)
        html = result.read_text()
        assert "enabled" in html
        assert "mode" in html

    def test_generate_with_repeated_struct(self, tmp_path):
        yaml_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  sensor_data:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, notify]
    permissions: [read]
    payload:
      count: uint8
      samples[]:
        x: uint16
        y: uint16
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(yaml_content)
        schema = load_schema(schema_file)

        output = tmp_path / "docs" / "test.html"
        result = docs.generate(schema, output)
        html = result.read_text()
        assert "samples" in html
        assert "sensor_data" in html

    def test_generate_with_named_values(self, tmp_path):
        yaml_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  command:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [write]
    permissions: [write]
    payload:
      opcode:
        type: uint8
        values:
          0: "reset"
          1: "start"
          2: "stop"
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(yaml_content)
        schema = load_schema(schema_file)

        output = tmp_path / "docs" / "test.html"
        result = docs.generate(schema, output)
        html = result.read_text()
        assert "reset" in html
        assert "start" in html
        assert "stop" in html


# ---------------------------------------------------------------------------
# Integration tests: generate_combined()
# ---------------------------------------------------------------------------

class TestGenerateCombined:
    def _load_schema_from_yaml(self, tmp_path, name, yaml_content):
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml_content)
        return load_schema(path)

    def test_combined_basic(self, tmp_path):
        schema1 = self._load_schema_from_yaml(tmp_path, "svc1", _simple_schema_yaml(
            service_name="service_alpha",
            service_uuid="11111111-1111-1111-1111-111111111111",
        ))
        schema2 = self._load_schema_from_yaml(tmp_path, "svc2", _simple_schema_yaml(
            service_name="service_beta",
            service_uuid="22222222-2222-2222-2222-222222222222",
        ))

        output = tmp_path / "docs" / "combined.html"
        result = docs.generate_combined([schema1, schema2], output)

        assert result.exists()
        html = result.read_text()
        assert "service_alpha" in html
        assert "service_beta" in html

    def test_combined_title(self, tmp_path):
        schema = self._load_schema_from_yaml(tmp_path, "svc", _simple_schema_yaml())
        output = tmp_path / "docs" / "combined.html"
        result = docs.generate_combined([schema], output)
        html = result.read_text()
        assert "GATT Services Documentation" in html

    def test_combined_adds_html_extension(self, tmp_path):
        schema = self._load_schema_from_yaml(tmp_path, "svc", _simple_schema_yaml())
        output = tmp_path / "docs" / "combined"
        result = docs.generate_combined([schema], output, fmt="html")
        assert result.suffix == ".html"
        assert result.exists()

    def test_combined_with_diffs(self, tmp_path):
        schema1 = self._load_schema_from_yaml(tmp_path, "svc1", _simple_schema_yaml(
            service_name="svc_a",
            service_uuid="11111111-1111-1111-1111-111111111111",
        ))
        schema2 = self._load_schema_from_yaml(tmp_path, "svc2", _simple_schema_yaml(
            service_name="svc_b",
            service_uuid="22222222-2222-2222-2222-222222222222",
        ))

        char_change = CharacteristicChange(
            name="temperature", change_type="added",
        )
        diffs = {
            "svc_a": SchemaDiff(
                service_name="svc_a", has_changes=True,
                characteristic_changes=[char_change],
            ),
        }

        output = tmp_path / "docs" / "combined.html"
        result = docs.generate_combined([schema1, schema2], output, diffs=diffs)
        html = result.read_text()
        assert "added" in html.lower()
        assert "svc_a" in html
        assert "svc_b" in html

    def test_combined_with_changelogs(self, tmp_path):
        schema1 = self._load_schema_from_yaml(tmp_path, "svc1", _simple_schema_yaml(
            service_name="svc_a",
            service_uuid="11111111-1111-1111-1111-111111111111",
        ))
        schema2 = self._load_schema_from_yaml(tmp_path, "svc2", _simple_schema_yaml(
            service_name="svc_b",
            service_uuid="22222222-2222-2222-2222-222222222222",
        ))

        changelogs = {
            "svc_a": [{"timestamp": "2026-01-15 10:00", "revision": 1,
                        "message": "Init",
                        "characteristics": {"added": [], "removed": [],
                                            "modified": {}}}],
        }

        output = tmp_path / "docs" / "combined.html"
        result = docs.generate_combined(
            [schema1, schema2], output, changelogs=changelogs
        )
        html = result.read_text()
        assert "Init" in html

    def test_combined_unreleased(self, tmp_path):
        schema = self._load_schema_from_yaml(tmp_path, "svc", _simple_schema_yaml())
        output = tmp_path / "docs" / "combined.html"
        result = docs.generate_combined([schema], output, unreleased=True)
        html = result.read_text()
        assert "unreleased" in html.lower()


# ---------------------------------------------------------------------------
# Integration tests: Markdown output
# ---------------------------------------------------------------------------

_BITFIELD_SCHEMA_YAML = """
schema_version: "1.0"

service:
  name: bit_service
  uuid: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

characteristics:
  status:
    uuid: "aaaaaaaa-aaaa-aaaa-aaaa-000000000001"
    properties: [read]
    permissions: [read]
    payload:
      flags:
        type: uint8
        bits:
          0: ready
          1: error
"""


class TestGenerateMarkdown:
    def _load(self, tmp_path, name, yaml_content):
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml_content)
        return load_schema(path)

    def test_basic_markdown(self, tmp_path):
        schema = self._load(tmp_path, "test", _simple_schema_yaml())
        output = tmp_path / "docs" / "test.md"
        result = docs.generate(schema, output, fmt="md")

        assert result.suffix == ".md"
        assert result.exists()
        md = result.read_text()
        assert "# Service:" in md
        assert "## Characteristics" in md
        assert "|---" in md  # GFM table separator

    def test_numbered_subtable(self, tmp_path):
        schema = self._load(tmp_path, "bits", _BITFIELD_SCHEMA_YAML)
        output = tmp_path / "docs" / "bits.md"
        result = docs.generate(schema, output, fmt="md")

        md = result.read_text()
        assert "see Table 1" in md
        assert "#### Table 1 —" in md
        assert "`flags` bitfield" in md

    def test_structured_changelog_entry(self, tmp_path):
        schema = self._load(tmp_path, "test", _simple_schema_yaml())
        changelog = [{
            "revision": 2,
            "timestamp": "2026-04-15 10:00",
            "message": "Overhaul",
            "characteristics": {
                "added": ["device_info"],
                "removed": ["legacy_cmd"],
                "modified": {
                    "temperature": {
                        "uuid": {"old": "aaa", "new": "bbb"},
                        "fields_removed": ["stale_field"],
                        "fields_modified": [{"name": "value", "detail": "type uint16 -> int16"}],
                        "offsets_changed": True,
                    },
                },
            },
        }]

        output = tmp_path / "docs" / "test.md"
        result = docs.generate(schema, output, fmt="md", changelog=changelog)
        md = result.read_text()

        assert "### Revision 2 — 2026-04-15" in md
        # Added / removed characteristics appear as rows in the service-level table
        assert "#### Modified service" in md
        assert "| Characteristic added | `device_info` |" in md
        assert "| Characteristic removed | `legacy_cmd` |" in md
        assert "#### Modified `1. temperature`" in md
        assert "| Change | Detail |" in md
        assert "| UUID changed | `aaa` → `bbb` |" in md
        assert "| Field removed | `stale_field` |" in md
        assert "| Payload offsets changed | — |" in md
        # Old diff fence should be gone
        assert "```diff" not in md

    def test_service_level_uuid_change_renders_as_UUID(self, tmp_path):
        schema = self._load(tmp_path, "test", _simple_schema_yaml())
        changelog = [{
            "revision": 2,
            "timestamp": "2026-04-15 10:00",
            "message": "Rename",
            "service_changes": ["Service UUID changed: aaa -> bbb"],
        }]

        output = tmp_path / "docs" / "test.md"
        result = docs.generate(schema, output, fmt="md", changelog=changelog)
        md = result.read_text()

        assert "| UUID changed | — |" in md
        assert "Uuid" not in md

    def test_combined_markdown_prefixes_headings(self, tmp_path):
        schema1 = self._load(tmp_path, "svc1", _simple_schema_yaml(
            service_name="service_alpha",
            service_uuid="11111111-1111-1111-1111-111111111111",
        ))
        schema2 = self._load(tmp_path, "svc2", _simple_schema_yaml(
            service_name="service_beta",
            service_uuid="22222222-2222-2222-2222-222222222222",
        ))

        output = tmp_path / "docs" / "combined.md"
        result = docs.generate_combined([schema1, schema2], output, fmt="md")

        md = result.read_text()
        assert "# 1. service_alpha" in md
        assert "# 2. service_beta" in md
        assert "\n---\n" in md  # service separator
        # Characteristics numbered as <service>.<char> in combined mode
        assert "### 1.1 temperature" in md
        assert "### 2.1 temperature" in md

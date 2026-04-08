"""Tests for schema parsing."""

import pytest
from gattc.schema import (
    parse_type, TypeInfo, Field, Payload, Characteristic, Service, Schema,
    _parse_field, _parse_payload, load_schema, validate_schema,
    _is_valid_uuid, _validate_c_identifier,
)
from pathlib import Path


class TestParseType:
    """Tests for parse_type function."""

    def test_uint8(self):
        t = parse_type("uint8")
        assert t.base == "uint8"
        assert t.size == 1
        assert t.endian == "none"
        assert not t.is_array

    def test_uint16_little_endian(self):
        t = parse_type("uint16")
        assert t.base == "uint16"
        assert t.size == 2
        assert t.endian == "little"
        assert not t.is_array

    def test_uint16_big_endian(self):
        t = parse_type("uint16_be")
        assert t.base == "uint16"
        assert t.size == 2
        assert t.endian == "big"
        assert not t.is_array

    def test_int32_little_endian(self):
        t = parse_type("int32")
        assert t.base == "int32"
        assert t.size == 4
        assert t.endian == "little"
        assert not t.is_array

    def test_int32_big_endian(self):
        t = parse_type("int32_be")
        assert t.base == "int32"
        assert t.size == 4
        assert t.endian == "big"
        assert not t.is_array

    def test_bytes_array(self):
        t = parse_type("bytes[6]")
        assert t.base == "bytes"
        assert t.size == 1
        assert t.endian == "none"
        assert t.is_array
        assert t.array_size == 6

    def test_fixed_array(self):
        t = parse_type("uint16[10]")
        assert t.base == "uint16"
        assert t.size == 2
        assert t.endian == "little"
        assert t.is_array
        assert t.array_size == 10

    def test_mtu_fill_array(self):
        t = parse_type("uint16[]")
        assert t.base == "uint16"
        assert t.size == 2
        assert t.is_array
        assert t.array_size is None

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            parse_type("unknown_type")


class TestParseField:
    """Tests for _parse_field function."""

    def test_simple_field(self):
        field = _parse_field("value", "uint16")
        assert field.name == "value"
        assert field.type_info.base == "uint16"
        assert field.type_info.size == 2

    def test_field_with_metadata(self):
        field = _parse_field("temperature", {
            "type": "int16",
            "unit": "celsius_x100",
            "values": [-40, 85],
            "description": "Temperature reading"
        })
        assert field.name == "temperature"
        assert field.type_info.base == "int16"
        assert field.unit == "celsius_x100"
        assert field.values == [-40, 85]
        assert field.description == "Temperature reading"

    def test_field_with_explicit_offset(self):
        field = _parse_field("future", {
            "type": "uint16",
            "offset": 16
        })
        assert field.name == "future"
        assert field.offset == 16

    def test_field_with_bits(self):
        field = _parse_field("flags", {
            "type": "uint8",
            "bits": {
                "0": "enabled",
                "1-3": "mode"
            }
        })
        assert field.name == "flags"
        assert field.bits == {"0": "enabled", "1-3": "mode"}

    def test_repeated_struct(self):
        field = _parse_field("samples[]", {
            "x": "uint16",
            "y": "uint16",
            "z": "uint16"
        })
        assert field.name == "samples"
        assert field.type_info.is_repeated_struct
        assert field.type_info.is_array
        assert field.type_info.size == 6  # 3 * 2 bytes
        assert len(field.fields) == 3


class TestParsePayload:
    """Tests for _parse_payload function."""

    def test_simple_payload(self):
        payload = _parse_payload({
            "value": "uint16"
        })
        assert len(payload.fields) == 1
        assert payload.fields[0].name == "value"
        assert payload.fields[0].offset == 0

    def test_auto_offset_computation(self):
        payload = _parse_payload({
            "a": "uint8",
            "b": "uint16",
            "c": "uint32"
        })
        assert payload.fields[0].offset == 0  # uint8 at 0
        assert payload.fields[1].offset == 1  # uint16 at 1
        assert payload.fields[2].offset == 3  # uint32 at 3

    def test_explicit_offset_gap(self):
        payload = _parse_payload({
            "version": "uint8",
            "future": {
                "type": "uint16",
                "offset": 16
            }
        })
        assert payload.fields[0].offset == 0
        assert payload.fields[1].offset == 16

    def test_variable_mode(self):
        payload = _parse_payload({
            "_mode": "variable",
            "_min_size": 1,
            "_max_size": 20,
            "data": "uint8[]"
        })
        assert payload.mode == "variable"
        assert payload.min_size == 1
        assert payload.max_size == 20


class TestLoadSchema:
    """Tests for loading schema files."""

    def test_load_debug_schema(self, tmp_path):
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  temperature:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, notify]
    permissions: [read]
    payload:
      value:
        type: int16
        unit: celsius_x100
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        assert schema.service.name == "test_service"
        assert len(schema.characteristics) == 1
        assert schema.characteristics[0].name == "temperature"
        assert schema.characteristics[0].payload.fields[0].name == "value"
        assert schema.characteristics[0].payload.fields[0].type_info.base == "int16"

    def test_load_directional_payloads(self, tmp_path):
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  control:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, write, notify]
    permissions: [read, write]

    write_payload:
      command: uint8
      param: uint16

    read_payload:
      status: uint8

    notify_payload:
      event: uint32
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        char = schema.characteristics[0]

        assert char.payload is None
        assert char.write_payload is not None
        assert char.read_payload is not None
        assert char.notify_payload is not None

        assert char.write_payload.fields[0].name == "command"
        assert char.read_payload.fields[0].name == "status"
        assert char.notify_payload.fields[0].name == "event"


class TestUuidValidation:
    """Tests for UUID format validation."""

    def test_valid_uuid_lowercase(self):
        assert _is_valid_uuid("12345678-1234-1234-1234-123456789abc")

    def test_valid_uuid_uppercase(self):
        assert _is_valid_uuid("12345678-1234-1234-1234-123456789ABC")

    def test_valid_uuid_mixed_case(self):
        assert _is_valid_uuid("12345678-abcd-ABCD-1234-123456789abc")

    def test_invalid_uuid_too_short(self):
        assert not _is_valid_uuid("12345678-1234-1234-1234")

    def test_invalid_uuid_no_dashes(self):
        assert not _is_valid_uuid("12345678123412341234123456789abc")

    def test_invalid_uuid_wrong_format(self):
        assert not _is_valid_uuid("not-a-valid-uuid")

    def test_invalid_uuid_empty(self):
        assert not _is_valid_uuid("")


class TestValidateCIdentifier:
    """Tests for _validate_c_identifier function."""

    def test_valid_simple(self):
        assert _validate_c_identifier("temperature") is None

    def test_valid_with_underscores(self):
        assert _validate_c_identifier("my_field") is None

    def test_valid_starts_with_underscore(self):
        assert _validate_c_identifier("_value") is None

    def test_invalid_starts_with_digit(self):
        assert _validate_c_identifier("123abc") is not None

    def test_invalid_contains_hyphen(self):
        assert _validate_c_identifier("foo-bar") is not None

    def test_invalid_contains_space(self):
        assert _validate_c_identifier("my field") is not None

    def test_invalid_empty(self):
        assert _validate_c_identifier("") is not None

    def test_invalid_keyword_int(self):
        reason = _validate_c_identifier("int")
        assert reason is not None
        assert "reserved keyword" in reason

    def test_invalid_keyword_static(self):
        assert _validate_c_identifier("static") is not None

    def test_valid_keyword_like(self):
        assert _validate_c_identifier("integer") is None


def _make_schema(service_name="test_svc", char_name="temperature", field_name="value", bits=None):
    """Helper to build a minimal valid Schema for validation tests."""
    field = Field(name=field_name, type_info=parse_type("uint8"), offset=0, bits=bits)
    payload = Payload(fields=[field])
    char = Characteristic(
        name=char_name,
        uuid="12345678-1234-1234-1234-123456789abc",
        properties=["read"],
        permissions=["read"],
        payload=payload,
    )
    return Schema(
        schema_version="1.0",
        service=Service(name=service_name, uuid="12345678-1234-1234-1234-123456789001"),
        characteristics=[char],
    )


class TestValidateSchemaIdentifiers:
    """Tests for C identifier validation in validate_schema."""

    def test_valid_names_no_errors(self):
        schema = _make_schema()
        errors = validate_schema(schema)
        assert not any("C identifier" in e for e in errors)

    def test_invalid_service_name(self):
        schema = _make_schema(service_name="my-service")
        errors = validate_schema(schema)
        assert any("Service name" in e and "C identifier" in e for e in errors)

    def test_invalid_char_name(self):
        schema = _make_schema(char_name="123bad")
        errors = validate_schema(schema)
        assert any("Characteristic name" in e and "C identifier" in e for e in errors)

    def test_invalid_field_name(self):
        schema = _make_schema(field_name="int")
        errors = validate_schema(schema)
        assert any("Field name" in e and "C identifier" in e for e in errors)

    def test_invalid_bit_name(self):
        schema = _make_schema(bits={"0": "foo bar"})
        errors = validate_schema(schema)
        assert any("Bit name" in e and "C identifier" in e for e in errors)

    def test_multiple_invalid_names_all_reported(self):
        schema = _make_schema(service_name="bad-svc", char_name="1char", field_name="my field")
        errors = [e for e in validate_schema(schema) if "C identifier" in e]
        assert len(errors) >= 3

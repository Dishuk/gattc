"""Tests for Zephyr code generator."""

import pytest
from pathlib import Path
from gattc.schema import load_schema
from gattc.generators import zephyr


class TestZephyrGenerator:
    """Tests for Zephyr code generation."""

    def test_generate_simple_service(self, tmp_path):
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
        output_path = tmp_path / "generated" / "test_service"

        header_path, source_path = zephyr.generate(schema, output_path)

        assert header_path.exists()
        assert source_path.exists()

        header = header_path.read_text()
        source = source_path.read_text()

        # Check header contains expected elements
        assert "TEST_SERVICE_UUID_VAL" in header
        assert "TEST_SERVICE_TEMPERATURE_UUID_VAL" in header
        assert "} __packed test_service_temperature_t;" in header
        assert "test_service_temperature_t" in header
        assert "int16_t value;" in header
        assert "_Static_assert" in header

    def test_generate_with_arrays(self, tmp_path):
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  data:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read]
    permissions: [read]
    payload:
      count: uint8
      values: uint16[10]
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        output_path = tmp_path / "generated" / "test_service"

        header_path, _ = zephyr.generate(schema, output_path)
        header = header_path.read_text()

        assert "uint16_t values[10];" in header

    def test_generate_with_bytes(self, tmp_path):
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  info:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read]
    permissions: [read]
    payload:
      mac: bytes[6]
      serial: bytes[8]
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        output_path = tmp_path / "generated" / "test_service"

        header_path, _ = zephyr.generate(schema, output_path)
        header = header_path.read_text()

        assert "uint8_t mac[6];" in header
        assert "uint8_t serial[8];" in header

    def test_generate_with_repeated_struct(self, tmp_path):
        schema_content = """
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
      packet_count: uint8
      timestamp: uint32
      samples[]:
        x: uint16
        y: uint16
        z: uint16
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        output_path = tmp_path / "generated" / "test_service"

        header_path, _ = zephyr.generate(schema, output_path)
        header = header_path.read_text()

        # Check nested struct
        assert "test_service_sensor_data_samples_t" in header
        assert "uint16_t x;" in header
        assert "uint16_t y;" in header
        assert "uint16_t z;" in header

        # Check flexible array member
        assert "test_service_sensor_data_samples_t samples[];" in header

        # Check MTU helper
        assert "items_per_mtu" in header

    def test_generate_pack_unpack(self, tmp_path):
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  config:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, write]
    permissions: [read, write]
    payload:
      mode: uint8
      threshold: uint16
      flags: uint32
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        output_path = tmp_path / "generated" / "test_service"

        header_path, _ = zephyr.generate(schema, output_path)
        header = header_path.read_text()

        # Check pack function
        assert "test_service_config_pack" in header
        assert "sys_cpu_to_le16" in header
        assert "sys_cpu_to_le32" in header

        # Check unpack function
        assert "test_service_config_unpack" in header
        assert "sys_le16_to_cpu" in header
        assert "sys_le32_to_cpu" in header

    def test_generate_bitfield_macros(self, tmp_path):
        schema_content = """
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
          1: error
          2-4: mode
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        output_path = tmp_path / "generated" / "test_service"

        header_path, _ = zephyr.generate(schema, output_path)
        header = header_path.read_text()

        assert "TEST_SERVICE_STATUS_FLAGS_ENABLED" in header
        assert "TEST_SERVICE_STATUS_FLAGS_ERROR" in header
        assert "TEST_SERVICE_STATUS_FLAGS_MODE_MASK" in header
        assert "TEST_SERVICE_STATUS_FLAGS_MODE_SHIFT" in header

    def test_generate_separate_paths(self, tmp_path):
        """Test generating header and source to different directories."""
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  temperature:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read]
    permissions: [read]
    payload:
      value: int16
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        header_dir = tmp_path / "include" / "generated"
        source_dir = tmp_path / "src" / "generated"

        header_path, source_path = zephyr.generate(
            schema,
            header_path=header_dir,
            source_path=source_dir,
        )

        # Check files are in correct directories
        assert header_path.parent == header_dir
        assert source_path.parent == source_dir
        assert header_path.name == "test_service.h"
        assert source_path.name == "test_service.c"
        assert header_path.exists()
        assert source_path.exists()

        # Check source includes the header correctly
        source = source_path.read_text()
        assert '#include "test_service.h"' in source

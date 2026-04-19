"""Tests for Zephyr code generator."""

import re

from gattc.generators import zephyr
from gattc.schema import load_schema


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

    def test_val_attr_idx_shifts_across_ccc(self, tmp_path):
        """First char with notify inserts a CCC attr, shifting the second char's value index."""
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  alpha:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, notify]
    permissions: [read]
    payload:
      value: int16
  beta:
    uuid: "12345678-1234-1234-1234-123456789002"
    properties: [read]
    permissions: [read]
    payload:
      value: int16
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        header_path, _ = zephyr.generate(schema, tmp_path / "generated" / "test_service")
        header = header_path.read_text()

        assert "#define TEST_SERVICE_ALPHA_VAL_ATTR_IDX 2" in header
        assert "#define TEST_SERVICE_BETA_VAL_ATTR_IDX 5" in header
        assert "extern const struct bt_gatt_service_static test_service_svc;" in header

    def test_val_attr_idx_matches_source_layout(self, tmp_path):
        """Each VAL_ATTR_IDX must match the characteristic's actual position in the source.

        Guards against silent drift if source.c.j2 gains another BT_GATT_* macro
        that contributes attributes (e.g., BT_GATT_CUD) without the val_attr_idx
        calculation being updated.
        """
        schema_content = """
schema_version: "1.0"

service:
  name: test_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  alpha:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, notify]
    permissions: [read]
    payload:
      value: int16
  beta:
    uuid: "12345678-1234-1234-1234-123456789002"
    properties: [read, indicate]
    permissions: [read]
    payload:
      value: int16
  gamma:
    uuid: "12345678-1234-1234-1234-123456789003"
    properties: [read]
    permissions: [read]
    payload:
      value: int16
"""
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(schema_content)

        schema = load_schema(schema_file)
        header_path, source_path = zephyr.generate(schema, tmp_path / "generated" / "test_service")
        header = header_path.read_text()
        source = source_path.read_text()

        body_match = re.search(r"BT_GATT_SERVICE_DEFINE\s*\([^,]+,(.*?)\);", source, re.DOTALL)
        assert body_match, "BT_GATT_SERVICE_DEFINE not found in generated source"

        # Attrs each known BT_GATT_* macro contributes (Zephyr API contract).
        attr_counts = {
            "PRIMARY_SERVICE": 1,
            "CHARACTERISTIC": 2,
            "CCC": 1,
        }

        macros = re.findall(r"BT_GATT_([A-Z_]+)\s*\(", body_match.group(1))
        unknown = [m for m in macros if m not in attr_counts]
        assert not unknown, (
            f"Unknown BT_GATT_{unknown[0]} in source template — update attr_counts "
            f"here and _char_attr_count in generators/zephyr.py"
        )

        pos = 0
        char_names = [c.name.upper() for c in schema.characteristics]
        char_idx = 0
        for m in macros:
            if m == "CHARACTERISTIC":
                expected = pos + 1
                assert f"#define TEST_SERVICE_{char_names[char_idx]}_VAL_ATTR_IDX {expected}" in header, (
                    f"Header VAL_ATTR_IDX for {char_names[char_idx]} disagrees with source "
                    f"(expected {expected})"
                )
                char_idx += 1
            pos += attr_counts[m]

        assert char_idx == len(char_names)


class TestZephyrCombinedGenerator:
    """Tests for combined-mode Zephyr code generation."""

    SCHEMA_A = """
schema_version: "1.0"

service:
  name: service_alpha
  uuid: "11111111-1111-1111-1111-111111111111"

characteristics:
  temperature:
    uuid: "11111111-1111-1111-1111-111111111001"
    properties: [read, notify]
    permissions: [read]
    payload:
      value: int16
"""

    SCHEMA_B = """
schema_version: "1.0"

service:
  name: service_beta
  uuid: "22222222-2222-2222-2222-222222222222"

characteristics:
  humidity:
    uuid: "22222222-2222-2222-2222-222222222001"
    properties: [read]
    permissions: [read]
    payload:
      level: uint8
"""

    def _load(self, tmp_path, name, content):
        path = tmp_path / f"{name}.yaml"
        path.write_text(content)
        return load_schema(path)

    def test_generate_combined_basic(self, tmp_path):
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)
        s2 = self._load(tmp_path, "b", self.SCHEMA_B)

        output = tmp_path / "generated" / "combined"
        header, source = zephyr.generate_combined([s1, s2], output_path=output)

        assert header.exists()
        assert source.exists()

        h = header.read_text()
        assert "SERVICE_ALPHA" in h
        assert "SERVICE_BETA" in h
        assert "temperature" in h.lower() or "TEMPERATURE" in h
        assert "humidity" in h.lower() or "HUMIDITY" in h

        s = source.read_text()
        assert "service_alpha" in s or "SERVICE_ALPHA" in s
        assert "service_beta" in s or "SERVICE_BETA" in s

    def test_generate_combined_output_naming_default(self, tmp_path):
        """output_name controls file naming when using header_path/source_path."""
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)

        header, source = zephyr.generate_combined(
            [s1], header_path=tmp_path / "include", source_path=tmp_path / "src",
        )

        assert header.name == "gatt_services.h"
        assert source.name == "gatt_services.c"

    def test_generate_combined_output_naming_custom(self, tmp_path):
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)

        header, source = zephyr.generate_combined(
            [s1], header_path=tmp_path / "include",
            source_path=tmp_path / "src", output_name="my_services",
        )

        assert header.name == "my_services.h"
        assert source.name == "my_services.c"

    def test_generate_combined_separate_paths(self, tmp_path):
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)
        s2 = self._load(tmp_path, "b", self.SCHEMA_B)

        hdir = tmp_path / "include"
        sdir = tmp_path / "src"

        header, source = zephyr.generate_combined(
            [s1, s2], header_path=hdir, source_path=sdir,
        )

        assert header.parent == hdir
        assert source.parent == sdir
        assert header.exists()
        assert source.exists()

    def test_generate_combined_header_guard(self, tmp_path):
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)

        header, _ = zephyr.generate_combined(
            [s1], output_path=tmp_path / "out", output_name="my_ble_services"
        )

        h = header.read_text()
        assert "MY_BLE_SERVICES_H" in h

    def test_generate_combined_multiple_characteristics(self, tmp_path):
        yaml_multi = """
schema_version: "1.0"

service:
  name: multi_service
  uuid: "33333333-3333-3333-3333-333333333333"

characteristics:
  sensor_a:
    uuid: "33333333-3333-3333-3333-333333333001"
    properties: [read]
    permissions: [read]
    payload:
      value: uint16
  sensor_b:
    uuid: "33333333-3333-3333-3333-333333333002"
    properties: [read, notify]
    permissions: [read]
    payload:
      reading: int32
"""
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)
        s2 = self._load(tmp_path, "multi", yaml_multi)

        header, _ = zephyr.generate_combined([s1, s2], output_path=tmp_path / "out")
        h = header.read_text()

        assert "SERVICE_ALPHA" in h
        assert "MULTI_SERVICE" in h
        assert "SENSOR_A" in h
        assert "SENSOR_B" in h

    def test_generate_combined_source_includes_header(self, tmp_path):
        s1 = self._load(tmp_path, "a", self.SCHEMA_A)

        header, source = zephyr.generate_combined([s1], output_path=tmp_path / "out")
        s = source.read_text()
        assert f'#include "{header.name}"' in s

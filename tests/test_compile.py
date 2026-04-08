"""Compile-validation smoke tests for generated C code."""

import subprocess
import shutil
import pytest
from pathlib import Path
from gattc.schema import load_schema
from gattc.generators import zephyr

STUBS_DIR = Path(__file__).parent / "stubs"
GCC = shutil.which("gcc")

pytestmark = pytest.mark.skipif(GCC is None, reason="gcc not found")

# Exercises: scalars, arrays, bytes, repeated structs, pack/unpack, bitfields
SCHEMA = """
schema_version: "1.0"

service:
  name: smoke_service
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

  sensor_array:
    uuid: "12345678-1234-1234-1234-123456789002"
    properties: [read]
    permissions: [read]
    payload:
      count: uint8
      values: uint16[10]

  device_info:
    uuid: "12345678-1234-1234-1234-123456789003"
    properties: [read]
    permissions: [read]
    payload:
      mac: bytes[6]
      serial: bytes[8]

  accel_data:
    uuid: "12345678-1234-1234-1234-123456789004"
    properties: [read, notify]
    permissions: [read]
    payload:
      packet_count: uint8
      timestamp: uint32
      samples[]:
        x: int16
        y: int16
        z: int16

  config:
    uuid: "12345678-1234-1234-1234-123456789005"
    properties: [read, write]
    permissions: [read, write]
    payload:
      mode: uint8
      threshold: uint16
      max_value: uint32

  status:
    uuid: "12345678-1234-1234-1234-123456789006"
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

SCHEMA_B = """
schema_version: "1.0"

service:
  name: battery_service
  uuid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

characteristics:
  level:
    uuid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee01"
    properties: [read, notify]
    permissions: [read]
    payload:
      percent: uint8
"""


def _compile_check(header: Path, source: Path):
    result = subprocess.run(
        [GCC, "-fsyntax-only", "-std=c11", "-Wno-unused-function",
         f"-I{STUBS_DIR}", str(header), str(source)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"gcc syntax check failed:\n{result.stderr}"


def test_single_service_compiles(tmp_path):
    schema_file = tmp_path / "smoke.yaml"
    schema_file.write_text(SCHEMA)
    schema = load_schema(schema_file)
    header, source = zephyr.generate(schema, tmp_path / "out" / "smoke_service")
    _compile_check(header, source)


def test_combined_services_compile(tmp_path):
    f1 = tmp_path / "smoke.yaml"
    f1.write_text(SCHEMA)
    f2 = tmp_path / "battery.yaml"
    f2.write_text(SCHEMA_B)
    s1 = load_schema(f1)
    s2 = load_schema(f2)
    header, source = zephyr.generate_combined(
        [s1, s2], output_path=tmp_path / "out" / "combined",
    )
    _compile_check(header, source)

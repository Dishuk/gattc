"""Round-trip pack/unpack tests: generate C code, compile, run, verify."""

import subprocess
import shutil
import pytest
from pathlib import Path
from gattc.schema import load_schema
from gattc.generators import zephyr

STUBS_DIR = Path(__file__).parent / "stubs"
GCC = shutil.which("gcc")

pytestmark = pytest.mark.skipif(GCC is None, reason="gcc not found")

SCHEMA = """
schema_version: "1.0"

service:
  name: rt
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  scalars:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read]
    permissions: [read]
    payload:
      val_u8: uint8
      val_i16: int16
      val_u16: uint16
      val_u32: uint32

  scalars_be:
    uuid: "12345678-1234-1234-1234-123456789002"
    properties: [read]
    permissions: [read]
    payload:
      val_u16: uint16_be
      val_i16: int16_be
      val_u32: uint32_be

  mixed:
    uuid: "12345678-1234-1234-1234-123456789003"
    properties: [read]
    permissions: [read]
    payload:
      le_val: uint16
      be_val: uint32_be
      le_val2: uint16

  raw:
    uuid: "12345678-1234-1234-1234-123456789004"
    properties: [read]
    permissions: [read]
    payload:
      mac: bytes[6]
      serial: bytes[4]

  arrays:
    uuid: "12345678-1234-1234-1234-123456789005"
    properties: [read]
    permissions: [read]
    payload:
      u8s: uint8[4]
      u16s: uint16[3]
      i32s: int32[2]

  repeated:
    uuid: "12345678-1234-1234-1234-123456789006"
    properties: [read]
    permissions: [read]
    payload:
      count: uint8
      ts: uint32
      samples[]:
        x: int16
        y: int16

  bits:
    uuid: "12345678-1234-1234-1234-123456789007"
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

HARNESS = r"""
#include <stdio.h>
#include <string.h>
#include "rt.h"

#define ASSERT_EQ(a, b, msg) do { \
    if ((long long)(a) != (long long)(b)) { \
        fprintf(stderr, "FAIL %s: %lld != %lld\n", msg, \
                (long long)(a), (long long)(b)); \
        return 1; \
    } \
} while(0)

#define ASSERT_MEM(a, b, n, msg) do { \
    if (memcmp(a, b, n) != 0) { \
        fprintf(stderr, "FAIL %s: memcmp\n", msg); \
        return 1; \
    } \
} while(0)

static int test_scalars(void) {
    rt_scalars_t buf;
    rt_scalars_pack(&buf, 0x42, -1234, 0x1234, 0xDEADBEEF);
    uint8_t u8; int16_t i16; uint16_t u16; uint32_t u32;
    rt_scalars_unpack(&buf, &u8, &i16, &u16, &u32);
    ASSERT_EQ(u8, 0x42, "scalars.u8");
    ASSERT_EQ(i16, -1234, "scalars.i16");
    ASSERT_EQ(u16, 0x1234, "scalars.u16");
    ASSERT_EQ(u32, 0xDEADBEEF, "scalars.u32");
    return 0;
}

static int test_scalars_be(void) {
    rt_scalars_be_t buf;
    rt_scalars_be_pack(&buf, 0x1234, -1234, 0xDEADBEEF);
    uint16_t u16; int16_t i16; uint32_t u32;
    rt_scalars_be_unpack(&buf, &u16, &i16, &u32);
    ASSERT_EQ(u16, 0x1234, "be.u16");
    ASSERT_EQ(i16, -1234, "be.i16");
    ASSERT_EQ(u32, 0xDEADBEEF, "be.u32");
    return 0;
}

static int test_mixed(void) {
    rt_mixed_t buf;
    rt_mixed_pack(&buf, 0x1234, 0xDEADBEEF, 0x5678);
    uint16_t le1, le2; uint32_t be;
    rt_mixed_unpack(&buf, &le1, &be, &le2);
    ASSERT_EQ(le1, 0x1234, "mixed.le1");
    ASSERT_EQ(be, 0xDEADBEEF, "mixed.be");
    ASSERT_EQ(le2, 0x5678, "mixed.le2");
    return 0;
}

static int test_raw(void) {
    rt_raw_t buf;
    uint8_t mac_in[6] = {0x01,0x02,0x03,0x04,0x05,0x06};
    uint8_t ser_in[4] = {0xAA,0xBB,0xCC,0xDD};
    rt_raw_pack(&buf, mac_in, ser_in);
    uint8_t mac_out[6], ser_out[4];
    rt_raw_unpack(&buf, mac_out, ser_out);
    ASSERT_MEM(mac_in, mac_out, 6, "raw.mac");
    ASSERT_MEM(ser_in, ser_out, 4, "raw.serial");
    return 0;
}

static int test_arrays(void) {
    rt_arrays_t buf;
    uint8_t u8s_in[4] = {10, 20, 30, 40};
    uint16_t u16s_in[3] = {0x1234, 0x5678, 0x9ABC};
    int32_t i32s_in[2] = {-100000, 100000};
    rt_arrays_pack(&buf, u8s_in, u16s_in, i32s_in);
    uint8_t u8s_out[4]; uint16_t u16s_out[3]; int32_t i32s_out[2];
    rt_arrays_unpack(&buf, u8s_out, u16s_out, i32s_out);
    ASSERT_MEM(u8s_in, u8s_out, 4, "arrays.u8s");
    for (int i = 0; i < 3; i++) ASSERT_EQ(u16s_in[i], u16s_out[i], "arrays.u16s");
    for (int i = 0; i < 2; i++) ASSERT_EQ(i32s_in[i], i32s_out[i], "arrays.i32s");
    return 0;
}

static int test_repeated(void) {
    uint8_t raw[sizeof(rt_repeated_t) + 2 * sizeof(rt_repeated_samples_t)];
    memset(raw, 0, sizeof(raw));
    rt_repeated_t *buf = (rt_repeated_t *)raw;

    rt_repeated_pack(buf, 2, 0xDEADBEEF);
    rt_repeated_pack_item(&buf->samples[0], 100, -200);
    rt_repeated_pack_item(&buf->samples[1], -300, 400);

    uint8_t count; uint32_t ts;
    rt_repeated_unpack(buf, &count, &ts);
    ASSERT_EQ(count, 2, "repeated.count");
    ASSERT_EQ(ts, 0xDEADBEEF, "repeated.ts");

    int16_t x, y;
    rt_repeated_unpack_item(&buf->samples[0], &x, &y);
    ASSERT_EQ(x, 100, "repeated[0].x");
    ASSERT_EQ(y, -200, "repeated[0].y");
    rt_repeated_unpack_item(&buf->samples[1], &x, &y);
    ASSERT_EQ(x, -300, "repeated[1].x");
    ASSERT_EQ(y, 400, "repeated[1].y");
    return 0;
}

static int test_bits(void) {
    rt_bits_t buf;
    uint8_t flags_in = RT_BITS_FLAGS_ENABLED | (0x05 << RT_BITS_FLAGS_MODE_SHIFT);
    rt_bits_pack(&buf, flags_in);
    uint8_t flags_out;
    rt_bits_unpack(&buf, &flags_out);
    ASSERT_EQ(flags_in, flags_out, "bits.flags");
    return 0;
}

int main(void) {
    int rc = 0;
    rc |= test_scalars();
    rc |= test_scalars_be();
    rc |= test_mixed();
    rc |= test_raw();
    rc |= test_arrays();
    rc |= test_repeated();
    rc |= test_bits();
    if (rc == 0) fprintf(stderr, "All round-trip tests passed\n");
    return rc;
}
"""


def test_roundtrip(tmp_path):
    # Write schema and generate code
    schema_file = tmp_path / "rt.yaml"
    schema_file.write_text(SCHEMA)
    schema = load_schema(schema_file)
    header, source = zephyr.generate(schema, tmp_path / "out" / "rt")
    out_dir = header.parent

    # Write the C harness
    harness = tmp_path / "test_main.c"
    harness.write_text(HARNESS)

    # Compile to executable
    exe = tmp_path / "test_roundtrip.exe"
    result = subprocess.run(
        [GCC, "-std=c11", "-Wno-unused-function",
         f"-I{STUBS_DIR}", f"-I{out_dir}",
         str(harness), str(source),
         "-o", str(exe)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Compilation failed:\n{result.stderr}"

    # Run it
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, f"Round-trip failed:\n{result.stderr}"

# gattc Example Project

- [What's In Here](#whats-in-here)
- [Folder Layout](#folder-layout)
- [Timeline — How This Example Was Built](#timeline--how-this-example-was-built)
  - [1. Scaffold the Project](#1-scaffold-the-project)
  - [2. Initial Release (rev 001)](#2-initial-release-rev-001)
  - [3. v2 Hardware Changes (rev 002)](#3-v2-hardware-changes-rev-002)
  - [4. Accelerometer Added (rev 003, Single-Service)](#4-accelerometer-added-rev-003-single-service)
  - [5. Refresh Generated C](#5-refresh-generated-c)
- [Using the Generated Code](#using-the-generated-code)

## What's In Here

Two BLE services that together exercise most gattc features:

- **`heart_rate_service`** — Bluetooth SIG Heart Rate (`0x180D`). Standard-spec service with bit flags, enums, variable-length arrays (`uint16[]`), and notify/write properties.
- **`device_telemetry`** — Custom service: battery, firmware info, uptime, internal thermometer, 3-axis accelerometer. Demonstrates signed types, fixed-size byte arrays (`bytes[N]`), custom UUIDs, and repeated structs (`samples[]:`).

> **Not shown here:** directional payloads (`read_payload` / `write_payload` / `notify_payload`), big-endian types (`uint16_be`, …), variable-length payload mode (`_mode: variable`), `write_without_response` / `indicate` properties, authenticated/encrypted permissions, `bool` / `int8` / `uint64`, fixed-size typed arrays (`uint16[10]`), explicit offset gaps, HTML docs output, per-service docs output, and per-service output overrides. See [`docs/schema.md`](../docs/schema.md) and [`docs/config.md`](../docs/config.md) for the full feature set.

## Folder Layout

```
example/
├── gattc.yaml                   # Project config: schema paths, output paths, doc format
├── gattc/
│   ├── heart_rate_service.yaml  # Schema source
│   ├── device_telemetry.yaml    # Schema source
│   ├── snapshots/               # Last-released schema state (diff source for `gattc release`)
│   └── changelog/               # Per-service release history — one NNN.md per revision
├── src/generated/               # Zephyr C output: .h + .c per service
└── docs/ble/                    # Rendered Markdown documentation
```

## Timeline — How This Example Was Built

### 1. Scaffold the Project
```bash
gattc init
```
Creates `gattc.yaml` and a placeholder `gattc/echo_service.yaml`. The placeholder is replaced with hand-written schemas.

### 2. Initial Release (rev 001)
```bash
gattc release
```
No snapshots exist yet, so every service is recorded as an *initial release*. Changelog files `001.md` are written, snapshots are created under `gattc/snapshots/`, and Markdown docs are generated. A subsequent `gattc compile` produces the first pass of C code.

### 3. v2 Hardware Changes (rev 002)
Edits across both services:

- `heart_rate_service` — added bit `5: rr_resolution_1ms`, added enum value `7: upper_arm`, refined the characteristic description.
- `device_telemetry` — added bit `4: thermal_throttle`, added new `thermometer` characteristic.

```bash
gattc release
```
The editor opens once per changed service, pre-filled with the auto-detected diff. The message describes *why* the change was made — the tool records the structural details into the changelog frontmatter automatically. Both services get a `002.md`, snapshots are updated, and docs are regenerated with change highlighting.

### 4. Accelerometer Added (rev 003, Single-Service)
Edit to `device_telemetry` only — new `accelerometer` characteristic demonstrating the `samples[]:` repeated-struct pattern (header fields followed by a packed sample array).

```bash
gattc release gattc/device_telemetry.yaml -m "Add batched 3-axis accelerometer telemetry for motion analysis"
```
Passing an explicit schema path skips the editor and produces a single rev-003 entry for `device_telemetry` only. `heart_rate_service` remains at rev 002.

### 5. Refresh Generated C
`gattc release` regenerates docs, changelog, and snapshots but not C code. After any release:
```bash
gattc compile
```

## Using the Generated Code

Each `.h` in `src/generated/` ships packed structs, UUID macros, pack/unpack helpers, `*_VAL_ATTR_IDX` constants, and callback declarations. Wire them into a Zephyr app:

- Implement the declared callbacks (`*_read_cb`, `*_write_cb`, `*_ccc_changed`).
- Send notifications using the generated `pack()` + the `*_VAL_ATTR_IDX` macro, e.g.:

```c
device_telemetry_battery_status_t buf;
device_telemetry_battery_status_pack(&buf, level, status);
bt_gatt_notify(NULL,
    &device_telemetry_svc.attrs[DEVICE_TELEMETRY_BATTERY_STATUS_VAL_ATTR_IDX],
    &buf, sizeof(buf));
```

See [`docs/getting-started.md`](../docs/getting-started.md#using-generated-code) for pack/unpack patterns, write validation, CCC callbacks, and build integration.

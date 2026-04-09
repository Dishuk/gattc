# Getting Started

## Prerequisites

- Python >= 3.10
- Zephyr RTOS >= 3.5.0

## Installation

```bash
pip install git+https://github.com/polesskiy-dev/gattc.git
```

## Quick Start

### 1. Initialize Project

```bash
cd my-project
gattc init
```

Creates:
```
gattc.yaml              # Project configuration
gattc/
└── echo_service.yaml   # Example schema
```

### 2. Define a Service

Create `gattc/temperature_service.yaml`:

```yaml
schema_version: "1.0"

service:
  name: temperature_service                       # C identifier prefix
  uuid: "00001234-0000-1000-8000-00805f9b34fb"    # 128-bit service UUID

characteristics:
  temperature:                                    # Characteristic name
    uuid: "00001235-0000-1000-8000-00805f9b34fb"
    properties: [read, notify]                    # BLE operations allowed
    permissions: [read]                           # Security requirements
    payload:                                      # Data layout
      value:
        type: int16                               # Little-endian by default
        unit: celsius_x100                        # Documentation hint
      flags:
        type: uint8
        bits:                                     # Generates bitmask macros
          0: valid
          1: overflow

  config:
    uuid: "00001236-0000-1000-8000-00805f9b34fb"
    properties: [read, write]
    permissions: [read, write]
    payload:
      interval_ms: uint16                         # Short syntax: just type
      enabled: bool
```

### 3. Validate Schema

Check for errors without generating anything:

```bash
gattc check
```

Validates UUID format, C identifier names, property/permission consistency, bitfield ranges, overlapping bitfields, and field uniqueness. Exit code 0 means valid.

### 4. Generate Code

```bash
# Using gattc.yaml config (schemas and output defined there)
gattc compile

# Or specify schema and output directly
gattc compile gattc/temperature_service.yaml -o src/ble/generated/
```

Generates `temperature_service.h` and `temperature_service.c`.

### 5. Generate Documentation

```bash
# Standalone HTML docs
gattc docs -o docs/ble/

# Or generate docs alongside C code
gattc compile --docs
```

Generates an HTML page per service with characteristic tables, payload layouts, bitfield definitions, and value descriptions.

## Using Generated Code

### Generated Structs

```c
typedef struct {
    int16_t value;
    uint8_t flags;
} __packed temperature_service_temperature_t;
```

### Bitfield Macros

```c
#define TEMPERATURE_SERVICE_TEMPERATURE_FLAGS_VALID    (1 << 0)
#define TEMPERATURE_SERVICE_TEMPERATURE_FLAGS_OVERFLOW (1 << 1)
```

### Pack (send data)

```c
ssize_t temperature_read_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                            void *buf, uint16_t len, uint16_t offset)
{
    temperature_service_temperature_t payload;
    temperature_service_temperature_pack(&payload, current_temp, flags);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &payload, sizeof(payload));
}
```

### Unpack (receive data)

```c
ssize_t config_write_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                        const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    uint16_t interval;
    bool enabled;
    temperature_service_config_unpack(buf, &interval, &enabled);
    // Use values...
    return len;
}
```

### Write Validation

```c
ssize_t config_write_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                        const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    if (!TEMPERATURE_SERVICE_CONFIG_WRITE_VALID(len, offset)) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }
    // ...
}
```

### Notify

```c
void send_notification(int16_t temp, uint8_t flags)
{
    temperature_service_temperature_t payload;
    temperature_service_temperature_pack(&payload, temp, flags);
    bt_gatt_notify(NULL, &temperature_service_svc.attrs[1], &payload, sizeof(payload));
}
```

### CCC Callback

Generated for characteristics with `notify` or `indicate`:

```c
void temperature_service_temperature_ccc_changed(const struct bt_gatt_attr *attr,
                                                  uint16_t value)
{
    bool subscribed = (value == BT_GATT_CCC_NOTIFY);
    // Start/stop notifications...
}
```

## Schema Features

### Directional Payloads

Characteristics can have different payloads per direction:

```yaml
device_command:
  uuid: "..."
  properties: [read, write, notify]
  permissions: [read, write]

  write_payload:         # What client sends TO device
    command: uint8
    parameter: uint16

  read_payload:          # What device returns on read
    last_command: uint8
    status: uint8

  notify_payload:        # What device sends via notification
    event_type: uint8
    event_data: uint32
```

If `payload` is defined instead, it applies to all directions.

### Repeated Structs

Variable-length payloads with repeated elements:

```yaml
sensor_data:
  uuid: "..."
  properties: [read, notify]
  permissions: [read]
  payload:
    packet_count: uint8
    timestamp: uint32
    samples[]:              # Flexible array of structs
      x: int16
      y: int16
      z: int16
```

Generates a nested struct, `pack_item()`/`unpack_item()` functions, and an `items_per_mtu()` helper.

### Big-Endian Fields

Append `_be` to any multi-byte type:

```yaml
payload:
  network_order_value: uint32_be
  local_value: uint16           # Little-endian (default for BLE)
```

Pack/unpack functions handle byte-swapping automatically.

### Field Metadata

Fields support documentation hints that appear in generated HTML docs:

```yaml
temperature:
  type: int16
  unit: celsius_x100               # Unit hint
  values: [-4000, 8500]            # Valid range
  description: "Temperature * 100" # Human-readable note
```

Values can also be named enumerations:

```yaml
status:
  type: uint8
  values:
    0: "success"
    1: "error"
    0xff: "unknown"
```

See [Schema Specification](schema.md) for the full type system and syntax.

## Release Tracking

gattc tracks schema changes across releases using snapshots and changelogs.

### Recording a Release

After modifying a schema, record the change:

```bash
gattc release -m "Add humidity field for v2.1 hardware"
```

This:
1. Compares the current schema against the stored snapshot
2. Detects structural changes (added/removed/modified characteristics, fields, properties)
3. Records a changelog entry with your message and the detected changes
4. Updates the snapshot to the current state
5. Regenerates HTML documentation

### Change Detection During Compile

When snapshots exist, `gattc compile` automatically compares against them and shows what changed in the CLI output. This is informational only — it does not update snapshots or changelog.

Use `--no-diff` to skip change detection.

### Unreleased Changes in Documentation

If you run `gattc compile --docs` or `gattc docs` after modifying a schema but before running `gattc release`, the generated HTML shows an **"UNRELEASED"** banner at the top, warning that the documentation reflects changes not yet recorded.

Running `gattc release` clears the banner and adds change highlighting (green for added, red for removed) to the documentation.

### Editing the Changelog Manually

The changelog is stored as plain JSON at `gattc/snapshots/<service_name>.changelog.json`. You can edit it directly — fix a typo in a release message, add context to an entry, or remove an incorrect record. The format is an array of entries (oldest first):

```json
[
  {
    "timestamp": "2025-03-15 14:30",
    "revision": 1,
    "message": "Initial release",
    "characteristics": {
      "added": ["temperature", "config"]
    }
  }
]
```

Changes you make to the changelog are picked up by `gattc docs` and appear in the generated HTML.

### Reverting a Release

```bash
gattc release --revert
```

Undoes the last release: restores the previous snapshot and removes the last changelog entry. Supports one level of undo.

## Project Configuration

`gattc.yaml` controls schema discovery and output paths:

```yaml
schemas:
  - gattc/                          # Scan directory for .yaml files

output:
  zephyr:
    header: src/ble/generated/      # .h files
    source: src/ble/generated/      # .c files (defaults to header path)
    per_service: true               # One file pair per service (default)

  docs:
    path: docs/ble/
    per_service: true

# Optional: per-service output overrides
services:
  sensor_service:
    output:
      zephyr:
        header: src/sensors/include/
        source: src/sensors/src/
```

See [Configuration Reference](config.md) for all options.

## Build Integration

### Makefile

```makefile
.PHONY: ble-generate

ble-generate:
	gattc compile

build: ble-generate
	west build -b nrf52840dk_nrf52840
```

### CI Check

```bash
# Fail if generated files are stale
gattc compile
git diff --exit-code src/generated/ || \
    (echo "Generated files out of sync" && exit 1)
```

## Reference

| Document | Description |
|----------|-------------|
| [Schema Specification](schema.md) | Full type system, field syntax, validation rules |
| [Configuration](config.md) | `gattc.yaml` reference |
| [CLI Reference](cli.md) | All commands, options, and exit codes |
| [Code Generation](codegen.md) | Generated code details, resource costs, endianness handling |
| [Documentation Generation](docgen.md) | HTML output modes and customization |
| [Architecture](architecture.md) | System design and data flow |
| [Development](development.md) | Build, test, contribute |

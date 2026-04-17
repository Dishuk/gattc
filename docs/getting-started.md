# Getting Started

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [1. Initialize Project](#1-initialize-project)
  - [2. Define a Service](#2-define-a-service)
  - [3. Validate Schema](#3-validate-schema)
  - [4. Generate Code](#4-generate-code)
  - [5. Generate Documentation](#5-generate-documentation)
- [Using Generated Code](#using-generated-code)
- [Schema Features](#schema-features)
- [Release Tracking](#release-tracking)
- [Project Configuration](#project-configuration)
- [Build Integration](#build-integration)
- [Reference](#reference)

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
# Standalone Markdown docs (default)
gattc docs -o docs/ble/

# HTML instead
gattc docs -o docs/ble/ -f html

# Or generate docs alongside C code
gattc compile --docs
```

Generates one file per service with characteristic tables, payload layouts, bitfield definitions, and value descriptions. Markdown is the default (git-friendly, renders on GitHub); set `output.docs.format: html` in `gattc.yaml` for a styled standalone HTML page.

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
    bt_gatt_notify(NULL, &temperature_service_svc.attrs[TEMPERATURE_SERVICE_TEMPERATURE_VAL_ATTR_IDX],
                   &payload, sizeof(payload));
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

Fields support documentation hints that appear in generated docs:

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
3. Records a changelog entry with the provided message and the detected changes
4. Updates the snapshot to the current state
5. Regenerates documentation in the configured format

### Change Detection During Compile

When snapshots exist, `gattc compile` automatically compares against them and shows what changed in the CLI output. This is informational only — it does not update snapshots or changelog.

Use `--no-diff` to skip change detection.

### Unreleased Changes in Documentation

Running `gattc compile --docs` or `gattc docs` after modifying a schema but before running `gattc release` causes the generated document to show an **"UNRELEASED"** banner at the top, warning that the documentation reflects changes not yet recorded.

Running `gattc release` clears the banner and adds change highlighting (green for added, red for removed) to the documentation.

### Writing a Release Message

Omit `-m` and `gattc release` opens `$EDITOR` — prefilled with the detected
structural changes as comments — to allow a longer message, much like
`git commit`. Saving and closing records the release; exiting with an empty message aborts it.

### Editing the Changelog

Each release is stored as a markdown file with YAML frontmatter at
`gattc/changelog/<service_name>/NNN.md` (e.g. `001.md`, `002.md`). Example:

```markdown
---
revision: 1
timestamp: 2025-03-15 14:30
characteristics:
  added: [temperature, config]
---
Initial release.
```

The message is the body; the frontmatter captures the detected changes. To edit
the latest entry interactively (omit the revision — it defaults to latest):

```bash
gattc changelog edit
```

Or open a specific revision by number:

```bash
gattc changelog edit 2
```

The same default applies to `gattc changelog path` — omit the revision to get
the path to the latest entry.

The `.md` changelog files can also be edited directly. Changes are picked up by `gattc docs` and appear in the generated documentation.

Use `gattc changelog` (or `gattc changelog list`) to see all revisions.

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
| [Documentation Generation](docgen.md) | Markdown/HTML output modes and customization |
| [Architecture](architecture.md) | System design and data flow |
| [Development](development.md) | Build, test, contribute |

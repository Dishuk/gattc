# Schema Specification

- [Top-Level Structure](#top-level-structure)
- [Service Definition](#service-definition)
- [Characteristic Definition](#characteristic-definition)
  - [Properties](#properties)
  - [Permissions](#permissions)
- [Data Types](#data-types)
  - [Standard Types](#standard-types)
  - [Big-Endian Types](#big-endian-types)
  - [Raw Bytes](#raw-bytes)
  - [Arrays](#arrays)
- [Payload Definition](#payload-definition)
  - [Field Syntax](#field-syntax)
  - [Auto-Computed Offsets](#auto-computed-offsets)
  - [Bitfields](#bitfields)
  - [Field Metadata](#field-metadata)
  - [Values](#values)
  - [Units](#units)
- [Directional Payloads](#directional-payloads)
- [Repeated Structs](#repeated-structs)
- [Variable-Length Payloads](#variable-length-payloads)
- [Validation Rules](#validation-rules)

## Top-Level Structure

```yaml
schema_version: "1.0"

service:
  name: string              # Required: Service identifier (snake_case)
  uuid: string              # Required: 128-bit UUID
  description: string       # Optional: Human-readable description

characteristics:
  <name>:                   # Characteristic identifier (snake_case)
    uuid: string
    properties: [...]
    permissions: [...]
    payload:
      ...
```

## Service Definition

```yaml
service:
  name: my_service
  uuid: "12345678-1234-1234-1234-123456789abc"
  description: "My custom BLE service"
```

### UUID Format

UUIDs must be 128-bit in standard format:

```
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Characteristic Definition

```yaml
characteristics:
  my_characteristic:
    uuid: "12345678-..."           # Required
    description: "..."              # Optional
    properties: [read, write]       # Required
    permissions: [read_authen]      # Required
    payload:                        # Required
      ...
```

### Properties

| Property | Description |
|----------|-------------|
| `read` | Characteristic can be read |
| `write` | Characteristic can be written (with response) |
| `write_without_response` | Characteristic can be written (no response) |
| `notify` | Characteristic supports notifications (auto-generates CCC descriptor) |
| `indicate` | Characteristic supports indications (auto-generates CCC descriptor) |

> **Note:** Characteristics with `notify` or `indicate` automatically get a CCC (Client Characteristic Configuration) descriptor generated. This allows clients to subscribe/unsubscribe to notifications.

### Permissions

| Permission | Description |
|------------|-------------|
| `read` | Read allowed without authentication |
| `read_authen` | Read requires authentication |
| `read_encrypt` | Read requires encryption |
| `write` | Write allowed without authentication |
| `write_authen` | Write requires authentication |
| `write_encrypt` | Write requires encryption |

## Data Types

### Standard Types

| Type | Size | Endianness | Description |
|------|------|------------|-------------|
| `uint8` | 1 | none | Unsigned 8-bit |
| `int8` | 1 | none | Signed 8-bit |
| `uint16` | 2 | little | Unsigned 16-bit |
| `int16` | 2 | little | Signed 16-bit |
| `uint32` | 4 | little | Unsigned 32-bit |
| `int32` | 4 | little | Signed 32-bit |
| `uint64` | 8 | little | Unsigned 64-bit |
| `int64` | 8 | little | Signed 64-bit |
| `bool` | 1 | none | Boolean (0 or 1) |

### Big-Endian Types

Append `_be` suffix for big-endian:

| Type | Size | Description |
|------|------|-------------|
| `uint16_be` | 2 | Unsigned 16-bit, big-endian |
| `int16_be` | 2 | Signed 16-bit, big-endian |
| `uint32_be` | 4 | Unsigned 32-bit, big-endian |
| `int32_be` | 4 | Signed 32-bit, big-endian |
| `uint64_be` | 8 | Unsigned 64-bit, big-endian |
| `int64_be` | 8 | Signed 64-bit, big-endian |

### Raw Bytes

| Type | Size | Description |
|------|------|-------------|
| `bytes[N]` | N | Fixed-size byte array (e.g., `bytes[6]` for MAC address) |

### Arrays

| Syntax | Description |
|--------|-------------|
| `uint16[10]` | Fixed array of 10 uint16 elements |
| `uint8[]` | Flexible array (MTU-fill, must be last field) |

## Payload Definition

### Field Syntax

Fields are defined as key-value pairs:

```yaml
payload:
  # Simple: just type
  field_name: uint16

  # With metadata
  field_name:
    type: uint16
    unit: celsius
    values: [0, 100]
    description: "Temperature value"

  # Explicit offset (for gaps/reserved space)
  field_name:
    type: uint8
    offset: 10
```

### Auto-Computed Offsets

Offsets are computed sequentially. Only specify `offset` for gaps:

```yaml
payload:
  version: uint8          # offset 0
  flags: uint8            # offset 1
  reserved:
    type: bytes[6]
    offset: 2             # explicit (though sequential here)
  future_field:
    type: uint16
    offset: 16            # gap: bytes 8-15 reserved
```

### Bitfields

Pack flags into a single integer:

```yaml
payload:
  flags:
    type: uint8
    bits:
      0: enabled          # Single bit
      1: error
      2-4: mode           # Multi-bit field (bits 2,3,4)
      5-7: reserved
```

### Field Metadata

| Property | Description |
|----------|-------------|
| `type` | Data type (required if expanded syntax) |
| `offset` | Byte offset, auto-computed if omitted |
| `unit` | Unit hint for documentation |
| `values` | Valid values (see below) |
| `description` | Human-readable description |
| `bits` | Bitfield definition |

### Values

The `values` field supports three formats:

**Range** - valid numeric range:

```yaml
temperature:
  type: int16
  values: [-4000, 8500]    # min, max
```

**Named values** - enumeration mapping:

```yaml
status:
  type: uint8
  values:
    0: "success"
    1: "error"
    2: "pending"
    0xff: "unknown"
```

**Text description** - free-form:

```yaml
device_id:
  type: bytes[6]
  values: "MAC address in little-endian"
```

### Units

Units are documentation hints:

```yaml
unit: celsius          # Temperature
unit: celsius_x100     # Temperature * 100 (fixed-point)
unit: percent          # Percentage 0-100
unit: seconds          # Time
unit: milliseconds
unit: milli_g          # Acceleration
unit: millivolts       # Voltage
```

## Directional Payloads

Characteristics can have different payloads per direction:

```yaml
characteristics:
  device_command:
    uuid: "..."
    properties: [read, write, notify]

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

If `payload` is defined, it's used for all directions (symmetrical).

## Repeated Structs

For variable-length payloads with repeated elements:

```yaml
payload:
  packet_count: uint8
  timestamp: uint32
  samples[]:              # Flexible array of structs
    x: int16
    y: int16
    z: int16
```

This generates:
- Nested struct for the repeated element
- `pack_item()` / `unpack_item()` functions
- `items_per_mtu()` helper

## Variable-Length Payloads

```yaml
payload:
  _mode: variable
  _min_size: 1
  _max_size: 20
  data: uint8[]
```

## Validation Rules

1. **UUID Format**: Must be valid 128-bit UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
2. **C Identifiers**: Service names, characteristic names, field names, and bit names must be valid C identifiers (start with letter or underscore, contain only `[A-Za-z0-9_]`) and must not be C reserved keywords
3. **No Offset Overlap**: Fields cannot overlap in memory
4. **No Offset Gaps**: Warning if there are unintentional gaps
5. **Unique Names**: Field names must be unique within payload
6. **Characteristic Names**: Must be unique within service
7. **Unique UUIDs**: Characteristic UUIDs must be unique within service
8. **Property/Permission Consistency**: `read` property requires a read permission, `write`/`write_without_response` properties require a write permission
9. **Bitfield Range**: Bit indices must not exceed the field's type size (e.g., max bit 7 for `uint8`, max bit 15 for `uint16`), and range start must not exceed end

# Getting Started

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
gatt/
└── echo_service.yaml   # Example schema
```

### 2. Define a Service

Create `gatt/temperature_service.yaml`:

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

### 3. Generate Code

```bash
# Using gattc.yaml config (schemas and output defined there)
gattc compile

# Or specify schema and output directly
gattc compile gatt/temperature_service.yaml -o src/ble/generated/
```

Generates `temperature_service.h` and `temperature_service.c`.

## Using Generated Code

### Generated Structs

```c
typedef struct __attribute__((packed)) {
    int16_t value;
    uint8_t flags;
} temperature_service_temperature_t;
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

## Next Steps

- [Configuration](config.md) - Project configuration (`gattc.yaml`)
- [Schema Specification](schema.md) - YAML format reference
- [Code Generation](codegen.md) - Generated code details
- [CLI Reference](cli.md) - All commands

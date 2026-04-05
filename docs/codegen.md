# Code Generation

## Philosophy

**Provide tools, not restrictions.**

- Developer CAN use generated utilities → guaranteed schema sync
- Developer CAN ignore them → full freedom, manual responsibility
- No forced patterns, no wrapper requirements

## What Gets Generated

From this schema:

```yaml
shock_threshold:
  uuid: "cb8dfa98-..."
  properties: [read, write]
  permissions: [read, write]
  payload:
    threshold_mg:
      type: uint16
      unit: milli_g
```

### 1. Struct (buffer layout)

```c
typedef struct __attribute__((packed)) {
    uint16_t threshold_mg;  /* unit: milli_g */
} my_service_shock_threshold_t;
```

### 2. Compile-time validation

```c
#define MY_SERVICE_SHOCK_THRESHOLD_SIZE 2

_Static_assert(sizeof(my_service_shock_threshold_t) == MY_SERVICE_SHOCK_THRESHOLD_SIZE,
               "my_service_shock_threshold size mismatch");
```

### 3. Pack function (values → buffer)

For sending data (read callback, notify):

```c
static inline void my_service_shock_threshold_pack(
    my_service_shock_threshold_t *buf,
    uint16_t threshold_mg)
{
    buf->threshold_mg = sys_cpu_to_le16(threshold_mg);
}
```

### 4. Unpack function (buffer → values)

For receiving data (write callback):

```c
static inline void my_service_shock_threshold_unpack(
    const my_service_shock_threshold_t *buf,
    uint16_t *threshold_mg)
{
    *threshold_mg = sys_le16_to_cpu(buf->threshold_mg);
}
```

## Developer Usage

### Sending data (read/notify)

```c
ssize_t shock_thresh_read_cb(struct bt_conn *conn, ...) {
    my_service_shock_threshold_t buf;
    my_service_shock_threshold_pack(&buf, get_threshold());
    return bt_gatt_attr_read(conn, attr, buf_out, len, offset, &buf, sizeof(buf));
}
```

### Receiving data (write)

```c
ssize_t shock_thresh_write_cb(struct bt_conn *conn, ..., const void *buf, ...) {
    uint16_t value;
    my_service_shock_threshold_unpack(buf, &value);
    set_threshold(value);
    return len;
}
```

### Or ignore utilities entirely

```c
// Developer can still do manual packing
uint16_t value = sys_le16_to_cpu(*(uint16_t*)buf);
```

## How Drift is Caught

**Scenario: Schema adds a field**

```yaml
payload:
  threshold_mg: uint16
  sensitivity: uint8      # NEW
```

**Generated pack() changes:**

```c
void my_service_shock_threshold_pack(
    my_service_shock_threshold_t *buf,
    uint16_t threshold_mg,
    uint8_t sensitivity)   // NEW PARAMETER
```

**Developer's old code:**

```c
my_service_shock_threshold_pack(&buf, get_threshold());
// ERROR: too few arguments
```

**Compiler catches the drift.**

## Variable-Length Payloads

For payloads with repeated elements:

```yaml
sensor_data:
  payload:
    packet_count: uint8
    timestamp: uint32
    samples[]:
      x: int16
      y: int16
      z: int16
```

Generates:

```c
// Nested struct for repeated element
typedef struct __attribute__((packed)) {
    int16_t x;
    int16_t y;
    int16_t z;
} my_service_sensor_data_samples_t;

// Main struct with flexible array
typedef struct __attribute__((packed)) {
    uint8_t packet_count;
    uint32_t timestamp;
    my_service_sensor_data_samples_t samples[];
} my_service_sensor_data_t;

// Pack/unpack for individual items
static inline void my_service_sensor_data_pack_item(
    my_service_sensor_data_samples_t *item,
    int16_t x, int16_t y, int16_t z);

// MTU helper
static inline size_t my_service_sensor_data_items_per_mtu(uint16_t mtu);
```

## Resource Considerations

Embedded systems have limited ROM/RAM.

### Cost Analysis

| Generated Code | ROM | RAM | Notes |
|----------------|-----|-----|-------|
| Struct typedef | 0 | 0 | Type only |
| `_Static_assert` | 0 | 0 | Compile-time only |
| Inline pack/unpack | ~10-50 bytes per call | Stack only | Inlined at use |

### Endianness Reality

On little-endian ARM (nRF52, STM32, ESP32):
- `sys_cpu_to_le16()` compiles to nothing
- Pack function is often just a store instruction

### Bitfield Macros

For fields with `bits` defined:

```c
/* status_flags bit definitions */
#define MY_SERVICE_STATUS_FLAGS_ENABLED (1 << 0)
#define MY_SERVICE_STATUS_FLAGS_ERROR (1 << 1)
#define MY_SERVICE_STATUS_FLAGS_MODE_MASK 0x1C
#define MY_SERVICE_STATUS_FLAGS_MODE_SHIFT 2
```

Usage:
```c
uint8_t flags = buf.status_flags;
bool enabled = flags & MY_SERVICE_STATUS_FLAGS_ENABLED;
uint8_t mode = (flags & MY_SERVICE_STATUS_FLAGS_MODE_MASK) >> MY_SERVICE_STATUS_FLAGS_MODE_SHIFT;
```

## Notify/Indicate Support

Characteristics with `notify` or `indicate` properties automatically get a CCC (Client Characteristic Configuration) descriptor generated.

### What Gets Generated

For a characteristic with notify:

```yaml
sensor_data:
  uuid: "..."
  properties: [read, notify]
  permissions: [read]
  payload:
    value: uint16
```

**In `.c` file:**
```c
/* sensor_data */
BT_GATT_CHARACTERISTIC(MY_SERVICE_SENSOR_DATA_UUID,
    BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
    BT_GATT_PERM_READ,
    my_service_sensor_data_read_cb, NULL, NULL),
BT_GATT_CCC(my_service_sensor_data_ccc_changed,
    BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
```

**In `.h` file:**
```c
void my_service_sensor_data_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value);
```

### CCC Callback Implementation

The CCC callback is called when a client subscribes or unsubscribes:

```c
void my_service_sensor_data_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    bool notify_enabled = (value == BT_GATT_CCC_NOTIFY);

    if (notify_enabled) {
        // Client subscribed - start sending notifications
        start_sensor_sampling();
    } else {
        // Client unsubscribed - stop sending
        stop_sensor_sampling();
    }
}
```

### Sending Notifications

Use `bt_gatt_notify()` to send data to subscribed clients:

```c
void send_sensor_update(uint16_t value)
{
    my_service_sensor_data_t buf;
    my_service_sensor_data_pack(&buf, value);

    bt_gatt_notify(NULL, &my_service_svc.attrs[SENSOR_DATA_ATTR_INDEX],
                   &buf, sizeof(buf));
}
```

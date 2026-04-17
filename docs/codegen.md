# Code Generation

- [What Gets Generated](#what-gets-generated)
- [Usage](#usage)
- [How Drift is Caught](#how-drift-is-caught)
- [Variable-Length Payloads](#variable-length-payloads)
- [Resource Considerations](#resource-considerations)
- [Attribute Table Access](#attribute-table-access)
- [Notify/Indicate Support](#notifyindicate-support)

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
typedef struct {
    uint16_t threshold_mg;  /* unit: milli_g */
} __packed my_service_shock_threshold_t;
```

### 2. Compile-time validation

```c
#define MY_SERVICE_SHOCK_THRESHOLD_SIZE 2

_Static_assert(sizeof(my_service_shock_threshold_t) == MY_SERVICE_SHOCK_THRESHOLD_SIZE,
               "my_service_shock_threshold size mismatch");
```

### 3. Pack function (values -> buffer)

For sending data (read callback, notify):

```c
static inline void my_service_shock_threshold_pack(
    my_service_shock_threshold_t *buf,
    uint16_t threshold_mg)
{
    buf->threshold_mg = sys_cpu_to_le16(threshold_mg);
}
```

### 4. Unpack function (buffer -> values)

For receiving data (write callback):

```c
static inline void my_service_shock_threshold_unpack(
    const my_service_shock_threshold_t *buf,
    uint16_t *threshold_mg)
{
    *threshold_mg = sys_le16_to_cpu(buf->threshold_mg);
}
```

## Usage

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
// Manual packing is still possible
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

**Existing call site:**

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
typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} __packed my_service_sensor_data_samples_t;

// Main struct with flexible array
typedef struct {
    uint8_t packet_count;
    uint32_t timestamp;
    my_service_sensor_data_samples_t samples[];
} __packed my_service_sensor_data_t;

// Pack/unpack for individual items
static inline void my_service_sensor_data_pack_item(
    my_service_sensor_data_samples_t *item,
    int16_t x, int16_t y, int16_t z);

// MTU helper
static inline size_t my_service_sensor_data_items_per_mtu(uint16_t mtu);
```

## Resource Considerations

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
#define MY_SERVICE_STATUS_FLAGS_ENABLED (1 << 0)  /* bit 0 */
#define MY_SERVICE_STATUS_FLAGS_ERROR (1 << 1)  /* bit 1 */
/* bits 2-4 (width 3) */
#define MY_SERVICE_STATUS_FLAGS_MODE_MASK 0x1C
#define MY_SERVICE_STATUS_FLAGS_MODE_SHIFT 2
```

Usage:
```c
uint8_t flags = buf.status_flags;
bool enabled = flags & MY_SERVICE_STATUS_FLAGS_ENABLED;
uint8_t mode = (flags & MY_SERVICE_STATUS_FLAGS_MODE_MASK) >> MY_SERVICE_STATUS_FLAGS_MODE_SHIFT;
```

### Write Validation Macros

For each payload, a validation macro is generated to help validate write callback parameters:

```c
/* Validate write parameters for fixed-size payload */
#define MY_SERVICE_SHOCK_THRESHOLD_WRITE_VALID(len, offset) \
    ((offset) == 0 && (len) >= MY_SERVICE_SHOCK_THRESHOLD_SIZE)
```

Usage in write callback:
```c
ssize_t shock_thresh_write_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                               const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    if (!MY_SERVICE_SHOCK_THRESHOLD_WRITE_VALID(len, offset)) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint16_t value;
    my_service_shock_threshold_unpack(buf, &value);
    set_threshold(value);
    return len;
}
```

## Attribute Table Access

The generated header also exports symbols for reaching into the service's GATT attribute table from other translation units.

### Service extern

For each service, the `.c` defines the service handle and the `.h` declares it `extern`:

```c
extern const struct bt_gatt_service_static my_service_svc;
```

This lets application code reference the service (e.g. to pass attribute pointers to Zephyr APIs) without having to include the generated source.

### Value-attribute index macros

For every characteristic, the header defines a macro giving the index of that characteristic's value attribute within `my_service_svc.attrs[]`:

```c
#define MY_SERVICE_SENSOR_DATA_VAL_ATTR_IDX 2
```

Use it wherever a `struct bt_gatt_attr *` for the characteristic is needed — for example with `bt_gatt_notify()`, `bt_gatt_indicate()`, or attribute lookups — instead of hand-counting or hard-coding an index. Adding or removing characteristics (or their CCCs) updates the macro automatically, so callers stay in sync with the table layout.

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

### CCC Permission Inheritance

CCC descriptor permissions are automatically derived from the characteristic's permissions:

| Characteristic Permission | CCC Permissions |
|--------------------------|-----------------|
| `read` or `write` | `BT_GATT_PERM_READ \| BT_GATT_PERM_WRITE` |
| `read_encrypt` or `write_encrypt` | `BT_GATT_PERM_READ_ENCRYPT \| BT_GATT_PERM_WRITE_ENCRYPT` |
| `read_authen` or `write_authen` | `BT_GATT_PERM_READ_AUTHEN \| BT_GATT_PERM_WRITE_AUTHEN` |

Example with authentication:

```yaml
secure_sensor:
  properties: [read, notify]
  permissions: [read_authen]
```

Generates:
```c
BT_GATT_CCC(my_service_secure_sensor_ccc_changed,
    BT_GATT_PERM_READ_AUTHEN | BT_GATT_PERM_WRITE_AUTHEN),
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

    bt_gatt_notify(NULL, &my_service_svc.attrs[MY_SERVICE_SENSOR_DATA_VAL_ATTR_IDX],
                   &buf, sizeof(buf));
}
```

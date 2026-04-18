## Contents
- [1. Device Telemetry](#svc-device_telemetry)
  - [Changelog](#changelog-device_telemetry)
  - [1.1 Battery Status](#char-device_telemetry-battery_status)
  - [1.2 Firmware Info](#char-device_telemetry-firmware_info)
  - [1.3 Uptime](#char-device_telemetry-uptime)
  - [1.4 Thermometer](#char-device_telemetry-thermometer)
  - [1.5 Accelerometer](#char-device_telemetry-accelerometer)
- [2. Heart Rate Service](#svc-heart_rate_service)
  - [Changelog](#changelog-heart_rate_service)
  - [2.1 Hr Measurement](#char-heart_rate_service-hr_measurement)
  - [2.2 Body Sensor Location](#char-heart_rate_service-body_sensor_location)
  - [2.3 Heart Rate Control Point](#char-heart_rate_service-heart_rate_control_point)

<a id="svc-device_telemetry"></a>
# 1. Device Telemetry

- **UUID:** `e5a1b2c3-0000-4000-8000-abc000000001`
- **Version:** 1.0

Device health and identification — custom service

<a id="changelog-device_telemetry"></a>
## Changelog

### Revision 1 — 2026-04-18

Initial schema release

### Revision 2 — 2026-04-18

Expose v2 hardware thermal monitoring: add thermometer characteristic and thermal_throttle status bit

#### Modified service
| Change | Detail |
|--------|--------|
| Characteristic added | `1.4 thermometer` |

#### Modified `1.1 battery_status`
| Change | Detail |
|--------|--------|
| Field changed | `status` (bitfield changed) |

### Revision 3 — 2026-04-18

Add batched 3-axis accelerometer telemetry for motion analysis

#### Modified service
| Change | Detail |
|--------|--------|
| Characteristic added | `1.5 accelerometer` |


## Characteristics

<a id="char-device_telemetry-battery_status"></a>
### 1.1 Battery Status

- **UUID:** `e5a1b2c3-0000-4000-8000-abc000000002`
- **Properties:** `read`, `notify`
- **Permissions:** `read`

Battery level and charging state


#### Payload (2 bytes)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `level` | 0 | 1 | `uint8` | Remaining charge | 0..100 | percent |
| `status` | 1 | 1 | `uint8` | - | [Table 1.1.1](#table-1-1-1) | - |


<a id="table-1-1-1"></a>
#### Table 1.1.1 — `status` bitfield
| Range | Name |
|-------|------|
| `[0]` | `charging` |
| `[1]` | `low_battery` |
| `[2]` | `critical` |
| `[3]` | `fault` |
| `[4]` | `thermal_throttle` |
| `[5:7]` | `reserved` |


---

<a id="char-device_telemetry-firmware_info"></a>
### 1.2 Firmware Info

- **UUID:** `e5a1b2c3-0000-4000-8000-abc000000003`
- **Properties:** `read`
- **Permissions:** `read`

Firmware and hardware identification


#### Payload (10 bytes)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `fw_major` | 0 | 1 | `uint8` | - | - | - |
| `fw_minor` | 1 | 1 | `uint8` | - | - | - |
| `fw_patch` | 2 | 1 | `uint8` | - | - | - |
| `hw_revision` | 3 | 1 | `uint8` | - | - | - |
| `serial_number` | 4 | 6 | `bytes[6]` | - | - | - |


---

<a id="char-device_telemetry-uptime"></a>
### 1.3 Uptime

- **UUID:** `e5a1b2c3-0000-4000-8000-abc000000004`
- **Properties:** `read`, `notify`
- **Permissions:** `read`

Seconds since last boot


#### Payload (4 bytes)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `seconds` | 0 | 4 | `uint32` | - | - | - |


---

<a id="char-device_telemetry-thermometer"></a>
### 1.4 Thermometer

- **UUID:** `e5a1b2c3-0000-4000-8000-abc000000005`
- **Properties:** `read`, `notify`
- **Permissions:** `read`

Internal board temperature (added in v2 hardware)


#### Payload (2 bytes)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `temperature` | 0 | 2 | `int16` | Board temperature, hundredths of a degree Celsius | -4000..12500 | celsius_x100 |


---

<a id="char-device_telemetry-accelerometer"></a>
### 1.5 Accelerometer

- **UUID:** `e5a1b2c3-0000-4000-8000-abc000000006`
- **Properties:** `notify`
- **Permissions:** `read`

Packed 3-axis accelerometer samples for motion analysis


#### Payload (variable length)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `sample_rate_hz` | 0 | 2 | `uint16` | Sampling rate of the enclosed batch | - | hertz |
| `first_sample_timestamp` | 2 | 4 | `uint32` | - | - | - |
| `samples` | 6 | 6*N | `struct[]` | - | [Table 1.5.1](#table-1-5-1) | - |


<a id="table-1-5-1"></a>
#### Table 1.5.1 — `samples` struct layout
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `x` | 0 | 2 | `int16` | - | - | milli_g |
| `y` | 2 | 2 | `int16` | - | - | milli_g |
| `z` | 4 | 2 | `int16` | - | - | milli_g |



---

<a id="svc-heart_rate_service"></a>
# 2. Heart Rate Service

- **UUID:** `0000180d-0000-1000-8000-00805f9b34fb`
- **Version:** 1.0

Bluetooth SIG Heart Rate service (0x180D)

<a id="changelog-heart_rate_service"></a>
## Changelog

### Revision 1 — 2026-04-18

Initial schema release

### Revision 2 — 2026-04-18

Support v2 RR-interval resolution hint and upper-arm sensor placement

#### Modified `2.1 hr_measurement`
| Change | Detail |
|--------|--------|
| Description updated | — |
| Field changed | `flags` (bitfield changed) |

#### Modified `2.2 body_sensor_location`
| Change | Detail |
|--------|--------|
| Field changed | `location` (values changed) |


## Characteristics

<a id="char-heart_rate_service-hr_measurement"></a>
### 2.1 Hr Measurement

- **UUID:** `00002a37-0000-1000-8000-00805f9b34fb`
- **Properties:** `notify`
- **Permissions:** `read`

Heart rate measurement with optional energy, RR-intervals, and v2 RR resolution hint


#### Payload (variable length)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `flags` | 0 | 1 | `uint8` | - | [Table 2.1.1](#table-2-1-1) | - |
| `heart_rate` | 1 | 1 | `uint8` | Instantaneous heart rate | 0..255 | bpm |
| `energy_expended` | 2 | 2 | `uint16` | Cumulative energy since last reset (valid if flag bit 3 set) | - | kilojoules |
| `rr_intervals` | 4 | 2*N | `uint16[]` | - | - | - |


<a id="table-2-1-1"></a>
#### Table 2.1.1 — `flags` bitfield
| Range | Name |
|-------|------|
| `[0]` | `hr_format_16bit` |
| `[1]` | `sensor_contact_detected` |
| `[2]` | `sensor_contact_supported` |
| `[3]` | `energy_expended_present` |
| `[4]` | `rr_interval_present` |
| `[5]` | `rr_resolution_1ms` |
| `[6:7]` | `reserved` |


---

<a id="char-heart_rate_service-body_sensor_location"></a>
### 2.2 Body Sensor Location

- **UUID:** `00002a38-0000-1000-8000-00805f9b34fb`
- **Properties:** `read`
- **Permissions:** `read`

Where on the body the sensor is worn


#### Payload (1 byte)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `location` | 0 | 1 | `uint8` | - | [Table 2.2.1](#table-2-2-1) | - |


<a id="table-2-2-1"></a>
#### Table 2.2.1 — `location` enum values
| Value | Name |
|-------|------|
| `0` | `other` |
| `1` | `chest` |
| `2` | `wrist` |
| `3` | `finger` |
| `4` | `hand` |
| `5` | `ear_lobe` |
| `6` | `foot` |
| `7` | `upper_arm` |


---

<a id="char-heart_rate_service-heart_rate_control_point"></a>
### 2.3 Heart Rate Control Point

- **UUID:** `00002a39-0000-1000-8000-00805f9b34fb`
- **Properties:** `write`
- **Permissions:** `write`

Write commands to control the HR service


#### Payload (1 byte)
| Name | Offset | Length | Type | Description | Value | Units |
|------|--------|--------|------|-------------|-------|-------|
| `command` | 0 | 1 | `uint8` | - | [Table 2.3.1](#table-2-3-1) | - |


<a id="table-2-3-1"></a>
#### Table 2.3.1 — `command` enum values
| Value | Name |
|-------|------|
| `1` | `reset_energy_expended` |



---

_Generated by gattc._

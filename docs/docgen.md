# Documentation Generation

Generate HTML documentation from GATT schemas for sharing with mobile teams, creating ICDs, or internal reference.

## Quick Start

```bash
# Single schema
gattc docs services/sensor_service.yaml -o docs/

# All schemas in project
gattc docs -o docs/ble/
```

## CLI Reference

```
gattc docs [OPTIONS] [SCHEMA]

Arguments:
  SCHEMA    Path to schema file (optional if gattc.yaml exists)

Options:
  -o, --output PATH    Output directory or file path
  --combined           Merge all services into single HTML file
  --per-service        Generate separate HTML file per service (default)
```

## Configuration

In `gattc.yaml`:

```yaml
output:
  docs:
    path: "docs/ble/"           # Output directory
    per_service: true           # true = one .html per service (default)
                                # false = all services in gatt_services.html
```

## Output Modes

### Per-Service (default)

Each schema produces its own HTML file:

```
docs/ble/
├── sensor_service.html
├── device_info.html
└── echo_service.html
```

### Combined

All services merged into one HTML file:

```bash
gattc docs --combined -o docs/ble/
```

Produces: `docs/ble/gatt_services.html`

## Generated Content

The HTML documentation includes:

| Section | Contents |
|---------|----------|
| Service Info | Name, UUID, description |
| Characteristics | Name, UUID, properties, permissions |
| Payload Tables | Field name, type, offset, size, description |
| Bitfield Details | Bit ranges and flag names |
| Named Values | Value-to-name mappings |

## Integration with Compile

Generate docs alongside C code:

```bash
# Using --docs flag
gattc compile --docs

# Or configure in gattc.yaml
output:
  zephyr:
    header: "src/generated/"
    source: "src/generated/"
  docs:
    path: "docs/ble/"
```

Then `gattc compile` generates both C code and HTML docs.

## Schema Features for Documentation

Add descriptions and metadata to improve generated docs:

```yaml
service:
  name: sensor_service
  uuid: "..."
  description: "Environmental sensor data service"  # Shown in header

characteristics:
  temperature:
    uuid: "..."
    description: "Current temperature reading"      # Shown in table
    properties: [read, notify]
    permissions: [read]
    payload:
      value:
        type: int16
        unit: celsius_x100                          # Shown in Unit column
        description: "Temperature * 100"            # Shown in Description
        values: [-4000, 8500]                       # Shown as valid range
      status:
        type: uint8
        values:                                     # Named values table
          0: "ok"
          1: "sensor_error"
          2: "out_of_range"
```

## Example Output

For a characteristic with bitfields:

```yaml
flags:
  type: uint8
  bits:
    0: enabled
    1: error
    2-4: mode
```

The HTML shows:

| Field | Type | Offset | Size | Description |
|-------|------|--------|------|-------------|
| flags | uint8 | 0 | 1 | |

With expanded bitfield table:
| Bits | Name |
|------|------|
| [0] | enabled |
| [1] | error |
| [2:4] | mode |

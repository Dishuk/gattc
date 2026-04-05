# gattc - GATT Compiler

A contract-first tool for BLE development. Define your GATT services once in YAML, generate type-safe code for firmware, and eliminate drift between teams.

## The Problem

BLE development across firmware and mobile is fragmented:

- **Scattered definitions**: UUIDs in `.h` files, byte layout implicit in code, docs separate
- **Silent drift**: Firmware changes payload structure, mobile breaks at runtime
- **Manual sync**: Mobile devs read ICDs and manually implement characteristics

## The Solution

`gattc` generates from a single YAML schema:

- **C headers** for Zephyr (UUIDs, packed structs, pack/unpack functions)

> **Note:** Additional generators (TypeScript, Swift, Markdown docs) are nice-to-have features for future consideration, not requirements. The primary focus is Zephyr code generation.

## Quick Start

```bash
# Install
pip install gattc

# Initialize new project
gattc init

# Edit gatt/echo_service.yaml, then compile
gattc compile

# Or compile a single schema directly
gattc compile services/my_service.yaml -o src/generated/
```

## Example Schema

```yaml
schema_version: "1.0"

service:
  name: sensor_service
  uuid: "12345678-1234-1234-1234-123456789abc"

characteristics:
  temperature:
    uuid: "12345678-1234-1234-1234-123456789001"
    properties: [read, notify]
    permissions: [read]
    payload:
      value:
        type: int16
        unit: celsius_x100
      flags:
        type: uint8
        bits:
          0: valid
          1: overflow
```

## Documentation

See [docs/](docs/) for detailed documentation:

- [Schema Specification](docs/schema.md) - YAML format, data types
- [Architecture](docs/architecture.md) - System design
- [Code Generation](docs/codegen.md) - What gets generated
- [CLI Reference](docs/cli.md) - Command-line usage
- [Development](docs/development.md) - Build, test, contribute

## License

MIT

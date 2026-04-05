# gattc - GATT Compiler

A contract-first tool for BLE development. Define your GATT services once in YAML, generate type-safe code for firmware.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Python](https://www.python.org/) | >= 3.9 | Runtime |
| pip | any | Package installation |

## Features

- **Contract-first** — Single YAML schema as source of truth
- **Type-safe C code** — Packed structs with compile-time size validation
- **Endian-correct** — Automatic byte order handling for BLE
- **Drift detection** — Schema changes break compilation, not runtime

## Quick Start

```bash
# Install
pip install git+https://github.com/polesskiy-dev/gattc.git

# Initialize new project (creates boilerplate echo_service.yaml)
gattc init

# Edit the generated schema, then compile
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

## Project Structure

```
gattc/
├── src/gattc/
│   ├── cli.py              # CLI entry point
│   ├── schema.py           # YAML parsing and validation
│   ├── config.py           # Project configuration
│   └── generators/
│       ├── zephyr.py       # C code generator
│       └── docs.py         # HTML documentation generator
├── tests/
└── docs/
```

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Step-by-step tutorial with Zephyr integration |
| [Configuration](docs/config.md) | Project configuration (`gattc.yaml`) |
| [Schema Specification](docs/schema.md) | YAML schema format, data types, field syntax |
| [CLI Reference](docs/cli.md) | Command-line usage and options |
| [Code Generation](docs/codegen.md) | What gets generated, philosophy, resource considerations |
| [Documentation Generation](docs/docgen.md) | HTML documentation output |
| [Architecture](docs/architecture.md) | System design, components, data flow |
| [Development](docs/development.md) | Build commands, testing, contributing |

## License

MIT

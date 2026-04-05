# gattc Documentation

## Overview

gattc (GATT Compiler) is a contract-first tool for BLE development. Define GATT services once in YAML, generate type-safe C code for Zephyr and HTML documentation from a single source of truth.

## Documentation Index

| Document | Description |
|----------|-------------|
| [Schema Specification](schema.md) | YAML schema format, data types, field syntax |
| [Architecture](architecture.md) | System design, components, data flow |
| [Code Generation](codegen.md) | What gets generated, philosophy, resource considerations |
| [CLI Reference](cli.md) | Command-line usage and options |
| [Development](development.md) | Build commands, testing, contributing |

## Quick Start

```bash
# Install
pip install gattc

# Initialize new project
gattc init

# Edit gatt/echo_service.yaml, then compile
gattc compile
```

## The Problem

BLE development across firmware and mobile is fragmented:

- **Scattered definitions**: UUIDs in `.h` files, byte layout implicit in code, docs separate
- **Silent drift**: Firmware changes payload structure, mobile breaks at runtime
- **Manual sync**: Mobile devs read ICDs and manually implement characteristics
- **Implicit byte order**: Endianness buried in code

## The Solution

`gattc` generates from a single YAML schema:

- **C code** for Zephyr (UUIDs, packed structs, pack/unpack functions)
- **HTML documentation** for service reference

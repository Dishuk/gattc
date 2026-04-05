# Architecture

## System Overview

**CLI** (click) &rarr; **Core** (parser, validator, config) &rarr; **Generators** (zephyr, docs)

| Layer | Module | Responsibility |
|-------|--------|----------------|
| CLI | `cli.py` | Command-line interface |
| Core | `schema.py` | YAML parsing, validation |
| Core | `config.py` | Project configuration |
| Generator | `zephyr.py` | C code output (.h, .c) |
| Generator | `docs.py` | HTML documentation |

## Data Flow

1. **Load** - `schema.load_schema()` parses YAML into Schema object
2. **Validate** - `schema.validate_schema()` checks for errors
3. **Generate C** - `zephyr.generate()` outputs .h and .c files
4. **Generate Docs** (optional) - `docs.generate()` outputs .html files

## Components

### CLI (`cli.py`)

Click-based command-line interface:

- `gattc compile [schema]` - Generate code from schema
- `gattc check [schema]` - Validate schema without generating
- `gattc docs [schema]` - Generate HTML documentation
- `gattc init` - Initialize project with gattc.yaml and example schema

### Schema Parser (`schema.py`)

Parses YAML into typed Python objects:

```python
@dataclass
class TypeInfo:
    base: str           # e.g., "uint16", "bytes"
    size: int           # Size in bytes
    endian: str         # "little", "big", "none"
    is_array: bool
    array_size: int | str | None

@dataclass
class Field:
    name: str
    type_info: TypeInfo
    offset: int | None
    unit: str | None
    range: list[int] | None
    bits: dict | None
    fields: list[Field] | None  # For repeated structs

@dataclass
class Payload:
    fields: list[Field]
    mode: str | None        # "variable", "mtu_packed"
    min_size: int | None
    max_size: int | None

@dataclass
class Characteristic:
    name: str
    uuid: str
    properties: list[str]
    permissions: list[str]
    payload: Payload | None
    read_payload: Payload | None
    write_payload: Payload | None
    notify_payload: Payload | None

@dataclass
class Service:
    name: str
    uuid: str
    description: str

@dataclass
class Schema:
    schema_version: str
    service: Service
    characteristics: list[Characteristic]
```

### Validator (`schema.py`)

Validates schema for:

- Duplicate characteristic names
- Duplicate UUIDs
- Duplicate field names within payload
- Missing required fields

### Generators (`generators/`)

#### Zephyr Generator (`generators/zephyr.py`)

Generates C code for Zephyr RTOS:

**Header (.h) contains:**
- UUID macros (`BT_UUID_*_VAL`, `BT_UUID_*`)
- Packed struct definitions
- Size constants and `_Static_assert`
- Pack/unpack inline functions
- Bitfield macros
- MTU helper functions
- Callback declarations (read, write, CCC)

**Source (.c) contains:**
- `BT_GATT_SERVICE_DEFINE` macro
- Characteristic definitions
- CCC descriptors for notify/indicate characteristics

#### HTML Documentation Generator (`generators/docs.py`)

Generates HTML documentation for GATT services:

- Service overview with UUID
- Characteristic tables with properties/permissions
- Payload field definitions with types, offsets, units
- Bitfield and value definitions
- Responsive navigation sidebar

## File Structure

```
gattc/
├── src/gattc/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── schema.py           # Parsing and validation
│   ├── config.py           # Project configuration (gattc.yaml)
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── zephyr.py       # Zephyr C generator
│   │   └── docs.py         # HTML documentation generator
│   └── templates/
│       ├── zephyr/         # Jinja2 templates for C code
│       └── docs/           # Jinja2 templates for HTML
├── tests/
│   ├── test_schema.py
│   ├── test_generator.py
│   └── test_config.py
└── docs/                   # Documentation
```

## Error Handling

Validation errors include context:

```
Duplicate characteristic name: 'temperature'
Duplicate characteristic UUID: '12345678-...' (in 'humidity')
Duplicate field name 'value' in 'sensor_config'
```

## Future Components (Nice-to-Have)

The following generators are optional enhancements, not requirements:

- **TypeScript Generator**: Type definitions for web/mobile
- **Swift Generator**: iOS type definitions

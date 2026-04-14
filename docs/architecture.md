# Architecture

## System Overview

**CLI** (click) &rarr; **Core** (parser, validator, config, snapshots) &rarr; **Generators** (zephyr, docs)

| Layer | Module | Responsibility |
|-------|--------|----------------|
| CLI | `cli.py` | Command-line interface |
| Core | `schema.py` | YAML parsing, validation, type system |
| Core | `config.py` | Project configuration (`gattc.yaml`) |
| Core | `snapshot.py` | Schema snapshot storage for change tracking |
| Core | `diff.py` | Schema diffing and change detection |
| Core | `changelog.py` | Release history tracking |
| Generator | `zephyr.py` | C code output (.h, .c) |
| Generator | `docs.py` | HTML documentation |

## Data Flow

1. **Load** - `schema.load_schema()` parses YAML into Schema object
2. **Validate** - `schema.validate_schema()` checks for errors
3. **Diff** (if snapshots exist) - `diff.diff_schemas()` compares current schema against stored snapshot
4. **Generate C** - `zephyr.generate()` outputs .h and .c files
5. **Generate Docs** (optional) - `docs.generate()` outputs .html files with change highlighting
6. **Release** (on `gattc release`) - `snapshot.save_snapshot()` stores current state, `changelog.write_entry()` records changes

## Components

### CLI (`cli.py`)

Click-based command-line interface:

- `gattc init` - Initialize project with gattc.yaml and example schema
- `gattc compile [schema]` - Generate C code from schema (with automatic change detection)
- `gattc check [schema]` - Validate schema without generating
- `gattc docs [schema]` - Generate HTML documentation
- `gattc release [schema]` - Record schema changes, update snapshots, regenerate docs

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
    schema_revision: int | None
```

### Validator (`schema.py`)

Validates schema for:

- Valid 128-bit UUID format
- C identifier validity (service, characteristic, field, and bit names)
- C reserved keyword avoidance
- Duplicate characteristic names and UUIDs
- Duplicate field names within payload
- Property/permission consistency (read property requires read permission, etc.)
- Bitfield range validation (bit indices within type size)

### Snapshot System (`snapshot.py`)

Stores JSON snapshots of compiled schemas for change tracking:

- `save_snapshot()` - Serializes current schema to JSON
- `load_snapshot()` - Loads previous snapshot for comparison
- Backup mechanism with `.prev.json` files for revert support
- Default location: `gattc/snapshots/`, configurable in `gattc.yaml`

### Change Detection (`diff.py`)

Compares old snapshot to current schema and produces structured diffs:

- Detects added/removed/modified characteristics
- Tracks field-level changes (type, unit, values, bitfields, offsets)
- Tracks property and permission changes
- Tracks UUID changes
- Generates human-readable changelog text

### Release History (`changelog.py`)

Tracks schema changes over time:

- Stores revision history with timestamps and messages
- Used by `gattc release` to record changes
- Used by `gattc docs` to show changelog in generated HTML

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
- Write validation macros
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
- Change highlighting (when diff data available)
- Changelog history
- Responsive navigation sidebar

## File Structure

```
gattc/
├── src/gattc/
│   ├── __init__.py
│   ├── __main__.py         # python -m gattc entry point
│   ├── cli.py              # CLI entry point
│   ├── schema.py           # Parsing and validation
│   ├── config.py           # Project configuration (gattc.yaml)
│   ├── snapshot.py         # Schema snapshot storage
│   ├── diff.py             # Schema diffing
│   ├── changelog.py        # Release history
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── zephyr.py       # Zephyr C generator
│   │   └── docs.py         # HTML documentation generator
│   └── templates/
│       ├── zephyr/         # Jinja2 templates for C code
│       └── docs/           # Jinja2 templates for HTML
├── tests/
│   ├── test_schema.py      # Schema parsing and validation
│   ├── test_generator.py   # Zephyr code generation
│   ├── test_config.py      # Configuration loading
│   ├── test_docs.py        # HTML documentation generation
│   ├── test_diff.py        # Change detection
│   ├── test_snapshot.py    # Snapshot storage
│   ├── test_release.py     # Release/revert flow
│   ├── test_compile.py     # C compilation smoke tests
│   └── test_cli.py         # CLI integration tests
└── docs/                   # Documentation
```

## Error Handling

Validation errors include context:

```
Duplicate characteristic name: 'temperature'
Duplicate characteristic UUID: '12345678-...' (in 'humidity')
Duplicate field name 'value' in 'sensor_config'
Service name 'int' is not a valid C identifier: is a C reserved keyword
Bit 9 in 'status.flags' exceeds type size (max bit: 7)
```

Use `--debug` for full Python tracebacks on unexpected errors.

## Future Components (Nice-to-Have)

The following generators are optional enhancements, not requirements:

- **TypeScript Generator**: Type definitions for web/mobile
- **Swift Generator**: iOS type definitions

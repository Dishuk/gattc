# Development Guide

## Setup

```bash
# Clone repository
git clone <repo>
cd gattc

# Install in development mode
pip install -e ".[dev]"
```

## Build Commands

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_schema.py -v

# Run single test
pytest tests/test_schema.py::TestParseType::test_uint8 -v

# Run with coverage
pytest --cov=gattc
```

## Project Structure

```
gattc/
├── src/gattc/
│   ├── __init__.py         # Version
│   ├── cli.py              # CLI entry point (click)
│   ├── schema.py           # YAML parsing and validation
│   ├── config.py           # Project configuration (gattc.yaml)
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── zephyr.py       # Zephyr C code generator
│   │   └── docs.py         # HTML documentation generator
│   └── templates/
│       ├── zephyr/         # C code templates (.j2)
│       └── docs/           # HTML templates (.j2)
├── tests/
│   ├── test_schema.py      # Schema parsing tests
│   ├── test_generator.py   # Code generation tests
│   └── test_config.py      # Configuration tests
└── docs/                   # Documentation
```

## Key Components

### schema.py

- `parse_type(type_str)` - Parse type strings into TypeInfo
- `_parse_field(name, data)` - Parse field definitions
- `_parse_payload(data)` - Parse payload with auto-offset
- `load_schema(path)` - Load and parse YAML schema
- `validate_schema(schema)` - Validate for errors

### generators/zephyr.py

- `generate(schema, output_path)` - Main entry point
- `_write_header_file()` - Generate .h file
- `_write_source_file()` - Generate .c file
- `_write_struct()` - Generate packed struct
- `_write_pack_function()` - Generate pack function
- `_write_unpack_function()` - Generate unpack function

## Adding a New Type

1. Add to `BASE_TYPE_SIZES` in `schema.py`:
   ```python
   BASE_TYPE_SIZES = {
       ...
       "new_type": size_in_bytes,
   }
   ```

2. Add C type mapping in `zephyr.py`:
   ```python
   C_TYPE_MAP = {
       ...
       "new_type": "c_type_t",
   }
   ```

3. Add tests in `test_schema.py`

## Adding a New Generator

1. Create `generators/new_target.py`
2. Implement `generate(schema, output_path)` function
3. Add to CLI in `cli.py`

## Testing Guidelines

- Test type parsing for all supported types
- Test field parsing with all metadata options
- Test payload offset computation
- Test generated code structure (not exact formatting)
- Use `tmp_path` fixture for file operations

## Code Style

- Python 3.9+
- Type hints throughout
- Dataclasses for schema objects
- Minimal dependencies: click, pyyaml, jinja2

## Common Issues

### Tests failing with "Unknown type"

Check that the type is in `BASE_TYPE_SIZES`.

### Generated code has wrong endianness

Check that `_get_endian_pack_func()` handles the type size.

### Offsets computed incorrectly

Check `Payload.compute_offsets()` and field size calculations.

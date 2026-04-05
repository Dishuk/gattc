# CLI Reference

## Installation

```bash
pip install -e ".[dev]"
```

## Commands

### compile

Generate code from schema files.

```bash
gattc compile <schema> [options]
```

**Arguments:**
- `<schema>` - Path to YAML schema file(s)

**Options:**
- `-o, --output` - Output directory (default: current directory)

**Examples:**

```bash
# Compile single schema
gattc compile services/my_service.yaml

# Compile with output directory
gattc compile services/my_service.yaml -o src/generated/

# Compile multiple schemas
gattc compile services/*.yaml -o src/generated/
```

**Output:**

For each schema, generates:
- `<service_name>.h` - Header with structs, UUIDs, pack/unpack functions
- `<service_name>.c` - Source with GATT service definition

### check

Validate schema without generating code.

```bash
gattc check [schema]
```

**Arguments:**
- `[schema]` - Path to YAML schema file (optional if gattc.yaml exists)

**Examples:**

```bash
# Validate single schema
gattc check services/my_service.yaml

# Validate all schemas in project (requires gattc.yaml)
gattc check
```

**Output:**

- Success: No output, exit code 0
- Errors: List of validation errors, exit code 1

### docs

Generate HTML documentation from schema(s).

```bash
gattc docs [schema] [options]
```

**Arguments:**
- `[schema]` - Path to YAML schema file (optional if gattc.yaml exists)

**Options:**
- `-o, --output` - Output directory or file path
- `--combined` - Generate all services in a single HTML file
- `--per-service` - Generate separate HTML file per service (default)

**Examples:**

```bash
# Generate docs for single schema
gattc docs services/my_service.yaml -o docs/

# Generate combined docs for all schemas in project
gattc docs --combined

# Generate per-service docs with custom output
gattc docs --per-service -o docs/ble/
```

### init

Initialize gattc in current directory.

```bash
gattc init
```

Creates:
- `gattc.yaml` - Project configuration file
- `gatt/` - Schema directory
- `gatt/echo_service.yaml` - Example schema

**Example:**

```bash
# Initialize new project
mkdir my-ble-project && cd my-ble-project
gattc init

# Edit schemas and compile
gattc compile
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation error or generation failure |
| 2 | File not found or invalid arguments |

## Build Integration

### Makefile

```makefile
.PHONY: ble-generate

ble-generate:
	gattc compile services/*.yaml -o src/generated/

build: ble-generate
	west build -b nrf52840dk_nrf52840
```

### CI Check

```bash
# Fail if generated files are stale
gattc compile services/*.yaml -o src/generated/
git diff --exit-code src/generated/ || \
    (echo "Generated files out of sync" && exit 1)
```

## Future Commands

Planned but not yet implemented:

- `gattc compile --watch` - Watch mode for development
- `gattc compile --dry-run` - Check without writing files
- `gattc diff` - Show changes between schema versions

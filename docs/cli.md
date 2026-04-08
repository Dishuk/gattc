# CLI Reference

## Installation

```bash
pip install -e ".[dev]"
```

## Global Options

| Option | Description |
|--------|-------------|
| `--debug` | Show full tracebacks on errors (default: user-friendly messages with hint) |
| `--version` | Show version and exit |

## Commands

### init

Initialize gattc in current directory.

```bash
gattc init
```

Creates:
- `gattc.yaml` - Project configuration file
- `gattc/` - Schema directory
- `gattc/echo_service.yaml` - Example schema

**Example:**

```bash
# Initialize new project
mkdir my-ble-project && cd my-ble-project
gattc init

# Edit schemas and compile
gattc compile
```

### compile

Generate Zephyr C code from schema files.

```bash
gattc compile [SCHEMA] [options]
```

**Arguments:**
- `[SCHEMA]` - Path to YAML schema file (optional if `gattc.yaml` exists)

**Options:**

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Output directory (sets both header and source location) |
| `--header PATH` | Output directory for header files (.h) |
| `--source PATH` | Output directory for source files (.c) |
| `--combined` | Generate all services in a single .h/.c file pair |
| `--per-service` | Generate separate .h/.c files per service (default) |
| `--docs / --no-docs` | Generate HTML documentation alongside C code |
| `--no-diff` | Skip change detection against snapshots |

**Modes:**

- **Single schema mode:** `gattc compile path/to/schema.yaml -o output/`
- **Project mode:** `gattc compile` (reads schemas and output paths from `gattc.yaml`)

**Change detection:**

When snapshots exist (created by `gattc release`), compile automatically compares
current schemas against stored snapshots and shows changes in CLI output. This does
NOT update snapshots or changelog — use `gattc release` for that. Use `--no-diff`
to skip change detection.

**Examples:**

```bash
# Compile single schema
gattc compile services/my_service.yaml -o src/generated/

# Compile all schemas from gattc.yaml
gattc compile

# Split header and source output
gattc compile --header src/include/ --source src/

# Combined output (all services in one file pair)
gattc compile --combined

# Generate C code and HTML docs together
gattc compile --docs
```

**Output:**

For each schema (per-service mode):
- `<service_name>.h` - Header with structs, UUIDs, pack/unpack functions
- `<service_name>.c` - Source with GATT service definition

Combined mode:
- `ble_services.h` - All services in one header
- `ble_services.c` - All services in one source

### check

Validate schema without generating code.

```bash
gattc check [SCHEMA]
```

**Arguments:**
- `[SCHEMA]` - Path to YAML schema file (optional if `gattc.yaml` exists)

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
gattc docs [SCHEMA] [options]
```

**Arguments:**
- `[SCHEMA]` - Path to YAML schema file (optional if `gattc.yaml` exists)

**Options:**

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Output directory or file path |
| `--combined` | Generate all services in a single HTML file |
| `--per-service` | Generate separate HTML file per service (default) |

**Examples:**

```bash
# Generate docs for single schema
gattc docs services/my_service.yaml -o docs/

# Generate combined docs for all schemas in project
gattc docs --combined

# Generate per-service docs with custom output
gattc docs --per-service -o docs/ble/
```

### release

Record schema changes and regenerate documentation.

```bash
gattc release [SCHEMA] [options]
```

Compares current schemas against stored snapshots, records changes as a
changelog entry with your message, updates snapshots, and regenerates
HTML documentation.

**Arguments:**
- `[SCHEMA]` - Path to YAML schema file (optional if `gattc.yaml` exists)

**Options:**

| Option | Description |
|--------|-------------|
| `-m, --message TEXT` | Describe what changed and why |
| `--revert` | Revert the last release (one level of undo) |

The `-m` message should describe WHY the change was made — the tool records
the structural details (added/removed/modified fields, properties, etc.) automatically.

**Examples:**

```bash
# Record a release with a message
gattc release -m "Add humidity field for v2.1 hardware"

# Record removal of deprecated fields
gattc release -m "Remove deprecated legacy fields"

# Undo the last release (restores previous snapshot, removes last changelog entry)
gattc release --revert
```

**What happens on release:**
1. Loads current schemas and compares against stored snapshots
2. Detects all changes (added/removed/modified characteristics, fields, properties)
3. Creates a changelog entry with your message and the detected changes
4. Updates snapshots to current schema state
5. Regenerates HTML documentation (with change highlighting if applicable)

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
	gattc compile

build: ble-generate
	west build -b nrf52840dk_nrf52840
```

### CI Check

```bash
# Fail if generated files are stale
gattc compile
git diff --exit-code src/generated/ || \
    (echo "Generated files out of sync" && exit 1)
```

## Future Commands

Planned but not yet implemented:

- `gattc compile --watch` - Watch mode for development
- `gattc compile --dry-run` - Check without writing files
- `gattc diff` - Show changes between schema versions (standalone)

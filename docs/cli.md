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
| `--docs / --no-docs` | Generate documentation (Markdown by default, HTML if configured) alongside C code |
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

# Generate C code and docs together (format comes from gattc.yaml; defaults to Markdown)
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

Generate documentation from schema(s) as Markdown (default) or HTML.

```bash
gattc docs [SCHEMA] [options]
```

**Arguments:**
- `[SCHEMA]` - Path to YAML schema file (optional if `gattc.yaml` exists)

**Options:**

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Output directory or file path |
| `-f, --format FMT` | Output format: `md` (default) or `html` |
| `--combined` | Generate all services in a single file |
| `--per-service` | Generate a separate file per service (default) |

**Format resolution** (first rule wins):

1. `-f / --format`
2. Suffix of `-o` (if `.md` or `.html`)
3. `output.docs.format` in `gattc.yaml`
4. Fallback: `md`

`-f` and a conflicting `-o` suffix (e.g. `-f md -o out.html`) produce an error.

**Examples:**

```bash
# Generate Markdown for single schema (default)
gattc docs services/my_service.yaml -o docs/

# Generate HTML (explicit flag)
gattc docs services/my_service.yaml -o docs/ -f html

# Generate HTML (inferred from file suffix)
gattc docs services/my_service.yaml -o docs/my_service.html

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
changelog entry with the provided message, updates snapshots, and regenerates
documentation (in the format configured by `output.docs.format`; Markdown by default).

**Arguments:**
- `[SCHEMA]` - Path to YAML schema file (optional if `gattc.yaml` exists)

**Options:**

| Option | Description |
|--------|-------------|
| `-m, --message TEXT` | Describe what changed and why. If omitted, `$EDITOR` opens (like `git commit`) prefilled with the detected changes. |

The message should describe WHY the change was made — the tool records
the structural details (added/removed/modified fields, properties, etc.) automatically.

**Examples:**

```bash
# Record a release with an inline message
gattc release -m "Add humidity field for v2.1 hardware"

# Open $EDITOR to write a longer release note
gattc release
```

### changelog

List and edit recorded release entries.

```bash
gattc changelog [--service NAME] [SUBCOMMAND] [REVISION]
```

Entries are stored as one markdown file per revision under
`gattc/changelog/<service>/NNN.md` with YAML frontmatter (revision number,
timestamp, detected structural changes) followed by the author's message.

**Options:**

| Option | Description |
|--------|-------------|
| `--service NAME` | Limit to a specific service. `list` shows every service when omitted; `path`/`edit` require a single service (so this is only needed if the project defines more than one). |

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `list` (default) | Print all revisions with their file paths and first-line messages |
| `path [REVISION]` | Print the absolute path to a revision file. **When `REVISION` is omitted, the latest revision is used.** |
| `edit [REVISION]` | Open a revision file in `$EDITOR`. **When `REVISION` is omitted, the latest revision is opened.** |

**Examples:**

```bash
# List all revisions for the sole service
gattc changelog

# Edit the latest revision's message
gattc changelog edit

# Edit a specific revision
gattc changelog edit 3

# Print path to revision 2 (for scripting)
gattc changelog path 2
```

**What happens on release:**
1. Loads current schemas and compares against stored snapshots
2. Detects all changes (added/removed/modified characteristics, fields, properties)
3. Creates a changelog entry with the provided message and the detected changes
4. Updates snapshots to current schema state
5. Regenerates documentation in the configured format (with change highlighting if applicable)

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

# Documentation Generation

Generate documentation from GATT schemas for sharing with mobile teams, creating ICDs, or internal reference. **Markdown is the default output**; HTML is available as an opt-in.

## Quick Start

```bash
# Single schema, Markdown (default)
gattc docs services/sensor_service.yaml -o docs/

# All schemas in project
gattc docs -o docs/ble/

# HTML output instead
gattc docs -o docs/ble/ -f html
```

## CLI Reference

```
gattc docs [OPTIONS] [SCHEMA]

Arguments:
  SCHEMA    Path to schema file (optional if gattc.yaml exists)

Options:
  -o, --output PATH    Output directory or file path
  -f, --format FMT     Output format: md (default) or html
  --combined           Merge all services into a single file
  --per-service        Generate a separate file per service (default)
```

### Format resolution

The format is chosen from the first rule that matches:

1. Explicit `-f / --format` flag
2. Suffix of `-o` (if it ends in `.md` or `.html`)
3. `output.docs.format` in `gattc.yaml`
4. Fallback: `md`

If `-f` and the `-o` suffix disagree (e.g. `-f md -o out.html`), the command exits with an error.

## Configuration

In `gattc.yaml`:

```yaml
output:
  docs:
    path: "docs/ble/"           # Output directory
    per_service: true           # true = one file per service (default)
                                # false = all services in gatt_services.<ext>
    format: md                  # "md" (default) or "html"
```

## Output Modes

### Per-Service (default)

Each schema produces its own file:

```
docs/ble/
├── sensor_service.md
├── device_info.md
└── echo_service.md
```

Switch the whole project to HTML via `format: html` in `gattc.yaml`, or per-command via `-f html`.

### Combined

All services merged into one file:

```bash
gattc docs --combined -o docs/ble/
```

Produces: `docs/ble/gatt_services.md` (or `gatt_services.html` with `-f html`).

## Markdown vs HTML

| Aspect | Markdown (default) | HTML |
|--------|--------------------|------|
| Renders on GitHub / GitLab / Bitbucket | ✅ natively | ❌ raw source shown |
| Embeds into Confluence / Notion / wikis | ✅ paste-friendly | needs conversion |
| Git-diffable reviews | ✅ clean diffs | noisy due to styling |
| Standalone styling & theming | — | ✅ self-contained, dark mode, search |
| Nested tables | simulated via numbered appendix tables | native nested tables |

Markdown is a better default for contract-first sharing; HTML is preferable when you want a polished, self-contained artifact to open in a browser.

> **Note:** the Markdown output targets GitHub Flavored Markdown — pipe tables and raw `<a id>` anchor tags. Strict CommonMark renderers will show the anchor tags as literal text and won't parse the tables.

## Generated Content

Both formats include the same information:

| Section | Contents |
|---------|----------|
| Service Info | Name, UUID, description, schema version/revision |
| Characteristics | Name, UUID, properties, permissions |
| Payload Tables | Field name, type, offset, size, description, unit |
| Bitfield Details | Bit ranges and flag names |
| Named Values | Value-to-name mappings |
| Changelog | Per-revision structural changes and release messages |

In Markdown, complex per-field details (bitfields, named enums, nested structs) are rendered as numbered sub-tables linked via inline anchors (e.g. `[Table 1.1](#table-1-1)`) to work around Markdown's lack of nested tables. HTML renders them inline. A `## Contents` table of contents is emitted at the top of every Markdown doc (flat in single-service mode, two-level in combined mode).

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
    format: md              # picks format for `compile --docs` and `release`
```

Then `gattc compile` generates both C code and the configured documentation format.

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

The Markdown main field row links to a numbered sub-table:

```markdown
| Name    | Offset | Length | Type    | Description | Value                      | Units |
|---------|--------|--------|---------|-------------|----------------------------|-------|
| `flags` | 0      | 1      | `uint8` | -           | [Table 1.1](#table-1-1)    | -     |

<a id="table-1-1"></a>
#### Table 1.1 — `flags` bitfield
| Range | Name     |
|-------|----------|
| `0`   | `enabled`|
| `1`   | `error`  |
| `2-4` | `mode`   |
```

HTML renders the bitfield as an inline nested table under the main row.

## Generating Both Formats

`gattc compile` and `gattc release` only clear files in the *currently configured* format. This means you can keep Markdown and HTML outputs side-by-side in the same directory — useful when you want MD for git reviews and HTML for browser viewing:

```bash
# Generate both (MD from config, HTML on demand)
gattc compile --docs                    # writes docs/ble/*.md
gattc docs -f html -o docs/ble/         # writes docs/ble/*.html, leaves .md untouched
```

Each invocation only touches files in its own format, so mixing formats in one directory is safe.

**Caveat:** this also means that if you *change* the configured format (`format: md` → `format: html`), the old files from the previous format aren't removed automatically. Delete them yourself if you don't want stale copies hanging around.

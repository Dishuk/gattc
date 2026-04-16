# Configuration Reference

Project configuration file `gattc.yaml` defines schemas location and output paths.

## File Location

gattc searches for `gattc.yaml` in the current directory and parent directories. Place it in the project root.

## Minimal Example

```yaml
schemas:
  - gattc/

output:
  zephyr:
    header: src/ble/generated/
```

## Full Example

```yaml
schemas:
  - gattc/sensor_service.yaml
  - gattc/config_service.yaml

output:
  zephyr:
    header: src/ble/include/generated/
    source: src/ble/src/generated/
    per_service: true

  docs:
    path: docs/ble/
    per_service: true

services:
  sensor_service:
    output:
      zephyr:
        header: src/sensors/include/
        source: src/sensors/src/
```

## Fields

### schemas

Schema files or directories to compile.

```yaml
# Single file
schemas: gattc/my_service.yaml

# Multiple files
schemas:
  - gattc/sensor_service.yaml
  - gattc/config_service.yaml

# Directory (all .yaml files inside)
schemas:
  - gattc/

# Mixed
schemas:
  - gattc/
  - custom/special_service.yaml
```

### output

Output configuration for generators.

#### output.zephyr

C code output for Zephyr.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `header` | string | - | Header files (.h) output directory |
| `source` | string | same as header | Source files (.c) output directory |
| `per_service` | bool | `true` | `true` = separate file pair per service, `false` = single combined file |

```yaml
output:
  zephyr:
    header: src/ble/include/
    source: src/ble/src/
    per_service: true
```

**Per-service output** (`per_service: true`):
```
src/ble/include/
├── sensor_service.h
└── config_service.h
src/ble/src/
├── sensor_service.c
└── config_service.c
```

**Combined output** (`per_service: false`):
```
src/ble/include/
└── ble_services.h
src/ble/src/
└── ble_services.c
```

If only `header` is specified, `source` defaults to the same path:

```yaml
output:
  zephyr:
    header: src/generated/   # Both .h and .c go here
```

#### output.docs

Documentation output. Generates Markdown by default; HTML is available via `format: html`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | - | Documentation output directory |
| `per_service` | bool | `true` | `true` = separate file per service, `false` = single combined file |
| `format` | string | `md` | Output format: `md` (Markdown) or `html` |

```yaml
output:
  docs:
    path: docs/ble/
    per_service: false   # All services in one file
    format: md           # or "html"
```

Short syntax (path only, defaults to `per_service: true`, `format: md`):

```yaml
output:
  docs: docs/ble/
```

The `format` set here is used by `gattc compile --docs`, `gattc release`, and — unless overridden — by `gattc docs`. The CLI's `-f/--format` flag (and inference from `-o` suffix) overrides this on a per-invocation basis.

### services

Per-service output overrides. Useful when different services need different output locations.

```yaml
services:
  sensor_service:
    output:
      zephyr:
        header: src/sensors/
      docs:
        path: docs/sensors/

  bootloader_service:
    output:
      zephyr:
        header: src/bootloader/
```

### snapshots

Configuration for schema change tracking. Snapshots are JSON files that store the
current state of each schema, used by `gattc compile` (change detection) and
`gattc release` (changelog generation).

```yaml
snapshots:
  path: "gattc/snapshots"    # Default location
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | `gattc/snapshots` | Directory for per-service snapshot JSON files |

Files created per service:
- `gattc/snapshots/<service_name>.json` - Current schema snapshot
- `gattc/changelog/<service_name>/NNN.md` - One markdown file per revision (release history)

The `changelog/` directory sits alongside `snapshots/` under the same parent.

## CLI Override

Command-line arguments override `gattc.yaml`:

```bash
# Uses gattc.yaml
gattc compile

# Overrides output path
gattc compile -o custom/path/

# Ignores gattc.yaml, uses explicit paths
gattc compile gattc/my_service.yaml -o src/generated/
```

## Directory Structure

Recommended project layout:

```
project/
├── gattc.yaml
├── gattc/
│   ├── sensor_service.yaml
│   └── config_service.yaml
├── src/
│   └── ble/
│       └── generated/
│           ├── sensor_service.h
│           ├── sensor_service.c
│           ├── config_service.h
│           └── config_service.c
└── docs/
    └── ble/
        ├── sensor_service.md
        └── config_service.md
```

Corresponding `gattc.yaml`:

```yaml
schemas:
  - gattc/

output:
  zephyr:
    header: src/ble/generated/
  docs:
    path: docs/ble/
```

# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-04-16

### Added
- Markdown output format for `gattc docs`, alongside HTML.
- Clickable table of contents and stable heading anchors in generated Markdown docs.
- Hierarchical table numbering for service-level changes in Markdown output.

### Changed
- Service-level change entries now use tag-based labels for clearer grouping.

### Fixed
- Broke a circular import between `cli` and `commands` by extracting a shared `_errors` module.

### Removed
- Redundant tests and stale doc references left behind by earlier refactors.

## [0.2.0] - 2026-04-14

First tagged release.

### Added
- `gattc` CLI: `init`, `compile`, `check`, `docs`, `release` commands.
- Code generation for Zephyr (requires Zephyr 3.5.0+).
- HTML documentation generator with light/dark themes.
- YAML schema with C identifier validation, overlapping bitfield detection, and unknown-key warnings.
- Per-revision Markdown changelog storage and editor-driven release messages.
- `scripts/bump_version.py` helper and `gattc.__version__` sourced from package metadata.
- GitHub Actions CI running the test suite on push and PR to `main`.

[Unreleased]: https://github.com/Dishuk/gattc/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Dishuk/gattc/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Dishuk/gattc/releases/tag/v0.2.0

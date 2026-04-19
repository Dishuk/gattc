"""Output file management helpers shared across commands."""

from pathlib import Path

import click


def clear_files(files: list[Path]) -> int:
    """Delete specific files. Returns the number of files deleted."""
    deleted = 0
    for file_path in files:
        if file_path.is_file():
            file_path.unlink()
            deleted += 1
    return deleted


def collect_output_files(
    names: list[str],
    header_dir: Path | None,
    source_dir: Path | None,
    docs_dir: Path | None,
    generate_docs: bool,
    docs_fmt: str = "md",
) -> list[Path]:
    """Build the list of files that will be generated, so only those get cleared."""
    files: list[Path] = []
    for name in names:
        if header_dir:
            files.append(header_dir / f"{name}.h")
        if source_dir:
            files.append(source_dir / f"{name}.c")
            if header_dir is None:
                files.append(source_dir / f"{name}.h")
        if generate_docs and docs_dir:
            files.append(docs_dir / f"{name}.{docs_fmt}")
    return files


def clear_output_files(
    names: list[str],
    header_dir: Path | None,
    source_dir: Path | None,
    docs_dir: Path | None,
    generate_docs: bool,
    docs_fmt: str = "md",
) -> None:
    """Clear only the files that will be regenerated."""
    files = collect_output_files(names, header_dir, source_dir, docs_dir, generate_docs, docs_fmt)
    cleared = clear_files(files)
    if cleared:
        click.echo(f"Cleared {cleared} previously generated file(s)")

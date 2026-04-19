"""
Bump the project version, commit, and tag.

Usage:
    python scripts/bump_version.py {major|minor|patch}

- Reads current version from pyproject.toml (single source of truth).
- Rewrites pyproject.toml only — `gattc.__version__` reads installed
  package metadata at runtime.
- Requires a clean working tree.
- Creates a single commit containing only the version bump and an
  annotated tag `vX.Y.Z`. Does not push.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

PART_CHOICES = ("major", "minor", "patch")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        args, cwd=REPO_ROOT, capture_output=capture, text=True, check=False
    )
    if result.returncode != 0:
        if capture:
            sys.stderr.write(result.stderr)
        die(f"command failed: {' '.join(args)}")
    return (result.stdout or "").strip()


def read_current_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not m:
        die("could not find version in pyproject.toml")
    return m.group(1)


def bump(version: str, part: str) -> str:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        die(f"current version {version!r} is not semver X.Y.Z")
    major, minor, patch = (int(x) for x in m.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def replace_in_file(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if n != 1:
        die(f"could not update version in {path.relative_to(REPO_ROOT)}")
    path.write_text(new_text, encoding="utf-8")


def ensure_clean_tree() -> None:
    status = run("git", "status", "--porcelain", capture=True)
    if status:
        die("working tree is dirty; commit or stash changes first")


def ensure_tag_free(tag: str) -> None:
    existing = run("git", "tag", "--list", tag, capture=True)
    if existing:
        die(f"tag {tag} already exists")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in PART_CHOICES:
        die(f"usage: python scripts/bump_version.py {{{'|'.join(PART_CHOICES)}}}")

    part = sys.argv[1]
    ensure_clean_tree()

    current = read_current_version()
    new = bump(current, part)
    tag = f"v{new}"
    ensure_tag_free(tag)

    replace_in_file(
        PYPROJECT,
        r'^version\s*=\s*"[^"]+"',
        f'version = "{new}"',
    )

    run("git", "add", str(PYPROJECT))
    run("git", "commit", "-m", f"Bump version to {new}")
    run("git", "tag", "-a", tag, "-m", f"Release {new}")

    print(f"bumped {current} -> {new}")
    print(f"tagged {tag}")
    print("next: git push && git push --tags")


if __name__ == "__main__":
    main()

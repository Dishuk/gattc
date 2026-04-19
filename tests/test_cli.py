"""CLI integration tests for init, compile, check, and docs commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from gattc.cli import main

MINIMAL_SCHEMA = """\
schema_version: "1.0"
service:
  name: test_svc
  uuid: "12345678-1234-1234-1234-123456789abc"
characteristics:
  sensor:
    uuid: "12345678-1234-1234-1234-000000000001"
    properties: [read]
    permissions: [read]
    payload:
      temperature: uint16
"""

INVALID_SCHEMA = """\
schema_version: "1.0"
service:
  name: test_svc
"""

MINIMAL_CONFIG = """\
schemas:
  - "gattc/"
output:
  zephyr:
    header: "out/"
"""


@pytest.fixture
def project_dir(tmp_path):
    schema_dir = tmp_path / "gattc"
    schema_dir.mkdir()
    (schema_dir / "test_svc.yaml").write_text(MINIMAL_SCHEMA)
    (tmp_path / "gattc.yaml").write_text(MINIMAL_CONFIG)
    return tmp_path


runner = CliRunner()


def test_init(tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        cwd = Path.cwd()
        assert (cwd / "gattc.yaml").exists()
        assert (cwd / "gattc" / "echo_service.yaml").exists()


def test_compile(project_dir):
    with runner.isolated_filesystem(temp_dir=project_dir):
        result = runner.invoke(main, ["compile", "--no-diff"], catch_exceptions=False)
        assert result.exit_code == 0
        assert (project_dir / "out" / "test_svc.h").exists()
        assert (project_dir / "out" / "test_svc.c").exists()


def test_check_valid(project_dir):
    schema = project_dir / "gattc" / "test_svc.yaml"
    with runner.isolated_filesystem(temp_dir=project_dir):
        result = runner.invoke(main, ["check", str(schema)], catch_exceptions=False)
        assert result.exit_code == 0


def test_check_invalid(tmp_path):
    schema = tmp_path / "bad.yaml"
    schema.write_text(INVALID_SCHEMA)
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["check", str(schema)])
        assert result.exit_code == 1


def test_docs(project_dir):
    schema = project_dir / "gattc" / "test_svc.yaml"
    out = project_dir / "docs_out"
    with runner.isolated_filesystem(temp_dir=project_dir):
        result = runner.invoke(
            main, ["docs", str(schema), "-o", str(out)], catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert (out / "test_svc.md").exists()


def test_docs_infers_format_from_output_suffix(project_dir):
    schema = project_dir / "gattc" / "test_svc.yaml"
    out = project_dir / "out.html"
    with runner.isolated_filesystem(temp_dir=project_dir):
        result = runner.invoke(
            main, ["docs", str(schema), "-o", str(out)], catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert out.is_file()
        assert "<html" in out.read_text().lower()


def test_docs_errors_on_format_output_suffix_conflict(project_dir):
    schema = project_dir / "gattc" / "test_svc.yaml"
    out = project_dir / "out.html"
    with runner.isolated_filesystem(temp_dir=project_dir):
        result = runner.invoke(main, ["docs", str(schema), "-o", str(out), "-f", "md"])
        assert result.exit_code != 0
        assert "conflicts" in result.output.lower()

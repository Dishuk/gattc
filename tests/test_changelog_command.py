"""Tests for the `gattc changelog` command group."""

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

MODIFIED_SCHEMA = MINIMAL_SCHEMA.replace("temperature: uint16", "temperature: uint32")


@pytest.fixture
def project_with_revision(tmp_path):
    schema_dir = tmp_path / "gattc"
    schema_dir.mkdir()
    (schema_dir / "test_svc.yaml").write_text(MINIMAL_SCHEMA)
    (tmp_path / "gattc.yaml").write_text(
        'schemas:\n  - "gattc/"\noutput:\n  zephyr:\n    header: "out/"\n'
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
        (tmp_path / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)
        runner.invoke(main, ["release", "-m", "Upgrade to uint32"], catch_exceptions=False)
    return tmp_path


def test_changelog_list_shows_revisions(project_with_revision):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=project_with_revision):
        result = runner.invoke(main, ["changelog", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "001.md" in result.output
        assert "Upgrade to uint32" in result.output


def test_changelog_default_subcommand_is_list(project_with_revision):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=project_with_revision):
        result = runner.invoke(main, ["changelog"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "001.md" in result.output


def test_changelog_path_prints_absolute_path(project_with_revision):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=project_with_revision):
        result = runner.invoke(main, ["changelog", "path", "1"], catch_exceptions=False)
        assert result.exit_code == 0
        expected = project_with_revision / "gattc" / "changelog" / "test_svc" / "001.md"
        assert str(expected) in result.output


def test_changelog_edit_updates_message(project_with_revision, monkeypatch):
    def fake_edit(filename=None, **kw):
        text = Path(filename).read_text(encoding="utf-8")
        fm_end = text.index("---", 4) + 3
        Path(filename).write_text(text[:fm_end] + "\n\nEdited message\n", encoding="utf-8")

    monkeypatch.setattr("click.edit", fake_edit)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=project_with_revision):
        result = runner.invoke(main, ["changelog", "edit", "1"], catch_exceptions=False)
        assert result.exit_code == 0

        list_result = runner.invoke(main, ["changelog", "list"], catch_exceptions=False)
        assert "Edited message" in list_result.output


def test_changelog_list_empty_project(tmp_path):
    (tmp_path / "gattc").mkdir()
    (tmp_path / "gattc" / "test_svc.yaml").write_text(MINIMAL_SCHEMA)
    (tmp_path / "gattc.yaml").write_text(
        'schemas:\n  - "gattc/"\noutput:\n  zephyr:\n    header: "out/"\n'
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["changelog", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "no changelog" in result.output.lower()

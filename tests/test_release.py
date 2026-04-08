"""Tests for gattc release, amend, and revert commands."""

import json
import pytest
from pathlib import Path

from click.testing import CliRunner

from gattc.cli import main
from gattc.snapshot import get_snapshot_path, load_snapshot, save_snapshot
from gattc.changelog import load_changelog
from gattc.schema import Schema, Service, Characteristic, Payload, Field, TypeInfo


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


@pytest.fixture
def project_dir(tmp_path):
    """Set up a minimal gattc project in a temp directory."""
    schema_dir = tmp_path / "gattc"
    schema_dir.mkdir()
    (schema_dir / "test_svc.yaml").write_text(MINIMAL_SCHEMA)
    (tmp_path / "gattc.yaml").write_text(
        'schemas:\n  - "gattc/"\noutput:\n  zephyr:\n    header: "out/"\n'
    )
    return tmp_path


class TestRelease:

    def test_release_requires_message(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            result = runner.invoke(main, ["release"], catch_exceptions=False)
            assert result.exit_code != 0
            assert "Missing option" in result.output or "required" in result.output.lower() or result.exit_code == 2

    def test_release_creates_snapshot_and_changelog(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            # First release — creates initial snapshot, no changelog (no prior baseline)
            result = runner.invoke(
                main, ["release", "-m", "Initial release"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Initial snapshot" in result.output

            snapshot = load_snapshot("test_svc", config=None, root_dir=project_dir)
            assert snapshot is not None
            assert snapshot["service"]["name"] == "test_svc"

    def test_release_records_changes_with_message(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            # Create initial snapshot
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)

            # Modify schema
            modified = MINIMAL_SCHEMA.replace("temperature: uint16", "temperature: uint32")
            (project_dir / "gattc" / "test_svc.yaml").write_text(modified)

            # Release with message
            result = runner.invoke(
                main, ["release", "-m", "Upgraded to uint32 for precision"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Changes recorded" in result.output

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 1
            assert changelog[0]["message"] == "Upgraded to uint32 for precision"
            assert changelog[0]["revision"] == 1

    def test_release_no_changes(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            # Create initial snapshot
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)

            # Release again with no changes
            result = runner.invoke(
                main, ["release", "-m", "Nothing changed"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "No changes" in result.output

            # No changelog entry should exist
            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 0


MODIFIED_SCHEMA = MINIMAL_SCHEMA.replace("temperature: uint16", "temperature: uint32")


class TestRevert:

    def test_revert_removes_last_entry(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
            (project_dir / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)
            runner.invoke(main, ["release", "-m", "Will revert"], catch_exceptions=False)

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 1

            result = runner.invoke(
                main, ["release", "--revert"], catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Reverted" in result.output

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 0

    def test_revert_restores_previous_snapshot(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
            old_snapshot = load_snapshot("test_svc", config=None, root_dir=project_dir)

            (project_dir / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)
            runner.invoke(main, ["release", "-m", "Changed"], catch_exceptions=False)

            runner.invoke(main, ["release", "--revert"], catch_exceptions=False)
            restored = load_snapshot("test_svc", config=None, root_dir=project_dir)
            assert restored == old_snapshot

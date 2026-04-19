"""Tests for shared command helpers: output management and mode resolution."""

import click
import pytest
from click.testing import CliRunner

from gattc.cli import main
from gattc.commands._output_management import (
    clear_files,
    clear_output_files,
    collect_output_files,
)
from gattc.commands._schema_loading import resolve_combined_mode


class TestResolveCombinedMode:
    def test_combined_flag_wins_over_config(self):
        assert resolve_combined_mode(True, None, config_is_combined=False) is True

    def test_per_service_flag_wins_over_config(self):
        assert resolve_combined_mode(None, True, config_is_combined=True) is False

    def test_falls_back_to_config_when_no_flags(self):
        assert resolve_combined_mode(None, None, config_is_combined=True) is True
        assert resolve_combined_mode(None, None, config_is_combined=False) is False

    def test_raises_when_both_flags_set(self):
        with pytest.raises(click.ClickException, match="both --combined and --per-service"):
            resolve_combined_mode(True, True, config_is_combined=False)


class TestCollectOutputFiles:
    def test_header_and_source_in_same_dir(self, tmp_path):
        files = collect_output_files(
            ["svc"], tmp_path, tmp_path, docs_dir=None, generate_docs=False,
        )
        assert set(files) == {tmp_path / "svc.h", tmp_path / "svc.c"}

    def test_separate_header_and_source_dirs(self, tmp_path):
        hdir = tmp_path / "include"
        sdir = tmp_path / "src"
        files = collect_output_files(
            ["svc"], hdir, sdir, docs_dir=None, generate_docs=False,
        )
        assert set(files) == {hdir / "svc.h", sdir / "svc.c"}

    def test_source_only_places_header_next_to_source(self, tmp_path):
        files = collect_output_files(
            ["svc"], header_dir=None, source_dir=tmp_path,
            docs_dir=None, generate_docs=False,
        )
        assert set(files) == {tmp_path / "svc.c", tmp_path / "svc.h"}

    def test_includes_docs_with_chosen_format(self, tmp_path):
        docs_dir = tmp_path / "docs"
        files = collect_output_files(
            ["svc"], tmp_path, tmp_path, docs_dir,
            generate_docs=True, docs_fmt="html",
        )
        assert docs_dir / "svc.html" in files

    def test_omits_docs_when_generate_docs_false(self, tmp_path):
        docs_dir = tmp_path / "docs"
        files = collect_output_files(
            ["svc"], tmp_path, tmp_path, docs_dir, generate_docs=False,
        )
        assert all(f.parent != docs_dir for f in files)

    def test_multiple_names_emit_paths_for_each(self, tmp_path):
        files = collect_output_files(
            ["a", "b"], tmp_path, tmp_path, docs_dir=None, generate_docs=False,
        )
        assert {f.name for f in files} == {"a.h", "a.c", "b.h", "b.c"}


class TestClearOutputFiles:
    def test_removes_only_matching_names(self, tmp_path):
        (tmp_path / "svc.h").write_text("old")
        (tmp_path / "svc.c").write_text("old")
        (tmp_path / "other.h").write_text("keep")
        (tmp_path / "README.md").write_text("keep")

        clear_output_files(
            ["svc"], tmp_path, tmp_path, docs_dir=None, generate_docs=False,
        )

        assert not (tmp_path / "svc.h").exists()
        assert not (tmp_path / "svc.c").exists()
        assert (tmp_path / "other.h").exists()
        assert (tmp_path / "README.md").exists()

    def test_noop_when_target_files_missing(self, tmp_path):
        # No pre-existing files; must not raise or create anything.
        clear_output_files(
            ["svc"], tmp_path, tmp_path, docs_dir=None, generate_docs=False,
        )
        assert list(tmp_path.iterdir()) == []

    def test_clear_files_counts_only_actual_deletions(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        missing = tmp_path / "c.txt"

        deleted = clear_files([tmp_path / "a.txt", tmp_path / "b.txt", missing])

        assert deleted == 2


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

MINIMAL_CONFIG = """\
schemas:
  - "gattc/"
output:
  zephyr:
    header: "out/"
"""


class TestCombinedPerServiceConflictEndToEnd:
    """End-to-end CLI coverage for `--combined --per-service` rejection."""

    def test_compile_rejects_both_flags(self, tmp_path):
        schema_dir = tmp_path / "gattc"
        schema_dir.mkdir()
        (schema_dir / "test_svc.yaml").write_text(MINIMAL_SCHEMA)
        (tmp_path / "gattc.yaml").write_text(MINIMAL_CONFIG)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["compile", "--combined", "--per-service"])

        assert result.exit_code != 0
        assert "both --combined and --per-service" in result.output

"""Tests for gattc release command."""


import pytest
from click.testing import CliRunner

from gattc.changelog import get_changelog_dir, load_changelog
from gattc.cli import main
from gattc.snapshot import get_snapshot_path, load_snapshot

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

    def test_initial_release_with_message_records_entry(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            result = runner.invoke(
                main, ["release", "-m", "Init my service"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Initial release recorded" in result.output

            snapshot = load_snapshot("test_svc", config=None, root_dir=project_dir)
            assert snapshot is not None

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 1
            assert changelog[0]["revision"] == 1
            assert changelog[0]["message"] == "Init my service"
            # Initial entry has no characteristics: block (only changes, not state).
            assert "characteristics" not in changelog[0]

    def test_initial_release_editor_defaults_to_initial_schema(self, project_dir, monkeypatch):
        """No -m on initial release → editor returns template unchanged → 'Initial schema' recorded."""
        def fake_edit(text=None, **kw):
            return text  # user saved without changes

        monkeypatch.setattr("click.edit", fake_edit)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            result = runner.invoke(main, ["release"], catch_exceptions=False)
            assert result.exit_code == 0

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 1
            assert changelog[0]["message"] == "Initial schema"

    def test_initial_release_editor_abort_creates_nothing(self, project_dir, monkeypatch):
        """User wipes body → abort → no snapshot, no changelog file, no dir."""
        def fake_edit(text=None, **kw):
            return ""  # user cleared everything

        monkeypatch.setattr("click.edit", fake_edit)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            result = runner.invoke(main, ["release"], catch_exceptions=False)
            assert "Aborted" in result.output
            assert load_snapshot("test_svc", config=None, root_dir=project_dir) is None
            assert load_changelog("test_svc", config=None, root_dir=project_dir) == []
            # No orphan empty changelog dir
            assert not (project_dir / "gattc" / "changelog" / "test_svc").exists()

    def test_initial_release_editor_true_abort_returns_none(self, project_dir, monkeypatch):
        """click.edit returning None (editor failed / user Ctrl+C'd) → clean abort."""
        def fake_edit(text=None, **kw):
            return None

        monkeypatch.setattr("click.edit", fake_edit)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            result = runner.invoke(main, ["release"], catch_exceptions=False)
            assert "Aborted" in result.output
            assert load_snapshot("test_svc", config=None, root_dir=project_dir) is None
            assert load_changelog("test_svc", config=None, root_dir=project_dir) == []
            assert not (project_dir / "gattc" / "changelog" / "test_svc").exists()

    def test_inconsistent_state_fails_loudly(self, project_dir):
        """If changelog has entries but no snapshot, release must refuse with a clear error."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)

            # Simulate the old orphan bug: delete the snapshot but keep the changelog.
            snapshot_path = get_snapshot_path("test_svc", config=None, root_dir=project_dir)
            snapshot_path.unlink()

            result = runner.invoke(main, ["release", "-m", "Another"], catch_exceptions=False)
            assert result.exit_code != 0
            assert "inconsistent state" in result.output.lower()

    def test_release_records_changes_with_message(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)

            modified = MINIMAL_SCHEMA.replace("temperature: uint16", "temperature: uint32")
            (project_dir / "gattc" / "test_svc.yaml").write_text(modified)

            result = runner.invoke(
                main, ["release", "-m", "Upgraded to uint32 for precision"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Changes recorded" in result.output

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 2
            assert changelog[0]["revision"] == 1
            assert changelog[0]["message"] == "Initial"
            assert changelog[1]["revision"] == 2
            assert changelog[1]["message"] == "Upgraded to uint32 for precision"

    def test_allow_empty_records_entry_without_schema_changes(self, project_dir):
        """--allow-empty should create a changelog entry when schema hasn't changed."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)

            result = runner.invoke(
                main, ["release", "--allow-empty", "-m", "Build 2.3.1 re-tag"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Empty release recorded" in result.output

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 2
            assert changelog[1]["revision"] == 2
            assert changelog[1]["message"] == "Build 2.3.1 re-tag"
            # Empty release entry has no characteristics: block.
            assert "characteristics" not in changelog[1]

    def test_allow_empty_is_noop_when_changes_exist(self, project_dir):
        """--allow-empty with real changes still follows the normal 'changed' path."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
            (project_dir / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)

            result = runner.invoke(
                main, ["release", "--allow-empty", "-m", "Upgrade"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Changes recorded" in result.output

            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 2
            assert "characteristics" in changelog[1]

    def test_release_no_changes(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)

            result = runner.invoke(
                main, ["release", "-m", "Nothing changed"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "No changes" in result.output

            # Only the initial entry exists; the second call recorded nothing.
            changelog = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(changelog) == 1
            assert changelog[0]["message"] == "Initial"


class TestChangelogFiles:

    def test_release_writes_md_file_with_frontmatter(self, project_dir):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
            (project_dir / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)
            runner.invoke(main, ["release", "-m", "Upgrade to uint32"], catch_exceptions=False)

            changelog_dir = get_changelog_dir("test_svc", config=None, root_dir=project_dir)
            rev_file = changelog_dir / "002.md"
            assert rev_file.exists()

            content = rev_file.read_text(encoding="utf-8")
            assert content.startswith("---\n")
            assert "revision: 2" in content
            assert "Upgrade to uint32" in content
            assert "characteristics:" in content  # this entry has diff data

    def test_release_editor_aborts_on_empty_body(self, project_dir, monkeypatch):
        """Editor flow on a real change: empty body → no new entry, old state preserved."""
        def fake_edit(text=None, **kw):
            return ""  # user cleared the template and saved empty

        monkeypatch.setattr("click.edit", fake_edit)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
            (project_dir / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)
            result = runner.invoke(main, ["release"], catch_exceptions=False)
            assert "Aborted" in result.output

            entries = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(entries) == 1
            assert entries[0]["message"] == "Initial"

            # No orphan 002.md on disk.
            changelog_dir = get_changelog_dir("test_svc", config=None, root_dir=project_dir)
            assert not (changelog_dir / "002.md").exists()

    def test_release_editor_records_typed_body(self, project_dir, monkeypatch):
        """Editor flow: user saves a real message → entry recorded."""
        def fake_edit(text=None, **kw):
            # Strip template markers and substitute a typed message.
            return "New feature: added unit byte.\n"

        monkeypatch.setattr("click.edit", fake_edit)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_dir):
            runner.invoke(main, ["release", "-m", "Initial"], catch_exceptions=False)
            (project_dir / "gattc" / "test_svc.yaml").write_text(MODIFIED_SCHEMA)
            runner.invoke(main, ["release"], catch_exceptions=False)

            entries = load_changelog("test_svc", config=None, root_dir=project_dir)
            assert len(entries) == 2
            assert "New feature" in entries[1]["message"]

    def test_initial_release_with_docs_output_regenerates(self, tmp_path):
        """Initial entry (no 'characteristics' key) must not crash the docs template."""
        schema_dir = tmp_path / "gattc"
        schema_dir.mkdir()
        (schema_dir / "test_svc.yaml").write_text(MINIMAL_SCHEMA)
        (tmp_path / "gattc.yaml").write_text(
            'schemas:\n  - "gattc/"\n'
            'output:\n  zephyr:\n    header: "out/"\n  docs:\n    path: "docs/"\n'
        )

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                main, ["release", "-m", "Initial"], catch_exceptions=False
            )
            assert result.exit_code == 0
            assert "Initial release recorded" in result.output
            # Docs file should have been generated without template errors.
            assert any((tmp_path / "docs").glob("*.md"))

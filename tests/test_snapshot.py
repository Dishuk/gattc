"""Tests for gattc snapshot and changelog functionality."""

from gattc.snapshot import (
    get_snapshot_dir,
    get_snapshot_path,
    load_snapshot,
    save_snapshot,
    snapshot_exists,
    DEFAULT_SNAPSHOT_PATH,
)
from gattc.changelog import build_frontmatter, load_changelog, next_revision, write_entry
from gattc.diff import diff_schemas
from gattc.schema import Schema, Service, Characteristic, Payload, Field, TypeInfo
from gattc.config import load_config


class TestGetSnapshotDir:
    """Tests for get_snapshot_dir function."""

    def test_default_path_no_config(self, tmp_path):
        """Test default snapshot path when no config provided."""
        snapshot_dir = get_snapshot_dir(config=None, root_dir=tmp_path)
        assert snapshot_dir == tmp_path / DEFAULT_SNAPSHOT_PATH

    def test_custom_path_from_config(self, tmp_path):
        """Test custom snapshot path from config."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
snapshots:
  path: "custom/snapshots"
''')
        config = load_config(config_file)

        snapshot_dir = get_snapshot_dir(config=config, root_dir=tmp_path)
        assert snapshot_dir == tmp_path / "custom/snapshots"

    def test_snapshots_string_shorthand(self, tmp_path):
        """Test snapshots config as string shorthand."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
snapshots: "my_snapshots/"
''')
        config = load_config(config_file)

        snapshot_dir = get_snapshot_dir(config=config, root_dir=tmp_path)
        assert snapshot_dir == tmp_path / "my_snapshots/"


class TestGetSnapshotPath:
    """Tests for get_snapshot_path function."""

    def test_snapshot_path_format(self, tmp_path):
        """Test snapshot path includes service name and .json extension."""
        path = get_snapshot_path("my_service", config=None, root_dir=tmp_path)
        assert path == tmp_path / DEFAULT_SNAPSHOT_PATH / "my_service.json"

    def test_snapshot_path_with_custom_config(self, tmp_path):
        """Test snapshot path with custom config."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
snapshots:
  path: "data/snapshots"
''')
        config = load_config(config_file)

        path = get_snapshot_path("test_service", config=config, root_dir=tmp_path)
        assert path == tmp_path / "data/snapshots/test_service.json"


class TestSnapshotExists:
    """Tests for snapshot_exists function."""

    def test_returns_false_when_not_exists(self, tmp_path):
        """Test returns False when snapshot doesn't exist."""
        assert snapshot_exists("nonexistent", config=None, root_dir=tmp_path) is False

    def test_returns_true_when_exists(self, tmp_path):
        """Test returns True when snapshot exists."""
        # Create a snapshot file
        snapshot_dir = tmp_path / DEFAULT_SNAPSHOT_PATH
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "existing_service.json").write_text("{}")

        assert snapshot_exists("existing_service", config=None, root_dir=tmp_path) is True


class TestSaveAndLoadSnapshot:
    """Tests for save_snapshot and load_snapshot functions."""

    def _create_test_schema(self) -> Schema:
        """Create a simple test schema."""
        return Schema(
            schema_version="1.0",
            service=Service(
                name="test_service",
                uuid="12345678-1234-1234-1234-123456789abc",
                description="Test service"
            ),
            characteristics=[
                Characteristic(
                    name="test_char",
                    uuid="12345678-1234-1234-1234-000000000001",
                    properties=["read", "write"],
                    permissions=["read", "write"],
                    description="Test characteristic"
                )
            ]
        )

    def test_load_returns_none_when_not_exists(self, tmp_path):
        """Test load_snapshot returns None when file doesn't exist."""
        data = load_snapshot("nonexistent", config=None, root_dir=tmp_path)
        assert data is None

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test saving and loading preserves schema data."""
        schema = self._create_test_schema()

        save_snapshot("test_service", schema, config=None, root_dir=tmp_path)
        loaded = load_snapshot("test_service", config=None, root_dir=tmp_path)

        assert loaded is not None
        assert loaded["schema_version"] == "1.0"
        assert loaded["service"]["name"] == "test_service"
        assert loaded["service"]["uuid"] == "12345678-1234-1234-1234-123456789abc"
        assert len(loaded["characteristics"]) == 1
        assert loaded["characteristics"][0]["name"] == "test_char"

    def test_save_with_schema_revision(self, tmp_path):
        """Test saving schema with revision number."""
        schema = Schema(
            schema_version="1.0",
            service=Service(
                name="versioned_service",
                uuid="12345678-1234-1234-1234-123456789abc",
            ),
            characteristics=[],
            schema_revision=5
        )

        save_snapshot("versioned_service", schema, config=None, root_dir=tmp_path)
        loaded = load_snapshot("versioned_service", config=None, root_dir=tmp_path)

        assert loaded["schema_revision"] == 5

    def test_save_overwrites_existing(self, tmp_path):
        """Test save_snapshot overwrites existing snapshot."""
        schema1 = Schema(
            schema_version="1.0",
            service=Service(name="svc", uuid="12345678-1234-1234-1234-123456789abc"),
            characteristics=[]
        )
        schema2 = Schema(
            schema_version="2.0",
            service=Service(name="svc", uuid="12345678-1234-1234-1234-123456789abc"),
            characteristics=[]
        )

        save_snapshot("svc", schema1, config=None, root_dir=tmp_path)
        save_snapshot("svc", schema2, config=None, root_dir=tmp_path)

        loaded = load_snapshot("svc", config=None, root_dir=tmp_path)
        assert loaded["schema_version"] == "2.0"


class TestChangelogMessage:
    """Tests for changelog message field."""

    def _make_schema(self, name="svc", uuid="12345678-1234-1234-1234-123456789abc", fields=None):
        chars = []
        if fields is not None:
            chars = [Characteristic(
                name="char1",
                uuid="12345678-1234-1234-1234-123456789ab0",
                properties=["read"],
                permissions=["read"],
                payload=Payload(fields=fields),
            )]
        return Schema(
            schema_version="1.0",
            service=Service(name=name, uuid=uuid),
            characteristics=chars,
        )

    def test_add_entry_includes_message(self, tmp_path):
        """Changelog entry should contain the provided message."""
        old_schema = self._make_schema(fields=[
            Field(name="temp", type_info=TypeInfo(base="uint8", size=1, endian="none", is_array=False), offset=0),
        ])
        new_schema = self._make_schema(fields=[
            Field(name="temp", type_info=TypeInfo(base="uint16", size=2, endian="little", is_array=False), offset=0),
        ])

        save_snapshot("svc", old_schema, config=None, root_dir=tmp_path)
        snapshot = load_snapshot("svc", config=None, root_dir=tmp_path)
        diff = diff_schemas(snapshot, new_schema)

        rev = next_revision("svc", config=None, root_dir=tmp_path)
        write_entry(
            "svc", rev, build_frontmatter(diff, rev),
            "Changed temp to uint16 for better precision",
            config=None, root_dir=tmp_path,
        )
        entries = load_changelog("svc", config=None, root_dir=tmp_path)

        assert len(entries) == 1
        assert entries[0]["message"] == "Changed temp to uint16 for better precision"


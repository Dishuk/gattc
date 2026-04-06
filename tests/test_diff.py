"""Tests for gattc schema diffing functionality."""

import pytest

from gattc.diff import (
    diff_schemas,
    SchemaDiff,
    CharacteristicChange,
    FieldChange,
    _compare_fields,
    _format_type_info,
)
from gattc.schema import (
    Schema,
    Service,
    Characteristic,
    Payload,
    Field,
    TypeInfo,
)
from gattc.snapshot import _schema_to_dict


class TestDiffSchemas:
    """Tests for diff_schemas function."""

    def _create_schema(
        self,
        name: str = "test_service",
        version: str = "1.0",
        characteristics: list = None
    ) -> Schema:
        """Create a test schema."""
        if characteristics is None:
            characteristics = []
        return Schema(
            schema_version=version,
            service=Service(
                name=name,
                uuid="12345678-1234-1234-1234-123456789abc",
            ),
            characteristics=characteristics
        )

    def _create_characteristic(
        self,
        name: str,
        properties: list = None,
        permissions: list = None,
        payload: Payload = None
    ) -> Characteristic:
        """Create a test characteristic."""
        return Characteristic(
            name=name,
            uuid=f"12345678-1234-1234-1234-{name[:12].ljust(12, '0')}",
            properties=properties or ["read"],
            permissions=permissions or ["read"],
            payload=payload
        )

    def test_no_changes_when_identical(self):
        """Test no changes detected for identical schemas."""
        schema = self._create_schema()
        old_dict = _schema_to_dict(schema)

        diff = diff_schemas(old_dict, schema)

        assert diff.has_changes is False
        assert diff.service_name == "test_service"
        assert len(diff.characteristic_changes) == 0

    def test_no_changes_when_no_snapshot(self):
        """Test no changes when no previous snapshot exists."""
        schema = self._create_schema()

        diff = diff_schemas(None, schema)

        assert diff.has_changes is False
        assert diff.service_name == "test_service"

    def test_detects_added_characteristic(self):
        """Test detection of added characteristic."""
        old_schema = self._create_schema(characteristics=[])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("new_char")
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].name == "new_char"
        assert diff.characteristic_changes[0].change_type == "added"

    def test_detects_removed_characteristic(self):
        """Test detection of removed characteristic."""
        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("old_char")
        ])
        new_schema = self._create_schema(characteristics=[])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].name == "old_char"
        assert diff.characteristic_changes[0].change_type == "removed"

    def test_detects_modified_characteristic_properties(self):
        """Test detection of modified characteristic properties."""
        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", properties=["read"])
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", properties=["read", "write"])
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].name == "char"
        assert diff.characteristic_changes[0].change_type == "modified"
        assert any("write" in p for p in diff.characteristic_changes[0].property_changes)

    def test_detects_schema_version_change(self):
        """Test detection of schema version change."""
        old_schema = self._create_schema(version="1.0")
        new_schema = self._create_schema(version="2.0")

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert diff.schema_version_changed is True
        assert diff.old_schema_version == "1.0"
        assert diff.new_schema_version == "2.0"

    def test_detects_added_field(self):
        """Test detection of added field in payload."""
        old_payload = Payload(fields=[
            Field(name="existing", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))
        ])
        new_payload = Payload(fields=[
            Field(name="existing", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            )),
            Field(name="new_field", type_info=TypeInfo(
                base="uint16", size=2, endian="little", is_array=False
            ))
        ])

        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=old_payload)
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=new_payload)
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        char_change = diff.characteristic_changes[0]
        assert char_change.change_type == "modified"
        assert any(fc.name == "new_field" and fc.change_type == "added"
                   for fc in char_change.field_changes)

    def test_detects_removed_field(self):
        """Test detection of removed field in payload."""
        old_payload = Payload(fields=[
            Field(name="keep", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            )),
            Field(name="remove", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))
        ])
        new_payload = Payload(fields=[
            Field(name="keep", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))
        ])

        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=old_payload)
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=new_payload)
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        char_change = diff.characteristic_changes[0]
        assert any(fc.name == "remove" and fc.change_type == "removed"
                   for fc in char_change.field_changes)

    def test_detects_modified_field_type(self):
        """Test detection of modified field type."""
        old_payload = Payload(fields=[
            Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))
        ])
        new_payload = Payload(fields=[
            Field(name="data", type_info=TypeInfo(
                base="uint16", size=2, endian="little", is_array=False
            ))
        ])

        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=old_payload)
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=new_payload)
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        char_change = diff.characteristic_changes[0]
        field_change = next(fc for fc in char_change.field_changes if fc.name == "data")
        assert field_change.change_type == "modified"
        assert "uint8" in field_change.details
        assert "uint16" in field_change.details


class TestSchemaDiffMethods:
    """Tests for SchemaDiff helper methods."""

    def test_to_changelog_text_no_changes(self):
        """Test changelog text when no changes."""
        diff = SchemaDiff(
            service_name="test",
            has_changes=False
        )

        text = diff.to_changelog_text()
        assert "No changes" in text

    def test_to_changelog_text_with_changes(self):
        """Test changelog text with various changes."""
        diff = SchemaDiff(
            service_name="test",
            has_changes=True,
            characteristic_changes=[
                CharacteristicChange(name="new_char", change_type="added"),
                CharacteristicChange(name="old_char", change_type="removed"),
                CharacteristicChange(
                    name="mod_char",
                    change_type="modified",
                    field_changes=[
                        FieldChange(name="new_field", change_type="added", new_value="uint16"),
                        FieldChange(name="old_field", change_type="removed"),
                    ],
                    property_changes=["+ Properties: write"],
                    offsets_changed=True
                )
            ]
        )

        text = diff.to_changelog_text()

        assert "Added characteristic: new_char" in text
        assert "Removed characteristic: old_char" in text
        assert "Modified: mod_char" in text
        assert "+ new_field" in text
        assert "- old_field" in text
        assert "Properties: write" in text
        assert "Payload offsets changed" in text

    def test_get_characteristic_status(self):
        """Test getting characteristic change status."""
        diff = SchemaDiff(
            service_name="test",
            has_changes=True,
            characteristic_changes=[
                CharacteristicChange(name="added", change_type="added"),
                CharacteristicChange(name="modified", change_type="modified"),
            ]
        )

        assert diff.get_characteristic_status("added") == "added"
        assert diff.get_characteristic_status("modified") == "modified"
        assert diff.get_characteristic_status("unchanged") is None

    def test_get_field_status(self):
        """Test getting field change status."""
        diff = SchemaDiff(
            service_name="test",
            has_changes=True,
            characteristic_changes=[
                CharacteristicChange(
                    name="char",
                    change_type="modified",
                    field_changes=[
                        FieldChange(name="new_field", change_type="added"),
                        FieldChange(name="changed_field", change_type="modified"),
                    ]
                )
            ]
        )

        assert diff.get_field_status("char", "new_field") == "added"
        assert diff.get_field_status("char", "changed_field") == "modified"
        assert diff.get_field_status("char", "unchanged") is None
        assert diff.get_field_status("other_char", "any") is None


class TestFormatTypeInfo:
    """Tests for _format_type_info helper function."""

    def test_simple_type(self):
        """Test formatting simple type."""
        type_info = {"base": "uint8", "size": 1, "endian": "none", "is_array": False}
        assert _format_type_info(type_info) == "uint8"

    def test_big_endian_type(self):
        """Test formatting big endian type."""
        type_info = {"base": "uint16", "size": 2, "endian": "big", "is_array": False}
        assert _format_type_info(type_info) == "uint16_be"

    def test_fixed_array_type(self):
        """Test formatting fixed array type."""
        type_info = {"base": "uint8", "size": 1, "endian": "none", "is_array": True, "array_size": 10}
        assert _format_type_info(type_info) == "uint8[10]"

    def test_dynamic_array_type(self):
        """Test formatting dynamic array type."""
        type_info = {"base": "bytes", "size": 1, "endian": "none", "is_array": True, "array_size": None}
        assert _format_type_info(type_info) == "bytes[]"

    def test_empty_type_info(self):
        """Test formatting empty type info."""
        assert _format_type_info({}) == "unknown"
        assert _format_type_info(None) == "unknown"


class TestCompareFields:
    """Tests for _compare_fields helper function."""

    def test_no_changes(self):
        """Test no changes when fields identical."""
        fields = [
            {"name": "a", "type_info": {"base": "uint8", "size": 1}},
            {"name": "b", "type_info": {"base": "uint16", "size": 2}},
        ]

        changes, offsets_changed = _compare_fields(fields, fields)
        assert len(changes) == 0
        assert offsets_changed is False

    def test_added_field(self):
        """Test detecting added field."""
        old = [{"name": "a", "type_info": {"base": "uint8", "size": 1}}]
        new = [
            {"name": "a", "type_info": {"base": "uint8", "size": 1}},
            {"name": "b", "type_info": {"base": "uint16", "size": 2}},
        ]

        changes, offsets_changed = _compare_fields(old, new)

        assert len(changes) == 1
        assert changes[0].name == "b"
        assert changes[0].change_type == "added"

    def test_removed_field(self):
        """Test detecting removed field."""
        old = [
            {"name": "a", "type_info": {"base": "uint8", "size": 1}},
            {"name": "b", "type_info": {"base": "uint16", "size": 2}},
        ]
        new = [{"name": "a", "type_info": {"base": "uint8", "size": 1}}]

        changes, offsets_changed = _compare_fields(old, new)

        assert len(changes) == 1
        assert changes[0].name == "b"
        assert changes[0].change_type == "removed"

    def test_modified_field(self):
        """Test detecting modified field."""
        old = [{"name": "a", "type_info": {"base": "uint8", "size": 1, "endian": "none", "is_array": False}}]
        new = [{"name": "a", "type_info": {"base": "uint16", "size": 2, "endian": "little", "is_array": False}}]

        changes, offsets_changed = _compare_fields(old, new)

        assert len(changes) == 1
        assert changes[0].name == "a"
        assert changes[0].change_type == "modified"
        assert "uint8" in changes[0].details
        assert "uint16" in changes[0].details

    def test_field_reorder_detected(self):
        """Test detecting field reordering via offset change flag."""
        old = [
            {"name": "first", "type_info": {"base": "uint8", "size": 1}, "offset": 0},
            {"name": "last", "type_info": {"base": "uint8", "size": 1}, "offset": 1},
        ]
        new = [
            {"name": "last", "type_info": {"base": "uint8", "size": 1}, "offset": 0},
            {"name": "first", "type_info": {"base": "uint8", "size": 1}, "offset": 1},
        ]

        changes, offsets_changed = _compare_fields(old, new)

        # Offset-only changes don't create field_changes, just set the flag
        assert len(changes) == 0
        assert offsets_changed is True


class TestNewChangeDetection:
    """Tests for new change detection cases."""

    def _create_schema(
        self,
        name: str = "test_service",
        version: str = "1.0",
        uuid: str = "12345678-1234-1234-1234-123456789abc",
        description: str = "",
        characteristics: list = None,
        schema_revision: int = None
    ) -> Schema:
        """Create a test schema."""
        if characteristics is None:
            characteristics = []
        return Schema(
            schema_version=version,
            service=Service(
                name=name,
                uuid=uuid,
                description=description,
            ),
            characteristics=characteristics,
            schema_revision=schema_revision
        )

    def _create_characteristic(
        self,
        name: str,
        properties: list = None,
        permissions: list = None,
        payload: Payload = None,
        description: str = ""
    ) -> Characteristic:
        """Create a test characteristic."""
        return Characteristic(
            name=name,
            uuid=f"12345678-1234-1234-1234-{name[:12].ljust(12, '0')}",
            properties=properties or ["read"],
            permissions=permissions or ["read"],
            payload=payload,
            description=description
        )

    def test_detects_service_name_changed(self):
        """Test detection of service name change."""
        old_schema = self._create_schema(name="old_service")
        new_schema = self._create_schema(name="new_service")

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert "Service name changed" in diff.service_changes

    def test_detects_service_uuid_changed(self):
        """Test detection of service UUID change."""
        old_schema = self._create_schema(uuid="12345678-1234-1234-1234-123456789abc")
        new_schema = self._create_schema(uuid="87654321-4321-4321-4321-cba987654321")

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert "Service UUID changed" in diff.service_changes

    def test_detects_service_description_changed(self):
        """Test detection of service description change."""
        old_schema = self._create_schema(description="Old description")
        new_schema = self._create_schema(description="New description")

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert "Service description changed" in diff.service_changes

    def test_detects_characteristic_description_changed(self):
        """Test detection of characteristic description change."""
        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", description="Old description")
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", description="New description")
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].description_changed is True

    def test_detects_payload_mode_changed(self):
        """Test detection of payload mode change."""
        old_payload = Payload(
            fields=[Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))],
            mode="variable"
        )
        new_payload = Payload(
            fields=[Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))],
            mode="mtu_packed"
        )

        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=old_payload)
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=new_payload)
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].payload_config_changed is True

    def test_detects_payload_min_size_changed(self):
        """Test detection of payload min_size change."""
        old_payload = Payload(
            fields=[Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))],
            min_size=1
        )
        new_payload = Payload(
            fields=[Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))],
            min_size=2
        )

        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=old_payload)
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=new_payload)
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].payload_config_changed is True

    def test_detects_payload_max_size_changed(self):
        """Test detection of payload max_size change."""
        old_payload = Payload(
            fields=[Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))],
            max_size=100
        )
        new_payload = Payload(
            fields=[Field(name="data", type_info=TypeInfo(
                base="uint8", size=1, endian="none", is_array=False
            ))],
            max_size=200
        )

        old_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=old_payload)
        ])
        new_schema = self._create_schema(characteristics=[
            self._create_characteristic("char", payload=new_payload)
        ])

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert len(diff.characteristic_changes) == 1
        assert diff.characteristic_changes[0].payload_config_changed is True

    def test_detects_schema_revision_changed(self):
        """Test detection of schema_revision change."""
        old_schema = self._create_schema(schema_revision=1)
        new_schema = self._create_schema(schema_revision=2)

        old_dict = _schema_to_dict(old_schema)
        diff = diff_schemas(old_dict, new_schema)

        assert diff.has_changes is True
        assert diff.schema_revision_changed is True
        assert diff.old_schema_revision == 1
        assert diff.new_schema_revision == 2

    def test_detects_nested_struct_fields_changed(self):
        """Test detection of nested struct field changes."""
        old = [
            {
                "name": "items",
                "type_info": {"base": "struct", "size": 2, "endian": "none", "is_array": True, "is_repeated_struct": True},
                "fields": [
                    {"name": "a", "type_info": {"base": "uint8", "size": 1}}
                ]
            }
        ]
        new = [
            {
                "name": "items",
                "type_info": {"base": "struct", "size": 4, "endian": "none", "is_array": True, "is_repeated_struct": True},
                "fields": [
                    {"name": "a", "type_info": {"base": "uint8", "size": 1}},
                    {"name": "b", "type_info": {"base": "uint8", "size": 1}}
                ]
            }
        ]

        changes, offsets_changed = _compare_fields(old, new)

        assert len(changes) == 1
        assert changes[0].name == "items"
        assert changes[0].change_type == "modified"
        assert "struct fields changed" in changes[0].details

    def test_to_changelog_text_includes_new_changes(self):
        """Test changelog text includes new change types."""
        diff = SchemaDiff(
            service_name="test",
            has_changes=True,
            service_changes=["Service description changed"],
            schema_revision_changed=True,
            old_schema_revision=1,
            new_schema_revision=2,
            characteristic_changes=[
                CharacteristicChange(
                    name="char",
                    change_type="modified",
                    description_changed=True,
                    payload_config_changed=True
                )
            ]
        )

        text = diff.to_changelog_text()

        assert "Schema revision: 1 -> 2" in text
        assert "Service description changed" in text
        assert "Description changed" in text
        assert "Payload config changed" in text

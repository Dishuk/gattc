"""Tests for gattc configuration loading."""

import pytest
from pathlib import Path

from gattc.config import load_config, find_config, find_schemas, Config, OutputConfig


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_simple_config(self, tmp_path):
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"
''')

        config = load_config(config_file)

        assert config is not None
        assert config.schemas == [tmp_path / "gattc/"]
        assert config.output.zephyr.header == tmp_path / "src/generated/"
        assert config.output.zephyr.get_header_path() == tmp_path / "src/generated/"
        assert config.output.zephyr.get_source_path() == tmp_path / "src/generated/"

    def test_load_full_config(self, tmp_path):
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas:
  - "gattc/"
  - "services/"

output:
  zephyr:
    header: "src/generated/"
  docs:
    path: "docs/ble/"
''')

        config = load_config(config_file)

        assert config is not None
        assert len(config.schemas) == 2
        assert config.schemas[0] == tmp_path / "gattc/"
        assert config.schemas[1] == tmp_path / "services/"
        assert config.output.zephyr.header == tmp_path / "src/generated/"
        assert config.output.docs.path == tmp_path / "docs/ble/"

    def test_load_config_with_docs_shorthand(self, tmp_path):
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"
docs: "docs/"
''')

        config = load_config(config_file)

        assert config.output.zephyr.header == tmp_path / "src/generated/"
        assert config.output.docs.path == tmp_path / "docs/"

    def test_load_config_with_docs_per_service(self, tmp_path):
        """Test loading config with docs per_service setting."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"
  docs:
    path: "docs/ble/"
    per_service: false
''')

        config = load_config(config_file)

        assert config is not None
        assert config.output.docs.path == tmp_path / "docs/ble/"
        assert config.output.docs.per_service is False
        assert config.output.docs.is_combined() is True

    def test_load_config_with_zephyr_per_service(self, tmp_path):
        """Test loading config with zephyr per_service setting."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "include/generated/"
    source: "src/generated/"
    per_service: false
''')

        config = load_config(config_file)

        assert config is not None
        assert config.output.zephyr.header == tmp_path / "include/generated/"
        assert config.output.zephyr.source == tmp_path / "src/generated/"
        assert config.output.zephyr.per_service is False
        assert config.output.zephyr.is_combined() is True

    def test_load_config_with_separate_paths(self, tmp_path):
        """Test loading config with separate header and source paths."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "include/generated/"
    source: "src/generated/"
''')

        config = load_config(config_file)

        assert config is not None
        assert config.output.zephyr.header == tmp_path / "include/generated/"
        assert config.output.zephyr.source == tmp_path / "src/generated/"
        assert config.output.zephyr.get_header_path() == tmp_path / "include/generated/"
        assert config.output.zephyr.get_source_path() == tmp_path / "src/generated/"

    def test_load_config_with_per_service_override(self, tmp_path):
        """Test loading config with per-service configuration."""
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"

services:
  special_service:
    output:
      zephyr:
        header: "include/special/"
        source: "src/special/"
''')

        config = load_config(config_file)

        assert config is not None
        # Default output
        assert config.output.zephyr.header == tmp_path / "src/generated/"
        # Per-service override
        service_config = config.get_service_config("special_service")
        assert service_config.output.zephyr.header == tmp_path / "include/special/"
        assert service_config.output.zephyr.source == tmp_path / "src/special/"
        # Non-existent service returns empty config
        other_config = config.get_service_config("other_service")
        assert other_config.output.zephyr.get_header_path() is None

    def test_load_empty_config(self, tmp_path):
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('')

        config = load_config(config_file)

        assert config is not None
        assert config.schemas == []

    def test_load_nonexistent_returns_none(self):
        config = load_config(Path("/nonexistent/gattc.yaml"))
        assert config is None


class TestFindConfig:
    """Tests for find_config function."""

    def test_find_in_current_dir(self, tmp_path):
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text("schemas: gattc/")

        found = find_config(tmp_path)

        assert found == config_file

    def test_find_in_parent_dir(self, tmp_path):
        config_file = tmp_path / "gattc.yaml"
        config_file.write_text("schemas: gattc/")

        subdir = tmp_path / "src" / "bluetooth"
        subdir.mkdir(parents=True)

        found = find_config(subdir)

        assert found == config_file

    def test_not_found_returns_none(self, tmp_path):
        found = find_config(tmp_path)
        assert found is None


class TestFindSchemas:
    """Tests for find_schemas function."""

    def test_find_yaml_files(self, tmp_path):
        gatt_dir = tmp_path / "gatt"
        gatt_dir.mkdir()

        (gatt_dir / "sensor.yaml").write_text("test: 1")
        (gatt_dir / "config.yaml").write_text("test: 2")
        (gatt_dir / "readme.txt").write_text("ignore")

        config = Config(schemas=[gatt_dir])
        schemas = find_schemas(config)

        assert len(schemas) == 2
        assert all(s.suffix == ".yaml" for s in schemas)

    def test_ignores_gattc_yaml(self, tmp_path):
        gatt_dir = tmp_path / "gatt"
        gatt_dir.mkdir()

        (gatt_dir / "sensor.yaml").write_text("test: 1")
        (gatt_dir / "gattc.yaml").write_text("test: 2")

        config = Config(schemas=[gatt_dir])
        schemas = find_schemas(config)

        assert len(schemas) == 1
        assert schemas[0].name == "sensor.yaml"

    def test_multiple_directories(self, tmp_path):
        dir1 = tmp_path / "gatt"
        dir2 = tmp_path / "services"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "a.yaml").write_text("test: 1")
        (dir2 / "b.yaml").write_text("test: 2")

        config = Config(schemas=[dir1, dir2])
        schemas = find_schemas(config)

        assert len(schemas) == 2

    def test_nonexistent_directory(self, tmp_path):
        config = Config(schemas=[tmp_path / "nonexistent"])
        schemas = find_schemas(config)

        assert schemas == []


class TestServiceConfigValidation:
    """Tests for per-service configuration validation."""

    def test_validate_service_configs_valid(self, tmp_path):
        """Test validation passes when service config matches found service."""
        from gattc.config import validate_service_configs

        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"
services:
  test_service:
    output:
      zephyr:
        header: "include/special/"
''')
        config = load_config(config_file)
        found_services = {"test_service", "other_service"}

        errors = validate_service_configs(config, found_services)

        assert errors == []

    def test_validate_service_configs_invalid(self, tmp_path):
        """Test validation fails when service config doesn't match any service."""
        from gattc.config import validate_service_configs

        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"
services:
  nonexistent_service:
    output:
      zephyr:
        header: "include/special/"
''')
        config = load_config(config_file)
        found_services = {"test_service", "other_service"}

        errors = validate_service_configs(config, found_services)

        assert len(errors) == 1
        assert "nonexistent_service" in errors[0]
        assert "not found" in errors[0]

    def test_validate_service_configs_multiple_invalid(self, tmp_path):
        """Test validation reports all invalid service configs."""
        from gattc.config import validate_service_configs

        config_file = tmp_path / "gattc.yaml"
        config_file.write_text('''
schemas: "gattc/"
output:
  zephyr:
    header: "src/generated/"
services:
  missing_one:
    output:
      zephyr:
        header: "out1/"
  missing_two:
    output:
      zephyr:
        header: "out2/"
''')
        config = load_config(config_file)
        found_services = {"actual_service"}

        errors = validate_service_configs(config, found_services)

        assert len(errors) == 2
        assert any("missing_one" in e for e in errors)
        assert any("missing_two" in e for e in errors)

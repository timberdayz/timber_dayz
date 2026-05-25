from pathlib import Path
import re


def test_field_mapping_template_schema_defines_header_bindings_column():
    source = Path("modules/core/db/schema_parts/data_platform.py").read_text(encoding="utf-8")

    assert "header_bindings = Column(JSONB" in source
    assert "header_bindings" in source


def test_field_mapping_template_header_bindings_migration_exists():
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*header_bindings*.py"))
    assert matches, "expected a header-bindings migration in migrations/versions"


def test_field_mapping_template_header_bindings_migration_declares_revision():
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*header_bindings*.py"))
    assert matches, "expected a header-bindings migration in migrations/versions"
    source = matches[-1].read_text(encoding="utf-8")

    assert re.search(r'^revision\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert re.search(r'^down_revision\s*=\s*"([^"]+)"', source, re.MULTILINE)

from pathlib import Path

from modules.core.db import CatalogFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_UPDATE_REQUIRED = "template_update_required"


def test_catalog_file_status_column_can_store_template_update_required():
    status_column = CatalogFile.__table__.c.status

    assert status_column.type.length >= 64
    assert status_column.type.length >= len(TEMPLATE_UPDATE_REQUIRED)


def test_active_migration_expands_catalog_file_status_for_template_update_required():
    migration_path = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260618_expand_catalog_file_status_for_template_update.py"
    )

    assert migration_path.exists()
    migration_text = migration_path.read_text(encoding="utf-8")
    assert TEMPLATE_UPDATE_REQUIRED in migration_text
    assert "VARCHAR(64)" in migration_text or "String(64)" in migration_text
    assert "ck_catalog_files_status" in migration_text


def test_data_sync_files_frontend_exposes_template_update_required_state():
    view_text = (
        PROJECT_ROOT
        / "frontend"
        / "src"
        / "domains"
        / "data_platform"
        / "views"
        / "DataSyncFiles.vue"
    ).read_text(encoding="utf-8")

    assert "value=\"template_update_required\"" in view_text
    assert "value: 'template_update_required'" in view_text
    assert "getFileStatusType(row.status)" in view_text
    assert "getFileStatusText(row.status)" in view_text
    assert "isTemplateUpdateRequiredHistory(row)" in view_text

from pathlib import Path


MIGRATION_TABLES = (
    "cloud_b_class_sync_checkpoints",
    "cloud_b_class_sync_runs",
    "cloud_b_class_sync_tasks",
)


def test_cloud_sync_tables_are_covered_by_alembic_migration():
    versions_dir = Path("migrations/versions")

    matching_files = []
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if all(table_name in text for table_name in MIGRATION_TABLES):
            matching_files.append(path.name)

    assert matching_files, (
        "Expected an Alembic migration under migrations/versions to create "
        "cloud sync state tables"
    )


def test_cloud_sync_runs_error_summary_drift_repair_is_covered_by_migration():
    versions_dir = Path("migrations/versions")

    matching_files = []
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if (
            "cloud_b_class_sync_runs" in text
            and "error_summary" in text
            and "alter column" in text
            and "type text" in text
        ):
            matching_files.append(path.name)

    assert matching_files, (
        "Expected an Alembic migration to repair cloud_b_class_sync_runs.error_summary "
        "back to text when existing local state tables drifted to json/jsonb"
    )

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

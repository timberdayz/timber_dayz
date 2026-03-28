from pathlib import Path


def test_task_center_migration_exists():
    versions_dir = Path("migrations/versions")
    matches = list(versions_dir.glob("*task_center*.py"))

    assert matches, "expected a task_center migration in migrations/versions"


def test_task_center_migration_references_all_three_tables():
    versions_dir = Path("migrations/versions")
    migration_path = next(iter(versions_dir.glob("*task_center*.py")))
    source = migration_path.read_text(encoding="utf-8")

    assert "task_center_tasks" in source
    assert "task_center_logs" in source
    assert "task_center_links" in source

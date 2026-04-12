from pathlib import Path

from modules.core.db import Base


def test_approval_center_tables_are_registered():
    assert "approval_templates" in Base.metadata.tables
    assert "approval_instances" in Base.metadata.tables
    assert "approval_steps" in Base.metadata.tables
    assert "approval_action_logs" in Base.metadata.tables


def test_approval_instance_table_has_core_columns():
    instance_table = Base.metadata.tables["approval_instances"]

    for column_name in (
        "approval_id",
        "template_code",
        "applicant_user_id",
        "business_key",
        "status",
        "current_step",
        "submitted_at",
        "finished_at",
        "created_at",
        "updated_at",
    ):
        assert column_name in instance_table.c


def test_approval_step_table_has_core_columns():
    step_table = Base.metadata.tables["approval_steps"]

    for column_name in (
        "approval_pk",
        "step_order",
        "approver_type",
        "approver_user_id",
        "status",
        "acted_at",
    ):
        assert column_name in step_table.c


def test_approval_center_migration_exists():
    versions_dir = Path("migrations/versions")
    matches = list(versions_dir.glob("*approval*center*.py"))

    assert matches, "expected an approval-center migration in migrations/versions"


def test_approval_center_migration_mentions_all_four_tables():
    versions_dir = Path("migrations/versions")
    migration_path = next(iter(versions_dir.glob("*approval*center*.py")))
    source = migration_path.read_text(encoding="utf-8")

    assert "approval_templates" in source
    assert "approval_instances" in source
    assert "approval_steps" in source
    assert "approval_action_logs" in source

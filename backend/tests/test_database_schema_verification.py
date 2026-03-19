from backend.models import database as db_module


def test_expand_existing_table_aliases_adds_unqualified_names_for_schema_tables():
    existing_tables = {
        "core.accounts",
        "core.collection_tasks",
        "a_class.performance_config",
        "finance.gl_accounts",
        "public.catalog_files",
        "staging_orders",
    }

    aliases = db_module._expand_existing_table_aliases(existing_tables)

    assert "core.accounts" in aliases
    assert "accounts" in aliases
    assert "collection_tasks" in aliases
    assert "performance_config" in aliases
    assert "gl_accounts" in aliases
    assert "catalog_files" in aliases
    assert "staging_orders" in aliases


def test_pick_effective_current_revision_prefers_head_when_duplicate_version_tables_exist():
    revisions = {
        "public": "20260111_complete_missing",
        "core": "20260316_tz",
    }

    chosen = db_module._pick_effective_current_revision(
        revisions_by_schema=revisions,
        head_revision="20260316_tz",
    )

    assert chosen == "20260316_tz"


def test_pick_effective_current_revision_falls_back_to_latest_known_revision_when_head_missing():
    revisions = {
        "public": "20260111_complete_missing",
        "core": "20260217_started_completed",
    }

    chosen = db_module._pick_effective_current_revision(
        revisions_by_schema=revisions,
        head_revision="20260316_tz",
    )

    assert chosen == "20260217_started_completed"

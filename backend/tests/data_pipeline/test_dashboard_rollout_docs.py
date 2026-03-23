from pathlib import Path


def test_production_grey_runbook_mentions_router_enable_and_ops_checks():
    text = Path("docs/development/POSTGRESQL_DASHBOARD_PRODUCTION_GREY_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER=true" in text
    assert "Dashboard router source: PostgreSQL" in text
    assert "ops.pipeline_run_log" in text
    assert "Rollback" in text


def test_rollback_commands_doc_mentions_disable_and_restart():
    text = Path("docs/development/POSTGRESQL_DASHBOARD_ROLLBACK_COMMANDS.md").read_text(
        encoding="utf-8"
    )
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER=false" in text
    assert "Restart application" in text
    assert "Dashboard router source: Metabase compatibility" in text

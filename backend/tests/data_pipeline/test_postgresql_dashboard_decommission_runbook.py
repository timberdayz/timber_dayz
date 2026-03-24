from pathlib import Path


def test_post_grey_decommission_runbook_exists_and_covers_required_assets():
    text = Path(
        "docs/development/POSTGRESQL_DASHBOARD_POST_GREY_DECOMMISSION_RUNBOOK.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "PostgreSQL Dashboard post-grey decommission runbook" in text
    assert "archive/metabase/backend/routers/dashboard_api.py" in text
    assert "archive/metabase/backend/routers/metabase_proxy.py" in text
    assert "archive/metabase/backend/services/metabase_question_service.py" in text
    assert "archive/metabase/config/metabase_config.yaml" in text
    assert "archive/metabase/docker/docker-compose.metabase.yml" in text


def test_post_grey_decommission_runbook_defines_sequence_and_verification():
    text = Path(
        "docs/development/POSTGRESQL_DASHBOARD_POST_GREY_DECOMMISSION_RUNBOOK.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "Phase 1" in text
    assert "Phase 2" in text
    assert "Verification" in text
    assert "Rollback" not in text
    assert "python -m pytest backend/tests/data_pipeline -q" in text

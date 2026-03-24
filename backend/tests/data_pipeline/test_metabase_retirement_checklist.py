from pathlib import Path


def test_metabase_retirement_checklist_has_three_retention_buckets():
    text = Path("docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "Remove Now" in text
    assert "Historical Reference Only" in text


def test_metabase_retirement_checklist_lists_key_assets():
    text = Path("docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "archive/metabase/backend/routers/dashboard_api.py" in text
    assert "archive/metabase/backend/routers/metabase_proxy.py" in text
    assert "archive/metabase/backend/services/metabase_question_service.py" in text
    assert "archive/metabase/config/metabase_config.yaml" in text
    assert "archive/metabase/docker/docker-compose.metabase.yml" in text

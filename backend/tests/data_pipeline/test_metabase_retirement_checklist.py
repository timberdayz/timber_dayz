from pathlib import Path


def test_metabase_retirement_checklist_has_three_retention_buckets():
    text = Path("docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "Immediate removal candidates" in text
    assert "Remove after gray validation" in text
    assert "Retain longer-term" in text


def test_metabase_retirement_checklist_lists_key_assets():
    text = Path("docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "backend/routers/dashboard_api.py" in text
    assert "backend/routers/metabase_proxy.py" in text
    assert "backend/services/metabase_question_service.py" in text
    assert "config/metabase_config.yaml" in text
    assert "docker-compose.metabase.yml" in text

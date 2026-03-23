from pathlib import Path


def test_v4252_release_actions_doc_exists_and_explains_gap():
    text = Path(
        "docs/development/POSTGRESQL_DASHBOARD_V4_25_2_RELEASE_ACTIONS.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "v4.25.2 release actions" in text.lower()
    assert "v4.25.1" in text
    assert "main" in text
    assert "codex/postgresql-api-semantic-mart-cutover" in text
    assert "origin tag release" in text.lower()


def test_v4252_release_actions_doc_lists_must_ship_areas():
    text = Path(
        "docs/development/POSTGRESQL_DASHBOARD_V4_25_2_RELEASE_ACTIONS.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "docker-compose.prod.yml" in text
    assert "nginx/nginx.prod.conf" in text
    assert "backend/main.py" in text
    assert "backend/services/postgresql_dashboard_service.py" in text
    assert "backend/services/data_pipeline/refresh_registry.py" in text

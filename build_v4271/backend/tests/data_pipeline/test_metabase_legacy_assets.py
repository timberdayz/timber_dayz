from pathlib import Path


def test_metabase_runtime_assets_are_marked_legacy():
    files = {
        "archive/metabase/backend/routers/metabase_proxy.py": ["legacy", "Metabase"],
        "archive/metabase/backend/services/metabase_question_service.py": ["legacy", "Metabase"],
        "archive/metabase/config/metabase_config.yaml": ["legacy", "Metabase"],
        "archive/metabase/docker/docker-compose.metabase.yml": ["legacy", "Metabase"],
        "archive/metabase/docker/docker-compose.metabase.dev.yml": ["legacy", "Metabase"],
    }

    for path_str, required_terms in files.items():
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        for term in required_terms:
            if term == "legacy":
                assert term in lowered
            else:
                assert term in text


def test_metabase_legacy_asset_status_doc_exists():
    path = Path("docs/development/METABASE_LEGACY_ASSET_STATUS.md")
    text = path.read_text(encoding="utf-8", errors="replace")

    assert "Metabase legacy asset status" in text
    assert "retained as historical assets only" in text
    assert "archive/metabase/backend/routers/metabase_proxy.py" in text
    assert "archive/metabase/backend/services/metabase_question_service.py" in text
    assert "archive/metabase/config/metabase_config.yaml" in text
    assert "archive/metabase/docker/docker-compose.metabase.yml" in text

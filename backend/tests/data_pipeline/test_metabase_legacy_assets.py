from pathlib import Path


def test_metabase_runtime_assets_are_marked_legacy():
    files = {
        "backend/routers/metabase_proxy.py": ["legacy", "Metabase"],
        "backend/services/metabase_question_service.py": ["legacy", "Metabase"],
        "config/metabase_config.yaml": ["legacy", "Metabase"],
        "docker-compose.metabase.yml": ["legacy", "Metabase"],
        "docker-compose.metabase.dev.yml": ["legacy", "Metabase"],
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
    assert "retained for fallback/debug only" in text
    assert "backend/routers/metabase_proxy.py" in text
    assert "backend/services/metabase_question_service.py" in text
    assert "config/metabase_config.yaml" in text
    assert "docker-compose.metabase.yml" in text

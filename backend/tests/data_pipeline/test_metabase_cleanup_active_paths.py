from pathlib import Path


def test_agents_md_no_longer_describes_metabase_as_runtime_fallback():
    text = Path("AGENTS.md").read_text(encoding="utf-8", errors="replace")

    assert "Metabase remains a compatibility and fallback path" not in text


def test_backend_schemas_no_longer_export_metabase_contracts():
    text = Path("backend/schemas/__init__.py").read_text(encoding="utf-8", errors="replace")

    assert "backend.schemas.metabase" not in text
    assert "EmbeddingTokenRequest" not in text
    assert "DashboardEmbedUrlRequest" not in text


def test_legacy_mv_router_describes_postgresql_primary_architecture():
    text = Path("backend/routers/mv.py").read_text(encoding="utf-8", errors="replace")

    assert "DSS/Metabase" not in text
    assert "PostgreSQL semantic/mart/api" in text


def test_active_runtime_comments_no_longer_claim_metabase_processing():
    runtime_files = [
        Path("backend/services/cache_service.py"),
        Path("backend/services/data_ingestion_service.py"),
    ]

    banned_phrases = [
        "在Metabase中完成",
        "Metabase中完成",
        "DB/Metabase",
    ]

    for path in runtime_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in banned_phrases:
            assert phrase not in text

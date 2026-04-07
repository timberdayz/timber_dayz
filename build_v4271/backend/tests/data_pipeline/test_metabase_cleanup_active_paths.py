from pathlib import Path


def test_agents_md_no_longer_describes_metabase_as_runtime_fallback():
    text = Path("AGENTS.md").read_text(encoding="utf-8", errors="replace")

    assert "Metabase remains a compatibility and fallback path" not in text


def test_backend_schemas_no_longer_export_metabase_contracts():
    text = Path("backend/schemas/__init__.py").read_text(
        encoding="utf-8", errors="replace"
    )

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
        "Metabase查询",
        "DB/Metabase",
    ]

    for path in runtime_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in banned_phrases:
            assert phrase not in text


def test_active_historical_docs_and_scripts_are_marked_historical():
    paths = [
        Path("docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md"),
        Path("docs/deployment/CLOUD_METABASE_ACCESS.md"),
        Path("docs/deployment/CLOUD_4C8G_REFERENCE.md"),
        Path("docs/deployment/CLOUD_DEPLOYMENT_FILE_CHECK.md"),
        Path("docs/deployment/CLOUD_ENV_UPDATE_CHECKLIST.md"),
        Path("docs/deployment/ENVIRONMENT_VARIABLES_REFERENCE.md"),
        Path("docs/deployment/LOCAL_AND_CLOUD_DEPLOYMENT_ROLES.md"),
        Path("docs/deployment/LOCAL_COLLECTION_DEV.md"),
        Path("docs/guides/QUICK_START_ALL_FEATURES.md"),
        Path("README.md"),
        Path("scripts/check_b_class_tables.py"),
        Path("scripts/migrate_tables_to_b_class_schema.py"),
        Path("scripts/test_data_sync_pipeline.py"),
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        assert "historical" in text or "历史" in text


def test_quick_start_no_longer_recommends_metabase_runtime_steps():
    text = Path("docs/guides/QUICK_START_ALL_FEATURES.md").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "python run.py --use-docker --with-metabase --collection" not in text
    assert "docker-compose -f docker-compose.metabase.yml up -d" not in text
    assert "Metabase Web UI：http://localhost:8080" not in text
    assert "PostgreSQL-first" in text


def test_local_collection_docs_do_not_treat_metabase_overlay_as_current_path():
    paths = [
        Path("docs/deployment/LOCAL_COLLECTION_DEV.md"),
        Path("docs/deployment/LOCAL_AND_CLOUD_DEPLOYMENT_ROLES.md"),
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "python run.py --use-docker --with-metabase --collection" not in text
        assert "docker-compose.metabase.yml --profile dev-full up -d" not in text
        assert "docker-compose.metabase.dev.yml" not in text
        assert "historical" in text.lower() or "历史" in text


def test_environment_reference_marks_metabase_variables_historical_only():
    text = Path("docs/deployment/ENVIRONMENT_VARIABLES_REFERENCE.md").read_text(
        encoding="utf-8",
        errors="replace",
    ).lower()

    assert "metabase" in text
    assert "historical" in text or "历史" in text


def test_active_compose_entrypoints_no_longer_require_metabase_overlays():
    collection_dev = Path("docker-compose.collection-dev.yml").read_text(
        encoding="utf-8", errors="replace"
    )
    verify_local = Path("docker-compose.verify-local.yml").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "docker-compose.metabase.yml" not in collection_dev
    assert "docker-compose.metabase.dev.yml" not in collection_dev
    assert "metabase:" not in verify_local
    assert "Historical note" in collection_dev
    assert "Historical note" in verify_local

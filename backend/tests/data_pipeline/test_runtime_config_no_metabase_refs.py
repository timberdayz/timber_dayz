from pathlib import Path


def test_runtime_configs_no_longer_reference_metabase_runtime():
    files = (
        ".env",
        ".env.production",
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.prod.yml",
    )

    forbidden = (
        "METABASE_URL",
        "ENABLE_METABASE_PROXY",
        "metabase_app",
    )

    for path_str in files:
        path = Path(path_str)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in forbidden:
            assert token not in text, f"{path_str} still contains {token}"


def test_backend_main_uses_postgresql_dashboard_warmup_delay_name():
    text = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    assert "POSTGRESQL_DASHBOARD_CACHE_WARMUP_DELAY_SECONDS" in text
    assert "METABASE_CACHE_WARMUP_DELAY_SECONDS" not in text

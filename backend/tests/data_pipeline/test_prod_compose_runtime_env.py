from pathlib import Path


def test_prod_compose_celery_services_receive_required_secrets():
    text = Path("docker-compose.prod.yml").read_text(encoding="utf-8", errors="replace")

    required_pairs = [
        "celery-worker:",
        "celery-beat:",
        "SECRET_KEY: ${SECRET_KEY}",
        "JWT_SECRET_KEY: ${JWT_SECRET_KEY}",
    ]

    for item in required_pairs:
        assert item in text


def test_prod_compose_backend_has_explicit_dashboard_router_flags():
    text = Path("docker-compose.prod.yml").read_text(encoding="utf-8", errors="replace")

    assert "USE_POSTGRESQL_DASHBOARD_ROUTER: ${USE_POSTGRESQL_DASHBOARD_ROUTER:-false}" in text
    assert "ENABLE_METABASE_PROXY: ${ENABLE_METABASE_PROXY:-false}" in text

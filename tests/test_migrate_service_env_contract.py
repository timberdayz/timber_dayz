from pathlib import Path


def test_migrate_service_includes_production_secret_envs():
    compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "migrate:" in compose
    assert "SECRET_KEY: ${SECRET_KEY}" in compose
    assert "JWT_SECRET_KEY: ${JWT_SECRET_KEY}" in compose

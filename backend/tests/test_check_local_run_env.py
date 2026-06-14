import importlib.util


def _load_check_local_run_env_module():
    spec = importlib.util.spec_from_file_location(
        "check_local_run_env_module",
        "scripts/check_local_run_env.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_collection_profile_accepts_minimum_required_settings(monkeypatch):
    module = _load_check_local_run_env_module()

    monkeypatch.setenv("ENABLE_COLLECTION", "true")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "true")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_ENABLED", "false")

    ok, errors = module.validate_collection_profile()

    assert ok is True
    assert errors == []


def test_validate_collection_profile_requires_cloud_sync_values(monkeypatch):
    module = _load_check_local_run_env_module()

    monkeypatch.setenv("ENABLE_COLLECTION", "false")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "false")
    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_ENABLED", "true")
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_HOST", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_PORT", raising=False)

    ok, errors = module.validate_collection_profile()

    assert ok is False
    assert "ENABLE_COLLECTION must be true" in errors
    assert "CLOUD_SYNC_WORKER_ENABLED must be true" in errors
    assert "CLOUD_DATABASE_URL is required for cloud sync" in errors
    assert "CLOUD_SYNC_TUNNEL_HOST is required when tunnel is enabled" in errors
    assert "CLOUD_SYNC_TUNNEL_PORT is required when tunnel is enabled" in errors


def test_validate_collection_profile_requires_reachable_tunnel_in_formal_mode(monkeypatch):
    module = _load_check_local_run_env_module()

    monkeypatch.setenv("ENABLE_COLLECTION", "true")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "true")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_ENABLED", "true")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_HOST", "127.0.0.1")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_PORT", "15433")
    monkeypatch.setattr(module, "check_tcp", lambda host, port: False)

    ok, errors = module.validate_collection_profile(require_tunnel_reachable=True)

    assert ok is False
    assert "CLOUD_SYNC_TUNNEL 127.0.0.1:15433 is not reachable" in errors

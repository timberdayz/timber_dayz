import backend.main as main


def test_api_role_disables_collection_background_workers(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ROLE", "api")
    monkeypatch.delenv("ENABLE_COLLECTION", raising=False)

    role = main.resolve_background_task_role("production")

    assert role == "api"
    assert main.should_start_collection_scheduler(role) is False
    assert main.should_start_collection_queue_runner(role) is False
    assert main.should_start_cloud_sync_worker(role) is False


def test_collector_role_enables_collection_background_workers(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ROLE", "collector")
    monkeypatch.setenv("ENABLE_COLLECTION", "true")

    role = main.resolve_background_task_role("development")

    assert role == "collector"
    assert main.should_start_collection_scheduler(role) is True
    assert main.should_start_collection_queue_runner(role) is True
    assert main.should_start_cloud_sync_worker(role) is True
    assert main.should_start_resource_monitor(role) is False
    assert main.should_start_websocket_cleanup(role) is False


def test_production_without_explicit_role_defaults_to_api(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_ROLE", raising=False)
    monkeypatch.delenv("APP_RUNTIME_MODE", raising=False)

    assert main.resolve_background_task_role("production") == "api"


def test_development_without_explicit_role_defaults_to_all(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_ROLE", raising=False)
    monkeypatch.delenv("APP_RUNTIME_MODE", raising=False)

    role = main.resolve_background_task_role("development")

    assert role == "all"
    assert main.should_start_resource_monitor(role) is True
    assert main.should_start_websocket_cleanup(role) is True


def test_api_role_keeps_api_local_background_tasks(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ROLE", "api")

    role = main.resolve_background_task_role("production")

    assert main.should_start_resource_monitor(role) is True
    assert main.should_start_websocket_cleanup(role) is True

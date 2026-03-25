import argparse

from backend.services.cloud_b_class_auto_sync_factory import (
    _build_checkpoint_scope_key,
    CloudSyncWorkerFactory,
    build_cloud_sync_service_from_env,
    build_cloud_sync_worker_factory_from_env,
)


def test_build_cloud_sync_service_from_env_supports_dry_run(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15433/xihong_erp")

    service = build_cloud_sync_service_from_env(dry_run=True)

    assert service is not None
    assert service.remote_writer.dry_run is True
    assert type(service.mirror_manager).__name__ == "NoOpCloudBClassMirrorManager"
    assert service.checkpoint_scope == "cloud_sync:dry_run"


def test_build_cloud_sync_worker_factory_returns_worker(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15433/xihong_erp")

    worker_factory = build_cloud_sync_worker_factory_from_env(dry_run=True)
    worker = worker_factory()

    assert worker is not None
    assert worker.sync_executor is not None


def test_cloud_sync_worker_factory_reuses_shared_engines():
    class FakeEngine:
        pass

    shared_local_engine = FakeEngine()
    shared_cloud_engine = FakeEngine()

    factory = CloudSyncWorkerFactory(
        local_engine=shared_local_engine,
        cloud_engine=shared_cloud_engine,
        session_factory=lambda: object(),
        dry_run=True,
    )

    worker_a = factory()
    worker_b = factory()

    assert worker_a.sync_executor.local_engine is shared_local_engine
    assert worker_b.sync_executor.local_engine is shared_local_engine
    assert worker_a.sync_executor.cloud_engine is shared_cloud_engine
    assert worker_b.sync_executor.cloud_engine is shared_cloud_engine


def test_checkpoint_scope_key_changes_with_cloud_target():
    scope_a = _build_checkpoint_scope_key(
        cloud_database_url="postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp",
        dry_run=False,
    )
    scope_b = _build_checkpoint_scope_key(
        cloud_database_url="postgresql://erp_user:pass@127.0.0.1:15434/xihong_erp",
        dry_run=False,
    )

    assert scope_a.startswith("cloud_sync:")
    assert scope_b.startswith("cloud_sync:")
    assert scope_a != scope_b

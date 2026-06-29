import argparse
from pathlib import Path

import pytest

from backend.services.cloud_b_class_auto_sync_factory import (
    _build_checkpoint_scope_key,
    CloudSyncWorkerFactory,
    build_cloud_sync_runtime_from_env,
    build_cloud_sync_service_from_env,
    build_cloud_sync_worker_factory_from_env,
    run_cloud_sync_startup_checks_from_env,
)
from backend.services.cloud_b_class_mirror_manager import CloudBClassMirrorManager
from backend.services.cloud_b_class_sync_service import CloudBClassSyncService, SQLAlchemyCloudWriter, build_sync_payload
from backend.services.cloud_b_class_auto_sync_runtime import CloudBClassAutoSyncRuntime


def test_build_cloud_sync_service_from_env_supports_dry_run(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15433/xihong_erp")

    service = build_cloud_sync_service_from_env(dry_run=True)

    assert service is not None
    assert service.remote_writer.dry_run is True
    assert type(service.mirror_manager).__name__ == "NoOpCloudBClassMirrorManager"
    assert service.checkpoint_scope == "cloud_sync:dry_run"


def test_cloud_sync_writer_targets_b_class_schema():
    sql = SQLAlchemyCloudWriter._build_upsert_sql(
        table_name="fact_shopee_orders_monthly",
        data_domain="orders",
    )

    assert 'INSERT INTO b_class."fact_shopee_orders_monthly"' in sql
    assert "cloud_b_class" not in sql


def test_runtime_cloud_sync_service_no_longer_writes_cloud_b_class_schema():
    source = Path("backend/services/cloud_b_class_sync_service.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "INSERT INTO cloud_b_class" not in source


def test_cloud_sync_table_filter_excludes_test_fact_tables():
    tables = CloudBClassSyncService._filter_b_class_tables(
        [
            "fact_shopee_orders_monthly",
            "fact_test_platform_orders_daily",
            "dim_shop",
            "b_class.fact_tiktok_orders_daily",
        ]
    )

    assert tables == ["fact_shopee_orders_monthly"]


def test_build_sync_payload_drops_local_foreign_keys_for_cloud_write():
    payload = build_sync_payload(
        {
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "data_domain": "orders",
            "granularity": "monthly",
            "file_id": 2875,
            "template_id": 91,
            "data_hash": "hash-1",
        }
    )

    assert payload["file_id"] is None
    assert payload["template_id"] is None


def test_build_sync_payload_preserves_source_file_id_in_raw_data_metadata():
    payload = build_sync_payload(
        {
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "data_domain": "orders",
            "granularity": "monthly",
            "file_id": 2804,
            "template_id": 91,
            "data_hash": "hash-1",
            "raw_data": {"order_id": "A-1"},
        }
    )

    assert payload["file_id"] is None
    assert payload["template_id"] is None
    assert payload["raw_data"]["_cloud_sync_source_file_id"] == 2804


def test_cloud_sync_mirror_manager_defaults_to_b_class_schema():
    manager = CloudBClassMirrorManager(engine=object())

    assert manager.schema_name == "b_class"


def test_cloud_sync_mirror_manager_rejects_existing_table_missing_canonical_columns(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, stmt):
            return None

    class FakeEngine:
        def begin(self):
            return FakeConnection()

    class FakeInspector:
        def has_table(self, table_name, schema=None):
            return True

        def get_columns(self, table_name, schema=None):
            return [{"name": "platform_code"}, {"name": "data_hash"}]

    monkeypatch.setattr(
        "backend.services.cloud_b_class_mirror_manager.inspect",
        lambda engine: FakeInspector(),
    )

    manager = CloudBClassMirrorManager(engine=FakeEngine())

    with pytest.raises(RuntimeError, match="missing canonical columns"):
        manager.ensure_cloud_mirror_table("fact_shopee_orders_monthly", "orders")


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


def test_build_cloud_sync_runtime_from_env_returns_none_when_worker_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_COLLECTION", "true")
    monkeypatch.setenv("DEPLOYMENT_ROLE", "local")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "false")
    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)

    runtime = build_cloud_sync_runtime_from_env()

    assert runtime is None


def test_build_cloud_sync_runtime_from_env_requires_cloud_database_url(monkeypatch):
    monkeypatch.setenv("ENABLE_COLLECTION", "true")
    monkeypatch.setenv("DEPLOYMENT_ROLE", "local")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "true")
    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="CLOUD_DATABASE_URL"):
        build_cloud_sync_runtime_from_env()


def test_build_cloud_sync_runtime_from_env_returns_runtime_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_COLLECTION", "true")
    monkeypatch.setenv("DEPLOYMENT_ROLE", "local")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ENABLED", "true")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15433/xihong_erp")
    monkeypatch.setenv("CLOUD_SYNC_POLL_INTERVAL_SECONDS", "9")
    monkeypatch.setenv("CLOUD_SYNC_WORKER_ID", "cloud-sync-worker-test")

    runtime = build_cloud_sync_runtime_from_env(dry_run=True)

    assert isinstance(runtime, CloudBClassAutoSyncRuntime)
    assert runtime.poll_interval_seconds == 9.0
    assert runtime.worker_id == "cloud-sync-worker-test"


def test_run_cloud_sync_startup_checks_reports_degraded_when_cloud_db_missing(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def exec_driver_sql(self, sql: str):
            return 1

    class FakeEngine:
        def begin(self):
            return FakeConnection()

        def dispose(self):
            return None

    class FakeInspector:
        def get_table_names(self, schema=None):
            return [
                "cloud_b_class_sync_checkpoints",
                "cloud_b_class_sync_runs",
                "cloud_b_class_sync_tasks",
            ]

    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.create_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.sa_inspect", lambda *args, **kwargs: FakeInspector())
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_code_alembic_heads", lambda: {"head-revision"})
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_database_alembic_revisions", lambda engine: {"head-revision"})

    payload = run_cloud_sync_startup_checks_from_env()

    assert payload["status"] == "degraded"
    assert payload["checks"]["local_database"]["ok"] is True
    assert payload["checks"]["cloud_sync_state_tables"]["ok"] is True
    assert payload["checks"]["cloud_database_url"]["ok"] is False


def test_run_cloud_sync_startup_checks_reports_ok_when_tunnel_and_cloud_db_are_reachable(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def exec_driver_sql(self, sql: str):
            return 1

    class FakeEngine:
        def begin(self):
            return FakeConnection()

        def dispose(self):
            return None

    class FakeInspector:
        def get_table_names(self, schema=None):
            if schema == "ops":
                return ["cloud_sync_receive_log"]
            return [
                "cloud_b_class_sync_checkpoints",
                "cloud_b_class_sync_runs",
                "cloud_b_class_sync_tasks",
            ]

    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://erp_user:pass@host.docker.internal:15433/xihong_erp")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_ENABLED", "true")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_HOST", "host.docker.internal")
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_PORT", "15433")
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.create_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.sa_inspect", lambda *args, **kwargs: FakeInspector())
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._tcp_probe", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_code_alembic_heads", lambda: {"head-revision"})
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_database_alembic_revisions", lambda engine: {"head-revision"})

    payload = run_cloud_sync_startup_checks_from_env()

    assert payload["status"] == "ok"
    assert payload["checks"]["cloud_database_tcp"]["ok"] is True
    assert payload["checks"]["cloud_sync_tunnel"]["ok"] is True


def test_run_cloud_sync_startup_checks_auto_migrates_cloud_when_enabled(monkeypatch):
    class FakeConnection:
        def __init__(self, revision):
            self.revision = revision

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def exec_driver_sql(self, sql: str):
            return 1

    class FakeEngine:
        def __init__(self, revision):
            self.revision = revision

        def begin(self):
            return FakeConnection(self.revision)

        def dispose(self):
            return None

    class FakeInspector:
        def __init__(self, *, cloud=False):
            self.cloud = cloud

        def get_table_names(self, schema=None):
            if self.cloud and schema == "ops":
                return ["cloud_sync_receive_log"]
            return [
                "cloud_b_class_sync_checkpoints",
                "cloud_b_class_sync_runs",
                "cloud_b_class_sync_tasks",
            ]

    upgrades = []

    def fake_create_engine(url, *args, **kwargs):
        if str(url).startswith("postgresql://cloud"):
            return FakeEngine("old-revision")
        return FakeEngine("head-revision")

    def fake_inspect(engine):
        return FakeInspector(cloud=getattr(engine, "revision", "") == "old-revision")

    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://cloud:pass@127.0.0.1:15433/xihong_erp")
    monkeypatch.setenv("ENABLE_CLOUD_SYNC_AUTO_MIGRATION", "true")
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.create_engine", fake_create_engine)
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.sa_inspect", fake_inspect)
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._tcp_probe", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_code_alembic_heads", lambda: {"head-revision"})
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory._get_database_alembic_revisions",
        lambda engine: {getattr(engine, "revision", "head-revision")},
    )
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory._run_alembic_upgrade",
        lambda database_url, target="heads": upgrades.append((database_url, target)),
    )

    payload = run_cloud_sync_startup_checks_from_env()

    assert payload["status"] == "ok"
    assert upgrades == [("postgresql://cloud:pass@127.0.0.1:15433/xihong_erp", "heads")]
    assert payload["checks"]["cloud_alembic_revision"]["ok"] is True
    assert payload["checks"]["cloud_alembic_revision"]["detail"] == "auto-migrated to heads"


def test_run_cloud_sync_startup_checks_rechecks_receive_log_after_auto_migration(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def exec_driver_sql(self, sql: str):
            return 1

    class FakeEngine:
        def __init__(self, revision):
            self.revision = revision

        def begin(self):
            return FakeConnection()

        def dispose(self):
            return None

    migrated = {"done": False}

    class FakeInspector:
        def __init__(self, *, cloud=False):
            self.cloud = cloud

        def get_table_names(self, schema=None):
            if self.cloud and schema == "ops":
                return ["cloud_sync_receive_log"] if migrated["done"] else []
            return [
                "cloud_b_class_sync_checkpoints",
                "cloud_b_class_sync_runs",
                "cloud_b_class_sync_tasks",
            ]

    def fake_create_engine(url, *args, **kwargs):
        if str(url).startswith("postgresql://cloud"):
            return FakeEngine("old-revision")
        return FakeEngine("head-revision")

    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://cloud:pass@127.0.0.1:15433/xihong_erp")
    monkeypatch.setenv("ENABLE_CLOUD_SYNC_AUTO_MIGRATION", "true")
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.create_engine", fake_create_engine)
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory.sa_inspect",
        lambda engine: FakeInspector(cloud=getattr(engine, "revision", "") == "old-revision"),
    )
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._tcp_probe", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_code_alembic_heads", lambda: {"head-revision"})
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory._get_database_alembic_revisions",
        lambda engine: {getattr(engine, "revision", "head-revision")},
    )

    def fake_upgrade(database_url, target="heads"):
        migrated["done"] = True

    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._run_alembic_upgrade", fake_upgrade)

    payload = run_cloud_sync_startup_checks_from_env()

    assert payload["status"] == "ok"
    assert payload["checks"]["cloud_receive_log_table"]["ok"] is True


def test_run_cloud_sync_startup_checks_errors_when_cloud_revision_stale_without_auto_migration(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def exec_driver_sql(self, sql: str):
            return 1

    class FakeEngine:
        def __init__(self, revision):
            self.revision = revision

        def begin(self):
            return FakeConnection()

        def dispose(self):
            return None

    class FakeInspector:
        def __init__(self, *, cloud=False):
            self.cloud = cloud

        def get_table_names(self, schema=None):
            if self.cloud and schema == "ops":
                return ["cloud_sync_receive_log"]
            return [
                "cloud_b_class_sync_checkpoints",
                "cloud_b_class_sync_runs",
                "cloud_b_class_sync_tasks",
            ]

    def fake_create_engine(url, *args, **kwargs):
        if str(url).startswith("postgresql://cloud"):
            return FakeEngine("old-revision")
        return FakeEngine("head-revision")

    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://cloud:pass@127.0.0.1:15433/xihong_erp")
    monkeypatch.delenv("ENABLE_CLOUD_SYNC_AUTO_MIGRATION", raising=False)
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory.create_engine", fake_create_engine)
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory.sa_inspect",
        lambda engine: FakeInspector(cloud=getattr(engine, "revision", "") == "old-revision"),
    )
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._tcp_probe", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("backend.services.cloud_b_class_auto_sync_factory._get_code_alembic_heads", lambda: {"head-revision"})
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory._get_database_alembic_revisions",
        lambda engine: {getattr(engine, "revision", "head-revision")},
    )

    payload = run_cloud_sync_startup_checks_from_env()

    assert payload["status"] == "error"
    assert payload["checks"]["cloud_alembic_revision"]["ok"] is False
    assert "old-revision" in payload["checks"]["cloud_alembic_revision"]["detail"]


def test_worker_factory_recover_stale_running_tasks_recovers_legacy_scope(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp")

    recovered = []

    class FakeTask:
        def __init__(self, status, scope):
            self.status = status
            self.job_id = f"job-{scope}"
            self.source_table_name = "fact_demo"
            self.claimed_by = "worker-1"
            self.lease_expires_at = argparse.Namespace()
            self.heartbeat_at = "hb"
            self.next_retry_at = "next"
            self.last_attempt_finished_at = None
            self.metadata_json = {"checkpoint_scope": scope}
            self.error_code = None
            self.last_error = None

    current_scope = _build_checkpoint_scope_key(
        "postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp",
        dry_run=False,
    )
    legacy_scope = _build_checkpoint_scope_key(
        "postgresql://erp_user:pass@127.0.0.1:15434/xihong_erp",
        dry_run=False,
    )
    tasks = [
        FakeTask("running", current_scope),
        FakeTask("running", legacy_scope),
    ]

    class FakeResult:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return self

        def all(self):
            return self._values

    class FakeSession:
        def execute(self, stmt):
            return FakeResult(tasks)

        def commit(self):
            recovered.extend(tasks)

        def rollback(self):
            return None

        def close(self):
            return None

    factory = CloudSyncWorkerFactory(
        local_engine=object(),
        cloud_engine=argparse.Namespace(url="postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp"),
        session_factory=lambda: FakeSession(),
        dry_run=False,
    )

    result = factory.recover_stale_running_tasks("worker-a")

    assert result["recovered_count"] == 2
    assert tasks[0].status == "pending"
    assert tasks[1].status == "failed"
    assert tasks[1].error_code == "legacy_scope_stale_recovered"

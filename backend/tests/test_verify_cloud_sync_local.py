import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "verify_cloud_sync_local.py"
MIGRATION_SCRIPT = Path(__file__).parents[2] / "scripts" / "migrate_cloud_sync_tables.py"


def _load_module(script=SCRIPT):
    spec = importlib.util.spec_from_file_location(script.stem, script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_verification_initializes_cloud_sync_target_before_sync(monkeypatch):
    module = _load_module()
    calls = []

    def fake_run(command, env=None):
        calls.append((command, env))

    monkeypatch.setattr(module, "_run_command", fake_run)
    monkeypatch.setattr(module, "_build_verify_database_url", lambda _: "postgresql://verify-target")

    module.run_verification(verify_db="verify", table="fact_shopee_orders_monthly")

    target_initialization = next(
        (command, env)
        for command, env in calls
        if command == [module.sys.executable, "scripts/migrate_cloud_sync_tables.py", "--target"]
    )
    assert target_initialization[1]["CLOUD_DATABASE_URL"] == "postgresql://verify-target"
    target_index = calls.index(target_initialization)
    sync_index = next(
        index
        for index, (command, _) in enumerate(calls)
        if command[:2] == [module.sys.executable, "scripts/sync_b_class_to_cloud.py"]
        and "--table" in command
    )
    assert target_index < sync_index


def test_target_initialization_creates_only_cloud_sync_receiver_tables(monkeypatch):
    module = _load_module(MIGRATION_SCRIPT)
    created_tables = []
    statements = []

    class FakeConnection:
        def execute(self, statement):
            statements.append(str(statement))

    class FakeTransaction:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, *_):
            return False

    class FakeEngine:
        def begin(self):
            return FakeTransaction()

        def dispose(self):
            pass

    fake_engine = FakeEngine()
    assert "engine" not in module.__dict__
    monkeypatch.setattr(module, "create_engine", lambda _: fake_engine)
    monkeypatch.setattr(
        module.Base.metadata,
        "create_all",
        lambda **kwargs: created_tables.extend(kwargs["tables"]),
    )

    module.initialize_cloud_sync_target("postgresql://verify-target")

    assert any("CREATE SCHEMA IF NOT EXISTS ops" in statement for statement in statements)
    assert any("CREATE SCHEMA IF NOT EXISTS core" in statement for statement in statements)
    assert created_tables == [
        module.CloudSyncReceiveLog.__table__,
        module.RefreshQueueTask.__table__,
    ]

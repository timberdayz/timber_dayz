from scripts.verify_production_migration_contracts import (
    DEFAULT_TESTS,
    main,
    parse_args,
    postgres_ready_with_sqlalchemy,
    run_contracts,
    wait_for_postgres_ready,
)


def test_parse_args_defaults():
    args = parse_args([])

    assert args.db_host == "127.0.0.1"
    assert args.db_port == "5432"
    assert args.db_user == "migration_test_user"
    assert args.db_name == "migration_test_db"


def test_wait_for_postgres_ready_returns_true_when_sqlalchemy_probe_succeeds(monkeypatch):
    calls = []

    def fake_runner(command, env=None):
        calls.append(command)

    monkeypatch.setattr(
        "scripts.verify_production_migration_contracts.postgres_ready_with_sqlalchemy",
        lambda **kwargs: True,
    )

    assert wait_for_postgres_ready(
        db_host="127.0.0.1",
        db_port="5432",
        db_user="migration_test_user",
        db_password="migration_test_pass",
        db_name="migration_test_db",
        timeout_seconds=5,
        runner=fake_runner,
    ) is True
    assert calls == []


def test_postgres_ready_with_sqlalchemy_uses_connection_url(monkeypatch):
    captured = {}

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            captured["statement"] = str(statement)

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

        def dispose(self):
            captured["disposed"] = True

    def fake_create_engine(url):
        captured["url"] = url
        return _FakeEngine()

    monkeypatch.setattr(
        "scripts.verify_production_migration_contracts.create_engine",
        fake_create_engine,
    )

    assert postgres_ready_with_sqlalchemy(
        db_host="127.0.0.1",
        db_port="5432",
        db_user="migration_test_user",
        db_password="migration_test_pass",
        db_name="migration_test_db",
    ) is True
    assert captured["url"] == (
        "postgresql://migration_test_user:migration_test_pass@127.0.0.1:5432/migration_test_db"
    )
    assert captured["disposed"] is True


def test_run_contracts_executes_pytest_after_db_ready():
    calls = []

    def fake_runner(command, env=None):
        calls.append(command)

    args = parse_args([])
    assert run_contracts(args, runner=fake_runner) is True
    assert calls[-1] == ["python", "-m", "pytest", "-q", *DEFAULT_TESTS] or calls[-1][1:] == ["-m", "pytest", "-q", *DEFAULT_TESTS]


def test_main_returns_zero_when_contracts_pass():
    code = main([], runner=lambda command, env=None: None)
    assert code == 0

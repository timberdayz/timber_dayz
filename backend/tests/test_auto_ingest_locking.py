from types import SimpleNamespace

from backend.tasks import scheduled_tasks


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakePostgresSession:
    def __init__(self, scalar_value=True):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        self.scalar_value = scalar_value
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params or {}))
        return _FakeScalarResult(self.scalar_value)


class _FakeConnection:
    def __init__(self, scalar_value=True):
        self.scalar_value = scalar_value
        self.executed = []
        self.closed = False
        self.transaction = SimpleNamespace(rollback=lambda: setattr(self, "rolled_back", True))
        self.rolled_back = False

    def begin(self):
        return self.transaction

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params or {}))
        return _FakeScalarResult(self.scalar_value)

    def close(self):
        self.closed = True


class _FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


def test_auto_ingest_lock_uses_transaction_scoped_advisory_lock():
    db = _FakePostgresSession()

    assert scheduled_tasks._acquire_auto_ingest_lock(db, lock_key=928451203) is True

    sql = db.executed[0][0]
    assert "pg_try_advisory_xact_lock" in sql
    assert "pg_try_advisory_lock" not in sql


def test_auto_ingest_lock_holds_transaction_on_dedicated_connection():
    connection = _FakeConnection()
    db = SimpleNamespace(bind=_FakeEngine(connection))

    assert scheduled_tasks._acquire_auto_ingest_lock(db, lock_key=928451203) is True

    assert "pg_try_advisory_xact_lock" in connection.executed[0][0]
    assert hasattr(db, "_auto_ingest_lock_handle")

    scheduled_tasks._release_auto_ingest_lock(db, lock_key=928451203)

    assert connection.rolled_back is True
    assert connection.closed is True
    assert not hasattr(db, "_auto_ingest_lock_handle")


def test_release_auto_ingest_lock_is_noop_for_transaction_scoped_lock():
    db = _FakePostgresSession()

    scheduled_tasks._release_auto_ingest_lock(db, lock_key=928451203)

    assert db.executed == []


def test_detect_auto_ingest_orphan_locks_returns_idle_holder_without_running_task():
    class _Rows:
        def mappings(self):
            return self

        def all(self):
            return [
                {
                    "pid": 123,
                    "state": "idle",
                    "lock_age_seconds": 601,
                    "running_auto_ingest_tasks": 0,
                    "query": "ROLLBACK",
                }
            ]

    class _Session(_FakePostgresSession):
        def execute(self, statement, params=None):
            self.executed.append((str(statement), params or {}))
            return _Rows()

    db = _Session()

    locks = scheduled_tasks.detect_auto_ingest_orphan_locks(
        db,
        lock_key=928451203,
        idle_seconds=300,
    )

    assert locks == [
        {
            "pid": 123,
            "state": "idle",
            "lock_age_seconds": 601,
            "running_auto_ingest_tasks": 0,
            "query": "ROLLBACK",
        }
    ]
    assert "pg_locks" in db.executed[0][0]
    assert "task_center_tasks" in db.executed[0][0]

import pytest


def test_is_supported_backend_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///scheduler_jobs.db")

    from backend.services.collection_leader_lock import CollectionLeaderLock

    assert CollectionLeaderLock.is_supported_backend() is False


def test_is_supported_backend_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/dbname")

    from backend.services.collection_leader_lock import CollectionLeaderLock

    assert CollectionLeaderLock.is_supported_backend() is True


@pytest.mark.asyncio
async def test_acquire_release_call_backend_methods(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/dbname")

    from backend.services import collection_leader_lock

    calls: list[tuple[str, int]] = []

    class _Db:
        def close(self):
            return None

    def fake_session_local():
        return _Db()

    def fake_try_lock(_session, key: int) -> bool:
        calls.append(("try", key))
        return True

    def fake_unlock(_session, key: int) -> bool:
        calls.append(("unlock", key))
        return True

    monkeypatch.setattr(collection_leader_lock, "SessionLocal", fake_session_local)
    monkeypatch.setattr(collection_leader_lock.CollectionLeaderLock, "_pg_try_advisory_lock", staticmethod(fake_try_lock))
    monkeypatch.setattr(collection_leader_lock.CollectionLeaderLock, "_pg_advisory_unlock", staticmethod(fake_unlock))

    lock = collection_leader_lock.CollectionLeaderLock(key=123)
    acquired = await lock.acquire()
    assert acquired is True
    await lock.release()

    assert calls == [("try", 123), ("unlock", 123)]


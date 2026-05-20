from __future__ import annotations

import asyncio
import logging
import os
import zlib

from sqlalchemy import text

from backend.models.database import SessionLocal

logger = logging.getLogger(__name__)


def _default_lock_key() -> int:
    # Stable 32-bit key derived from a human-readable label.
    # PostgreSQL advisory locks accept bigint; we keep it in unsigned 32-bit range.
    return int(zlib.crc32(b"collection_scheduler_leader_lock") & 0xFFFFFFFF)


class CollectionLeaderLock:
    """PG advisory lock helper to ensure only one scheduler main loop runs."""

    def __init__(self, key: int | None = None):
        self.key = int(_default_lock_key() if key is None else key)

    @staticmethod
    def is_supported_backend(database_url: str | None = None) -> bool:
        url = (database_url or os.getenv("DATABASE_URL") or "").strip()
        scheme = url.split(":", 1)[0].lower() if url else ""
        return scheme in {"postgres", "postgresql"}

    @staticmethod
    def _pg_try_advisory_lock(session, key: int) -> bool:
        return bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": int(key)},
            ).scalar()
        )

    @staticmethod
    def _pg_advisory_unlock(session, key: int) -> bool:
        return bool(
            session.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": int(key)},
            ).scalar()
        )

    async def acquire(self) -> bool:
        if not self.is_supported_backend():
            database_url = (os.getenv("DATABASE_URL") or "").strip()
            scheme = database_url.split(":", 1)[0].lower() if database_url else ""
            logger.info(
                "CollectionLeaderLock: non-PostgreSQL DATABASE_URL scheme=%r, "
                "skip advisory lock and treat as acquired=true",
                scheme or "<empty>",
            )
            return True

        def _sync_acquire() -> bool:
            db = SessionLocal()
            try:
                return bool(self._pg_try_advisory_lock(db, self.key))
            finally:
                db.close()

        loop = asyncio.get_running_loop()
        return bool(await loop.run_in_executor(None, _sync_acquire))

    async def release(self) -> None:
        if not self.is_supported_backend():
            return None

        def _sync_release() -> None:
            db = SessionLocal()
            try:
                self._pg_advisory_unlock(db, self.key)
            except Exception:
                # Best-effort: release should not crash the scheduler loop.
                logger.exception("CollectionLeaderLock: failed to release advisory lock key=%s", self.key)
            finally:
                db.close()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_release)


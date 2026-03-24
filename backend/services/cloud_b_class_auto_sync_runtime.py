from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone


def should_enable_cloud_sync_worker(
    enabled_flag: str | None,
    enable_collection: bool,
    deployment_role: str | None,
) -> bool:
    return (
        str(enabled_flag or "").lower() in {"1", "true", "yes", "on"}
        and enable_collection
        and (deployment_role or "").lower() != "cloud"
    )


class CloudBClassAutoSyncRuntime:
    """Async runtime loop for cloud-sync worker execution."""

    def __init__(
        self,
        worker_factory,
        poll_interval_seconds: float = 5.0,
        worker_id: str = "cloud-sync-worker-1",
    ) -> None:
        self.worker_factory = worker_factory
        self.poll_interval_seconds = poll_interval_seconds
        self.worker_id = worker_id
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._status = "not_started"
        self._last_error: str | None = None
        self._last_heartbeat_at: str | None = None

    async def start(self) -> bool:
        if self.worker_factory is None:
            self._status = "not_configured"
            return False

        if self._task and not self._task.done():
            return True

        self._stop_event.clear()
        self._status = "running"
        self._task = asyncio.create_task(self._run_loop())
        return True

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.worker_factory is not None and hasattr(self.worker_factory, "close"):
            self.worker_factory.close()
        self._status = "stopped"

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                worker = self.worker_factory()
                try:
                    run_result = worker.run_one(self.worker_id)
                    if inspect.isawaitable(run_result):
                        await run_result
                    self._last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                finally:
                    if hasattr(worker, "close"):
                        worker.close()
                await asyncio.sleep(self.poll_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = str(exc)
            self._status = "error"

    def get_health(self) -> dict:
        return {
            "status": self._status,
            "worker_id": self.worker_id,
            "poll_interval_seconds": self.poll_interval_seconds,
            "last_error": self._last_error,
            "last_heartbeat_at": self._last_heartbeat_at,
        }

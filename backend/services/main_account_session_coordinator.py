from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Dict


@dataclass
class _LockState:
    lock: asyncio.Lock
    waiters: int = 0


class MainAccountSessionCoordinator:
    def __init__(self) -> None:
        self._states: Dict[str, _LockState] = {}
        self._registry_lock = asyncio.Lock()

    def _key(self, platform: str, main_account_id: str) -> str:
        return f"{str(platform or '').strip().lower()}:{str(main_account_id or '').strip()}"

    async def _get_state(self, platform: str, main_account_id: str) -> _LockState:
        key = self._key(platform, main_account_id)
        async with self._registry_lock:
            state = self._states.get(key)
            if state is None:
                state = _LockState(lock=asyncio.Lock())
                self._states[key] = state
            return state

    @asynccontextmanager
    async def acquire(self, platform: str, main_account_id: str) -> AsyncIterator[None]:
        state = await self._get_state(platform, main_account_id)
        state.waiters += 1
        try:
            await state.lock.acquire()
        except Exception:
            state.waiters -= 1
            raise

        state.waiters -= 1
        try:
            yield
        finally:
            if state.lock.locked():
                state.lock.release()

    def waiter_count(self, platform: str, main_account_id: str) -> int:
        key = self._key(platform, main_account_id)
        state = self._states.get(key)
        return state.waiters if state else 0

    def is_locked(self, platform: str, main_account_id: str) -> bool:
        key = self._key(platform, main_account_id)
        state = self._states.get(key)
        return state.lock.locked() if state else False


_default_coordinator = MainAccountSessionCoordinator()


def get_main_account_session_coordinator() -> MainAccountSessionCoordinator:
    return _default_coordinator

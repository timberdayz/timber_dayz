"""账号会话协调器 —— 兼容外壳(Task 3)。

历史
----
原实现是**进程内** ``asyncio.Lock``(模块级单例)。生产是
``gunicorn --workers 4`` × 两个独立容器 → 最多 8 个 OS 进程, 进程内锁完全无效;
且 API 触发的采集走 ``asyncio.create_task``, 不受 ``CollectionLeaderLock`` 保护
→ 正是最容易并发打开同一 profile 的来源。

现在
----
内部改走**跨进程**的 ``MainAccountSessionLock``(Redis ``SET NX`` + Lua CAS)。

兼容契约(L6, 不得破坏)
------------------------
* ``acquire(platform, main_account_id)`` 位置参数签名;
* ``@asynccontextmanager`` 且 **yield None**(不得改成 yield token);
* ``waiter_count`` / ``is_locked`` 必须继续存在;
* ``CollectionExecutorV2(main_account_session_coordinator=...)`` 注入点必须继续可用。

新增(向后兼容的补充)
----------------------
* ``waiter_count_async`` / ``is_locked_async``: 跨进程精确视图(L7)——
  同步版本在 Redis 后端下只能给出「本进程 + 最近快照」, 不足以让
  「等待主账号会话」的状态推送在跨进程下触发。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from backend.services.main_account_session_lock import (
    MainAccountSessionLock,
    SessionLockBackend,
)


class MainAccountSessionCoordinator:
    """账号会话协调器(兼容外壳)。

    对外接口与原实现完全一致; 内部改读跨进程账号锁。
    """

    def __init__(
        self,
        lock: Optional[MainAccountSessionLock] = None,
        *,
        backend: Optional[SessionLockBackend] = None,
        **lock_kwargs: Any,
    ) -> None:
        self._lock = lock
        self._backend = backend
        self._lock_kwargs = lock_kwargs

    @property
    def session_lock(self) -> MainAccountSessionLock:
        """底层跨进程锁(惰性创建 —— 避免 import 期就去连 Redis)。"""
        if self._lock is None:
            self._lock = MainAccountSessionLock(
                backend=self._backend, **self._lock_kwargs
            )
        return self._lock

    @asynccontextmanager
    async def acquire(
        self,
        platform: str,
        main_account_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[None]:
        """获取主账号会话锁。**yield None**(兼容契约)。"""
        async with self.session_lock.acquire(
            platform, main_account_id, timeout=timeout
        ):
            yield None

    def waiter_count(self, platform: str, main_account_id: str) -> int:
        """正在等待该主账号会话的任务数(进程内视图)。"""
        return self.session_lock.waiter_count(platform, main_account_id)

    async def waiter_count_async(self, platform: str, main_account_id: str) -> int:
        """正在等待该主账号会话的任务数(跨进程精确视图)。"""
        return await self.session_lock.waiter_count_async(platform, main_account_id)

    def is_locked(self, platform: str, main_account_id: str) -> bool:
        """该主账号当前是否被占用(进程内视图)。"""
        return self.session_lock.is_locked(platform, main_account_id)

    async def is_locked_async(self, platform: str, main_account_id: str) -> bool:
        """该主账号当前是否被占用(跨进程精确视图)。"""
        return await self.session_lock.is_locked_async(platform, main_account_id)


_default_coordinator = MainAccountSessionCoordinator()


def get_main_account_session_coordinator() -> MainAccountSessionCoordinator:
    return _default_coordinator

"""账号级跨进程会话锁(Task 3 / R6)。

为什么必须是跨进程的
------------------
同一主账号(``main_account_id``)的持久 profile 目录**不能被两个浏览器进程同时打开**:
Chromium 的 user-data-dir 自带 ``SingletonLock``, 双开会直接抛原始错误; 更糟的是两条采集
链路会**互相覆盖**登录态(会话是无条件覆盖写入), 造成**静默的数据损坏**。

进程内 ``asyncio.Lock`` 挡不住这种情况:

* 生产是 ``gunicorn backend.main:app --workers 4``(``Dockerfile.backend``) × **两个独立容器**
  (``docker-compose.prod.yml`` 的 ``backend-api`` / ``backend-collector``) → 最多 8 个 OS 进程;
* API 触发的采集走 ``asyncio.create_task``(``collection_tasks.py``), **不受**
  ``CollectionLeaderLock`` 保护(``should_start_collection_queue_runner("api")`` 为 False)。

因此锁必须是**跨进程**的: Redis ``SET NX`` + **token 校验的 Lua CAS** 释放。

设计要点
--------
* **粒度 = main_account_id**(L1): ``core.shop_accounts.main_account_id`` 是 FK, 1 主账号 → N 店铺账号;
  按店铺锁会漏掉「同一主账号下多店铺并行打开同一 profile」。
* **释放 = token 校验 + Lua CAS**(L2): 不能照搬 ``asyncio.Lock`` 的「先检查再释放」——
  分布式下那会**误删他人的锁**。
* **key = 白名单 + 截断 + 64 位哈希**(L3): ``main_account_id`` 实测含中文/空格/全角
  (如 ``虾皮巴西（东朗照明主体）``、``shopee KR``); **禁止 crc32**(32 位会碰撞 → 两个不同主账号互相阻塞)。
* **TTL 与续期解耦**(L4): 采集不是 celery 任务、``DEFAULT_TASK_TIMEOUT`` 从未被强制,
  采集可以跑 > 30 min → 单次 ``EX`` 必然提前过期 → 锁提前失效 → 双开。
  因此本模块实现 **heartbeat**(每 ``TTL/3`` 刷新 ``EXPIRE``)。
* **不可用时分级**(L5): 生产 Redis 不可用 → **fail-closed**(任务失败, 报「账号会话锁服务不可用」);
  开发/测试 → **fail-open 到进程内 ``asyncio.Lock``**。
* **兼容既有契约**(L6): ``acquire(platform, main_account_id)`` 位置参数签名、
  ``@asynccontextmanager`` 且 **yield None**、``waiter_count`` / ``is_locked`` 继续存在。
* **waiter_count 不退化为恒 0**(L7): 等待者用**独立**的 Hash/ZSET 记录, 使
  「等待主账号会话」的状态推送在跨进程下依然能触发。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import socket
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, Protocol, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: Redis 里可检索的锁 key 前缀
DEFAULT_KEY_PREFIX = "xihong:acct_session_lock"

#: 锁 TTL(秒)。采集可能跑 > 30min, 靠**续期**维持, 而不是靠一次长 EX。
DEFAULT_TTL_SECONDS = 300

#: 续期间隔 = TTL / 3
DEFAULT_RENEW_DIVISOR = 3

#: 等待锁的最长时间(秒)
DEFAULT_WAIT_TIMEOUT_SECONDS = 1800

#: 抢锁失败后的重试间隔(秒)
DEFAULT_RETRY_INTERVAL_SECONDS = 0.5

#: key 片段白名单: 只允许小写字母 / 数字 / 下划线 / 连字符
_SAFE_SEGMENT_RE = re.compile(r"[^a-z0-9_-]+")

#: key 片段最大长度(截断)
_SAFE_SEGMENT_LIMIT = 40

#: 旁路 profile 后缀(``persistent_browser_manager`` 的 ``<account>_alt``)
PROFILE_ALT_SUFFIX = "_alt"

#: 释放锁的 Lua 脚本: **token 校验 + 原子删除**(L2)。
#: 不得拆成「先 GET 再 DEL」两步 —— 分布式下会误删他人的锁。
RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)

#: 续期的 Lua 脚本: **token 校验 + 原子 EXPIRE**(L4)
RENEW_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
)


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------


class MainAccountSessionLockError(RuntimeError):
    """账号会话锁错误基类。"""


class MainAccountSessionLockUnavailableError(MainAccountSessionLockError):
    """锁服务不可用(生产 fail-closed)。

    与「锁冲突」严格区分(E2):

    * 本错误 = **基础设施故障**(Redis 认证失败 / 连不上) → 采集必须被拒绝;
    * ``MainAccountSessionLockTimeoutError`` = **资源被正常占用** → 应当排队等待。
    """


class MainAccountSessionLockTimeoutError(MainAccountSessionLockError):
    """等待账号会话锁超时 —— 该主账号正被其它采集任务占用。"""


# ---------------------------------------------------------------------------
# key 构造(L1 / L3)
# ---------------------------------------------------------------------------


def normalize_profile_identity(profile_identity: Any) -> str:
    """把 profile 目录身份归一化成「逻辑账号身份」。

    旁路 profile(``<account>_alt``)与主 profile(``<account>``)属于**同一个逻辑账号**,
    承载的是同一份登录态语义 → 必须共用**同一把**跨进程锁。否则会出现
    「主 profile 被任务 A 锁住、旁路 profile 被任务 B 打开」的交叉双开。

    代价: 账号名本身以 ``_alt`` 结尾时会被归一到它的前缀(极罕见, 只会造成两个账号
    互相排队, 不会造成双开)。
    """
    text = str(profile_identity or "").strip()
    if text.lower().endswith(PROFILE_ALT_SUFFIX):
        return text[: -len(PROFILE_ALT_SUFFIX)]
    return text


def sanitize_key_segment(value: Any, *, limit: int = _SAFE_SEGMENT_LIMIT) -> str:
    """key 片段白名单化 + 截断(仅用于排障, 不参与唯一性判定)。"""
    return _SAFE_SEGMENT_RE.sub("_", str(value or "").strip().lower())[:limit]


def compute_lock_digest(platform: Any, main_account_id: Any) -> str:
    """64 位摘要(L3)。

    **禁止 crc32**: 只有 32 位, 账号规模上去会碰撞 → 两个不同主账号互相阻塞。
    这里用 ``blake2b(digest_size=8)`` → 64 位 / 16 个 hex 字符。
    """
    raw = f"{str(platform or '').strip().lower()}|{normalize_profile_identity(main_account_id)}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


def build_lock_key(
    platform: Any,
    main_account_id: Any,
    *,
    key_prefix: str = DEFAULT_KEY_PREFIX,
) -> str:
    """构造账号会话锁的 Redis key。

    形如 ``xihong:acct_session_lock:shopee:shopee_kr:3f2a...(64bit)``:
    前两段是可读前缀(白名单 + 截断), 末段是 64 位哈希(唯一性判定)。
    """
    identity = normalize_profile_identity(main_account_id)
    return (
        f"{key_prefix}:{sanitize_key_segment(platform)}:"
        f"{sanitize_key_segment(identity)}:{compute_lock_digest(platform, identity)}"
    )


def waiter_key_for(key: str) -> str:
    """等待者集合的 key(与锁 key 同前缀, 便于一起清理)。"""
    return f"{key}:waiters"


# ---------------------------------------------------------------------------
# 后端协议与实现
# ---------------------------------------------------------------------------


class SessionLockBackend(Protocol):
    """账号会话锁后端协议。

    实现必须保证:

    * ``set_nx`` 是原子的 ``SET NX EX``;
    * ``delete_if_token`` / ``renew`` 是**原子**的 token 校验操作(Lua CAS),
      不得拆成「先 GET 再 DEL」两步;
    * ``add_waiter`` / ``remove_waiter`` / ``waiter_count`` 用于统计等待者(L7)。
    """

    async def set_nx(self, key: str, token: str, ttl_seconds: int) -> bool:
        """原子地「不存在才写入」, 返回是否抢到。"""

    async def get(self, key: str) -> Optional[str]:
        """读取锁值(``None`` 表示没人持锁)。"""

    async def delete_if_token(self, key: str, token: str) -> bool:
        """仅当锁值 == token 时删除(Lua CAS)。返回是否真的删掉了。"""

    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool:
        """仅当锁值 == token 时刷新 TTL(Lua CAS)。返回是否续期成功。"""

    async def add_waiter(self, key: str, waiter_id: str, ttl_seconds: int) -> None:
        """登记一个等待者。"""

    async def remove_waiter(self, key: str, waiter_id: str) -> None:
        """注销一个等待者。"""

    async def waiter_count(self, key: str) -> int:
        """当前等待者数量(跨进程)。"""


class RedisSessionLockBackend:
    """Redis 后端: ``SET NX`` + Lua CAS 释放/续期 + Hash 记录等待者。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def set_nx(self, key: str, token: str, ttl_seconds: int) -> bool:
        result = await self._client.set(
            key, token, ex=max(1, int(ttl_seconds)), nx=True
        )
        return bool(result)

    async def get(self, key: str) -> Optional[str]:
        value = await self._client.get(key)
        return None if value is None else str(value)

    async def delete_if_token(self, key: str, token: str) -> bool:
        result = await self._client.eval(RELEASE_LOCK_LUA, 1, key, token)
        return int(result or 0) == 1

    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool:
        result = await self._client.eval(
            RENEW_LOCK_LUA, 1, key, token, max(1, int(ttl_seconds))
        )
        return int(result or 0) == 1

    async def add_waiter(self, key: str, waiter_id: str, ttl_seconds: int) -> None:
        waiter_key = waiter_key_for(key)
        await self._client.hset(waiter_key, waiter_id, str(time.time()))
        await self._client.expire(waiter_key, int(ttl_seconds))

    async def remove_waiter(self, key: str, waiter_id: str) -> None:
        await self._client.hdel(waiter_key_for(key), waiter_id)

    async def waiter_count(self, key: str) -> int:
        return int(await self._client.hlen(waiter_key_for(key)) or 0)


class LocalSessionLockBackend:
    """进程内后端(开发/测试默认, 或 Redis 不可用时的 fail-open 目标)。

    只保证**同一进程内**互斥 —— 多进程部署必须使用 Redis 后端, 否则会出现
    「两个进程同时打开同一 profile」。因此它只用于:

    * 开发/测试环境(L5 的 fail-open 目标);
    * 生产 Redis 挂掉时的**降级**(此时会明确告警, 且生产默认 fail-closed 不会走到这里)。
    """

    def __init__(self) -> None:
        # (event_loop_id, key) -> asyncio.Lock
        self._locks: Dict[Tuple[int, str], asyncio.Lock] = {}
        # (event_loop_id, key) -> token
        self._holders: Dict[Tuple[int, str], str] = {}
        # (event_loop_id, key) -> {waiter_id}
        self._waiters: Dict[Tuple[int, str], Set[str]] = {}

    @staticmethod
    def _scope(key: str) -> Tuple[int, str]:
        """按事件循环隔离锁对象(避免跨事件循环复用 asyncio.Lock 报错)。"""
        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:  # pragma: no cover - 同步上下文
            loop_id = 0
        return (loop_id, key)

    async def set_nx(self, key: str, token: str, ttl_seconds: int) -> bool:
        scope = self._scope(key)
        lock = self._locks.get(scope)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[scope] = lock
        if lock.locked():
            return False
        # 未被占用时 acquire 不会挂起 → 整个判定+占用是原子的
        await lock.acquire()
        self._holders[scope] = token
        return True

    async def get(self, key: str) -> Optional[str]:
        scope = self._scope(key)
        return self._holders.get(scope)

    async def delete_if_token(self, key: str, token: str) -> bool:
        scope = self._scope(key)
        if self._holders.get(scope) != token:
            return False
        self._holders.pop(scope, None)
        lock = self._locks.get(scope)
        if lock is not None and lock.locked():
            lock.release()
        return True

    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool:
        scope = self._scope(key)
        return self._holders.get(scope) == token

    async def add_waiter(self, key: str, waiter_id: str, ttl_seconds: int) -> None:
        self._waiters.setdefault(self._scope(key), set()).add(waiter_id)

    async def remove_waiter(self, key: str, waiter_id: str) -> None:
        scope = self._scope(key)
        bucket = self._waiters.get(scope)
        if bucket is not None:
            bucket.discard(waiter_id)
            if not bucket:
                self._waiters.pop(scope, None)

    async def waiter_count(self, key: str) -> int:
        return self.waiter_count_sync(key)

    # -- 同步视图(仅进程内后端能给出精确值) ---------------------------------

    def is_locked_sync(self, key: str) -> bool:
        return any(scope[1] == key for scope in self._holders)

    def waiter_count_sync(self, key: str) -> int:
        return sum(len(bucket) for scope, bucket in self._waiters.items() if scope[1] == key)


_local_backend_singleton: Optional[LocalSessionLockBackend] = None


def get_local_session_lock_backend() -> LocalSessionLockBackend:
    """进程内后端单例(同一进程内所有锁实例共享)。"""
    global _local_backend_singleton
    if _local_backend_singleton is None:
        _local_backend_singleton = LocalSessionLockBackend()
    return _local_backend_singleton


# ---------------------------------------------------------------------------
# Redis 客户端获取(L9 —— 方案 A: 进程级惰性单例)
# ---------------------------------------------------------------------------

_redis_client_singleton: Optional[Any] = None
_redis_client_resolved = False


async def get_shared_redis_client() -> Optional[Any]:
    """进程级惰性 Redis 单例。

    为什么不用 ``app.state.redis``(L9 的方案 B): 采集是在 ``asyncio.create_task``
    里跑的, **拿不到 app**; 而巡店面板 / 脚本 / CLI 根本不经过 router。
    惰性单例与 ``cache_service.get_cache_service()`` 的既有模式一致, 三个入口都能用。

    每个 gunicorn worker 各建一条连接(4 worker × 2 容器 = 8 条), 完全可接受。
    """
    global _redis_client_singleton, _redis_client_resolved
    if _redis_client_resolved:
        return _redis_client_singleton

    _redis_client_resolved = True
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        logger.warning("[AccountSessionLock] 未配置 REDIS_URL, 账号会话锁不可用")
        return None

    try:
        from redis import asyncio as aioredis

        client = aioredis.from_url(
            redis_url,
            encoding="utf8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        await client.ping()
    except Exception as exc:
        logger.warning("[AccountSessionLock] Redis 连接失败: %s", exc)
        return None

    try:
        from backend.utils.redis_client import sanitize_redis_url_for_log

        safe_url = sanitize_redis_url_for_log(redis_url)
    except Exception:  # pragma: no cover - 脱敏工具不可用时兜底
        safe_url = "redis://***"

    logger.info("[AccountSessionLock] Redis 已连接: %s", safe_url)
    _redis_client_singleton = client
    return _redis_client_singleton


async def reset_shared_redis_client() -> None:
    """测试辅助: 丢弃进程级 Redis 单例。"""
    global _redis_client_singleton, _redis_client_resolved
    client = _redis_client_singleton
    _redis_client_singleton = None
    _redis_client_resolved = False
    if client is not None:
        with contextlib.suppress(Exception):
            await client.aclose()


# ---------------------------------------------------------------------------
# 后端选择(L5 分级)
# ---------------------------------------------------------------------------


def _backend_mode() -> str:
    """后端模式: ``auto`` / ``redis`` / ``local``。

    * ``auto``(默认): 生产强制 Redis; 非生产用进程内锁(测试绝不连真实 Redis, L8)。
    * ``redis``: 强制 Redis(不可用时按 fail-closed 分级)。
    * ``local``: 强制进程内锁。
    """
    from backend.utils.config import (
        account_session_lock_backend,
        account_session_lock_environment,
    )

    mode = account_session_lock_backend()
    if mode not in {"auto", "redis", "local"}:
        logger.warning(
            "[AccountSessionLock] 未知的 ACCOUNT_SESSION_LOCK_BACKEND=%r, 回退 auto", mode
        )
        mode = "auto"
    if mode == "auto":
        return "redis" if account_session_lock_environment() == "production" else "local"
    return mode


def default_fail_closed() -> bool:
    """生产默认 fail-closed; 非生产默认 fail-open(L5)。"""
    from backend.utils.config import account_session_lock_fail_closed

    return bool(account_session_lock_fail_closed())


async def create_default_backend(*, fail_closed: Optional[bool] = None) -> SessionLockBackend:
    """按当前配置创建默认后端。"""
    if _backend_mode() == "local":
        return get_local_session_lock_backend()

    client = await get_shared_redis_client()
    if client is None:
        should_fail_closed = default_fail_closed() if fail_closed is None else bool(fail_closed)
        if should_fail_closed:
            raise MainAccountSessionLockUnavailableError(
                "账号会话锁服务不可用: 无法连接 Redis(生产 fail-closed, 拒绝采集以避免 profile 双开)"
            )
        logger.warning(
            "[AccountSessionLock] Redis 不可用, 降级为进程内锁(仅同进程互斥, 跨进程仍可能双开)"
        )
        return get_local_session_lock_backend()
    return RedisSessionLockBackend(client)


# ---------------------------------------------------------------------------
# 主锁
# ---------------------------------------------------------------------------


def _build_token(task_id: str = "") -> str:
    """构造锁 token(同时承载持有者信息, 便于排障)。"""
    return (
        f"{uuid.uuid4().hex}:{os.getpid()}:{socket.gethostname()}:"
        f"{int(time.time())}:{task_id or '-'}"
    )


class MainAccountSessionLock:
    """账号级跨进程锁。

    同一 ``main_account_id`` 的 profile 目录不能被两个浏览器进程同时打开,
    因此锁必须是跨进程的(Redis ``SET NX``), 进程内 ``asyncio.Lock`` 不够。
    """

    def __init__(
        self,
        backend: Optional[SessionLockBackend] = None,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        ttl_seconds: Optional[int] = None,
        renew_interval: Optional[float] = None,
        wait_timeout: Optional[float] = None,
        retry_interval: float = DEFAULT_RETRY_INTERVAL_SECONDS,
        fail_closed: Optional[bool] = None,
        task_id: str = "",
    ) -> None:
        self._backend = backend
        self._resolved_backend: Optional[SessionLockBackend] = None
        self._degraded_backend: Optional[SessionLockBackend] = None
        self._key_prefix = key_prefix
        from backend.utils.config import (
            account_session_lock_ttl_seconds,
            account_session_lock_wait_timeout,
        )

        self._ttl_seconds = (
            float(ttl_seconds)
            if ttl_seconds is not None
            else float(account_session_lock_ttl_seconds())
        )
        self._renew_interval = (
            float(renew_interval)
            if renew_interval is not None
            else max(1.0, self._ttl_seconds / DEFAULT_RENEW_DIVISOR)
        )
        self._wait_timeout = (
            float(wait_timeout)
            if wait_timeout is not None
            else float(account_session_lock_wait_timeout())
        )
        self._retry_interval = float(retry_interval)
        self._fail_closed = fail_closed
        self._task_id = task_id

        # 进程内视图(同步诊断接口用)
        self._local_holders: Set[str] = set()
        self._local_waiters: Dict[str, int] = {}
        self._remote_snapshot: Dict[str, Tuple[bool, int]] = {}
        # 同协程重入计数: (task_id, key) -> 深度
        self._reentrant: Dict[Tuple[int, str], int] = {}

    # -- key ---------------------------------------------------------------

    def build_key(self, platform: str, main_account_id: str) -> str:
        """锁 key(含旁路 profile 归一化, 见 ``normalize_profile_identity``)。"""
        return build_lock_key(platform, main_account_id, key_prefix=self._key_prefix)

    # -- 后端 ---------------------------------------------------------------

    def _drop_reentrant(self, reentrant_key: Tuple[Any, str]) -> None:
        """释放一层「同协程重入」计数。"""
        remaining = self._reentrant.get(reentrant_key, 1) - 1
        if remaining <= 0:
            self._reentrant.pop(reentrant_key, None)
        else:
            self._reentrant[reentrant_key] = remaining

    async def _resolve_backend(self) -> SessionLockBackend:
        # 已降级到进程内锁(fail-open)时不再回头连 Redis
        if self._degraded_backend is not None:
            return self._degraded_backend
        if self._backend is not None:
            return self._backend
        if self._resolved_backend is not None:
            return self._resolved_backend
        backend = await create_default_backend(fail_closed=self._fail_closed)
        self._resolved_backend = backend
        return backend

    def _should_fail_closed(self) -> bool:
        if self._fail_closed is not None:
            return bool(self._fail_closed)
        return default_fail_closed()

    # -- 诊断接口 -----------------------------------------------------------

    def is_locked(self, platform: str, main_account_id: str) -> bool:
        """同步诊断: 该主账号当前是否被占用。

        进程内后端给出精确值; Redis 后端给出「本进程持有的 + 最近一次远程快照」。
        需要**跨进程精确值**时请用 ``is_locked_async``。
        """
        key = self.build_key(platform, main_account_id)
        backend = self._backend or self._resolved_backend
        if backend is not None:
            getter = getattr(backend, "is_locked_sync", None)
            if getter is not None:
                try:
                    return bool(getter(key))
                except Exception:  # pragma: no cover - 诊断不应影响主流程
                    logger.debug("[AccountSessionLock] is_locked_sync 失败", exc_info=True)
        if key in self._local_holders:
            return True
        snapshot = self._remote_snapshot.get(key)
        return bool(snapshot[0]) if snapshot else False

    async def is_locked_async(self, platform: str, main_account_id: str) -> bool:
        """跨进程精确的占用状态(L7 的前提)。"""
        key = self.build_key(platform, main_account_id)
        try:
            backend = await self._resolve_backend()
            value = await backend.get(key)
        except Exception as exc:
            logger.warning("[AccountSessionLock] 查询锁状态失败: %s", exc)
            return self.is_locked(platform, main_account_id)
        locked = value is not None
        previous = self._remote_snapshot.get(key, (False, 0))
        self._remote_snapshot[key] = (locked, previous[1])
        return locked

    def waiter_count(self, platform: str, main_account_id: str) -> int:
        """同步诊断: 正在等待该主账号会话的任务数。

        进程内后端给出精确值; Redis 后端给出「本进程等待者 + 最近一次远程快照」的最大值。
        需要**跨进程精确值**时请用 ``waiter_count_async``。
        """
        key = self.build_key(platform, main_account_id)
        backend = self._backend or self._resolved_backend
        if backend is not None:
            getter = getattr(backend, "waiter_count_sync", None)
            if getter is not None:
                try:
                    return int(getter(key))
                except Exception:  # pragma: no cover
                    logger.debug("[AccountSessionLock] waiter_count_sync 失败", exc_info=True)
        local = self._local_waiters.get(key, 0)
        snapshot = self._remote_snapshot.get(key)
        return max(local, snapshot[1] if snapshot else 0)

    async def waiter_count_async(self, platform: str, main_account_id: str) -> int:
        """跨进程精确的等待者数量(L7)。"""
        key = self.build_key(platform, main_account_id)
        try:
            backend = await self._resolve_backend()
            count = int(await backend.waiter_count(key))
        except Exception as exc:
            logger.warning("[AccountSessionLock] 查询等待者数量失败: %s", exc)
            return self.waiter_count(platform, main_account_id)
        previous = self._remote_snapshot.get(key, (False, 0))
        self._remote_snapshot[key] = (previous[0], count)
        return count

    # -- 加锁 ---------------------------------------------------------------

    @asynccontextmanager
    async def acquire(
        self,
        platform: str,
        main_account_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[None]:
        """获取账号会话锁。**yield None**(L6: 不得改成 yield token)。"""
        key = self.build_key(platform, main_account_id)
        task = asyncio.current_task()
        # 用 task **对象**而不是 id(task) 做 key: id 会在任务被回收后复用,
        # 一旦复用就会让新任务误判「本协程已持锁」-> 直接放行 -> profile 双开。
        reentrant_key = (task if task is not None else object(), key)
        depth = self._reentrant.get(reentrant_key, 0)
        if depth:
            # 同协程重入: 直接放行。跨进程版若不复位就会「等一个自己永远不释放的锁」。
            self._reentrant[reentrant_key] = depth + 1
            try:
                yield None
            finally:
                self._drop_reentrant(reentrant_key)
            return

        backend = await self._resolve_backend()
        token = _build_token(self._task_id)
        waiter_id = f"{os.getpid()}:{uuid.uuid4().hex}"
        loop = asyncio.get_running_loop()
        effective_timeout = self._wait_timeout if timeout is None else float(timeout)
        deadline = loop.time() + effective_timeout

        registered = False
        acquired = False
        delay = min(self._retry_interval, 0.05)
        try:
            while True:
                try:
                    acquired = await backend.set_nx(key, token, self._ttl_seconds)
                except Exception as exc:
                    logger.error("[AccountSessionLock] 抢锁失败: %s", exc)
                    if self._should_fail_closed():
                        raise MainAccountSessionLockUnavailableError(
                            "账号会话锁服务不可用: 无法写入账号会话锁(生产 fail-closed, 拒绝采集)"
                        ) from exc
                    backend = get_local_session_lock_backend()
                    self._degraded_backend = backend
                    acquired = await backend.set_nx(key, token, self._ttl_seconds)
                if acquired:
                    break

                if not registered:
                    with contextlib.suppress(Exception):
                        await backend.add_waiter(key, waiter_id, self._ttl_seconds)
                    registered = True
                    self._local_waiters[key] = self._local_waiters.get(key, 0) + 1

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise MainAccountSessionLockTimeoutError(
                    "账号会话被其它采集任务占用: "
                    f"platform={platform}, main_account_id={main_account_id}, "
                    f"waited={effective_timeout}s"
                    )
                await asyncio.sleep(min(delay, remaining))
                # 指数退避: 持锁者刚释放时要尽快接上, 长时间等待时再放慢轮询
                delay = min(self._retry_interval, max(delay * 2, delay + 0.01))

            self._local_holders.add(key)
            # 记录「本协程已持有这把锁」-> 同协程二次 acquire 直接放行(不死锁)
            self._reentrant[reentrant_key] = self._reentrant.get(reentrant_key, 0) + 1
            heartbeat = asyncio.create_task(self._renew_loop(backend, key, token))
            try:
                yield None
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await heartbeat
                self._local_holders.discard(key)
                self._drop_reentrant(reentrant_key)
                try:
                    await backend.delete_if_token(key, token)
                except Exception as exc:
                    logger.warning(
                        "[AccountSessionLock] 释放锁失败(将等 TTL 自然过期): %s", exc
                    )
        finally:
            if registered:
                with contextlib.suppress(Exception):
                    await backend.remove_waiter(key, waiter_id)
                self._local_waiters[key] = max(0, self._local_waiters.get(key, 1) - 1)

    async def _renew_loop(self, backend: SessionLockBackend, key: str, token: str) -> None:
        """心跳续期(L4): 每 ``TTL/3`` 刷新一次 EXPIRE。"""
        while True:
            await asyncio.sleep(self._renew_interval)
            try:
                renewed = await backend.renew(key, token, self._ttl_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[AccountSessionLock] 续期失败: %s", exc)
                continue
            if not renewed:
                logger.error(
                    "[AccountSessionLock] 续期失败: 锁已不属于本任务"
                    "(可能已被 TTL 过期或被他人抢占), profile 双开风险!"
                )
                return

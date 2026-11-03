"""账号级跨进程会话锁(Task 3 / R6)的单元测试。

护栏(L8): **绝不连真实 Redis / PG** —— 全部用假后端。
``backend/tests/conftest.py`` 已把 ``ACCOUNT_SESSION_LOCK_BACKEND`` 钉成 ``local``,
这里显式注入假后端来验证跨进程语义。

假后端的关键设计: 两个独立锁实例必须**共享同一个** ``FakeSessionLockBackend``
实例(模拟同一个 Redis)。否则测的是两个互不相干的字典, 必然"不互斥" → 假绿。
"""

from __future__ import annotations

import asyncio
import sys
import time
import types
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import CollectionResult

# 预先 import 真实的 redis_client(脱敏工具): 下面的用例会替换 sys.modules["redis"],
# 若那时才 import 它, fastapi_cache 会去 import 真实 redis 包并因假模块缺属性而失败。
from backend.utils.redis_client import sanitize_redis_url_for_log  # noqa: F401


# ---------------------------------------------------------------------------
# 假后端
# ---------------------------------------------------------------------------


class FakeSessionLockBackend:
    """假后端: 模拟**一个** Redis 实例(SET NX / GET / Lua CAS / Hash 等待者)。"""

    def __init__(self) -> None:
        self.values: Dict[str, str] = {}
        self.expiry: Dict[str, float] = {}
        self.waiters: Dict[str, Set[str]] = {}
        self.calls: List[Tuple[str, str]] = []
        self.waiter_ttls: List[int] = []
        self.unavailable = False

    # -- 内部 -------------------------------------------------------------

    def _now(self) -> float:
        return time.monotonic()

    def _live(self, key: str) -> Optional[str]:
        if key not in self.values:
            return None
        deadline = self.expiry.get(key)
        if deadline is not None and deadline <= self._now():
            self.values.pop(key, None)
            self.expiry.pop(key, None)
            return None
        return self.values[key]

    def _guard(self) -> None:
        if self.unavailable:
            raise RuntimeError("fake redis unavailable")

    # -- 后端协议 ---------------------------------------------------------

    async def set_nx(self, key: str, token: str, ttl_seconds: int) -> bool:
        self._guard()
        self.calls.append(("set_nx", key))
        if self._live(key) is not None:
            return False
        self.values[key] = token
        self.expiry[key] = self._now() + ttl_seconds
        return True

    async def get(self, key: str) -> Optional[str]:
        self._guard()
        self.calls.append(("get", key))
        return self._live(key)

    async def delete_if_token(self, key: str, token: str) -> bool:
        self._guard()
        self.calls.append(("delete_if_token", key))
        if self._live(key) != token:
            return False
        self.values.pop(key, None)
        self.expiry.pop(key, None)
        return True

    async def renew(self, key: str, token: str, ttl_seconds: int) -> bool:
        self._guard()
        self.calls.append(("renew", key))
        if self._live(key) != token:
            return False
        self.expiry[key] = self._now() + ttl_seconds
        return True

    async def add_waiter(self, key: str, waiter_id: str, ttl_seconds: int) -> None:
        self._guard()
        self.calls.append(("add_waiter", key))
        self.waiter_ttls.append(int(ttl_seconds))
        self.waiters.setdefault(key, set()).add(waiter_id)

    async def remove_waiter(self, key: str, waiter_id: str) -> None:
        self._guard()
        self.calls.append(("remove_waiter", key))
        bucket = self.waiters.get(key)
        if bucket:
            bucket.discard(waiter_id)

    async def waiter_count(self, key: str) -> int:
        self._guard()
        self.calls.append(("waiter_count", key))
        return len(self.waiters.get(key, ()))


class FakeRedisClient:
    """假 Redis 客户端: 只实现账号会话锁用到的命令。"""

    def __init__(self) -> None:
        self.values: Dict[str, str] = {}
        self.waiters: Dict[str, Dict[str, str]] = {}
        self.calls: List[Tuple[str, Any]] = []

    async def set(self, key, value, ex=None, nx=False):
        self.calls.append(("set", (key, value, ex, nx)))
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key):
        self.calls.append(("get", key))
        return self.values.get(key)

    async def eval(self, script, numkeys, key, *args):
        self.calls.append(("eval", (script, numkeys, key, args)))
        if "del" in script:
            if self.values.get(key) == args[0]:
                self.values.pop(key, None)
                return 1
            return 0
        if "expire" in script:
            return 1 if self.values.get(key) == args[0] else 0
        return 0

    async def hset(self, key, field, value):
        self.calls.append(("hset", (key, field)))
        self.waiters.setdefault(key, {})[field] = value

    async def expire(self, key, ttl):
        self.calls.append(("expire", (key, ttl)))

    async def hdel(self, key, field):
        self.calls.append(("hdel", (key, field)))
        self.waiters.get(key, {}).pop(field, None)

    async def hlen(self, key):
        self.calls.append(("hlen", key))
        return len(self.waiters.get(key, {}))


class _StubRedisClient:
    """最小可用的假 Redis 客户端(只实现账号会话锁用到的命令)。"""

    def __init__(self, *, ping_error: Optional[Exception] = None) -> None:
        self.ping_error = ping_error
        self.closed = False

    async def ping(self) -> bool:
        if self.ping_error is not None:
            raise self.ping_error
        return True

    async def aclose(self) -> None:
        self.closed = True


def _install_fake_redis_asyncio(monkeypatch, from_url) -> None:
    """把 ``sys.modules["redis"]`` 换成假模块 —— **绝不连真实 Redis**。"""
    fake_asyncio_module = types.ModuleType("redis.asyncio")
    fake_asyncio_module.from_url = from_url  # type: ignore[attr-defined]
    fake_redis_module = types.ModuleType("redis")
    fake_redis_module.asyncio = fake_asyncio_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio_module)


# ---------------------------------------------------------------------------
# L1 / L3: key 构造
# ---------------------------------------------------------------------------


def test_lock_key_uses_main_account_id_granularity() -> None:
    """L1: 锁粒度是 main_account_id(不是 shop_account_id)。"""
    from backend.services.main_account_session_lock import build_lock_key

    key_main = build_lock_key("shopee", "main-a")
    key_other_main = build_lock_key("shopee", "main-b")

    assert key_main != key_other_main
    # 平台不同也算不同的锁
    assert key_main != build_lock_key("tiktok", "main-a")


def test_lock_key_is_whitelisted_and_truncated() -> None:
    """L3: key 片段必须白名单化 + 截断(main_account_id 实测含中文/空格/全角)。"""
    from backend.services.main_account_session_lock import (
        build_lock_key,
        sanitize_key_segment,
    )

    raw = "虾皮巴西（东朗照明主体） shopee KR"
    segment = sanitize_key_segment(raw)

    assert segment == segment.lower()
    assert all(ch.isalnum() or ch in "_-" for ch in segment)
    assert len(segment) <= 40

    key = build_lock_key("Shopee", raw)
    assert " " not in key
    assert "（" not in key
    assert "）" not in key


def test_lock_digest_is_64bit_and_not_crc32() -> None:
    """L3: 摘要必须是 64 位(blake2b), 禁止 crc32 的 32 位。"""
    from backend.services.main_account_session_lock import compute_lock_digest

    digest = compute_lock_digest("shopee", "main-a")

    assert len(digest) == 16  # 64 bit -> 16 hex 字符
    assert int(digest, 16) < 2**64


def test_different_main_accounts_never_share_a_key() -> None:
    """L3: 两个不同主账号不得互相阻塞。"""
    from backend.services.main_account_session_lock import build_lock_key

    keys = {build_lock_key("shopee", f"main-{index}") for index in range(200)}
    assert len(keys) == 200


def test_lock_key_covers_both_main_and_alt_profile_identity() -> None:
    """跨进程锁的 key 必须同时覆盖 ``<account>`` 与 ``<account>_alt``。

    旁路 profile 与主 profile 属于同一个逻辑账号 → 必须共用同一把锁,
    否则会出现「主 profile 被任务 A 锁住、旁路 profile 被任务 B 打开」的交叉双开。
    """
    from backend.services.main_account_session_lock import (
        build_lock_key,
        normalize_profile_identity,
    )

    assert normalize_profile_identity("虾皮巴西东朗照明主体_alt") == "虾皮巴西东朗照明主体"
    assert build_lock_key("shopee", "acct") == build_lock_key("shopee", "acct_alt")
    assert build_lock_key("shopee", "acct") != build_lock_key("shopee", "acct2")


def test_persistent_browser_manager_alt_profile_shares_the_same_lock_key(
    monkeypatch,
    tmp_path,
) -> None:
    """旁路 profile(<account>_alt)必须与主 profile 共用同一把跨进程锁。

    ``persistent_browser_manager`` 的旁路 profile 是主 profile 的**同目录兄弟**
    (``<account>_alt``), 属于同一个逻辑账号 → 账号会话锁的 key 构造必须把它们归一化到同一把锁。
    """
    from backend.services.main_account_session_lock import build_lock_key
    from modules.utils import persistent_browser_manager as manager_module

    profile_dir = tmp_path / "profiles" / "shopee"
    profile_dir.mkdir(parents=True)
    main_profile = profile_dir / "main-acct"

    monkeypatch.setattr(
        manager_module.SessionManager,
        "get_persistent_profile_path",
        lambda self, platform, account_id: main_profile,
    )
    monkeypatch.setattr(
        manager_module,
        "default_downloads_path",
        lambda platform: tmp_path / "downloads",
    )
    monkeypatch.setattr(
        manager_module.DeviceFingerprintManager,
        "get_or_create_fingerprint",
        lambda self, platform, account_id, account_config=None: {
            "user_agent": "UA",
            "viewport": {"width": 1920, "height": 1080},
            "locale": "zh-CN",
            "timezone": "Asia/Shanghai",
        },
    )

    used_dirs = []

    class _FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            used_dirs.append(user_data_dir)
            if len(used_dirs) == 1:
                raise RuntimeError("profile is locked by another process")
            return object()

    manager = manager_module.PersistentBrowserManager.__new__(
        manager_module.PersistentBrowserManager
    )
    manager.playwright = type(
        "FakePlaywright", (), {"chromium": _FakeChromium()}
    )()
    manager.session_manager = manager_module.SessionManager()
    manager.fingerprint_manager = manager_module.DeviceFingerprintManager()
    manager.active_contexts = {}
    manager._fallback_browsers = {}

    manager._create_persistent_context("shopee", "main-acct", {})

    assert len(used_dirs) == 2
    alt_dir = used_dirs[1]
    assert alt_dir.endswith("_alt")
    # 旁路目录与主目录是同一个逻辑账号 -> 同一把锁
    assert build_lock_key("shopee", "main-acct") == build_lock_key("shopee", "main-acct_alt")


# ---------------------------------------------------------------------------
# L2: Lua CAS 释放
# ---------------------------------------------------------------------------


def test_release_lua_script_uses_token_check() -> None:
    """L2: 释放必须是 token 校验 + Lua CAS, 不能是「先 GET 再 DEL」。"""
    from backend.services.main_account_session_lock import RELEASE_LOCK_LUA

    assert "redis.call('get', KEYS[1]) == ARGV[1]" in RELEASE_LOCK_LUA
    assert "redis.call('del', KEYS[1])" in RELEASE_LOCK_LUA
    assert "return 0" in RELEASE_LOCK_LUA


@pytest.mark.asyncio
async def test_release_does_not_delete_lock_owned_by_another_holder() -> None:
    """L2: token 不匹配时**不得**删锁(否则会误删他人的锁)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    lock = MainAccountSessionLock(backend=backend)

    key = lock.build_key("shopee", "main-a")
    assert await backend.set_nx(key, "token-holder-a", 60) is True

    # 别的持有者拿着不同 token 来释放 -> 必须删不掉
    assert await backend.delete_if_token(key, "token-holder-b") is False
    assert await backend.get(key) == "token-holder-a"

    # 真正的持有者释放 -> 删掉
    assert await backend.delete_if_token(key, "token-holder-a") is True
    assert await backend.get(key) is None


@pytest.mark.asyncio
async def test_lock_release_uses_cas_on_backend() -> None:
    """L2: 锁释放必须走 token 校验路径(delete_if_token), 不是裸 delete。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    lock = MainAccountSessionLock(backend=backend)

    async with lock.acquire("shopee", "main-a"):
        assert ("set_nx", lock.build_key("shopee", "main-a")) in backend.calls

    assert ("delete_if_token", lock.build_key("shopee", "main-a")) in backend.calls
    assert await backend.get(lock.build_key("shopee", "main-a")) is None


# ---------------------------------------------------------------------------
# L4: 续期
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_is_renewed_before_ttl_expiry() -> None:
    """L4: 采集可以跑 > TTL(采集不是 celery 任务), 必须靠续期维持。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    holder = MainAccountSessionLock(
        backend=backend, ttl_seconds=0.3, renew_interval=0.05, wait_timeout=5
    )
    other = MainAccountSessionLock(
        backend=backend, ttl_seconds=0.3, renew_interval=0.05, wait_timeout=5
    )

    key = holder.build_key("shopee", "main-a")

    async with holder.acquire("shopee", "main-a"):
        # 持有时间远超单次 TTL(0.3s)
        await asyncio.sleep(0.8)
        # 续期生效: 锁还在, 且后端收到过 renew
        assert await backend.get(key) is not None
        assert any(call[0] == "renew" for call in backend.calls)

        # 另一个实例抢不到
        with pytest.raises(Exception):
            async with other.acquire("shopee", "main-a", timeout=0.2):
                pass


@pytest.mark.asyncio
async def test_lock_expires_when_heartbeat_is_disabled() -> None:
    """L4 的反面: 没有续期时 TTL 到期必须自动释放(进程被 kill 的兜底)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    holder = MainAccountSessionLock(
        backend=backend, ttl_seconds=0.2, renew_interval=60, wait_timeout=5
    )
    other = MainAccountSessionLock(
        backend=backend, ttl_seconds=0.2, renew_interval=60, wait_timeout=5
    )

    key = holder.build_key("shopee", "main-a")
    async with holder.acquire("shopee", "main-a"):
        assert await backend.get(key) is not None
        await asyncio.sleep(0.35)
        # TTL 已过 -> 锁自动消失
        assert await backend.get(key) is None

    async with other.acquire("shopee", "main-a", timeout=1):
        pass


# ---------------------------------------------------------------------------
# L8: 假后端 + 跨实例互斥
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_independent_lock_instances_are_mutually_exclusive() -> None:
    """端到端: 两个独立锁实例(共享同一假后端)对同一账号必须互斥。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    lock_a = MainAccountSessionLock(backend=backend, wait_timeout=5)
    lock_b = MainAccountSessionLock(backend=backend, wait_timeout=5)

    events: List[str] = []
    holder_ready = asyncio.Event()

    async def holder():
        async with lock_a.acquire("shopee", "shopee KR"):
            events.append("a-enter")
            holder_ready.set()
            await asyncio.sleep(0.2)

    async def waiter():
        await holder_ready.wait()
        async with lock_b.acquire("shopee", "shopee KR"):
            events.append("b-enter")

    await asyncio.wait_for(asyncio.gather(holder(), waiter()), timeout=5)

    assert events == ["a-enter", "b-enter"]


@pytest.mark.asyncio
async def test_different_keys_run_concurrently() -> None:
    """不同主账号必须真并发(不能被一把全局锁串行化)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    lock_a = MainAccountSessionLock(backend=backend, wait_timeout=5)
    lock_b = MainAccountSessionLock(backend=backend, wait_timeout=5)

    first_entered = asyncio.Event()
    second_entered = asyncio.Event()

    async def first():
        async with lock_a.acquire("shopee", "main-a"):
            first_entered.set()
            await asyncio.wait_for(second_entered.wait(), timeout=2)

    async def second():
        async with lock_b.acquire("shopee", "main-b"):
            second_entered.set()
            await asyncio.wait_for(first_entered.wait(), timeout=2)

    await asyncio.wait_for(asyncio.gather(first(), second()), timeout=5)


@pytest.mark.asyncio
async def test_waiting_holder_times_out_with_dedicated_error() -> None:
    """E2: 「锁冲突」必须与「锁服务不可用」报出**不同**的错误。"""
    from backend.services.main_account_session_lock import (
        MainAccountSessionLock,
        MainAccountSessionLockTimeoutError,
        MainAccountSessionLockUnavailableError,
    )

    backend = FakeSessionLockBackend()
    lock_a = MainAccountSessionLock(backend=backend, wait_timeout=5)
    lock_b = MainAccountSessionLock(backend=backend, wait_timeout=5)

    async with lock_a.acquire("shopee", "main-a"):
        with pytest.raises(MainAccountSessionLockTimeoutError) as excinfo:
            async with lock_b.acquire("shopee", "main-a", timeout=0.2):
                pass

    assert not isinstance(excinfo.value, MainAccountSessionLockUnavailableError)
    assert "占用" in str(excinfo.value)


# ---------------------------------------------------------------------------
# L5: 不可用时分级
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_fails_closed_when_lock_backend_unavailable() -> None:
    """L5: 生产 Redis 不可用 -> fail-closed(明确报「账号会话锁服务不可用」)。"""
    from backend.services.main_account_session_lock import (
        MainAccountSessionLock,
        MainAccountSessionLockUnavailableError,
    )

    backend = FakeSessionLockBackend()
    backend.unavailable = True
    lock = MainAccountSessionLock(backend=backend, fail_closed=True, wait_timeout=1)

    with pytest.raises(MainAccountSessionLockUnavailableError) as excinfo:
        async with lock.acquire("shopee", "main-a"):
            pass

    assert "账号会话锁服务不可用" in str(excinfo.value)


@pytest.mark.asyncio
async def test_development_fails_open_to_process_local_lock() -> None:
    """L5: 开发/测试 Redis 不可用 -> fail-open 到进程内锁(不阻断采集)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    backend.unavailable = True
    lock = MainAccountSessionLock(
        backend=backend, fail_closed=False, wait_timeout=1, retry_interval=0.05
    )

    async with lock.acquire("shopee", "main-a-fail-open"):
        # 降级后必须真的拿到了锁(进程内锁生效)
        assert lock.is_locked("shopee", "main-a-fail-open") is True


@pytest.mark.asyncio
async def test_default_fail_closed_follows_environment(monkeypatch) -> None:
    """L5: 生产默认 fail-closed, 非生产默认 fail-open。"""
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.delenv("ACCOUNT_SESSION_LOCK_FAIL_CLOSED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert lock_module.default_fail_closed() is True

    monkeypatch.setenv("ENVIRONMENT", "development")
    assert lock_module.default_fail_closed() is False


# ---------------------------------------------------------------------------
# L6: 兼容契约
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_acquire_keeps_positional_signature_and_yields_none() -> None:
    """L6: acquire(platform, main_account_id) 位置参数 + yield None。"""
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    coordinator = MainAccountSessionCoordinator()
    async with coordinator.acquire("shopee", "main-a") as value:
        assert value is None


@pytest.mark.asyncio
async def test_coordinator_keeps_waiter_count_and_is_locked_api() -> None:
    """L6: waiter_count / is_locked 必须继续存在且语义正确。"""
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    coordinator = MainAccountSessionCoordinator()
    assert coordinator.is_locked("shopee", "main-a") is False
    assert coordinator.waiter_count("shopee", "main-a") == 0

    async with coordinator.acquire("shopee", "main-a"):
        assert coordinator.is_locked("shopee", "main-a") is True
        # 后端已解析 -> 同步诊断走「进程内后端的精确视图」
        assert coordinator.waiter_count("shopee", "main-a") == 0
        assert await coordinator.is_locked_async("shopee", "main-a") is True
        assert await coordinator.waiter_count_async("shopee", "main-a") == 0

    assert coordinator.is_locked("shopee", "main-a") is False


@pytest.mark.asyncio
async def test_coordinator_reentrant_acquire_does_not_self_deadlock() -> None:
    """同协程重入必须放行(跨进程版否则会等一个自己永远不释放的锁)。"""
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    coordinator = MainAccountSessionCoordinator()
    async with coordinator.acquire("shopee", "main-a"):
        async with coordinator.acquire("shopee", "main-a"):
            assert coordinator.is_locked("shopee", "main-a") is True


# ---------------------------------------------------------------------------
# L7: waiter_count 不得退化为恒 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_waiter_count_is_visible_to_other_lock_instances() -> None:
    """L7: 等待者必须能被**另一个实例**看到(跨进程场景的等价物)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    holder = MainAccountSessionLock(backend=backend, wait_timeout=5)
    waiter = MainAccountSessionLock(backend=backend, wait_timeout=5, retry_interval=0.05)

    acquired = asyncio.Event()
    release = asyncio.Event()

    async def hold():
        async with holder.acquire("shopee", "main-a"):
            acquired.set()
            await release.wait()

    holder_task = asyncio.create_task(hold())
    await acquired.wait()

    waiter_task = asyncio.create_task(waiter.acquire("shopee", "main-a").__aenter__())
    await asyncio.sleep(0.1)

    # 另一个实例(相当于另一个进程)能看到等待者
    assert await waiter.waiter_count_async("shopee", "main-a") == 1
    assert await holder.waiter_count_async("shopee", "main-a") == 1

    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    release.set()
    await holder_task


@pytest.mark.asyncio
async def test_waiter_count_is_not_degraded_to_zero_for_remote_holder() -> None:
    """L7: 远端持锁时, 本实例必须能读到 is_locked=True(不能恒 False)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = FakeSessionLockBackend()
    remote = MainAccountSessionLock(backend=backend, wait_timeout=5)
    local = MainAccountSessionLock(backend=backend, wait_timeout=5)

    async with remote.acquire("shopee", "main-a"):
        assert await local.is_locked_async("shopee", "main-a") is True
        assert local.is_locked("shopee", "main-a") is True


# ---------------------------------------------------------------------------
# L9: Redis 客户端获取(方案 A: 进程级惰性单例)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_redis_client_returns_none_without_redis_url(
    monkeypatch,
) -> None:
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert await lock_module.get_shared_redis_client() is None


@pytest.mark.asyncio
async def test_shared_redis_client_masks_password_before_logging(
    monkeypatch,
    caplog,
) -> None:
    """L9: REDIS_URL 的密码进日志前必须脱敏。"""
    from backend.services import main_account_session_lock as lock_module

    # 先把脱敏工具 import 进来(cache 住): 下面会把 sys.modules["redis"] 换成假模块,
    # 若此刻才 import backend.utils.redis_client, fastapi_cache 会去 import 真实
    # redis 包并因假模块缺属性而失败。
    from backend.utils.redis_client import sanitize_redis_url_for_log

    created: Dict[str, object] = {}

    class _FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    def _fake_from_url(url: str, **kwargs):
        created["url"] = url
        return _FakeRedis()

    fake_redis_module = types.ModuleType("redis")
    fake_asyncio_module = types.ModuleType("redis.asyncio")
    fake_asyncio_module.from_url = _fake_from_url  # type: ignore[attr-defined]
    fake_redis_module.asyncio = fake_asyncio_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio_module)
    monkeypatch.setenv("REDIS_URL", "redis://:super-secret@localhost:6379/0")

    await lock_module.reset_shared_redis_client()
    with caplog.at_level("INFO"):
        client = await lock_module.get_shared_redis_client()

    assert client is not None
    assert "super-secret" not in caplog.text
    assert "***@localhost:6379" in caplog.text

    await lock_module.reset_shared_redis_client()


# ---------------------------------------------------------------------------
# F3: 锁边界(顺序路径持有到 profile 关闭)
# ---------------------------------------------------------------------------


class _RecordingCoordinator:
    """记录加锁/解锁时序的假协调器。"""

    def __init__(self, events: List[str]) -> None:
        self.events = events
        self.acquired_with: List[Tuple[str, str]] = []

    def acquire(self, platform: str, main_account_id: str):
        coordinator = self

        class _CM:
            async def __aenter__(self):
                coordinator.events.append("lock-acquire")
                coordinator.acquired_with.append((platform, main_account_id))
                return None

            async def __aexit__(self, exc_type, exc, tb):
                coordinator.events.append("lock-release")
                return None

        return _CM()

    def is_locked(self, platform: str, main_account_id: str) -> bool:
        return False

    def waiter_count(self, platform: str, main_account_id: str) -> int:
        return 0

    async def is_locked_async(self, platform: str, main_account_id: str) -> bool:
        return False

    async def waiter_count_async(self, platform: str, main_account_id: str) -> int:
        return 0


@pytest.mark.asyncio
async def test_sequential_path_holds_profile_lock_until_context_closed(
    monkeypatch,
) -> None:
    """F3: 顺序路径的锁必须持有到 profile context 真正关闭之后才释放。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)

    monkeypatch.setattr(
        executor,
        "_open_runtime_bundle",
        AsyncMock(side_effect=_bundle_opener(events)),
    )
    monkeypatch.setattr(
        executor,
        "_execute_shared_login_phase",
        AsyncMock(return_value=(object(), object(), None)),
    )
    monkeypatch.setattr(
        executor,
        "_execute_with_python_components",
        AsyncMock(
            return_value=CollectionResult(
                task_id="task-1", status="completed", files_collected=0
            )
        ),
    )

    async def _fake_cleanup(**kwargs):
        events.append("context-closed")

    monkeypatch.setattr(executor, "_cleanup_browser_runtime", AsyncMock(side_effect=_fake_cleanup))

    result = await executor.execute(
        task_id="task-1",
        platform="miaoshou",
        account_id="shop-1",
        account={
            "username": "u",
            "password": "p",
            "main_account_id": "main-1",
            "shop_account_id": "shop-1",
        },
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=object(),
        browser_type=object(),
        session_runtime_mode="persistent_profile",
    )

    assert result.status == "completed"
    # 锁的释放必须发生在 profile context 关闭之后
    assert events.index("lock-release") > events.index("context-closed")
    # 锁必须在打开 profile 之前就拿到
    assert events.index("lock-acquire") < events.index("profile-opened")


@pytest.mark.asyncio
async def test_executor_locks_by_main_account_id_not_shop_account_id(
    monkeypatch,
) -> None:
    """L1: 执行器必须用 main_account_id 加锁(不是 shop_account_id)。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)

    monkeypatch.setattr(
        executor,
        "_open_runtime_bundle",
        AsyncMock(side_effect=_bundle_opener(events)),
    )
    monkeypatch.setattr(
        executor,
        "_execute_shared_login_phase",
        AsyncMock(return_value=(object(), object(), None)),
    )
    monkeypatch.setattr(
        executor,
        "_execute_with_python_components",
        AsyncMock(
            return_value=CollectionResult(
                task_id="task-1", status="completed", files_collected=0
            )
        ),
    )
    monkeypatch.setattr(executor, "_cleanup_browser_runtime", AsyncMock())

    await executor.execute(
        task_id="task-1",
        platform="miaoshou",
        account_id="shop-1",
        account={
            "username": "u",
            "password": "p",
            "main_account_id": "main-1",
            "shop_account_id": "shop-1",
        },
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=object(),
        browser_type=object(),
        session_runtime_mode="persistent_profile",
    )

    assert coordinator.acquired_with == [("miaoshou", "main-1")]


def _bundle_opener(events: List[str]):
    """构造一个假的 ``_open_runtime_bundle``, 并记录「profile 打开/关闭」时序。"""

    class _Ctx:
        async def close(self):
            events.append("profile-closed")

    class _Page:
        async def close(self):
            return None

    async def _open(**kwargs):
        events.append("profile-opened")
        return type(
            "Bundle",
            (),
            {
                "reused_session": False,
                "context": _Ctx(),
                "page": _Page(),
                "mode": "persistent_profile",
            },
        )()

    return _open


@pytest.mark.asyncio
async def test_requires_profile_session_lock_only_for_profile_modes(
    monkeypatch,
) -> None:
    """只在真正要打开持久 profile 时才加锁。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    executor = CollectionExecutorV2()

    assert (
        executor._requires_profile_session_lock(
            platform="shopee",
            session_owner_id="main-1",
            session_runtime_mode="persistent_profile",
        )
        is True
    )
    assert (
        executor._requires_profile_session_lock(
            platform="shopee",
            session_owner_id="main-1",
            session_runtime_mode="storage_state_fanout",
        )
        is False
    )

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._manual_storage_state_exists",
        lambda platform, account_id: False,
    )
    assert (
        executor._requires_profile_session_lock(
            platform="shopee",
            session_owner_id="main-1",
            session_runtime_mode="auto",
        )
        is True
    )


@pytest.mark.asyncio
async def test_requires_profile_session_lock_locks_auto_without_profile_dir(
    monkeypatch,
) -> None:
    """R6：auto 模式下即使 profile 目录**还不存在**也必须加锁。

    新账号首次采集时 profile 目录还不存在 → 旧口径（探目录是否存在）会漏加锁 →
    两个任务可以同时**首开**同一目录 → 第二个撞 Chromium 对 user_data_dir 的独占锁
    启动失败，更糟的是 profile 可能被写坏。
    """
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    executor = CollectionExecutorV2()

    # profile 目录**还不存在**（新账号首次采集）
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: False,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._manual_storage_state_exists",
        lambda platform, account_id: False,
    )

    assert (
        executor._requires_profile_session_lock(
            platform="shopee",
            session_owner_id="main-1",
            session_runtime_mode="auto",
        )
        is True
    )


@pytest.mark.asyncio
async def test_requires_profile_session_lock_follows_mode_not_directory_state(
    monkeypatch,
) -> None:
    """判定口径是**运行时模式**，不是「profile 目录此刻存不存在」。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    executor = CollectionExecutorV2()

    for has_profile in (False, True):
        monkeypatch.setattr(
            "modules.apps.collection_center.runtime_session.runtime_profile_exists",
            lambda platform, session_owner_id, _has=has_profile: _has,
        )
        monkeypatch.setattr(
            "modules.apps.collection_center.executor_v2._manual_storage_state_exists",
            lambda platform, account_id: False,
        )

        # 显式走 profile → 加锁
        assert (
            executor._requires_profile_session_lock(
                platform="shopee",
                session_owner_id="main-1",
                session_runtime_mode="persistent_profile",
            )
            is True
        )
        # auto → 目标载体是 profile 目录 → 加锁（与目录是否存在无关）
        assert (
            executor._requires_profile_session_lock(
                platform="shopee",
                session_owner_id="main-1",
                session_runtime_mode="auto",
            )
            is True
        )
        # 纯 storage_state 扇出不碰 profile 目录 → 不加锁
        assert (
            executor._requires_profile_session_lock(
                platform="shopee",
                session_owner_id="main-1",
                session_runtime_mode="storage_state_fanout",
            )
            is False
        )


@pytest.mark.asyncio
async def test_auto_mode_takes_account_lock_even_when_profile_dir_missing(
    monkeypatch,
) -> None:
    """R6 + Task 4：auto 模式下 profile 目录还不存在也必须拿到**跨进程**账号锁。

    判据不是「有没有调过加锁接口」（进程内协调器也会走同一个接口），
    而是「账号锁是否持有到 profile context 关闭之后」——
    只有跨进程锁路径（``session_lock_cm``）才会这样（R6 + F3）。
    """
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    events: List[str] = []
    coordinator = _RecordingCoordinator(events)
    executor = CollectionExecutorV2(main_account_session_coordinator=coordinator)
    executor._update_status = AsyncMock()

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: False,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2._manual_storage_state_exists",
        lambda platform, account_id: False,
    )

    class _Ctx:
        async def close(self):
            events.append("context-closed")

    class _Page:
        async def close(self):
            return None

    class _Bundle:
        reused_session = False
        mode = "persistent_profile"
        profile_path = "profiles/miaoshou/main-1"

        def __init__(self) -> None:
            self.context = _Ctx()
            self.page = _Page()

    async def _open_runtime_bundle(**kwargs):
        events.append("profile-opened")
        return _Bundle()

    async def _execute_shared_login_phase(**kwargs):
        return kwargs["play_context"], kwargs["page"], None

    monkeypatch.setattr(executor, "_open_runtime_bundle", _open_runtime_bundle)
    monkeypatch.setattr(
        executor, "_execute_shared_login_phase", _execute_shared_login_phase
    )
    monkeypatch.setattr(
        executor,
        "_execute_with_python_components",
        AsyncMock(
            return_value=CollectionResult(
                task_id="task-1", status="completed", files_collected=0
            )
        ),
    )

    await executor.execute(
        task_id="task-1",
        platform="miaoshou",
        account_id="shop-1",
        account={
            "username": "u",
            "password": "p",
            "main_account_id": "main-1",
            "shop_account_id": "shop-1",
        },
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=object(),
        browser_type=object(),
        session_runtime_mode="auto",
    )

    # 账号锁必须在打开 profile 之前拿到
    assert events.index("lock-acquire") < events.index("profile-opened")
    # 且必须持有到 profile context 关闭之后（R6：不能让另一个进程双开同一目录）
    assert events.index("context-closed") < events.index("lock-release")


# ---------------------------------------------------------------------------
# 后端实现与降级路径
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RedisSessionLockBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_backend_uses_set_nx_with_ttl() -> None:
    from backend.services.main_account_session_lock import RedisSessionLockBackend

    client = FakeRedisClient()
    backend = RedisSessionLockBackend(client)

    assert await backend.set_nx("k", "token-1", 30) is True
    assert await backend.set_nx("k", "token-2", 30) is False

    set_call = [payload for name, payload in client.calls if name == "set"][0]
    key, value, ex, nx = set_call
    assert (key, value, nx) == ("k", "token-1", True)
    assert ex >= 1
    assert await backend.get("k") == "token-1"


@pytest.mark.asyncio
async def test_redis_backend_release_and_renew_use_lua_cas() -> None:
    from backend.services.main_account_session_lock import (
        RELEASE_LOCK_LUA,
        RENEW_LOCK_LUA,
        RedisSessionLockBackend,
    )

    client = FakeRedisClient()
    backend = RedisSessionLockBackend(client)

    await backend.set_nx("k", "token-1", 30)

    # token 不匹配 -> Lua 返回 0 -> 不删
    assert await backend.delete_if_token("k", "token-x") is False
    assert await backend.get("k") == "token-1"
    assert await backend.renew("k", "token-x", 30) is False

    # token 匹配 -> Lua 返回 1
    assert await backend.renew("k", "token-1", 30) is True
    assert await backend.delete_if_token("k", "token-1") is True
    assert await backend.get("k") is None

    scripts = [payload[0] for name, payload in client.calls if name == "eval"]
    assert RELEASE_LOCK_LUA in scripts
    assert RENEW_LOCK_LUA in scripts


@pytest.mark.asyncio
async def test_redis_backend_tracks_waiters_in_separate_hash() -> None:
    from backend.services.main_account_session_lock import (
        RedisSessionLockBackend,
        waiter_key_for,
    )

    client = FakeRedisClient()
    backend = RedisSessionLockBackend(client)

    await backend.add_waiter("lock-key", "waiter-1", 60)
    assert await backend.waiter_count("lock-key") == 1
    assert waiter_key_for("lock-key") == "lock-key:waiters"

    await backend.remove_waiter("lock-key", "waiter-1")
    assert await backend.waiter_count("lock-key") == 0
    # 等待者集合与锁 key 是**两个** key -> 锁过期不会连带清掉等待者统计
    assert "lock-key" not in client.values


# ---------------------------------------------------------------------------
# LocalSessionLockBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_backend_provides_process_local_exclusion() -> None:
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()

    assert await backend.set_nx("k", "token-1", 60) is True
    assert await backend.set_nx("k", "token-2", 60) is False
    assert await backend.get("k") == "token-1"
    assert backend.is_locked_sync("k") is True

    assert await backend.renew("k", "token-x", 60) is False
    assert await backend.renew("k", "token-1", 60) is True

    # token 不匹配不得释放
    assert await backend.delete_if_token("k", "token-x") is False
    assert await backend.get("k") == "token-1"

    assert await backend.delete_if_token("k", "token-1") is True
    assert await backend.get("k") is None
    assert backend.is_locked_sync("k") is False

    # 释放后可以重新获取
    assert await backend.set_nx("k", "token-3", 60) is True
    assert await backend.delete_if_token("k", "token-3") is True


@pytest.mark.asyncio
async def test_local_backend_tracks_waiters() -> None:
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()

    assert await backend.waiter_count("k") == 0
    await backend.add_waiter("k", "waiter-1", 60)
    await backend.add_waiter("k", "waiter-2", 60)
    assert await backend.waiter_count("k") == 2
    assert backend.waiter_count_sync("k") == 2

    await backend.remove_waiter("k", "waiter-1")
    assert backend.waiter_count_sync("k") == 1
    await backend.remove_waiter("k", "waiter-2")
    assert backend.waiter_count_sync("k") == 0

    # 注销一个不存在的等待者不应报错
    await backend.remove_waiter("unknown-key", "waiter-x")


@pytest.mark.asyncio
async def test_local_backend_reclaims_lock_objects_after_release() -> None:
    """评审 F9: 释放后必须回收锁对象(否则 ``_locks`` 随账号数单调增长)。

    实测旧实现「200 次加解锁后 _locks=200」—— 条目永久保留(``_holders`` 会 pop)。
    """
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()

    for index in range(20):
        key = f"key-{index}"
        assert await backend.set_nx(key, f"token-{index}", 60) is True
        assert await backend.delete_if_token(key, f"token-{index}") is True

    assert backend._holders == {}
    assert backend._locks == {}, "锁对象必须在释放后被回收"


@pytest.mark.asyncio
async def test_local_backend_keeps_lock_object_while_waiters_exist() -> None:
    """评审 F9: 还有等待者时锁对象**不能**被回收(等待者还要靠它互斥)。"""
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()

    assert await backend.set_nx("k", "token-1", 60) is True
    await backend.add_waiter("k", "waiter-1", 60)
    assert await backend.delete_if_token("k", "token-1") is True

    assert len(backend._locks) == 1, "仍有等待者时锁对象必须保留"

    await backend.remove_waiter("k", "waiter-1")


@pytest.mark.asyncio
async def test_local_backend_release_when_lock_not_held() -> None:
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()
    # 从未持有 -> 释放必须安全返回 False
    assert await backend.delete_if_token("never-held", "token") is False

    # 持有者登记了但没有对应的 asyncio.Lock 对象(例如锁对象已被清理):
    # 释放必须成功且不能因为缺锁对象而崩掉。
    scope = backend._scope("orphan-key")
    backend._holders[scope] = "token"
    assert await backend.delete_if_token("orphan-key", "token") is True


# ---------------------------------------------------------------------------
# 后端模式与分级
# ---------------------------------------------------------------------------


def test_backend_mode_selection(monkeypatch) -> None:
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "local")
    assert lock_module._backend_mode() == "local"

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "redis")
    assert lock_module._backend_mode() == "redis"

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "auto")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert lock_module._backend_mode() == "local"
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert lock_module._backend_mode() == "redis"

    # 未知值 -> 回退 auto
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "nonsense")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert lock_module._backend_mode() == "local"


def test_fail_closed_env_override(monkeypatch) -> None:
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_FAIL_CLOSED", "true")
    assert lock_module.default_fail_closed() is True
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_FAIL_CLOSED", "off")
    assert lock_module.default_fail_closed() is False


@pytest.mark.asyncio
async def test_create_default_backend_local_mode(monkeypatch) -> None:
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "local")
    backend = await lock_module.create_default_backend()
    assert isinstance(backend, lock_module.LocalSessionLockBackend)


@pytest.mark.asyncio
async def test_create_default_backend_redis_mode(monkeypatch) -> None:
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "redis")
    client = FakeRedisClient()

    async def _fake_client():
        return client

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    backend = await lock_module.create_default_backend()
    assert isinstance(backend, lock_module.RedisSessionLockBackend)


@pytest.mark.asyncio
async def test_create_default_backend_fails_closed_without_redis(monkeypatch) -> None:
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "redis")

    async def _fake_client():
        return None

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    with pytest.raises(lock_module.MainAccountSessionLockUnavailableError):
        await lock_module.create_default_backend(fail_closed=True)


@pytest.mark.asyncio
async def test_create_default_backend_falls_open_without_redis(monkeypatch) -> None:
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "redis")

    async def _fake_client():
        return None

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    backend = await lock_module.create_default_backend(fail_closed=False)
    assert isinstance(backend, lock_module.LocalSessionLockBackend)


# ---------------------------------------------------------------------------
# Redis 客户端获取
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_redis_client_is_cached_after_first_resolution(
    monkeypatch,
) -> None:
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    class _FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    fake_asyncio_module = types.ModuleType("redis.asyncio")
    fake_asyncio_module.from_url = lambda url, **kwargs: _FakeRedis()
    fake_redis_module = types.ModuleType("redis")
    fake_redis_module.asyncio = fake_asyncio_module
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio_module)

    first = await lock_module.get_shared_redis_client()
    second = await lock_module.get_shared_redis_client()

    assert first is not None
    assert second is first  # 第二次直接走缓存

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_returns_none_when_connection_fails(
    monkeypatch,
) -> None:
    """连接失败 -> 返回 None(但**不得**把失败永久缓存, 见下一个用例)。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    attempts: List[str] = []

    def _boom(url: str, **kwargs):
        attempts.append(url)
        raise RuntimeError("connection refused")

    _install_fake_redis_asyncio(monkeypatch, _boom)

    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 1

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_retries_connection_after_failure(
    monkeypatch,
) -> None:
    """回归: 第一次连接失败后, 第二次调用**必须重新尝试连接**。

    旧实现把 ``_redis_client_resolved`` 在连接**之前**置位 -> 一次抖动后该进程
    此后永远拿不到 Redis -> 生产 fail-closed -> 该 worker 的采集被永久拒绝。
    """
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    # 关掉冷却窗, 让第二次调用立刻重试
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_REDIS_RETRY_COOLDOWN_SECONDS", "0")

    attempts: List[str] = []
    client = _StubRedisClient()

    def _from_url(url: str, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            raise RuntimeError("connection refused")
        return client

    _install_fake_redis_asyncio(monkeypatch, _from_url)

    assert await lock_module.get_shared_redis_client() is None
    # 第二次: 必须真的重新尝试连接(而不是复用缓存的失败)
    assert await lock_module.get_shared_redis_client() is client
    assert len(attempts) == 2

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_does_not_retry_within_cooldown_window(
    monkeypatch,
) -> None:
    """冷却窗内不再白等连接超时(快速返回 None), 窗口外自动重试。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_REDIS_RETRY_COOLDOWN_SECONDS", "0.05")

    attempts: List[str] = []

    def _boom(url: str, **kwargs):
        attempts.append(url)
        raise RuntimeError("connection refused")

    _install_fake_redis_asyncio(monkeypatch, _boom)

    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 1

    # 冷却窗内 -> 不再重连, 但仍然是 None(fail-closed 语义不变)
    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 1

    # 冷却窗外 -> 自动重试
    await asyncio.sleep(0.1)
    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 2

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_closes_client_when_ping_fails(
    monkeypatch,
) -> None:
    """from_url 成功但 ping 失败 -> 已创建的连接必须被关闭(不泄漏)。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    client = _StubRedisClient(ping_error=RuntimeError("auth failed"))

    _install_fake_redis_asyncio(monkeypatch, lambda url, **kwargs: client)

    assert await lock_module.get_shared_redis_client() is None
    assert client.closed is True

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_failure_log_gives_operator_hint(
    monkeypatch,
    caplog,
) -> None:
    """失败日志必须给出**可执行**的运维提示(会重连 + 该查什么)。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    def _boom(url: str, **kwargs):
        raise RuntimeError("connection refused")

    _install_fake_redis_asyncio(monkeypatch, _boom)

    with caplog.at_level("ERROR"):
        assert await lock_module.get_shared_redis_client() is None

    assert "自动重连" in caplog.text
    assert "REDIS_PASSWORD" in caplog.text

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_does_not_leak_connection_on_concurrent_call(
    monkeypatch,
) -> None:
    """并发首连: 只保留一条连接, 另一条必须被关闭(不得泄漏)。

    评审 F2: 断言必须是**身份级**而不是计数级 —— 要防的 bug 是
    「后到者把**先到者(共享单例)**的连接提前关掉」。计数级断言(关了几个)
    对这个变异完全无感(照样全绿), 所以这里明确断言:
    被关掉的是**非单例**那条, 且**单例本身没被关**。
    """
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    created: List[_StubRedisClient] = []
    gate = asyncio.Event()

    class _GatedRedis(_StubRedisClient):
        async def ping(self) -> bool:
            # 等到两个客户端都建好 -> 强制两个调用交错
            if len(created) >= 2:
                gate.set()
            await gate.wait()
            return True

    def _from_url(url: str, **kwargs):
        client = _GatedRedis()
        created.append(client)
        return client

    _install_fake_redis_asyncio(monkeypatch, _from_url)

    first, second = await asyncio.gather(
        lock_module.get_shared_redis_client(),
        lock_module.get_shared_redis_client(),
    )

    assert first is not None
    assert first is second
    assert len(created) == 2

    # 共享单例是「先到的那条」——它**不能**被关掉
    singleton = first
    others = [client for client in created if client is not singleton]
    assert len(others) == 1
    assert others[0].closed is True, "后到者必须关闭**自己**那条连接"
    assert singleton.closed is False, "共享单例不得被后到者关掉"

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_failure_log_includes_sanitized_url(
    monkeypatch,
    caplog,
) -> None:
    """评审 F10: 连接失败日志必须带(脱敏后的)URL —— 运维要能看出连的是哪台。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://redis.internal:6380/3")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    def _boom(url: str, **kwargs):
        raise RuntimeError("connection refused")

    _install_fake_redis_asyncio(monkeypatch, _boom)

    with caplog.at_level("ERROR"):
        assert await lock_module.get_shared_redis_client() is None

    assert "redis.internal:6380" in caplog.text
    assert "/3" in caplog.text

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_shared_redis_client_success_clears_failure_cooldown_state(
    monkeypatch,
) -> None:
    """评审 F11: 连接成功必须清掉失败冷却状态(否则状态残留)。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    client = _StubRedisClient()
    _install_fake_redis_asyncio(monkeypatch, lambda url, **kwargs: client)

    # 先人为制造一次失败状态残留
    lock_module._redis_client_failed_at = 123.0

    resolved = await lock_module.get_shared_redis_client()

    assert resolved is client
    assert lock_module._redis_client_failed_at is None

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_reset_shared_redis_client_discards_in_flight_connection(
    monkeypatch,
) -> None:
    """评审 F11: 连接期间发生 reset -> 在途连接醒来后必须自行关闭并丢弃。

    否则它会把 reset 刚清掉的单例**复活**(``_redis_client_singleton = client``),
    reset 等于没做。
    """
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    ping_started = asyncio.Event()
    release_ping = asyncio.Event()
    client = _StubRedisClient()

    class _SlowPingRedis(_StubRedisClient):
        async def ping(self) -> bool:
            ping_started.set()
            await release_ping.wait()
            return True

    client = _SlowPingRedis()
    _install_fake_redis_asyncio(monkeypatch, lambda url, **kwargs: client)

    task = asyncio.create_task(lock_module.get_shared_redis_client())
    await ping_started.wait()

    # 连接还在途中 -> 此刻 reset
    await lock_module.reset_shared_redis_client()
    release_ping.set()

    result = await task

    assert result is None, "被 reset 掉的在途连接不得再写回全局单例"
    assert client.closed is True, "被丢弃的连接必须关闭(不得泄漏)"
    assert lock_module._redis_client_singleton is None

    await lock_module.reset_shared_redis_client()


@pytest.mark.asyncio
async def test_reset_shared_redis_client_clears_failure_cooldown(
    monkeypatch,
) -> None:
    """reset 必须同时清掉失败时间戳(否则冷却状态会跨调用残留)。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_REDIS_RETRY_COOLDOWN_SECONDS", "300")

    attempts: List[str] = []

    def _boom(url: str, **kwargs):
        attempts.append(url)
        raise RuntimeError("connection refused")

    _install_fake_redis_asyncio(monkeypatch, _boom)

    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 1

    # 冷却窗内 -> 不重连
    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 1

    # reset 之后 -> 冷却状态被清掉 -> 立刻重试
    await lock_module.reset_shared_redis_client()
    assert await lock_module.get_shared_redis_client() is None
    assert len(attempts) == 2

    await lock_module.reset_shared_redis_client()


# ---------------------------------------------------------------------------
# 诊断接口的异常降级
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_diagnostics_degrade_to_local_view_on_backend_error() -> None:
    from backend.services.main_account_session_lock import MainAccountSessionLock

    class _BrokenBackend:
        async def set_nx(self, key, token, ttl_seconds):
            raise RuntimeError("boom")

        async def get(self, key):
            raise RuntimeError("boom")

        async def delete_if_token(self, key, token):
            raise RuntimeError("boom")

        async def renew(self, key, token, ttl_seconds):
            raise RuntimeError("boom")

        async def add_waiter(self, key, waiter_id, ttl_seconds):
            raise RuntimeError("boom")

        async def remove_waiter(self, key, waiter_id):
            raise RuntimeError("boom")

        async def waiter_count(self, key):
            raise RuntimeError("boom")

    lock = MainAccountSessionLock(
        backend=_BrokenBackend(), fail_closed=False, wait_timeout=1, retry_interval=0.05
    )

    assert await lock.is_locked_async("shopee", "main-a") is False
    assert await lock.waiter_count_async("shopee", "main-a") == 0

    # 降级到进程内锁后仍然可以加锁
    async with lock.acquire("shopee", "main-a-degraded"):
        pass


@pytest.mark.asyncio
async def test_lock_release_failure_is_logged_and_does_not_raise() -> None:
    """释放失败(Redis 抖动)不能把采集任务带崩 —— 锁会等 TTL 自然过期。"""

    class _ReleaseFailBackend:
        def __init__(self) -> None:
            self.holder = None

        async def set_nx(self, key, token, ttl_seconds):
            self.holder = token
            return True

        async def get(self, key):
            return self.holder

        async def delete_if_token(self, key, token):
            raise RuntimeError("release failed")

        async def renew(self, key, token, ttl_seconds):
            return True

        async def add_waiter(self, key, waiter_id, ttl_seconds):
            return None

        async def remove_waiter(self, key, waiter_id):
            return None

        async def waiter_count(self, key):
            return 0

    from backend.services.main_account_session_lock import MainAccountSessionLock

    backend = _ReleaseFailBackend()
    lock = MainAccountSessionLock(backend=backend, wait_timeout=1)

    async with lock.acquire("shopee", "main-a"):
        pass


@pytest.mark.asyncio
async def test_lock_reuses_local_backend_after_degrading() -> None:
    """降级后不再回头连 Redis(避免每次加锁都等一次连接超时)。"""
    from backend.services import main_account_session_lock as lock_module
    from backend.services.main_account_session_lock import MainAccountSessionLock

    class _BrokenBackend:
        async def set_nx(self, key, token, ttl_seconds):
            raise RuntimeError("boom")

        async def get(self, key):
            raise RuntimeError("boom")

        async def delete_if_token(self, key, token):
            raise RuntimeError("boom")

        async def renew(self, key, token, ttl_seconds):
            raise RuntimeError("boom")

        async def add_waiter(self, key, waiter_id, ttl_seconds):
            raise RuntimeError("boom")

        async def remove_waiter(self, key, waiter_id):
            raise RuntimeError("boom")

        async def waiter_count(self, key):
            raise RuntimeError("boom")

    lock = MainAccountSessionLock(
        backend=_BrokenBackend(), fail_closed=False, wait_timeout=1, retry_interval=0.05
    )

    async with lock.acquire("shopee", "main-a-first"):
        pass
    # 第二次加锁直接走已降级的进程内后端
    async with lock.acquire("shopee", "main-a-second"):
        pass

    assert lock._degraded_backend is lock_module.get_local_session_lock_backend()


@pytest.mark.asyncio
async def test_default_backend_is_resolved_once_and_cached(monkeypatch) -> None:
    """默认后端只解析一次并缓存(避免每次加锁都重新建连接)。"""
    from backend.services import main_account_session_lock as lock_module
    from backend.services.main_account_session_lock import MainAccountSessionLock

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "local")
    lock = MainAccountSessionLock()

    first = await lock._resolve_backend()
    second = await lock._resolve_backend()

    assert first is second
    assert lock._resolved_backend is first


@pytest.mark.asyncio
async def test_fail_closed_defaults_to_environment_when_not_configured(
    monkeypatch,
) -> None:
    """没显式配置时, fail-closed 跟随 ENVIRONMENT(生产拒绝采集)。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    class _BrokenBackend:
        async def set_nx(self, key, token, ttl_seconds):
            raise RuntimeError("boom")

        async def get(self, key):
            raise RuntimeError("boom")

        async def delete_if_token(self, key, token):
            raise RuntimeError("boom")

        async def renew(self, key, token, ttl_seconds):
            raise RuntimeError("boom")

        async def add_waiter(self, key, waiter_id, ttl_seconds):
            raise RuntimeError("boom")

        async def remove_waiter(self, key, waiter_id):
            raise RuntimeError("boom")

        async def waiter_count(self, key):
            raise RuntimeError("boom")

    monkeypatch.delenv("ACCOUNT_SESSION_LOCK_FAIL_CLOSED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    lock = MainAccountSessionLock(
        backend=_BrokenBackend(), wait_timeout=1, retry_interval=0.05
    )
    with pytest.raises(Exception) as excinfo:
        async with lock.acquire("shopee", "main-a"):
            pass
    assert "账号会话锁服务不可用" in str(excinfo.value)


@pytest.mark.asyncio
async def test_sync_diagnostics_survive_broken_backend_sync_view() -> None:
    """同步诊断接口读后端视图失败时必须降级, 不能把主流程带崩。"""

    class _BrokenSyncView:
        def is_locked_sync(self, key):
            raise RuntimeError("boom")

        def waiter_count_sync(self, key):
            raise RuntimeError("boom")

        async def set_nx(self, key, token, ttl_seconds):
            return True

        async def get(self, key):
            return None

        async def delete_if_token(self, key, token):
            return True

        async def renew(self, key, token, ttl_seconds):
            return True

        async def add_waiter(self, key, waiter_id, ttl_seconds):
            return None

        async def remove_waiter(self, key, waiter_id):
            return None

        async def waiter_count(self, key):
            return 0

    from backend.services.main_account_session_lock import MainAccountSessionLock

    lock = MainAccountSessionLock(backend=_BrokenSyncView(), wait_timeout=1)

    assert lock.is_locked("shopee", "main-a") is False
    assert lock.waiter_count("shopee", "main-a") == 0


# ---------------------------------------------------------------------------
# 续期心跳
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renew_loop_logs_and_continues_when_renew_raises() -> None:
    from backend.services.main_account_session_lock import MainAccountSessionLock

    calls = {"count": 0}

    class _FlakyBackend:
        async def renew(self, key, token, ttl_seconds):
            calls["count"] += 1
            raise RuntimeError("temporary failure")

    lock = MainAccountSessionLock(backend=_FlakyBackend(), renew_interval=0.01)
    task = asyncio.create_task(lock._renew_loop(_FlakyBackend(), "k", "token"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls["count"] >= 1


@pytest.mark.asyncio
async def test_renew_loop_stops_when_lock_is_lost() -> None:
    """续期返回 False(锁已不属于本任务) -> 心跳必须停止并告警。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    class _LostBackend:
        async def renew(self, key, token, ttl_seconds):
            return False

    lock = MainAccountSessionLock(backend=_LostBackend(), renew_interval=0.01)
    await asyncio.wait_for(lock._renew_loop(_LostBackend(), "k", "token"), timeout=2)


@pytest.mark.asyncio
async def test_renew_loop_propagates_cancellation() -> None:
    from backend.services.main_account_session_lock import MainAccountSessionLock

    started = asyncio.Event()

    class _SlowBackend:
        async def renew(self, key, token, ttl_seconds):
            started.set()
            await asyncio.sleep(10)
            return True

    lock = MainAccountSessionLock(backend=_SlowBackend(), renew_interval=0.01)
    task = asyncio.create_task(lock._renew_loop(_SlowBackend(), "k", "token"))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# REDIS_PASSWORD 注入(URL 不带密码但环境变量有密码 -> AUTH 必然失败)
# ---------------------------------------------------------------------------


def test_inject_redis_password_keeps_url_that_already_has_password() -> None:
    """URL 已含密码 -> 原样使用(以 URL 为准, 不覆盖)。"""
    from backend.services.main_account_session_lock import inject_redis_password

    url = "redis://:existing-secret@redis:6379/0"
    assert inject_redis_password(url, "other-secret") == url


def test_inject_redis_password_injects_password_into_plain_url() -> None:
    """URL 不含密码 + 有密码 -> 注入 ``:password@``。"""
    from backend.services.main_account_session_lock import inject_redis_password

    assert (
        inject_redis_password("redis://redis:6379/0", "s3cret")
        == "redis://:s3cret@redis:6379/0"
    )


def test_inject_redis_password_keeps_url_when_no_password_available() -> None:
    """URL 不含密码 + 没有环境变量密码 -> 原样使用(兼容无密码 Redis)。"""
    from backend.services.main_account_session_lock import inject_redis_password

    url = "redis://redis:6379/0"
    assert inject_redis_password(url, "") == url
    assert inject_redis_password("", "s3cret") == ""


def test_inject_redis_password_reads_environment_variable(
    monkeypatch,
) -> None:
    """省略 password 时读环境变量 ``REDIS_PASSWORD``。"""
    from backend.services.main_account_session_lock import inject_redis_password

    monkeypatch.setenv("REDIS_PASSWORD", "env-secret")
    assert (
        inject_redis_password("redis://redis:6379/0")
        == "redis://:env-secret@redis:6379/0"
    )

    monkeypatch.setenv("REDIS_PASSWORD", "")
    assert inject_redis_password("redis://redis:6379/0") == "redis://redis:6379/0"


def test_inject_redis_password_handles_userinfo_without_password() -> None:
    """畸形形态: URL 带 userinfo 但**没有**密码 -> 保留用户名并补上密码。"""
    from backend.services.main_account_session_lock import inject_redis_password

    assert (
        inject_redis_password("redis://some-user@redis:6379/0", "s3cret")
        == "redis://some-user:s3cret@redis:6379/0"
    )


def test_inject_redis_password_keeps_unparsable_url() -> None:
    """URL 解析失败 -> 原样使用(连接层会给出明确报错)。"""
    from backend.services.main_account_session_lock import inject_redis_password

    broken = "redis://[::1"
    assert inject_redis_password(broken, "s3cret") == broken


def test_inject_redis_password_keeps_url_without_supported_scheme() -> None:
    """评审 F8: 无 scheme 的畸形 URL 必须**原样返回**(不得产出更畸形的 URL)。

    ``urlsplit("host:6379")`` **不抛异常**(把 ``host`` 当 scheme、``6379`` 当 path)
    → 旧实现会产出 ``host://:pw@/6379`` —— 比原 URL 更畸形, 且必然连不上。
    """
    from backend.services.main_account_session_lock import inject_redis_password

    assert inject_redis_password("host:6379", "s3cret") == "host:6379"
    assert inject_redis_password("localhost:6379", "s3cret") == "localhost:6379"
    # 受支持的 scheme 仍然正常注入
    assert (
        inject_redis_password("rediss://redis:6379/0", "s3cret")
        == "rediss://:s3cret@redis:6379/0"
    )


@pytest.mark.asyncio
async def test_shared_redis_client_injects_password_and_masks_it_in_logs(
    monkeypatch,
    caplog,
) -> None:
    """端到端: URL 不带密码 -> 用环境变量密码连接, 且密码绝不能进日志。"""
    from backend.services import main_account_session_lock as lock_module

    await lock_module.reset_shared_redis_client()
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("REDIS_PASSWORD", "top-secret")

    used: Dict[str, Any] = {}

    def _from_url(url: str, **kwargs):
        used["url"] = url
        return _StubRedisClient()

    _install_fake_redis_asyncio(monkeypatch, _from_url)

    with caplog.at_level("INFO"):
        client = await lock_module.get_shared_redis_client()

    assert client is not None
    assert used["url"] == "redis://:top-secret@redis:6379/0"
    assert "top-secret" not in caplog.text
    assert "***@redis:6379" in caplog.text

    await lock_module.reset_shared_redis_client()


# ---------------------------------------------------------------------------
# 降级为进程内锁时必须按 error 告警(跨进程保护已失效)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_degrade_to_local_lock_is_reported_as_error(
    monkeypatch,
    caplog,
) -> None:
    """Redis 不可用而 fail-open 时, 必须 error 级别告警并写明跨进程保护失效。"""
    from backend.services import main_account_session_lock as lock_module

    monkeypatch.setenv("ACCOUNT_SESSION_LOCK_BACKEND", "redis")

    async def _fake_client():
        return None

    monkeypatch.setattr(lock_module, "get_shared_redis_client", _fake_client)

    with caplog.at_level("ERROR"):
        backend = await lock_module.create_default_backend(fail_closed=False)

    assert isinstance(backend, lock_module.LocalSessionLockBackend)
    assert "跨进程保护已失效" in caplog.text


# ---------------------------------------------------------------------------
# 等待者 Hash 的 TTL 必须覆盖整个等待时长
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_waiter_hash_ttl_covers_the_configured_max_wait_time() -> None:
    """等待者 Hash 的 TTL 必须覆盖**配置的最大等待时长**(锁 TTL 只有 300s)。"""
    from backend.services.main_account_session_lock import (
        MainAccountSessionLock,
        MainAccountSessionLockTimeoutError,
    )

    backend = FakeSessionLockBackend()
    holder = MainAccountSessionLock(backend=backend, ttl_seconds=300, wait_timeout=1800)
    waiter = MainAccountSessionLock(
        backend=backend, ttl_seconds=300, wait_timeout=1800, retry_interval=0.05
    )

    async with holder.acquire("shopee", "main-a"):
        task = asyncio.create_task(waiter.acquire("shopee", "main-a").__aenter__())
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # 等待时长 1800s -> 等待者 Hash 的 TTL 必须 >= 1800(否则 waiter_count 会归零)
    assert backend.waiter_ttls == [1800 + 60]


@pytest.mark.asyncio
async def test_redis_backend_refreshes_waiter_hash_ttl_on_every_registration() -> None:
    """每次登记等待者都要刷新等待者 Hash 的 TTL。"""
    from backend.services.main_account_session_lock import RedisSessionLockBackend

    client = FakeRedisClient()
    backend = RedisSessionLockBackend(client)

    await backend.add_waiter("lock-key", "waiter-1", 1860)
    await backend.add_waiter("lock-key", "waiter-2", 1860)

    expire_calls = [payload for name, payload in client.calls if name == "expire"]
    assert expire_calls == [("lock-key:waiters", 1860), ("lock-key:waiters", 1860)]


# ---------------------------------------------------------------------------
# 进程内后端的事件循环作用域标识不得用 id(loop)(id 会被复用)
# ---------------------------------------------------------------------------


def test_local_backend_scope_uses_a_non_reusable_loop_identity() -> None:
    """作用域标识必须是唯一且**不复用**的 uuid, 不能是 ``id(loop)``。"""
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()
    scopes: List[Tuple[str, str]] = []

    async def _capture():
        scopes.append(backend._scope("k"))

    loop_a = asyncio.new_event_loop()
    try:
        loop_a.run_until_complete(_capture())
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        loop_b.run_until_complete(_capture())
    finally:
        loop_b.close()

    # 两个不同的 event loop -> 两个不同的作用域(否则会误判为「同一把锁」)
    assert scopes[0] != scopes[1]
    assert scopes[0][1] == scopes[1][1] == "k"
    # 明确不是 id(loop): 是 uuid4 的 32 位 hex
    assert len(scopes[0][0]) == 32
    assert all(char in "0123456789abcdef" for char in scopes[0][0])


@pytest.mark.asyncio
async def test_local_backend_scope_is_stable_within_the_same_loop() -> None:
    """同一个 event loop 内, 作用域标识必须稳定(否则锁根本互斥不了)。"""
    from backend.services.main_account_session_lock import LocalSessionLockBackend

    backend = LocalSessionLockBackend()
    first = backend._scope("k")
    second = backend._scope("k")

    assert first == second



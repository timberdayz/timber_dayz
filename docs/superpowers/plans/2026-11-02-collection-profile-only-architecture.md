# 采集会话 profile 单一载体架构实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 废除「会话文件」(`data/sessions/**`)，把登录态收敛到唯一的持久化 profile 载体；同时打通 IP 隔离（代理）链路，让账号级代理真正生效。

**Architecture:** 账号 = 一台"电脑" = 一个 profile 目录（`profiles/<platform>/<main_account_id>`）。人工巡店用同一个 profile 开 headed 浏览器，人工登录后由 Chromium 自动持久化；采集顺序路径直接 `launch_persistent_context(profile, proxy)`；并行路径从 profile context 导出**内存**快照，每数据域 `new_context(快照)` 并发。代理按账号配置，绑在 profile 上。

**Tech Stack:** Python 3 / Playwright async / Redis（跨进程锁）/ FastAPI + SQLAlchemy async / pytest / Vue 3

---

## 0. 前置条件与约束

| 项 | 值 |
|---|---|
| 规范来源 | `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` **生效版 v3**（R1~R8 / P1~P4 / D1~D7） |
| 作废计划 | `docs/superpowers/plans/2026-11-02-collection-session-overwrite-semantics.md`（已标注作废） |
| 分支 / worktree | `feature/session-profile-only` / `.worktrees/session-profile-only` |
| 单文件测试 | `python -m pytest backend/tests/<file>.py -v` |
| Redis | 本地 `:16379`，容器 `6379`；已有依赖，无需新组件 |
| 提交规范 | 显式文件列表；禁 `git add -A` / `git add .`；禁 `git stash` |
| 数据库 | **本计划不改表结构** —— 代理配置放 `core.shop_accounts.extra_config`（jsonb，已有），避免迁移与生产变更 |
| 前端 | 需要改（诊断字段），见 Task 8 |

**不在本计划范围**：真正配置代理池与账号-IP 绑定策略（运维动作）；`modules/collectors/shopee_collector.py` 与 `modules/collectors/base/base_collector.py` 的**自有**会话体系（落 `temp/sessions/`，与本次无关，不动）；`modules/core/db/schema_parts/platform.py` 的 legacy `core.platform_accounts.proxy_required` 列（保留不动）。

---

## 1. 变更地图

| 文件 | 责任 | Task |
|---|---|---|
| `modules/utils/sessions/session_manager.py` | 收窄为「profile 路径 + 指纹路径」，删会话文件读写 | 7 |
| `modules/utils/pwcli_native.py` | 删 `command_state_save` / 会话文件回写 | 6 |
| `scripts/pwcli_helpers.ps1` | 删 `Save-PwcliPlatformState` 及 3 个平台包装 | 6 |
| `scripts/pwcli_inspection_panel.py` + `static/index.html` | 删「保存会话」按钮与端点 | 6 |
| `modules/apps/collection_center/runtime_session.py` | profile 模式为唯一路径；代理注入；快照内存化 | 2, 4, 5 |
| `modules/apps/collection_center/executor_v2.py` | 顺序路径走 profile；删会话读写；诊断字段 | 2, 4, 5, 8 |
| `modules/utils/sessions/device_fingerprint.py` | 代理注入条件放宽 | 2 |
| `backend/services/account_loader_service.py` | 透出代理配置 | 1 |
| `backend/domains/collection/routers/collection_tasks.py` | 传 proxy；诊断字段 | 2, 8 |
| `backend/services/main_account_session_coordinator.py` + 新文件 | 跨进程账号锁 | 3 |
| `frontend/src/domains/collection/views/collection/CollectionTasks.vue` | 诊断展示 | 8 |
| `frontend/scripts/collectionTaskSessionQualityUi.test.mjs` | 前端守卫测试 | 8 |

**保留不动**：`modules/utils/persistent_browser_manager.py` 的 profile 管理能力（28 处调用方），**只移除它写会话文件的耦合**（`save_context_state` → `:350`）。

---

## Task 0: 建立 worktree 并确认基线

- [ ] **Step 1: 建 worktree**

```powershell
git worktree add .worktrees/session-profile-only -b feature/session-profile-only main
```

- [ ] **Step 2: 确认基线绿**

```powershell
Set-Location F:\Vscode\python_programme\AI_code\xihong_erp\.worktrees\session-profile-only
python -m pytest backend/tests/test_session_manager_protection.py backend/tests/test_session_storage_roots.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_task_runtime_metadata.py backend/tests/test_legacy_shop_session_cleanup.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_persistent_browser_manager_session_metadata.py -v
```

Expected: 全部 PASS。**基线本身失败的，停下报告，不要算到本计划头上。**

---

## Task 1: 账号代理配置透出

**Files:**
- Modify: `backend/services/account_loader_service.py:34`、`:70`
- Test: `backend/tests/test_collection_task_runtime_metadata.py`（追加）或新建 `backend/tests/test_account_proxy_config.py`

- [ ] **Step 1: 写失败测试**

```python
def test_account_loader_exposes_proxy_config(tmp_path, monkeypatch):
    """P1：代理配置挂账号上，从 extra_config 透出到账号 dict。"""
    from backend.services import account_loader_service as als

    account = als._build_account_dict(
        {
            "id": 1,
            "platform": "shopee",
            "shop_account_id": "shopee_sg_x",
            "main_account_id": "shopee KR",
            "extra_config": {
                "proxy": {"enabled": True, "server": "http://10.0.0.9:8080", "region": "sg"}
            },
        }
    )
    assert account["proxy_enabled"] is True
    assert account["proxy_server"] == "http://10.0.0.9:8080"
    assert account["proxy_region"] == "sg"
```

> 实施时先读 `account_loader_service.py` 现有实现，函数名可能不同 —— 按实际结构调整测试，但断言内容不变。

- [ ] **Step 2: 跑测试确认失败** → FAIL（当前只透出 `proxy_required`）

- [ ] **Step 3: 实现**

在 `account_loader_service.py` 的账号 dict 组装处，从 `extra_config["proxy"]` 透出三个平铺键：

```python
    proxy_cfg = dict((extra_config or {}).get("proxy") or {})
    account["proxy_enabled"] = bool(proxy_cfg.get("enabled"))
    account["proxy_server"] = str(proxy_cfg.get("server") or "").strip()
    account["proxy_region"] = str(proxy_cfg.get("region") or "").strip()
    # 兼容历史遗留布尔标记
    account["proxy_required"] = bool(
        account.get("proxy_required")
        or (extra_config or {}).get("legacy_proxy_required")
        or account["proxy_enabled"]
    )
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```powershell
git add backend/services/account_loader_service.py backend/tests/test_account_proxy_config.py
git commit -m "feat(account): 从 extra_config 透出账号级代理配置"
```

---

## Task 2: 打通代理链路（P1~P4）

**Files:**
- Modify: `backend/domains/collection/routers/collection_tasks.py:1725-1739`、`:1920-1934`（传 proxy）
- Create: `backend/services/account_proxy_config.py`（共享代理解析 helper）
- Modify: `backend/services/shop_account_loader_service.py:58-74`（`compat_account` 补 proxy 键 —— **主运行时路径**）
- Modify: `backend/services/account_loader_service.py`（改用共享 helper）
- Modify: `modules/apps/collection_center/executor_v2.py:1839`（proxy 参数）、`:426-441`（allowed 白名单）、`:1976`（browser launch）、`:6008-6013`（并行路径硬编码 None）
- Modify: `modules/apps/collection_center/runtime_session.py:422-437`（allowed 白名单）、`:758-762`（`launch_persistent_context` 传 proxy）、`:819`
- Modify: `modules/utils/sessions/device_fingerprint.py:445-446`
- Test: `backend/tests/test_account_proxy_config.py`（追加）

**复用点（不要从零写）**：`modules/utils/proxy_config_manager.py` 已有 `get_proxy_for_account`（`:287`）、`get_account_proxy_region`（`:310`）、`get_playwright_proxy_config`（`:486`）；代理池配置在 `config/proxy_config.py`。

- [ ] **Step 1: 写失败测试**

```python
def test_proxy_reaches_context_options():
    """代理必须进入 Playwright context options（白名单不能丢）。"""
    from modules.apps.collection_center.runtime_session import (
        _build_playwright_context_options_from_fingerprint,
    )

    opts = _build_playwright_context_options_from_fingerprint(
        {"proxy": {"server": "http://10.0.0.9:8080"}}
    )
    assert opts["proxy"]["server"] == "http://10.0.0.9:8080"
```

- [ ] **Step 2: 跑测试确认失败** → FAIL（allowed 白名单不含 `proxy`）

- [ ] **Step 3: 修白名单（两处）**

`modules/apps/collection_center/runtime_session.py:422-437` 与 `modules/apps/collection_center/executor_v2.py:426-441` 的 `allowed` 集合都加入 `"proxy"`。

- [ ] **Step 4: 放宽指纹注入条件**

`modules/utils/sessions/device_fingerprint.py:445-446`：

```python
        # 添加代理配置：代理已由账号配置解析并注入，此处不再依赖旧的 proxy_required 布尔标记
        if proxy:
            context_options["proxy"] = proxy
```

- [ ] **Step 5: 路由层传 proxy**

`backend/domains/collection/routers/collection_tasks.py` 的两处 `executor.execute(...)` 调用，补上：

```python
    proxy=resolve_account_proxy(account),
```

新增 helper（放在 `backend/services/account_loader_service.py` 或就近的 service）：

```python
def resolve_account_proxy(account: dict) -> dict | None:
    """P1/P3：账号级代理。server 为空则不启用。"""
    server = str((account or {}).get("proxy_server") or "").strip()
    if not server or not (account or {}).get("proxy_enabled"):
        return None
    proxy = {"server": server}
    region = str((account or {}).get("proxy_region") or "").strip()
    if region:
        proxy["region"] = region
    return proxy
```

> 若 `proxy_config_manager.get_playwright_proxy_config` 能按 region 解析出可用代理，优先用它（它已有池化与健康检查逻辑）。

- [ ] **Step 5b: 补主运行时路径的 proxy 透出（Task 1 实施中发现的缺口）**

Task 1 只改了 `AccountLoaderService`，但**主运行时路径优先走 `shop_account_loader_service`**：

- `backend/services/collection_account_runtime_service.py:132-141` —— 先试 `shop_account_loader_service`，成功直接 `return shop_payload["compat_account"]`
- `backend/domains/collection/routers/collection_tasks.py:1842-1850` —— 同样是先 shop loader，`:1854-1860` 才 fallback 到 `AccountLoaderService`
- `backend/services/shop_account_loader_service.py:58-74` 的 `compat_account` **一个 proxy 键都没有**（连 `proxy_required` 都没有）

因此必须在 `shop_account_loader_service` 的 `compat_account` 里同样平铺出 `proxy_enabled` / `proxy_server` / `proxy_region`（数据同样来自 `core.shop_accounts.extra_config["proxy"]`），否则 Task 2 接浏览器时拿到的账号 dict 里没有代理信息。

**实现建议**：把解析逻辑抽成一个共享 helper（例如 `backend/services/account_proxy_config.py` 的 `extract_proxy_config(extra_config) -> dict`），`AccountLoaderService` 与 `ShopAccountLoaderService` 都调用它，避免两处重复解析规则。

- [ ] **Step 6: 浏览器级全局代理（避免 per-context 另起进程）**

`modules/apps/collection_center/executor_v2.py:1976`：

```python
            browser_instance = await browser_type.launch(
                **self._build_runtime_launch_kwargs(debug_mode),
                **({"proxy": proxy} if proxy else {}),
            )
```

`runtime_session.py:758-762`：

```python
    context = await browser_type.launch_persistent_context(
        user_data_dir=str(profile_path),
        **({"proxy": proxy} if proxy else {}),
        **launch_options,
        **context_options,
    )
```

- [ ] **Step 7: 修并行路径硬编码 None**

`modules/apps/collection_center/executor_v2.py:6008-6013`：

```python
                fp_opts = await _get_fingerprint_context_options_async(
                    platform, session_owner_id, account, proxy=proxy
                )
```

`proxy` 从 `execute_parallel_domains` 的入参或账号 dict 解析得到。

- [ ] **Step 8: 跑测试**

```powershell
python -m pytest backend/tests/test_account_proxy_config.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py -v
```

- [ ] **Step 9: 提交**

```powershell
git add backend/domains/collection/routers/collection_tasks.py backend/services/account_loader_service.py modules/apps/collection_center/executor_v2.py modules/apps/collection_center/runtime_session.py modules/utils/sessions/device_fingerprint.py backend/tests/test_account_proxy_config.py
git commit -m "feat(collection): 打通账号级代理链路，代理进入浏览器与 context"
```

---

## Task 3: 跨进程账号锁（R6）

**Files:**
- Create: `backend/services/main_account_session_lock.py`
- Modify: `modules/apps/collection_center/executor_v2.py:854`、`:5843`
- Test: `backend/tests/test_main_account_session_lock.py`（新建）

**问题**：`MainAccountSessionCoordinator` 是**进程内** `asyncio.Lock`（模块级单例 `main_account_session_coordinator.py:60`），生产 celery `--concurrency=4`（prefork 4 子进程）下跨进程无效 → 同一 profile 可能被两个浏览器进程同时打开。

- [ ] **Step 1: 写失败测试**

```python
import pytest


def test_lock_is_acquired_across_independent_coordinator_instances():
    """两个独立实例（模拟两个 celery 子进程）必须互斥。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    lock_a = MainAccountSessionLock()
    lock_b = MainAccountSessionLock()

    async def scenario():
        async with lock_a.acquire("shopee", "shopee KR"):
            with pytest.raises(Exception):
                async with lock_b.acquire("shopee", "shopee KR", timeout=0.2):
                    pass

    import asyncio
    asyncio.run(scenario())
```

> 实现若用 Redis，本测试需 Redis 可用；**同时提供一个内存实现作为测试替身**，测试用注入的后端。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

`backend/services/main_account_session_lock.py`：

```python
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional


class MainAccountSessionLock:
    """账号级跨进程锁。

    同一 main_account_id 的 profile 目录不能被两个浏览器进程同时打开，
    因此锁必须是跨进程的（Redis SET NX），进程内 asyncio.Lock 不够。
    """

    def __init__(self, redis_client=None, *, key_prefix: str = "xihong:account_session_lock", ttl_seconds: int = 1800):
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._local: dict[str, asyncio.Lock] = {}

    def _key(self, platform: str, main_account_id: str) -> str:
        return f"{self._key_prefix}:{str(platform or '').strip().lower()}:{str(main_account_id or '').strip()}"

    @asynccontextmanager
    async def acquire(self, platform: str, main_account_id: str, *, timeout: float = 300.0) -> AsyncIterator[None]:
        key = self._key(platform, main_account_id)
        token = f"{os.getpid()}-{time.time()}"
        deadline = time.time() + max(0.0, timeout)
        acquired = False
        while time.time() < deadline:
            if self._redis is None:
                acquired = True
                break
            acquired = bool(self._redis.set(key, token, nx=True, ex=self._ttl_seconds))
            if acquired:
                break
            await asyncio.sleep(1.0)
        if not acquired:
            raise TimeoutError(f"account session lock timeout: {platform}/{main_account_id}")
        try:
            yield
        finally:
            if self._redis is not None:
                try:
                    self._redis.delete(key)
                except Exception:
                    pass
```

> 生产实现里释放应校验 token（Lua CAS）以免误删他人锁；实施时补上。

- [ ] **Step 4: executor 接入**

`executor_v2.py:854` 与 `:5843` 改成使用新锁（保留 `MainAccountSessionCoordinator` 的 `waiter_count` / `is_locked` 诊断接口，内部改为读新锁）。

- [ ] **Step 5: 跑测试并提交**

```powershell
git add backend/services/main_account_session_lock.py modules/apps/collection_center/executor_v2.py backend/tests/test_main_account_session_lock.py
git commit -m "feat(collection): 账号级会话锁改为跨进程实现"
```

---

## Task 4: 采集顺序路径统一走 profile（R1 / R4 / R8）

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py:517-572`（`choose_runtime_strategy`）、`:694-721`
- Modify: `modules/apps/collection_center/executor_v2.py:899-1034`（`_open_runtime_bundle`）
- Test: `backend/tests/test_collection_session_reuse_contract.py`（改写）

- [ ] **Step 1: 改写既有测试表达新规则**

`test_collection_session_reuse_contract.py` 中断言「人工会话优先于 profile」的两条用例（`test_manual_storage_state_wins_over_existing_profile`、`test_open_runtime_bundle_auto_prefers_manual_session_over_persistent_profile`）改为断言**恒走 profile**。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: `choose_runtime_strategy` 收敛**

正式采集一律 `persistent_profile`：

```python
    if execution_kind == "formal_collection":
        return RuntimeStrategyDecision(
            mode="persistent_profile",
            reason="profile_is_single_source_of_truth",
            used_storage_state=False,
            used_persistent_profile=True,
            fallback_allowed=False,
        )
```

其余分支（工具/录制）保留。

- [ ] **Step 4: `_open_runtime_bundle` 去掉 storage_state 分支**

`executor_v2.py:914-1010` 的「优先人工会话 / 读会话文件 / bootstrap」三段全部删除，统一走：

```python
            runtime_bundle = await self._open_runtime_bundle(
                session_runtime_mode="auto",
                browser=browser,
                browser_type=browser_type,
                platform=platform,
                session_owner_id=session_owner_id,
                runtime_account=runtime_account,
                storage_state=None,
                launch_kwargs=self._build_runtime_launch_kwargs(debug_mode=debug_mode),
                proxy=proxy,
            )
```

并删除 `_manual_storage_state_path` / `_manual_storage_state_exists` / `_load_or_bootstrap_session_async` / `_should_prefer_manual_storage_state`。

- [ ] **Step 5: R8 指纹一致性**

确认 `normalize_persistent_profile_context_options` 在顺序与并行两条路径都生效（profile 模式下不注入 UA/locale/时区）。**顺序路径现在也是 profile 模式，所以自动一致** —— 在测试中断言这一点。

- [ ] **Step 6: R7 正常关闭**

确认采集结束时 context 被**正常 close**（`await context.close()`），不是 `playwright.stop()` 强杀。在 `open_persistent_runtime_bundle` 的调用方补上 `finally: await context.close()`。

- [ ] **Step 7: 跑测试并提交**

```powershell
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_collection_session_reuse_contract.py
git commit -m "refactor(collection): 正式采集统一走持久化 profile"
```

---

## Task 5: 并行路径快照纯内存化（R5）

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py:835-955`（`snapshot_runtime_storage_state`）
- Modify: `modules/apps/collection_center/executor_v2.py:5948-5954`
- Test: `backend/tests/test_collection_executor_session_alignment.py`（改写）

- [ ] **Step 1: 改写测试**

`test_collection_executor_session_alignment.py:1026` 附近断言快照落盘的用例 → 改为断言**不落盘**（`data/sessions` 下不产生新文件）。

- [ ] **Step 2: 实现**

`runtime_session.py` 的 `snapshot_runtime_storage_state`：删除 `persist` 参数与 `if persist and session_owner_id:` 分支（含 TikTok 的 `seller_local_storage` 落盘前置检查一并删除 —— 不落盘就不需要这个检查）。函数只返回内存快照。

`executor_v2.py:5948-5954` 改为 `persist=False` → 直接去掉 `persist` 实参。

删除 `persist_runtime_session_state`（`:958-964`）。

- [ ] **Step 3: 跑测试并提交**

```powershell
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_session_alignment.py
git commit -m "refactor(collection): 并行快照改为纯内存，不再落盘会话文件"
```

---

## Task 6: 巡店面板删除「保存会话」（D6 / R3）

**Files:**
- Modify: `scripts/pwcli_inspection_panel.py:35-39`（`SAVE_HELPERS`）、`:176-210`（`run_action` / `/api/accounts/save`）
- Modify: `scripts/pwcli_inspection_panel_static/index.html:200`、`:223`、`:290`、`:299`
- Modify: `scripts/pwcli_helpers.ps1:249-304`（`Save-PwcliPlatformState`）、`:363`、`:368`、`:373`（三个平台包装）
- Modify: `modules/utils/pwcli_native.py:899-935`（`command_state_save`）、`:325-348`（`save_default_storage_state_from_context`）、`:1006`（`main` 分支）
- Test: `backend/tests/test_pwcli_inspection_panel_reporting.py`、`tests/test_pwcli_inspection_panel.py`、`backend/tests/test_pwcli_helpers_session_targeting.py`

- [ ] **Step 1: 改写测试**

面板测试中「save」动作的用例改为断言：`/api/accounts/save` **返回 404**（端点已删除），前端 HTML **不含**「保存会话」按钮。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 删面板端点**

`scripts/pwcli_inspection_panel.py`：删除 `SAVE_HELPERS` 字典、`/api/accounts/save` 路由、`run_action` 里的 `"saving"`/`"saved"` 分支（保留 `open` / `skip`）。

- [ ] **Step 4: 删前端按钮**

`scripts/pwcli_inspection_panel_static/index.html`：删除 `:290` 的 `<button class="save danger">保存会话</button>` 与 `:299` 的监听绑定；更新 `:200` 与 `:223` 的说明文案（改为「打开账号浏览器后人工登录，登录态由浏览器 profile 自动保存」）。

- [ ] **Step 5: 删 PowerShell 保存函数**

`scripts/pwcli_helpers.ps1`：删除 `Save-PwcliPlatformState`（`:249-304`）与 `Save-PwcliMiaoshouState` / `Save-PwcliShopeeState` / `Save-PwcliTiktokState`（`:363`、`:368`、`:373`）。

- [ ] **Step 6: 删 pwcli_native 的 state-save**

`modules/utils/pwcli_native.py`：删除 `command_state_save`、删 `main()` 里的 `state-save` 分支；`save_default_storage_state_from_context` 中 `state_mode == "session_manager"` 分支改为**不写会话文件**（profile 自己会存）。

- [ ] **Step 7: 跑测试并提交**

```powershell
git add scripts/pwcli_inspection_panel.py scripts/pwcli_inspection_panel_static/index.html scripts/pwcli_helpers.ps1 modules/utils/pwcli_native.py backend/tests/test_pwcli_inspection_panel_reporting.py tests/test_pwcli_inspection_panel.py backend/tests/test_pwcli_helpers_session_targeting.py
git commit -m "feat(pwcli): 巡店面板移除保存会话，登录态由 profile 自动持久化"
```

---

## Task 7: 废弃会话文件（R1）

**Files:**
- Modify: `modules/utils/sessions/session_manager.py`（大幅收窄）
- Modify: `modules/apps/collection_center/executor_v2.py:240`、`:246`、`:256`、`:316`
- Modify: `modules/apps/collection_center/runtime_session.py:253`、`:306`、`:326`
- Modify: `modules/utils/persistent_browser_manager.py:350`、`:432`
- Modify: `modules/collectors/miaoshou_smart_login.py:505`
- Modify: `modules/collectors/shopee_workflow_manager.py:424`
- Modify: `modules/services/shopee_exporter.py:194`
- Modify: `modules/utils/sessions/legacy_shop_artifact_cleanup.py:47`
- Modify: `backend/main.py:289-309`、`run.py:360-363`
- Delete: `backend/tests/test_session_manager_protection.py`
- Test: `backend/tests/test_session_storage_roots.py`（改写）

**会话文件写入点清单（全部要清零）**：

| 位置 | 处置 |
|---|---|
| `executor_v2.py:316` `_save_session_async` | 删除函数与调用点 |
| `runtime_session.py:326` `_save_session_async` | 删除 |
| `runtime_session.py:306` bootstrap 落盘 | 删除（profile 就是引导源） |
| `persistent_browser_manager.py:350` `save_context_state` | 改为只关闭 profile context，不写文件 |
| `pwcli_native.py:340` 人工保存 | Task 6 已删 |
| `miaoshou_smart_login.py:505` | 删除写回（Chromium 自己存） |

- [ ] **Step 1: 写失败测试**

`backend/tests/test_session_storage_roots.py` 改写：断言 `SessionManager` **不再暴露** `save_session` / `load_session` / `get_session_path` / `restore_session` / `cleanup_expired_sessions`，且 `get_persistent_profile_path` 仍可用。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 收窄 `SessionManager`**

保留：`__init__`（仅 `persistent_profiles_path`）、`get_persistent_profile_path`、新 `get_profile_path`（legacy `data/session_profiles`，`miaoshou_smart_login.py:134` 仍在用）。

删除：`save_session` / `load_session` / `restore_session` / `get_session_path` / `get_session_metadata` / `get_session_info` / `list_sessions` / `cleanup_expired_sessions` / `delete_session` / `is_session_valid` / `describe_storage_targets` / `session_quality_score` / `session_meets_quality_gate` / `_merge_tiktok_storage_state` / `_session_freshness_timestamp` / `_write_json_atomic`（若无其他用户）/ `safe_session_account_dirname`（改由 `get_persistent_profile_path` 统一）。

保留 `modules/utils/sessions/__init__.py` 的导出，但去掉 `SessionManager` 之外的失效符号。

- [ ] **Step 4: 清理调用点**

按上表逐条改。`shopee_workflow_manager.py:424` 的 `restore_session` 调用改为「用 `SessionManager().get_persistent_profile_path(...)` + profile context」。

`modules/services/shopee_exporter.py:194` 的 `from_persistent_session` —— 它当前 `'cookies' in session_data` 判断恒假（`load_session` 返回的是带 `storage_state` 包装的结构），改造时按 profile 语义重写或直接废弃该函数（先查调用方再定）。

- [ ] **Step 5: 清理遗留物收集与告警**

`legacy_shop_artifact_cleanup.py:47` 移除 `data/sessions` 候选；`backend/main.py:289-309` 与 `run.py:360-363` 的告警文案改为「检测到店铺级 profile 遗留」。

- [ ] **Step 6: 跑测试**

```powershell
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_legacy_shop_session_cleanup.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_persistent_browser_manager_session_metadata.py -v
```

> 旧语义测试（人工保护 / 质量分回退 / 30 天门禁）随 `test_session_manager_protection.py` 一并删除；其余文件里断言旧 metadata 的用例按新语义改写。

- [ ] **Step 7: 提交**

```powershell
git rm backend/tests/test_session_manager_protection.py
git add modules/utils/sessions/session_manager.py modules/utils/sessions/__init__.py modules/apps/collection_center/executor_v2.py modules/apps/collection_center/runtime_session.py modules/utils/persistent_browser_manager.py modules/collectors/miaoshou_smart_login.py modules/collectors/shopee_workflow_manager.py modules/services/shopee_exporter.py modules/utils/sessions/legacy_shop_artifact_cleanup.py backend/main.py run.py backend/tests/test_session_storage_roots.py backend/tests/test_legacy_shop_session_cleanup.py
git commit -m "refactor(session): 废弃会话文件，登录态只保留 profile 单一载体"
```

---

## Task 8: 诊断字段与前端展示

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:1103-1149`（`_runtime_session_diagnostics`）
- Modify: `backend/domains/collection/routers/collection_tasks.py:436-466`
- Modify: `frontend/src/domains/collection/views/collection/CollectionTasks.vue:360-394`、`:1080-1120`
- Modify: `frontend/scripts/collectionTaskSessionQualityUi.test.mjs`
- Test: `backend/tests/test_collection_task_runtime_metadata.py`

**字段变更**：

| 旧 | 新 |
|---|---|
| `session_quality_score` | 删除 |
| `session_quality_gate_passed` | 删除 |
| `session_quality_source` | `session_source`（取值 `profile`） |
| `session_manual_seeded` | 删除 |
| `session_protected` | 删除 |
| — | `session_profile_path`（新增） |
| — | `session_reused`（新增，profile 内是否已有登录态） |
| — | `session_proxy`（新增，脱敏后的代理标识） |

- [ ] **Step 1: 改写后端测试**

`test_collection_task_runtime_metadata.py:41` 的断言改为新字段集。

- [ ] **Step 2: 实现后端**

`executor_v2._runtime_session_diagnostics` 产出新字段；`collection_tasks.py:436-466` 同步抽取与透出。

- [ ] **Step 3: 改前端**

`CollectionTasks.vue`：删除「质量来源」「质量评分」「质量门槛」「人工播种」「会话保护」五项；新增「会话载体」（profile 路径）、「是否复用」「出口代理」三项。同步更新 `getSessionQualitySourceLabel` 等标签映射函数。

- [ ] **Step 4: 改前端守卫测试**

`frontend/scripts/collectionTaskSessionQualityUi.test.mjs` 重写为断言新字段。

- [ ] **Step 5: 跑测试**

```powershell
python -m pytest backend/tests/test_collection_task_runtime_metadata.py -v
cd frontend; npm run build; node scripts/collectionTaskSessionQualityUi.test.mjs
```

- [ ] **Step 6: 提交**

```powershell
git add modules/apps/collection_center/executor_v2.py backend/domains/collection/routers/collection_tasks.py frontend/src/domains/collection/views/collection/CollectionTasks.vue frontend/scripts/collectionTaskSessionQualityUi.test.mjs backend/tests/test_collection_task_runtime_metadata.py
git commit -m "refactor(diagnostics): 会话诊断字段改为 profile 载体语义"
```

---

## Task 9: 文档同步

**Files:**
- Modify: `docs/guides/COLLECTION_SESSION_LIFECYCLE.md`（v3 → v3.1，回填实现结果）
- Modify: `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`（「代理预留」段改为已实现）
- Modify: `docs/superpowers/plans/STATUS.md`（新增条目）
- Verify: `docs/ACTIVE_DOCS.md`（已指向本文，无需改）

- [ ] **Step 1: 回填概念文档**

§10 验收口径补实测列；§11 变更记录追加 v3.1。

- [ ] **Step 2: 更新指纹指南的代理段**

原文「执行器创建 context 时暂不注入 proxy，当前采集在住宅 IP 环境下无需启用」→ 改为已实现，并说明注入位置（浏览器级全局代理优先）。

- [ ] **Step 3: STATUS.md 加条目**

```
## Session Profile-Only Architecture (2026-11)

- Plan: `docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md`
- Spec: `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` (v3)
```

- [ ] **Step 4: 跑文档校验**

```powershell
python scripts/verify_rules_completeness.py
python scripts/verify_root_md_whitelist.py
python scripts/verify_utf8_source_hygiene.py
```

Expected: 全部 exit=0。

- [ ] **Step 5: 提交**

```powershell
git add docs/guides/COLLECTION_SESSION_LIFECYCLE.md docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md docs/superpowers/plans/STATUS.md
git commit -m "docs(session): 回填 profile 单一载体架构实施结果"
```

---

## Task 10: 全量验收

- [ ] **Step 1: 后端全量测试**

```powershell
python -m pytest backend/tests -q
```

Expected: 全部 PASS（基线 318 附近；新增失败必须定位到本计划改动）。

- [ ] **Step 2: 前端构建 + 守卫测试**

```powershell
cd frontend
npm run build
node scripts/collectionTaskSessionQualityUi.test.mjs
```

Expected: exit=0。

- [ ] **Step 3: 发布前门禁**

```powershell
python scripts/verify_release_local.py --skip-build
```

Expected: exit=0。

- [ ] **Step 4: 真实采集验收（关键）**

在**本地笔记本**上按序执行：

1. 备份并清空旧的会话目录（不进 VCS）：把 `data/sessions/` 整体改名为 `data/sessions.bak-20261102`
2. 清空 `profiles/shopee/shopeeKR/` 下的 Chromium 状态（或整个目录改名备份）
3. 采集任务 A（`shopee_sg_eternalbloom_local`）→ 应要求登录 + 验证码
4. **检查 `profiles/shopee/shopeeKR/Default/Cookies` 的 mtime 已更新**，且 `data/sessions/` 下**没有**新文件
5. 立刻再跑一次采集 A' → **必须免验证码**
6. 巡店面板「打开巡店」→ 浏览器用的是**同一个** `profiles/shopee/shopeeKR` 目录（核对进程参数/目录占用）→ 人工登录 → 关闭浏览器 → 再次采集应免验证码
7. 巡店面板**没有**「保存会话」按钮
8. 并行采集（多数据域）→ 任务成功，且 `data/sessions/` 仍无新文件
9. 代理灰度：给一个账号配置 `extra_config.proxy` → 采集该账号 → 核对出站 IP 是代理 IP

**Expected**：第 4、5、6、7、8、9 步全部符合。**第 4 或第 5 步不过 → 停下报告，不要加临时补丁。**

- [ ] **Step 5: 记录验收结论**

写进 `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` §10。

- [ ] **Step 6: 提交**

```powershell
git add docs/guides/COLLECTION_SESSION_LIFECYCLE.md
git commit -m "docs(session): 记录 profile 单一载体架构的真实验收结论"
```

---

## 11. 合并与收尾

- [ ] **Step 1: 合并回 main**

```powershell
Set-Location F:\Vscode\python_programme\AI_code\xihong_erp
git merge --no-ff feature/session-profile-only
```

- [ ] **Step 2: 清理 worktree**

```powershell
git worktree remove .worktrees/session-profile-only
git branch -d feature/session-profile-only
```

- [ ] **Step 3: 复核**

```powershell
git status --porcelain
git log --oneline -5
```

Expected: 工作区干净。

> **本计划只改本地 main 分支。发布（打 tag、推双远端）不在范围内**，需另行按 `docs/guides/RELEASE_CHECKLIST.md` 执行。

---

## 附：风险与回退

| 风险 | 表现 | 处置 |
|---|---|---|
| profile 目录被两个进程同时打开 | Chromium 报 profile 锁 / 启动失败 | Task 3 的跨进程锁；Task 10 Step 4 验证 |
| 代理参数错误 | 连不上平台 / 大量验证码 | Task 2 单账号灰度；失败则先摘掉代理只验主链路 |
| Chromium per-context proxy 另起进程 | 并行 4 路 → 4 个浏览器进程，资源飙升 | 优先用浏览器级全局代理；Task 2 Step 6 |
| 顺序路径切 profile 后稳定性下降 | 登录组件在 profile 下行为不同 | Task 4 保留 storage_state 分支的 git 历史，必要时单点回滚 |
| 旧测试大面积红 | pytest 失败 | 逐条判断「旧语义断言」 vs 「真回归」；前者按新语义改写，后者停下报告 |
| 删掉会话文件后某些 legacy 采集器失效 | `shopee_collector` / `miaoshou_smart_login` 报错 | 这两套有**自有**会话体系（`temp/sessions/`），不受影响；若报错按 Task 7 清单补 |
| profile 异常退出丢登录态 | 表现为"登录了但没记住" | R7：正常关闭；异常后重跑自愈 |

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
- Modify: `backend/services/account_proxy_config.py`（**Task 1 已落地**，本 Task 扩展：凭据形态、无 scheme 归一）
- Modify: `backend/services/shop_account_loader_service.py:58-74`（`compat_account` 补 proxy 键 —— **主运行时路径**）
- Modify: `backend/services/account_loader_service.py`（修 Minor 1 的错误注释）
- Modify: `modules/apps/collection_center/executor_v2.py:1839`（proxy 参数）、`:426-441`（allowed 白名单）、`:1976`（browser launch）、`:5863`、`:6008-6013`（硬编码 None）
- Modify: `modules/apps/collection_center/runtime_session.py:422-437`（allowed 白名单）、`:758-762`（`launch_persistent_context` 传 proxy）、`:819`
- Modify: `modules/utils/sessions/device_fingerprint.py:445-446`
- Test: `backend/tests/test_account_proxy_config.py`（追加）

**复用点（不要从零写）**：`backend/services/account_proxy_config.py` 已有 `extract_proxy_config` / `split_proxy_credentials` / `mask_proxy_server`（Task 1 落地）。

**Task 2 必须满足的 5 条硬约束**（来自 Task 1 代码质量复审）：

| # | 约束 | 原因 |
|---|---|---|
| C1 | **账号自有 `proxy_server` 必须优先于遗留地区池**；账号有自有代理时**绝不**走 `proxy_config_manager.get_playwright_proxy_config` | 遗留链路全程不读账号自有的 `proxy_server`，只按 account_id + 地区池选 → 不改会「一账号两个 IP」，直接违反 P1/P2 |
| C2 | `proxy_config_manager` 的 `fallback_to_direct: True`（`config/proxy_config.py:221`）在**自有代理场景下必须禁用** | 代理失败静默回退直连 → 账号从宿主 IP 出现，IP 隔离形同虚设 |
| C3 | 代理串**必须带 scheme**（本仓约定见 `proxy_config_manager.py:61`）；无 scheme 的输入要归一（补 `http://`）或显式拒绝 | Playwright python 绑定不校验 `proxy.server`，畸形值只会在导航期报 `ERR_PROXY_CONNECTION_FAILED`，看不出是配置写错 |
| C4 | 凭据形态要定契约：**支持**「内嵌在 URL 的 user:pass」与「独立的 `proxy.username` / `proxy.password`」两种 | `extract_proxy_config` 目前静默丢弃独立的 username/password，形态未定会导致配置写不进去 |
| C5 | `mask_proxy_server` 要有生产调用方（规范 §8 的 `session_proxy` 脱敏诊断字段） | 否则是死代码；诊断字段本身在 Task 8 落地，本 Task 至少接线 |

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

新增 helper（**放在 `backend/services/account_proxy_config.py`**，与解析规则同源）：

```python
def resolve_account_proxy(account: dict) -> dict | None:
    """P1/P3/C1/C3/C4：账号级代理。

    账号自有 proxy_server 优先；绝不静默回退到遗留地区池。
    返回 Playwright 形态：{"server": ..., "username": ..., "password": ...}
    """
    server = str((account or {}).get("proxy_server") or "").strip()
    if not server or not (account or {}).get("proxy_enabled"):
        return None
    proxy = split_proxy_credentials(server)
    # 独立的 username/password 形态（覆盖 split 只认 URL 内嵌凭据的缺口）
    username = str((account or {}).get("proxy_username") or "").strip()
    password = str((account or {}).get("proxy_password") or "").strip()
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy
```

> **不要**在这里调用 `proxy_config_manager.get_playwright_proxy_config` —— 那是遗留地区池链路，会给同一个账号第二个 IP（C1）。

- [ ] **Step 5b: 补主运行时路径的 proxy 透出（Task 1 实施中发现的缺口）**

Task 1 只改了 `AccountLoaderService`，但**主运行时路径优先走 `shop_account_loader_service`**：

- `backend/services/collection_account_runtime_service.py:132-141` —— 先试 `shop_account_loader_service`，成功直接 `return shop_payload["compat_account"]`
- `backend/domains/collection/routers/collection_tasks.py:1842-1850` —— 同样是先 shop loader，`:1854-1860` 才 fallback 到 `AccountLoaderService`
- `backend/services/shop_account_loader_service.py:58-74` 的 `compat_account` **一个 proxy 键都没有**（连 `proxy_required` 都没有）

因此必须在 `shop_account_loader_service` 的 `compat_account` 里同样平铺出 `proxy_enabled` / `proxy_server` / `proxy_region`（数据同样来自 `core.shop_accounts.extra_config["proxy"]`），否则 Task 2 接浏览器时拿到的账号 dict 里没有代理信息。

**实现建议**：把解析逻辑抽成一个共享 helper（`backend/services/account_proxy_config.py` 的 `extract_proxy_config(extra_config) -> dict`），`AccountLoaderService` 与 `ShopAccountLoaderService` 都调用它，避免两处重复解析规则。

> Task 1 已落地 `account_proxy_config.py`，本 Step 直接 import 即可。**导入后模块 docstring 里「单一定义源」的说法才成立**（Task 1 复审 Minor 2）。

- [ ] **Step 5c: 扩展 `account_proxy_config.py`（C3 / C4）**

1. **无 scheme 归一**（C3）：`split_proxy_credentials("user:pass@h:8080")` 目前产出 `server="h:8080"`（无 scheme）。本仓约定必带 scheme（`proxy_config_manager.py:61`）。请归一为 `http://h:8080`，并补一条用例钉死。
2. **独立凭据形态**（C4）：`extract_proxy_config` 目前只回 3 个键，`proxy: {username, password}` 会被静默丢弃。请一并透出 `proxy_username` / `proxy_password`（来源仍是 `extra_config["proxy"]`），并让 `resolve_account_proxy` 优先用独立字段、无独立字段时回退 URL 内嵌凭据。
3. `mask_proxy_server` 要能把独立形态的凭据也抹掉。

- [ ] **Step 5d: 修 Task 1 复审的 Minor**

- **Minor 1**：`backend/services/account_loader_service.py:64-65` 的注释「getattr 兜底：测试替身（SimpleNamespace）可能没有 extra_config 属性」**事实错误** —— `_extract_legacy_shop_extra` 在更早位置就访问 `shop.extra_config`，属性缺失会先抛 `AttributeError`，`getattr` 实际不可达。请改成「与 legacy 路径保持一致的兜底」之类的准确表述，或直接写 `shop_account.extra_config`。
- **Minor 4**：补一条 loader 级回归断言 —— `enabled="false"` 时 `account["proxy_required"] is False`（I1 的生产后果防线，成本极低）。
- **Minor 6**：`account_proxy_config` 模块 docstring 承诺「任何异常输入都安全兜底」—— 这只对 `extract_proxy_config` 成立，**loader 层不成立**（legacy 那步先抛）。请把承诺范围写准。

- [ ] **Step 5e: 禁用自有代理场景下的直连回退（C2）**

`config/proxy_config.py:221` 的 `fallback_to_direct: True` 属于遗留地区池链路。**自有代理场景下不能让代理失败静默回退直连**。

要求：账号配置了自有代理时，代理不可用必须**显式失败**（抛错 / 任务失败 + 明确错误信息），不得直连。本 Task 只需保证**新链路**（`resolve_account_proxy` → 浏览器）不走那条静默回退；遗留 `proxy_config_manager` 链路本次**不动**（它不在采集主链路上），但要在代码注释里写明这一边界。

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

## Task 3~7 实施顺序与依赖（只读盘点后修订）

```
Task 2（代理链路）✅ 已完成
   │
   ▼
Task 3（跨进程锁）           ← 必须先于 Task 4
   │                          恒走 profile 后争用面从「部分账号」变「全部账号」
   ▼
Task 4（顺序路径恒走 profile）
   │
   ▼
Task 4.5（有头验证码回退走 profile）  ← 计划外新增，阻塞级
   │                                    否则 Task 7 删会话文件后，人工登录链路静默断链
   ▼
Task 5（并行快照纯内存）  ┐
                          ├→ 可并行
Task 6（面板删保存会话）  ┘
   │
   ▼
Task 7（废弃会话文件）    ← 必须最后
   │
   ▼
Task 8（诊断字段+前端）→ Task 9（文档同步）→ Task 10（验收）
```

**隐含耦合（计划原本没画，实施时必须一起考虑）**：

| # | 耦合 | 说明 |
|---|---|---|
| 1 | **Task 4.5 ↔ Task 7** | 有头回退用会话文件当中转站（`executor_v2.py:3078` 写 → `:2924` 读 → `:2960` 注入）。**Task 7 删文件前必须先重写这条路径** |
| 2 | **Task 4 ↔ Task 7** | `_resolve_session_metadata`（`:1107`）与 `_should_skip_post_login_session_persist`（`:2896`）依赖会话 metadata 的 `manual_seeded/protected` → Task 4 后 TikTok 落盘被跳过、shopee/miaoshou 仍落盘 → **行为分裂，必须在 Task 7 前统一** |
| 3 | **Task 5 ↔ Task 7** | Task 5 只删「并行快照落盘」，顺序路径 `:1343` 仍写、`session_manager.load_session` 读时回写 → **两个都要做**才满足「`data/sessions/` 不再产生新文件」 |
| 4 | **Task 6 ↔ Task 7** | `pwcli_native.save_default_storage_state_from_context` 的 `session_manager` 分支既是 Task 6 的「人工保存」、也是 Task 7 的写入点 → **改一处即可覆盖两个 Task** |
| 5 | **Task 6 ↔ R7/P2** | Task 6 把「打开巡店」变成唯一登录入口 → `command_close` 强杀（F6-4）与「巡店无代理」（F6-5）从「次要」升级为「阻塞」 |
| 6 | **Task 3 ↔ Task 7** | `persistent_browser_manager` 的 `_alt` 旁路 profile（F7-1）会把登录态分散到第二个目录 → **跨进程锁的 key 必须同时覆盖 `<account>` 与 `<account>_alt`**，或直接删掉旁路 |

---

## Task 3: 跨进程账号锁（R6）

**Files:**
- Create: `backend/services/main_account_session_lock.py`
- Modify: `backend/services/main_account_session_coordinator.py`（保留兼容外壳，内部改走跨进程锁）
- Modify: `modules/apps/collection_center/executor_v2.py:844-873`（顺序路径锁边界）、`:5838-5867`、`:5998-5999`（并行路径）
- Modify: `backend/utils/config.py`（锁后端开关）
- Test: `backend/tests/test_main_account_session_lock.py`（新建）
- Test 改写: `backend/tests/test_collection_executor_reused_session_scope.py:241-245`、`:837`、`backend/tests/test_collection_executor_session_alignment.py:999-1001`、`backend/tests/test_main_account_session_coordinator.py`

### Task 3 必须先纠正的 3 个前提（原计划有误，已只读核实）

| # | 原计划说法 | 核实结论 | 影响 |
|---|---|---|---|
| F1 | 「生产 celery `--concurrency=4`（prefork 4 子进程）下跨进程无效」 | **归因错误**。采集根本不在 celery 里跑（`backend/tasks/` 无 collection 任务）。真实多进程来源是 `Dockerfile.backend:89-91` 的 `gunicorn backend.main:app --workers 4`，且 `docker-compose.prod.yml:89 backend-api`（`DEPLOYMENT_ROLE: api`）与 `:181 backend-collector`（`DEPLOYMENT_ROLE: collector`）是**两个独立容器** → 最多 8 个 OS 进程 | 按错误归因设计会修错地方。锁必须按「gunicorn 4 worker × 2 容器」建模 |
| F2 | 未提及 API 触发路径 | `collection_tasks.py:748` 和 `:996` → `asyncio.create_task(...)` → **API 触发的采集跑在任意一个 gunicorn worker 里**；该路径**不受** `CollectionLeaderLock` 保护（`should_start_collection_queue_runner("api")` 返回 False，`backend/main.py:143-144`） | **这正是最容易并发打开同一 profile 的来源**，锁必须覆盖它 |
| F3 | 锁只改 `:854` / `:5843` 两处 | 顺序路径的锁边界**与 profile 生命周期不对齐**：`executor_v2.py:2110-2115` 的 `_run_with_main_account_session_lock(operation=_coordinated_login)` 在 `_coordinated_login` 返回时就释放锁，而 persistent profile context 一直活到 `:2648-2658` 的 `_cleanup_browser_runtime` 才关闭 | 换成跨进程锁后**仍然会双开**。锁的持有范围必须改为「profile 打开 → profile 关闭」 |

> 缓解事实：Chromium 的 user-data-dir 自带 `SingletonLock`，同机双开会**报错**而不是静默双开。但代价是第二个任务直接失败并抛 Chromium 原始错误，用户看到的是莫名报错而不是「排队等待」。跨进程锁的价值正是把它变成排队。

### 锁后端选型（已只读核实，非拍脑袋）

**选 Redis（`SET NX` + token 校验释放），不走 Postgres advisory lock。**

- Redis 在本项目是**强制基础设施**：`backend/utils/config.py:254-258` 生产环境 `REDIS_ENABLED=false` 直接 `RuntimeError`；`redis>=5.0.0` 已在 `requirements.txt:24` / `backend/requirements.txt:25`；异步客户端 `backend/utils/redis_client.py:17,50-75`（`redis.asyncio` + `socket_timeout=5`）已在用；验证码等待路径 `collection_tasks.py:1440-1462` 已经依赖 `app.state.redis`。
- TTL 是硬需求（进程被 kill 必须能自动解锁）→ Redis 原生支持；PG advisory lock 是 session 级、无 TTL。
- 需要 `is_locked` / `waiter_count` 诊断接口 → Redis 可查；PG advisory lock 只能「试拿」，查不到状态。
- `REDIS_URL` 与 `CELERY_BROKER_URL` 同实例同 db=0（`docker-compose.prod.yml:363-366`）→ Redis 挂了采集本来就派发不出来，「Redis 不可用」与「采集不可用」是同一故障，fail-open 无意义。
- PG advisory lock 另有 4 个坑：无碰撞哈希（`collection_leader_lock.py:18` 的 crc32 只有 32 位，账号规模上去会碰撞）、session 级锁要绑长连接（采集侧拿不到 `get_async_db()`，得用 `AsyncSessionLocal()` 直开）、无 TTL 需自建租约、查不到状态需自建状态表。

### Task 3 必须满足的硬约束

| # | 约束 | 原因 |
|---|---|---|
| L1 | **锁粒度用 `main_account_id`**（不是 `shop_account_id`） | `core.shop_accounts.main_account_id` 是 FK（`platform.py:182-187`），1 主账号 → N 店铺账号；按店铺锁会漏掉「同一主账号下多店铺并行打开同一 profile」 |
| L2 | **释放必须 token 校验 + Lua CAS** | 现有 `main_account_session_coordinator.py:46-47` 的 `if state.lock.locked(): release()` 是「检查与释放非原子」；照搬到分布式锁会「误删他人锁」 |
| L3 | **Key 必须白名单 + 截断 + 64 位哈希**，禁止 `crc32` | `main_account_id` 实测含中文/空格/全角（如 `虾皮巴西（东朗照明主体）`、`shopee KR`）；crc32 32 位碰撞会导致「两个不同主账号互相阻塞」 |
| L4 | **TTL 必须与续期解耦**：实现续期（heartbeat，每 TTL/3 刷新 EXPIRE） | `executor_v2.py:755-756` 的 `DEFAULT_TASK_TIMEOUT=1800` **从未被强制**（全文件无 `wait_for`/`asyncio.timeout`），采集不是 celery 任务（无 `task_time_limit`）→ 采集可跑 > 30 min，单次 `EX 1800` 必然提前过期 → 锁提前失效 → 双开 |
| L5 | **不可用时分级**：生产 Redis 不可用 → **fail-closed**（任务失败 + 明确错误「账号会话锁服务不可用」）；开发/测试 → **fail-open 到进程内 `asyncio.Lock`** | 双开 profile 会造成**静默的会话互相覆盖**（会话是「无条件覆盖写入」），数据损坏比拒绝采集危险得多。开发环境降级与 `config.py:260-272`「生产强制 Redis、开发降级内存」同构 |
| L6 | **必须保留既有兼容契约** | `acquire(platform, main_account_id)` 位置参数签名、`@asynccontextmanager` 且 **yield None**（不能改成 yield token）、`waiter_count` / `is_locked` 必须继续存在、`CollectionExecutorV2(main_account_session_coordinator=...)` 注入点（`executor_v2.py:760`）必须继续可用 |
| L7 | **`waiter_count` 在分布式下不得退化为恒 0** | 若实现成「key 存在 → is_locked=True, waiter_count=0」，则 `executor_v2.py:852-863` 的「等待主账号会话」状态推送**永远不触发** → 前端可观测性退化。需用独立 ZSET/Hash 记录等待者 |
| L8 | **单元测试一律用假后端，绝不连真实 Redis/PG** | `backend/tests/conftest.py:26-69` 记录过「测试写生产数据」的真实事故。参照 `backend/tests/test_collection_leader_lock.py:44` 的 monkeypatch 模式 + `pg_engine` fixture 的 `ImportError → pytest.skip` + `integration` marker 双开关 |
| L9 | **Redis 客户端的获取路径必须打通**（只读核实后的关键细节） | `backend/utils/redis_client.py:50-75` 把客户端挂在 **`app.state.redis`**；而采集执行在 `asyncio.create_task` 里（`collection_tasks.py:748`/`:996`）**不在请求上下文里，拿不到 `app`**。但 `CollectionExecutorV2` 是在**请求上下文**里构造的（`collection_tasks.py:1686`、`:1887`）→ **可以在构造时把 `app.state.redis` 传进去** |

### Redis 客户端获取方式（L9 的落地建议，三选一）

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A（推荐） | **进程级惰性单例**：新模块里自己 `aioredis.from_url(os.getenv("REDIS_URL"))` + `ping`，失败则返回 None（fail-open 到进程内锁） | 不依赖 FastAPI app 生命周期；采集/巡店/脚本三条路径都能用 | 每个 gunicorn worker 各建一条连接（4×2=8 条，可接受）；需处理连接关闭 |
| B | router 构造 executor 时把 `app.state.redis` 注入 → executor 传给 coordinator | 复用现有连接，零额外连接 | 巡店面板/脚本等**不经过 router** 的路径拿不到锁 → 需另配 |
| C | A + B 混合：优先用注入的，没有则惰性建 | 覆盖最全 | 实现稍复杂 |

> 无论选哪个，`REDIS_URL` 的**密码必须脱敏后再进日志**（`redis_client.sanitize_redis_url_for_log` 已提供，`redis_client.py:32-47`）。

### 实施前必须确认的两个外部事实（无法从代码确定）

| # | 待确认 | 影响 | 建议动作 |
|---|---|---|---|
| E1 | 生产 Redis 的 `maxmemory-policy` | 若为 `volatile-lru` / `allkeys-lru`，**带 TTL 的锁 key 会被 LRU 淘汰** → 锁凭空消失 → 双开（`REDIS_URL` 与 Celery broker 同 db=0，`docker-compose.prod.yml:363-366`） | ✅ **已核实**：本地 Redis 实测 `maxmemory-policy = noeviction`（Redis 7.4.7）；生产 compose 的启动命令是 `redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}`（`docker-compose.prod.yml:63`）**未覆盖 maxmemory-policy** → 用默认值 `noeviction` → **锁 key 不会被淘汰**。仍建议生产上线前跑一次 `redis-cli CONFIG GET maxmemory-policy` 确认 |
| E2 | 生产实际生效的 compose 组合与 Redis 认证形态 | `docker-compose.collection.yml:112` 只有 `REDIS_URL: redis://${REDIS_HOST}:${REDIS_PORT}/0` —— **无密码、无内建 redis 服务**，与其他 compose 的 `${REDIS_PASSWORD}` 拼装不一致。若生产用这套栈，新锁会因认证失败**永远拿不到锁** → 全部采集被 fail-closed 拒绝 | ⚠️ **仍待运维确认**。代码侧必须让「认证失败」与「锁冲突」报出**不同**错误（前者是「锁服务不可用」，后者是「该主账号正被其他任务占用」） |

### 锁边界设计（修 F3）

| 路径 | 现状 | 目标 |
|---|---|---|
| 顺序路径 `execute()` | 锁覆盖「打开 profile + 登录 + 验证码等待」，**不覆盖** profile 的采集期使用（`:2115` 释放 → `:2648` 才关闭） | 锁持有范围改为**「打开 profile → 关闭 profile」**，即与 `_cleanup_browser_runtime` 对齐 |
| 并行路径 `execute_parallel_domains()` | 锁覆盖「打开 profile + 登录 + 验证码 + snapshot」，`:6003` 已关闭 context → **边界已对齐** | 保持；扇出的 `new_context(storage_state=...)` 不碰 profile 目录，不受锁约束 |

> 锁边界扩大后，`waiter_count` / `is_locked` 的可观测语义会变（等锁时间变长），需在诊断文案上体现。

- [ ] **Step 1: 写失败测试**

```python
import pytest


def test_lock_is_acquired_across_independent_lock_instances():
    """两个独立实例（模拟两个 gunicorn worker）必须互斥。"""
    from backend.services.main_account_session_lock import MainAccountSessionLock

    lock_a = MainAccountSessionLock(backend=FakeLockBackend())
    lock_b = MainAccountSessionLock(backend=FakeLockBackend())

    async def scenario():
        async with lock_a.acquire("shopee", "shopee KR"):
            with pytest.raises(Exception):
                async with lock_b.acquire("shopee", "shopee KR", timeout=0.2):
                    pass

    import asyncio
    asyncio.run(scenario())
```

> **两个实例必须共享同一个假后端**（模拟同一个 Redis），否则测的是两个独立内存字典、必然不互斥 —— 这是「假绿」的典型来源。假后端要提供 `set_nx(key, token, ttl)` / `get(key)` / `delete_if_token(key, token)` / `add_waiter` / `remove_waiter`。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

`backend/services/main_account_session_lock.py`：

```python
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import socket
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

_SAFE = re.compile(r"[^a-z0-9_-]+")


def _sanitize(value: str, *, limit: int = 40) -> str:
    """可读前缀：白名单化 + 截断（仅用于排障，不参与唯一性判定）。"""
    return _SAFE.sub("_", str(value or "").strip().lower())[:limit]


def _digest(platform: str, main_account_id: str) -> str:
    """64 位摘要：避免 crc32 的 32 位碰撞。"""
    raw = f"{str(platform or '').strip().lower()}|{str(main_account_id or '').strip()}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


class MainAccountSessionLock:
    """账号级跨进程锁。

    同一 main_account_id 的 profile 目录不能被两个浏览器进程同时打开，
    因此锁必须是跨进程的（Redis SET NX），进程内 asyncio.Lock 不够。
    """

    def __init__(self, backend=None, *, key_prefix: str = "xihong:acct_lock", ttl_seconds: int = 300):
        self._backend = backend
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._local: dict[str, asyncio.Lock] = {}

    def _key(self, platform: str, main_account_id: str) -> str:
        return (
            f"{self._key_prefix}:{_sanitize(platform)}:"
            f"{_sanitize(main_account_id)}:{_digest(platform, main_account_id)}"
        )
```

> **TTL 不再是单一固定 1800**：并行路径典型 1~2 min、最坏 ~8 min → 300s 够；顺序路径若按 F3 扩到 profile 全生命周期，则必须**实现续期**（每 TTL/3 刷新 EXPIRE）而不是一次 `EX`。任何覆盖登录阶段的锁，TTL 必须 > 验证码等待上限 300s（`collection_tasks.py:70`）。
>
> **释放必须 Lua CAS**（L2），不能照搬 `delete(key)`：典型脚本 `if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end`。
>
> **holder 信息**要写进锁值（`{pid, task_id, hostname, acquired_at}`）便于排障并支持 `is_locked` 返回详情。
>
> **重入**（L2 配套）：`asyncio.Lock` 不可重入，同 key 同协程二次 acquire 会自死锁；跨进程版会变成「等一个永远不释放的分布式锁」，更隐蔽。新实现必须显式处理同 token 重入（放行或快速失败），且 `acquire` 必须有 `timeout` 兜底。

- [ ] **Step 4: 接入 executor（含锁边界修正）**

- `executor_v2.py:844-873`（`_run_with_main_account_session_lock`）与 `:5838-5867`、`:5998-5999` 改成使用新锁。
- 保留 `MainAccountSessionCoordinator` 的 `waiter_count` / `is_locked` 诊断接口，**内部改为读新锁**（`main_account_session_coordinator.py` 变成兼容外壳，L6）。
- **锁边界按 F3 修正**：顺序路径的锁要覆盖到 profile 关闭（`:2648` `_cleanup_browser_runtime`），否则跨进程锁形同虚设。
- 锁不可用时按 L5 分级：生产 fail-closed、开发 fail-open 到进程内 `asyncio.Lock`。
- `waiter_count` 按 L7 用独立 ZSET/Hash 记录等待者，保证 `:852-863` 的状态推送仍工作。

- [ ] **Step 5: 改写会被打破的既有测试**

- `backend/tests/test_collection_executor_reused_session_scope.py:241-245` —— **源码字符串断言**硬编码了 `"main_account_session_coordinator.acquire("` 字面量 → 改造后必然失败，必须同步改写。
- `backend/tests/test_collection_executor_reused_session_scope.py:837` —— 硬编码 `"_run_with_main_account_session_lock"`。
- `backend/tests/test_collection_executor_session_alignment.py:999-1001` —— 把 `acquire` / `is_locked` / `waiter_count` 三个方法整体打桩 → 新接口若改签名要一起改。
- `backend/tests/test_main_account_session_coordinator.py` —— 3 个用例直接实例化协调器并断言 `waiter_count` 的「等锁者计数」语义 → 新实现必须保住这个语义。

- [ ] **Step 6: 跑测试并提交**

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pytest backend/tests/test_main_account_session_lock.py backend/tests/test_main_account_session_coordinator.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_executor_session_alignment.py -v
```

```powershell
git add backend/services/main_account_session_lock.py backend/services/main_account_session_coordinator.py backend/utils/config.py modules/apps/collection_center/executor_v2.py backend/tests/test_main_account_session_lock.py backend/tests/test_main_account_session_coordinator.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_executor_session_alignment.py
git commit -m "feat(collection): 账号级会话锁改为跨进程实现并对齐 profile 生命周期"
```

> **顺序提示**：Task 3 必须**先于** Task 4 落地。Task 4 把顺序路径改成「恒走 profile」后，所有采集都会打开 profile 目录 → 争用面从「部分账号」变成「全部账号」→ 锁的吞吐与 TTL 压力显著上升。Task 4 落地后需重新评估等待超时与 TTL。

---

## Task 4: 采集顺序路径统一走 profile（R1 / R4 / R8）

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py:517-572`（`choose_runtime_strategy`）、`:694-721`
- Modify: `modules/apps/collection_center/executor_v2.py:899-1034`（`_open_runtime_bundle`）、`:467-588`（`_prepare_runtime_page_bundle` 死代码）
- Test: `backend/tests/test_collection_session_reuse_contract.py`（改写）

### Task 4 只读盘点结论（实施前必读，行号以真实代码为准）

| # | 事实 | 影响 |
|---|---|---|
| F4-1 | `choose_runtime_strategy`（`runtime_session.py:519-582`）生产只有 1 个调用方（`executor_v2.py:954`），另 1 处在工具脚本；`force_persistent_profile` 与 `parallel_mode` 两个分支**在生产中恒为 False**（死分支） | 收敛时可一并删死分支，但**不要**误判并行路径不受影响 —— 两处调用都传 `execution_kind="formal_collection"` |
| F4-2 | `runtime_session.py:996-1021` 的 storage_state 回退段已被 `normalized_mode != "persistent_profile"` 条件保护 ✅ | `normalized_mode` 变成 `persistent_profile` 后该段自动跳过，不会误读会话文件 |
| F4-3 | **profile 模式下会多开一个 Chromium 进程**：`executor_v2.py:1991-2006` 的 `browser_type.launch(...)` 起的 browser 在 profile 模式下完全不用（profile 分支只吃 `browser_type`），但会一直挂到 `_cleanup_browser_runtime`（`:2653`）才关 | 同账号同代理下多一个进程 → 资源浪费 + IP 出口多一个。Task 4 应让 profile 模式**不再创建这个 browser** |
| F4-4 | **`executor_v2._prepare_runtime_page_bundle`（`:467-588`）是死代码**，但它模块级 import 了 `_load_or_bootstrap_session_async` | Step 4 删掉 `_load_or_bootstrap_session_async` 后，若不先删这段死代码 → **`executor_v2` 整个模块 ImportError → 所有采集全挂**。必须先删死代码 |
| F4-5 | **R8 注入点共 7 处**，其中 `executor_v2.py:6050-6068`（并行扇出 `domain_context_options`）仍在注入 UA/locale/timezone | 与 R8「顺序与并行指纹行为必须一致」**直接冲突**，需在 Task 5 一并处理或明确说明取舍 |
| F4-6 | `_profile_contains_state`（`runtime_session.py:460-464`）只判「目录非空」；`get_persistent_profile_path` 会 `mkdir` 空目录 | 从未登录的账号也返回 True → `reused_session=True` 误报 → Task 8 的 `session_reused` 字段失真。**Task 4 或 Task 8 必须修** |
| F4-7 | `_should_skip_post_login_session_persist`（`executor_v2.py:2866-2898`）依赖 `_runtime_session_mode == "persistent_profile"` 且 session_metadata 里没有 `manual_seeded/protected` | Task 4 后顺序路径恒为 profile → TikTok 自动落盘被跳过，但**非 TikTok 平台（shopee/miaoshou）仍会落盘会话文件**（`:1325-1361` 的条件只有 `save_session_after_login`）→ **Task 7 前必须统一** |

- [ ] **Step 1: 改写既有测试表达新规则**

`test_collection_session_reuse_contract.py` 中断言「人工会话优先于 profile」的两条用例（`test_manual_storage_state_wins_over_existing_profile`、`test_open_runtime_bundle_auto_prefers_manual_session_over_persistent_profile`）改为断言**恒走 profile**。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 先删死代码（F4-4）**

**先**删除 `executor_v2._prepare_runtime_page_bundle`（`:467-588`）及其模块级 import，再做 Step 4。顺序反了会导致 `executor_v2` ImportError。

- [ ] **Step 4: `choose_runtime_strategy` 收敛**

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

- [ ] **Step 5: `_open_runtime_bundle` 去掉 storage_state 分支**

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

- [ ] **Step 6: profile 模式不再多开 Chromium（F4-3）**

`executor_v2.py:1991-2006` 的 browser 创建条件加上「非 persistent_profile 模式」，避免 profile 模式下多挂一个进程。

- [ ] **Step 7: R8 指纹一致性**

确认 `normalize_persistent_profile_context_options` 在顺序与并行两条路径都生效（profile 模式下不注入 UA/locale/时区）。**顺序路径现在也是 profile 模式，所以自动一致** —— 在测试中断言这一点。

并行扇出的 `domain_context_options`（F4-5）若仍注入 UA/locale/timezone，必须在测试中显式断言「顺序与并行一致」，否则 R8 不成立。

- [ ] **Step 8: R7 正常关闭**

确认采集结束时 context 被**正常 close**（`await context.close()`），不是 `playwright.stop()` 强杀。在 `open_persistent_runtime_bundle` 的调用方补上 `finally: await context.close()`。

- [ ] **Step 9: 跑测试并提交**

```powershell
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_collection_session_reuse_contract.py
git commit -m "refactor(collection): 正式采集统一走持久化 profile"
```

---

## Task 4.5: 有头验证码回退走 profile（计划外新增，阻塞级）

**为什么必须单独一个 Task**：盘点发现 `_run_headful_login_fallback`（`executor_v2.py:2966-3102`）**完全绕开 profile**：

```
profile 模式下需要人工过验证码时
  → :2989-2995 另起一套 async_playwright()，开一个全新的、非 persistent、注入了完整指纹的 headed 浏览器
  → 人工在这个浏览器里登录
  → :3078  把登录态写进**会话文件**
  → :2924  再从**会话文件**读回来
  → :2960  new_context(storage_state=...) 注入主 context
```

**Task 7 删掉会话文件后，这条路径直接断链** —— 登录成功但主 context 拿不到登录态 → **采集在登录页跑完（静默失败，不报错）**。

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:2966-3102`（`_run_headful_login_fallback`）、`:2922-2960`（`_prepare_runtime_page_bundle` 一带的 storage_state 注入）

**要求**：

1. 有头登录回退**改为在同一个 profile 目录上开 headed persistent context**（`launch_persistent_context(user_data_dir=<profile 路径>, headless=False, proxy=...)`），登录态由 Chromium 自己写进 profile。
2. 回退结束后**正常 close**（R7），让 Chromium 刷盘。
3. 不再有任何「写会话文件 → 读会话文件」的中转。
4. `proxy` 必须透传（Task 2 已把代理接到 `_run_headful_login_fallback`，这里要保证它用的是账号代理）。

**验收**：测试断言「有头回退走的是 profile 目录，且全程不产生 `data/sessions` 写入」。

> 这条与 Task 6 的 `command_close` 优雅关闭（F6-4）是同一类问题：**必须正常关闭，profile 才记得住登录态**。

---

## Task 5: 并行路径快照纯内存化（R5）

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py:835-955`（`snapshot_runtime_storage_state`）、`:958-964`（`persist_runtime_session_state`）
- Modify: `modules/apps/collection_center/executor_v2.py:5948-5954`
- Test: `backend/tests/test_collection_executor_session_alignment.py`（改写）

### Task 5 只读盘点结论（实施前必读）

| # | 事实 | 影响 |
|---|---|---|
| F5-1 | 并行路径的快照**本来就是内存 dict**：`executor_v2.py:5994-5999` 产出 → 扇出时 `browser.new_context(storage_state=...)` 直接用它，**不从磁盘读** ✅ | Task 5 要删的是「顺手落盘」那一下，不是传输机制 |
| F5-2 | 落盘点不止一处：计划只列了 `snapshot_runtime_storage_state` 的 `persist` 分支，**但顺序路径 `executor_v2.py:1343`（登录后 `_save_session_async`）仍会写会话文件** | **Task 5 单独做完，验收口径「`data/sessions/` 不再产生新文件」不成立** —— 顺序路径的写入要一起处理（可归 Task 5 或 Task 7，**但 Task 10 验收前必须归零**） |
| F5-3 | 🔴 **`session_manager.load_session` 读操作会回写文件**（`session_manager.py:555-560` 刷新 `last_used_at` 后 `_write_json_atomic`） | 「不落盘」若只改写路径不改这里，**读路径仍产生磁盘写** → 验收口径同样不成立 |
| F5-4 | `snapshot_runtime_storage_state` 返回 `None` 时（`:856-863` 异常），`opts["storage_state"] = None` → `new_context(storage_state=None)` → 扇出 context **完全无登录态且不报错** → 采集在登录页跑完 | 删落盘后更隐蔽（没有会话文件作为「失败留痕」）→ **必须显式失败**，不能静默用 None |

- [ ] **Step 1: 改写测试**

`test_collection_executor_session_alignment.py:1026` 附近断言快照落盘的用例 → 改为断言**不落盘**（`data/sessions` 下不产生新文件）。

同时补一条用例钉死 F5-4：快照为 `None` 时**必须显式失败**（抛错或任务失败），不能带着 `storage_state=None` 继续扇出。

- [ ] **Step 2: 实现**

`runtime_session.py` 的 `snapshot_runtime_storage_state`：删除 `persist` 参数与 `if persist and session_owner_id:` 分支（含 TikTok 的 `seller_local_storage` 落盘前置检查一并删除 —— 不落盘就不需要这个检查）。函数只返回内存快照。

`executor_v2.py:5948-5954` 改为 `persist=False` → 直接去掉 `persist` 实参。

删除 `persist_runtime_session_state`（`:958-964`）。

- [ ] **Step 3: 顺带处理顺序路径落盘（F5-2）与读时回写（F5-3）**

`executor_v2.py:1343` 的登录后落盘 + `session_manager.py:555-560` 的读时回写，一并改为不写盘。

> 若决定把这部分留给 Task 7，**必须在 Task 7 的验收口径里明确写出**，不要让 Task 5 的提交留下「已不落盘」的误导。

- [ ] **Step 4: 跑测试并提交**

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
- Modify: `modules/utils/pwcli_native.py:899-935`（`command_state_save`）、`:325-348`（`save_default_storage_state_from_context`）、`:970`（usage 文本）、`:1005-1006`（`main` 分支）
- Modify: `scripts/pwcli_helpers.ps1:548-571`（交互式巡店循环里的 3 处 Save 调用）
- Modify: `scripts/verify_pwcli_helpers.ps1:10-12`（校验 3 个 Save 函数存在）
- Modify: `scripts/generate_pwcli_account_commands.py:137/145/153`（生成的文档含 Save 命令）
- Modify: `scripts/pwcli_account_inventory.py:26/32/38`（`PLATFORM_HELPERS` 的 `"save"` 键）
- Test: `backend/tests/test_pwcli_inspection_panel_reporting.py`、`tests/test_pwcli_inspection_panel.py`、`backend/tests/test_pwcli_helpers_session_targeting.py`、`tests/test_pwcli_daily_inspection_helpers.py`、`backend/tests/test_pwcli_native_session_alignment.py`

### Task 6 只读盘点结论（实施前必读）

| # | 事实 | 影响 |
|---|---|---|
| F6-1 | 巡店面板**已经**用 profile 启动浏览器（`pwcli_native.command_open:719` → `resolve_default_profile_dir` → `launch_browser:609` `user_data_dir`），且 profile 路径规则（`session_manager_safe_token`）与采集的 `SessionManager.get_persistent_profile_path` **完全一致** ✅ | 验收口径「巡店与采集共用同一 profile」成立，Task 6 只需去掉会话文件读写 |
| F6-2 | `save_default_storage_state_from_context` 有 **9 个调用点**：`pwcli_native.py:661`(open)、`:772`(close)、`:803`(reload)、`:825`(snapshot)、`:844`(click)、`:859`(fill)、`:873`(press)、`:892`(screenshot)、`:914`+`:932`(state-save) | 把 `state_mode == "session_manager"` 分支改成「不写」即可**一次性全灭** |
| F6-3 | 面板 `POST /api/accounts/open` → `run_action("open")` → `build_pwcli_action_command` → `Open-Pwcli{Platform}` → `pwcli --session <name> open <url> --headed --account-id <id>` | 「打开巡店」链路完整，Task 6 主要删「保存」侧 |
| F6-4 | 🔴 **`command_close` 强杀浏览器**：`pwcli_native.py:778` → `:456-457` `taskkill /F /T` | Chromium 不刷盘 → **profile 没记住登录态** → R3/R7 达不到验收。**Task 6 必须同时改为优雅关闭** |
| F6-5 | 🔴 **巡店完全不注入代理**：`pwcli_native.py` 全文无 `proxy`；`launch_browser:617-628` 的 Chromium 命令行无 `--proxy-server=` | 人工登录走本机直连 IP、采集走账号代理 → **违反 P2「登录与使用同 IP」**，平台 cookie-IP 绑定会失效。**Task 6 必须补代理** |
| F6-6 | `pwcli_helpers.ps1:548-571` 的交互式巡店循环里 `Read-Host "Press Enter to save..."` → 调 3 个 Save 函数 | 删 Save 函数后 CLI 巡店流程直接断，**必须同步改写** |
| F6-7 | `pwcli_native.py:348` 的 `raw_json` 分支仍会写 `output/playwright/state/<platform>.json`（**非账号级**，仅在无 `--account-id` 时） | 与 `data/sessions` 无关，**可以保留**（人工导出会话能力） |
| F6-8 | `pwcli_native.py:436-439` 的 `save_session(session, metadata)` 写的是 `output/playwright/sessions/<token>/session.json`（pid/port 元数据） | **不是登录态**，不能随「删 save_session」一起删 |

- [ ] **Step 1: 改写测试**

面板测试中「save」动作的用例改为断言：`/api/accounts/save` **返回 404**（端点已删除），前端 HTML **不含**「保存会话」按钮。

`backend/tests/test_pwcli_helpers_session_targeting.py` 里 `_save_helper_block()` 按字符串 `"function Save-PwcliPlatformState"` 切块、且断言 `pwcli_helpers.ps1` 里**恰好 3 处** `Save-Pwcli*State -AccountId $account.account_id` 调用 —— 删函数后这些断言必失败，**整个文件的 save 相关用例要删/改写**（不是只改一处）。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 删面板端点**

`scripts/pwcli_inspection_panel.py`：删除 `SAVE_HELPERS` 字典、`/api/accounts/save` 路由、`run_action` 里的 `"saving"`/`"saved"` 分支（保留 `open` / `skip`）。

- [ ] **Step 4: 删前端按钮**

`scripts/pwcli_inspection_panel_static/index.html`：删除 `:290` 的 `<button class="save danger">保存会话</button>` 与 `:299` 的监听绑定；更新 `:200` 与 `:223` 的说明文案（改为「打开账号浏览器后人工登录，登录态由浏览器 profile 自动保存」）。

- [ ] **Step 5: 删 PowerShell 保存函数**

`scripts/pwcli_helpers.ps1`：删除 `Save-PwcliPlatformState`（`:249-304`）与 `Save-PwcliMiaoshouState` / `Save-PwcliShopeeState` / `Save-PwcliTiktokState`（`:363`、`:368`、`:373`）；**同步改写 `:548-571` 的交互式巡店循环**（F6-6）。

- [ ] **Step 6: 删 pwcli_native 的 state-save**

`modules/utils/pwcli_native.py`：删除 `command_state_save`、删 `main()` 里的 `state-save` 分支与 `:970` 的 usage 文本；`save_default_storage_state_from_context` 中 `state_mode == "session_manager"` 分支改为**不写会话文件**（profile 自己会存）。**保留** `raw_json` 分支（F6-7）与 `save_session` 元数据分支（F6-8）。

- [ ] **Step 6.5: `command_close` 改优雅关闭（F6-4）**

`pwcli_native.py:778` 的 `kill_process(pid)` 改为「先 CDP `Browser.close()` / 等进程自然退出，超时再强杀」，保证 Chromium 刷盘 → profile 记住登录态。

- [ ] **Step 6.6: 巡店注入账号代理（F6-5）**

`pwcli_native.launch_browser` 的 Chromium 启动参数加 `--proxy-server=<账号代理>`，凭据用 CDP `Fetch.continueWithAuth`。代理来源与采集一致（`extra_config["proxy"]`）。

> 若判定代理注入改动过大，可**拆到 Task 6.1** 单独交付，但**必须在 Task 10 验收前完成** —— 否则 P2 未满足。

- [ ] **Step 7: 跑测试并提交**

```powershell
git add scripts/pwcli_inspection_panel.py scripts/pwcli_inspection_panel_static/index.html scripts/pwcli_helpers.ps1 modules/utils/pwcli_native.py scripts/verify_pwcli_helpers.ps1 scripts/generate_pwcli_account_commands.py scripts/pwcli_account_inventory.py backend/tests/test_pwcli_inspection_panel_reporting.py tests/test_pwcli_inspection_panel.py backend/tests/test_pwcli_helpers_session_targeting.py tests/test_pwcli_daily_inspection_helpers.py backend/tests/test_pwcli_native_session_alignment.py
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
| `persistent_browser_manager.py:350` `save_context_state` | 改为只关闭 profile context，不写文件。**注意有 14 个调用方**：`app.py:776/960/2051/2321/2369`、`handlers.py:521/603/1398/1429`、`login_orchestrator.py:198`、`enhanced_recording_wizard.py:124`、`close_context:384` |
| `pwcli_native.py:340` 人工保存 | Task 6 已删（9 个调用点一次性清） |
| `miaoshou_smart_login.py:505` | 删除写回（Chromium 自己存）。**该路径事实上是死代码**（`miaoshou_smart_login.py:562` 的模块级 `_login()` 无调用方） |
| 🔴 `session_manager.py:560` **读时回写 `last_used_at`** | 删除（`load_session` 读操作不该改磁盘） |
| 🔴 `executor_v2.py:1343` **顺序路径登录后落盘** | 删除（Task 5 已处理或在此归零） |

### Task 7 只读盘点结论（实施前必读）

| # | 事实 | 影响 |
|---|---|---|
| F7-1 | 🔴 **`persistent_browser_manager.py:196` 的 `_alt` 旁路 profile**：主 profile 被锁时**静默改用** `profiles/<platform>/<account>_alt`（磁盘上已存在 `虾皮巴西东朗照明主体_alt`） | 登录态被**分散到第二个目录** → 违反 R1 单一载体；且 R6 的跨进程锁只锁 `<account>`、没锁 `<account>_alt` → **必须一并处理**（要么删旁路、要么锁两个 key） |
| F7-2 | 🔴 **`SessionManager.__init__` 无条件 `mkdir` `data/sessions` 与 `data/session_profiles`**（`session_manager.py:169-179`） | 即使不写文件，目录也永远存在 → **验收口径「`data/sessions/` 目录可整体删除」不成立** → 收窄 `__init__` 时必须去掉这个 mkdir |
| F7-3 | 🔴 **`modules/apps/collection_center/app.py:2259-2263` `_check_session_health`** 硬编码 `Path("data/sessions") / session_key`，目录非空即判 "healthy" | 废弃后失效 → **改为查 `profiles/<platform>/<account>`** |
| F7-4 | **3 套目录命名规则并存**（实测对照）：规则 A `safe_session_account_dirname`（会话目录，**保留空格**，`shopee KR` → `data/sessions/shopee/shopee KR/`）vs 规则 B `get_persistent_profile_path`（profile 目录，**剔空格**，`shopee KR` → `profiles/shopee/shopeeKR/`）vs 规则 C `pwcli_account_inventory.work_tag`（浏览器会话名，非存储路径） | 同一账号在两套规则下指向**两个不同目录** —— 这正是 R1 要消除的分裂。Task 7 删规则 A 后，统一到规则 B |
| F7-5 | 规则 B 另有**两处重复实现**：`pwcli_native.py:143-146` `session_manager_safe_token`、`scripts/pwcli_workflow.py:48-54` `_session_manager_safe_token` | 与 `session_manager.get_persistent_profile_path` 规则相同但是三份代码 → Task 7 收窄时应统一到一处 |
| F7-6 | `modules/collectors/base/base_collector.py:424-443` 与 `modules/collectors/shopee_collector.py:312-347` 各有**独立会话机制**（`temp/sessions/**`，24h 有效期） | **不在本次废除范围**，但容易被误判为「会话文件」→ 明确写进注释/文档，避免后续误删 |
| F7-7 | `modules/services/shopee_exporter.py:194` 的 `from_persistent_session` 当前 `'cookies' in session_data` **恒假** → 永远走 `cls()`（无 cookie）→ **这个功能今天已经是坏的** | 唯一调用方 `app.py:438`（CLI 交互 `export_product_performance_weekly`）→ 删除前需确认该 CLI 是否还重要 |
| F7-8 | `data/sessions/` 现有 **19 个文件、约 1.47 MB**，时间跨度 2025-08-18 → 2026-11-02；其中 5 个是「别名孤儿」（`account-1`/`account-2`/`test_account_001`/`妙手erp`/`miaoshou_erp`）；3 个平台命名空间（`miaoshou_erp` / `妙手erp` / `miaoshou`）与采集用的 `shopee`/`tiktok`/`miaoshou` **不统一** | **不要在代码里自动删**。清理策略：整体备份 → `data/sessions.bak-<日期>`（`data/` 已 gitignore）→ 观察 1~2 周 → 删除；`shopee KR`（事故现场证据）与 `tiktok/Tiktok 1店`（497 KB，含 IndexedDB 级 localStorage）建议单独留档 |

- [ ] **Step 1: 写失败测试**

`backend/tests/test_session_storage_roots.py` 改写：断言 `SessionManager` **不再暴露** `save_session` / `load_session` / `get_session_path` / `restore_session` / `cleanup_expired_sessions`，且 `get_persistent_profile_path` 仍可用。

补一条断言：`SessionManager` 初始化后**不会创建** `data/sessions` 目录（F7-2）。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 收窄 `SessionManager`**

保留：`__init__`（**仅 `persistent_profiles_path`，去掉 `data/sessions` 的 mkdir**）、`get_persistent_profile_path`、新 `get_profile_path`（legacy `data/session_profiles`，`miaoshou_smart_login.py:134` 仍在用）。

删除：`save_session` / `load_session` / `restore_session` / `get_session_path` / `get_session_metadata` / `get_session_info` / `list_sessions` / `cleanup_expired_sessions` / `delete_session` / `is_session_valid` / `describe_storage_targets` / `session_quality_score` / `session_meets_quality_gate` / `_merge_tiktok_storage_state` / `_session_freshness_timestamp` / `_write_json_atomic`（若无其他用户）/ `safe_session_account_dirname`（改由 `get_persistent_profile_path` 统一）。

保留 `modules/utils/sessions/__init__.py` 的导出，但去掉 `SessionManager` 之外的失效符号。

- [ ] **Step 3.5: 处理 `_alt` 旁路 profile（F7-1）**

`persistent_browser_manager.py:196` 的 `_alt` fallback 要么删除、要么把 `<account>_alt` 也纳入跨进程锁的 key。**与 Task 3 协调一致**（Task 3 的锁 key 需要覆盖两种目录名）。

- [ ] **Step 4: 清理调用点**

按上表逐条改。`shopee_workflow_manager.py:424` 的 `restore_session` 调用改为「用 `SessionManager().get_persistent_profile_path(...)` + profile context」。

`modules/services/shopee_exporter.py:194` 的 `from_persistent_session` —— 它当前 `'cookies' in session_data` 判断恒假，改造时按 profile 语义重写或直接废弃该函数（先查调用方再定，见 F7-7）。

`app.py:2259-2263` 的 `_check_session_health` 改为查 profile 目录（F7-3）。

- [ ] **Step 5: 清理遗留物收集与告警**

`legacy_shop_artifact_cleanup.py:47` 移除 `data/sessions` 候选；`backend/main.py:289-309` 与 `run.py:360-363` 的告警文案改为「检测到店铺级 profile 遗留」。

- [ ] **Step 6: 遗留数据的清理策略（F7-8）**

**代码不自动删**。产出操作说明：备份目录名、保留哪些、观察期多长，由运维执行。

- [ ] **Step 7: 跑测试**

```powershell
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_legacy_shop_session_cleanup.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_persistent_browser_manager_session_metadata.py -v
```

> 旧语义测试（人工保护 / 质量分回退 / 30 天门禁）随 `test_session_manager_protection.py` 一并删除；其余文件里断言旧 metadata 的用例按新语义改写。

- [ ] **Step 8: 提交**

```powershell
git rm backend/tests/test_session_manager_protection.py
git add modules/utils/sessions/session_manager.py modules/utils/sessions/__init__.py modules/apps/collection_center/executor_v2.py modules/apps/collection_center/runtime_session.py modules/utils/persistent_browser_manager.py modules/collectors/miaoshou_smart_login.py modules/collectors/shopee_workflow_manager.py modules/services/shopee_exporter.py modules/utils/sessions/legacy_shop_artifact_cleanup.py modules/apps/collection_center/app.py backend/main.py run.py backend/tests/test_session_storage_roots.py backend/tests/test_legacy_shop_session_cleanup.py
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

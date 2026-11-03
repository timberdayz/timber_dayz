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

## 0.1 实施进展（2026-11-03）

| Task | 状态 | 提交 / 结论 |
|---|---|---|
| Task 0 worktree + 基线 | ✅ | 10 文件 99 passed 基线 |
| Task 1 账号代理配置透出 | ✅ 双评审通过 | `9796a390` + `0b5c1864`；`account_proxy_config.py` 分支覆盖 100% |
| Task 2 打通代理链路 | ✅ 三轮评审通过 | `2b4a3b39` / `366cc4f9` / `76c821e3`；全量失败集合 NEW=0 |
| Task 3 跨进程账号锁 | ✅ 实现 + 规格评审 Compliant + 收口 | `b88fa447` + `39578201`（合并于 `ad3e42a4`）；覆盖率 100%；规格评审 2 项 Important 已修 |
| Task 4.5 有头回退走 profile | ✅ | `8d51df14`；9 个新用例；两种顺序 NEW=0 / FIXED=0 |
| Task 4.5 代码质量评审 | ✅ 修复完成 | 评审 VERDICT: NEEDS_FIX（F1🔴 + F2~F6🟠 + F8~F13🟡）→ 修复 `8bd831f4`；F1 重开页面未 prime 已用「两种情况都成立」的导航修法钉住；F4 compose 补 `extra_hosts: host-gateway`；锁模块覆盖率仍 100% |
| Task 4 补地基 | ✅ | `035523b7`；11 个新用例（TDD 证明 8 个在旧码上红）；`backend/tests` 两种顺序 NEW=0 / FIXED=0 |
| Task 6.0 清理遗留老程序 | ✅ | `6e63f501`；删 `app.py`(5170 行) + `handlers.py`(2524 行) + 2 个测试；路由表 740 条不变；NEW=0 / FIXED=0 |
| Task 6.5 录制子进程对齐 profile | ✅ | `b9fdcb62`；profile 身份改主账号 ID + 接入跨进程锁 + 删 14 处硬编码调试写入；NEW=0 / FIXED=0 |
| Task 4.2 顺序路径收敛 | ⏳ 进行中 | 分支 `feature/session-profile-only-t42` |
| Task 5 / 6 / 7 | ⏳ 进行中 | Task 5 分支 `...-t5`、Task 6 分支 `...-t6`；Task 7 已完成二次只读盘点，见各自章节的修订表 |
| Task 8 / 9 / 10 | ⏳ | Task 10 **必须在合并回 main 之后**跑（profile 根是仓库根相对，worktree 的 `profiles/` 是空的） |

**四路分支已合并进 `feature/session-profile-only`**（`0b615706`，**零冲突**）：`035523b7`(Task 4) + `60ed2be2`(_fix345) + `69155c16`(Task 6.0) + `0b615706`(Task 6.5)。合并后冒烟：关键 8 个测试文件 **180 passed**；三个守卫脚本 exit 0；`docker compose -f docker-compose.collection.yml config -q` exit 0。

**已知的仓库既有失败基线**：`backend/tests` 全量 **143 failed / 3986 passed / 22 errors**。判据是**失败集合逐条 diff**（`--junitxml`），**不是计数**。

**跑测试的两个环境坑**（实测，务必带上）：
1. 必须设 `$env:PYTHONUTF8='1'`（或 `PYTHONIOENCODING=utf-8`），否则 pytest capture 把 GBK 控制台字节按 UTF-8 解码 → setup 阶段 **5011 个假 error**。
2. 顺序敏感用例（`test_account_proxy_config.py` 与 `test_collection_executor_session_alignment.py` 谁先跑会影响结果）→ 验收必须**两个顺序都跑**；换序要用 `-p reorder_collection_tests` 自定义插件，**不能用重复路径参数**（pytest 会把目录整体跳过，只收 119 个用例）。

**未验证/待外部确认**：
- **E2**：生产实际生效的 compose 组合与 Redis 认证形态。已把代码侧的兜底做掉（`REDIS_PASSWORD` 注入 + 显式 `ACCOUNT_SESSION_LOCK_BACKEND`），但**生产用哪套 compose 仍需运维确认**。
- **E1**：生产 Redis 的 `maxmemory-policy`（本机 `noeviction`，锁 key 不会被淘汰）。
- **真实代理凭据**：本机 19 个 enabled shop_account 的 `extra_config->'proxy'` **全为 NULL** → 本轮用本地假代理跑通链路，真实出口 IP 待凭据到位后补。

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
Task 4.5（有头验证码回退走 profile）  ← 计划外新增，阻塞级
   │                                    必须先于 Task 4：Task 4 删掉多余 browser 后
   │                                    有头回退失去 browser.new_context 的依赖
   ▼
Task 4（补地基：异常路径不泄漏 + 模式解析统一）
   │                                    只修洞，不改行为语义；必须先于 4.2
   ▼
Task 4.2（收敛：顺序路径恒走 profile）
   │
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

> **顺序修订（2026-11-03，Task 4/4.5 只读盘点后）**：原顺序为「Task 4 → Task 4.5」，
> **已倒置为「Task 4.5 → Task 4」**。原因：Task 4 Step 6（profile 模式不再多开 Chromium）
> 会把 `browser_instance` 置为 `None`，而 `_run_headful_login_fallback` 依赖
> `browser.new_context()` 兜底（`executor_v2.py:3112`）—— Step 6 先落地会导致
> 有头人工验证码回退**静默失效**（`login_success=False` → 采集在登录页跑完）。
> Task 4.5 改写回退路径后，Step 6 才安全。

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
| E2 | 生产实际生效的 compose 组合与 Redis 认证形态 | `docker-compose.collection.yml:112` 只有 `REDIS_URL: redis://${REDIS_HOST}:${REDIS_PORT}/0` —— **无密码、无内建 redis 服务**，与其他 compose 的 `${REDIS_PASSWORD}` 拼装不一致。若生产用那套栈，新锁会因认证失败**永远拿不到锁** → 全部采集被 fail-closed 拒绝 | ⚠️ **仍待运维确认**，但**代码侧已加兜底**（见 Task 3 收口 B：`REDIS_URL` 无密码且 `REDIS_PASSWORD` 存在时自动注入）。代码侧必须让「认证失败」与「锁冲突」报出**不同**错误（前者是「锁服务不可用」，后者是「该主账号正被其他任务占用」） |

### Task 3 收口项（2026-11-03 规格评审 VERDICT: PARTIAL 后追加）

规格评审结论：**L1~L9 / F1~F3 / 锁边界 / `_alt` 旁路 / 既有测试改写 全部 ✅ Compliant，全量失败集合逐条 diff 零新增**，但有 2 项 Important 必须修。下表是收口清单。

| # | 级别 | 问题 | 位置 | 修法 |
|---|---|---|---|---|
| A | **Important** | **Redis 连接失败后永不重试** —— `_redis_client_resolved = True` 在连接**之前**置位，失败后单例被永久污染（`_redis_client_singleton` 恒为 `None`）→ 一次瞬时抖动让该 gunicorn worker **此后所有采集被永久拒绝**（生产 fail-closed），Redis 恢复也没用，只能重启进程 | `main_account_session_lock.py:353-396` | 成功后才置 `resolved`；失败分支 `aclose()` 已建 client；加失败冷却窗（避免每次取锁白等 5s 超时）；日志给可执行运维提示；补「第二次会重试」回归测试 |
| B | **Important**（新发现） | **`REDIS_URL` 无密码但环境变量有 `REDIS_PASSWORD` → 认证必然失败** —— 全仓没有任何地方把 `REDIS_PASSWORD` 注入 URL（`backend/utils/redis_client.py` 也没有） | `main_account_session_lock.py` `get_shared_redis_client()` | URL 不含 userinfo 且 `REDIS_PASSWORD` 非空时注入密码；URL 已含密码则原样用；注入后日志必须脱敏 |
| C | **Important** | **采集栈静默降级为进程内锁** —— `account_session_lock_environment()` 读 `ENVIRONMENT`（默认 development），而 `docker-compose.collection.yml` 的 `collection` 服务**既没设 `ENVIRONMENT` 也没设 `REDIS_URL`** → `auto` 走非生产分支 → 跨进程保护形同虚设 | `docker-compose.collection.yml` + `docker-compose.prod.yml` | `collection` 服务补 `REDIS_URL` / `REDIS_PASSWORD` / `ACCOUNT_SESSION_LOCK_BACKEND=redis`；prod 两服务显式设 `ACCOUNT_SESSION_LOCK_BACKEND=redis`；**代码侧降级日志提到 `error` 级**并写明「跨进程保护已失效」。**不要**改 `ENVIRONMENT`（那个 compose 也用于开发） |
| D | **P0**（新发现） | **持久 profile 目录在生产/采集容器里没有挂载持久化** —— profile 根是 `REPO_ROOT/profiles`（容器内 `/app/profiles`）；`docker-compose.yml:111`、`docker-compose.dev.yml:60`、`docker-compose.collection-cloud-sync.yml:61` **都挂了** `./profiles:/app/profiles`，但 **`docker-compose.prod.yml` 与 `docker-compose.collection.yml` 没挂** → 容器一重建，**所有账号的 Chromium 登录态全部丢失** → 每次都要重新人工登录 + 过验证码 → **整个「profile 唯一载体」架构在生产上失效** | `docker-compose.prod.yml`（`backend_api_service` volumes）、`docker-compose.collection.yml`（`collection` volumes） | 两个文件各加一行 `- ./profiles:/app/profiles` + 一行中文注释 |
| E | Minor | 等待者 Hash 的 TTL 与锁 TTL 相同（300s）→ 等待超 300s 后 `waiter_count` 归零，L7 退化 | `main_account_session_lock.py:241-250` | 每次 `add_waiter` 刷新 TTL，或把 Hash TTL 设为锁 TTL 的数倍 |
| F | Minor | `LocalSessionLockBackend._scope` 用 `id(loop)` 做 key —— Python 的 `id()` 在对象回收后**会被复用**，两个不同 loop 可能拿到同一个 id → 误判为同一把锁 | `main_account_session_lock.py:271-278` | 改用不会复用的标识（loop 上挂 uuid4 / 自增序号） |

> **A 与 D 是阻塞级**：A 让一次 Redis 抖动变成永久采集停摆；D 让整个架构在生产上失效。**两者都必须在 Task 4 之前修完。**

### 评审另记的 Minor（登记到后续 Task，本轮不修）

| # | 问题 | 归属 |
|---|---|---|
| M1 | `_open_runtime_bundle` 成功后、进入 `try` 之前抛错 → profile context 泄漏（`except BaseException` 已释放锁） | **Task 4 Step 8.1**（= F4-8） |
| M2 | `_requires_profile_session_lock` 与 `_open_runtime_bundle` 之间的 TOCTOU | Task 4 恒 `persistent_profile` 后自动消失 |
| M3 | TTL=300 未严格 > 验证码等待上限 300s（意图已由续期满足） | 文档说明即可 |
| M4 | **不取账号锁的 profile 打开路径**：`modules/apps/collection_center/app.py`（巡店 `:657/845/1032/1184`）、`handlers.py:498/580/1392/1423`、`backend/domains/collection/routers/component_recorder.py:553-634`（录制**子进程**，`use_persistent_context=True`）都直接开 profile，**不经过账号锁** → 采集持锁期间巡店/录制仍可打开同一 profile 目录 → **R6 的系统级覆盖尚未闭合** | **Task 6**（巡店必须纳入同一把账号锁） |

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

> **实施拆分（2026-11-03 追加）**：原 Task 4 一次要改 8 处、牵涉 12 个测试文件，单个子代理容易被打断（Task 4.5 已经中途中断过一次）。
> 拆成 **Task 4（补地基）** 与 **Task 4.2（做收敛）** 两段，各自独立实现 + 独立评审：
>
> | 段 | 内容 | 性质 | 依赖 |
> |---|---|---|---|
> | **Task 4** | ① `_cleanup_browser_runtime` 提到覆盖两段 try 的最外层 finally（F4-8/M1）② 模式解析上提（F4-9）③ `_requires_profile_session_lock` 跟随统一后的模式（不再依赖 `_manual_storage_state_exists`） | **只补洞，不改行为语义** —— 修的是「异常路径泄漏 profile context」与「模式判定脱节」 | 无（Task 4.5 之后即可） |
> | **Task 4.2** | ④ 删死代码 `_prepare_runtime_page_bundle` ⑤ `choose_runtime_strategy` 正式采集恒 `persistent_profile` ⑥ `_open_runtime_bundle` 只走 profile + 删 5 个函数 ⑦ profile 模式不再多开 Chromium（原 Step 6）⑧ R8 一致性断言 + 测试改写清单 | **行为收敛** —— 把「storage_state 优先」彻底换成「profile 唯一」 | 必须在 Task 4 之后（③ 要先解耦 `_manual_storage_state_exists`，⑥ 才能删它） |
>
> **为什么必须拆**：Task 4 的 ① 是**阻塞级正确性修复**（Task 4.2 落地后每次采集都开 profile，不修就等于每次采集都可能泄漏一个 Chromium 进程 + 泄漏 profile 目录锁 → 下一个任务双开）。它必须**先落地并单独验证**，不能和大改混在一起，否则出问题时分不清是「洞」还是「收敛」引入的。

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py:519-582`（`choose_runtime_strategy`）、`:703-730`（`normalize_persistent_profile_context_options`）
- Modify: `modules/apps/collection_center/executor_v2.py:991-1148`（`_open_runtime_bundle`）、`:468-596`（`_prepare_runtime_page_bundle` 死代码）、`:2152-2349`（第一段 try / 异常路径）、`:939-976`（`_requires_profile_session_lock`）
- Test: `backend/tests/test_collection_session_reuse_contract.py`（改写）、`backend/tests/test_collection_executor_session_alignment.py`、`backend/tests/test_collection_executor_reused_session_scope.py`、`backend/tests/test_collection_runtime_session.py`、`backend/tests/test_component_tester_runtime_config.py`、`backend/tests/test_account_proxy_config.py`、`backend/tests/test_main_account_session_lock.py`

### Task 4 只读盘点结论（实施前必读，行号以真实代码为准）

> ⚠️ **2026-11-03 二次只读盘点修订**：下表 F4-1/F4-3/F4-4/F4-5 的描述已被独立核实推翻，
> 真实结论见下方「二次盘点修订表」。**实施以二次盘点为准。**

| # | 事实 | 影响 |
|---|---|---|
| F4-1 | `choose_runtime_strategy`（`runtime_session.py:519-582`）生产只有 **1 个**调用方（`executor_v2.py:1057`，`execution_kind="formal_collection"`）；第 2 处是工具脚本 `tools/test_component.py:256`（`execution_kind="component_test"`）。`force_persistent_profile` 与 `parallel_mode` 两个分支**在生产中恒为 False**（死分支） | 收敛时可一并删死分支；**不要**误判并行路径不受影响 —— 生产入口 `collection_tasks.py:1744/:1945` 传 `session_runtime_mode="auto"` |
| F4-2 | `executor_v2.py:1099-1124` 的 storage_state 回退段已被 `normalized_mode != "persistent_profile"` 条件保护 ✅ | `normalized_mode` 变成 `persistent_profile` 后该段自动跳过，不会误读会话文件 |
| F4-3 | ⚠️ **原描述有误** —— 见二次盘点 R3 | 步骤必须排在 Task 4.5 之后 |
| F4-4 | ⚠️ **原描述有误** —— 见二次盘点 R4 | 不会 ImportError，但有 1 个测试需改写 |
| F4-5 | **R8 注入点**：真正违规的是 **3 处** —— `executor_v2.py:6201-6219`（并行扇出）、`:3098-3105` 与 `:3162-3166`（有头回退两条）。顺序 profile 路径的注入已被 `normalize_persistent_profile_context_options`（`runtime_session.py:703-730`）全部剥离 ✅ | 并行侧在 Task 5 处理，有头回退侧在 Task 4.5 处理 |
| F4-6 | `_profile_contains_state`（`runtime_session.py:460-464`）只判「目录非空」。**机制更正**：不是「从未登录也返回 True」，而是 `get_persistent_profile_path`（`session_manager.py:216`）`mkdir` 空目录 → 首次为 False；**首次 launch 后 Chromium 写入 `Default/`、`Local State` → 此后永远 True**，即使从未登录 | `reused_session=True` 误报 → Task 8 的 `session_reused` 字段失真。**Task 4 或 Task 8 必须修**（判据应为「profile 内有真实 cookie/登录态」） |
| F4-7 | `_should_skip_post_login_session_persist`（`executor_v2.py:3018-3050`）**只对 `platform=="tiktok" and mode=="persistent_profile"` 返回 True** | Task 4 后顺序路径恒为 profile → TikTok 自动落盘被跳过，但 **shopee/miaoshou 登录后仍写会话文件**（`:1428-1464`）→ **Task 7 前必须统一** |
| F4-8 | 🔴 **新增**：`execute()` 是**两段 try**。第一段 `try`（`:2152`）的 `except TaskCancelledError`（`:2330`）/ `except BaseException`（`:2345`）**只释放锁、直接 return/raise** → 第二段的 `finally`（`:2801`）永不执行 → **`_cleanup_browser_runtime` 被跳过 → profile context 泄漏**（Chromium 残留 + profile 目录锁不释放 + 账号锁已释放 → 下一个任务可双开同一 profile） | Task 4 前必须先把 `_cleanup_browser_runtime` 提到**覆盖两段 try 的最外层 finally**。Task 4 后每次采集都开 profile → 泄漏面从「部分账号」变「全部账号」 |
| F4-9 | 🟠 **新增**：`execute()` 的模式前置校验（`:2093-2117`）只看**原始** `session_runtime_mode`，与 `_open_runtime_bundle` 内部（`:1013-1073`）的模式解析**脱节** | Task 4 后 `_open_runtime_bundle` 恒 profile，但 `browser_type=None` 时会在 `:1084` 抛 AttributeError 而非清晰 ValueError |
| F4-10 | 🟠 **新增**：`_resolve_session_metadata`（`:1189-1215`）在 profile bundle 的 `session_metadata` 恒空（`RuntimeContextBundle` 构造器默认值，profile 分支从不填）时**回退去读 `SessionManager().get_session_metadata()`** → `load_session` 会**回写 `last_used_at`**（`session_manager.py:557-560`）→ profile 路径上仍产生**磁盘写** | Task 5/7 必须一并归零；Task 8 也要连带删 `_resolve_session_metadata` |

### 二次盘点修订表（2026-11-03，推翻原 F4-1/F4-3/F4-4）

| # | 原计划说法 | 独立核实结论 | 处置 |
|---|---|---|---|
| R3 | 「profile 模式下 `browser_type.launch()` 起的 browser 完全不用，只是浪费」 | **错 —— 这个 browser 有用**：`_open_runtime_bundle` 的 profile 分支只吃 `browser_type`，但 `browser_instance` 被继续传给 `_execute_shared_login_phase(browser=...)`（`:2219`）与 `_execute_with_python_components(browser=...)`（`:2359`），最终是 `_run_headful_login_fallback` → `_recreate_runtime_page_with_saved_session` 里 `browser.new_context()`（`:3112`）的**唯一依赖** | Task 4 Step 6 **必须排在 Task 4.5 之后**；Task 4.5 改写回退后 browser 参数废弃，Step 6 才可安全执行 |
| R4 | 「`_prepare_runtime_page_bundle` 模块级 import 了 `_load_or_bootstrap_session_async` → 顺序反了会 ImportError，所有采集全挂」 | **错 —— 不会有 ImportError**：`_load_or_bootstrap_session_async` 是同模块函数（`:285`），不是 import；函数内的 `get_browser_context_args` 是**函数内 import**（`:538-540`/`:549-551`）。真实影响 = **1 个测试**（`backend/tests/test_account_proxy_config.py:1077`）直接调用该函数，需随删除改写 | 仍先删死代码（减少会话文件耦合面），但**不再有 ImportError 风险** |
| R5 | 「`choose_runtime_strategy` 两处调用都传 `formal_collection`」 | **错** —— 生产 1 处 `formal_collection`，工具脚本 1 处 `component_test` | 收敛时保留 `execution_kind` 参数语义，工具脚本行为不变 |
| R6 | 「profile 模式下多开的 Chromium 进程 IP 出口多一个」 | 不准确 —— 该 browser 走同一 `proxy` 参数，不会多出出口 IP；但确实多占一个进程 | 同 R3 |

### Task 4（第一段：补地基）—— 只修洞，不改行为语义

> 这一段**不改**「storage_state 优先 / profile 兜底」的行为，只把三个「洞」补上。
> 它**必须先于 Task 4.2 落地**：Task 4.2 之后每次采集都会开 profile 目录，
> 不先修就等于**每次采集都可能泄漏一个 Chromium 进程 + 泄漏 profile 目录独占锁** →
> 下一个任务双开同一 profile → 登录态互相覆盖。

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:2152-2349`（第一段 try / 异常路径）、`:939-976`（`_requires_profile_session_lock`）、`:2093-2117`（模式前置校验）
- Test: `backend/tests/test_collection_executor_reused_session_scope.py`、`backend/tests/test_main_account_session_lock.py`、`backend/tests/test_collection_executor_session_alignment.py`

- [ ] **Step 4.0.1: `_cleanup_browser_runtime` 提到覆盖两段 try 的最外层 finally（F4-8 / M1）**

`execute()` 现在是**两段 try**：第一段 `try`（`:2152`）的 `except TaskCancelledError`（`:2330`）/ `except BaseException`（`:2345`）**只释放锁、直接 return/raise**，第二段的 `finally`（`:2801`）永不执行 → `_cleanup_browser_runtime` 被跳过 → **profile context 泄漏**（Chromium 进程残留 + profile 目录锁不释放 + 账号锁已释放 → 下一个任务可双开同一 profile）。

改法：把 `_cleanup_browser_runtime(...)` 提到**同时覆盖两段 try 的最外层 finally**，或在第一段的两个 except 分支里也调用它（必须**幂等** —— 第二段的 finally 也会调一次）。
**注意**：`_cleanup_browser_runtime` 依赖 `page` / `play_context` / `created_browser_instance` / `diagnostics_session` 等变量，其中一部分在第一段 try **内部**才赋值 → 提到外层时要处理「变量尚未绑定」的情况（用 `None` 初始化或先声明）。
**验收**：断言「第一段 try 抛异常时，profile context 仍被 close」；断言「正常路径不会 close 两次」。

- [ ] **Step 4.0.2: 模式解析上提（F4-9）**

把 `execute()` 的模式判定（`:2093-2117`）与 `_open_runtime_bundle` 的内部解析（`:1013-1073`）统一，避免 `browser_type=None` 时抛 AttributeError 而非清晰 ValueError。

- [ ] **Step 4.0.3: `_requires_profile_session_lock` 不再依赖 `_manual_storage_state_exists`**

`:939-976` 当前在 `auto` 模式下靠「profile 目录存在」+「没有人工会话」决定加不加锁。Task 4.2 之后顺序路径恒开 profile → **「新账号首次采集」也必须加锁**，否则两个任务可同时首开同一 profile 目录（违反 R6）。

**要求**：这一段把该判定**改成跟随 Step 4.0.2 上提后的统一模式判定**（`auto` → 本次会打开 profile → True），
但**不要**在这里删 `_manual_storage_state_exists`（Task 4.2 才删）。
**验收**：断言「`auto` 模式下即使 profile 目录还不存在，也加锁」。

- [ ] **Step 4.0.4: 跑测试并提交**

```powershell
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_main_account_session_lock.py backend/tests/test_collection_executor_session_alignment.py
git commit -m "fix(collection): 采集异常路径不再泄漏 profile context，账号锁判定与模式解析统一"
```

---

### Task 4.2（第二段：做收敛）—— profile 成为顺序路径唯一载体

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

`executor_v2.py:991-1148` 的「优先人工会话 / 读会话文件 / bootstrap」三段全部删除，统一走：

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

删除清单（真实调用点已独立核实）：

| 待删 | 真实位置 | 连带要改的地方 |
|---|---|---|
| `_manual_storage_state_path` | `:250-266` | 仅被 `_manual_storage_state_exists` 内部调用 |
| `_manual_storage_state_exists` | `:269-282` | `:976`（`_requires_profile_session_lock`）、`:1022`（`_open_runtime_bundle` B 段）、`executor_v2.py:3076` 附近、测试 `test_main_account_session_lock.py:912`、`test_collection_session_reuse_contract.py:84-85/113` |
| `_load_or_bootstrap_session_async` | `:285-308` | `:489`（死代码）、`:1033`（B 段）、`:1104`（E 段）、`:3076`（`_recreate_runtime_page_with_saved_session`，Task 4.5 已改写） |
| `_should_prefer_manual_storage_state` | `:978-989` | `:1024`（B 段）、测试 `test_collection_session_reuse_contract.py:57/61` |
| `_prepare_runtime_page_bundle` | `:468-596` | **1 个测试**：`test_account_proxy_config.py:1077`（验证「指纹失败回退仍带代理」）→ 需改写到新路径 |

> **注意**：删 `_load_or_bootstrap_session_async` 后，`runtime_session.load_runtime_session_candidate`（`:347`）与其内部依赖 `_load_session_async`（`:241`）、`_bootstrap_session_from_profile_sync`（`:258`）**全部变成死链**（唯一其它调用方也是 `_open_runtime_bundle`）。
> `_bootstrap_session_from_profile_sync` 还有一个**真实隐患**：它会用**同一 profile 目录再开一个持久 context**（`:258-286`），若在主 profile context 已开着时调用 → Chromium ProcessSingleton 冲突 → 被 `except Exception`（`:287`）吞掉 → 返回 `None` → **新 context 无登录态且不报错**。Task 4.5 改写 `_recreate_runtime_page_with_saved_session` 时必须一并消除这个调用。

- [ ] **Step 6: profile 模式不再多开 Chromium（F4-3 / R3）** — ⚠️ **必须排在 Task 4.5 之后**

`executor_v2.py:2105-2108` 的 browser 创建条件加上「非 persistent_profile 模式」：

```python
if (
    browser_instance is None
    and normalized_runtime_mode in {"auto", "storage_state_fanout"}
    and browser_type is not None
):
```

→ Task 4 后 `normalized_runtime_mode` 恒为 profile → 不再 launch 多余 browser。

> ⚠️ **前置依赖**：这一步会让 profile 模式下 `browser_instance` 变成 `None`。
> 在 Task 4.5 改写 `_run_headful_login_fallback` **之前**执行，`_run_headful_login_fallback`
> 会在 `:3244-3245` 直接 `return False, old_context, None` → `login_success=False`
> → `_execute_shared_login_phase:1392` 抛 `StepExecutionError("登录组件执行失败")`
> → **有头人工验证码回退彻底不可用**。因此实施顺序必须是 **Task 4.5 → Task 4（含本步）**。

- [ ] **Step 7: R8 指纹一致性**

确认 `normalize_persistent_profile_context_options`（`runtime_session.py:703-730`）在顺序路径生效 —— 顺序路径现在也是 profile 模式，所以自动一致 —— 在测试中断言这一点。

并行扇出的 `domain_context_options`（`executor_v2.py:6201-6219`）若仍注入 UA/locale/timezone，必须在 Task 5 显式断言「顺序与并行一致」，否则 R8 不成立。

- [ ] **Step 9: 跑测试并提交**

```powershell
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_collection_session_reuse_contract.py
git commit -m "refactor(collection): 正式采集统一走持久化 profile"
```

### Task 4 测试改写清单（盘点逐条核实）

**已红（基线就失败，是 Task 4 要重写的对象，不是新增失效）**：
- `test_component_tester_runtime_config.py:66-77` —— 断言 `decision.mode == "storage_state_fanout"`
- `test_component_tester_runtime_config.py:80-96` —— 断言 `decision.mode == "storage_state_fanout"` + `reason == "storage_state_available"`

**必改**：
- `test_collection_session_reuse_contract.py:6-27` / `:30-49` —— 调 `_load_or_bootstrap_session_async`（函数被删）
- `test_collection_session_reuse_contract.py:52-64` —— 调 `_should_prefer_manual_storage_state`（函数被删）
- `test_collection_session_reuse_contract.py:67-85` —— 调 `_manual_storage_state_exists`（函数被删）
- `test_collection_session_reuse_contract.py:88-143` —— **语义反转**（原本断言「人工会话优先」，现在断言「恒走 profile」）
- `test_collection_executor_session_alignment.py:48-78` —— 断言 storage_state 分支被调用
- `test_collection_executor_session_alignment.py:81-129` —— 语义过时，需改名改断言
- `test_collection_executor_session_alignment.py:808-883` —— 断言 `browser_type.launch.assert_awaited_once()`（Step 6 落地后失效）
- `test_collection_executor_reused_session_scope.py:133-195` / `:397-500` —— 用 `FakeBrowser()` 但**不传 `browser_type`** → 恒 profile 后会崩，需补 `browser_type`
- `test_main_account_session_lock.py:881-922` —— monkeypatch `_manual_storage_state_exists`（函数被删）
- `test_account_proxy_config.py:1050-1098` —— 调 `_prepare_runtime_page_bundle`（死代码被删）
- `test_collection_runtime_session.py:517-573` —— 3 个 `choose_runtime_strategy` 用例，`reason` 值变
- `test_collection_task_runtime_metadata.py:56/81` —— 断言 `session_source == "storage_state"` → 恒为 `"persistent_profile"`（随 Task 8 一并改）

**已核实不失效**：
- `test_collection_executor_session_alignment.py` 全文**不依赖**「顺序路径走 storage_state」——它只把 `_runtime_session_mode` 当**入参字符串**传进被测函数
- `test_collection_executor_reused_session_scope.py` 全文**无** `storage_state` / `session_source` 断言（逐条核对过）

---

## Task 4.5: 有头验证码回退走 profile（计划外新增，阻塞级）

> ⚠️ **实施顺序：Task 4.5 必须先于 Task 4**（见上文「顺序修订」与 Task 4 Step 6 的前置依赖说明）。

**为什么必须单独一个 Task**：盘点发现 `_run_headful_login_fallback`（`executor_v2.py:3118-3254`）**完全绕开 profile**：

```
profile 模式下需要人工过验证码时
  → :3141-3147 另起一套 async_playwright()，开一个全新的、非 persistent、注入了完整指纹的 headed 浏览器
  → 人工在这个浏览器里登录
  → :3230       把登录态写进**会话文件**
  → :3076       再从**会话文件**读回来
  → :3112       browser.new_context(storage_state=...) 注入主 context
```

**Task 7 删掉会话文件后，这条路径直接断链** —— 登录成功但主 context 拿不到登录态 → **采集在登录页跑完（静默失败，不报错）**。

**盘点新发现的、比「文件中转」更严重的问题**：

| # | 问题 | 后果 |
|---|---|---|
| H1 | `:3112` 用 `browser.new_context(...)` 建的是**非持久 context** | 回退之后**主 context 被降级成非持久 context** → profile 从此不再是载体 → 后续登录**不会写回 profile** → Task 7 后 profile 永远记不住登录态 |
| H2 | `:3084-3090` 注入**全量指纹**（UA/locale/时区） | 违反 R8（有头路径与顺序路径指纹行为不一致） |
| H3 | `:3076` 调的 `_load_or_bootstrap_session_async` 在拿不到会话文件时走 `_bootstrap_session_from_profile_sync` → **用同一 profile 目录再开一个持久 context** | 主 profile context 正开着 → Chromium ProcessSingleton 冲突 → 被 `except Exception` 吞掉 → 返回 `None` → **新 context 无登录态且不报错** |

**为什么不能「保留主 context，另开第二个 headed persistent context」**：

- 规范 R6 自证：`docs/guides/COLLECTION_SESSION_LIFECYCLE.md:111-113` —— 同一 `main_account_id` 的 profile 目录**不能被两个浏览器进程同时打开**（Chromium 对 user_data_dir 加独占锁）
- 仓库内实证：`modules/utils/persistent_browser_manager.py:188-215` —— 创建持久 context 失败时**重试到旁路目录 `<account>_alt`**，注释明写「避免主 Profile 被系统锁定/损坏」—— 这条重试逻辑本身就证明「重开同一目录」会失败
- Chromium 原始行为：第二次启动报 `Failed to create a ProcessSingleton for your profile directory.`
- Playwright 官方 MCP 源码亦在 `launchPersistentContext` 前做 `isProfileLocked5Times(userDataDir)` 检查

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:3118-3254`（`_run_headful_login_fallback`）、`:3065-3116`（`_recreate_runtime_page_with_saved_session`）、两个调用点 `:1331` 与 `:3323`
- Modify: `modules/apps/collection_center/runtime_session.py:733-812`（`open_persistent_runtime_bundle`，如需 headed 支持）

**目标方案（盘点推荐，已核实可行）**：

| 步 | 动作 | 依据 |
|---|---|---|
| 1 | `await old_context.close()`（关掉主持久 context）→ **释放 ProcessSingleton 锁 + 刷盘** | Playwright `crBrowser.js:467-472`：持久 context 的 `close()` 会连浏览器进程一起关 |
| 2 | `headed_ctx = await browser_type.launch_persistent_context(user_data_dir=profile_path, headless=False, proxy=proxy, ...)` | `browser_type` 生产全程存活（`collection_tasks.py:1694` 的 `async with async_playwright() as p:` 包住整个采集） |
| 3 | 人工登录：复用现有 `runtime_manifests` / adapter 分支（`:3172-3219` 原样搬过来），`VerificationRequiredError` 仍走 `_wait_verification_and_continue` | 现有逻辑可整体复用 |
| 4 | `await headed_ctx.close()` → **profile 刷盘（R7）** | 同上 |
| 5 | `await open_persistent_runtime_bundle(browser_type, ..., launch_kwargs={"headless": True}, proxy=proxy)` → **重开同一 profile** | 直接复用 `runtime_session.open_persistent_runtime_bundle`（`runtime_session.py:733-812`），自动获得 R8 剥离 + proxy 透传 + `reused_session/profile_path` 诊断 |
| 6 | `return True, new_ctx, new_page, "success"` | 调用方契约不变（`:1343-1349` / `:3335-3341` 已是 4 元组） |

**这个方案的额外收益**：主 context 被替换成**新的持久 context**（而不是现在的非持久 context）→ 顺带修掉 H1。

**要求**：

1. 有头登录回退**改为在同一个 profile 目录上开 headed persistent context**，登录态由 Chromium 自己写进 profile。
2. 回退结束后**正常 close**（R7），让 Chromium 刷盘。
3. 不再有任何「写会话文件 → 读会话文件」的中转（同时消除 H3）。
4. `proxy` 必须透传 —— **绝不能从 account 重解析代理**（account 已被 `strip_account_proxy_credentials` 去凭据 → 需认证代理会 407），必须用调用方已解析好的 `proxy` 参数。
5. headed persistent context 也必须走 `normalize_persistent_profile_context_options` → 复用 `open_persistent_runtime_bundle` 天然满足 R8（顺带修掉 H2）。
6. **签名要改**：现在 `_run_headful_login_fallback` 拿不到 `browser_type` 和 profile 路径。必须新增 `browser_type` + `profile_path`（或整个 `runtime_bundle`）参数，并从两个调用点（`:1331`、`:3323`）透传。`browser` 参数在 profile 模式下将不再需要。

**profile 路径来源**：`runtime_session` **没有** `get_persistent_profile_path` 这个函数（只有 `runtime_profile_exists` 与 `open_persistent_runtime_bundle` 内部调用）→ 直接用 `SessionManager().get_persistent_profile_path(platform, session_owner_id)`（`session_manager.py:200-218`），或给 `runtime_session` 加一个薄封装。**推荐**复用 `open_persistent_runtime_bundle(profile_path_override=...)`（`runtime_session.py:741` 已有该参数）。

**验收**：
1. 测试断言「有头回退开的是 `launch_persistent_context(user_data_dir=<profile 目录>, headless=False)`」。
2. 测试断言「有头回退全程不产生 `data/sessions` 写入」。
3. 测试断言「回退返回的新 context 仍是**持久 context**（不是 `browser.new_context`）」—— 修 H1。
4. 测试断言「回退后 profile 目录存在且含 Chromium 写入的登录态痕迹」。

> 这条与 Task 6 的 `command_close` 优雅关闭（F6-4）是同一类问题：**必须正常关闭，profile 才记得住登录态**。

### Task 4.5 实施细节（已逐处核实，勿再自行推断）

**参数穿线链**（当前 `browser_type` 只到 `_open_runtime_bundle`，`profile_path` 根本没往外传）：

```
execute(browser_type=...)                         executor_v2.py:1954
  └─ _open_runtime_bundle(...)                   :2157 / :2274   → runtime_bundle.profile_path
       └─ _execute_shared_login_phase(...)       :2213            ← 此处新增 browser_type / profile_path / launch_kwargs
            └─ _run_headful_login_fallback(...)  :1331            ← 此处新增 browser_type / profile_path / launch_kwargs
       └─ _execute_with_python_components(...)   :2353            ← 此处新增 browser_type / profile_path / launch_kwargs
            └─ _run_headful_login_fallback(...)  :3323            ← 此处新增同上
```

| 参数 | 来源 | 说明 |
|---|---|---|
| `browser_type` | `execute()` 的入参（`:1954`） | 生产入口 `collection_tasks.py:1694` 的 `async with async_playwright() as p:` 把 `p.chromium` 传进来，**全程存活**。Task 3 加的 `browser_type.launch`（`:2105`）用完即弃，但 `browser_type` 对象本身可复用 |
| `profile_path` | `runtime_bundle.profile_path`（`runtime_session.py:808`） | 需在 `execute()` 第一段 try 里把 `runtime_bundle.profile_path` 存到**第二段 try 也能访问**的变量（如 `runtime_profile_path`） |
| `launch_kwargs` | `self._build_runtime_launch_kwargs(debug_mode=debug_mode)` | 决定 headless/headed。回退的 headed 阶段用 `{"headless": False, "args": ["--start-maximized"]}`；回退后重开时用原 `launch_kwargs`（保持 headless 与主流程一致） |
| `proxy` | **调用方已解析好的对象** | 见「要求 4」—— 绝不能从 account 重解析 |

**headed 阶段建议直接复用 `open_persistent_runtime_bundle`**（而不是手写 `launch_persistent_context`）：

```python
headed_bundle = await runtime_session.open_persistent_runtime_bundle(
    browser_type=browser_type,
    platform=platform,
    session_owner_id=session_account_id,
    account=account,
    launch_kwargs={"headless": False, "args": ["--start-maximized"]},
    proxy=proxy,
    profile_path_override=profile_path,
)
```

这样自动满足 R8（`normalize_persistent_profile_context_options` 剥离 UA/locale/时区）、proxy 只传一次（`:766-770` 已处理「只传一次」语义）、`reused_session`/`profile_path` 诊断字段齐全。
**注意**：`open_persistent_runtime_bundle` 会 `mkdir` profile 目录并用 `_profile_contains_state` 判 `reused_session` —— 这在 headed 阶段是期望行为。

**重开阶段**：

```python
new_bundle = await runtime_session.open_persistent_runtime_bundle(
    browser_type=browser_type,
    platform=platform,
    session_owner_id=session_account_id,
    account=account,
    launch_kwargs=original_launch_kwargs,   # 保持与主流程一致的 headless
    proxy=proxy,
    profile_path_override=profile_path,
)
return True, new_bundle.context, new_bundle.page, "success"
```

**必须保留的现有行为**：
- `VerificationRequiredError` → `_wait_verification_and_continue` 的等待与截图逻辑（`:3172-3219`）
- 超时返回 `("timeout")` 语义（调用点 `:1350` 依赖 `fallback_outcome == "timeout"`）
- `fallback_result` 的 **3 元组 / 4 元组兼容**（`:1343-1349`、`:3335-3341`）
- 账号锁必须**全程持有**（关闭旧 context → headed 登录 → 关闭 → 重开，全过程都在 Task 3 的锁内，因为 `execute()` 的 finally 在 `_cleanup_browser_runtime` 之后才释放锁）

**要删的**：
- `_recreate_runtime_page_with_saved_session`（`:3065-3116`）整体删除 —— 它的存在意义就是「读会话文件 → `browser.new_context` 注入」，与 profile 单一载体直接冲突。**连带消除 H3**（它调的 `_load_or_bootstrap_session_async` → `_bootstrap_session_from_profile_sync` 会二次开同一 profile 目录）
- `_run_headful_login_fallback` 里的 `_save_session_async` 调用（`:3230`）与「读回会话文件」逻辑

### Task 4.5 质量评审结论（2026-11-03，VERDICT: NEEDS_FIX）

代码质量评审（不是规格评审）结论：**1 个 🔴 + 5 个 🟠 + 6 个 🟡**。评审已核实「无问题」的 18 项也一并记录，避免以后重复查。

| # | 级别 | 问题 | 位置 | 修法 |
|---|---|---|---|---|
| **F1** | 🔴 | **profile 回退重开的页面停在 `about:blank`，从未 prime → 登录闸门检查必然失败**。Playwright 对持久 context 启动时 push 的 URL 就是 `about:blank`（`chromium.js:254-255`）→ `context.pages[0]` 是空白页；而全仓只有 `:1310`（主流程）与 `:3402`（legacy 回退）两处调 `_prime_runtime_page_for_login_gate`，**新写的 profile 分支两处都没有** → 回退返回后 `:1407` 直接 `_ensure_login_gate_ready(page)` → `login_status_detector.py:809-819` 对 about:blank 明确返回 UNKNOWN/置信度≤0.59，而 `transition_gates.py:91-99` 的 READY 门槛是 `logged_in` + `confidence>=0.7` → **TikTok 平台确定性失败**，且报错完全指不到真因 | `executor_v2.py:3296-3306` | 重开后 prime（`await self._prime_runtime_page_for_login_gate(new_bundle.page, platform, account)`，`account` 要带 `login_url`）+ 调用方侧加「仍 about:blank 就主动导航」兜底。**修法要保证「页面是不是 about:blank」两种情况都成立** |
| **F2** | 🟠 | **并发首连用例假绿**：只断言 `len(created)==2` 与「关了 1 个连接」，**分辨不出关的是不是共享单例** → 把 `await client.aclose()` 改成 `await existing.aclose()` 照样全绿。**当前实现是对的**（评审实测 `LEAKED: []`），问题在测试守不住 | `test_main_account_session_lock.py:1371-1409` | 断言改成**身份级**：被关的是非单例那个，且**单例 `closed is False`** |
| **F3** | 🟠 | legacy 路径在 `session_account_id` 为空时**把登录态整个丢弃**：采集条件用 `session_platform and session_account_id`，而 `_run_headful_login_fallback` 自己已算出 `account_id = session_account_id or account["account_id"]`（`:3191`）却没用 → 主 context 以**完全未登录**状态创建 → 401/跳登录页，结果为空且错误现场与「有头登录已成功」脱节 | `executor_v2.py:3361-3370`、`:3386-3403` | 条件改用 `account_id`；`storage_state` 仍为空时**显式报错**，不静默造未登录 context。**不要**把 `_load_or_bootstrap_session_async` 加回 profile 路径（那是刻意删的，为了消除同目录二次开 profile） |
| **F4** | 🟠 | **`docker-compose.collection.yml` 的 `REDIS_HOST` 默认 `host.docker.internal` 在 Linux 不解析**（两个 compose 都没有 `extra_hosts: host-gateway`）→ 连不上 Redis；且 `collection` 服务**没设 `ENVIRONMENT`** → `account_session_lock_fail_closed()` 返回 False → **fail-open 降级为进程内锁** → compose 注释承诺的「显式指定 Redis ⇒ 不再降级」在默认 Linux 部署下**不成立** | `docker-compose.collection.yml:22/:24` | 优先补 `extra_hosts: ["host.docker.internal:host-gateway"]`；**不要**擅自把 `ENVIRONMENT` 改成 production（该 compose 也用于开发，Redis 不可达时会从「能跑」变成「拒绝采集」）。fail-closed 开关交给环境变量 |
| **F5** | 🟠 | 旧 context 关闭失败只 `logger.debug` → 而它**正是 ProcessSingleton 冲突的根因** → 根因在默认日志里看不见，暴露出来的却是 Chromium 原始报错 → 运维误判为 profile 损坏 | `executor_v2.py:3260-3264` → `_close_playwright_resource:5965-5973` | 至少提到 `warning` 并提示「可能触发 profile 独占锁冲突」；更好的做法是 **close 失败 → 直接中止回退并给清晰中文错误**，别继续撞 Chromium 原始异常 |
| **F6** | 🟠 | 测试没断言「headed context 在**重开之前**已关闭」的**顺序**：关闭用例只断言最终状态 `closed is True` → 有人把 close 挪到重开之后，两条断言仍成立 → 运行时同目录**同时开两个持久 context** | `test_collection_headful_fallback_profile.py:348-369`、`:373-393` | 补断言：**所有 close 事件的下标都小于最后一次 launch_persistent 的下标** |
| **F8** | 🟡 | `inject_redis_password` 对「无 scheme 的畸形 URL」**不是原样返回**，而是产出更畸形的 URL（`urlsplit("host:6379")` 不抛异常，把 `host` 当 scheme）→ 实测 `host://:pw@/6379` | `main_account_session_lock.py:405-433` | 注入前先校验 scheme ∈ `{redis, rediss, unix}`，不匹配则原样返回 |
| **F9** | 🟡 | `LocalSessionLockBackend._locks` **永不回收**（实测 200 个 loop → 200 条目）；`asyncio.Lock` 竞争后会持有 loop 强引用 → 阻止 loop 回收 | `main_account_session_lock.py:277-283`、`:307-318` | `delete_if_token` 释放后，若该 scope 无 holder 无 waiter → `pop` 掉 `_locks` 条目 |
| **F10** | 🟡 | 连接失败日志**不带脱敏后的 URL** → 运维拿不到「连的是哪个 host:port/db」 | `main_account_session_lock.py:503-509` | 失败日志也带 `sanitize_redis_url_for_log(effective_url)` |
| **F11** | 🟡 | `reset_shared_redis_client()` 与并发首连**竞态**：reset 清了单例后，在途的 `ping()` 醒来仍会 `_redis_client_singleton = client` → **复活刚清掉的单例**；且成功后 `_redis_client_failed_at` 不清理 | `main_account_session_lock.py:533-542`、`:512-530` | 成功分支清 `_redis_client_failed_at`；reset 加「epoch」计数，在途连接醒来发现 epoch 变了就自行关闭丢弃 |
| **F12** | 🟡 | 「回退全程不写会话文件」的断言**覆盖面不足**，给人虚假安全感：该用例只调了 `_run_headful_login_fallback`；真实流程里 `_execute_shared_login_phase:1434` 仍会走 `save_session_after_login` → `_save_session_async` 写会话文件（非 TikTok 平台） | `test_collection_headful_fallback_profile.py:264-294` | 选 (a)：把断言文档字符串改准确（「本函数内不写」）。**不要**选 (b)，那会与「非 TikTok 仍落盘」这个待修项（F4-7，属后续 Task）冲突 |
| **F13** | 🟡 | 改写后的用例引用**真实仓库路径** `profiles/<platform>/<id>`（该目录被 gitignore）→ 将来换成真 Playwright 或让 fake 建目录就会在仓库里生成目录 | `test_collection_executor_session_alignment.py:186` | 改用 `tmp_path`（同批新用例已这么做） |

**评审已核实「无问题」的 18 项**（避免重复查）：密码不进日志 ✅ / `redis://:@host` **不会发空 AUTH**（redis-py `parse_url` 是 `if url.password:`，空串 falsy）✅ / IPv6 URL 往返完好 ✅ / 特殊字符密码 round-trip 正确 ✅ / 等待者 Hash 与锁 key 命名空间不冲突 ✅ / 等待者 TTL 计算正确 ✅ / 降级路径的 error 级日志覆盖完整 ✅ / 冷却窗用 `time.monotonic()` 正确 ✅ / 并发首连**实现本身正确** ✅ / `WeakKeyDictionary` 用 loop 做 key 安全 ✅ / 部署契约测试是**真解析 YAML** ✅ / R8 断言方式正确（断言 key 不存在）✅ / 代理未被从已 strip 的 account 重解析 ✅ / legacy 主 context 新增代理安全（Playwright 允许 browser 级 + context 级并存）✅ / `_recreate_runtime_page_with_saved_session` 全仓无残留引用 ✅ / compose 的 profiles 挂载与既有约定一致 ✅ / fallback 返回值 3/4 元组兼容保持 ✅ / `fallback_outcome == "timeout"` 语义保持 ✅。

**注意**：`open_persistent_runtime_bundle` 的 `profile_path_override` 参数已存在（`runtime_session.py:741`），**不需要新增**。


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

## Task 6.0: 清理遗留「采集中心老程序」（D8，用户 2026-11-03 拍板）

> **背景**：B1 的根因是**遗留老程序**（`modules/apps/collection_center/app.py` 4568 行 + `handlers.py` 2094 行）
> 用 `shop_account_id` 命名 profile，与采集的 `main_account_id` 命名空间冲突。
> 用户明确：「**老程序没有用了，我甚至觉得可以直接清理掉老代码，避免后续误用**」。

### 影响面（已独立核实）

| 事实 | 证据 |
|---|---|
| **没有任何生产代码 import `app.py` 或 `handlers.py`** | 全仓 grep：只有 `modules/apps/collection_center/__init__.py:10`（`from .app import CollectionCenterApp`）、`app.py:129/309`（包内 import handlers）、`contract_tests.py:129`（包内）、`backend/tests/test_recording_handler_manual_session_metadata.py:3`（**唯一**的外部测试引用） |
| `CollectionCenterApp` 只在自己 `__main__` 里被实例化 | `app.py:5097-5099`（`if __name__ == "__main__"`）→ 独立 CLI 程序，**不经 FastAPI** |
| 正式采集走 HTTP API，不经老程序 | `collection_tasks.py:1630/1815` → `CollectionExecutorV2`；`app.py:44-45` 自己的注释也写明「正式采集走 POST /api/collection/tasks，**不经过本 CLI**」 |
| 老程序贡献了 17 处 `get_or_create_persistent_context`（shop_account_id 命名空间） | `app.py:659/845/1032/1184/1241/1279/1326/1401/1612/1866/2335/4587/4664`(13) + `handlers.py:498/580/1392/1423`(4) |
| **pwcli 本身没有录制命令** | `pwcli_native.py` 的命令只有 open/list/close/close-all/reload/snapshot/click/fill/press/screenshot/state-save/state-load → pwcli 是**浏览器自动化 CLI**，不是录制器 |
| **录制/组件测试是另一条活链路，不能一起删** | `backend/domains/collection/routers/component_recorder.py`（FastAPI 路由）→ `ComponentTestService.run_component_test_subprocess`（`component_test_service.py:94`）→ **子进程** `tools/test_component.py` |

### 要做的

1. **删除** `modules/apps/collection_center/app.py`、`modules/apps/collection_center/handlers.py`。
2. **改** `modules/apps/collection_center/__init__.py`：去掉 `from .app import CollectionCenterApp` 与 `__all__`。
3. **处理** `modules/apps/collection_center/contract_tests.py`（包内引用 `handlers`）—— 删除或改写。
4. **删除** `backend/tests/test_recording_handler_manual_session_metadata.py`。
5. **排查删除后变死代码的模块**（逐个确认还有没有别的调用方再决定删不删，**不要顺手大删**）：
   - `modules/utils/persistent_browser_manager.py`（老程序贡献了大量调用方）
   - `modules/utils/account_manager.py`（`handlers.py` 的账号来源）
   - `modules/apps/collection_center/component_loader.py` 等包内其它文件
6. **`legacy_shop_artifact_cleanup.py:48`** 把 `profiles/<平台>/<shop_account_id>` 列为遗留物 → 老程序删掉后，**这个清理规则可以正式生效**（把仍在生产的 `tools/test_component.py` 产出的目录也纳入清理范围，见 Task 6.5）。
7. **文档同步**（Task 9）：`docs/guides/` 与 `openspec/` 里凡提到「采集中心应用 / 一键采集 CLI / `CollectionCenterApp`」的地方要改。

### 不在范围

- **不要**动 `tools/test_component.py` 的存在与否 —— 它是**活的**录制/组件测试子进程。改它的 profile 命名空间属于 **Task 6.5**。
- **不要**动 `executor_v2.py` / `runtime_session.py` / `collection_tasks.py` —— 那是别的 Task 的事。
- **不要**顺手重构 `modules/utils/` 下与老程序无关的模块。

---

## Task 6.5: 录制/组件测试子进程改用 main_account_id（与 Task 6.0 配套）

老程序删掉后，`profiles/<平台>/<shop_account_id>` 命名空间的**唯一活的生产者**只剩录制/组件测试子进程 `tools/test_component.py`。

- **位置**：`tools/test_component.py:1792` → `session_owner_id or self.account_id or account_info.get('account_id')`
- **事实**：`backend/services/component_test_service.py:69-72` **已经同时产出** `account_id`（shop）与 `main_account_id`，只是子进程**优先用了 shop 的**。
- **要求**：改成**优先用 `account_info['main_account_id']`** → 录制子进程与采集共用同一个 profile 目录 → R6「同一账号串行」成立、录制时登录的登录态**也能**让采集免验证码。
- **配套**：录制子进程也要走**同一把跨进程账号锁**（否则采集持锁时录制仍会打开同一目录）。
- **注意**：这条改完，`profiles/<平台>/<shop_account_id>` 就彻底没有生产者了 → Task 6.0 第 6 条的清理规则可以正式启用。

### Task 6.5 附带项：`tools/test_component.py` 里 14 处硬编码调试写入（🔴 会打崩子进程）

**实测发现**：`tools/test_component.py` 有 **14 处**遗留的 agent 调试代码，行号 `676 / 686 / 691 / 1755 / 1778 / 1865 / 1904 / 1940 / 2013 / 2039 / 2096 / 2124 / 2743 / 2760`，形态是：

```python
with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
    f.write(json.dumps({'location':'test_component.py:301', ...}) + '\n')
```

**危害**：
1. 路径是**硬编码的本机绝对路径** → 在**任何别的机器**（同事的开发机、生产服务器）上，`open(..., 'a')` 会抛 `FileNotFoundError`（父目录不存在）→ **直接把录制/组件测试子进程打崩**。本机因为 `.cursor/` 目录存在才没暴露。
2. 里面写的 `location` 是**过期行号**（如 `test_component.py:301`），说明是历史注入的残留。
3. 本机 `.cursor/debug.log` 已累积 **538 KB** 噪音。

**要求**：**全部 14 处删除**（连同 `# region agent log` / `# endregion` 注释块）。
**注意**：
- 删除后要检查这些 `with open(...)` 块里**有没有夹带业务逻辑**（本意只是写日志，但必须逐处确认，别连带删掉真实语句）。
- 有些块里包着**真正要执行的语句**（例如打印、赋值、调用），不能整块删 —— 要把调试写入摘掉、**保留**业务语句。
- 删完做一次语法自检：`python -c "import ast,sys; ast.parse(open('tools/test_component.py',encoding='utf-8').read())"`。
- 若同文件还有其它形式的调试残留（`print(` 调试输出、`# TODO`、临时 `logger.debug` 洪水），**只清理这 14 处**，其余不要顺手改（避免超范围）。

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
| F6-9 | 🔴 **巡店打开 profile 时不取账号锁**（2026-11-03 规格评审新发现，M4）—— `modules/apps/collection_center/app.py`（巡店 `:657/845/1032/1184`）与 `handlers.py:498/580/1392/1423` 直接调 `PersistentBrowserManager.get_or_create_persistent_context` 打开 profile，**不经过 Task 3 的账号锁**；`backend/domains/collection/routers/component_recorder.py:553-634`（录制**子进程**，`use_persistent_context=True`）同理 | 采集任务持锁期间，巡店/录制**仍可打开同一 profile 目录** → R6「同一账号串行」在系统层面**没有闭合**。**Task 6 必须让巡店也走同一把跨进程账号锁**（录制子进程同理，见 Step 5b） |

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

- [ ] **Step 6.7: 巡店也纳入同一把账号锁（F6-9 / R6 系统级闭合）**

> **范围已随 Task 6.0 收窄**：遗留 TUI 巡店（`app.py`/`handlers.py`）**已被删除** → 不再需要给它加锁。
> 剩下需要纳入同一把锁的是两条：
> ① **pwcli 巡店面板**（`scripts/pwcli_inspection_panel.py` → `pwcli_native.py`）—— `main_account_id` 直接可得（`pwcli_account_inventory.py:130`）
> ② **录制/组件测试子进程**（`tools/test_component.py`，Task 6.5）

Task 3 只给**采集**加了跨进程账号锁。巡店与录制仍然直接打开 profile 目录 → 采集持锁期间它们照样能打开同一个目录 → **Chromium ProcessSingleton 冲突**，或更糟：双开导致 profile 损坏。

要求：
1. 巡店打开 profile 前，必须用**同一把** `MainAccountSessionLock`（key = `build_lock_key(platform, main_account_id)`）取锁，并**持有到巡店浏览器关闭**（R7：正常关闭 → 刷盘 → 再放锁）。
2. 锁被占用时，巡店面板必须给出**明确提示**（「该账号正在采集中，请稍后再打开」），而不是让 Chromium 自己报 ProcessSingleton 错误。HTTP 状态码用 **409**（现有通路是 500，语义不对）。
3. **锁的持有期**：`pwcli open` 是一次性命令（`command_open:742` 返回 0，PowerShell/Python 结束，**Chromium 还活着**）→ 当前架构里**没有自然持有者**。
   - **推荐方案**：面板（常驻 uvicorn，`pwcli_inspection_panel.py:229`）在 `/api/accounts/open` 前取 Redis 锁 → 启动后从 `output/playwright/.pwcli_native/sessions/<session>/session.json` 读 `pid` → 轮询 `is_process_alive(pid)`（`:451-453`）→ 进程消失即放锁。
   - 面板 `run_action:176` 现在是 **sync def**（`subprocess.run` 阻塞）→ 端点要改 `async def` + `await` 取锁 + `asyncio.create_task` 后台轮询放锁。面板进程崩溃 → 锁泄漏到 TTL（靠 TTL + 心跳兜底）。
> **这一步是 R6「同一账号串行」在系统层面闭合的前提**，与 Task 3 的锁是同一把锁，不是新增一把。

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

### Task 6 / Task 7 二次只读盘点（2026-11-03，结论已独立核实）

> 下表推翻/修正上表 F6/F7 的多处说法。**实施以本表为准。**

#### 计划与真实代码的出入（逐条带证据）

| # | 计划说法 | 真实情况 | 处置 |
|---|---|---|---|
| G1 | F6-2「`save_default_storage_state_from_context` 有 **9 个**调用点」 | 真实 **11 处**：`pwcli_native.py:661`(open)/`:772`(close)/`:803`(reload)/`:825`(snapshot)/`:844`(click)/`:859`(fill)/`:873`(press)/`:892`(screenshot)/`:914`+`:932`(state-save)/**`:948`(`command_state_load`，计划完全漏列）** | 第 11 处（`:948`）在账号级 session 下**确实写 `data/sessions`** → 必须一并处理，否则「不写会话文件」不成立 |
| G2 | F6-8「写的是 `output/playwright/sessions/<token>/session.json`」 | 路径错 → 实际 `output/playwright/.pwcli_native/sessions/<token>/session.json`（`pwcli_native.py:31-32`、`:417-419`） | 改文案；结论不变（pid/port 元数据，不删） |
| G3 | F6-9「巡店开 profile 的 8 处调用点」 | 真实 **17 处** `get_or_create_persistent_context`：`app.py:659/845/1032/1184/1241/1279/1326/1401/1612/1866/2335/4587/4664`(13) + `handlers.py:498/580/1392/1423`(4) | Step 6.7 改造面比计划写的大 **2 倍** |
| G4 | 🔴 **Step 6.7 隐含前提「巡店与采集打开同一个 profile」** | **只对 pwcli 面板成立**。`app.py`/`handlers.py` 走 `resolve_account_session_id(account)` → `account["account_id"]` = **shop_account_id**（`modules/utils/account_identity.py:6-16`）；采集走 `session_owner_id` = **main_account_id**（`runtime_session.py:597-598`）→ **不是同一个目录**。磁盘实证：`profiles/tiktok/tiktok_my_flora_mall_local`（shop_account_id 命名，且是 18 个真实 profile 之一） | 见下方 **B1**（阻塞级，**已提请用户拍板**） |
| G5 | ✅ Step 6.7「面板怎么知道 `main_account_id`」存疑 | **不阻塞**：`scripts/pwcli_account_inventory.py:130` `"account_id": row.main_account_id`（源 `core.main_accounts.main_account_id`）→ 锁 key 可直接拼，与采集侧同 key 空间（`executor_v2.py:2152-2156`） | 面板侧加 Redis 调用即可，**不改数据源** |
| G6 | 🔴 Step 6.6「代理来源与采集一致（`extra_config["proxy"]`）」 | 采集的代理来自 **`core.shop_accounts.extra_config["proxy"]`**；面板数据源是 **`core.main_accounts`**（`pwcli_account_inventory.py:101`），**没有 shop_accounts 的行，也没有 proxy 字段**（`core.main_accounts` 虽有 `extra_config` 列但实测全空） | 面板 SQL 需 **LEFT JOIN `core.shop_accounts`** 取 `extra_config->'proxy'`；解析**复用** `backend/services/account_proxy_config.extract_proxy_config`，不要重写 |
| G7 | F6-5「巡店完全不注入代理」 | ✅ 证实（`pwcli_native.py` 全文 `proxy` 0 命中；`pwcli_helpers.ps1` 同样 0 命中）。**附加实测**：本机 **19 个 enabled shop_account 的 `extra_config->'proxy'` 全为 NULL** → 当前环境没有任何账号配了代理 | 保留 Step 6.6，但语义应是「**通道打通 + 有配置才生效**」 |
| G8 | F6-1「巡店面板已经用 profile，路径规则与采集完全一致」 | ✅ 对 **pwcli 面板**成立（`pwcli_native.py:170-171` = `REPO_ROOT/profiles/<token(platform)>/<token(account_id)>`，与 `session_manager.py:212-213` 同规则）。磁盘实证 `profiles/shopee/shopeeKR`、`profiles/tiktok/Tiktok1店` 都是 main_account_id 净化结果 | 保留 F6-1，但**必须加限定词「指 pwcli 面板」**，否则被 G4 推翻 |
| G9 | F7-2「`SessionManager.__init__` mkdir 两处」 | 真实 **3 处**：`session_manager.py:170`(`data/sessions`) `:175`(`data/session_profiles`) `:179`(`profiles`) | 收窄时三处都要处理（第三处要保留） |
| G10 | Task 7 写入点表「`executor_v2.py:316` `_save_session_async`」 | 行号偏：def 在 `:311-323`，`sm.save_session` 在 **`:321`** | 改行号 |
| G11 | 🔴 Task 7 写入点表「`executor_v2.py:1343` 顺序路径登录后落盘」 | **行号错** → 实际在 **`executor_v2.py:1446`**（条件 `:1428`） | 改行号 |
| G12 | 🔴 Task 7 写入点表只列了 1 处 `_save_session_async` 调用 | 实际 **3 处**：`:1446`（顺序路径）、**`:3230`**（有头验证码回退 —— Task 4.5 正在改）、**`:3412`**（第二个顺序分支） | 补 `:3230` / `:3412` |
| G13 | Task 7「`persistent_browser_manager.py:350` `save_context_state`」 | 偏移 → def 在 **`:319`**，`self.session_manager.save_session(...)` 在 **`:363`** | 改行号 |
| G14 | Task 7「`save_context_state` 有 **14 个**调用方」 | 真实 **12 处**（计划自己列了 12 个）。逐条核对全部存在：`app.py:776/960/2051/2321/2369`、`handlers.py:521/603/1398/1429`、`login_orchestrator.py:198`、`enhanced_recording_wizard.py:124`、`persistent_browser_manager.py:397`(close_context) | 把「14」改成「12」；`close_context:384` → **`:397`** |
| G15 | F7-7「`shopee_exporter.py:194` 恒假」 | `load_session` 在 `:194` ✅，判定在 **`:196`**；唯一调用方 `app.py:438` ✅ | 行号微调 |
| G16 | Task 7「`miaoshou_smart_login.py:505` 是死代码」 | **半对**：`login_miaoshou_account`（def `:543`）确实无调用方 ✅；但 `MiaoshouSmartLogin.__init__:39` 的 `SessionManager()` **会 mkdir `data/sessions`** → 即使死代码也产生目录 | 删写点 ✅ + **必须处理 `:39` 的构造副作用** |
| G17 | F7-6「`base_collector`/`shopee_collector` 的 `temp/sessions/**` 不在废除范围」 | ✅ 完全证实：`base_collector.py:131` `session_dir = Path(f"temp/sessions/{platform}_{account_id}")`（写 `:427/437`）、`shopee_collector.py:65` `Path("temp/sessions/shopee")/store_name`（写 `:339`）→ **都不写 `data/sessions`** | 保留 F7-6；建议加注释锁死 |
| G18 | F7-3「`app.py:2259-2263` 硬编码 `Path("data/sessions")`」 | ✅ 正确（`:2259` 硬编码，`:2260` 目录非空即 "healthy"）。补充：`:2256` 的 `session_key = f"{platform.lower()}/{account_label}"` 用 `account_label`，与 `SessionManager._safe_filename` 规则不同 → 即使今天也是「几乎永不命中」的判据 | 改查 profile 目录 ✅ |
| G19 | F7-4「3 套目录命名规则并存」 | ✅ 证实，**但漏了第 4 套**：`profiles/<platform>/<shop_account_id>`（`PersistentBrowserManager` 路径） | F7-4 改为「**4 套**」 |
| G20 | Task 6 Files 清单的行号 | 逐条核对**全部命中**（面板 `:35-39`/`:176-210`；HTML `:200`/`:223`/`:290`/`:299`；ps1 `:249-304`/`:363`/`:368`/`:373`/`:548-571`；`pwcli_native.py:899-935`/`:325-348`/`:970`/`:1005-1006`；`verify_pwcli_helpers.ps1:10-12`；`generate_pwcli_account_commands.py:137/145/153`；`pwcli_account_inventory.py:26/32/38`） | 无需改 |
| G21 | Task 6 Test 清单含 `backend/tests/test_pwcli_inspection_panel_reporting.py` | 该文件**不含任何 save 断言**（只断言 `result.status`/`result.message`/`combined_output`）→ 不会失效 | 从失效清单移除 |

#### 🔴 阻塞级耦合

| # | 问题 | 后果 | 处置 |
|---|---|---|---|
| **B1** | **profile 身份有三套命名空间**：采集 `profiles/<平台>/<main_account_id>`；pwcli 面板 `profiles/<平台>/<main_account_id>` ✅；**TUI 巡店/组件调试台/录制子进程 `profiles/<平台>/<shop_account_id>`** ❌ | ① TUI 巡店登录的登录态落在**采集永远不读**的目录；② 讽刺的是，**目前是它靠「人工会话优先」这条规则在给采集喂登录态**（`executor_v2.py:1020-1029` → `_should_prefer_manual_storage_state` 恒 True）→ **Task 7 删掉会话文件后这条桥彻底断**；③ `legacy_shop_artifact_cleanup.py:48` 把 `profiles/<平台>/<shop_account_id>` 列为「遗留物」→ **代码在持续制造被自己标记为垃圾的目录** | ✅ **用户已拍板（2026-11-03）：「老程序没有用了，可以直接清理掉老代码，避免后续误用」** → 见 **Task 6.0**（删除遗留老程序）+ **Task 6.5**（录制子进程改用 main_account_id） |
| **B2** | Task 7 删文件后 `_manual_storage_state_exists` 恒 False → 采集行为从「读人工会话」**静默翻转**为「走 profile」 | 方向正确（符合 R1/R4），但**必须在测试里显式断言这个翻转**，否则是静默行为变更 | Task 4.2 的测试改写清单里补一条「人工会话文件存在时也恒走 profile」 |
| **B3** | Step 6.7 的锁在 **TUI 巡店**路径上拿不到 `main_account_id` | `app.py`/`handlers.py` 的 account dict 来自 `AccountManager` 的**文件配置**（`accounts.enc`/`local_accounts.py`），**没有 `main_account_id` 字段** → 要新增 DB 查询 `core.shop_accounts.shop_account_id → main_account_id`。录制子进程**有**（`component_test_service.py:69-72`）但没被用（`tools/test_component.py:1792` 优先取 `session_owner_id or self.account_id`） | 随 B1 的拍板结果处理 |
| **B4** | `command_state_load`（`pwcli_native.py:948`）是第 11 个写入点，计划漏列 | 账号级 session 下它写 `data/sessions` | Task 6 必须单独把该分支置空 |

#### 🟠 重要级耦合

| # | 问题 | 处置 |
|---|---|---|
| **I1** | `manual_seeded` / `protected` 在 Task 6 后**全系统归零**（唯一生产者是 `pwcli_native.py:917-921` 的 `command_state_save`）。消费者：`executor_v2.py:3061`、`:1261`、`runtime_session.py:361/365/515-516`、`collection_tasks.py:464` | **Task 8 的诊断字段必须与 Task 6 同步**（规范 v3 已决定废除 `session_manual_seeded`/`session_protected` → 正好一致，但实施顺序要对齐） |
| **I2** | Task 7 删 `safe_session_account_dirname` 会**打断 `pwcli_native`**：`session_manager.py:131` → `pwcli_native.py:181`(函数内 import) → `runtime_account_state_path:174-190` → `resolve_default_state_config:211` → **每次账号级 open 都触发** → 运行时 `ImportError`（不是启动期） | **必须 Task 6 先把账号级 `default_state_path` / `default_state_mode` 拆掉**，或 Task 7 同步删 `runtime_account_state_path` |
| **I3** | `get_persistent_profile_path:216` 的 **mkdir 副作用** —— 「读 profile 存在性」会**创建空目录**（主仓已见 `profiles/shopee/account-1`、`account-2`、`main-1`、`profiles/miaoshou/acc-1`、`main-1` 等空目录） | 收窄 `SessionManager` 时去掉这个 mkdir，否则「目录可整体删除」的验收被空目录干扰 |
| **I4** | `SessionManager()` 有 **11+ 处构造点**，每处都会 mkdir `data/sessions`：`runtime_session.py:252/266/325/470/745`、`executor_v2.py:244/261/320/1210`、`persistent_browser_manager.py:48`、`shopee_workflow_manager.py:83/421`、`miaoshou_smart_login.py:39`、`shopee_exporter.py:193`、`pwcli_native.py:340`、`tools/test_component.py:1796`、`tools/launch_inspector_recorder.py:413` | 删 `:170` 的 mkdir 之后仍有人传 `base_path=` → **`SessionManager.__init__` 的 `base_path` 参数本身就该删**（`pwcli_native.py:340` 是唯一显式传参的） |
| **I5** | 巡店面板**读**旧会话文件注入 profile（`pwcli_native.py:658` → `:380-393`） | Task 6 只删「写」的话，**旧 `data/sessions` 里的过期 cookie 会被注入进新 profile**，直接违反 R1/R4 → **Task 6 必须同时清掉账号级 `default_state_path`** |
| **I6** | `command_open:723` **重复打开会强杀上一个窗口**（R7 违反）→ 「登录完 → 再点打开」会丢登录态 | Step 6.5 只改了 `command_close`（`:778`），**漏了 `:723`（重复打开）与 `:789`（close-all）** → **三处统一改** |
| **I7** | `persistent_browser_manager.py:205` 的 `_alt` 旁路仍会制造第二份登录态（主仓已有 `profiles/shopee/虾皮巴西东朗照明主体_alt`） | Task 7 Step 3.5 删这个 fallback ✅（方向正确） |

#### Task 6 补充要求（盘点新增）

1. **优雅关闭（Step 6.5）落成方案 D**：**CDP `Browser.close`** → Chromium 正常退出 → 刷盘；**必须带超时 + 回落 `taskkill`**。
   - 注意 `playwright.stop()`（`:777`）**不会关浏览器** —— 浏览器是 `connect_over_cdp` 接上的，Playwright 只断开 CDP，不拥有该浏览器进程。顺序必须是「`browser.close()` → 再 `playwright.stop()`」，**现在顺序相反**。
   - `close_all:788` 是逐个 session 处理、无 CDP 连接 → 要么补连接、要么逐个走同一路径。
2. **锁的持有期（Step 6.7 未回答）**：`pwcli open` 是一次性命令（`command_open:742` 返回 0，PowerShell/Python 结束，**Chromium 还活着**）→ 当前架构里**没有自然持有者**。
   - **推荐方案 ①**：面板（常驻 uvicorn，`pwcli_inspection_panel.py:229`）在 `/api/accounts/open` 前取 Redis 锁 → 启动后从 `output/playwright/.pwcli_native/sessions/<session>/session.json` 读 `pid` → 轮询 `is_process_alive(pid)`（`:451-453`）→ 进程消失即放锁。
   - 面板 `run_action:176` 现在是 **sync def**（`subprocess.run` 阻塞）→ 端点要改 `async def` + `await` 取锁 + `asyncio.create_task` 后台轮询放锁。面板进程崩溃 → 锁泄漏到 TTL（可接受，靠 TTL + 心跳）。
   - 锁被占用时的提示：面板 `run_action:191` 已有 `HTTPException` 通路，但 **500 语义不对 → 应改成 409**。
3. **代理传递要打通 5 环**（盘点逐环列出）：面板 SQL LEFT JOIN 取 proxy → 面板拼命令 → `pwcli_helpers.ps1` 加参数 → `pwcli_native.parse_open_args` 加 `--proxy-server/--proxy-username/--proxy-password` → Chromium `--proxy-server=`。
   - ⚠️ **凭据不要进命令行**（进程列表可见）→ 建议走环境变量或临时文件。
   - ⚠️ Chromium 的 `--proxy-server` **不支持 user:pass** → 需 CDP `Fetch.continueWithAuth`。更省事的替代：把 `launch_browser` 的裸 `subprocess.Popen` 换成 `playwright.chromium.launch_persistent_context(..., proxy={server,username,password})`（Playwright 原生支持带凭据代理，且 R8 更干净），但会改动 session 元数据/重连逻辑（`connect_browser` 依赖 `--remote-debugging-port`）→ **改动面更大，需在 Task 6.1 单独评估**。
4. **`save_default_storage_state_from_context` 改成 no-op 是安全的**：函数签名 `-> None`，**11 个调用点全部是裸语句、无一使用返回值**（已逐个核实）。
5. `:332-333` 的 TikTok origins 补充（`_supplement_tiktok_storage_state_from_pages`）**必须保留给 raw_json 分支**，否则 `pwcli state-save <file>`（人工导出）会丢 `localStorage`。
6. **R7 另一处硬伤**：`launch_browser` 用 `subprocess.Popen(DETACHED_PROCESS)` 启动 Chromium，**Playwright 从不 close 这个 context** → profile 的最终刷盘完全依赖 Chromium 进程自己退出。**用户手点 X = 优雅 ✅**；程序化 close / 重开 / close-all 三条路违反 R7 → 验收口径要写清楚这一点。

#### Task 7 补充要求（盘点新增）

1. **`base_collector` / `shopee_collector` 的 `temp/sessions/**` 明确排除**（G17 已证实）→ 建议加注释锁死，避免后续误删。
2. **`SessionManager` 收窄后外部调用方清单**（会断的）：`runtime_session.load_runtime_session_candidate`（`:347`）与其内部 `_load_session_async`（`:241`）、`_bootstrap_session_from_profile_sync`（`:258`）在 Task 4.2 后**全部变成死链**；`_bootstrap_session_from_profile_sync` 还有个隐患 —— 它会用**同一 profile 目录再开一个持久 context**，主 profile 开着时 → Chromium ProcessSingleton 冲突 → 被 `except Exception` 吞掉 → 返回 `None` → **新 context 无登录态且不报错**。
3. **文档同步范围要扩**（M5）：`docs/guides/` 下 4 个文档 + `openspec/specs/data-collection/spec.md:47/49` 仍在规定 `data/sessions` 为事实标准 → Task 9 必须逐一点名覆盖。


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
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_legacy_shop_session_cleanup.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_persistent_browser_manager_session_metadata.py -v
```

> ⚠️ **Task 6.0（2026-11-03 已完成）删掉了 `backend/tests/test_recording_handler_manual_session_metadata.py`**（它测的是已删除的 `handlers.py`）→ 上面的命令里已移除该项。

> 旧语义测试（人工保护 / 质量分回退 / 30 天门禁）随 `test_session_manager_protection.py` 一并删除；其余文件里断言旧 metadata 的用例按新语义改写。

- [ ] **Step 8: 提交**

```powershell
git rm backend/tests/test_session_manager_protection.py
git add modules/utils/sessions/session_manager.py modules/utils/sessions/__init__.py modules/apps/collection_center/executor_v2.py modules/apps/collection_center/runtime_session.py modules/utils/persistent_browser_manager.py modules/collectors/miaoshou_smart_login.py modules/collectors/shopee_workflow_manager.py modules/services/shopee_exporter.py modules/utils/sessions/legacy_shop_artifact_cleanup.py backend/main.py run.py backend/tests/test_session_storage_roots.py backend/tests/test_legacy_shop_session_cleanup.py
git commit -m "refactor(session): 废弃会话文件，登录态只保留 profile 单一载体"
```

> ⚠️ **Task 6.0 已删除 `modules/apps/collection_center/app.py`** → 上面 `git add` 清单里的该项**已移除**。

---

## Task 3.1: 账号锁后端统一（2026-11-03 Task 6.5 实施时新发现，计划外新增）

> **位置**：`backend/services/main_account_session_lock.py` 的 `_backend_mode()` + `backend/utils/config.py` 的 `account_session_lock_backend()` / `account_session_lock_environment()`。
> **规模**：小（单模块 + 测试）。

### 问题

`auto` 模式的解析规则是「生产 → Redis / 其余 → 进程内锁」（`main_account_session_lock.py:596`）：

```python
if mode == "auto":
    return "redis" if account_session_lock_environment() == "production" else "local"
```

但 Task 6.5 给**录制/组件测试子进程**选后端时用的是另一套规则：**只要配了 `REDIS_URL` 就走 Redis**（否则进程内锁对子进程完全无效，因为父子是两个进程）。

→ **非生产环境下**：父进程（FastAPI 采集任务）持**进程内锁**，子进程（录制）持**Redis 锁** → **两者互不排斥** → 采集持锁期间，录制仍可打开同一 profile 目录 → R6「同一账号串行」在非生产下**没闭合**。

### 修法

把 `auto` 的解析改成「生产 **或** 实际配了 `REDIS_URL` → Redis；否则 → 进程内锁」，让父子两侧用**同一套判定**。

- 「配了 `REDIS_URL`」的判据要看**真实生效值**（`REDIS_URL` 或 `CELERY_BROKER_URL`），不能只看环境变量是否存在（compose 里 `REDIS_URL: redis://${REDIS_HOST:-host.docker.internal}:${REDIS_PORT:-6379}/0` **恒有值**，即使宿主 Redis 没起 —— 那时 Redis 连不上会走 fail-open 降级，行为可接受）。
- 单元测试绝不连真实 Redis 这件事**由 `backend/tests/conftest.py` 的护栏保证**（无条件设 `ACCOUNT_SESSION_LOCK_BACKEND=local`），**不依赖** `auto` 的非生产语义 → 改 `auto` 不会破坏测试隔离。
- 两侧（`main_account_session_lock.py` 与 `tools/test_component.py`）的判定**必须收敛到同一个函数**，避免再次分叉。

### 验收

- 非生产 + 配了 `REDIS_URL` → 父进程与子进程都拿 **Redis** 锁 → 同一个 key 互相排斥。
- 未配 `REDIS_URL` → 两侧都退化为进程内锁并**明确告警**。
- 锁不可达时的降级行为保持分级（生产 fail-closed / 非生产 fail-open），并有 error 级日志。

---

## 遗留 profile 命名空间的剩余生产者（2026-11-03 Task 6.5 盘点新发现）

`profiles/<平台>/<店铺账号ID>` 这套**与采集侧不同的命名空间**，在 Task 6.0 删掉老程序后，生产者只剩：

| 生产者 | 状态 | 处理 |
|---|---|---|
| `tools/test_component.py` | ✅ Task 6.5 已改为按**主账号 ID** 命名 | 已闭环 |
| `modules/apps/collection_center/app.py` / `handlers.py` | ✅ Task 6.0 已删除 | 已闭环 |
| **`tools/launch_inspector_recorder.py:417`** | 🔴 **仍在用 `account_info['account_id']`（店铺账号 ID）** | **Task 7 必须一并改掉**，否则 `profiles/<平台>/<店铺账号ID>` 仍有活的生产者，遗留清理规则（`legacy_shop_artifact_cleanup.py`）清理不干净 |

> 顺带：`backend/services/recorder_segment_validator.py:237` 调用 `_run_login_before_non_login` 后**丢弃**返回的 context/page；若该路径触发有头回退，回退会关掉旧 context，而调用方仍持有已关闭的旧 page。**旧实现同样如此（非本次引入）**，但改用 profile 载体后该路径需要调用方接收新 page —— 列入 Task 7 一并核实。

---

## Task 8: 诊断字段与前端展示

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:1121-1167`（`_runtime_session_diagnostics`）、`:1094-1119`（`_resolve_session_metadata`）、`:2874-2905`（`_should_skip_post_login_session_persist`）、`:2055/:2167/:5935`（`params["session_metadata"]`）、`:2068/:2180`（诊断调用点）、`:29-32`（import）
- Modify: `backend/domains/collection/routers/collection_tasks.py:437-467`（白名单抽取）、`:470-540`（顶层提升）
- Modify: `backend/schemas/collection.py:377-424`（`TaskResponse` 字段声明）
- Modify: `frontend/src/domains/collection/views/collection/CollectionTasks.vue:360-395`、`:1093-1122`
- Modify: `frontend/scripts/collectionTaskSessionQualityUi.test.mjs`（建议同时改名 `collectionTaskSessionProfileUi.test.mjs`）
- Test: `backend/tests/test_collection_task_runtime_metadata.py`、`backend/tests/test_collection_executor_session_alignment.py:935-981`、`backend/tests/test_collection_frontend_contracts.py:247-259`

### Task 8 只读盘点结论（实施前必读）

| # | 事实 | 影响 |
|---|---|---|
| F8-1 | **代码里已有等价字段，名字不同**：`persistent_profile_path`（`executor_v2.py:1141` ← `bundle.profile_path`）、`profile_contains_state`（`:1142-1144` ← `bundle.reused_session`） | 规范 §8 的 `session_profile_path` / `session_reused` 是**改名**，不是新增。改名要同步 executor + router + 2 个后端测试共 4 处 |
| F8-2 | **`session_source` 已存在**（`executor_v2.py:1149`），取值是 `persistent_profile` / `storage_state` / `manual_storage_state` / `fresh_login`（`:1042-1046` 赋值），前端 `:366-368` 已在展示 | 计划把它当「新增」是误判。**按规范 v3（单一载体）应收敛为 `profile`** → 需同步 executor 赋值点 + 前端标签映射 |
| F8-3 | 🔴 **前端那 5 个旧字段今天就是死代码**：`TaskResponse`（`backend/schemas/collection.py:377-424`）未声明 `session_quality_*`，`response_model` 会把未声明字段全部丢弃；Vue 读的是顶层 `detailTask.session_quality_source`，而 router 只把 7 个键提升到顶层（`collection_tasks.py:532-539`） | **删这 5 项没有功能回退风险**（它们从未渲染过） |
| F8-4 | 🔴 **新字段默认也传不到前端**：router 不把 `persistent_profile_path`/`profile_contains_state` 提升到顶层，`TaskResponse` 也没声明 | **必须同时改** `collection_tasks.py:470-540`（提升顶层）+ `backend/schemas/collection.py:377-424`（声明字段），否则 Task 8 Step 3 是空做 |
| F8-5 | 🔴 **Task 8 与 Task 7 强耦合**：旧字段的值来自 `session_metadata`，而 `session_metadata` 来自 `SessionManager.get_session_metadata()`（`executor_v2.py:1112-1116`）——Task 7 Step 3 要删该方法 | Task 8 必须连带删 `_resolve_session_metadata`（`:1094-1119`）与三处 `params["session_metadata"]` 赋值，否则 Task 7 一执行 Task 8 就断 |
| F8-6 | 🔴 **并行路径根本没有会话诊断**：`execute_parallel_domains`（`:5779`）里 `:5935` 只设 `session_metadata`，**从不调用** `_runtime_session_diagnostics` | Task 10 第 8 步（并行采集）拿不到 profile/复用/代理诊断 → 若要在并行侧取证，需在 `execute_parallel_domains` 补一次诊断写入 |
| F8-7 | `session_proxy` 的数据源在作用域内：`proxy` 是 `execute()` 局部变量（`:1895`），两个诊断调用点（`:2068`/`:2180`）同属 `execute()` → 最小改动是给 `_runtime_session_diagnostics` 加 `proxy=` 关键字参数并用 `mask_proxy_server` 脱敏 | `executor_v2.py:29-32` 的 import 加 `mask_proxy_server` 即可 |
| F8-8 | `profile_contains_state` 语义失真：只判「profile 目录非空」（`runtime_session.py:460-464`），而 `session_manager.py:216` 会 `mkdir` 空目录 → 未登录账号也报 True | 改名成 `session_reused` **不解决**失真。要么同步修判定（Task 4 F4-6），要么字段名用更诚实的措辞 |
| F8-9 | 前端无 TS 类型定义、无快照测试；`frontend/scripts/*.mjs` **不进 CI**（`.github/workflows/ci.yml:242-243` 只跑 `ci_frontend_test_silence_gate.py`） | 守卫测试只能手工 `node --test` 跑 |
| F8-10 | `backend/tests/test_collection_frontend_contracts.py:247-259` 断言 Vue 里存在 `session_source`、`getSessionSourceLabel`、旧文案 | 改标签映射文案会让它红 → **必须同步改写**（计划未列） |

**字段变更表（按规范 v3 收敛）**：

| 旧 | 新 |
|---|---|
| `session_quality_score` | 删除 |
| `session_quality_gate_passed` | 删除 |
| `session_quality_source` | 删除（其语义由 `session_source` 承载） |
| `session_manual_seeded` | 删除 |
| `session_protected` | 删除 |
| `persistent_profile_path` | 改名 `session_profile_path` |
| `profile_contains_state` | 改名 `session_reused` |
| `session_source`（4 值） | **取值收敛为 `profile`**（单一载体） |
| — | `session_proxy`（新增，脱敏后的代理标识） |

- [ ] **Step 1: 改写后端测试**

`test_collection_task_runtime_metadata.py:41` 的断言改为新字段集；同时改写 `test_collection_executor_session_alignment.py:935-981`（断言 `persistent_profile_path`/`profile_contains_state`）与 `test_collection_frontend_contracts.py:247-259`（断言 Vue 里的字段名与文案）。

- [ ] **Step 2: 实现后端**

1. `executor_v2._runtime_session_diagnostics`：产出 `session_profile_path` / `session_reused` / `session_source`（收敛为 `profile`）/ `session_proxy`（`mask_proxy_server` 脱敏）；删 5 个旧字段。
2. 删除 `_resolve_session_metadata`（`:1094-1119`）与三处 `params["session_metadata"]` 赋值（`:2055`/`:2167`/`:5935`），以及 `_should_skip_post_login_session_persist`（`:2874-2905`，依赖 `manual_seeded`/`protected`）。
3. `collection_tasks.py:437-467` 白名单同步；`:470-540` 把新字段提升到响应顶层。
4. `backend/schemas/collection.py:377-424` 的 `TaskResponse` 声明新字段（否则 `response_model` 会丢弃）。
5. 两个诊断调用点传 `proxy=proxy`。

- [ ] **Step 3: 改前端**

`CollectionTasks.vue`：删除「质量来源」「质量评分」「质量门槛」「人工播种」「会话保护」五项；新增「会话载体」（profile 路径）、「是否复用」「出口代理」三项；删除 `getSessionQualitySourceLabel`；`getSessionSourceLabel` 映射改为 `profile` 语义。

- [ ] **Step 4: 改前端守卫测试**

`frontend/scripts/collectionTaskSessionQualityUi.test.mjs` 重写为断言新字段名，**并加反向断言**（旧字段名不应再出现）——反向断言比「存在断言」更抗回归。建议同时改文件名。

- [ ] **Step 5: 跑测试**

```powershell
python -m pytest backend/tests/test_collection_task_runtime_metadata.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_frontend_contracts.py -v
cd frontend; npm run build; node scripts/collectionTaskSessionQualityUi.test.mjs
```

- [ ] **Step 6: 提交**

```powershell
git add modules/apps/collection_center/executor_v2.py backend/domains/collection/routers/collection_tasks.py backend/schemas/collection.py frontend/src/domains/collection/views/collection/CollectionTasks.vue frontend/scripts/collectionTaskSessionQualityUi.test.mjs backend/tests/test_collection_task_runtime_metadata.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_frontend_contracts.py
git commit -m "refactor(diagnostics): 会话诊断字段改为 profile 载体语义"
```

---

## Task 9: 文档同步

**Files:**
- Modify: `docs/guides/COLLECTION_SESSION_LIFECYCLE.md`（v3 → v3.1，回填实现结果）
- Modify: `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`（「代理预留」段改为已实现）
- Modify: `docs/superpowers/plans/STATUS.md`（新增条目）
- Verify: `docs/ACTIVE_DOCS.md`（已指向本文，无需改）

### Task 6.0 交接的文档清单（2026-11-03，删老程序后必须同步）

Task 6.0 删除了遗留 CLI 老程序，以下文档仍提到「采集中心应用 / 一键采集 CLI / `CollectionCenterApp`」，**Task 9 必须改**：

| 文档 | 要改什么 |
|---|---|
| `docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md` | 本文自身（Task 7 的 git add / 测试清单已改，见上文标注） |
| `docs/superpowers/plans/2026-03-28-platform-adapter-surface-convergence.md` | 「Isolate Legacy `collection_center/app.py`」那一节 |
| `docs/superpowers/plans/2026-04-02-main-account-shop-account-domain-chain-implementation.md` | 提到老程序的部分 |
| `docs/superpowers/plans/2026-11-02-collection-session-overwrite-semantics.md`（已作废） | 548/594/613 行改 `handlers.py` 的地方 —— **该文档已标作废**，只需加一句「相关代码已随 Task 6.0 删除」 |
| `docs/guides/maintenance_scheduler_guide.md` | 引用了已死的 `modules/utils/recording_maintenance.py` |
| `docs/guides/COLLECTION_PATH_LEGACY_INVENTORY.md` | 遗留路径盘点清单，去掉已删的老程序 |
| `openspec/`（**活**的 `changes/` 与 `specs/`） | 已核实**无**活引用；`openspec/changes/archive/**` 是历史归档，**不要动** |

### Task 6.0 保留但已无调用方的模块（文档里若提到，要标注）

以下模块在老程序删除后**没有活调用方**，但**本次不删**（避免超范围大删），文档里不要再把它们描述成「在用」：

`modules/utils/template_generator.py` / `modules/utils/har_capture_utils.py` / `modules/automation/shopee_seller_auto_login.py` / `modules/utils/account_identity.py`（`describe_account_identity` 无调用方）/ `modules/utils/data_processing_pipeline.py`（**本身已损坏**：`from models.database import CollectionTask, DatabaseManager`，这两个名字在 `modules/core/db/schema.py` 单一数据源下都不存在，模块根本 import 不了）。

> ⚠️ `modules/utils/persistent_browser_manager.py`、`modules/utils/account_manager.py`、包内 `component_loader.py` 等**仍有活调用方**（`login_orchestrator` / `enhanced_recording_wizard` / `shopee_playwright_exporter` / `tools/launch_inspector_recorder.py`）→ **不要**把它们写成「已废弃」。

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

- [ ] **Step 0: 落一份可复用的基线快照**

仓库里**没有** pytest 基线对比脚本，「143 failed + 22 errors」这个基线也没有任何文档记录 → 判定「零新增失败」不可复现。**先落一份基线快照文件**（含失败用例 id 列表），后续每次验收都拿它做集合 diff。

- [ ] **Step 1: 后端全量测试**

```powershell
python -m pytest backend/tests -q --tb=no -rfE
```

Expected: **失败数不高于基线**，且**新增失败必须定位到本计划改动**。

> ⚠️ **不是「全部 PASS」** —— 仓库既有基线就是 **143 failed + 22 errors**（已用同 worktree 同环境双向验证过）。「全部 PASS」这个口径不可能达成，也不该达成。
>
> **判据必须是失败集合逐条 diff，不是看计数**。可用 `--junitxml` 产出后比对（`NEW failures=0`）。
>
> ⚠️ 跑全量会改写 `modules/platforms/shopee/components/login_v1_0_0.py` 的行尾 → 跑完 `git checkout --` 复原，不要提交它。

- [ ] **Step 2: 前端构建 + 守卫测试**

```powershell
cd frontend
npm run build
node scripts/collectionTaskSessionQualityUi.test.mjs
```

Expected: exit=0。

> ⚠️ `frontend/scripts/*.mjs` **不进 CI**（`.github/workflows/ci.yml:242-243` 只跑 `ci_frontend_test_silence_gate.py`）→ 必须手工跑。
> ⚠️ Task 8 会把守卫测试改名（建议 `collectionTaskSessionProfileUi.test.mjs`）→ 此处命令同步改。

- [ ] **Step 3: 发布前门禁**

```powershell
python scripts/verify_release_local.py --skip-build
```

Expected: exit=0。

> ⚠️ **本地可能跑不通**（不要误判成代码问题）：该脚本需要 `.env.production`（**本地 worktree 不存在**）、docker compose 文件齐全，且内部第 3 步 `verify_system_role_integrity.py --repair` **会写库**。
>
> 跑不通时改为**只跑只读的那几项门禁**（`verify_rules_completeness.py` / `verify_root_md_whitelist.py` / `verify_utf8_source_hygiene.py`），并在验收记录里注明「发布门禁因缺 `.env.production` 未执行」。

- [ ] **Step 4: 真实采集验收（关键）**

在**本地笔记本**上按序执行：

1. 备份并清空旧的会话目录（不进 VCS）：把 `data/sessions/` 整体改名为 `data/sessions.bak-<日期>`
2. 清空验收账号对应的 profile 目录（或整个目录改名备份）。**账号与目录的对应关系**（实测）：`shopee_sg_eternalbloom_local` → `profiles/shopee/shopee_sg_eternalbloom_local`（下划线保留）。`profiles/shopee/shopeeKR` 是账号 "shopee KR" 的**旧目录**，不是验收账号的目录
3. 采集任务 A（`shopee_sg_eternalbloom_local`）→ 应要求登录 + 验证码
4. **检查 `profiles/shopee/shopee_sg_eternalbloom_local/Default/Network/Cookies` 的 mtime 已更新**（⚠️ **不是** `Default/Cookies` —— 本机 Chromium 的 cookie 库实际在 `Default/Network/Cookies`，实测存在），且 `data/sessions/` 下**没有**新文件
5. 立刻再跑一次采集 A' → **必须免验证码**
6. 巡店面板「打开巡店」→ 浏览器用的是**同一个** profile 目录（核对进程参数 `--user-data-dir`）→ 人工登录 → 关闭浏览器 → 再次采集应免验证码
7. 巡店面板**没有**「保存会话」按钮
8. 并行采集（多数据域）→ 任务成功，且 `data/sessions/` 仍无新文件
9. 代理灰度（**按 2026-11-03 用户决定：本轮用本地假代理跑通链路，真实代理凭据后补**）：
   1. 起一个本地 HTTP 代理（记录收到的请求行），脚本模板见 `%TEMP%\proxy_chain_probe.py`（**已预验证通过**：Playwright 带 `proxy=` 时流量确实经过代理，输出 `PROXY_CHAIN_OK`）。
   2. 给验收账号写 `core.shop_accounts.extra_config["proxy"] = {"enabled": true, "server": "http://127.0.0.1:<代理端口>"}`（本地假代理**不需要凭据**）。
   3. 采集该账号 → 判据：假代理收到了发往平台的请求行，且任务诊断里的 `session_proxy`（脱敏后）等于 `http://127.0.0.1:<端口>`。
   4. **本步只证明「流量确实经过代理」**，不证明真实出口 IP。真实出口 IP 的验证留到拿到真代理凭据后补做（届时核对平台侧展示的 IP）。

**「免验证码」的客观判据**（第 5 步判定依据，四项同时成立才算过）：

| # | 证据 | 取证方式 |
|---|---|---|
| E1 | 全程没弹验证码 | `core.collection_tasks.verification_type` 与 `verification_screenshot` **均为 NULL** |
| E2 | 登录门检查通过 | `core.collection_task_logs.details` 里 `step_id="login_gate_result"` 的 `login_gate_ready=true` |
| E3 | 确实复用了 profile 登录态 | 同一行 details 里 `reused_session=true` + 诊断 `session_reused=true` + `session_source=profile` |
| E4 | profile cookie 已刷盘 | `profiles/<p>/<a>/Default/Network/Cookies` 的 **mtime 前进** |

> E1~E3 可直接用 SQL 从 `core.collection_task_logs` 取证；E4 从文件系统取证。
> 「无验证码截图」可作辅助证据：`temp/screenshots/verification_<platform>_<时间戳>.png` 在采集窗口内**没有**新文件。

**Expected**：第 4、5、6、7、8、9 步全部符合。**第 4 或第 5 步不过 → 停下报告，不要加临时补丁。**

> ⚠️ **前置依赖**：本步依赖 Task 3 / 4 / 5 / 6 / 7 **全部完成**。在 Task 7 落地前，`SessionManager.__init__` 仍会 mkdir 并写 `data/sessions/`（`session_manager.py:169-170`）→ 第 1/4/5/8 步必然失败。
>
> ⚠️ **profile 根目录是「仓库根相对」的，不是 cwd 相对**（实测）：`session_manager.py:25` 的 `REPO_ROOT = Path(__file__).resolve().parents[3]`，
> `get_persistent_profile_path` 用 `REPO_ROOT / "profiles" / <platform> / <safe_account_id>`。
> → **从 worktree 跑验收，用的是 worktree 自己的 `profiles/`，里面是空的**（只有 6 个测试残留的空目录：
> `miaoshou/acc-1`、`miaoshou/main-1`、`shopee/account-1`、`shopee/account-2`、`shopee/main-1`、`shopee/shopee_sg_x`）。
> → **主仓 `profiles/` 实测有 18 个真实 profile**（每个含 `Default/Network/Cookies`），例如
> `shopee/Leslieshopmain`（2026-11-1）、`shopee/shopeeKR`（2026-11-2）、`tiktok/Tiktok1店`（2026-11-2）；
> 还存在一个 `_alt` 旁路目录 `shopee/虾皮巴西东朗照明主体_alt`（Task 7 要清理）。
> → **验收账号 `shopee_sg_eternalbloom_local` 在主仓 `profiles/` 里没有对应目录** → 第 2 步是「无 profile 可清」，
> 第 3 步必然是**首次人工登录**。
> → **因此真实采集验收必须在「分支合并回 main 之后」跑**（或在 worktree 里先把主仓 profile 拷过去）。
> 在 worktree 里跑只能证明「首次登录能落进 profile」，**证明不了「第二次免验证码」**（那是本步的核心）。
>
> ⚠️ **`safe_account_id` 的净化规则**（`session_manager.py:213`）：`isalnum() or _ or -` → **空格被去掉，中文保留**。
> 所以账号 "shopee KR" 的 profile 目录是 `profiles/shopee/shopeeKR/`，
> 账号 "虾皮巴西东朗照明主体" 的目录是 `profiles/shopee/虾皮巴西东朗照明主体/`。
> 这与会话目录规则 A（`safe_session_account_dirname`，**保留空格**）**不同** —— 两套命名规则并存是既有事实，不要混用。
>
> ⚠️ **本地触发采集的唯一入口是 HTTP API**：`POST /api/collection/tasks`（需管理员登录）。仓库里**没有**创建采集任务的 CLI 脚本。巡店面板启动：`python scripts/pwcli_inspection_panel.py`（自动开 `http://127.0.0.1:<port>/?token=<token>`）。
>
> ⚠️ **代理配置无 UI**：只能直接改 DB 的 `core.shop_accounts.extra_config["proxy"]`。
>
> ⚠️ **并行侧无诊断**（F8-6）：第 8 步拿不到 profile/复用/代理证据，只能靠「任务成功 + `data/sessions/` 无新文件」判定。

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

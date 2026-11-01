# 店铺身份与巡店会话复用 · 第二批（正本）实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「改名」「一账号一窗口」「内部标准名」这三件本来只能靠人记住的事，变成系统保证 —— 改名不再产生分歧、账号不再互相踢窗口、内部标准名有唯一约束且带地区标识。

**Architecture:** 第一批把会话与身份两条链路修通后，本批做三件事。**会话线**（Task 12–14）：`slugify` 保留中文并加稳定哈希后缀，让每个账号的 session 名唯一；会话新鲜度改以 `saved_at` 为准；TikTok 走持久 profile 时也落 storage_state。**身份线**（Task 15–16）：新增内部标准名 `internal_code` 的回填与账号管理页编辑入口；把「改名」收进一个带联动的入口 —— 唯一性校验 → 旧名转曾用名 → 新名接管主别名 → 同步旧表 → 同步标准名 → 刷新队列。

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / Pydantic / PostgreSQL 15.14（`postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp`）/ pytest / PowerShell 5.1 / Vue 3 + Element Plus

**Spec:** `docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md`（v3）

**前置条件**：第一批计划 `docs/superpowers/plans/2026-11-01-shop-identity-and-session-reuse-batch1.md` 全部完成并合入。**本批不能先于第一批做改名** —— 改名依赖第一批的别名区域维度（D10）与语义层判定（D13）。

---

## 0. 适用范围与全局约定

### 0.1 本计划覆盖的 spec 条款

| Spec 条款 | 计划任务 | 验收项 |
|---|---|---|
| D9 slug 保留中文 / session 名可区分 | Task 12 | B1 B2 |
| D7 会话新鲜度以 `saved_at` 为准 | Task 13 | A11 |
| D8 TikTok 持久 profile 也落 storage_state | Task 14 | A12 |
| §4.1 内部标准名 + D10 | Task 15 | B4 |
| D15 曾用名 / D16 别名应用级约束 / D17 改名联动 | Task 16 | A13 B3 B5 |

### 0.2 明确不在本计划范围

- IP 隔离（spec §10）。
- `TK新加坡3C店` 的认领（第一批已做可见性，业务决定暂不认领）。
- `data/sessions` 历史别名孤儿目录清理（spec §10）。
- 启用 disabled 主账号（业务决策，spec §11.2 第 2 条）。

### 0.3 全局约定

- **分支**：`git switch -c feature/shop-identity-batch2`（从第一批合入后的 main 拉）。
- 提交信息风格：`type(scope): 中文标题` + 要点正文。
- ORM SSOT：`modules/core/db/schema_parts/platform.py`。
- Pydantic 契约放 `backend/schemas/`。
- 新后端运行时代码用 `AsyncSession` / `get_async_db()`，`datetime.now(timezone.utc)`。
- Windows 终端输出不带 emoji。
- **不新增抓取能力**。

---

## Task 12: `slugify` 保留中文 + session 名可区分（一账号一巡店窗口）

**Files:**
- Modify: `scripts/pwcli_account_inventory.py:48-55`（`slugify` / `work_tag`）
- Modify: `modules/utils/pwcli_native.py:701-709`（`command_open` 杀同名 session 的逻辑）
- Test: `backend/tests/test_pwcli_session_naming.py`（新建）

**背景**：`scripts/pwcli_account_inventory.py:48-51` 的 `slugify` 用 `re.sub(r"[^A-Za-z0-9]+", "-", ...)` → **丢弃全部非字母数字** → 中文账号名塌成 `account`。实测 `虾皮巴西（东朗照明主体）` 与 `验证码测试账号` 都 slug 成 `account` → work_tag 相同 → session 名相同 → `modules/utils/pwcli_native.py:705-708` 的 `command_open` 在打开时**杀掉同名 session** → 账号之间互相踢浏览器、互相覆盖 storage_state。

这是 ③（一账号一巡店窗口）与 ④（账号标识唯一化）的**共同根因**。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_pwcli_session_naming.py`：

```python
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pwcli_account_inventory import slugify, work_tag  # noqa: E402


def test_slugify_keeps_non_ascii_distinct():
    """中文账号名不能塌成同一个 slug。"""
    assert slugify("虾皮巴西（东朗照明主体）") != slugify("验证码测试账号")


def test_slugify_is_stable_for_same_input():
    a = slugify("虾皮巴西（东朗照明主体）")
    b = slugify("虾皮巴西（东朗照明主体）")
    assert a == b


def test_slugify_output_is_filesystem_and_shell_safe():
    out = slugify("Leslieshop:main")
    assert ":" not in out
    assert "/" not in out
    assert " " not in out


def test_work_tag_differs_per_account():
    assert work_tag("shopee", "虾皮巴西（东朗照明主体）") != work_tag("shopee", "验证码测试账号")
    assert work_tag("shopee", "hongxikeji:main") != work_tag("tiktok", "hongxikeji:main")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_session_naming.py -q
```

Expected: `test_slugify_keeps_non_ascii_distinct` 与 `test_work_tag_differs_per_account` FAIL。

- [ ] **Step 3: 改 `slugify`**

把 `scripts/pwcli_account_inventory.py:48-55` 替换为：

```python
def slugify(value: str) -> str:
    """把账号标识转成可安全用于路径与 session 名的短标签。

    非 ASCII 字符（中文账号名）必须保留或参与哈希，否则不同账号会塌成同一个
    slug，导致巡店窗口互相踢、storage_state 互相覆盖（见 spec D9）。
    """
    text = str(value or "").strip().lower()
    if not text:
        return "account"

    ascii_part = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    non_ascii = "".join(ch for ch in text if ord(ch) > 127)

    if not ascii_part:
        # 纯中文账号名：用稳定短哈希区分，避免全部塌成 "account"
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        return f"cn-{digest}"

    if non_ascii:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        return f"{ascii_part}-{digest}"

    return ascii_part


def work_tag(platform: str, account_id: str) -> str:
    return f"{slugify(platform)}-{slugify(account_id)}-inspect"
```

并在文件顶部补 `import hashlib`。

- [ ] **Step 4: 让 `command_open` 只杀同账号的 session**

`modules/utils/pwcli_native.py:701-709` 目前按 **session 名**杀进程。session 名在修好 slugify 后已按账号唯一，所以这一步只需**补注释与断言**，不改变行为：

```python
def command_open(session: str, args: list[str]) -> int:
    url, headed, profile_dir, account_id = parse_open_args(args)
    if profile_dir is None:
        profile_dir = resolve_default_profile_dir(session, account_id)
    existing = load_session(session)
    # session 名按账号唯一（见 spec D9 / scripts/pwcli_account_inventory.py:work_tag），
    # 因此这里杀掉的只会是「同一个账号的上一次窗口」，不会误伤其它账号。
    if existing and is_process_alive(int(existing["pid"])):
        kill_process(int(existing["pid"]))
        remove_session(session)
    metadata = launch_browser(session, url, headed, profile_dir, account_id=account_id)
    ...
```

> **实施者必须核对**：`session` 参数的来源。面板走 `Open-PwcliPlatform -WorkTag <work_tag>` → session = `"$platformName-$WorkTag"`，而 work_tag 已按账号唯一。**若发现 session 名在某些调用路径上仍是平台级**（如 `Open-PwcliPlatform` 不带 `-WorkTag` 时默认 `explore`），必须同步在 `Open-PwcliPlatform` 里把 work_tag 拼上账号，否则两个账号仍会共用 `shopee-explore`。这一条是本 Task 的**必查项**。

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_session_naming.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_pwcli_helpers_session_targeting.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 核对磁盘上没有因旧 slug 产生的冲突目录**

```bash
Get-ChildItem output/playwright/profiles -Recurse -Directory | Where-Object { $_.Name -eq "account" } | Select-Object FullName
```

Expected: 列出历史遗留的 `account` 目录（**不要在本 Task 删**，清理属 spec §10 的独立任务）。记录下来交业务确认。

- [ ] **Step 7: 提交**

```bash
git add scripts/pwcli_account_inventory.py modules/utils/pwcli_native.py backend/tests/test_pwcli_session_naming.py
git commit -m "fix(巡店): slugify 保留非 ASCII 身份，一账号一巡店窗口

- slugify 丢弃全部非字母数字导致中文账号名塌成 account，
  两个账号共用 session 名 -> 打开第二个会杀掉第一个的浏览器并覆盖 storage_state
- 改为 ASCII 部分保留 + 非 ASCII 部分加稳定短哈希
- command_open 杀 session 的语义补注释说明（session 名现已按账号唯一）"
```

---

## Task 13: 会话新鲜度以 `saved_at` 为准

**Files:**
- Modify: `modules/utils/sessions/session_manager.py:108-121`（`_session_freshness_timestamp`）
- Modify: `modules/utils/sessions/session_manager.py:438-447`（`save_session` 保留旧 state 时仍刷新 `saved_at`）
- Modify: `modules/utils/sessions/session_manager.py:523-525`（`load_session` 读时回写）
- Test: `backend/tests/test_session_manager_protection.py`（扩充）

**背景（两处叠加）**：
1. `_session_freshness_timestamp` 取 `max(saved_at, last_used_at, created_at)`，而 `load_session` 每次读取都把 `last_used_at` 刷成当前时间 → **30 天过期机制实际永不触发**。实测 `Tiktok 1店` 的文件 mtime 是今日，但 `saved_at` 停在 2026-06-22。
2. `save_session` 在**保留 protected 旧 state** 时（`:424-436` 的 `selected_state = old_state`），仍然执行 `merged_metadata["saved_at"] = current_time`（`:447`）→ **人工会话的保存时间被自动回写刷新**。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_session_manager_protection.py` 末尾追加：

```python
def test_freshness_uses_saved_at_only(tmp_path):
    """新鲜度必须以 saved_at 为准，last_used_at 不得参与。"""
    from modules.utils.sessions.session_manager import _session_freshness_timestamp

    session = {
        "metadata": {"saved_at": 1000.0},
        "last_used_at": 9_999_999.0,
        "created_at": 500.0,
    }
    assert _session_freshness_timestamp(session) == 1000.0


def test_freshness_falls_back_to_created_at(tmp_path):
    from modules.utils.sessions.session_manager import _session_freshness_timestamp

    session = {"metadata": {}, "created_at": 500.0}
    assert _session_freshness_timestamp(session) == 500.0


def test_load_session_does_not_refresh_saved_at(tmp_path):
    """读一次会话不得刷新 saved_at。"""
    import json
    import time

    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager(base_path=tmp_path / "data" / "sessions")
    manager.save_session("shopee", "acct", {"cookies": [], "origins": []})
    path = manager.get_session_path("shopee", "acct")
    first = json.loads(path.read_text(encoding="utf-8"))
    saved_at = first["metadata"]["saved_at"]

    time.sleep(0.05)
    manager.load_session("shopee", "acct")

    second = json.loads(path.read_text(encoding="utf-8"))
    assert second["metadata"]["saved_at"] == saved_at
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_session_manager_protection.py -q -k "freshness or saved_at"
```

Expected: 至少 2 个 FAIL。

- [ ] **Step 3: 改 `_session_freshness_timestamp`**

把 `modules/utils/sessions/session_manager.py:108-121` 替换为：

```python
def _session_freshness_timestamp(session_data: Optional[Dict[str, Any]]) -> float:
    """会话的新鲜度时间戳。

    只认 ``metadata.saved_at``（真实保存时间）。``last_used_at`` 会在每次读取时刷新，
    参与计算会让过期机制永不触发（见 spec D7）。``saved_at`` 缺失时才回退 ``created_at``。
    """
    if not isinstance(session_data, dict):
        return 0.0

    metadata = session_data.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    saved_at = metadata.get("saved_at")
    if isinstance(saved_at, (int, float)):
        return float(saved_at)

    created_at = session_data.get("created_at")
    if isinstance(created_at, (int, float)):
        return float(created_at)

    return 0.0
```

- [ ] **Step 4: 保留旧 state 时不刷新 `saved_at`**

`modules/utils/sessions/session_manager.py` 的 `save_session`：在 `old_state is not None` 的分支里，需要知道「是否保留了旧 state」。改法：

先把 `:438-447` 附近改成：

```python
            current_time = time.time()
            # created_at 保留首次创建时间；会话新鲜度由 saved_at 驱动。
            created_at = current_time
            if existing_session and isinstance(existing_session.get("created_at"), (int, float)):
                created_at = float(existing_session.get("created_at"))

            kept_old_state = old_state is not None and selected_state is old_state

            merged_metadata: Dict[str, Any] = {}
            merged_metadata.update(old_metadata)
            merged_metadata.update(incoming_metadata)
            # 保留了旧 state 就不能刷新 saved_at，否则人工会话的保存时间会被自动回写刷掉
            if not kept_old_state:
                merged_metadata["saved_at"] = current_time
            merged_metadata["quality_score"] = selected_score
            merged_metadata["quality_gate_passed"] = bool(selected_gate)
```

- [ ] **Step 5: `load_session` 改为「内容没变就不回写」**

把 `modules/utils/sessions/session_manager.py:523-525` 替换为：

```python
            # 只在内容真正变化时回写。读一次会话不该刷新 saved_at（见 spec D7），
            # 但仍需要维护 last_used_at 以便排查最近一次使用时间。
            previous_last_used_at = session_data.get("last_used_at")
            session_data["last_used_at"] = time.time()
            if previous_last_used_at != session_data["last_used_at"]:
                _write_json_atomic(session_file, session_data)
```

> **注意**：这会让**每次读取都写文件**（因为 last_used_at 一定变）。若 `last_used_at` 的刷新本身不需要落盘，直接**删掉整段回写**：
> ```python
>             # 读取不改写磁盘：saved_at 与 last_used_at 都不因读取而变化（见 spec D7）
>             pass
> ```
> 二选一，取决于 `last_used_at` 是否被别处依赖。**实施者必须先 grep `last_used_at` 的所有使用点再决定**，并在提交说明里写明。

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_session_manager_protection.py backend/tests/test_session_storage_roots.py backend/tests/test_collection_session_reuse_contract.py -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add modules/utils/sessions/session_manager.py backend/tests/test_session_manager_protection.py
git commit -m "fix(会话): 新鲜度只认 saved_at，30 天过期机制恢复有效

- _session_freshness_timestamp 不再取 max(saved_at, last_used_at, created_at)
- load_session 读取不再把 last_used_at 刷成当前时间导致永不过期
- save_session 保留 protected 旧 state 时不再刷新 saved_at"
```

---

## Task 14: TikTok 持久 profile 模式下也要落 storage_state

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:2805-2822`（`_should_skip_post_login_session_persist`）
- Modify: `modules/apps/collection_center/executor_v2.py:255-309`（executor 版 bootstrap 补 TikTok 质量门禁）
- Test: `backend/tests/test_collection_executor_session_alignment.py`（扩充）

**背景**：
- `executor_v2.py:2822` 的 `_should_skip_post_login_session_persist` 在 `platform=='tiktok' and runtime_mode=='persistent_profile'` 时**不落 storage_state** → 人工巡店保存的会话在 TikTok 上拿不到。
- `executor_v2.py:255-309` 的 executor 版 bootstrap **缺** `modules/apps/collection_center/runtime_session.py:74-136` 的 TikTok 质量门禁 → 低质量会话会被当可用。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_collection_executor_session_alignment.py` 末尾追加：

```python
def test_manual_seeded_session_is_not_skipped_for_tiktok():
    """人工保存的会话在 TikTok 持久 profile 模式下也必须落盘。"""
    from modules.apps.collection_center.executor_v2 import _should_skip_post_login_session_persist

    assert not _should_skip_post_login_session_persist(
        platform="tiktok",
        runtime_mode="persistent_profile",
        session_metadata={"manual_seeded": True, "protected": True},
    )


def test_automatic_tiktok_persistent_profile_may_still_skip():
    """自动来源的 TikTok 持久 profile 保持原有跳过行为。"""
    from modules.apps.collection_center.executor_v2 import _should_skip_post_login_session_persist

    assert _should_skip_post_login_session_persist(
        platform="tiktok",
        runtime_mode="persistent_profile",
        session_metadata={},
    )
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_collection_executor_session_alignment.py -q -k "skip_post_login or manual_seeded"
```

Expected: `test_manual_seeded_session_is_not_skipped_for_tiktok` FAIL。

- [ ] **Step 3: 改 `_should_skip_post_login_session_persist`**

把 `modules/apps/collection_center/executor_v2.py:2805-2822` 替换为：

```python
def _should_skip_post_login_session_persist(
    platform: str,
    runtime_mode: str,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """TikTok 走持久 profile 时默认不落 storage_state。

    但**人工巡店保存的会话必须落盘**（spec D8）——否则采集侧读不到人工会话，
    自动化保存的会话保持原行为。
    """
    metadata = session_metadata if isinstance(session_metadata, dict) else {}
    if metadata.get("manual_seeded") or metadata.get("protected"):
        return False
    return platform == "tiktok" and runtime_mode == "persistent_profile"
```

> **实施者必须核对**真实函数签名并同步所有调用点（grep `_should_skip_post_login_session_persist`）。
> 若现签名没有 `session_metadata` 参数，需要新增并把会话元数据传进来。

- [ ] **Step 4: 补 executor 版 bootstrap 的 TikTok 质量门禁**

把 `modules/apps/collection_center/runtime_session.py:74-136` 的质量门禁逻辑（`tiktok_storage_state_meets_quality_gate` 等）复用到 `executor_v2.py:255-309` 的 bootstrap 路径：加载 storage_state 后，若平台是 TikTok 且质量门禁未过，则视为「无会话」，走重新登录。

> **实施者必须先读** `runtime_session.py:74-136` 的确切实现与导出符号，再在 executor 侧调用同一套函数，**不要复制一份**。

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_session_reuse_contract.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_executor_session_alignment.py
git commit -m "fix(采集): 人工保存的会话在 TikTok 持久 profile 模式下也落盘

- _should_skip_post_login_session_persist 对 manual_seeded / protected 会话不再跳过
- executor 版 bootstrap 补上 runtime_session 的 TikTok 质量门禁（原先只有 runtime 侧有）"
```

---

## Task 15: 内部标准名回填 + 账号管理页编辑入口

**Files:**
- Create: `backend/services/shop_internal_code_service.py`（新增：建议值生成 + 回填）
- Modify: `backend/domains/collection/routers/shop_accounts.py:121-154`（序列化）、`:363-405`（更新）
- Modify: `backend/schemas/`（Pydantic 契约）
- Modify: `frontend/src/domains/platform/views/AccountManagement.vue:428-445`（编辑表单）
- Test: `backend/tests/test_shop_internal_code.py`（新建）

**业务约定（spec §11.1 第 2 条）**：内部标准名 = `FIORO_SG` / `FIORO_MY` / `FIORO_PH` 形式，**同平台同区域多主账号冲突时**才追加主账号短标识（`FIORO_MY_T1`）。标准名**不参与数据匹配**。

**建议值生成规则**（spec §4.1）：

```
大写化(store_name 去掉已知地区后缀) → 非字母数字转 _ → 去首尾 _ → 拼 "_" + shop_region
```

| `store_name` 形态 | 样例 | 处理 | 区域 | 建议值 |
|---|---|---|---|---|
| 带域名后缀 | `xhkj1.my` | 剥掉 `.my` | MY | `XHKJ1_MY` |
| 带括号 | `Malaysia(Flora Mall)` | 括号转 `_` | MY | `MALAYSIA_FLORA_MALL_MY` |
| 纯英文带空格 | `DAWIE Mall` | 空格转 `_` | MY | `DAWIE_MALL_MY` |
| 纯中文 | `xihong` | 原样 | （空） | `XIHONG` |

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_shop_internal_code.py`：

```python
from __future__ import annotations

from backend.services.shop_internal_code_service import suggest_internal_code


def test_suggest_strips_known_region_suffix():
    assert suggest_internal_code("xhkj1.my", "MY") == "XHKJ1_MY"
    assert suggest_internal_code("xhkj11.sg", "SG") == "XHKJ11_SG"


def test_suggest_handles_parentheses_and_spaces():
    assert suggest_internal_code("Malaysia(Flora Mall)", "MY") == "MALAYSIA_FLORA_MALL_MY"
    assert suggest_internal_code("DAWIE Mall", "MY") == "DAWIE_MALL_MY"


def test_suggest_handles_chinese():
    assert suggest_internal_code("西虹照明", "SG") == "西虹照明_SG"


def test_suggest_is_deterministic():
    a = suggest_internal_code("DAWIE Mall", "MY")
    b = suggest_internal_code("DAWIE Mall", "MY")
    assert a == b
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_shop_internal_code.py -q
```

Expected: FAIL（模块不存在）。

- [ ] **Step 3: 新建服务**

创建 `backend/services/shop_internal_code_service.py`：

```python
"""内部标准名（internal_code）的建议值生成与冲突消歧。

内部标准名是「给人看的唯一标识」，例如 FIORO_SG / FIORO_MY / FIORO_PH。
它**不参与数据匹配**（匹配只走平台 + 主账号 + 原始导出标签 + 区域），
见 docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md。
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# 已知的地区后缀（小写），从店铺名尾部剥离，避免重复拼接区域码
_KNOWN_REGION_SUFFIXES = (
    "my", "sg", "ph", "vn", "th", "tw", "id", "br", "mx", "cl", "co", "ar",
    "uk", "de", "fr", "it", "es", "jp", "kr", "us", "ca", "au",
)

_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def suggest_internal_code(
    store_name: str,
    shop_region: Optional[str] = None,
    *,
    main_account_id: Optional[str] = None,
    taken: Optional[Iterable[str]] = None,
) -> str:
    """按 店铺名 + 区域 生成内部标准名建议值。

    Args:
        store_name: 平台侧真实店名
        shop_region: 区域码，例如 ``MY``
        main_account_id: 主账号 ID，仅在冲突时用于追加短标识
        taken: 已占用的标准名集合，用于消歧

    Returns:
        建议的标准名，例如 ``FIORO_SG``
    """
    base = str(store_name or "").strip()
    base = _strip_region_suffix(base)
    code = _NON_ALNUM_RE.sub("_", base.upper()).strip("_")
    if not code:
        code = "SHOP"

    region = str(shop_region or "").strip().upper()
    candidate = f"{code}_{region}" if region else code

    used = {str(item) for item in (taken or [])}
    if candidate not in used:
        return candidate

    # 同平台同区域多主账号冲突 -> 追加主账号短标识
    suffix = _main_account_short_id(main_account_id)
    if suffix:
        alternate = f"{candidate}_{suffix}"
        if alternate not in used:
            return alternate

    return candidate


def _strip_region_suffix(store_name: str) -> str:
    """剥离店铺名尾部已知的地区域名后缀，例如 ``xhkj1.my`` -> ``xhkj1``。"""
    text = store_name.strip()
    if "." not in text:
        return text
    head, _, tail = text.rpartition(".")
    if tail.lower() in _KNOWN_REGION_SUFFIXES and head:
        return head
    return text


def _main_account_short_id(main_account_id: Optional[str]) -> str:
    """主账号 ID -> 短标识，例如 ``Tiktok 1店`` -> ``T1``、``a@b.com`` -> ``AB``。"""
    text = str(main_account_id or "").strip()
    if not text:
        return ""
    if "@" in text:
        return "".join(ch for ch in text.split("@")[0].upper() if ch.isalnum())[:2] or "M1"
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return f"T{digits}"
    return "".join(ch for ch in text.upper() if ch.isalnum())[:2] or "M1"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_shop_internal_code.py -q
```

Expected: PASS。

- [ ] **Step 5: 回填存量标准名**

写一次性回填（**遵循"不新增根目录临时脚本"约束** —— 放到 `backend/services/` 的一个可重复执行的函数里，由管理接口或一次性调用触发）：

```python
async def backfill_internal_codes(db: AsyncSession) -> dict[str, int]:
    """回填存量店铺账号的内部标准名。

    规则：同平台内保证唯一；冲突时追加主账号短标识。
    已人工填写过 internal_code 的记录不动。
    """
```

实现要求：
- 只处理 `internal_code IS NULL` 的记录；
- 同平台分组，按 `shop_region` + `main_account_id` 排序，逐个生成并检查唯一性，冲突则追加短标识；
- 回填结果写入 `updated_by='system:backfill'`。

调用与核对：

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text('''select platform, count(*) total,
        count(internal_code) filled, count(distinct internal_code) distinct_codes
        from core.shop_accounts group by 1 order by 1''')):
        print(tuple(r))
"
```

Expected: 每个平台的 `distinct_codes == total`（同平台内唯一）。

- [ ] **Step 6: 后端 API 暴露建议值**

在 `backend/domains/collection/routers/shop_accounts.py`：

- `_serialize_shop_account`（:121-154）里加上 `internal_code` 与 `suggested_internal_code`；
- `update_shop_account`（:363-405）接受 `internal_code`，做**同平台唯一性校验**，冲突返回 409 并给出冲突详情（哪个店占用了这个名字）。

Pydantic 契约放 `backend/schemas/`，不要写在 router 里。

- [ ] **Step 7: 前端编辑入口**

在 `frontend/src/domains/platform/views/AccountManagement.vue`：

- 表格列（:337-355）加一列「内部标准名」，展示 `internal_code`，为空时显示建议值的灰色提示；
- 编辑表单（:428-445）加一行「内部标准名」，输入框带建议值 placeholder，用户可改；
- 同平台重名时展示后端返回的冲突详情。

- [ ] **Step 8: 测试 + 构建**

```bash
python -m pytest backend/tests/test_shop_internal_code.py backend/tests/test_shop_account_aliases_api.py -q
cd frontend; npm run build
```

Expected: 测试 PASS；构建成功。

- [ ] **Step 9: 提交**

```bash
git add backend/services/shop_internal_code_service.py backend/domains/collection/routers/shop_accounts.py backend/schemas/ frontend/src/domains/platform/views/AccountManagement.vue backend/tests/test_shop_internal_code.py
git commit -m "feat(店铺身份): 新增内部标准名 internal_code 及账号管理页编辑入口

- 建议值规则：店铺名去掉已知地区后缀 -> 大写化 -> 非字母数字转 _ -> 拼 _ + 区域
- 同平台同区域多主账号冲突时追加主账号短标识（FIORO_MY_T1）
- 标准名只供人读，不参与数据匹配
- 存量 52 个店铺账号回填 internal_code，同平台内保证唯一"
```

---

## Task 16: 改名联动（一次改名，三处同步，老数据不断）

**Files:**
- Modify: `backend/domains/collection/routers/shop_accounts.py:363-405`（`update_shop_account`）
- Modify: `backend/domains/collection/routers/shop_account_aliases.py:297-307`（409 判定放宽）、`:164-180`（`_clear_primary_aliases`）
- Modify: `backend/services/shop_sync_service.py:83-103`（`core.platform_accounts.store_name` 同步）
- Test: `backend/tests/test_shop_rename_flow.py`（新建）

**业务背景（spec §11.1 第 1 条 + D15 + D17）**：

平台侧真实店名**最终都要改**（`DAONE Mall` → `FIORO`）。不改未来会有分歧：同一个店在库里出现两个名字，老数据认旧名、新数据认新名，数据分裂。

所以改名必须是一次**联动操作**，六个步骤缺一不可：

1. **唯一性校验**：同平台 `internal_code` 唯一；同主账号 `store_name` 唯一。
2. **旧名转曾用名**：把旧 `store_name` 写入别名表（`is_active=true`, `is_primary=false`, `alias_type='former_name'`）→ **老数据继续命中同一个店**。
3. **新名接管**：新 `store_name` 写入别名表并置 `is_primary=true`；原主别名降为 `is_primary=false`、`is_active` 保持 True。
4. **同步 `core.platform_accounts.store_name`** → 否则 `dim_shops` 会被打回旧名。
5. **同步 `internal_code`**（若随之改动）。
6. **入刷新队列** → 触发**一次**归属重算（必要，因为归属路径要重算）。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_shop_rename_flow.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = REPO_ROOT / "backend" / "domains" / "collection" / "routers" / "shop_accounts.py"


def test_update_shop_account_has_rename_linking():
    """改名必须走联动流程，不能是裸 setattr。"""
    text = ROUTER.read_text(encoding="utf-8")
    body = text.split("async def update_shop_account", 1)[1].split("\nasync def ", 1)[0]
    assert "former_name" in body, "改名流程没有写曾用名"
    assert "is_primary" in body, "改名流程没有处理主别名接管"
    assert "platform_accounts" in body, "改名流程没有同步 core.platform_accounts"
    assert "setattr" not in body, "update_shop_account 仍是裸 setattr"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_shop_rename_flow.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现改名联动**

在 `backend/domains/collection/routers/shop_accounts.py` 里新增一个内部函数（放在 router 模块内或抽到 `backend/services/`，二选一，但**只留一份**）：

```python
async def _apply_store_name_rename(
    db: AsyncSession,
    shop_account: ShopAccount,
    new_store_name: str,
    *,
    operator: Optional[str] = None,
) -> None:
    """执行一次改名联动（spec D17）。

    顺序固定：
      1. 旧名转曾用名（别名表 is_active=true, is_primary=false）
      2. 新名写入别名表并接管 is_primary
      3. 同步 core.platform_accounts.store_name
      4. 同步 internal_code（若随之改动）
      5. 入刷新队列
    """
    platform = (shop_account.platform or "").strip().lower()
    old_store_name = (shop_account.store_name or "").strip()
    new_store_name = (new_store_name or "").strip()
    if not new_store_name or new_store_name == old_store_name:
        return

    # 1) 旧名转曾用名
    await _upsert_shop_alias(
        db,
        shop_account=shop_account,
        alias_value=old_store_name,
        alias_type="former_name",
        is_primary=False,
        is_active=True,
    )

    # 2) 新名接管主别名
    await _upsert_shop_alias(
        db,
        shop_account=shop_account,
        alias_value=new_store_name,
        alias_type="primary",
        is_primary=True,
        is_active=True,
    )

    # 3) 同步旧表
    await sync_platform_account_store_name(db, platform, shop_account.shop_account_id, new_store_name)

    # 4) 落库
    shop_account.store_name = new_store_name
    if operator:
        shop_account.updated_by = operator

    # 5) 刷新队列（一次）
    await _enqueue_shop_identity_refresh(changed_fields=["store_name", "alias"])
```

要求：
- `_upsert_shop_alias` 必须处理「该别名已存在且属于别的店」的情况 → 冲突则报 409，**不静默覆盖**；
- 唯一约束 `(platform, alias_normalized, shop_region, is_active)`（第一批 Task 5 已建）保证同平台同区域同别名不会重复；
- 若旧名与新名规范化后相同（如 `DAONE Mall` → `DAONE MALL`），跳过别名写入，只改 `store_name`（避免撞唯一约束）。

- [ ] **Step 4: `update_shop_account` 改用联动流程**

把 `backend/domains/collection/routers/shop_accounts.py:363-405` 的裸 `setattr` 改为：

```python
    if "store_name" in payload and payload["store_name"] != shop_account.store_name:
        # 同主账号下 store_name 唯一
        await _assert_store_name_unique_in_main_account(
            db, shop_account.main_account_id, payload["store_name"], exclude_id=shop_account.id
        )
        await _apply_store_name_rename(db, shop_account, payload["store_name"], operator=current_user)
    else:
        for field in editable_fields:
            if field in payload:
                setattr(shop_account, field, payload[field])
```

- [ ] **Step 5: 别名应用级约束放宽（D16）**

`backend/domains/collection/routers/shop_account_aliases.py:297-307` 的 409 判定从「同平台同别名已有 active 记录」放宽为「同平台同别名**同区域**已有 active 记录」。

同时 `_clear_primary_aliases`（:164-180）保持现状：**旧别名仅降 `is_primary`，`is_active` 仍为 True**（曾用名机制依赖这一点）。

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_shop_rename_flow.py backend/tests/test_shop_account_aliases_api.py backend/tests/test_shop_internal_code.py -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 端到端验证改名（用 live 库的只读副本思路）**

**不要在 live 库上直接试改名。** 在测试库/快照库上：

```bash
python -m pytest backend/tests/test_shop_rename_flow.py -q -k "end_to_end"
```

> 若还没有端到端用例，在本 Step 补一个：用 `AsyncSession` + 事务回滚（`async with db.begin(): ... raise Rollback`）模拟一次改名，断言：
> - 旧名在别名表里新增了一条 `is_primary=false, is_active=true, alias_type='former_name'` 的记录；
> - 新名成为 `is_primary=true` 的记录；
> - `core.platform_accounts.store_name` 已同步；
> - 刷新队列入队 1 次。

- [ ] **Step 8: 提交**

```bash
git add backend/domains/collection/routers/shop_accounts.py backend/domains/collection/routers/shop_account_aliases.py backend/services/shop_sync_service.py backend/tests/test_shop_rename_flow.py
git commit -m "feat(店铺身份): 改名走联动流程，老数据不断、新数据不串

- 改名固定六步：唯一性校验 -> 旧名转曾用名 -> 新名接管主别名
  -> 同步 core.platform_accounts.store_name -> 同步 internal_code -> 入刷新队列一次
- 曾用名是别名表里 is_primary=false 且 is_active=true 的记录，仍参与匹配
- 别名应用级 409 从「同平台同别名」放宽为「同平台同别名同区域」"
```

---

## 17. 第二批总验收

- [ ] **Step 1: 跑全量相关测试**

```bash
python -m pytest backend/tests/test_pwcli_session_naming.py backend/tests/test_session_manager_protection.py backend/tests/test_session_storage_roots.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_shop_internal_code.py backend/tests/test_shop_rename_flow.py backend/tests/test_shop_account_aliases_api.py backend/tests/test_shop_identity_schema_migration.py backend/tests/test_alias_normalization_consistency.py backend/tests/data_pipeline/test_shop_identity_resolution_sql.py -q
```

Expected: 全部 PASS。

- [ ] **Step 2: 核对 spec 第二批验收项**

| 验收项 | 验证方式 | 结果 |
|---|---|---|
| A11 会话新鲜度 | Task 13 Step 1/2 | |
| A12 持久化口径 | Task 14 Step 1/2 | |
| A13 改名联动 | Task 16 Step 1/7 | |
| B1 一账号一窗口 | Task 12 Step 5 + 手工开两个账号的窗口 | |
| B2 账号标识唯一 | Task 12 Step 5 + 磁盘核对 | |
| B3 曾用名 | Task 16 Step 7 | |
| B4 标准名 | Task 15 Step 5/6/7 | |
| B5 改名后自动重认 | 改名一个真实店铺后重新采集，比对 `semantic.fact_orders_atomic` 的归属 | |

- [ ] **Step 3: 验证改名不塌缩（关键）**

在一个真实店铺上做一次改名演练（**先在快照库**，确认无误后再在生产库做），然后核对：

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text(\"select shop_id, count(*) from semantic.fact_orders_atomic where platform_code='tiktok' group by 1 order by 2 desc\")):
        print(tuple(r))
"
```

Expected: 改名**前后各店的行数一致**（老数据通过曾用名继续命中同一店），`unknown` 不增加。

- [ ] **Step 4: 同步镜像并合入**

按 `docs/guides/RELEASE_CHECKLIST.md` 与 `scripts/sync_main_mirrors.ps1` 走流程。**不要直接 push main。**

- [ ] **Step 5: 更新 plan 完成状态**

在 `docs/superpowers/plans/STATUS.md` 记录本计划已完成。

---

## 18. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| Task 16 改名触发一次 raw 层全量重算 | 耗时长 | 这是必要的（归属路径确实要重算）；重算只发生一次；上线前在快照库演练 |
| Task 16 别名写入与既有别名冲突 | 改名失败 | 冲突报 409 并指出冲突店铺，不静默覆盖 |
| Task 15 存量回填产生重复标准名 | 唯一约束报错 | 回填按平台分组 + 冲突追加主账号短标识；回填前后各跑一次唯一性核对 |
| Task 12 slugify 规则变更导致历史 session 名对不上 | 旧窗口找不到 | 旧 session 名只影响「复用同一次窗口」，不影响已保存的 storage_state（按账号目录走） |
| Task 13 新鲜度口径变更让一批旧会话被判过期 | 需重新登录一次 | 属预期效果；上线前先统计有多少会话会因此过期并告知运营 |

**回滚**：每个 Task 独立提交，`git revert <commit>` 即可。Task 15 / 16 涉及数据库数据，回滚需要配套的数据订正脚本。

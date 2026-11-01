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
| §4.1 内部标准名 + D10a | Task 15 | B4 |
| D15 曾用名 / D16 别名唯一性预检 / D17 改名联动 | Task 16 | A13 B3 B5 |
| **D10b 区域感知匹配** | Task 17 | B5 |

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
>
> **必查项必须覆盖 open 与 save 两条路径**：
> - **open** 路径：`scripts/pwcli_inspection_panel.py:122-123` 与 `scripts/pwcli_helpers.ps1:451-457` —— 现状**已**带 `-WorkTag`。
> - **save** 路径：`scripts/pwcli_inspection_panel.py:129-134` 与 `scripts/pwcli_helpers.ps1:479-485` —— **第一批 Task 2 的 Step 5b 已经补上 `-WorkTag`**（若第一批已完成，这里只需回归确认）。
>   漏了 save 路径 → 人工会话保存仍然落回 session `"default"` → A12、B1 的业务前提不成立。
>
> **核对命令**：`grep -n "WorkTag" scripts/pwcli_inspection_panel.py scripts/pwcli_helpers.ps1`
> → 必须同时看到 open 分支与 save 分支都带 `-WorkTag`。

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_session_naming.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_pwcli_helpers_session_targeting.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 核对磁盘上没有因旧 slug 产生的冲突痕迹**

**slug 塌缩真正落在 session 名与工作目录上，不在 profile 目录。**

```bash
# 1) 会话目录（session 名）
Get-ChildItem output/playwright/.pwcli_native/sessions -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*account*' } | Select-Object FullName

# 2) 工作目录（work tag）
Get-ChildItem output/playwright/work -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*account*' } | Select-Object FullName
```

Expected:
- **「目录不存在」也是合法结论** —— 当前工作区可能根本没有 `output/playwright`（该目录按需生成，通常不入库）。
  → 在提交说明里如实写「当前工作区无历史遗留」即可，**不要**为了让命令有输出而去造目录。
- 若存在 `*-account-inspect` 之类的目录 → 说明历史上有账号塌成了同一个 slug，记录下来交业务确认
  （**不要在本 Task 删**，清理属 spec §10 的独立任务）。

> **⚠ 别去 `profiles/` 找**：按账号的 profile 目录在 `<repo>/profiles/<platform>/<safe_token>`，
> 而 `session_manager_safe_token`（`modules/utils/pwcli_native.py:136-139`）用的是 `str.isalnum()` ——
> **中文会被保留**（实测 `profiles/妙手erp` 存在）→ 那里**不会出现**名为 `account` 的目录。

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
def test_freshness_uses_saved_at_only():
    """新鲜度必须以 saved_at 为准，last_used_at 不得参与。"""
    from modules.utils.sessions.session_manager import _session_freshness_timestamp

    session = {
        "metadata": {"saved_at": 1000.0},
        "last_used_at": 9_999_999.0,
        "created_at": 500.0,
    }
    assert _session_freshness_timestamp(session) == 1000.0


def test_freshness_falls_back_to_created_at():
    """saved_at 缺失时才回退 created_at（护栏：修复后仍须成立）。"""
    from modules.utils.sessions.session_manager import _session_freshness_timestamp

    session = {"metadata": {}, "created_at": 500.0}
    assert _session_freshness_timestamp(session) == 500.0


def test_protected_session_keeps_saved_at_when_overwritten(tmp_path):
    """protected 人工会话被自动 state 覆盖时，saved_at 不得被刷新（spec D7）。"""
    import json
    import time

    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager(base_path=tmp_path / "data" / "sessions")
    manager.save_session(
        "shopee",
        "acct",
        {"cookies": [{"name": "sid", "value": "v"}], "origins": []},
        metadata={"manual_seeded": True, "protected": True},
    )
    path = manager.get_session_path("shopee", "acct")
    saved_at = json.loads(path.read_text(encoding="utf-8"))["metadata"]["saved_at"]

    time.sleep(0.05)
    # 自动来源、质量更低的 state 覆盖 -> 保留旧 state，且 saved_at 不得刷新
    manager.save_session("shopee", "acct", {"cookies": [], "origins": []})

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["metadata"]["saved_at"] == saved_at, "protected 会话的 saved_at 被自动回写刷新了"


def test_expired_session_is_rejected_even_when_recently_read(tmp_path):
    """saved_at 过期时，即使 last_used_at 是现在，也必须判为过期。"""
    import json
    import time

    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager(base_path=tmp_path / "data" / "sessions")
    manager.save_session(
        "shopee",
        "acct",
        {"cookies": [{"name": "sid", "value": "v"}], "origins": []},
    )
    path = manager.get_session_path("shopee", "acct")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata"]["saved_at"] = time.time() - 40 * 86400
    payload["last_used_at"] = time.time()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert manager.load_session("shopee", "acct", max_age_days=30) is None
```

> **关于「Expected: FAIL」的准确说法**（实测）：
> - `test_freshness_uses_saved_at_only` → **今天 FAIL**（现状取 max，含 `last_used_at`）✅
> - `test_expired_session_is_rejected_even_when_recently_read` → **今天 FAIL**（现状 `last_used_at` 兜住了过期判定）✅
> - `test_protected_session_keeps_saved_at_when_overwritten` → **今天 FAIL**（现状 `save_session` 无条件刷新 `saved_at`）✅
> - `test_freshness_falls_back_to_created_at` → **今天 PASS**（护栏用例，修复后仍须成立）
>
> 原来那条 `test_load_session_does_not_refresh_saved_at` **今天就 PASS**（`load_session` 只改 `last_used_at`，
> 从不碰 `metadata.saved_at`），守不住任何东西 → **已删除**，换成上面两条真正能区分新旧行为的用例。

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_session_manager_protection.py -q -k "freshness or saved_at or expired"
```

Expected: **3 FAIL + 1 PASS**（`test_freshness_falls_back_to_created_at` 是护栏，本就 PASS）。

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

> **注意**：两个候选实现都不改 `saved_at` → 上面的测试无法区分；而 `last_used_at` 确实被
> `session_manager.py:668-686`（`get_session_info` → `last_used_date` 展示）消费。
> **默认选「保留回写」**（只把 `last_used_at` 刷新，不动 `saved_at`）——
> 这样既满足 D7，又保留「最近一次使用时间」的展示语义。
> 若实施者改选「删掉整段回写」，**必须在提交说明里写明 `last_used_date` 展示语义的变化**，并同步
> `backend/tests/test_session_manager_protection.py` 里依赖 `last_used_at` 的断言。

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
- Modify: `modules/apps/collection_center/executor_v2.py:245-309`（executor 版 bootstrap，`def` 在 `:245`、`return` 在 `:309`、下一个顶层 def 在 `:312`；整份删掉，改为复用 runtime_session 的实现）
- Test: `backend/tests/test_collection_executor_session_alignment.py`（扩充）

**背景**：
- `executor_v2.py:2822` 的 `_should_skip_post_login_session_persist` 在 `platform=='tiktok' and runtime_mode=='persistent_profile'` 时**不落 storage_state** → 人工巡店保存的会话在 TikTok 上拿不到。
- `executor_v2.py:245-309` 的 executor 版 bootstrap **缺** `modules/apps/collection_center/runtime_session.py:74-136` 的 TikTok 质量门禁 → 低质量会话会被当可用。

- [ ] **Step 1: 写失败测试**

**先补文件头** —— 该文件当前**没有** `REPO_ROOT` 定义
（实测：文件里 `grep REPO_ROOT` 无匹配）。直接追加用例会 `NameError: name 'REPO_ROOT' is not defined`，
而 `NameError` 发生在断言**之前** → 就算把 executor 的重复 bootstrap 删掉了，这条用例照样红，
实施者会卡死在 Step 5「Expected: 全部 PASS」。

在 `backend/tests/test_collection_executor_session_alignment.py` 的 import 区补上：

```python
from pathlib import Path
```

并在 import 区之后加一行：

```python
REPO_ROOT = Path(__file__).resolve().parents[2]
```

> 该文件当前的 import 区是：`from __future__ import annotations` / `from unittest.mock import AsyncMock` /
> `import pytest` / `from modules.apps.collection_center.executor_v2 import ...` /
> `from modules.apps.collection_center.transition_gates import ...`。

然后在文件**末尾**追加：

```python
def test_manual_seeded_session_is_not_skipped_for_tiktok():
    """人工保存的会话在 TikTok 持久 profile 模式下也必须落盘。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    params = {
        "_runtime_session_mode": "persistent_profile",
        "session_metadata": {"manual_seeded": True, "protected": True},
    }
    assert not CollectionExecutorV2._should_skip_post_login_session_persist(
        platform="tiktok",
        params=params,
    )


def test_automatic_tiktok_persistent_profile_may_still_skip():
    """自动来源的 TikTok 持久 profile 保持原有跳过行为。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    params = {
        "_runtime_session_mode": "persistent_profile",
        "session_metadata": {},
    }
    assert CollectionExecutorV2._should_skip_post_login_session_persist(
        platform="tiktok",
        params=params,
    )


def test_non_tiktok_platform_is_never_skipped():
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    params = {"_runtime_session_mode": "persistent_profile", "session_metadata": {}}
    assert not CollectionExecutorV2._should_skip_post_login_session_persist(
        platform="shopee",
        params=params,
    )


def test_executor_does_not_duplicate_profile_bootstrap():
    """executor 侧不得再保留一份没有 TikTok 质量门禁的 profile bootstrap。

    现状：``runtime_session._bootstrap_session_from_profile_sync`` 有门禁，
    ``executor_v2`` 里又抄了一份没有门禁的 → 低质量 state 会被提升为正式会话。
    修法是复用 runtime_session 的实现，不是再抄第三份。
    """
    text = (
        REPO_ROOT / "modules" / "apps" / "collection_center" / "executor_v2.py"
    ).read_text(encoding="utf-8")
    assert "def _bootstrap_session_from_profile_sync" not in text, (
        "executor 侧仍有一份自己的 _bootstrap_session_from_profile_sync（缺 TikTok 质量门禁），"
        "应改为复用 runtime_session 的实现"
    )
```

> **A12 后半句「不会覆盖人工保存的 protected 会话」**已由 `backend/tests/test_session_manager_protection.py`
> 现有用例覆盖（`save_session` 的 `old_protected` 保护逻辑），本 Task 不重复造用例。

> **真实签名（已核验 `executor_v2.py:2805-2822`）**：`_should_skip_post_login_session_persist` 是 `CollectionExecutorV2` 上的 `@staticmethod`，签名为 `(*, platform: str, params: Dict[str, Any]) -> bool`。`runtime_mode` 由 `params["_runtime_session_mode"]` 或 `params["params"]["_runtime_session_mode"]` 推导，**不是独立入参**。两个调用点在 `executor_v2.py:1291` 与 `:3158`，都只传 `platform` 与 `params`。

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_collection_executor_session_alignment.py -q -k "skip_post_login or manual_seeded"
```

Expected: `test_manual_seeded_session_is_not_skipped_for_tiktok` FAIL。

- [ ] **Step 3: 让跳过判定能看见「人工保存」标记**

**3a. 把会话元数据带进 `params`。**

**好消息：`session_metadata` 其实已经有了，只是没进 `params`。**

- `executor_v2.py:1031`：`setattr(bundle, "session_metadata", dict(session_candidate.metadata or {}))` —— **RuntimeBundle 的 session_metadata 已经被填好了**（`session_candidate` 来自 `runtime_session.load_runtime_session_candidate`）。
- `executor_v2.py:1083-1095`：`session_metadata = getattr(runtime_bundle, "session_metadata", None)`，为空时回退 `SessionManager().get_session_metadata(...)`。
- `executor_v2.py:1122-1126`：runtime bundle 摘要里已经有 `session_manual_seeded` / `session_protected`。

→ 所以**不需要**改任何取数逻辑，只要在构造 `params` 之后补一行：

```python
params["session_metadata"] = getattr(runtime_bundle, "session_metadata", None) or {}
```

写入点（**实测 `params["reused_session"]` 只出现在 `executor_v2.py:591`**；`_runtime_session_mode` 的写入点是 `:1998` / `:2104` / `:5835`）：
- `:591`（`_open_runtime_bundle` 里，`params` 已由 `_build_runtime_task_params` 在 `:583` 构造完）
- `:1998` / `:2104`（两处 `params["main_account_id"] = session_owner_id` 附近）
- `:5835`（`params["main_account_id"] = session_owner_id` 之后）

> **实施者必须先 `grep -n "_runtime_session_mode" modules/apps/collection_center/executor_v2.py`** 复核一遍 —— 漏一个点，那个分支就拿不到人工标记。
> 如果 `params` 是在没有 `runtime_bundle` 的分支构造的，就退化成 `{}`（等价于"不是人工会话"）。

**3b. 改判定逻辑（签名不变，两个调用点不用改）。**

把 `executor_v2.py:2805-2822` 替换为：

```python
    @staticmethod
    def _should_skip_post_login_session_persist(
        *,
        platform: str,
        params: Dict[str, Any],
    ) -> bool:
        """TikTok 走持久 profile 时默认不落 storage_state。

        但**人工巡店保存的会话必须落盘**（spec D8）—— 否则采集侧读不到人工会话。
        自动来源的会话保持原有跳过行为。
        """
        normalized_platform = str(platform or "").strip().lower()
        nested_params = params.get("params") or {}
        runtime_mode = (
            str(
                params.get("_runtime_session_mode")
                or nested_params.get("_runtime_session_mode")
                or ""
            )
            .strip()
            .lower()
        )
        if not (normalized_platform == "tiktok" and runtime_mode == "persistent_profile"):
            return False

        metadata = params.get("session_metadata")
        if not isinstance(metadata, dict):
            metadata = nested_params.get("session_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        if metadata.get("manual_seeded") or metadata.get("protected"):
            return False
        return True
```

> **签名刻意保持 `(*, platform, params)`**：现有两个调用点（`executor_v2.py:1291` 与 `:3158`）不需要改动，减少回归面。

- [ ] **Step 4: executor 侧的 bootstrap 复用 runtime_session 的实现（补上 TikTok 质量门禁）**

**现状核实**：`executor_v2.py:245-309`（`def` 在 `:245`、`return` 在 `:309`、下一个顶层 `def` 在 `:312`）有**一份自己的** `_bootstrap_session_from_profile_sync`，
它从持久 profile 读出 storage_state 就直接 `save_session` —— **没有 TikTok 质量门禁**。

而 `modules/apps/collection_center/runtime_session.py:258-312` 的同名函数**有**门禁：

```python
    if str(platform or "").strip().lower() == "tiktok":
        if not tiktok_storage_state_meets_quality_gate(storage_state):
            logger.warning(
                "Skip promoting bootstrapped TikTok storage_state without seller-quality session (score=%s) for %s/%s",
                tiktok_storage_state_quality_score(storage_state),
                platform,
                account_id,
            )
            return {"storage_state": storage_state}
```

→ 这就是「executor 版 bootstrap 缺 TikTok 质量门禁」的真正成因：**两份重复实现，runtime 那份有门禁，executor 那份没有。**

**修法（优先 DRY，不要再抄第三份）**：

1. 删掉 `executor_v2.py:245-309` 的重复实现（`def` 在 `:245`、`return` 在 `:309`），**并同步改调用点**：
   `executor_v2.py:330` 现在调的是**本地那份**（`_bootstrap_session_from_profile_sync(...)`，无模块前缀），
   **不是** `runtime_session` 的实现 —— 全文 grep 确认 executor 内从未出现过
   `runtime_session._bootstrap_session_from_profile_sync`。
   → 改法：把 `:330` 的 lambda 改成调用 `runtime_session._bootstrap_session_from_profile_sync(...)`。
   **只删函数不改调用点会直接 `NameError`。**
2. 如果因为依赖方向不能直接删（`executor_v2` 顶层 import `runtime_session` 造成循环），就改成
   `from modules.apps.collection_center import runtime_session` 的**函数内延迟 import**，与 `executor_v2.py:2831` 的既有写法一致。
3. **无论走哪条路，都必须保证 TikTok 分支经过 `tiktok_storage_state_meets_quality_gate`**，
   低质量 state **不得**被 `save_session` 提升为正式会话。

> **不要**把门禁逻辑再抄一遍到 executor 侧 —— 那正是当前问题的成因。
> 现成符号：`runtime_session.tiktok_storage_state_meets_quality_gate`（`:104`）、`runtime_session.tiktok_storage_state_quality_score`（`:74`）。
> （`_wait_and_capture_high_quality_tiktok_session` 定义在 `executor_v2.py:1432`，它在**函数体内**的 `:1472` / `:1477` / `:1493` 用这两个符号，属于**另一条**路径 —— 登录后的捕获，不在本 Step 范围。）

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
- Create: `backend/services/shop_rename_service.py`（新增：改名联动 + `core.dim_shops` 展示名同步）
- Modify: `backend/domains/collection/routers/shop_accounts.py:121-154`（序列化）、`:363-405`（更新）
- Modify: `backend/schemas/shop_account.py`（`ShopAccountUpdate` / `ShopAccountResponse` 加 `internal_code`）
- Modify: `frontend/src/domains/platform/views/AccountManagement.vue:337-355`（表格列）、`:428-445`（编辑表单）、`:740-764`（`accountForm`）、`:1097-1104`（提交载荷）
- Modify: `frontend/src/stores/accounts.js:38-65`（**`buildShopAccountUpdatePayload` 的字段白名单** —— 不改这里，前端填的内部标准名会被静默丢弃）
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

Expected: **collection error**（不是用例 FAIL）—— `from backend.services.shop_internal_code_service import ...`
写在**模块级**，而该模块今天还不存在 → pytest 报
`ModuleNotFoundError: No module named 'backend.services.shop_internal_code_service'` 并**中断整轮收集**，
所以输出是 `ERROR` 而不是 `failed`。

> 若实施者希望看到"用例级 FAIL"，把 import 写进用例函数体内即可（第一批 Task 9 的 `resolve_file_identity`
> 就是这么写的，失败形态是 `ImportError: cannot import name ...`）。
> 两种写法都可以，**但必须知道今天看到的是 collection error**。

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

Expected: 每个平台 **`filled == total`（全部回填，没有 NULL）** 且 **`distinct_codes == filled`（同平台内唯一）**。

> **口径坑**：`count(distinct x)` **不统计 NULL**。若用 `distinct_codes == total` 判断，
> 只要有一行没回填就会**误报成「不唯一」**，而且按这个口径永远修不好。
> 正确判据是 `count(distinct internal_code) == count(internal_code)`
> —— 左边是去重后的非空值个数，右边是非空值总行数；两者相等 ⟺ 无 NULL 且唯一。

- [ ] **Step 6: 后端 API 暴露建议值**

`backend/schemas/shop_account.py`（**Pydantic 契约放这里，不要写在 router 里**）：

- `ShopAccountUpdate` 增加 `internal_code: Optional[str] = None`；
- `ShopAccountResponse` 增加 `internal_code: Optional[str]` 与 `suggested_internal_code: Optional[str]`。

`backend/domains/collection/routers/shop_accounts.py`：

- `_serialize_shop_account`（:121-154）里带上 `internal_code` 与 `suggested_internal_code`（后者由 `shop_internal_code_service.suggest_internal_code` 实时算，不落库）；
- `update_shop_account`（:363-405）接受 `internal_code`，做**同平台唯一性校验**，冲突返回 409 并给出冲突详情（哪个店占用了这个名字）。

> 读方向本来就通：`frontend/src/stores/accounts.js:8` 的 `normalizeShopAccount` 用 `...shopAccount` 展开，
> 后端返回即带出。**写方向才缺一环**，见 Step 7。

- [ ] **Step 7: 前端编辑入口（含 payload 白名单）**

**7a. 改 payload 构建器（不做这一步，表单里填的内部标准名会被静默丢弃）。**

`frontend/src/stores/accounts.js:38-65` 的 `buildShopAccountUpdatePayload` 用的是固定字段白名单：

```js
const fields = ['store_name','shop_region','shop_type','business_role','capabilities','enabled','notes']
```

`internal_code` 不在里面 → **前端填了也传不出去**。必须把它加进白名单。

**7b. 改页面。** 在 `frontend/src/domains/platform/views/AccountManagement.vue`：

- 表格列（:337-355）加一列「内部标准名」，展示 `internal_code`，为空时显示建议值的灰色提示；
- 编辑表单（:428-445）加一行「内部标准名」，输入框带建议值 placeholder，用户可改；
- `accountForm`（:740-764）加上 `internal_code` 初始值；
- 提交载荷（:1097-1104）是 `{ ...accountForm }` 整表提交 —— **确认 `internal_code` 在 `accountForm` 里**，否则会被整表覆盖掉；
- 同平台重名时展示后端返回的冲突详情。

> **必须验证**：`buildShopAccountUpdatePayload` 的白名单改完后，`AccountManagement.vue` 提交时
> `internal_code` 确实出现在请求体里。**这是 B4 能否落地的唯一卡点** —— 只改页面不改 store 不会生效。

- [ ] **Step 8: 测试 + 构建**

```bash
python -m pytest backend/tests/test_shop_internal_code.py backend/tests/test_shop_account_aliases_api.py -q
cd frontend; npm run build
```

Expected: 测试 PASS；构建成功。

- [ ] **Step 9: 提交**

```bash
git add backend/services/shop_internal_code_service.py backend/domains/collection/routers/shop_accounts.py backend/schemas/shop_account.py frontend/src/domains/platform/views/AccountManagement.vue frontend/src/stores/accounts.js backend/tests/test_shop_internal_code.py
git commit -m "feat(店铺身份): 新增内部标准名 internal_code 及账号管理页编辑入口

- 建议值规则：店铺名去掉已知地区后缀 -> 大写化 -> 非字母数字转 _ -> 拼 _ + 区域
- 同平台同区域多主账号冲突时追加主账号短标识（FIORO_MY_T1）
- 标准名只供人读，不参与数据匹配
- 前端 payload 白名单同步加入 internal_code，否则表单填了也传不出去
- 存量 52 个店铺账号回填 internal_code，同平台内保证唯一"
```

---

## Task 16: 改名联动（一次改名，三处同步，老数据不断）

**Files:**
- Modify: `backend/domains/collection/routers/shop_accounts.py:363-405`（`update_shop_account`）
- Modify: `backend/domains/collection/routers/shop_account_aliases.py:297-307`（409 判定放宽）、`:164-180`（`_clear_primary_aliases`）
- Create: `backend/services/shop_rename_service.py`（改名联动 + `core.dim_shops` 展示名同步）
- Test: `backend/tests/test_shop_rename_flow.py`（新建）

**业务背景（spec §11.1 第 1 条 + D15 + D17）**：

平台侧真实店名**最终都要改**（`DAONE Mall` → `FIORO`）。不改未来会有分歧：同一个店在库里出现两个名字，老数据认旧名、新数据认新名，数据分裂。

所以改名必须是一次**联动操作**，六个步骤缺一不可：

1. **唯一性校验**：同平台 `internal_code` 唯一；同主账号 `store_name` 唯一。
2. **旧名转曾用名**：把旧 `store_name` 写入别名表（`is_active=true`, `is_primary=false`, `alias_type='former_name'`）→ **老数据继续命中同一个店**。
3. **新名接管**：新 `store_name` 写入别名表并置 `is_primary=true`；原主别名降为 `is_primary=false`、`is_active` 保持 True。
4. **同步 `core.dim_shops.shop_name`** → 否则页面、绩效、提成里显示的还是旧名。
5. **同步 `internal_code`**（若随之改动）。
6. **入刷新队列** → 触发**一次**归属重算（必要，因为归属路径要重算）。

> **⚠ 同步目标是 `core.dim_shops`，不是 `core.platform_accounts`。**
> 已核验（live 库）：`core.platform_accounts` 是**主账号粒度**的旧表（11 行，`account_id` = 主账号 ID，`store_name` = 主账号名如 `Tiktok 1店`，`shop_id` 全为 NULL）。
> **改店铺名不应该改它** —— 那会把店铺名写回主账号名上。
> 真正需要同步的是 `core.dim_shops`（49 行，其中店铺粒度的行 `shop_id = tiktok_my_dawie_mall_local` / `xhkj1.my` 等，其 `shop_name` 已经等于 `core.shop_accounts.store_name`）。
> `core.dim_shops.shop_name` 被 `backend/domains/business/routers/hr_commission.py`、`target_management.py`、`backend/services/clearance_ranking_service.py`、`c_class_data_service.py` 等读取并展示 → 不同步就会显示旧名。
> `backend/services/shop_sync_service.py:83-103` 现有的是 `core.platform_accounts` → `core.dim_shops` 的同步（方向相反，粒度也不同），**不能直接复用**。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_shop_rename_flow.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = REPO_ROOT / "backend" / "domains" / "collection" / "routers" / "shop_accounts.py"
SERVICE = REPO_ROOT / "backend" / "services" / "shop_rename_service.py"


def test_rename_flow_is_wired():
    """改名必须走联动服务，且不得破坏现有的字段赋值与唯一性校验。

    注意：断言必须**跨文件**看「调用了具名服务 + 服务里做了什么」，
    不能在 ``update_shop_account`` 函数体内找字符串 —— 联动逻辑放在独立服务里，
    在函数体内找 ``former_name`` / ``dim_shops`` 永远找不到。
    """
    body = ROUTER.read_text(encoding="utf-8").split("async def update_shop_account", 1)[1].split("\nasync def ", 1)[0]

    # 1) 改名分支必须调用具名的联动服务
    assert "_apply_store_name_rename" in body, "update_shop_account 没有调用改名联动"

    # 2) 现有的通用赋值与 platform_shop_id 唯一性校验必须保留
    #    （前端每次编辑提交整个表单，改名分支若用 if/else 会把其它字段全丢掉）
    assert "setattr(record, field, value)" in body, "改名把原有的字段赋值分支弄丢了"
    assert "_assert_platform_shop_id_unique" in body, "改名把 platform_shop_id 唯一性校验弄丢了"

    # 3) 联动服务里必须有曾用名、主别名接管、dim_shops 同步
    assert SERVICE.exists(), "缺少改名联动服务 backend/services/shop_rename_service.py"
    service = SERVICE.read_text(encoding="utf-8")
    assert "former_name" in service, "改名联动没有写曾用名"
    assert "is_primary" in service, "改名联动没有处理主别名接管"
    assert "dim_shops" in service, "改名联动没有同步 core.dim_shops 展示名"
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
) -> None:
    """执行一次改名联动（spec D17）。

    顺序固定：
      1. 旧名转曾用名（别名表 is_active=true, is_primary=false）
      2. 新名写入别名表并接管 is_primary
      3. 同步 core.dim_shops.shop_name（展示用的维度表，店铺粒度）
      4. 落库 core.shop_accounts.store_name
      5. 入刷新队列（一次）
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

    # 3) 同步展示用的维度表（店铺粒度）
    await _sync_dim_shop_name(db, platform, shop_account.shop_account_id, new_store_name)

    # 4) 落库
    shop_account.store_name = new_store_name

    # 5) 刷新队列（一次）
    await _enqueue_shop_identity_refresh(
        db,
        shop_account=shop_account,
        changed_fields=["store_name", "alias"],
    )
```

> **同步目标说明**：第 3 步同步的是 **`core.dim_shops.shop_name`**（`platform_code = platform AND shop_id = shop_account_id`），
> **不是** `core.platform_accounts` —— 后者是主账号粒度的旧表（11 行，`store_name` = 主账号名），改店铺名不该动它。
> `_sync_dim_shop_name` 需要新建：找不到对应行时**不新建**，只记日志。
>
> **`_enqueue_shop_identity_refresh` 的真实签名**是 `(db, *, shop_account, changed_fields)`（`backend/domains/collection/routers/shop_accounts.py:209-213`），
> **必须**传 `db` 与 `shop_account=` —— 漏了会 TypeError。
>
> **`operator` 参数不存在**：现状 `update_shop_account` 写死 `record.updated_by = "system"`，改名沿用即可，不要另造参数。

要求：
- `_upsert_shop_alias` 必须处理「该别名已存在且属于别的店」的情况 → 冲突则报 409，**不静默覆盖**；
- 唯一约束 `(platform, alias_normalized, shop_region, is_active)`（第一批 Task 5 已建）保证同平台同区域同别名不会重复；
- 若旧名与新名规范化后相同（如 `DAONE Mall` → `DAONE MALL`），跳过别名写入，只改 `store_name`（避免撞唯一约束）。

- [ ] **Step 4: `update_shop_account` 改用联动流程**

**真实代码（已核验 `backend/domains/collection/routers/shop_accounts.py:363-405`）**：

```python
@router.put("/{shop_account_id}", response_model=ShopAccountResponse)
async def update_shop_account(
    shop_account_id: str,
    payload: ShopAccountUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    record = await _get_shop_account_or_404(db, shop_account_id)
    update_data = payload.model_dump(exclude_unset=True)
    ...
    for field, value in update_data.items():
        setattr(record, field, value)
    ...
    record.updated_by = "system"
    ...
    changed_identity_fields = [
        field for field in update_data.keys() if field in _SHOP_IDENTITY_FIELDS
    ]
    await _enqueue_shop_identity_refresh(
        db,
        shop_account=record,
        changed_fields=changed_identity_fields,
    )
```

要点（实施者必须按这个改，不要照抄本 Task 早期版本里的变量名）：

| 事实 | 说明 |
|---|---|
| 变量是 `update_data`，不是 `payload` | `payload` 是 Pydantic 模型，`update_data` 才是字段字典 |
| **没有** `editable_fields` | 现有实现是 `for field, value in update_data.items(): setattr(...)` 全量裸赋值 |
| **没有** `current_user` | 操作人写死 `record.updated_by = "system"` |
| **`_enqueue_shop_identity_refresh` 已经接上了** | `:400-404` 已调用，且 `_SHOP_IDENTITY_FIELDS`（`:42-47`）已包含 `store_name` → **改名本来就会触发一次刷新**。本 Task **不需要**新增刷新调用，只需保证改名走联动流程时 `changed_fields` 里带上 `store_name` |
| 刷新的目标是 `_SHOP_IDENTITY_REFRESH_TARGETS`（`:38-41`）= `semantic.fact_orders_monthly_atomic_mv` + `semantic.fact_analytics_monthly_atomic_mv` | 改 `fact_orders_atomic` 视图不在该列表里 —— 见下面的补充说明 |

改法（**先全量赋值，再对 store_name 走联动** —— 不要用 if/else 二选一）：

```python
    original_store_name = record.store_name

    # 1) 先按现有逻辑全量赋值（保留 platform_shop_id 唯一性校验与 capabilities 处理）
    for field, value in update_data.items():
        setattr(record, field, value)

    # 2) 再对 store_name 走改名联动
    #    注意：前端每次编辑提交整个表单（store_name 恒存在），
    #    若把改名做成 if/else，else 分支永远不走 -> 其它字段全部不落库。
    if "store_name" in update_data and update_data["store_name"] != original_store_name:
        await _assert_store_name_unique_in_main_account(
            db, record.main_account_id, update_data["store_name"], exclude_id=record.id
        )
        await _apply_store_name_rename(db, record, update_data["store_name"])
```

> **⚠ 为什么不能写成 if/else**：前端 `frontend/src/domains/platform/views/AccountManagement.vue:1097-1104`
> 提交的是 `{ ...accountForm }` 整表，而 `accountForm` 恒含 `store_name`。
> → `if "store_name" in update_data and ... != 原值` 一旦成立，`else` 分支被跳过，
> `shop_region / shop_type / business_role / capabilities / enabled / notes / platform_shop_id` **全部不落库**，
> 同时 `shop_accounts.py:373-379` 的 `_assert_platform_shop_id_unique` 也被绕过。
> → **必须先全量 setattr，再叠加改名联动。**

**补充（实施者必须处理）**：`_SHOP_IDENTITY_REFRESH_TARGETS` 目前只有两个 monthly 物化视图，而第一批 Task 7/8 改的是 `semantic.fact_orders_atomic`（VIEW）与 `semantic.fact_analytics_atomic`（VIEW）。改名后要保证**这三个视图的归属都被重算**：
- 两个 monthly 物化视图 → 现有 `_enqueue_shop_identity_refresh` 已覆盖（需 `REFRESH MATERIALIZED VIEW`）；
- 两个 VIEW → 改定义即生效，但**旧数据不会自动重算** → 需要在改名后显式触发一次 raw 层重建。
→ **实施者必须先确认 `RefreshQueueService.enqueue_refresh` 的实际重算范围**（`backend/services/data_pipeline/refresh_queue_service.py:44`），再决定是否需要把 `semantic.fact_orders_atomic` / `semantic.fact_analytics_atomic` 加进 `_SHOP_IDENTITY_REFRESH_TARGETS`。**这一条是 B5「改名后自动重认」能否成立的关键，不得跳过。**

- [ ] **Step 5: 别名唯一性的应用层友好预检（D16）**

> **先纠正一处误解**：现有代码里**只有一处** 409（`backend/domains/collection/routers/shop_account_aliases.py:301-307`），
> 它的语义是「**同一个店铺账号自己**已有主别名、且规范化值与新值不同 → 409」，
> 是**账号内**主别名唯一性 —— 代码里**不存在**跨账号的「同平台同别名」应用级检查。
>
> → 所以这一步**不是"放宽"**，而是**补一条友好预检**：
> 库层约束（第一批 Task 5 建的 `UNIQUE NULLS NOT DISTINCT (platform, alias_normalized, shop_region, is_active)`）
> 已经实现了 D16 的「同平台同别名同区域只能一条 active」。
> 应用层要做的是在写库前把这个约束翻译成人话，让运营知道「这个别名在这个区域已经被 X 店占用了」，
> 而不是抛数据库约束异常。

实现要求：

1. 在创建/认领别名前，用 `(platform, alias_normalized, shop_region, is_active=True)` 查一次；
   命中且属于**别的**店铺账号 → 409，错误信息带上占用方（店铺名 + 区域）。
2. `shop_region` 为 NULL 的别名（不限区域）**不与有区域的别名冲突** —— 与库层 `NULLS NOT DISTINCT` 语义一致：NULL 只与 NULL 冲突。
3. 现有的账号内主别名 409（`:301-307`）**保持不动**。
4. `_clear_primary_aliases`（:164-180）保持现状：**旧别名仅降 `is_primary`，`is_active` 仍为 True**（曾用名机制依赖这一点）。

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
> - **`core.dim_shops` 里对应行的 `shop_name` 已更新为新名**（`platform_code` + `shop_id` 定位）；
> - `core.shop_accounts.store_name` 已更新；
> - 刷新队列入队 1 次；
> - **同一次 payload 里的其它字段（`shop_region` / `platform_shop_id` / `enabled` 等）仍然落库** —— 这是「先全量 setattr 再联动」的保护用例。

- [ ] **Step 8: 提交**

```bash
git add backend/domains/collection/routers/shop_accounts.py backend/domains/collection/routers/shop_account_aliases.py backend/services/shop_rename_service.py backend/tests/test_shop_rename_flow.py
git commit -m "feat(店铺身份): 改名走联动流程，老数据不断、新数据不串

- 改名固定六步：唯一性校验 -> 旧名转曾用名 -> 新名接管主别名
  -> 同步 core.dim_shops.shop_name -> 同步 internal_code -> 入刷新队列一次
- 曾用名是别名表里 is_primary=false 且 is_active=true 的记录，仍参与匹配
- 先全量 setattr 再叠加改名联动，避免前端整表提交时丢掉其它字段
- 别名唯一性补一条应用层友好预检（库层约束已由第一批落地）"
```

---

## Task 17: 区域感知匹配（D10b —— 让同名品牌店按站点分流）

**Files:**
- Modify: `sql/semantic/shop_identity_resolution_candidates.sql`（`alias_match` 分支带出别名的 `shop_region`；并先在 `active_shop_accounts` CTE 里补出 `candidate_shop_region`）
- 前置（**第一批已完成**）：`backend/services/data_pipeline/refresh_registry.py` 里
  `PIPELINE_DEPENDENCIES["semantic.fact_orders_atomic"]` 已声明
  `["semantic.shop_identity_resolution_candidates"]` —— 没有这条依赖边，
  本 Task 的 `rebuild_views.py` 会先重建 `fact_orders_atomic`、再建候选视图 → 直接失败
- Modify: `sql/semantic/orders_atomic.sql`（**`cleaned` 层(:280) 加 `source_region`** —— 该层的 `source_site` 已是真实输入列）
- Modify: `sql/semantic/orders_monthly_atomic_mv.sql`（`mapped_monthly_orders`(:19) 新算 `source_site` → `normalized_monthly_orders`(:114) 加 `source_region`）
- **不改** `sql/semantic/analytics_atomic.sql` / `sql/semantic/analytics_monthly_atomic_mv.sql`
  （raw 里没有站点来源；Step 1 的反向护栏会断言这两个文件里**不得**出现 `AS source_region`）
- Test: `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py`（扩充）
- Test: `backend/tests/test_semantic_ambiguous_identity_sql.py`（**改写第一批留下的护栏用例** —— 见 Step 2）

**背景**：第一批 D10a 给别名表加了 `shop_region` 列与新约束 —— 于是同一个 `FIORO` 可以分别注册给 SG/MY/PH 三个店。
但**匹配还只看 `(platform, alias_normalized)`** → `FIORO` 会同时命中三个店 → 落 `unknown` + `ambiguous_shop_label`。
**这是安全状态（不静默错配），但认不出店。** D10b 就是让区域参与匹配，把它变成正确归属。

**已核实的事实（实施者照此做，不要另造映射）**：

| 事实 | 位置 |
|---|---|
| raw 数据里的站点是中文，且 100% 覆盖、改名后不变 | `b_class.fact_tiktok_orders_monthly.raw_data->>'站点'`（菲律宾/新加坡/马来/…） |
| `orders_atomic.sql` 已经把站点抽出来了 | `sql/semantic/orders_atomic.sql:62` `source_site` |
| 现成的「站点 → 国家码」映射 | `backend/domains/collection/routers/account_alignment.py:796-805` 的 `site_map`（菲律宾→ph、新加坡→sg、马来/马来西亚→my、泰国→th、越南→vn、印尼→id、巴西→br） |
| 店铺侧区域是**大写** | `core.shop_accounts.shop_region` = `MY` / `PH` / `SG`（与 `site_map` 的小写差一个 `upper()`） |

- [ ] **Step 1: 写失败测试**

在 `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py` 末尾追加：

```python
def test_sql_assets_map_site_to_region():
    """语义层必须把 raw 的中文站点映射成店铺区域码（大写）。

    只有**有站点来源**的两条 orders 路径需要区域映射 ——
    analytics 的 raw 里既没有站点也没有店铺标签
    （实测 `b_class.fact_tiktok_analytics_monthly` 1263 行，站点 0 / 店铺 0），
    给它硬造一个区域字段只会多一个永远是 NULL 的列。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for rel in (
        "sql/semantic/orders_atomic.sql",
        "sql/semantic/orders_monthly_atomic_mv.sql",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "source_region" in text, f"{rel} 没有把站点映射成区域"
        assert "'菲律宾'" in text, f"{rel} 缺少站点映射表"


def test_site_map_matches_python_side():
    """SQL 的站点→区域映射必须与 `account_alignment.py` 的 `site_map` **逐项**一致。

    只比 key→value，**不比 fallback** —— 两侧 fallback 的大小写本来就不同，是有意的：
    Python 侧（`account_alignment.py:806`）产出小写，只用于生成建议 id（`:820-821`）；
    SQL 侧产出大写，要与 `core.shop_accounts.shop_region`（实测存大写 `MY`/`PH`/`SG`）比较。

    这条断言让「只锁 8 项映射」真的成为事实，而不是靠文档承诺。
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]

    src = (root / "backend" / "domains" / "collection" / "routers"
           / "account_alignment.py").read_text(encoding="utf-8")
    site_map = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "site_map" for t in node.targets
        ):
            site_map = ast.literal_eval(node.value)
            break
    assert site_map, "account_alignment.py 里找不到 site_map"

    for rel in (
        "sql/semantic/orders_atomic.sql",
        "sql/semantic/orders_monthly_atomic_mv.sql",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        for site, code in site_map.items():
            assert f"WHEN '{site}' THEN '{code.upper()}'" in text, (
                f"{rel} 缺少站点映射 {site} -> {code.upper()}"
                f"（与 account_alignment.py 的 site_map 不一致）"
            )


def test_analytics_assets_do_not_get_region_column():
    """反向护栏：两条 analytics 路径**不得**出现区域列。

    它们没有站点来源（raw 里 `站点` / `店铺` 都是 0 行），
    加了只会是永远 NULL 的列，还会让"区域感知匹配"的适用范围变得含糊。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for rel in (
        "sql/semantic/analytics_atomic.sql",
        "sql/semantic/analytics_monthly_atomic_mv.sql",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        # 只匹配「真的定义了列」的形态，避免一句解释性注释就误红
        assert not re.search(r"AS\s+source_region\b", text, re.I), (
            f"{rel} 不该有区域列（raw 里没有站点来源）"
        )
        assert not re.search(r"WHEN\s+'[^']+'\s+THEN\s+'[A-Z]{2}'", text), (
            f"{rel} 不该有站点映射表"
        )
```

- [ ] **Step 2: 更新第一批留下的护栏用例（不做这一步，第二批落地后裸 `pytest` 必红）**

第一批的 `backend/tests/test_semantic_ambiguous_identity_sql.py::test_candidate_view_untouched_in_batch1`
断言候选视图里**没有** `shop_region` —— 本 Task 要给视图加区域列，**该断言必然失败**。

把那条用例改成：

```python
def test_candidate_view_carries_region_dimension():
    """第二批：候选视图必须带出区域维度，供同名品牌店按站点消歧。

    视图的 identity_rows 是 4 路 UNION ALL；加列必须同时改 4 个分支
    **和** 视图末尾的 SELECT 列表，否则 PostgreSQL 报
    `each UNION query must have the same number of columns`（已实测）。
    """
    text = _text("sql/semantic/shop_identity_resolution_candidates.sql")
    assert text.count("UNION ALL") == 3, "候选视图的 UNION 分支数变了（应为 4 路 UNION ALL）"
    assert "identity_shop_region" in text, "候选视图没有带出区域维度"
    assert "candidate_shop_region" in text, "候选视图的 CTE 没有店铺区域列"
```

> 同一个文件里的 `test_no_sql_asset_uses_bare_limit_1_on_identity` 与
> `test_monthly_assets_keep_legacy_warning_codes` **不受影响**，保持原样。

- [ ] **Step 2b: 运行测试确认失败**

```bash
python -m pytest backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_ambiguous_identity_sql.py -q -k "site_to_region or site_map or region_dimension or region_column"
```

Expected: **3 FAIL + 1 PASS** ——
- `test_sql_assets_map_site_to_region`：两条 orders 资产今天都没有 `source_region` → FAIL；
- `test_site_map_matches_python_side`：SQL 里还没有站点映射表 → FAIL
  （实测今天的报错是 `sql/semantic/orders_atomic.sql 缺少站点映射 菲律宾 -> PH`）；
- `test_candidate_view_carries_region_dimension`（Step 2 改写的那条）：候选视图今天没有区域列 → FAIL；
- `test_analytics_assets_do_not_get_region_column`：这条**今天就通过**（analytics 确实没有区域列），
  它是**反向护栏** —— 防止实施者为了"统一"给 analytics 硬造一个永远 NULL 的区域列。

> `-k` 里必须带上 `site_map`，否则 `test_site_map_matches_python_side` 会被 deselect 掉（名字里没有前三个关键词）。

- [ ] **Step 3: 抽取站点 → 区域（**逐文件落点不同，不要照抄**）**

> ⚠ **本 Step 早期版本写的是「三个 SQL 资产的 `mapped` CTE 里都加一列」—— 那是错的**（实测）：
> - `orders_atomic.sql` 有 `mapped` CTE（`:32`）且已有 `source_site`（`:62`）✅
> - `analytics_atomic.sql` 有 `mapped` CTE（`:34`）但**没有** `source_site` ❌
> - `orders_monthly_atomic_mv.sql` **根本没有 `mapped` CTE** ❌
>   （它的链是 `raw_monthly_orders`(:9) → `mapped_monthly_orders`(:19) → `normalized_monthly_orders`(:114)
>   → `prepared_identity_monthly_orders`(:200) → `resolved_monthly_orders` → `deduplicated_monthly_orders`(:284)）
>
> 而且 —— **两条 analytics 路径根本没有站点可映射**（live 实测，见下表）。
> 区域感知匹配**只对有站点信息的 orders 路径生效**。

**站点 → 区域的映射表达式（两个 orders 文件共用）**：

```sql
        CASE lower(NULLIF(TRIM(BOTH FROM COALESCE(source_site, '')), ''))
            WHEN '菲律宾' THEN 'PH'
            WHEN '新加坡' THEN 'SG'
            WHEN '马来' THEN 'MY'
            WHEN '马来西亚' THEN 'MY'
            WHEN '泰国' THEN 'TH'
            WHEN '越南' THEN 'VN'
            WHEN '印尼' THEN 'ID'
            WHEN '巴西' THEN 'BR'
            ELSE UPPER(LEFT(NULLIF(TRIM(BOTH FROM COALESCE(source_site, '')), ''), 2))
        END AS source_region,
```

> **8 项映射必须逐项一致**（菲律宾→ph、新加坡→sg、马来/马来西亚→my、泰国→th、越南→vn、印尼→id、巴西→br）
> —— 与 `backend/domains/collection/routers/account_alignment.py:796-805` 的 `site_map` 对齐。
> 实施者要在这两个地方各加一条注释互相指认，避免以后单边改。（SQL 侧没法直接 import Python 常量，
> 只能靠约定 + 双向注释 + 测试守住。）
>
> **⚠ fallback 的大小写两侧本来就不同，这是有意的，不要"修正"成一致**：
> - Python `account_alignment.py:806`：`site_map.get(site, site.lower()[:2] if site else "")` → **小写**。
>   它的产物只用于**生成建议 id**（`:820-821` 拼成 `tiktok_ph_xxx`），从不与 `shop_region` 比较。
> - SQL 侧：`UPPER(LEFT(..., 2))` → **大写**。
>   它的产物要与 `core.shop_accounts.shop_region`（实测存**大写** `MY` / `PH` / `SG`）比较，必须大写。
>
> → **护栏只锁「8 项映射」一致，不锁 fallback 的大小写**。
> live 数据里只出现已收录的三个中文站点（菲律宾 / 新加坡 / 马来），两边的差异目前不会显现；
> 但如果实施者把 SQL 的 fallback 改成小写，未收录站点会永远匹配不上区域码 → 区域过滤退化为层 2 兜底（安全，但消歧失效）。

**逐文件落点（⚠ 同一条 SELECT 列表里不能引用本层的输出别名，落地位置必须按下表）**：

> **PostgreSQL 的硬规则**：同一个 `SELECT` 列表里**不能**引用同层的输出别名。
> 所以 `source_region` **不能**紧跟在 `source_site` 后面（`source_site` 是上一层 CTE 的输出别名），
> 否则报 `column "source_site" does not exist`（已实测复现）。
> `source_region` 必须在**`source_site` 已经是真实输入列**的那一层计算。

| 文件 | `source_site` 在哪 | **`source_region` 在哪算** | 区域过滤是否生效 |
|---|---|---|---|
| `sql/semantic/orders_atomic.sql` | `mapped`(:32) 里 `:62` 算出（读 `raw_data->>'站点'`），并**透传**到 `cleaned`(:280) 的显式清单 `:286` | **`cleaned`(:280)** —— 在 `:286` 的 `source_site` 那一行**正下方**加（此处 `source_site` 是真实输入列，可直接引用） | ✅ 生效 |
| `sql/semantic/orders_monthly_atomic_mv.sql` | `mapped_monthly_orders`(:19) 里**新加**：`NULLIF(TRIM(COALESCE(raw_data->>'站点', raw_data->>'site')), '')`，并**透传**到 `normalized_monthly_orders`(:114) 的显式清单（该清单 `:115-198` 目前**没有** `source_site`） | **`normalized_monthly_orders`(:114)** —— 在新增的 `source_site` 那一行下面加 | ✅ 生效 |
| `sql/semantic/analytics_atomic.sql` | **不动** | **不动** | ❌ 不适用 |
| `sql/semantic/analytics_monthly_atomic_mv.sql` | **不动** | **不动** | ❌ 不适用 |

**透传清单（漏一条就报 `column ... does not exist`，已实测复现）**：

> **`source_region` 只用于匹配，不对外暴露**：两条路径的 `source_region` 都停在**中间 CTE**，
> 不进最终 SELECT 的输出列。
> - `orders_atomic.sql`：最终 SELECT（`:477-530`）**不加**它 —— LATERAL 在 `alias_resolved`(:406) 里，
>   该层直接用 `d.source_region`（`d` = `deduplicated`），中间不需要把它写进任何显式清单。
> - `orders_monthly_atomic_mv.sql`：**也不需要**写进任何显式清单 ——
>   `prepared_identity_monthly_orders`(:200) 是 `SELECT n.*, ARRAY_REMOVE(...) FROM normalized_monthly_orders n`，
>   `n.*` 已经把 `source_region` 带进来了 → 该层的 LATERAL 直接用 `m.source_region`（`m` = prepared 层）即可；
>   最终 SELECT（`:293-311`）**不加**它 → 对外仍然只有原有的那些列
>   （第一批 Task 7 会给这个 MV 加 `identity_candidate_count` / `identity_candidates`，
>   所以 Task 7 之后是 18 列；两个薄封装 VIEW 是显式列清单，是否带出新列取决于 Task 7 的「方案 A / B」）。

| 文件 | CTE 链（谁带显式列清单） | `source_region` 的传递路径 |
|---|---|---|
| `orders_atomic.sql` | `mapped`(:32) → **`cleaned`(:280，显式列清单)** → `deduplicated`(:390，`SELECT *`) → `alias_resolved`(:406) | `cleaned` 里**新算** → `deduplicated`（`SELECT *`）自动带上 → `alias_resolved` 的 LATERAL 用 `d.source_region` ✅ |
| `orders_monthly_atomic_mv.sql` | `mapped_monthly_orders`(:19) → **`normalized_monthly_orders`(:114，显式列清单)** → `prepared_identity_monthly_orders`(:200，`n.*`) → **`resolved_monthly_orders`(:221，显式列清单)** → `deduplicated_monthly_orders`(:284，`SELECT *`) | `mapped_monthly_orders` 新算 `source_site` → `normalized_monthly_orders` 显式清单里带上 `source_site` 并**新算** `source_region` → `prepared_identity_monthly_orders`（`n.*`）自动带上 → `resolved_monthly_orders` 的 LATERAL 用 `m.source_region` ✅（`m` = prepared 层）→ **不需要**再往 `resolved_monthly_orders` 的显式清单里补（`m.source_region` 已经能引用到；最终 SELECT 也不加它） |

> `orders_monthly_atomic_mv.sql` 的 `prepared_identity_monthly_orders`(:200) 是 `SELECT n.*, ARRAY_REMOVE(...) ...`，
> `n.*` 会把 `normalized_monthly_orders` 的所有列带过来 ✅ —— 这一层不用改。
> `orders_atomic.sql` 的 `deduplicated`(:390) 是 `SELECT *` ✅ —— 同样不用改。

**实测（live PG 15.14，只读）**：

| 场景 | 结果 |
|---|---|
| **反例**：在同一条 `SELECT` 列表里用 `source_site` 输出别名算 `source_region` | `ERROR: column "source_site" does not exist` ✅（这就是"不能紧跟在 `source_site` 后面"的依据） |
| `orders_atomic.sql` 落点：`cleaned` 层用真实输入列 `source_site` 算 `source_region` | ✅ 正常返回。**注意口径**：`orders_atomic.sql` 吃 daily+weekly+monthly 三个粒度 → tiktok 合计 **5004 行**（菲律宾 2762 / 新加坡 1662 / 马来 580）；另有 shopee **28261 行无站点** → `source_region` 为 NULL → 走层 2 兜底 |
| `orders_monthly_atomic_mv.sql` 落点：`normalized_monthly_orders` 层算 `source_region` | ✅ 正常返回。该 MV 共 **31289 行** = tiktok 4662（菲律宾 2450 / 新加坡 1635 / 马来 577）+ shopee 26627（站点全 NULL → 层 2 兜底） |
| 过滤条件引用 `d.source_region` / `m.source_region` | ✅ 正常返回 |

> 反例那行**必须报错** —— 它证明"同层不能引用输出别名"这条 PostgreSQL 规则在 live 上确实生效，
> 实施者如果把 `source_region` 放错层，部署时会立刻看到 `column "source_site" does not exist`，
> 而不是等到数据错配才发现。



**为什么两条 analytics 路径不适用（live 实测，只读）**：

| raw 表 | 行数 | 有 `站点` | 有 `店铺` | 有 `shop_account_id` |
|---|---|---|---|---|
| `b_class.fact_tiktok_orders_monthly` | 4662 | **4662（100%）** | **4662（100%）** | 2751（59%） |
| `b_class.fact_tiktok_analytics_monthly` | 1263 | **0** | **0** | 543（43%） |
| `b_class.fact_shopee_orders_monthly` | 26627 | **0** | **26627（100%）** | 15432（58%） |

即：
- **analytics 的 raw 里既没有站点、也没有店铺标签** → 无从推导区域。
  这两条路径靠 `shop_account_id`（稳定锚点）匹配，**不会**出现「同一标签命中多个店」的歧义，
  所以只需要第一批的「候选唯一才归属」判定（候选 0 → `unmatched_shop_label`，候选 ≥2 → `ambiguous_shop_label`），
  **不需要**区域过滤。
- **shopee 的 raw 里也没有站点** → `source_site` 为 NULL → `source_region` 为 NULL →
  区域过滤对 shopee 自动失效（等价于「不限区域」），**行为不变**。

> **不要**为了「三个文件统一」而给 analytics 硬造一个区域字段 —— 那会引入一个永远是 NULL 的列，
> 或者更糟：让实施者以为 analytics 也能按区域消歧。

- [ ] **Step 4: 候选视图带出别名的区域**

`sql/semantic/shop_identity_resolution_candidates.sql` 的 `alias_match` 分支要带出 `saa.shop_region`。
**注意**：该视图的 `identity_rows` 是 **4 路 UNION ALL**（`platform_shop_id` / `shop_account_id` / `alias_match` / `store_name_match`），
加列必须**同时**改 4 个分支 **和** 视图末尾的 SELECT 列表，否则 PostgreSQL 报
`each UNION query must have the same number of columns`（已实测）。

建议新增列 `identity_shop_region`，取值如下：

| 分支 | `identity_shop_region` |
|---|---|
| `alias_match` | `saa.shop_region`（别名自己的区域；NULL = 「不限区域」） |
| `platform_shop_id` | `active_shop_accounts.candidate_shop_region` |
| `shop_account_id` | `active_shop_accounts.candidate_shop_region` |
| `store_name_match` | `active_shop_accounts.candidate_shop_region` |

> ⚠ **`active_shop_accounts.candidate_shop_region` 这一列当前并不存在**（候选视图的 CTE 只有
> `shop_account_pk` / `platform_code` / `resolved_shop_account_id` / `candidate_platform_shop_id` /
> `candidate_store_label` / `resolved_shop_id` 六列）。实施者必须**先**在该 CTE 里补出：
>
> ```sql
>         NULLIF(TRIM(COALESCE(sa.shop_region, '')), '') AS candidate_shop_region,
> ```
>
> 放在 `candidate_store_label` 那一行后面，再在 4 个 UNION 分支与最终 SELECT 里引用它。

> ⚠ `core.shop_account_aliases.shop_region` 是**第一批 Task 5 新加的列**（当前 live 还没有）。
> 若该列不存在，`alias_match` 分支会直接报错 → 实施者必须确认第一批迁移已应用
> （`python scripts/run_current_schema_migrations.py --preflight-only --json`）。

- [ ] **Step 5: 匹配时按区域消歧（**只对两条 orders 路径生效**）**

`orders_atomic.sql` 与 `orders_monthly_atomic_mv.sql` 的 LATERAL 在候选集合上增加区域过滤，规则：

```
完整候选集 = 候选视图里 identity_value_normalized 命中的行（D10a 的口径）
层 1（精确匹配）：identity_shop_region = 该行 source_region，且 source_region IS NOT NULL
层 2（兜底）    ：当层 1 为空时，用**完整候选集**（不做任何区域过滤）

最终候选集 = 层 1 非空 ? 层 1 : 层 2
```

- 候选集为空 → `unmatched_shop_label`；
- 最终候选集里仍有多个候选 → `ambiguous_shop_label`。

> **为什么层 2 是「完整候选集」而不是「只取 `identity_shop_region IS NULL` 的别名」**：
> 「只取不限区域的别名」在**没有站点**的数据上（shopee 的 raw 里没有 `站点`，实测 26627 行全空）
> 会把该平台所有别名都滤掉 → **凭空制造新的 unknown**，直接违反「区域过滤只用于消歧、不制造新 unknown」这条硬约束。
> 用「层 1 为空就回落完整候选集」可以**证明**区域过滤只会让归属更精确、不会让归属变少：
> 层 1 ⊆ 完整候选集 → `candidate_count` 只会不变或变小；变小只可能把 `ambiguous(≥2)` 变成 `unique(1)`，不会把 `unique(1)` 变成 `ambiguous`。

**可执行实现（已在 live PG 15.14 实测，下表 6 种输入全部符合预期）**：

```sql
                   AND (
                         (
                             c.identity_shop_region IS NOT NULL
                             AND m.source_region IS NOT NULL
                             AND c.identity_shop_region = m.source_region
                         )
                         OR NOT EXISTS (
                             SELECT 1
                             FROM semantic.shop_identity_resolution_candidates c_exact
                             WHERE c_exact.platform_code = lower(COALESCE(m.platform_code, ''))
                               AND c_exact.identity_value_normalized = ANY (m.normalized_identity_candidates)
                               AND c_exact.identity_shop_region IS NOT NULL
                               AND m.source_region IS NOT NULL
                               AND c_exact.identity_shop_region = m.source_region
                         )
                   )
```

> 这段条件要**同时**加在 Step 4b 模板里的两个子查询上（`agg` 计数子查询 与 `best` 最优候选子查询），
> 否则会出现「计数按过滤后的候选算、归属却取到未过滤的候选」的不一致。
> `orders_atomic.sql` 里把 `m.` 换成 `d.`。

**实测记录（live PG 15.14，只读；用「候选视图 + 新增区域列」的等价 CTE 模拟）**：

| 场景 | 输入 | `candidate_count` | 落点 |
|---|---|---|---|
| 单候选 + 区域命中 | `['新加坡1店']`，`source_region='SG'` | 1 | `tiktok_sg_daone_mall_local` |
| **目标场景**：同名品牌 + 站点分流 | `['新加坡1店','马来1店']`，`source_region='SG'` | **1** | `tiktok_sg_daone_mall_local`（D10a 下这里是 2 → `ambiguous_shop_label`） |
| 同名品牌 + 站点分流（另一区） | `['新加坡1店','马来1店']`，`source_region='MY'` | 1 | `tiktok_my_dawie_mall_local` |
| 无精确匹配 → 层 2 兜底 | `['马来1店']`，`source_region='SG'` | 1 | `tiktok_my_dawie_mall_local`（**不是 unknown**） |
| 无站点（shopee 式） → 层 2 兜底 | `['马来1店']`，`source_region=NULL` | 1 | `tiktok_my_dawie_mall_local`（**不是 unknown**） |
| 零候选 | `['不存在的店名xyz']` | 0 | `unknown` + `unmatched_shop_label` |

> **未收录站点不会制造新 unknown**：映射表 `ELSE UPPER(LEFT(site,2))` 对未收录的中文站点会产出中文串
> （如「美国」→「美国」），它与任何区域码都不相等 → 没有层 1 命中 → 自动落到层 2 完整候选集 → 归属不变。
> 这条与 Step 3 的映射表实现无关，**即使 fallback 保留原样也安全**。

**两条 analytics 路径不做区域过滤**（`analytics_atomic.sql` / `analytics_monthly_atomic_mv.sql`）——
它们的 raw 里既没有站点也没有店铺标签（Step 3 实测表），无从推导区域；
这两条路径靠 `shop_account_id` 匹配，不会出现同名品牌歧义。

**注意 `candidate_count` 的算口径**：区域过滤必须作用在**候选集合本身**上，
也就是把「计数用的 `agg` 子查询」和「取最优候选的 `best` 子查询」**都**加上**同一段**过滤条件
（就是上面那段 `AND ( 精确匹配 OR NOT EXISTS(精确匹配) )`），
否则会出现「计数按过滤后的候选算、归属却取到未过滤的候选」的不一致。

`<source_region 表达式>` 在 `orders_atomic.sql` 里是 `d.source_region`，
在 `orders_monthly_atomic_mv.sql` 里是 `m.source_region`（**Step 3 新算的列**，透传路径见 Step 3 的透传清单）。

> **不要**把过滤条件写成「`c.identity_shop_region = <src> OR c.identity_shop_region IS NULL`」——
> 那是**并集**语义：不限区域的别名会与精确匹配的别名一起被计入 → `candidate_count ≥ 2` → 仍然落
> `ambiguous_shop_label`，「优先/兜底」等于没实现；而且在没有站点的数据上（shopee）会把别名全滤掉 →
> **凭空制造新的 unknown**。正确写法就是上面那段带 `NOT EXISTS` 的版本。

> **必须保证**：区域过滤**只用于消歧，不制造新的 unknown**。
> 存量 21 条别名在 Task 5 已按 `core.shop_accounts.shop_region` 回填区域，
> 而 raw 的 `站点` 映射出来的区域与店铺区域一致（实测 TikTok 六个店：MY/PH/SG ↔ 马来/菲律宾/新加坡）→
> 存量数据应全部**继续唯一命中**。

- [ ] **Step 6: 部署 + 回归**

> **⚠⚠ 必须先 `rebuild_views.py`，不能只跑 bootstrap**（第一批 Task 8 Step 1 的同一条规矩）：
> `bootstrap_postgresql_dashboard.py` 走 `refresh_runner.execute_sql_target(recreate_views=False)`，
> 而 `backend/services/data_pipeline/refresh_runner.py:408` 对**库里已存在的普通视图**会**直接跳过**。
> 本 Task 改的 `sql/semantic/shop_identity_resolution_candidates.sql` 是**普通 VIEW**，
> `sql/semantic/orders_atomic.sql` 也是普通 VIEW → 只跑 bootstrap 的话**两个都不会重建**，
> `identity_shop_region` / `candidate_shop_region` / `source_region` 不会出现，
> 而 monthly MV 会重建 → 回归查询**照样「通过」** → **静默失败**。

```bash
python scripts/rebuild_views.py --dry-run      # 1) 先看要重建什么
python scripts/rebuild_views.py                # 2) 真跑（recreate_views=True，按依赖顺序重建整链）
python scripts/bootstrap_postgresql_dashboard.py --module all --refresh-materializations   # 3) 补资产 + 刷新
```

**列级护栏（必须查，不能只看数据行数）**：

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    # ① 候选视图是普通 VIEW，用 information_schema 查它的输出列
    cols = [r[0] for r in c.execute(sa.text('''
        select column_name from information_schema.columns
         where table_schema='semantic' and table_name='shop_identity_resolution_candidates'
           and column_name like '%shop_region%'
         order by column_name'''))]
    print('candidates view ->', cols)
    # ② source_region 只用于匹配、**不对外暴露** -> 不能查列，要查视图定义
    d = c.execute(sa.text(
        "select pg_get_viewdef(CAST('semantic.fact_orders_atomic' AS regclass), true)"
    )).scalar()
    print('fact_orders_atomic def has source_region =', 'source_region' in d)
"
```

Expected:
- `candidates view -> ['identity_shop_region']`（**1 列**）
- `fact_orders_atomic def has source_region = True`

> ⚠ **为什么候选视图只期望 1 列**：`candidate_shop_region` 是 `active_shop_accounts` CTE 的**内部列**，
> 视图的最终 SELECT（7 列显式清单）只把它包成 `identity_shop_region` 输出一列 →
> `information_schema.columns` 里**看不到** `candidate_shop_region`。
> 它的存在由第一批留下的护栏 `test_candidate_view_carries_region_dimension`
> 断言 SQL 文本里的 `"candidate_shop_region" in text` 来守。
>
> ⚠ **为什么 `source_region` 要查视图定义而不是列**：
> Step 3 明确「`source_region` 只用于匹配、不对外暴露」→ 它**不出现在**最终 SELECT 里，
> `information_schema.columns` 查它是 `[]`（那是**正确的**，不是没重建）。
> 要验证它，只能查 `pg_get_viewdef` 里有没有这个表达式。
> （如果实施者把 `source_region` 加进了最终 SELECT，那条护栏会变成 `[]` → 反而说明设计被改坏了。）

> 少了任何一列 = 视图定义没真正重建 → 回到 `rebuild_views.py`。
> **不要用 bootstrap 的 `--check` / drift 当护栏** ——
> `dashboard_bootstrap.py:510-515` 在跑完后会**无条件**把 `asset_fingerprint_applied` 写成期望值、
> `status` 写成 `ready`，所以 drift 信号会被自己抹掉。**唯一可信的证据就是上面的列级检查。**

然后跑一次与第一批 Task 8 Step 3 相同的基线对比：

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text(\"select shop_id, count(*) from semantic.fact_orders_atomic where platform_code='tiktok' group by 1 order by 2 desc\")):
        print(tuple(r))
"
```

Expected: **与第一批 Task 0 的基线完全一致**（2473 / 1448 / 505 / 289 / 124 / 90 / 75）——
区域过滤**不得**改变存量数据的归属。

- [ ] **Step 7: 提交**

```bash
git add sql/semantic/ backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_ambiguous_identity_sql.py
git commit -m "feat(语义层): 区域参与身份匹配，同名品牌店按站点分流

- cleaned / normalized_monthly_orders 层把 raw 的中文站点映射成区域码（与 account_alignment.py 的 site_map 对齐）
- 候选视图带出别名/店铺的区域维度
- 匹配时先按区域精确匹配；没有精确匹配时回落到**完整候选集**（不是「只取不限区域的别名」）
- 存量数据归属不变（与第一批基线一致）"
```

---

## 18. 第二批总验收

- [ ] **Step 1: 跑全量相关测试**

```bash
python -m pytest backend/tests/test_pwcli_session_naming.py backend/tests/test_session_manager_protection.py backend/tests/test_session_storage_roots.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_shop_internal_code.py backend/tests/test_shop_rename_flow.py backend/tests/test_shop_account_aliases_api.py backend/tests/test_shop_identity_schema_migration.py backend/tests/test_alias_normalization_consistency.py backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/data_pipeline/test_refresh_runner.py backend/tests/test_semantic_ambiguous_identity_sql.py -q
```

Expected: 全部 PASS。

- [ ] **Step 1b: 确认区域感知匹配没有改变存量归属**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text(\"select shop_id, count(*) from semantic.fact_orders_atomic where platform_code='tiktok' group by 1 order by 2 desc\")):
        print(tuple(r))
"
```

Expected: 与第一批 Task 0 的基线一致（2473 / 1448 / 505 / 289 / 124 / 90 / 75）。

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

## 19. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| Task 16 改名触发一次 raw 层全量重算 | 耗时长 | 这是必要的（归属路径确实要重算）；重算只发生一次；上线前在快照库演练 |
| Task 16 别名写入与既有别名冲突 | 改名失败 | 冲突报 409 并指出冲突店铺，不静默覆盖 |
| Task 15 存量回填产生重复标准名 | 唯一约束报错 | 回填按平台分组 + 冲突追加主账号短标识；回填前后各跑一次唯一性核对 |
| Task 12 slugify 规则变更导致历史 session 名对不上 | 旧窗口找不到 | 旧 session 名只影响「复用同一次窗口」，不影响已保存的 storage_state（按账号目录走） |
| Task 13 新鲜度口径变更让一批旧会话被判过期 | 需重新登录一次 | 属预期效果；上线前先统计有多少会话会因此过期并告知运营 |

**回滚**：每个 Task 独立提交，`git revert <commit>` 即可。Task 15 / 16 涉及数据库数据，回滚需要配套的数据订正脚本。

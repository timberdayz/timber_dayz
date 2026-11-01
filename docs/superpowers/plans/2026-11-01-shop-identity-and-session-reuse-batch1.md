# 店铺身份与巡店会话复用 · 第一批（止血）实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让人工巡店保存下来的会话**真的能被采集复用**且**失败看得见**，同时把「订单重复入账」「同名店铺数据张冠李戴」两个数据正确性漏洞堵上。

**Architecture:** 两条互不依赖的线同时收敛。**会话线**（Task 1–4）：把巡店面板的 session 定位、退出码传播、读写路径三处断点接上，并补 `pwcli_native` 直接调用入口的 `sys.path` 兜底。**身份线**（Task 5–11）：先加别名表的区域维度与内部标准名列（迁移），再统一别名规范化，再把语义层从「`LIMIT 1` 归第一」改成「唯一才归属、多候选落 `unknown` + 告警码」，最后把采集入库的身份字段与 `data_hash` 口径换成稳定的 `shop_account_id`。

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / Pydantic / PostgreSQL 15.14（`postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp`）/ pytest / PowerShell 5.1 / Playwright sync API（pwcli 侧）/ Vue 3 + Element Plus

**Spec:** `docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md`（v3，含 §11.1 四项业务拍板结论）

---

## 0. 适用范围与全局约定

### 0.1 本计划覆盖的 spec 条款

| Spec 条款 | 计划任务 | 验收项 |
|---|---|---|
| D5 会话读写路径统一 | Task 1 | A3 |
| D1 保存按账号定位会话 / D2 退出码传播 | Task 2 | A1 A2 |
| D3 面板渲染真实输出 | Task 3 | A2 |
| D4 `pwcli_native` 直接调用 `sys.path` 兜底 | Task 4 | A1 |
| D10 别名表区域维度 | Task 5 | A10 |
| D12 平台大小写归一 | Task 5 | A9 |
| D11 别名规范化统一 | Task 6 | A8 |
| D13 多候选落 unknown + 告警码 | Task 7 Task 8 | A6 A7 |
| D14 稳定身份编号落库 | Task 9 Task 10 | A5 |
| A14 待认领清单 | Task 11 | A14 |

### 0.2 明确不在本计划范围（属第二批 / 独立计划）

- 第二批全部：③一账号一巡店窗口、④账号标识唯一化、⑦曾用名、⑨改名后按站点重认、⑪内部标准名前端、⑫会话新鲜度与持久化、⑬改名联动。
- IP 隔离（spec §10）。
- `TK新加坡3C店` 的认领（业务已决定暂不认领，Task 11 只做**可见性**）。
- `data/sessions` 下 18~20 个历史别名孤儿目录的清理（spec §10）。

### 0.3 全局约定

- **分支**：`main` 是发布分支，本计划在特性分支上做：`git switch -c feature/shop-identity-batch1`。
- **PowerShell 不展开 `*`**：pytest 必须显式列出文件路径。
- **提交信息风格**：`type(scope): 中文标题` + 要点正文。参考 `10739b23`、`0b60c196`。
- **数据库**：连接串 `postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp`。迁移落在 `current_migrations/versions/`（活动迁移集，当前 head = `current_schema_20261028_drop_deprecated_traffic_fact_tables`）。
- **ORM SSOT**：`modules/core/db/schema_parts/platform.py`。改列必须同步这里。
- **Pydantic 契约**放 `backend/schemas/`，不放 router。
- **新后端运行时代码**用 `AsyncSession` / `get_async_db()`，用 `datetime.now(timezone.utc)`。
- **Windows 终端输出不带 emoji**。
- **不新增抓取能力**。

### 0.4 实施顺序约束

```
Task 1 → Task 2 → Task 3 → Task 4          （会话线，可与身份线并行）
Task 5 → Task 6 → Task 7 → Task 8          （身份线，必须串行：迁移 → 规范化 → 语义层）
Task 9 → Task 10                          （落库，必须在 Task 5 之后）
Task 11                                  （面板可见性，依赖 Task 7/8）
```

**Task 9（补齐 `catalog_files.shop_account_id`）必须先于 Task 10（改 `data_hash` 口径）**，否则会造成全量历史行重复。

---

## Task 0: 分支与基线核对

**Files:**
- 无文件改动

- [ ] **Step 1: 建分支**

```bash
git switch -c feature/shop-identity-batch1
git status --short
```

Expected: 无输出（工作区干净）。

- [ ] **Step 2: 记录基线测试结果**

```bash
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_session_manager_protection.py backend/tests/test_shop_account_aliases_api.py backend/tests/data_pipeline/test_shop_identity_resolution_sql.py -q
```

Expected: 全部 PASS。**把实际通过数记在提交信息里**，后续每个 Task 都要对比回归。

- [ ] **Step 3: 记录 live 语义层基线（用于 Task 8 前后对比）**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text(\"select shop_id, count(*) from semantic.fact_orders_atomic where platform_code='tiktok' group by 1 order by 2 desc\")):
        print(tuple(r))
"
```

Expected（当前基线，必须逐行记下）:

```
('tiktok_ph_explorers_mall_local', 2473)
('tiktok_sg_daone_mall_local', 1448)
('tiktok_my_dawie_mall_local', 505)
('tiktok_ph_daju_mall_local', 289)
('tiktok_sg_hx_home_local', 124)
('unknown', 90)
('tiktok_my_flora_mall_local', 75)
```

- [ ] **Step 4: 提交基线记录**

```bash
git commit --allow-empty -m "chore(batch1): 记录店铺身份与巡店会话复用第一批的基线

- 基线测试：见提交正文
- live semantic.fact_orders_atomic (tiktok) 分布已记录，用于 Task 8 前后对比"
```

---

## Task 1: 会话读写路径统一（写入用净化名，读取也必须用净化名）

**Files:**
- Modify: `modules/utils/sessions/session_manager.py:773-794`（`_safe_filename`）
- Modify: `modules/utils/pwcli_native.py:167-175`（`runtime_account_state_path`）
- Test: `backend/tests/test_pwcli_native_session_alignment.py`

**背景**：`SessionManager.save_session` 写到 `data/sessions/<platform>/hongxikeji_main/storage_state.json`（`_safe_filename` 把 `:` 换成 `_`），而巡店侧读取用 `runtime_account_state_path` 的**原始 account_id** → `data/sessions/<platform>/hongxikeji:main/storage_state.json`。磁盘上只有前者 → **即使保存成功，下次打开仍读不到，每次都要重新登录**。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_pwcli_native_session_alignment.py` 末尾追加：

```python
def test_runtime_account_state_path_matches_session_manager_write_path(tmp_path, monkeypatch):
    """巡店读取路径必须与 SessionManager 写入路径完全一致。"""
    from modules.utils.pwcli_native import runtime_account_state_path
    from modules.utils.sessions.session_manager import SessionManager

    monkeypatch.setattr("modules.utils.pwcli_native.REPO_ROOT", tmp_path)
    manager = SessionManager(base_path=tmp_path / "data" / "sessions")

    account_id = "hongxikeji:main"
    expected = manager.get_session_path("shopee", account_id)
    actual = runtime_account_state_path("shopee", account_id)

    assert actual == expected
    assert actual.parent.name == "hongxikeji_main"
    assert actual.name == "storage_state.json"


def test_runtime_account_state_path_is_stable_for_colon_accounts(tmp_path, monkeypatch):
    """带冒号的账号 ID 与已净化账号 ID 必须指向同一个目录。"""
    from modules.utils.pwcli_native import runtime_account_state_path

    monkeypatch.setattr("modules.utils.pwcli_native.REPO_ROOT", tmp_path)

    a = runtime_account_state_path("shopee", "hongxikeji:main")
    b = runtime_account_state_path("shopee", "hongxikeji_main")
    assert a == b
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_native_session_alignment.py -q -k "runtime_account_state_path"
```

Expected: FAIL —— `actual` 指向 `hongxikeji:main` 目录，与 `expected`（`hongxikeji_main`）不相等。

- [ ] **Step 3: 在 `session_manager.py` 抽出公开的目录名函数**

把 `modules/utils/sessions/session_manager.py:773-794` 的 `_safe_filename` 改成：

```python
    @staticmethod
    def _safe_filename(filename: str) -> str:
        """
        转换为安全的文件名

        Args:
            filename: 原始文件名

        Returns:
            安全的文件名
        """
        return safe_session_account_dirname(filename)
```

并在**模块级**（`_session_freshness_timestamp` 附近）新增：

```python
def safe_session_account_dirname(account_id: str) -> str:
    """账号 ID -> 会话目录名。

    会话的**写入路径**与**读取路径**必须共用本函数，否则巡店保存的会话
    在下次打开时读不到（见 spec D5）。

    Args:
        account_id: 原始账号 ID，例如 ``hongxikeji:main``

    Returns:
        安全的目录名，例如 ``hongxikeji_main``
    """
    unsafe_chars = '<>:"/\\|?*'
    safe_name = str(account_id)
    for char in unsafe_chars:
        safe_name = safe_name.replace(char, "_")
    if len(safe_name) > 50:
        safe_name = safe_name[:50]
    return safe_name
```

- [ ] **Step 4: 改 `pwcli_native.runtime_account_state_path`**

替换 `modules/utils/pwcli_native.py:167-175`：

```python
def runtime_account_state_path(platform: str, account_id: str) -> Path:
    """巡店侧会话读取路径。

    必须与 SessionManager 的写入路径完全一致（spec D5）：
    写入用 safe_session_account_dirname 净化，读取也必须用同一个函数，
    否则保存下来的会话在下次打开时读不到。
    """
    from modules.utils.sessions.session_manager import safe_session_account_dirname

    return (
        REPO_ROOT
        / "data"
        / "sessions"
        / platform.lower()
        / safe_session_account_dirname(str(account_id).strip())
        / "storage_state.json"
    )
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_native_session_alignment.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 回归**

```bash
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_session_manager_protection.py -q
```

Expected: 全部 PASS（`test_session_storage_roots.py` 断言的是「session 目录名 ≠ profile 目录名」，本 Task 不改变 profile 目录名）。

- [ ] **Step 7: 提交**

```bash
git add modules/utils/sessions/session_manager.py modules/utils/pwcli_native.py backend/tests/test_pwcli_native_session_alignment.py
git commit -m "fix(会话): 让巡店读取路径与会话写入路径完全一致

- SessionManager 抽出公开的 safe_session_account_dirname，写入与读取共用
- pwcli_native.runtime_account_state_path 改用同一净化规则
- 修复：会话保存成功但下次打开读不到（hongxikeji:main vs hongxikeji_main）"
```

---

## Task 2: 保存动作按账号定位会话 + 退出码传播

**Files:**
- Modify: `scripts/pwcli.ps1:6-7`
- Modify: `scripts/pwcli_helpers.ps1:195-225`（`Save-PwcliPlatformState`）
- Modify: `scripts/pwcli_helpers.ps1:281-294`（`Save-Pwcli{Platform}State`）
- Test: `backend/tests/test_pwcli_helpers_session_targeting.py`（新建）

**背景（两个断点叠加）**：

1. `Save-PwcliPlatformState -AccountId X` **完全不用 X 定位会话**，只读 `$env:PLAYWRIGHT_CLI_SESSION`；面板每次动作起新 PowerShell 进程（`scripts/pwcli_inspection_panel.py:54-68`），该变量不在进程环境里 → 落到 `pwcli state-save` → session 解析为 `"default"` → `require_session("default")` 失败。
2. `scripts/pwcli.ps1` 结尾没有 `exit $LASTEXITCODE` → 失败也返回 0 → 面板 `result.exit_code != 0` 永远为假 → **永远显示成功**。

session 名的唯一真源是 `scripts/pwcli_account_inventory.py:54-55` 的 `work_tag(platform, account_id) = f"{slugify(platform)}-{slugify(account_id)}-inspect"`，`scripts/pwcli_helpers.ps1:164` 拼成 `"$platformName-$WorkTag"`。**不要在 PowerShell 里复制 slugify 逻辑** —— 改为由调用方显式传 `-WorkTag`。

- [ ] **Step 1: 写失败测试（静态断言 + 实跑）**

新建 `backend/tests/test_pwcli_helpers_session_targeting.py`：

```python
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPERS = REPO_ROOT / "scripts" / "pwcli_helpers.ps1"
LAUNCHER = REPO_ROOT / "scripts" / "pwcli.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_launcher_propagates_exit_code():
    """pwcli.ps1 必须把 python 的退出码传给调用方，否则失败会被当成成功。"""
    text = _read(LAUNCHER)
    assert re.search(r"exit\s+\$LASTEXITCODE", text), "pwcli.ps1 缺少 exit $LASTEXITCODE"


def test_save_helper_accepts_work_tag():
    """保存函数必须能按账号定位会话，不能只依赖环境变量。"""
    text = _read(HELPERS)
    save_block = text.split("function Save-PwcliPlatformState", 1)[1].split("function ", 1)[0]
    assert "WorkTag" in save_block, "Save-PwcliPlatformState 缺少 -WorkTag 参数"
    assert "$platformName-$WorkTag" in save_block.replace(" ", "").replace(
        '"$platformName-$WorkTag"', '"$platformName-$WorkTag"'
    ) or '"$platformName-$WorkTag"' in save_block


def test_save_helper_throws_on_nonzero_exit():
    """保存失败必须抛错，让调用方拿到非 0 退出码。"""
    text = _read(HELPERS)
    save_block = text.split("function Save-PwcliPlatformState", 1)[1].split("function ", 1)[0]
    assert "$LASTEXITCODE" in save_block
    assert "throw" in save_block
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_helpers_session_targeting.py -q
```

Expected: 3 个 FAIL（分别缺 `exit $LASTEXITCODE`、缺 `-WorkTag`、缺 `$LASTEXITCODE`/`throw` 检查）。

- [ ] **Step 3: `scripts/pwcli.ps1` 传播退出码**

把 `scripts/pwcli.ps1` 全文替换为：

```powershell
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$CliArgs
)

$ScriptPath = Join-Path $PSScriptRoot "pwcli_native.py"
& python $ScriptPath @CliArgs
exit $LASTEXITCODE
```

- [ ] **Step 4: `Save-PwcliPlatformState` 支持 `-WorkTag` 并检查退出码**

把 `scripts/pwcli_helpers.ps1:195-225` 整段替换为：

```powershell
function Save-PwcliPlatformState {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform,
        [string]$AccountId,
        [string]$Filename,
        [string]$WorkTag
    )

    $platformName = $Platform.ToLower()

    if ($AccountId -and $WorkTag) {
        # session 名必须与 Open-PwcliPlatform 完全一致（同一平台 + 同一 work tag）。
        # 不能依赖 $env:PLAYWRIGHT_CLI_SESSION —— 面板每次动作都是新进程，变量不在里面。
        $session = "$platformName-$WorkTag"
        pwcli --session $session state-save
        if ($LASTEXITCODE -ne 0) {
            throw "pwcli state-save failed for session '$session' (exit code $LASTEXITCODE)"
        }
        return
    }

    if (-not $Filename) {
        $Filename = Get-PwcliStateFile -Platform $platformName
    }

    New-Item -ItemType Directory -Force (Split-Path -Parent $Filename) | Out-Null
    $session = Get-PwcliActiveSession
    if ($session) {
        pwcli --session $session state-save $Filename
    } else {
        pwcli state-save $Filename
    }
    if ($LASTEXITCODE -ne 0) {
        throw "pwcli state-save failed for session '$session' (exit code $LASTEXITCODE)"
    }
}
```

- [ ] **Step 5: 三个平台包装函数透传 `-WorkTag`**

把 `scripts/pwcli_helpers.ps1:281-294` 整段替换为：

```powershell
function Save-PwcliMiaoshouState {
    param([string]$AccountId, [string]$WorkTag)
    Save-PwcliPlatformState -Platform miaoshou -AccountId $AccountId -WorkTag $WorkTag
}

function Save-PwcliShopeeState {
    param([string]$AccountId, [string]$WorkTag)
    Save-PwcliPlatformState -Platform shopee -AccountId $AccountId -WorkTag $WorkTag
}

function Save-PwcliTiktokState {
    param([string]$AccountId, [string]$WorkTag)
    Save-PwcliPlatformState -Platform tiktok -AccountId $AccountId -WorkTag $WorkTag
}
```

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_helpers_session_targeting.py -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 实跑验证退出码传播（只读，不启动浏览器）**

```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '$PWD\scripts\pwcli.ps1' --session no-such-session-xyz state-save; exit $LASTEXITCODE"
```

Expected: 打印 `No browser session found for 'no-such-session-xyz'`，**退出码 ≠ 0**。

- [ ] **Step 8: 提交**

```bash
git add scripts/pwcli.ps1 scripts/pwcli_helpers.ps1 backend/tests/test_pwcli_helpers_session_targeting.py
git commit -m "fix(巡店): 保存会话按账号定位，并让失败真正返回非 0 退出码

- pwcli.ps1 补 exit \$LASTEXITCODE，失败不再被当成成功
- Save-PwcliPlatformState 新增 -WorkTag，session 名与 Open-PwcliPlatform 完全一致
- 不再依赖 \$env:PLAYWRIGHT_CLI_SESSION（面板每次动作都是新进程，变量不在里面）
- 保存失败时 throw，调用方能拿到非 0 退出码"
```

---

## Task 3: 面板渲染真实输出（失败原因必须可见）

**Files:**
- Modify: `scripts/pwcli_inspection_panel.py:175-190`（`run_action`）
- Modify: `scripts/pwcli_inspection_panel_static/index.html:311-324`（`runAction`）
- Test: `backend/tests/test_pwcli_inspection_panel_reporting.py`（新建）

**背景**：`scripts/pwcli_inspection_panel_static/index.html:320` 的日志只渲染 `result.status`，**不渲染含真实 stdout/stderr 的 `result.message`** → 即使后端返回了错误原因，用户也看不到。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_pwcli_inspection_panel_reporting.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL_HTML = REPO_ROOT / "scripts" / "pwcli_inspection_panel_static" / "index.html"
PANEL_PY = REPO_ROOT / "scripts" / "pwcli_inspection_panel.py"


def test_panel_html_renders_message_not_only_status():
    """前端日志必须渲染 message（真实 stdout/stderr），不能只有 status。"""
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert "result.message" in text or ".message" in text, "前端未渲染 result.message"


def test_panel_records_stderr_on_failure():
    """后端在失败时必须把 stderr 原文记进日志。"""
    text = PANEL_PY.read_text(encoding="utf-8")
    assert "result.stderr" in text
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_inspection_panel_reporting.py -q
```

Expected: 至少 1 个 FAIL。

- [ ] **Step 3: 后端把 stdout+stderr 一起记进日志**

把 `scripts/pwcli_inspection_panel.py:182-190` 替换为：

```python
        result = state.command_runner(command)
        combined_output = "\n".join(
            part for part in (result.stdout, result.stderr) if part and part.strip()
        ).strip()
        if result.exit_code != 0 or not combined_output:
            state.statuses[key] = "error"
            message = combined_output or f"Command failed with exit code {result.exit_code}"
            state.record(action, account, "error", message)
            raise HTTPException(status_code=500, detail=message)
        state.statuses[key] = success
        state.record(action, account, success, combined_output or (result.stdout or "").strip())
        return {**account, "status": success, "message": combined_output}
```

- [ ] **Step 4: 前端渲染 message**

在 `scripts/pwcli_inspection_panel_static/index.html` 的 `runAction` 里，把日志写入改为**同时**渲染 `result.message` 与 `result.status`。定位方式：搜索 `result.status` 的日志渲染语句，替换为：

```javascript
        const detail = (result && result.message) ? result.message : '';
        appendLog(
          `${label} · ${account.display_name || account.account_id} · ${result.status || 'unknown'}`
          + (detail ? `\n${detail}` : '')
        );
```

> 实施者注意：本仓库的 JS 变量名以实际文件为准。**要求是：日志文本必须包含 `result.message` 的内容**，且失败时 `result.status` 为 `error`。
> 若文件里已有 `appendLog` 之类的辅助函数，复用它，不要新增第二个日志函数。

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_inspection_panel_reporting.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add scripts/pwcli_inspection_panel.py scripts/pwcli_inspection_panel_static/index.html backend/tests/test_pwcli_inspection_panel_reporting.py
git commit -m "fix(巡店面板): 把真实 stdout/stderr 渲染到日志里

- 后端失败时把 stdout 与 stderr 合并记录，成功时也一并返回
- 前端日志不再只显示 status，失败原因对运营可见"
```

---

## Task 4: `pwcli_native` 直接调用入口补 `sys.path` 兜底

**Files:**
- Modify: `modules/utils/pwcli_native.py:23`（`REPO_ROOT` 定义之后）
- Test: `backend/tests/test_pwcli_native_sys_path_bootstrap.py`（新建）

**背景**：`modules/utils/pwcli_native.py:320` 的延迟导入 `from modules.utils.sessions.session_manager import SessionManager` 只有在 `default_state_mode == "session_manager"`（即传了 `--account-id`）时才执行。生产链 `scripts/pwcli.ps1` → `scripts/pwcli_native.py`（shim，第 4 行已 `sys.path.insert`）**不受影响**；但直接 `python modules/utils/pwcli_native.py …` 会抛 `ModuleNotFoundError: No module named 'modules'`。直接调用是公开入口，必须兜底。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_pwcli_native_sys_path_bootstrap.py`：

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_direct_script_launch_can_import_session_manager():
    """直接以脚本方式启动 pwcli_native 时，必须能 import 到 modules.*。"""
    probe = REPO_ROOT / "modules" / "utils" / "pwcli_native.py"
    code = (
        "import runpy, sys;"
        "sys.argv = ['pwcli_native.py', '--help'];"
        "runpy.run_path(r'%s', run_name='__main__')" % probe
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "ModuleNotFoundError" not in (result.stderr or ""), result.stderr
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_native_sys_path_bootstrap.py -q
```

Expected: FAIL，`stderr` 含 `ModuleNotFoundError: No module named 'modules'`。

- [ ] **Step 3: 加 `sys.path` 引导**

在 `modules/utils/pwcli_native.py:23`（`REPO_ROOT = ...` 那一行）**之后**插入：

```python
REPO_ROOT = Path(__file__).resolve().parents[2]

# 直接以 `python modules/utils/pwcli_native.py` 启动时，sys.path[0] 是脚本目录而非仓库根，
# 延迟导入 modules.* 会抛 ModuleNotFoundError（见 spec D4）。
# scripts/pwcli_native.py 这个 shim 已经做了同样的事，这里保证两种入口行为一致。
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_native_sys_path_bootstrap.py -q
```

Expected: PASS。

- [ ] **Step 5: 手工确认直接调用不再报错（不启动浏览器）**

```bash
python modules/utils/pwcli_native.py --help
```

Expected: 正常打印 usage，**无** `ModuleNotFoundError`。

- [ ] **Step 6: 提交**

```bash
git add modules/utils/pwcli_native.py backend/tests/test_pwcli_native_sys_path_bootstrap.py
git commit -m "fix(pwcli): 直接调用 modules/utils/pwcli_native.py 时补 sys.path 兜底

与 scripts/pwcli_native.py shim 的行为对齐，避免 --account-id 场景下
延迟导入 SessionManager 抛 ModuleNotFoundError"
```

---

## Task 5: 迁移 —— 别名表区域维度 + 内部标准名列 + 平台大小写归一

**Files:**
- Create: `current_migrations/versions/20261101_shop_identity_region_and_code.py`
- Modify: `modules/core/db/schema_parts/platform.py:165-248`（`ShopAccount` / `ShopAccountAlias`）
- Test: `backend/tests/test_shop_identity_schema_migration.py`（新建）

**背景**：
- `core.shop_account_aliases` 现有唯一约束 `UniqueConstraint("platform","alias_normalized","is_active")` → **同平台同一别名只能 active 一条** → 三个 `FIORO` 不可能同时归给三个店。
- 该约束**大小写敏感**，而别名表里 `platform` 同时存在 `'Shopee'`/`'shopee'`/`'Tiktok'`/`'tiktok'` → `'Shopee'` 与 `'shopee'` 可以同时 active 一个 `3c店`。
- PostgreSQL 默认 `UNIQUE` 语义是 **NULL 互不相等** → 存量 21 行 `shop_region` 全为 NULL 时约束形同虚设 → 必须用 `NULLS NOT DISTINCT`（PG 15.14 支持）。

**规模事实**（live 实测，动手前复核）：

```
core.shop_account_aliases: 21 行
core.shop_accounts: 52 行（enabled 20）
```

- [ ] **Step 1: 写迁移结构测试**

新建 `backend/tests/test_shop_identity_schema_migration.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "current_migrations" / "versions" / "20261101_shop_identity_region_and_code.py"


def test_migration_file_exists():
    assert MIGRATION.exists(), f"缺少迁移文件 {MIGRATION}"


def test_migration_adds_region_column_and_internal_code():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "shop_region" in text
    assert "internal_code" in text
    assert "NULLS NOT DISTINCT" in text, "别名唯一约束必须使用 NULLS NOT DISTINCT，否则 NULL 行互不冲突"


def test_orm_schema_has_internal_code_and_shop_region():
    text = (REPO_ROOT / "modules" / "core" / "db" / "schema_parts" / "platform.py").read_text(
        encoding="utf-8"
    )
    assert "internal_code" in text
    assert "shop_region" in text
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_shop_identity_schema_migration.py -q
```

Expected: 全部 FAIL（迁移文件不存在）。

- [ ] **Step 3: 写迁移文件**

创建 `current_migrations/versions/20261101_shop_identity_region_and_code.py`：

```python
"""Add shop identity region dimension and internal standard code.

对齐 spec docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md
的 D10 / D12：

- core.shop_account_aliases 增加 shop_region，使同平台同一别名可以在不同区域
  分别绑定到不同店铺账号（三个同名 FIORO 店铺的唯一锚点是 shop_account_id，
  区域是消歧维度）。
- 别名唯一约束改为 UNIQUE NULLS NOT DISTINCT，避免存量 NULL 区域行互不冲突。
- core.shop_account_aliases.platform 统一小写。
- core.shop_accounts 增加 internal_code（内部标准名，如 FIORO_SG）。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261101_shop_identity_region_and_code"
down_revision = "current_schema_20261028_drop_deprecated_traffic_fact_tables"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str, schema: str = "core") -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    return column in {c["name"] for c in inspector.get_columns(table, schema=schema)}


def _constraint_exists(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    for schema in ("core",):
        for table in ("shop_account_aliases", "shop_accounts"):
            for c in inspector.get_unique_constraints(table, schema=schema):
                if c.get("name") == name:
                    return True
    return False


def upgrade() -> None:
    # 第 1 步：平台大小写归一（必须先做，避免下一步加约束时冲突）。
    # 保留 is_active=true 且 is_primary=true 的那条；另一条降级为非 active 非 primary。
    op.execute(
        """
        UPDATE core.shop_account_aliases a
           SET is_active = false,
               is_primary = false
         WHERE a.platform IN ('Shopee', 'Tiktok')
           AND EXISTS (
                SELECT 1 FROM core.shop_account_aliases b
                 WHERE b.platform = lower(a.platform)
                   AND b.alias_normalized = a.alias_normalized
                   AND b.is_active = true
                   AND b.id <> a.id
           )
        """
    )
    op.execute("UPDATE core.shop_account_aliases SET platform = lower(platform) WHERE platform IN ('Shopee', 'Tiktok')")

    # 第 2 步：别名表加区域维度。
    if not _has_column("shop_account_aliases", "shop_region"):
        op.add_column(
            "shop_account_aliases",
            sa.Column("shop_region", sa.String(50), nullable=True),
            schema="core",
        )

    # 第 3 步：换唯一约束（NULLS NOT DISTINCT）。
    op.execute("ALTER TABLE core.shop_account_aliases DROP CONSTRAINT IF EXISTS uq_shop_account_aliases_active_alias")
    op.execute(
        """
        ALTER TABLE core.shop_account_aliases
          ADD CONSTRAINT uq_shop_account_aliases_active_alias
          UNIQUE NULLS NOT DISTINCT (platform, alias_normalized, shop_region, is_active)
        """
    )

    # 第 4 步：内部标准名列。
    if not _has_column("shop_accounts", "internal_code"):
        op.add_column(
            "shop_accounts",
            sa.Column("internal_code", sa.String(100), nullable=True),
            schema="core",
        )
        op.execute(
            """
            ALTER TABLE core.shop_accounts
              ADD CONSTRAINT uq_shop_accounts_platform_internal_code
              UNIQUE (platform, internal_code)
            """
        )

    # 第 5 步：别名表按店铺账号回填区域（能回填的回填，回填不了的留 NULL = 不限区域）。
    op.execute(
        """
        UPDATE core.shop_account_aliases a
           SET shop_region = s.shop_region
          FROM core.shop_accounts s
         WHERE s.id = a.shop_account_id
           AND a.shop_region IS NULL
           AND s.shop_region IS NOT NULL
           AND btrim(s.shop_region) <> ''
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE core.shop_accounts DROP CONSTRAINT IF EXISTS uq_shop_accounts_platform_internal_code")
    op.execute("ALTER TABLE core.shop_accounts DROP COLUMN IF EXISTS internal_code")
    op.execute("ALTER TABLE core.shop_account_aliases DROP CONSTRAINT IF EXISTS uq_shop_account_aliases_active_alias")
    op.execute(
        """
        ALTER TABLE core.shop_account_aliases
          ADD CONSTRAINT uq_shop_account_aliases_active_alias
          UNIQUE (platform, alias_normalized, is_active)
        """
    )
    op.execute("ALTER TABLE core.shop_account_aliases DROP COLUMN IF EXISTS shop_region")
```

- [ ] **Step 4: 同步 ORM SSOT**

在 `modules/core/db/schema_parts/platform.py`：

`ShopAccount`（:165-248）里，`platform_shop_id_status` 之前或 `store_name` 之后新增：

```python
    internal_code = Column(String(100), nullable=True, comment="内部标准名：同平台内唯一，带地区标识")
```

并在 `ShopAccount.__table_args__` 里加：

```python
        UniqueConstraint("platform", "internal_code", name="uq_shop_accounts_platform_internal_code"),
```

`ShopAccountAlias`（:221-248）里，新增：

```python
    shop_region = Column(String(50), nullable=True, comment="区域维度：同平台同别名可按区域绑定到不同店铺")
```

并把 `__table_args__` 里的约束从

```python
        UniqueConstraint("platform", "alias_normalized", "is_active", name="uq_shop_account_aliases_active_alias"),
```

改为**唯一索引**（不是 UniqueConstraint）：

```python
        Index(
            "uq_shop_account_aliases_active_alias",
            "platform",
            "alias_normalized",
            "shop_region",
            "is_active",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
```

> **为什么用 Index 而不是 UniqueConstraint**：仓库当前 SQLAlchemy 是 **2.0.41**，`UniqueConstraint.__init__` **不支持** `postgresql_nulls_not_distinct` 参数（已实测：`"postgresql_nulls_not_distinct" in inspect.signature(UniqueConstraint.__init__).parameters` → `False`）。只有 `Index` 支持该参数。
> 迁移脚本里用的是原生 SQL（`ALTER TABLE ... ADD CONSTRAINT ... UNIQUE NULLS NOT DISTINCT (...)`），与这里的 Index 定义语义一致。

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_shop_identity_schema_migration.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 在 live 库上跑迁移**

```bash
python -m alembic -c current_migrations/alembic.ini upgrade head
```

> 若仓库的 alembic 入口不同，先确认：`Get-ChildItem current_migrations -Filter "*.ini"`。**不要猜**，按实际配置文件执行。

Expected: 迁移成功，无报错。

- [ ] **Step 7: 核对迁移结果**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text('select platform, count(*) from core.shop_account_aliases group by 1 order by 1')):
        print('alias platform:', tuple(r))
    for r in c.execute(sa.text('select count(*) from core.shop_account_aliases where shop_region is null')):
        print('alias shop_region IS NULL:', tuple(r))
    for r in c.execute(sa.text('select count(*) from core.shop_accounts where internal_code is not null')):
        print('shop_accounts internal_code filled:', tuple(r))
"
```

Expected:
- `alias platform` 只出现小写（`shopee` / `tiktok`）；
- `alias shop_region IS NULL` 数量显著下降（能回填的都已回填）；
- `shop_accounts internal_code filled` = **0**（本 Task 只加列，标准名回填属第二批 ⑪）。

- [ ] **Step 8: 提交**

```bash
git add current_migrations/versions/20261101_shop_identity_region_and_code.py modules/core/db/schema_parts/platform.py backend/tests/test_shop_identity_schema_migration.py
git commit -m "feat(店铺身份): 别名表加区域维度，店铺账号加内部标准名列

- core.shop_account_aliases 增加 shop_region，唯一约束改 UNIQUE NULLS NOT DISTINCT
  （普通 UNIQUE 下 NULL 行互不冲突，存量 21 行会让约束形同虚设）
- 别名表 platform 统一小写，冲突时保留 active+primary 的那条
- core.shop_accounts 增加 internal_code，同平台内唯一
- 迁移落 current_migrations/versions/，down_revision 接 20261028 head"
```

---

## Task 6: 别名规范化统一（写侧与查侧必须一致）

**Files:**
- Modify: `backend/utils/text_normalization.py:68-76`（`normalize_alias_key`）
- Modify: `sql/semantic/shop_identity_resolution_candidates.sql:70-80`（store_name 规范化）
- Modify: `sql/semantic/orders_atomic.sql:467`（别名比对）
- Modify: `sql/semantic/analytics_atomic.sql`（同处）
- Test: `backend/tests/test_alias_normalization_consistency.py`（新建）

**背景（真 bug）**：

| 侧 | 规则 | `TK-新加坡-1店` | `Malaysia(Flora Mall)` |
|---|---|---|---|
| 写侧 Python `normalize_alias_key` | 小写+折叠空白+剥前缀+strip，**不删分隔符** | `-新加坡-1店` | `malaysia(flora mall)` |
| 查侧 SQL | 剥前缀 + 删 `[[:space:]_()/-]+` | `新加坡1店` | `malaysiafloramall` |

→ **认领了也可能永远匹配不上。** 现在 21 条别名恰好都是无分隔符的中文标签，两侧结果碰巧相同，才没暴露。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_alias_normalization_consistency.py`：

```python
from __future__ import annotations

import re
from pathlib import Path

from backend.utils.text_normalization import normalize_alias_key

REPO_ROOT = Path(__file__).resolve().parents[2]

CASES = [
    ("TK-新加坡-1店", "新加坡1店"),
    ("TK新加坡1店", "新加坡1店"),
    ("Malaysia(Flora Mall)", "malaysiafloramall"),
    ("Shopee3C店", "3c店"),
    ("3C店", "3c店"),
    ("xhkj1.my", "xhkj1my"),
]


def test_normalize_alias_key_matches_sql_semantics():
    """Python 侧规范化必须与 SQL 侧（剥前缀 + 删分隔符）完全一致。"""
    for raw, expected in CASES:
        assert normalize_alias_key(raw) == expected, f"{raw!r} -> {normalize_alias_key(raw)!r} != {expected!r}"


def test_normalize_alias_key_is_idempotent():
    """规范化必须幂等：normalize(normalize(x)) == normalize(x)。"""
    for raw, _ in CASES:
        once = normalize_alias_key(raw)
        assert normalize_alias_key(once) == once


def test_sql_assets_use_stored_alias_normalized():
    """直接引用别名表的 SQL 必须用存储的 alias_normalized。

    注：``analytics_atomic.sql`` 与 ``orders_monthly_atomic_mv.sql`` 走的是候选视图
    ``semantic.shop_identity_resolution_candidates``，不直接 JOIN 别名表，
    所以对这两个文件断言的是「引用了候选视图」。
    """
    for rel in (
        "sql/semantic/shop_identity_resolution_candidates.sql",
        "sql/semantic/orders_atomic.sql",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "saa.alias_normalized" in text, f"{rel} 未使用存储的 alias_normalized"

    for rel in (
        "sql/semantic/analytics_atomic.sql",
        "sql/semantic/orders_monthly_atomic_mv.sql",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "shop_identity_resolution_candidates" in text, f"{rel} 未引用候选视图"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_alias_normalization_consistency.py -q
```

Expected: `test_normalize_alias_key_matches_sql_semantics` 与 `test_normalize_alias_key_is_idempotent` FAIL。

- [ ] **Step 3: 改 Python 侧规范化**

把 `backend/utils/text_normalization.py:68-76` 的 `normalize_alias_key` 替换为：

```python
_ALIAS_PLATFORM_PREFIX_RE = re.compile(
    r"^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*",
    re.IGNORECASE,
)
_ALIAS_SEPARATOR_RE = re.compile(r"[\s_()/-]+")


def normalize_alias_key(value: str) -> str:
    """把原始导出标签规范化成匹配键。

    规则必须与 SQL 侧完全一致（剥平台前缀 -> 小写 -> 折叠空白 -> 删分隔符），
    否则「认领了却匹配不上」。唯一真源是本函数；SQL 侧只允许使用存储好的
    ``alias_normalized``，不得再做第二次规范化。

    Args:
        value: 原始标签，例如 ``TK-新加坡-1店``

    Returns:
        规范化后的匹配键，例如 ``新加坡1店``
    """
    text = str(value or "").strip()
    if not text:
        return ""
    text = _ALIAS_PLATFORM_PREFIX_RE.sub("", text, count=1)
    text = text.strip().lower()
    text = _ALIAS_SEPARATOR_RE.sub("", text)
    return text.strip()
```

> 若该文件已有 `import re`，无需新增；若没有，补上。

- [ ] **Step 4: 改 SQL 侧——只用存储值，不再二次规范化**

`sql/semantic/shop_identity_resolution_candidates.sql`：

- `alias_match` 分支的 `identity_value_normalized` 保持 `lower(TRIM(BOTH FROM saa.alias_normalized))`（这是对**存储值**做大小写/空白规整，不是二次规则）。
- `store_name_match` 分支（:70-80）的规范化改为与 Python 一致的表达式：

```sql
   regexp_replace(
     lower(
       trim(both from regexp_replace(
         trim(both from coalesce(active_shop_accounts.candidate_store_label, '')),
         '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
         '',
         'i'
       ))
     ),
     '[\s_()/-]+',
     '',
     'g'
   ) AS identity_value_normalized
```

`sql/semantic/analytics_atomic.sql` 与 `sql/semantic/orders_monthly_atomic_mv.sql` **不直接 JOIN 别名表**，它们走候选视图 `semantic.shop_identity_resolution_candidates` → **不需要改**（候选视图里已经用的是 `saa.alias_normalized`）。

`sql/semantic/orders_atomic.sql:467` 的别名比对条件：

```sql
                     OR LOWER(COALESCE(saa.alias_normalized, '')) = REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(COALESCE(d.store_label_raw, ''))), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'), '\s+', ' ', 'g')
```

改为（把原始标签规范化成与存储值同一套规则：剥前缀 → 小写 → 删分隔符）：

```sql
                     OR LOWER(COALESCE(saa.alias_normalized, '')) = REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(COALESCE(d.store_label_raw, ''))), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'), '[\s_()/-]+', '', 'g'), '\s+', ' ', 'g')
```

> **同时把 `:470` 的 ORDER BY 里的同一段表达式一并替换**（`:470` 的 `CASE WHEN LOWER(COALESCE(saa.alias_normalized, '')) = REGEXP_REPLACE(...)` 用的是旧规则，不改会导致"能命中但排序按旧规则"）。
> **本 Task 不动 `orders_atomic.sql` 的整体解析结构** —— 它在 Task 7 会被整体改成走候选视图。

> **实施者必须做的核对**：改完后，用 live 库验证「21 条存量别名的 `alias_normalized` 是否已符合新规则」。若不符合，需要一条数据订正脚本把存量值重算（**这一步会改变匹配行为，必须单独一个提交并说明**）。

- [ ] **Step 5: 核对存量别名的规范化值**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text('''select id, platform, alias_value, alias_normalized
        from core.shop_account_aliases order by id''')):
        print(tuple(r))
"
```

Expected: 每行的 `alias_normalized` 必须等于 `normalize_alias_key(alias_value)`。

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_alias_normalization_consistency.py backend/tests/test_shop_account_aliases_api.py -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/utils/text_normalization.py sql/semantic/shop_identity_resolution_candidates.sql sql/semantic/orders_atomic.sql sql/semantic/analytics_atomic.sql backend/tests/test_alias_normalization_consistency.py
git commit -m "fix(别名): 写侧与查侧规范化统一，认领了不再匹配不上

- normalize_alias_key 改为剥前缀 + 小写 + 删分隔符，与 SQL 侧完全一致
- SQL 侧只使用存储的 alias_normalized，消除双份规则
- 修复 TK-新加坡-1店 -> -新加坡-1店 与 SQL 的 新加坡1店 不一致"
```

---

## Task 7: 语义层多候选不静默归一（落 unknown + 告警码）

**Files:**
- Modify: `sql/semantic/shop_identity_resolution_candidates.sql`
- Modify: `sql/semantic/orders_atomic.sql:439-474`
- Modify: `sql/semantic/analytics_atomic.sql:175-229`
- Modify: `sql/semantic/orders_monthly_atomic_mv.sql:267-292`
- Test: `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py`（扩充）
- Test: `backend/tests/test_semantic_ambiguous_identity_sql.py`（新建）

**背景（spec §2.5）**：
- live 有**三套并存**的解析逻辑，全部 `LIMIT 1`。
- 两条路径的塌缩胜者还不同：`semantic.fact_orders_atomic` 路径 → SG 店；候选视图路径 → MY 店。
- 候选池**不按 `enabled` 过滤**（65/136 行来自 disabled 账号）——业务已决定**不排除**（停用只是暂时的），唯一性判定必须用**完整候选集**。

**判定口径（唯一真源，三条路径共用）**：

```
候选数 = 0  → shop_id = 'unknown', identity_warning_code = 'unmatched_shop_label'
候选数 = 1  → shop_id = 该店, identity_warning_code = NULL
候选数 >= 2 → shop_id = 'unknown', identity_warning_code = 'ambiguous_shop_label'
                identity_candidate_count = 候选数
                identity_candidates = 候选 shop_account_id 列表
```

**候选集定义**：与 `semantic.shop_identity_resolution_candidates` 视图一致 —— platform 相同 + `identity_value_normalized` 命中 `normalized_identity_candidates` 数组。**含 disabled 账号。**

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_semantic_ambiguous_identity_sql.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SQL_ASSETS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
    "sql/semantic/orders_monthly_atomic_mv.sql",
)


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_no_sql_asset_uses_bare_limit_1_on_identity():
    """三条语义路径都不允许再对身份候选直接 LIMIT 1。"""
    for rel in SQL_ASSETS:
        text = _text(rel)
        assert "ambiguous_shop_label" in text, f"{rel} 缺少 ambiguous_shop_label 告警码"
        assert "unmatched_shop_label" in text, f"{rel} 缺少 unmatched_shop_label 告警码"
        assert "identity_candidate_count" in text, f"{rel} 缺少 identity_candidate_count"


def test_candidate_view_exposes_region_dimension():
    """候选视图必须带上 shop_region 维度。"""
    text = _text("sql/semantic/shop_identity_resolution_candidates.sql")
    assert "shop_region" in text
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_semantic_ambiguous_identity_sql.py -q
```

Expected: FAIL。

- [ ] **Step 3: 在候选视图里带上区域维度**

`sql/semantic/shop_identity_resolution_candidates.sql` 的 `active_shop_accounts` CTE 里补一列：

```sql
            NULLIF(TRIM(BOTH FROM COALESCE(sa.shop_region, '')), '')::text AS candidate_shop_region,
```

并在 `alias_match` 分支的 SELECT 列表里带上 `active_shop_accounts.candidate_shop_region`。

> 视图的对外列变化会影响下游 SELECT 列表 —— **实施者必须同步更新三个 SQL 资产里引用该视图的列清单**，否则视图会因列数不匹配而报错。

- [ ] **Step 4: 三条语义路径统一判定逻辑**

**三条路径的现状（已核验，勿凭印象改）：**

| 文件 | 现状 | 关键位置 |
|---|---|---|
| `sql/semantic/orders_atomic.sql`（530 行） | **不走候选视图**，直接 `LATERAL` 扫 `core.shop_accounts sa` + `LEFT JOIN core.shop_account_aliases saa`，条件是 `store_name` 等值 **OR** `platform_shop_id` 等值 **OR** 别名匹配，`ORDER BY 别名命中 → is_primary → sa.id LIMIT 1` | `:451-474`（LATERAL）、`:462-467`（匹配条件）、`:469-473`（排序 + LIMIT 1） |
| `sql/semantic/analytics_atomic.sql`（328 行） | 走候选视图，`LATERAL` + `ORDER BY resolution_priority, resolved_shop_id LIMIT 1` | `:175-229` |
| `sql/semantic/orders_monthly_atomic_mv.sql`（317 行） | 走候选视图，`LATERAL` + `ORDER BY c.resolution_priority, c.resolved_shop_id LIMIT 1`；候选集合由 `mapped` 层的 `normalized_identity_candidates` 数组提供 | `:139-147`（LATERAL）、`:267-292` |

**4a. 先把 `orders_atomic.sql` 改成走候选视图（口径统一的前提）。**

`orders_atomic.sql` 是三条里唯一自己扫 `core.shop_accounts` 的，因此它的塌缩胜者（SG 店）与另两条（MY 店）不同。

改动要求：
1. 在 `mapped` CTE 里补出 `normalized_identity_candidates` 数组，**构造方式照抄 `sql/semantic/orders_monthly_atomic_mv.sql` 的 mapped 层**（候选来源 = `source_platform_shop_id` / `source_shop_account_id` / `source_shop_id`（排除 `xihong`/`unknown`/`none`）/ `source_shop_id_compact` / `normalized_store_label_raw`）。
   > `orders_atomic.sql` 当前**没有** `normalized_identity_candidates`（实测 0 次），`mapped` 层也没有 `normalized_store_label_raw` —— 这两个都要补。
2. 把 `:451-474` 的 LATERAL 换成扫 `semantic.shop_identity_resolution_candidates c`，条件 `c.platform_code = lower(d.platform_code) AND c.identity_value_normalized = ANY (d.normalized_identity_candidates)`。
3. 删掉 `orders_atomic.sql` 里对 `core.shop_account_aliases` 的直接 JOIN —— 别名匹配统一由候选视图的 `alias_match` 分支承担。
4. 保留原有的「`shop_id` 为 `''`/`none`/`unknown`/`xihong` 时落 `unknown`」兜底。

**4b. 三条路径的 LATERAL 改成「候选集合 + 计数」。**

以 `sql/semantic/orders_monthly_atomic_mv.sql:139-147` 为样板（三个文件做同样改动）：

```sql
         LEFT JOIN LATERAL (
             SELECT c.resolved_shop_id,
                    c.resolution_method,
                    c.resolution_priority,
                    c.resolved_shop_account_id,
                    count(*) OVER () AS candidate_count,
                    array_agg(c.resolved_shop_id ORDER BY c.resolution_priority, c.resolved_shop_id) AS candidate_shop_ids
               FROM semantic.shop_identity_resolution_candidates c
              WHERE c.platform_code = lower(COALESCE(d.platform_code, ''))
                AND (c.identity_value_normalized = ANY (d.normalized_identity_candidates))
              GROUP BY c.resolved_shop_id, c.resolution_method, c.resolution_priority, c.resolved_shop_account_id
             ) resolved ON TRUE
```

> `count(*) OVER ()` 在 `GROUP BY` 之后是**分组窗口计数**（不是 `count(*) OVER ()` 的默认整表计数），语义正确；`array_agg` 必须与 `GROUP BY` 的列一致。实施者**必须在 live 上先跑一次这条 SQL 验证语法**，不要直接部署。

然后把 `shop_id` 的 CASE 改成：

```sql
             CASE
                 WHEN resolved.candidate_count = 1 THEN resolved.resolved_shop_id
                 ELSE 'unknown'
             END AS shop_id,
```

并新增三列：

```sql
             CASE
                 WHEN resolved.candidate_count IS NULL OR resolved.candidate_count = 0 THEN 'unmatched_shop_label'
                 WHEN resolved.candidate_count > 1 THEN 'ambiguous_shop_label'
                 ELSE NULL
             END AS identity_warning_code,
             resolved.candidate_count AS identity_candidate_count,
             resolved.candidate_shop_ids::text AS identity_candidates,
```

> `identity_warning_code` / `identity_candidate_count` / `identity_candidates` 三列在 `fact_orders_atomic` 与 `fact_analytics_atomic` 上是**新增列**（`fact_orders_atomic` 现有 43 列），加列后必须同步：
> - 三个 SQL 资产各自的**最终 SELECT 列表**（`orders_atomic.sql` 的 `:477+`、`analytics_atomic.sql` 的最终 SELECT、`orders_monthly_atomic_mv.sql` 的最终 SELECT）；
> - 下游消费这些视图的 mart / api 层 SQL（`sql/mart/*`、`sql/api/*`）—— 若它们用了 `SELECT *` 则无需改；若是显式列表，需要补列；
> - `backend/schemas/` 下暴露这些字段的 Pydantic 契约（若有）。
>
> **实施者必须先 grep 全部下游引用**：`grep -rn "fact_orders_atomic" sql/ backend/ --include=*.sql --include=*.py`。

- [ ] **Step 5: 跑语义层 SQL 资产一致性测试**

```bash
python -m pytest backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_alias_sql_assets.py backend/tests/test_semantic_ambiguous_identity_sql.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add sql/semantic/ backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_ambiguous_identity_sql.py
git commit -m "feat(语义层): 多候选不再静默归一，落 unknown + 告警码

- 三条语义路径统一判定：候选 1 才归属，候选 0 落 unmatched_shop_label，
  候选 >=2 落 ambiguous_shop_label 并输出 identity_candidate_count / identity_candidates
- 候选集含 disabled 账号（业务确认停用只是暂时的，唯一性判定用完整候选集）
- 候选视图带上 shop_region 维度"
```

---

## Task 8: 语义层部署到 live + MV 刷新 + 前后对比

**Files:**
- Modify: `sql/semantic/orders_atomic.sql` / `analytics_atomic.sql` / `orders_monthly_atomic_mv.sql`（若上一步已同步则无改动）
- 无新文件

**背景**：`semantic.fact_orders_atomic` / `fact_analytics_atomic` 是 **VIEW**（改定义即时生效）；`semantic.fact_orders_monthly_atomic_mv` 是 **MATVIEW**（改定义后必须 `REFRESH MATERIALIZED VIEW` 才生效），`semantic.fact_orders_monthly_atomic` 是它的薄封装 VIEW。

- [ ] **Step 1: 先在 live 上重建三个对象**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.begin() as c:
    for rel in (
        'sql/semantic/shop_identity_resolution_candidates.sql',
        'sql/semantic/orders_atomic.sql',
        'sql/semantic/analytics_atomic.sql',
        'sql/semantic/orders_monthly_atomic_mv.sql',
    ):
        sql = open(rel, encoding='utf-8').read()
        c.execute(sa.text(sql))
        print('applied', rel)
"
```

Expected: 四个对象全部重建成功，无报错。

> **若某个 SQL 文件里含 `DROP ... IF EXISTS` + `CREATE`，直接整段执行即可。若含 alembic 风格的占位符，先按仓库既有部署脚本的方式处理（`Get-ChildItem scripts -Filter "*semantic*"`）。**

- [ ] **Step 2: 刷新 MATVIEW**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.begin() as c:
    c.execute(sa.text('REFRESH MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv'))
    print('refreshed')
"
```

Expected: 打印 `refreshed`。

- [ ] **Step 3: 与 Task 0 的基线对比**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text(\"select shop_id, count(*) from semantic.fact_orders_atomic where platform_code='tiktok' group by 1 order by 2 desc\")):
        print(tuple(r))
    print('--- warning codes ---')
    for r in c.execute(sa.text(\"select identity_warning_code, count(*) from semantic.fact_orders_monthly_atomic group by 1 order by 2 desc\")):
        print(tuple(r))
"
```

Expected（对照 Task 0 Step 3 的基线）:
- 六个 `tiktok_*_local` 的行数**保持不变**；
- `unknown` 的行数**不增加**（候选唯一的行仍唯一命中）；
- 若 `unknown` 增加了，说明某处候选口径被改宽了 → **必须查明原因再继续**。

- [ ] **Step 4: 验证多候选确实落 unknown 而不是归第一**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text('''
        select identity_warning_code, shop_id, count(*)
          from semantic.fact_orders_monthly_atomic
         where identity_warning_code is not null
         group by 1,2 order by 3 desc''')):
        print(tuple(r))
"
```

Expected: `unmatched_shop_label` 对应 `unknown`；`ambiguous_shop_label` 数量为 0 或极少（当前无同名店）。

- [ ] **Step 5: 提交（若上一步有改动）**

```bash
git add sql/semantic/
git commit -m "chore(语义层): 部署新的身份判定逻辑并刷新 MATVIEW"
```

> 若本 Task 无文件改动，跳过提交，但**必须在最终汇报里贴出 Step 3 的前后对比**。

---

## Task 9: 补齐 `catalog_files` 的店铺账号（data_hash 口径切换的前置）

**Files:**
- Modify: 采集入库链路中写 `catalog_files` 的位置（**实施者必须先定位**：`grep -rn "shop_account_id" backend/services/ modules/ --include=*.py`）
- Test: `backend/tests/test_catalog_file_identity_backfill.py`（新建）

**背景（live 实测）**：

| platform_code | 总行 | `platform_shop_id` 有值 | `shop_account_id` 有值 | `shop_id` 有值 |
|---|---|---|---|---|
| shopee | 332 | 0 | 49 | 332 |
| tiktok | 124 | 0 | 34 | 124 |
| miaoshou | 4 | 0 | 4 | 4 |
| 合计 | 460 | **0/460** | **87/460** | 460/460 |

`backend/services/data_ingestion_service.py:494-495` 读的是 `file_record.shop_id`（= `'xihong'` 这类账号级值），`data_hash` 作用域（:627-637）用的也是它 → **同一份数据改名后会重复入库**。
**必须先把 `catalog_files.shop_account_id` 补齐，再改 `data_hash` 口径**，否则切换瞬间会造成全量历史行重复。

- [ ] **Step 1: 定位写 `catalog_files` 的代码**

```bash
grep -rn "shop_account_id" backend/services/ backend/domains/ modules/ --include=*.py | Select-String -Pattern "catalog|CatalogFile"
```

Expected: 找到设置 `CatalogFile.shop_account_id` / `store_name` / `platform_shop_id` 的位置。

- [ ] **Step 2: 写失败测试**

新建 `backend/tests/test_catalog_file_identity_backfill.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ingestion_resolves_shop_account_id_for_catalog_files():
    """入库时必须能确定 catalog_files.shop_account_id，否则 data_hash 口径无法切换。"""
    candidates = list((REPO_ROOT / "backend").rglob("*.py"))
    hit = [
        p
        for p in candidates
        if "catalog_files" in p.read_text(encoding="utf-8", errors="ignore")
        and "shop_account_id" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert hit, "没有找到写入 catalog_files.shop_account_id 的代码"
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_catalog_file_identity_backfill.py -q
```

Expected: FAIL（`hit` 为空）。

- [ ] **Step 4: 实现回填**

在写 `catalog_files` 的位置，按以下优先级确定 `shop_account_id`：

1. 采集任务上下文里已知的 `shop_account_id`（采集任务本身是按店铺账号发起的 → **这是主路径**）；
2. 否则用 `file_metadata` 里的 `(platform, store_name, shop_region)` 或 `(platform, alias)` 反查 `core.shop_accounts`；
3. 都不是 → 保持 NULL（**不猜**）。

> **实施者必须确认**：采集任务发起时是否携带 `shop_account_id`。若携带（`backend/domains/collection/routers/collection_tasks.py:1837-1850` 组装 `shop_payload` 时有 `main_account_id` / `shop_account_id`），则主路径已经可用，只需补齐「老数据回填」。
>
> 老数据回填脚本（一次性，放在 `backend/services/` 或 `scripts/`，**遵循"不新增根目录临时脚本"约束**）：
> - 依据 `catalog_files.file_metadata` / `meta_file_path` 里的店铺标签 + 平台 + 站点反查 `core.shop_accounts`；
> - 命中唯一 → 回填；命中 0 个或多个 → 留 NULL 并记入待处理清单。

- [ ] **Step 5: 跑一次回填并核对覆盖率**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text('''select platform_code, count(*) total,
        count(*) filter (where shop_account_id is not null and shop_account_id<>'') filled
        from public.catalog_files group by 1 order by 2 desc''')):
        print(tuple(r))
"
```

Expected: `filled` 显著高于 87（基线）。**达不到 460/460 也没关系**，但必须把「仍为 NULL 的文件」列成清单交业务确认，不要为了凑数乱填。

- [ ] **Step 6: 运行测试确认通过 + 提交**

```bash
python -m pytest backend/tests/test_catalog_file_identity_backfill.py -q
git add backend/ scripts/ backend/tests/test_catalog_file_identity_backfill.py
git commit -m "feat(入库): 补齐 catalog_files 的店铺账号身份

shop_account_id 覆盖从 87/460 提升，platform_shop_id 在文件层 0/460 完全不可用。
这是 data_hash 口径切到稳定身份编号的前置条件（否则切换瞬间全量历史行重复）。"
```

---

## Task 10: `data_hash` 口径切到稳定身份编号

**Files:**
- Modify: `backend/services/data_ingestion_service.py:485-519`、`:627-637`
- Test: `backend/tests/test_data_ingestion_hash_identity.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_data_ingestion_hash_identity.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "backend" / "services" / "data_ingestion_service.py"


def test_hash_scope_uses_stable_identity_not_raw_shop_id():
    """data_hash 作用域必须用稳定身份编号，不能用会随改名变化的 shop_id。"""
    text = TARGET.read_text(encoding="utf-8")
    assert "shop_account_id" in text, "入库链路没有使用 shop_account_id 作为身份"
    hash_scope = text.split("hash_scope_values = {", 1)[1].split("}", 1)[0]
    assert "file_shop_id" not in hash_scope, "data_hash 作用域仍在使用 file_shop_id"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_data_ingestion_hash_identity.py -q
```

Expected: FAIL。

- [ ] **Step 3: 改文件级身份字段填充**

把 `backend/services/data_ingestion_service.py:493-519` 替换为：

```python
                # 文件级别确定稳定身份编号（spec D14）。
                # 优先级：shop_account_id（永不变化，全平台覆盖） > platform_shop_id > shop_id。
                # file_shop_id 会随改名变化，用它做 data_hash 作用域会导致同一份数据重复入库。
                file_shop_account_id = getattr(file_record, "shop_account_id", None) or None
                file_platform_shop_id = getattr(file_record, "platform_shop_id", None) or None
                file_shop_id = (
                    file_shop_account_id
                    or file_platform_shop_id
                    or file_record.shop_id
                    or "none"
                )
                file_main_account_id = getattr(file_record, "main_account_id", None)
                file_store_name = getattr(file_record, "store_name", None)
```

（注意：删除了原来的 `file_shop_account_id = getattr(file_record, "shop_account_id", None)`，避免变量重名。）

- [ ] **Step 4: 改 `data_hash` 作用域**

把 `:627-637` 的 `hash_scope_values` 替换为：

```python
                    hash_scope_values = {
                        "platform_code": (
                            file_platform_code
                            if "file_platform_code" in locals()
                            else platform
                        ),
                        "shop_account_id": (
                            file_shop_account_id
                            if "file_shop_account_id" in locals()
                            else None
                        ),
                        "platform_shop_id": (
                            file_platform_shop_id
                            if "file_platform_shop_id" in locals()
                            else None
                        ),
                        "shop_id": file_shop_id if "file_shop_id" in locals() else None,
                        "data_domain": domain,
                        "granularity": granularity,
                        "sub_domain": sub_domain,
                    }
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_data_ingestion_hash_identity.py -q
```

Expected: PASS。

- [ ] **Step 6: 验证不产生重复入库**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for r in c.execute(sa.text('''select platform_code, shop_id, count(*) n, count(distinct data_hash) d
        from b_class.fact_tiktok_orders_monthly group by 1,2 order by 3 desc limit 10''')):
        print(tuple(r))
"
```

Expected: `n == d`（同一 shop_id 下没有两个不同 data_hash 指向同一份数据）。若不等，说明口径切换前后各留了一版 → **需要一次全量重建**（`RefreshQueueService`），再对比。

- [ ] **Step 7: 提交**

```bash
git add backend/services/data_ingestion_service.py backend/tests/test_data_ingestion_hash_identity.py
git commit -m "fix(入库): data_hash 口径改用稳定身份编号，避免改名后重复入账

- 文件级身份优先级改为 shop_account_id > platform_shop_id > shop_id
- hash 作用域新增 shop_account_id / platform_shop_id，shop_id 不再单独决定去重"
```

---

## Task 11: 待认领清单在面板可见（`TK新加坡3C店`）

**Files:**
- Modify: `backend/domains/collection/routers/shop_account_aliases.py:49-111`（`_UNMATCHED_ALIAS_QUERY`）
- Modify: `frontend/src/domains/platform/views/AccountManagement.vue:12-30`（未匹配别名告警面板）
- Test: `backend/tests/test_shop_account_aliases_api.py`（扩充）

**业务决定**：`TK新加坡3C店`（monthly 88 行 / atomic unknown 90 行）**暂不认领**，保持 `unknown`，但必须在面板上**看得见**并说清为什么不能直接认领。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_shop_account_aliases_api.py` 末尾追加：

```python
def test_unmatched_alias_list_includes_occurrence_counts():
    """未匹配别名清单必须带上出现次数，让运营知道这条数据有多大。"""
    from backend.domains.collection.routers.shop_account_aliases import _UNMATCHED_ALIAS_QUERY

    sql = " ".join(_UNMATCHED_ALIAS_QUERY.split())
    assert "count(" in sql.lower(), "未匹配别名查询缺少出现次数统计"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_shop_account_aliases_api.py -q -k "unmatched_alias_list"
```

Expected: FAIL。

- [ ] **Step 3: 在未匹配别名查询里补出现次数与候选提示**

在 `backend/domains/collection/routers/shop_account_aliases.py` 的 `_UNMATCHED_ALIAS_QUERY` 里补：

- 出现次数统计（按 `(店铺标签, 站点)` 从 raw 层计数）；
- 候选提示（例如「该平台下 N 个店铺账号已被其它标签 1:1 占满，需新建店账号才能认领」）。

> **实施者必须先确认**未匹配别名的来源表与字段。live 上 TikTok 订单的原始标签在 `b_class.fact_tiktok_orders_monthly.raw_data->>'店铺'`，站点在 `raw_data->>'站点'`（**不是**物化列 —— 物化列有 191 行 NULL）。

- [ ] **Step 4: 前端展示**

在 `frontend/src/domains/platform/views/AccountManagement.vue` 的「未匹配店铺别名」告警面板里，加上：出现次数、站点、以及「暂不认领」的说明。样式沿用文件里已有的告警样式。

- [ ] **Step 5: 运行测试 + 构建**

```bash
python -m pytest backend/tests/test_shop_account_aliases_api.py -q
cd frontend; npm run build
```

Expected: 测试 PASS；构建成功。

- [ ] **Step 6: 提交**

```bash
git add backend/domains/collection/routers/shop_account_aliases.py frontend/src/domains/platform/views/AccountManagement.vue backend/tests/test_shop_account_aliases_api.py
git commit -m "feat(店铺身份): 未匹配别名清单带上出现次数与候选提示

TK新加坡3C店 按业务决定暂不认领，保持 unknown 并在面板可见，
说清「现有 TikTok 店已被其它标签 1:1 占满，需新建店账号才能认领」。"
```

---

## 12. 第一批总验收

- [ ] **Step 1: 跑全量相关测试**

```bash
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_session_manager_protection.py backend/tests/test_shop_account_aliases_api.py backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_alias_sql_assets.py backend/tests/test_alias_normalization_consistency.py backend/tests/test_semantic_ambiguous_identity_sql.py backend/tests/test_shop_identity_schema_migration.py backend/tests/test_catalog_file_identity_backfill.py backend/tests/test_data_ingestion_hash_identity.py backend/tests/test_pwcli_helpers_session_targeting.py backend/tests/test_pwcli_inspection_panel_reporting.py backend/tests/test_pwcli_native_sys_path_bootstrap.py -q
```

Expected: 全部 PASS，且**不少于 Task 0 Step 2 的基线通过数**。

- [ ] **Step 2: 核对 spec 第一批验收项**

| 验收项 | 验证方式 | 结果 |
|---|---|---|
| A1 会话保存写盘 | 面板点「保存会话」后检查 `data/sessions/<platform>/<净化owner>/storage_state.json` 的 `metadata.saved_at` 与 `metadata.manual_seeded` | |
| A2 失败可见 | `pwcli --session no-such-session-xyz state-save` 退出码 ≠ 0；面板日志可见 stderr | |
| A3 读写同路径 | Task 1 的测试 + 磁盘核对 | |
| A5 稳定编号落库 | Task 10 Step 6 | |
| A6 不静默错配 | Task 8 Step 3/4 | |
| A7 告警码词表 | Task 8 Step 4 | |
| A8 别名可认领 | Task 6 Step 5 | |
| A9 平台大小写 | Task 5 Step 7 | |
| A10 别名区域维度 | Task 5 Step 7 + `FIORO` 可挂三店的手工验证 | |
| A14 待认领清单 | Task 11 | |

- [ ] **Step 3: 同步镜像并合入**

按 `docs/guides/RELEASE_CHECKLIST.md` 与 `scripts/sync_main_mirrors.ps1` 的流程走。**不要直接 push main。**

- [ ] **Step 4: 更新 plan 完成状态**

在 `docs/superpowers/plans/STATUS.md` 记录本计划已完成，并注明第二批计划的入口。

---

## 13. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| Task 5 迁移在 live 上加唯一约束时存量数据冲突 | 迁移失败 | 迁移里先归一 platform 再加约束；加约束前用只读 SQL 预检冲突行 |
| Task 6 改别名规范化后存量 `alias_normalized` 与新规则不一致 | 匹配行为变化 | Task 6 Step 5 强制核对；不一致时**单独一个提交**做数据订正 |
| Task 7 改语义层判定后 `unknown` 行数上升 | 数据归属变少 | Task 8 Step 3 与基线对比；`unknown` 增加即视为回归，必须查明原因 |
| Task 8 在 live 上重建视图 | 生产语义层短暂不可用 | 在停机窗口执行；执行前先 `pg_dump` 相关视图定义 |
| Task 10 切 `data_hash` 口径造成新旧行并存 | 短期重复计数 | Task 9 必须先完成；切换后触发一次全量 semantic 重建并前后对比 |
| Task 2/3 改动影响现有面板使用者 | 操作习惯变化 | 面板 UI 不变，只是失败时显示更多信息 |

**回滚**：每个 Task 都是独立提交，`git revert <commit>` 即可单独回退。Task 5 与 Task 8 涉及数据库对象，回滚需要对应的 `downgrade()` 或 `DROP ... CREATE`。

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
| D10a 别名表区域维度（落库与约束） | Task 5 | A10 |
| D12 平台大小写归一 | Task 5 | A9 |
| D11 别名规范化统一 | Task 6 | A8 |
| D13 多候选落 unknown + 告警码 | Task 7 Task 8 | A6 A7 |
| D14 稳定身份编号落库 | Task 9 Task 10 | A5 |
| A14 待认领清单 | Task 11 | A14 |
| D6 采集优先使用人工保存的会话 | Task 12 | A4 |

### 0.2 明确不在本计划范围（属第二批 / 独立计划）

- 第二批全部：③一账号一巡店窗口、④账号标识唯一化、⑦曾用名、⑨改名后按站点重认、⑪内部标准名前端、⑫会话新鲜度与持久化、⑬改名联动。
  → **A11 / A12 / A13 按 spec §6 归第二批**（spec §8 把它们列在「第一批」小节里，是 spec 自身的编排出入；
  本计划以 spec §6 的批次划分为准）。
- **D10b 区域感知匹配**（用「站点 → 区域」映射让 `FIORO` + 站点正确分流到三个店）→ 属第二批 ⑨。
  本批次只做 D10a（别名表加列与约束）—— 加完列之后同名别名会产生多个候选，
  由 Task 7 的判定逻辑落成 `unknown` + `ambiguous_shop_label`，**不会静默错配**，是安全状态。
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
Task 12                                  （采集侧优先用人工会话，独立）
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


def _save_helper_block() -> str:
    text = _read(HELPERS)
    return text.split("function Save-PwcliPlatformState", 1)[1].split("\nfunction ", 1)[0]


def test_launcher_propagates_exit_code():
    """pwcli.ps1 必须把 python 的退出码传给调用方，否则失败会被当成成功。"""
    text = _read(LAUNCHER)
    assert re.search(r"exit\s+\$LASTEXITCODE", text), "pwcli.ps1 缺少 exit $LASTEXITCODE"


def test_save_helper_accepts_work_tag():
    """保存函数必须能按账号定位会话，不能只依赖环境变量。"""
    block = _save_helper_block()
    assert "WorkTag" in block, "Save-PwcliPlatformState 缺少 -WorkTag 参数"
    assert '"$platformName-$WorkTag"' in block, "保存函数没有用 platform+WorkTag 拼 session 名"


def test_save_helper_throws_on_nonzero_exit():
    """保存失败必须抛错，让调用方拿到非 0 退出码。"""
    block = _save_helper_block()
    assert "$LASTEXITCODE" in block
    assert "throw" in block


def test_save_helper_rejects_unresolvable_session():
    """既没有 -WorkTag、又没有活动会话时必须报错，不能静默退回 session=default。"""
    block = _save_helper_block()
    assert "cannot locate the browser session" in block, (
        "定位不到会话时必须报错（否则会退回 pwcli state-save -> session=default -> 断点 A）"
    )
    assert "Get-PwcliActiveSession" in block, "必须复用既有 Get-PwcliActiveSession 解析活动会话"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_helpers_session_targeting.py -q
```

Expected: **4 个 FAIL**（分别缺 `exit $LASTEXITCODE`、缺 `-WorkTag`、缺 `$LASTEXITCODE`/`throw` 检查、缺「定位不到会话」的报错）。
（Step 6b 之后本文件共 5 条用例。）

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

    if ($AccountId) {
        # 手工 SOP 形态（同一个 shell 里先 open 再 save）：
        # Open-PwcliPlatform 会把 $env:PLAYWRIGHT_CLI_SESSION 设成 "$platformName-$WorkTag"，
        # 这里直接复用既有的 Get-PwcliActiveSession 解析（今天这条路径就是好的，见 Step 5c）。
        $session = Get-PwcliActiveSession
        if (-not $session) {
            # 既没有 -WorkTag、又没有活动会话 -> 定位不到会话。
            # 这里必须报错：再往下走会退化成 `pwcli state-save`，
            # session 被解析成 "default" 并失败（正是 spec 断点 A）。
            throw "Save-PwcliPlatformState cannot locate the browser session for account '$AccountId': pass -WorkTag, or open the session in this shell first"
        }
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

- [ ] **Step 5b: 调用方必须真的把 `-WorkTag` 传进来（否则断点 A 原样保留）**

> **这是 Task 2 最容易被漏掉的一步。** 现有两个调用方都**没有**传 `-WorkTag`：
> - `scripts/pwcli_inspection_panel.py:129-134`（save 分支）拼的是 `Save-PwcliShopeeState -AccountId '<id>'`；
> - `scripts/pwcli_helpers.ps1:479-485`（巡店循环）拼的是 `Save-Pwcli*State -AccountId $account.account_id`。
>
> 对比 open 分支：`pwcli_inspection_panel.py:122-123` 与 `pwcli_helpers.ps1:451-457` **是**带 `-WorkTag` 的 —— 照抄它们的写法即可。

**5b-1 改面板。** 把 `scripts/pwcli_inspection_panel.py:129-134` 的 save 分支替换为：

```python
    elif action == "save":
        helper = SAVE_HELPERS.get(platform)
        if not helper:
            raise ValueError(f"Unsupported platform: {platform}")
        command = (
            utf8_prefix
            + f"Set-Location -LiteralPath '{quote_ps(str(repo_root))}'; "
            + f". '{quote_ps(str(repo_root / 'scripts' / 'pwcli_helpers.ps1'))}'; "
            + f"{helper} -AccountId '{quote_ps(str(account['account_id']))}' "
            + f"-WorkTag '{quote_ps(str(account['work_tag']))}'"
        )
```

**5b-2 改巡店循环。** `scripts/pwcli_helpers.ps1:477-491` 是 `switch ($account.platform)` 的**三个字面分支**
（**没有 `$PlatformName` 这个变量** —— 全文件 grep 0 命中；照字面写 `$($PlatformName)` 会得到
`Save-PwcliState` 这个空函数名 → 保存静默失败，正是本 Task 要消灭的"失败不可见"）。

把三个分支改成：

```powershell
        switch ($account.platform) {
            "miaoshou" {
                Save-PwcliMiaoshouState -AccountId $account.account_id -WorkTag $account.work_tag
            }
            "shopee" {
                Save-PwcliShopeeState -AccountId $account.account_id -WorkTag $account.work_tag
            }
            "tiktok" {
                Save-PwcliTiktokState -AccountId $account.account_id -WorkTag $account.work_tag
            }
            default {
                Write-Warning "Unsupported platform: $($account.platform)"
                continue
            }
        }
```

> **work_tag 从哪来**：`scripts/pwcli_account_inventory.py:54-55` 的 `work_tag(platform, account_id)`
> 与 `:111` 把 `work_tag` 放进账号字典 → 巡店循环里的 `$account.work_tag` 就是同一个值。
> 实施者必须**先读** `scripts/pwcli_helpers.ps1:440-495` 的实际变量名与 open 分支写法，
> 照抄同文件 open 分支（`:451-457` 附近）的形态，不要凭空造变量名。

- [ ] **Step 5c: 确认既有调用形态不受影响（文档 / 生成器 / SOP）**

> **为什么要有这一步**：本 Task 早期方案是「有 `-AccountId` 但缺 `-WorkTag` 就直接 `throw`」。
> 实测那样会打断**现有文档与生成脚本里的调用形态**（全部不带 `-WorkTag`）：
> - `docs/guides/PWCLI_MANUAL_SHOP_INSPECTION.md:119,151,163`
> - `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md:44-45`
> - `docs/guides/PWCLI_AGENT_COLLECTION_SOP.md:426-428`
> - `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`（多处，由 `scripts/generate_pwcli_account_commands.py:137,145,153` 生成）
>
> 这些都是**手工 SOP 形态**：同一个 PowerShell 会话里先
> `Open-PwcliShopee -WorkTag <tag> -AccountId '<id>'`
> （`Open-PwcliPlatform` 会把 `$env:PLAYWRIGHT_CLI_SESSION` 设成 `"$platformName-$WorkTag"`），
> 再 `Save-PwcliShopeeState -AccountId '<id>'`。这条路径**今天就是好的**，不能被新改动打断。
>
> → 所以 Step 4 的 `throw` 条件是「**既没有 `-WorkTag`、又没有活动会话**」，
> 而不是「缺 `-WorkTag` 就报错」。活动会话由既有的 `Get-PwcliActiveSession` 解析。

**只读核对（不改任何文档）**：

```bash
python -m pytest tests/test_pwcli_inspection_panel.py tests/test_pwcli_daily_inspection_helpers.py -q
```

Expected: 全部 PASS（这两个文件断言的是 helper 名字与调用形态，本 Task 不改它们）。

**手工确认既有 SOP 形态仍然可用**（同一个 shell 内）：

```powershell
. .\scripts\pwcli_helpers.ps1
Open-PwcliShopee -WorkTag explore -AccountId 'hongxikeji:main'
# 浏览器打开、人工操作完成后，在**同一个** shell 里执行：
Save-PwcliShopeeState -AccountId 'hongxikeji:main'
```

Expected: **不再**抛 `requires -WorkTag`；若确实定位不到会话，错误信息是
`Save-PwcliPlatformState cannot locate the browser session for account '...'`（可操作），
而不是 `No browser session found for 'default'`（不可操作）。

**本 Task 不改任何 `docs/` 文件** —— 文档与生成脚本的调用形态保持不变。
（第二轮复核已确认 `docs/generated/PWCLI_ACCOUNT_COMMANDS.md` 是生成物，
真要改生成模板时走 `scripts/generate_pwcli_account_commands.py`；本轮不需要。）

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_pwcli_helpers_session_targeting.py -q
```

Expected: 全部 PASS（共 5 条：Step 1 的 4 条 + Step 6b 的 1 条）。

- [ ] **Step 6b: 补一条「调用方确实传了 -WorkTag」的测试**

在 `backend/tests/test_pwcli_helpers_session_targeting.py` 里追加：

```python
def test_panel_save_command_passes_work_tag():
    """面板的保存命令必须带上 -WorkTag，否则 session 又会退回 default。"""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from pwcli_inspection_panel import build_pwcli_action_command

    account = {
        "platform": "shopee",
        "account_id": "hongxikeji:main",
        "work_tag": "shopee-hongxikeji-main-inspect",
        "display_name": "hongxikeji:main",
    }
    command = build_pwcli_action_command("save", account, REPO_ROOT)
    joined = " ".join(command)
    assert "-WorkTag" in joined, "面板保存命令缺少 -WorkTag"
    assert "shopee-hongxikeji-main-inspect" in joined, "面板保存命令没有传具体 work_tag"
```

- [ ] **Step 7: 实跑验证退出码传播（只读，不启动浏览器）**

**注意命令写法**：不能带尾部 `; exit $LASTEXITCODE`（那会让 `$LASTEXITCODE` 从内层脚本传出来，修复前后都返回非 0，验证不了差异）。要**直接看进程退出码**：

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/pwcli.ps1 --session no-such-session-xyz state-save
echo "exit code = $LASTEXITCODE"
```

Expected:
- 打印 `No browser session found for 'no-such-session-xyz'`；
- **`exit code` ≠ 0**。

> 修复前同样这条命令的 `exit code` 是 0（已实测）→ 修复前后可区分。

- [ ] **Step 8: 提交**

```bash
git add scripts/pwcli.ps1 scripts/pwcli_helpers.ps1 scripts/pwcli_inspection_panel.py backend/tests/test_pwcli_helpers_session_targeting.py
git commit -m "fix(巡店): 保存会话按账号定位，并让失败真正返回非 0 退出码

- pwcli.ps1 补 exit \$LASTEXITCODE，失败不再被当成成功
- Save-PwcliPlatformState 新增 -WorkTag，session 名与 Open-PwcliPlatform 完全一致
- 调用方补齐 -WorkTag：巡店面板 save 分支与 helpers 巡店循环
  （此前只改函数签名、调用方不传，session 仍会退回 default，断点 A 原样保留）
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
    """前端日志必须渲染 result.message（真实 stdout/stderr），不能只有 result.status。

    注意：断言必须写 ``result.message``（精确），不能写 ``.message`` —— 后者会被
    文件里已有的 ``error.message`` 命中，测试就成了永远通过的空守卫。
    """
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert "result.status" in text, "前端未渲染 result.status"
    assert "result.message" in text, "前端未渲染 result.message"

    matched = [line for line in text.splitlines() if "result.message" in line]
    assert matched, "未找到渲染 result.message 的语句"
    assert any("result.status" in line for line in matched), (
        "result.message 与 result.status 不在同一条日志里，失败信息仍会被丢掉"
    )


def test_panel_success_response_includes_message():
    """成功时也必须把 stdout 带回来，否则前端没有可显示的内容。"""
    text = PANEL_PY.read_text(encoding="utf-8")
    assert "combined_output" in text, "成功分支没有把 stdout/stderr 合并进 message"
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

`scripts/pwcli_inspection_panel_static/index.html:311-324` 的 `runAction` 现在长这样：

```javascript
    async function runAction(action, account) {
      try {
        const result = await api(`/api/accounts/${action}`, {
          method: 'POST',
          body: JSON.stringify({ platform: account.platform, account_id: account.account_id }),
        });
        const index = accounts.findIndex((item) => item.platform === result.platform && item.account_id === result.account_id);
        if (index >= 0) accounts[index] = result;
        render();
        addLog(`${account.display_name} ${action} -> ${result.status}`);
      } catch (error) {
        addLog(`${account.display_name} ${error.message}`);
      }
    }
```

改成（**沿用文件里已有的 `addLog(...)` 与 `action` 变量名**，不要新造辅助函数）：

```javascript
        addLog(`${account.display_name} ${action} -> ${result.status}` + (result.message ? `\n${result.message}` : ''));
      } catch (error) {
        addLog(`${account.display_name} ${action} -> error\n${(error && error.message) || '未知错误'}`);
      }
```

> 说明：`api()`（`index.html:247-257`）在非 2xx 时抛的是 `new Error(payload.detail || ...)`，而 Task 3 Step 3 让后端把 `detail` 设成真实 stderr → **失败路径的 `error.message` 已经是真实原因**。
> 本 Step 要补的是**成功路径**：把 `result.message`（后端合并的 stdout）也显示出来，让运营看到"保存到哪个文件"。

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
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_probe(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    probe = REPO_ROOT / "modules" / "utils" / "pwcli_native.py"
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, "-c", code, str(probe), *args],
            cwd=tmp,  # 关键：CWD 不在仓库根，否则仓库根会通过 CWD 混进 sys.path
            capture_output=True,
            text=True,
            timeout=180,
        )


def test_direct_script_launch_can_import_modules_package():
    """直接以脚本方式启动时，必须能 import 到 `modules.*`。

    这是生产故障的精确复现：`python modules/utils/pwcli_native.py ... --account-id X`
    时 `sys.path[0]` 是 `modules/utils`，不含仓库根 →
    `modules/utils/pwcli_native.py:320` 的延迟导入
    `from modules.utils.sessions.session_manager import SessionManager`
    抛 `ModuleNotFoundError: No module named 'modules'`。

    探针把 CWD 放在**临时目录**（不在仓库根），
    否则 `python -m pytest` 的 CWD 兜底会让这条断言今天就通过（已实测）。
    """
    code = (
        "import runpy, sys\n"
        "runpy.run_path(sys.argv[1], run_name='pwcli_probe')\n"
        "from modules.utils.sessions.session_manager import SessionManager\n"
        "print('SESSION_MANAGER_IMPORT_OK')\n"
    )
    result = _run_probe(code)
    assert result.returncode == 0, (
        "直接调用入口无法 import modules.*：\n" + (result.stderr or "")
    )
    assert "SESSION_MANAGER_IMPORT_OK" in result.stdout


def test_pwcli_native_bootstraps_repo_root_into_sys_path():
    """仓库根必须由模块**自己**放进 sys.path，而不是靠 CWD 兜底。

    判据不能写成 `repo_root in sys.path`：`python -m pytest` 会把 CWD（= 仓库根）
    放进 `sys.path`，那条断言今天就通过，守不住任何东西（已实测）。
    """
    code = (
        "import runpy, sys\n"
        "runpy.run_path(sys.argv[1], run_name='pwcli_probe')\n"
        "print('REPO_ROOT_IN_PATH=' + str(sys.argv[2] in [p.rstrip('/\\\\') for p in sys.path]))\n"
    )
    result = _run_probe(code, str(REPO_ROOT))
    assert "REPO_ROOT_IN_PATH=True" in result.stdout, (
        "pwcli_native 没有自己把仓库根放进 sys.path：\n"
        + result.stdout + (result.stderr or "")
    )


def test_direct_script_launch_does_not_fail_on_import():
    """直接以脚本方式启动时，不得出现 ModuleNotFoundError。"""
    probe = REPO_ROOT / "modules" / "utils" / "pwcli_native.py"
    result = subprocess.run(
        [sys.executable, str(probe), "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "ModuleNotFoundError" not in (result.stderr or ""), result.stderr
```

> **为什么探针要跑在临时目录里**：`python -m pytest` 与它批评的 `python -c` 是**同一个机制** ——
> 把 **CWD** 放进 `sys.path`。只要探针的 CWD 是仓库根，仓库根就天然在 `sys.path` 里，
> 断言 `repo_root in sys.path` 今天就会通过（**已实测**）→ 空守卫。
> 把 CWD 放到临时目录后，仓库根**只能**由 `pwcli_native` 自己插入 → 判据成立。
>
> **已实测（今天，修复前）**：
> ```
> probe1（import 探针）→ returncode=1
>   ModuleNotFoundError: No module named 'modules'
> probe2（sys.path 探针）→ REPO_ROOT_IN_PATH=False
> ```
> 两条都 FAIL —— 这就是要修的判据。
>
> `test_direct_script_launch_does_not_fail_on_import` 今天**就通过**
> （`--help` 不会触发 `:320` 的延迟导入），它是护栏不是判据。
> 真正会触发 `:320` 延迟导入的是**带 `--account-id` 的 open / state-save**，那需要真实浏览器，属于手工验证（Step 5）。

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_pwcli_native_sys_path_bootstrap.py -q
```

Expected: **2 FAIL** ——
- `test_direct_script_launch_can_import_modules_package`：子进程 `returncode=1`，stderr 含 `ModuleNotFoundError: No module named 'modules'`；
- `test_pwcli_native_bootstraps_repo_root_into_sys_path`：子进程打印 `REPO_ROOT_IN_PATH=False`。

`test_direct_script_launch_does_not_fail_on_import` 今天就通过（护栏，不是判据）。

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

改为：

```python
        UniqueConstraint(
            "platform",
            "alias_normalized",
            "shop_region",
            "is_active",
            name="uq_shop_account_aliases_active_alias",
            postgresql_nulls_not_distinct=True,
        ),
```

> **已实测（SQLAlchemy 2.0.41）**：`UniqueConstraint(..., postgresql_nulls_not_distinct=True)` 会生成
> `CONSTRAINT uq_t UNIQUE NULLS NOT DISTINCT (a, b, c)` —— 与迁移脚本里的原生 SQL 完全一致。
> （注意：`inspect.signature(UniqueConstraint.__init__)` 里看不到这个参数，因为它走的是 `**kw`；**不要**因此改用 `Index` —— `Index` 形式不会出现在 `CREATE TABLE` 里，反而与迁移不一致。）

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_shop_identity_schema_migration.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 在 live 库上跑迁移**

**迁移入口是 `scripts/run_current_schema_migrations.py`，不是 `alembic -c current_migrations/alembic.ini`。**
（`current_migrations/` 目录下**没有** `alembic.ini`；仓库根的 `alembic.ini:4` 指向的是历史链 `migrations`。）

先做只读预检：

```bash
python scripts/run_current_schema_migrations.py --preflight-only --json
```

Expected: 输出当前链状态与将要执行的动作，**不改库**。

确认无误后正式执行：

```bash
python scripts/run_current_schema_migrations.py --database-url "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
```

> 该脚本还支持 `--diagnose`（诊断当前链状态）与 `--json`（机器可读输出）。**实施者先跑 `python scripts/run_current_schema_migrations.py --help` 确认参数**，不要凭记忆敲。

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
    # 注意：分隔符集是 [\s_()/-]，**不含点号** —— 与 spec §2.4 的 SQL 口径
    # `[[:space:]_()/-]+` 保持一致。xhkj1.my 的规范化值就是 xhkj1.my。
    ("xhkj1.my", "xhkj1.my"),
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

Expected: **只有 `test_normalize_alias_key_matches_sql_semantics` FAIL**（`TK-新加坡-1店` 今天被规范化成 `-新加坡-1店`，不是 `新加坡1店`）。

`test_normalize_alias_key_is_idempotent` 今天**就通过**（旧规则也是幂等的）—— 它是**护栏**不是判据；
`test_sql_assets_use_stored_alias_normalized` 今天也通过（同样是护栏）。

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
git add backend/utils/text_normalization.py sql/semantic/shop_identity_resolution_candidates.sql sql/semantic/orders_atomic.sql backend/tests/test_alias_normalization_consistency.py
git commit -m "fix(别名): 写侧与查侧规范化统一，认领了不再匹配不上

- normalize_alias_key 改为剥前缀 + 小写 + 删分隔符，与 SQL 侧完全一致
- SQL 侧只使用存储的 alias_normalized，消除双份规则
- 修复 TK-新加坡-1店 -> -新加坡-1店 与 SQL 的 新加坡1店 不一致"
```

---

## Task 7: 语义层多候选不静默归一（落 unknown + 告警码）

**Files:**
- Modify: `sql/semantic/orders_atomic.sql:439-474`（`alias_resolved` 段的 LATERAL + 最终 SELECT `:477-530`）
- Modify: `backend/services/data_pipeline/refresh_registry.py:21`（**补依赖** —— 见下方 Step 4a-2）
- Modify: `backend/tests/data_pipeline/test_refresh_runner.py:88`（**同步改依赖断言** —— 不改会红）
- Modify: `sql/semantic/analytics_atomic.sql:162-206`（LATERAL）+ 最终 SELECT
- Modify: `sql/semantic/orders_monthly_atomic_mv.sql:233-292`（告警码 CASE + LATERAL `:267-279`）+ 最终 SELECT `:293-311`
- Modify: `sql/semantic/analytics_monthly_atomic_mv.sql:339-405`（告警码 CASE `:365-377` + LATERAL `:389-401`）+ 最终 SELECT
- Test: `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py`（扩充）
- Test: `backend/tests/test_semantic_ambiguous_identity_sql.py`（新建）

> **本 Task 不改 `sql/semantic/shop_identity_resolution_candidates.sql`（候选视图）** —— 区域感知匹配属第二批 ⑨。
> 该文件仍需在 `git add` 里带上（第一批 Task 6 改过它的规范化口径），但**本 Task 不动它**。

**背景（spec §2.5）**：
- live 有**四套并存**的解析逻辑，全部 `LIMIT 1`。
- 两条路径的塌缩胜者还不同：`semantic.fact_orders_atomic` 路径 → SG 店；候选视图路径 → MY 店。
- 候选池**不按 `enabled` 过滤**（65/136 行来自 disabled 账号）——业务已决定**不排除**（停用只是暂时的），唯一性判定必须用**完整候选集**。

**判定口径（唯一真源，四条路径共用）**：

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
    "sql/semantic/analytics_monthly_atomic_mv.sql",
)

LEGACY_WARNING_CODES = (
    "missing_identity",
    "unresolved_shop_account",
    "missing_required_platform_shop_id",
)


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_no_sql_asset_uses_bare_limit_1_on_identity():
    """四条语义路径都不允许再对身份候选直接 LIMIT 1。"""
    for rel in SQL_ASSETS:
        text = _text(rel)
        assert "ambiguous_shop_label" in text, f"{rel} 缺少 ambiguous_shop_label 告警码"
        assert "unmatched_shop_label" in text, f"{rel} 缺少 unmatched_shop_label 告警码"
        assert "identity_candidate_count" in text, f"{rel} 缺少 identity_candidate_count"


def test_monthly_assets_keep_legacy_warning_codes():
    """既有的三个告警码不能被新词表覆盖掉（spec A7 的「并存关系」）。

    live 上 `missing_identity` / `unresolved_shop_account` / `missing_required_platform_shop_id`
    已经在用（88 行 `unresolved_shop_account`），新词表只能**加**不能**盖**。
    """
    for rel in (
        "sql/semantic/orders_monthly_atomic_mv.sql",
        "sql/semantic/analytics_monthly_atomic_mv.sql",
    ):
        text = _text(rel)
        for code in LEGACY_WARNING_CODES:
            assert code in text, f"{rel} 丢了既有告警码 {code}"


def test_candidate_view_untouched_in_batch1():
    """本批次不改候选视图 —— 区域感知匹配属第二批 ⑨。

    视图的 identity_rows 是 4 路 UNION ALL；给视图加列必须同时改 4 个分支
    **和** 视图末尾的 SELECT 列表，否则 PostgreSQL 报
    `each UNION query must have the same number of columns`（已实测）。
    本批次只给别名表加列与约束，多候选由判定逻辑落 unknown。

    ⚠ **本用例是「第一批专用护栏」**：第二批 Task 17 要给候选视图加区域列，
    届时**必须**把本用例改成断言新列存在（见第二批计划的 Task 17 Step 1）。
    """
    text = _text("sql/semantic/shop_identity_resolution_candidates.sql")
    assert text.count("UNION ALL") == 3, "候选视图的 UNION 分支数变了（应为 4 路 UNION ALL）"
    assert "shop_region" not in text, "本批次不应改候选视图（区域感知匹配属第二批 ⑨）"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_semantic_ambiguous_identity_sql.py -q
```

Expected: FAIL。

- [ ] **Step 3: 候选视图本批次不动（区域感知匹配属第二批 ⑨）**

> **重要边界**：`sql/semantic/shop_identity_resolution_candidates.sql` 的 `identity_rows` 是 **4 路 UNION ALL**
> （`platform_shop_id` / `shop_account_id` / `alias_match` / `store_name_match`）。
> 给视图加列必须**同时**改 4 个分支 **和** 视图末尾的 SELECT 列表，否则 PostgreSQL 直接报
> `each UNION query must have the same number of columns`（已实测）。
>
> 但**本批次不需要给视图加区域列**：
> - 别名表加了 `shop_region` + 新唯一约束之后，同一个 `FIORO` 可以分别注册给 SG/MY/PH 三个店；
> - 此时按 `(platform, alias_normalized)` 匹配会得到 **3 个候选** → Task 7 的判定逻辑会把它落成
>   `unknown` + `ambiguous_shop_label` → **不会静默错配**（这正是 D13 要的行为）；
> - 真正把 `FIORO` + 站点正确分流到三个店，需要「站点 → 区域」映射参与匹配，
>   属于**第二批 ⑨**（见第二批计划的区域感知匹配 Task）。
>
> → **本 Task 不改视图**。Task 5 已经把 `shop_region` 列与新约束落库（那部分不受影响）。

- [ ] **Step 4: 四条语义路径统一判定逻辑**

**四条路径的现状（已核验，勿凭印象改）：**

| 文件 | 现状 | 关键位置 |
|---|---|---|
| `sql/semantic/orders_atomic.sql`（530 行） | **不走候选视图**，直接 `LATERAL` 扫 `core.shop_accounts sa` + `LEFT JOIN core.shop_account_aliases saa`，条件是 `store_name` 等值 **OR** `platform_shop_id` 等值 **OR** 别名匹配，`ORDER BY 别名命中 → is_primary → sa.id LIMIT 1` | `:451-474`（LATERAL）、`:462-467`（匹配条件）、`:469-473`（排序 + LIMIT 1） |
| `sql/semantic/analytics_atomic.sql`（328 行） | 走候选视图，`LATERAL` + `ORDER BY resolution_priority, resolved_shop_id LIMIT 1`；候选来自 `VALUES` 内联列表 | `:162-206`（LATERAL）、`:168-199`（内联候选） |
| `sql/semantic/orders_monthly_atomic_mv.sql`（317 行） | 走候选视图，`LATERAL` + `ORDER BY c.resolution_priority, c.resolved_shop_id LIMIT 1`；候选集合由 `prepared_identity_monthly_orders` 层的 `normalized_identity_candidates` 数组提供 | `:203-220`（数组构造）、`:267-279`（LATERAL）、`:247-259`（既有告警码词表） |
| `sql/semantic/analytics_monthly_atomic_mv.sql` | 走候选视图，`LATERAL` + `ORDER BY c.resolution_priority, c.resolved_shop_id LIMIT 1`；**带与 orders monthly 同一套既有告警码词表** | `:334`（数组）、`:389-401`（LATERAL）、`:365-377`（既有告警码词表） |

**4a. 先把 `orders_atomic.sql` 改成走候选视图（口径统一的前提）。**

`orders_atomic.sql` 是四条里唯一自己扫 `core.shop_accounts` 的，因此它的塌缩胜者（SG 店）与另三条（MY 店）不同。

改动要求：
1. 在 `mapped` CTE 里补出 `normalized_identity_candidates` 数组，**构造方式照抄 `sql/semantic/orders_monthly_atomic_mv.sql` 的 `prepared_identity_monthly_orders` 层**（`:200-218`）——
   ⚠ **不是 `mapped` 层**：`mapped` 层只抽原始列，数组是在 `prepared_identity_monthly_orders` 里用
   `ARRAY_REMOVE(ARRAY[...], NULL)` 构造的，**必须连 `ARRAY_REMOVE` 与 `xihong`/`unknown`/`none` 排除一起抄**，
   只抄 `mapped` 会漏掉去空与排除逻辑。
   候选来源 = `source_platform_shop_id` / `source_shop_account_id` / `source_shop_id`（排除 `xihong`/`unknown`/`none`）/ `source_shop_id_compact` / `normalized_store_label_raw`。
   > `orders_atomic.sql` 当前**没有** `normalized_identity_candidates`（实测 0 次），`mapped` 层也没有 `normalized_store_label_raw` —— 这两个都要补。
   > `orders_atomic.sql:62` 已经抽出了 `source_site`（`raw_data->>'站点'`），**保留它**，第二批的区域感知匹配要用。

1b. **⚠ 每个文件缺的身份线索列不一样 —— 照抄 monthly 的数组构造会引用到不存在的列**
   （实测 grep：`orders_atomic.sql` 里 `source_platform_shop_id` **0 次**、`source_shop_account_id` **0 次**、
   `canonical` **0 次**；`analytics_atomic.sql` 里 `canonical` 同样 **0 次**）：

| 文件 | `source_platform_shop_id` | `source_shop_account_id` | `source_shop_id` | `normalized_*` 具名列 | `canonical` JOIN |
|---|---|---|---|---|---|
| `orders_atomic.sql` | **缺** → 在 `mapped` 新增（取法照抄 `orders_monthly_atomic_mv.sql:39-45`：`raw_data->>'platform_shop_id'` / `平台店铺ID` / `店铺ID`），并**透传**到 `cleaned`(:280) 的显式清单 | **缺** → 在 `mapped` 新增（取法照抄 `orders_monthly_atomic_mv.sql:46-57`：`raw_data->>'shop_account_id'` / `account_id` / `店铺账号ID` / `账号ID` / `account`），并**透传**到 `cleaned` | `mapped`(:35) 有，但 `cleaned`(:283) 把它**改名成了 `shop_id`**（`COALESCE(source_shop_id,'unknown')`）→ 要在 `cleaned` 的显式清单里**同时保留 `source_shop_id`**（Step 4c 的 CASE 用的是 `source_shop_id`） | **缺**（Step 4a 已要求补 `normalized_store_label_raw` / `normalized_source_shop_id_compact`） | **缺** → 必须新增 |
| `analytics_atomic.sql` | `mapped`(:34) 里有（`:50-60`） | `mapped`(:34) 里有（`:61-72`） | `mapped`(:34) 里有（`:37`） | 无具名列（候选在 `:168-199` 用内联 `REGEXP_REPLACE` 构造） | **缺** → 必须新增 |
| `orders_monthly_atomic_mv.sql` | 有（`:45` → `:132` → `:172`） | 有（`:57` → `:133` → `:173`） | 有（`:23` → `:130` → `:171`） | 有（`normalized_source_shop_id_compact`:184、`normalized_store_label_raw`:195） | **已有**（`:280-282`） |
| `analytics_monthly_atomic_mv.sql` | 有（`:42` → `:113` → `:301`） | 有（`:54` → `:114` → `:302`） | 有（`:20` → `:111` → `:304`） | 无具名列（`:334` 内联构造数组） | **已有**（`:402-404`） |

   **`canonical` JOIN 怎么加**：Step 4c 的 CASE 用到 `canonical.shop_account_id` 与 `canonical.platform_shop_id`，
   而两个 atomic 资产**都没有**这个 JOIN → 照抄 CASE 会报 `column "canonical.shop_account_id" does not exist`。
   照抄 monthly 的写法（`orders_monthly_atomic_mv.sql:280-282`），
   **但右侧的 LATERAL 结果别名必须按文件替换**（照抄 `resolved` 会报
   `missing FROM-clause entry for table "resolved"`，在 `analytics_atomic.sql` 里还会与同名 CTE 冲突）：

   ```sql
   -- orders_atomic.sql（LATERAL 别名 = account_map），加在 alias_resolved(:406) 里、LATERAL 之后
       LEFT JOIN core.shop_accounts canonical
         ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(d.platform_code, ''))
        AND canonical.shop_account_id = account_map.resolved_shop_account_id
   ```
   ```sql
   -- analytics_atomic.sql（LATERAL 别名 = resolved_candidate），加在 resolved(:120) 里、LATERAL 之后
       LEFT JOIN core.shop_accounts canonical
         ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(m.platform_code, ''))
        AND canonical.shop_account_id = resolved_candidate.resolved_shop_account_id
   ```

   > 落点以**各文件自己的 CTE 结构**为准，不要照抄别处的行号。

1c. **⚠ 必须同步补依赖图，否则重建顺序会错、直接失败**

`backend/services/data_pipeline/refresh_registry.py:21`（映射表名是 `PIPELINE_DEPENDENCIES`，定义在 `:12`）现在是：

```text
    "semantic.fact_orders_atomic": [],
    "semantic.fact_analytics_atomic": ["semantic.shop_identity_resolution_candidates"],
```

Step 4a 让 `orders_atomic.sql` **改走候选视图** → 这个依赖从「不存在」变成「真实存在」，
**必须声明**，否则 `scripts/rebuild_views.py` 会把 `semantic.fact_orders_atomic` 排在
`semantic.shop_identity_resolution_candidates` **之前**重建（实测 `--dry-run` 的顺序就是这样：
orders_atomic 第 1、候选视图第 6）→ **第二批**候选视图加 `identity_shop_region` 之后，
`orders_atomic` 引用它就会找不到列 → **重建直接失败**。

> 实测改完之后 `--dry-run` 的顺序变成：候选视图第 **1**、`semantic.fact_orders_atomic` 第 **2** ✅。
>
> **这条依赖边是第二批 ⑨ 的前置** —— 第二批 Task 17 会给候选视图加区域列并让 orders 路径引用它，
> 必须在第一批就把依赖图改好，否则第二批的 `rebuild_views.py` 会直接失败。

改成：

```text
    "semantic.fact_orders_atomic": ["semantic.shop_identity_resolution_candidates"],
```

> **⚠ 现有的契约测试会因此变红，必须同步改**：
> `backend/tests/data_pipeline/test_refresh_runner.py:88` 断言的是
> `PIPELINE_DEPENDENCIES["semantic.fact_orders_atomic"] == []` → 要改成
> `== ["semantic.shop_identity_resolution_candidates"]`。
> **不改这条断言，跑全量 `pytest` 会红**（实测：内存改依赖后，该文件里**只有这一条**红，其余 21 条绿）。
> → 所以 `backend/tests/data_pipeline/test_refresh_runner.py` 已加入第一批 §12 Step 1 与第二批 §18 Step 1 的验收清单，
> **别等到 CI 才发现**。

> 改完用 `python scripts/rebuild_views.py --dry-run` 复核顺序：
> `semantic.shop_identity_resolution_candidates` 必须排在 `semantic.fact_orders_atomic` **之前**。
> （`fact_analytics_atomic`(:22) 与两个 monthly MV(:15-20) 本来就声明了这条依赖，不用改。）
2. 把 `:451-474` 的 LATERAL 换成扫 `semantic.shop_identity_resolution_candidates c`，条件 `c.platform_code = lower(d.platform_code) AND c.identity_value_normalized = ANY (d.normalized_identity_candidates)`。
3. 删掉 `orders_atomic.sql` 里对 `core.shop_account_aliases` 的直接 JOIN —— 别名匹配统一由候选视图的 `alias_match` 分支承担。
4. 保留原有的「`shop_id` 为 `''`/`none`/`unknown`/`xihong` 时落 `unknown`」兜底。

**4b. 四条路径的 LATERAL 改成「候选集合 + 计数」。**

样板：`sql/semantic/orders_monthly_atomic_mv.sql:267-279`（当前 `LIMIT 1` 的 LATERAL）。
四个文件做同样改动，只是候选表达式来源不同（见本节末尾的「四个文件的差异」）。

> **⚠ 不要用窗口函数做去重计数** —— PostgreSQL 不支持，两种「显然写法」都会出事（**已在 live PG 15.14 实测**）：
>
> | 写法 | 实测结果 | 后果 |
> |---|---|---|
> | `count(DISTINCT c.resolved_shop_id) OVER ()` | `ERROR: DISTINCT is not implemented for window functions` | 语义层重建**直接报错**，部署即失败 |
> | `count(*) OVER ()` | `[(1, [1, 1, 2])]` —— 窗口函数在**聚合之后**求值，`count` 统计的是「聚合结果的行数」而不是候选行数；在无 `GROUP BY` 的场景里恒为 1（分组场景里等于分组数，**同样不是候选数**） | 所有多候选都被判成 1 个 → **永远不落 `ambiguous_shop_label`** → 正是 D13/A6 要防的静默错配 |
>
> 所以候选计数必须写成**纯聚合**（`count(DISTINCT ...)` + `array_agg(DISTINCT ...)`），
> 放在**独立子查询**里，再用 `LEFT JOIN LATERAL` 拼回去。

**可执行实现（已在 live 实测：0 候选 / 1 候选 / 2 候选三种输入全部返回正确计数，输出行数恒为 1，无行放大）**：

```sql
         LEFT JOIN LATERAL (
             SELECT
                 agg.candidate_count,
                 agg.candidate_shop_ids,
                 best.resolved_shop_id,
                 best.resolved_shop_account_id,
                 best.resolution_method,
                 best.resolution_priority,
                 best.identity_source_value
             FROM (
                 -- ① 计数与候选清单：纯聚合，按去重后的店铺算
                 SELECT
                     count(DISTINCT c.resolved_shop_id)::int AS candidate_count,
                     array_agg(DISTINCT c.resolved_shop_id ORDER BY c.resolved_shop_id) AS candidate_shop_ids
                 FROM semantic.shop_identity_resolution_candidates c
                 WHERE c.platform_code = lower(COALESCE(m.platform_code, ''))
                   AND c.identity_value_normalized = ANY (m.normalized_identity_candidates)
             ) agg
             LEFT JOIN LATERAL (
                 -- ② 最优候选：每个店只保留优先级最高的一行
                 SELECT DISTINCT ON (c.resolved_shop_id)
                        c.resolved_shop_id,
                        c.resolved_shop_account_id,
                        c.resolution_method,
                        c.resolution_priority,
                        c.identity_source_value
                 FROM semantic.shop_identity_resolution_candidates c
                 WHERE c.platform_code = lower(COALESCE(m.platform_code, ''))
                   AND c.identity_value_normalized = ANY (m.normalized_identity_candidates)
                 ORDER BY c.resolved_shop_id, c.resolution_priority, c.resolution_method, c.identity_source_value
             ) best ON TRUE
             ORDER BY best.resolution_priority, best.resolved_shop_id
             LIMIT 1
         ) resolved ON TRUE
```

**为什么这样写（四条都实测过）**：
- `agg` 是**纯聚合**，没有窗口函数 → 规避上面两条错误；
  `count(DISTINCT ...)` 保证「同一个店通过多种方式命中」只算 **1 个**候选
  （live 上确实存在这种行：`验证码测试账号` 同时命中 `store_name_match` 与 `shop_account_id`）。
- `LEFT JOIN LATERAL ... best ON TRUE` 保证**候选为 0 时 LATERAL 仍返回 1 行**
  （`best.*` 全 NULL、`candidate_count = 0`），外层 `LEFT JOIN LATERAL ... ON TRUE` 也就不会把整行丢掉 ——
  这样「候选为 0」才能与「视图里根本没这行」区分开。
- `DISTINCT ON (resolved_shop_id)` + 外层 `ORDER BY ... LIMIT 1` 保证**输出恒为 1 行**
  （实测 2 候选时输出行数 = 1），不会因为候选变多而让主查询行放大。
- `array_agg(DISTINCT ... ORDER BY ...)` 是 PostgreSQL 允许的组合（DISTINCT 的表达式必须与 ORDER BY 一致）。

**实测记录（live PG 15.14，只读，未改任何数据）**：

| 输入候选数组 | `candidate_count` | `candidate_shop_ids` | `resolved_shop_id` |
|---|---|---|---|
| `['新加坡1店']` | 1 | `['tiktok_sg_daone_mall_local']` | `tiktok_sg_daone_mall_local` |
| `['新加坡1店','马来1店']` | 2 | `['tiktok_my_dawie_mall_local','tiktok_sg_daone_mall_local']` | `tiktok_my_dawie_mall_local`（仅用于展示；候选数 ≥ 2 时最终落 `unknown`） |
| `['不存在的店名xyz']` | 0 | NULL | NULL |

**四个文件的候选表达式来源不同 —— 不要照抄**：

| 文件 | LATERAL 外层别名 | 候选表达式 | 改法 |
|---|---|---|---|
| `orders_monthly_atomic_mv.sql` | `m` | `m.normalized_identity_candidates`（`:203-220` 构造） | 直接套用上面的模板 |
| `analytics_monthly_atomic_mv.sql` | `m` | `m.normalized_identity_candidates`（`:334`） | 直接套用上面的模板 |
| `orders_atomic.sql` | `d` | **今天没有** `normalized_identity_candidates` | 先按 Step 4a 在 `mapped` 层补出该数组，再套用模板（把 `m.` 换成 `d.`）。⚠ **LATERAL 结果别名是 `account_map`**（`:474`），不是 `resolved` → 模板里的 `resolved.*` 全要改成 `account_map.*`；或者把别名改名成 `resolved` 并**同步改** `:410-411` 两处引用 |
| `analytics_atomic.sql` | `m` | `VALUES (...)` 内联列表（`:168-199`），**不是数组** | 保留 `VALUES` 在 LATERAL **内部**，只把比较方式改成数组：⚠ `ANY` 的**右侧必须是数组** —— 直接写 `= ANY (cv.identity_value_normalized)` 会报 `op ANY/ALL (array) requires array on right side`（已实测）。正确写法：`= ANY (ARRAY(SELECT cand.identity_value_normalized FROM (VALUES ...) cand(identity_value_normalized)))`。**⚠ 不得把 `VALUES` 提到 LATERAL 之外** —— `:169-199` 的每个候选值都引用外层 `m.source_platform_shop_id` / `m.store_label_raw`，是**行相关**的；提到同层 CTE 后就不再与当前输出行相关 → LATERAL 退化成笛卡尔积 → **行放大** |

**⚠ 四个文件还有「中间 CTE 透传」与「LATERAL 结果别名」两处差异 —— 照抄上面的模板会报 `column does not exist`**：

| 文件 | CTE 链（谁带显式列清单） | LATERAL 结果别名 | 必须补的透传 |
|---|---|---|---|
| `orders_atomic.sql` | `mapped`(:32) → **`cleaned`(:280，显式列清单)** → `deduplicated`(:390，`SELECT *`) → `alias_resolved`(:406) | **`account_map`**(:474) | ① `normalized_identity_candidates` 必须在 `cleaned` 的显式清单里**再透传一次** —— 否则 `d.normalized_identity_candidates` 报 `column d.normalized_identity_candidates does not exist`；② `identity_warning_code` / `identity_candidate_count` / `identity_candidates` **在 `alias_resolved`(:406，LATERAL 所在层) 算出**，不经过 `cleaned` —— 只需加进 `alias_resolved` 的显式清单，再由最终 SELECT（`:477-530`）引用 |
| `analytics_atomic.sql` | `mapped`(:34) → `resolved`(:120) → **`cleaned`(:208，显式列清单)** → `deduplicated`(:279) | **`resolved_candidate`**(:206) | ① LATERAL 的结果别名是 `resolved_candidate`，**不是** `resolved` → 模板与 CASE 里的 `resolved.candidate_count` / `resolved.candidate_shop_ids` 都要改成 `resolved_candidate.*`；② 新列在 `resolved` 里算出后要穿过 `cleaned`(:208) 的显式清单 |
| `orders_monthly_atomic_mv.sql` | `mapped_monthly_orders`(:19) → `normalized_monthly_orders`(:114) → `prepared_identity_monthly_orders`(:200) → **`resolved_monthly_orders`(:221，显式列清单)** → `deduplicated_monthly_orders`(:284，`SELECT *`) | `resolved` | 新列在 `resolved_monthly_orders` 里算出 → 加进该 CTE 的显式清单 → `deduplicated`（`SELECT *`）自动带上 → 最终 SELECT 引用 |
| `analytics_monthly_atomic_mv.sql` | `mapped_monthly_traffic`(:16) → `normalized_monthly_traffic`(:107) → **`resolved_monthly_traffic`(:339，显式列清单)** → `deduplicated_monthly_traffic`(:406，`SELECT *`) | `resolved` | 同上 |

> **为什么必须写清楚**：PostgreSQL 不会自动把列带过 `SELECT 列清单` 形式的 CTE。
> 漏掉透传 → 语义层重建时直接报 `column ... does not exist`；
> 漏掉 LATERAL 别名 → CASE 里的 `resolved.*` 取不到值，`candidate_count` 恒为 NULL → **所有行都落 `unmatched_shop_label`**。
>
> **模板里的 `) resolved ON TRUE` 是占位别名** —— 落地时按上表的「LATERAL 结果别名」列改：
> `orders_atomic.sql` → `account_map`；`analytics_atomic.sql` → `resolved_candidate`；
> 两个 monthly MV → `resolved`。
> 改了别名之后，**模板与 CASE 里的 `resolved.*` 要同步替换**，否则 `candidate_count` 恒为 NULL。

然后把 `shop_id` 的 CASE 改成：

```sql
             CASE
                 WHEN resolved.candidate_count = 1 THEN resolved.resolved_shop_id
                 ELSE 'unknown'
             END AS shop_id,
```

并新增两列（告警码那一列见 Step 4c —— 它必须与既有词表并存，不能直接覆盖）：

```sql
             resolved.candidate_count AS identity_candidate_count,
             resolved.candidate_shop_ids::text AS identity_candidates,
```

**4c. `identity_warning_code` 的完整词表与并存关系（spec A7 要求「已定义」）。**

`identity_warning_code` 是**单值列**（下游 mart / api / 前端都按一个码读），所以新旧码必须按**固定优先级**共存。

**既有词表（live 已经在用，不许被新词表盖掉）**：

| 码 | 触发条件 | live 现状（实测） |
|---|---|---|
| `missing_identity` | 四个身份线索（`source_platform_shop_id` / `source_shop_account_id` / `store_label_raw` / `source_shop_id`）**全为空** | 0 行 |
| `unresolved_shop_account` | 候选为空 / 候选唯一但 `resolved_shop_account_id` 为空 / `canonical.shop_account_id` 查不到 | **88 行**（全部来自 `TK新加坡3C店`，`raw_shop_id='xihong'`） |
| `missing_required_platform_shop_id` | 已归属、平台是 shopee，但该店没有 `platform_shop_id` | 0 行 |
| `NULL` | 正常归属 | 31201 行 |

**新增两个码（本次改造）**：

| 码 | 触发条件 | 含义 |
|---|---|---|
| `unmatched_shop_label` | **候选数 = 0**（有身份线索，但候选视图里一个店都没命中） | 这个标签没人认领 → 需要建别名/认领 |
| `ambiguous_shop_label` | **候选数 ≥ 2** | 同一个标签命中多个店 → 必须消歧，**不许归第一** |

**并存优先级（从上到下，先命中先返回）**：

```sql
CASE
    WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL
        THEN 'missing_identity'                                   -- ① 连线索都没有
    WHEN resolved.candidate_count = 0
        THEN 'unmatched_shop_label'                               -- ② 有线索但没人认领
    WHEN resolved.candidate_count > 1
        THEN 'ambiguous_shop_label'                               -- ③ 命中多个店
    WHEN resolved.resolved_shop_account_id IS NULL
        THEN 'unresolved_shop_account'                            -- ④ 唯一候选但账号号为空
    WHEN resolved.resolved_shop_account_id IS NOT NULL AND canonical.shop_account_id IS NULL
        THEN 'unresolved_shop_account'                            -- ④ 唯一候选但 canonical 查不到
    WHEN resolved.resolved_shop_account_id IS NOT NULL
     AND LOWER(COALESCE(m.platform_code, '')) IN ('shopee')
     AND NULLIF(TRIM(canonical.platform_shop_id), '') IS NULL
        THEN 'missing_required_platform_shop_id'                  -- ⑤ shopee 缺平台店铺号
    ELSE NULL
END AS identity_warning_code
```

**为什么这样排**：
- ① 最严重（连线索都没有）→ 排最前，避免被「没人认领」盖住。
- ②③ 比 ④⑤ **更具体、更可执行**（「没店认领」/「多个店抢」比「账号号为空」更贴近人要做的事）→ 排在 ④⑤ 前面。
- ④⑤ 保留原语义与原触发条件，**只在新码没命中时才生效** → live 的 88 行不会凭空消失：
  它们会按新口径落进 `unmatched_shop_label`（`TK新加坡3C店` 确实一个店都没命中，实测候选集为空）。

**两个 monthly 资产都要改（不要只改 orders 一个）**：
- `sql/semantic/orders_monthly_atomic_mv.sql:247-259`（既有词表）
- `sql/semantic/analytics_monthly_atomic_mv.sql:365-377`（**同一套既有词表**；live `fact_analytics_monthly_atomic_mv` 3541 行、当前 `identity_warning_code` 全为 NULL）

> ⚠ **漏改 `analytics_monthly_atomic_mv.sql` 的后果**：两个 monthly 视图的告警码词表会不一致 ——
> orders 侧能报 `unmatched_shop_label`，analytics 侧只会报旧的 `unresolved_shop_account`，运营看板上两个口径互相打架。

**两个 monthly 薄封装 VIEW 用的是显式列清单 —— 加列必须同步，否则新列只在 MV 上、wrapper 上没有**：

| 薄封装 VIEW | 文件 | 显式列数 | 备注 |
|---|---|---|---|
| `semantic.fact_orders_monthly_atomic` | `sql/semantic/orders_monthly_atomic.sql:5-23` | 16 | `CREATE OR REPLACE`，无 DROP |
| `semantic.fact_analytics_monthly_atomic` | `sql/semantic/analytics_monthly_atomic.sql:5-27` | 20 | **`:3` 是 `DROP VIEW IF EXISTS ... CASCADE`** → 重建时必须由 runner 按依赖顺序重建下游 |

实施者的选择（两条都可行，但**必须显式做一遍**，不能默认「加了就有」）：
- **方案 A（推荐）**：两个 wrapper 也在末尾补上 `identity_candidate_count` / `identity_candidates`
  → 运营看板与下游 mart 直接能读到候选清单；
- **方案 B**：wrapper 不动 → 新列只存在于 MV 上，`fact_orders_monthly_atomic` 读不到候选清单，
  此时 Task 8 的核对查询要改成直接查 `semantic.fact_orders_monthly_atomic_mv`（**MV 在 live 里确实存在**，
  `pg_class.relkind='m'`，`information_schema.tables` 不列 MATVIEW，别据此判断它不存在）。

> ⚠ **CASE 里的外层别名也要按文件替换**：Step 4b 的模板用的是 `m.`（`m` = 月度/analytics 那条链的外层别名），
> 但 `orders_atomic.sql` 的 LATERAL 在 `alias_resolved`(:406) 里、外层是 `d`（`FROM deduplicated d`）→
> **Step 4c 的 CASE 里的 `m.source_platform_shop_id` / `m.source_shop_account_id` / `m.store_label_raw` / `m.source_shop_id`
> 在该文件里必须改成 `d.*`**，否则报 `column d.source_platform_shop_id does not exist`。
> `analytics_atomic.sql` 的外层是 `m`（`FROM mapped m`），保持 `m.` 不变。

> **⚠⚠ 加列位置有硬约束**：`orders_atomic.sql` 是 `CREATE OR REPLACE VIEW`（`:3`），
> PostgreSQL 只允许在列清单**末尾**追加列 —— 插到中间会报 `cannot change name of view column`。
> 所以：**`orders_atomic.sql` 的最终 SELECT（`:477-530`）里，三列必须追加在 `platform_total_cost_derived` 之后**，
> **不能**紧跟在 `shop_id` 后面。
> `analytics_atomic.sql`（`DROP VIEW ... CASCADE` + `CREATE`）与两个 monthly MV（`DROP MATERIALIZED VIEW` + `CREATE`）
> 是整表重建，位置无所谓；两个薄封装 VIEW 若走「方案 A」，同样必须**追加在末尾**。
>
> **⚠ 还有一个容易忽略的点**：Step 4b 的模板里，`shop_id` 的 CASE 与新三列是**分开的两段**——
> `shop_id` 的 CASE 落在 `alias_resolved`(:406) 里，新三列也落在同一层；
> 但**最终 SELECT**（`:477-530`）要按上面的顺序把它们放好。

**`fact_orders_atomic` / `fact_analytics_atomic` 今天没有 `identity_warning_code` 列**
（实测 live 列数分别为 **40** / **31**），本 Task 给它们**新增**三列：
`identity_warning_code` / `identity_candidate_count` / `identity_candidates`。加列后必须同步：
> - 四个 SQL 资产各自的**最终 SELECT 列表**（`orders_atomic.sql` 的 `:477-530`、`analytics_atomic.sql` 的最终 SELECT、两个 monthly MV 的最终 SELECT）；
> - 下游消费这些视图的 mart / api 层 SQL（`sql/mart/*`、`sql/api_modules/*`）—— 若它们用了 `SELECT *` 则无需改；若是显式列表，需要补列；
> - `backend/schemas/` 下暴露这些字段的 Pydantic 契约（若有）。
>
> **实施者必须先 grep 全部下游引用**：`grep -rn "fact_orders_atomic" sql/ backend/ --include=*.sql --include=*.py`。
>
> **实施者必须先在 live 上验证这段 SQL 能跑通**（`SELECT ... LIMIT 0` 或包一层子查询试跑），再改文件 ——
> 上面的模板已在 live PG 15.14 实测可执行。

- [ ] **Step 5: 跑语义层 SQL 资产一致性测试**

```bash
python -m pytest backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_alias_sql_assets.py backend/tests/test_semantic_ambiguous_identity_sql.py -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add sql/semantic/ backend/services/data_pipeline/refresh_registry.py backend/tests/data_pipeline/test_refresh_runner.py backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/test_semantic_ambiguous_identity_sql.py
git commit -m "feat(语义层): 多候选不再静默归一，落 unknown + 告警码

- 四条语义路径统一判定：候选 1 才归属，候选 0 落 unmatched_shop_label，
  候选 >=2 落 ambiguous_shop_label 并输出 identity_candidate_count / identity_candidates
- 候选集含 disabled 账号（业务确认停用只是暂时的，唯一性判定用完整候选集）
- 候选视图本批次**不改**（区域感知匹配属第二批 ⑨；本批次只给别名表加列与约束）"
```

---

## Task 8: 语义层部署到 live + MV 刷新 + 前后对比

**Files:**
- Modify: `sql/semantic/orders_atomic.sql` / `analytics_atomic.sql` / `orders_monthly_atomic_mv.sql` / `analytics_monthly_atomic_mv.sql`（若上一步已同步则无改动）
- Modify: `sql/semantic/orders_monthly_atomic.sql` / `analytics_monthly_atomic.sql`（薄封装 VIEW 的显式列清单 —— 若上一步选了方案 A）
- 无新文件

**背景**：`semantic.fact_orders_atomic` / `fact_analytics_atomic` 是 **VIEW**（改定义即时生效）；`semantic.fact_orders_monthly_atomic_mv` 是 **MATVIEW**（改定义后必须 `REFRESH MATERIALIZED VIEW` 才生效），`semantic.fact_orders_monthly_atomic` 是它的薄封装 VIEW。

- [ ] **Step 1: 走仓库的语义层部署入口，不要逐个执行原始 SQL**

> **⚠ 逐个执行这 4 个 SQL 文件会 CASCADE 掉下游对象且不重建**（已实测依赖链）：
> - `sql/semantic/orders_monthly_atomic_mv.sql:6` = `DROP MATERIALIZED VIEW ... CASCADE`
>   → 依赖者 `semantic.fact_orders_monthly_atomic`（由 `sql/semantic/orders_monthly_atomic.sql:5` 创建，**不在本 Task 的文件清单里**）
>   → Step 3/Step 4 的验证查询会直接报 `relation does not exist`。
> - `sql/semantic/analytics_atomic.sql:3` = `DROP VIEW ... CASCADE`
>   → 级联掉 5 个 mart 视图：`mart.platform_day_kpi` / `platform_week_kpi` / `shop_day_kpi` / `shop_hour_traffic_kpi` / `shop_week_kpi`
>   （资产在 `sql/mart/*.sql`，同样不在清单里）。
> - `sql/semantic/analytics_monthly_atomic.sql:3` = `DROP VIEW IF EXISTS ... CASCADE` —— 同样是级联重建。
>
> MV 文件自己的注释（`:3-5`）写明 CASCADE 只在"下游视图由 runner 按依赖顺序重建"的前提下可接受。

**⚠⚠ 必须用 `scripts/rebuild_views.py` 落地视图定义变更 —— `bootstrap` 不会重建已存在的视图。**

> **这是本 Task 最容易「静默失败」的地方**（已实测 `backend/services/data_pipeline/refresh_runner.py:408`）：
> ```text
> if not recreate_views and await _target_view_kind(db, planned_target) == "v":
>     # 普通视图不在数据刷新时重建（避免 CREATE OR REPLACE VIEW 拿 ACCESS EXCLUSIVE 锁）
>     ...
>     continue
> ```
> `bootstrap_postgresql_dashboard.py` 走的正是 `execute_sql_target(recreate_views=False)`
> → **库里已存在的普通视图会被直接跳过**。
>
> 而 Task 7 改的**正是视图定义**：
> `sql/semantic/orders_atomic.sql` = `CREATE OR REPLACE VIEW`、
> `sql/semantic/analytics_atomic.sql` = `DROP VIEW ... CASCADE` + `CREATE`。
>
> 后果（必须避免）：
> - 两个 atomic 视图**保持旧定义** → `identity_warning_code` / `identity_candidate_count` / `identity_candidates` **根本不会出现** → A7 不达标；
> - 两个 monthly MV（`relkind='m'`，不走跳过分支）**会被重建** →
>   **Step 3 / Step 4 的数据核对照样「通过」** → 失败是**静默**的，
>   下游按新列写 SQL 时才会炸。
>
> 仓库自己写明了这条规矩：
> - `scripts/deploy_remote_production.sh:863-868`（Phase 2.7「视图定义变更落地」）：
>   「改了 sql/ 里的视图定义，光部署是不会生效的」；
> - `tests/test_verify_remote_deploy_contracts.py:18-28` 的 `test_deploy_script_rebuilds_view_definitions`
>   断言部署脚本里必须出现 `rebuild_views.py`；
> - `scripts/rebuild_views.py:105` 用的是 `recreate_views=True`。

**先 dry-run 看清楚要重建什么**：

```bash
python scripts/rebuild_views.py --dry-run
```

**再真跑**（不给 `--target` 就是重建整条视图链，脚本内部按 `topologically_sort_targets` 排依赖顺序、串行执行）：

```bash
python scripts/rebuild_views.py
```

> 只想重建本次改动涉及的视图也可以（`--target` 可重复）：
> ```bash
> python scripts/rebuild_views.py --target semantic.fact_orders_atomic --target semantic.fact_analytics_atomic
> ```
> 但**两个 monthly MV 也必须重建**（它们要加 `identity_candidate_count` / `identity_candidates` 列），
> **所以建议直接全量跑** `python scripts/rebuild_views.py`。
>
> `rebuild_views.py` 会 `DROP ... CASCADE` 后按依赖顺序重建下游 —— 这正是需要的语义，
> **不要再手动逐个执行原始 SQL**。

**`bootstrap` 入口的定位要改**：它负责**补资产 + 刷新物化视图**，**不负责视图定义变更**。两者都要跑，顺序是「先 rebuild，再 bootstrap 刷新」：

```bash
python scripts/rebuild_views.py                                                                     # 1) 落地视图定义变更
python scripts/bootstrap_postgresql_dashboard.py --module all --refresh-materializations           # 2) 补资产 + 刷新
```

先只检查不改动：

```bash
python scripts/bootstrap_postgresql_dashboard.py --check --module all --json
```

> **实施者必须先跑 `--help` 确认参数**，并先 `--check` / `--dry-run` 看清楚将要动哪些对象。
> 若部署后仍有对象缺失（说明有资产不在 runner 的清单里），**用这两个入口的报告定位**，不要手动逐个执行原始 SQL。

Expected: 重建成功，`semantic.fact_orders_atomic` / `fact_analytics_atomic` / `fact_orders_monthly_atomic` / `fact_orders_monthly_atomic_mv` 以及 5 个 mart 视图全部存在。

- [ ] **Step 1b: 验证新列真的出现了（专门防「静默未生效」）**

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.connect() as c:
    for rel in ('fact_orders_atomic','fact_analytics_atomic','fact_orders_monthly_atomic','fact_analytics_monthly_atomic'):
        cols = [r[0] for r in c.execute(sa.text('''
            select column_name from information_schema.columns
             where table_schema='semantic' and table_name=:t
               and column_name in ('identity_warning_code','identity_candidate_count','identity_candidates')
             order by column_name'''), {'t': rel})]
        print(rel, '->', cols)
"
```

Expected（**改造前的 live 实测基线**：`fact_orders_atomic` 40 列 / `fact_analytics_atomic` 31 列，
两者的 `identity_*` 列**一个都没有**；`fact_orders_monthly_atomic` 16 列、`fact_analytics_monthly_atomic` 20 列，
两者都**只有** `identity_warning_code`）：

> **⚠ `information_schema.columns` 不列 MATVIEW**（实测：`fact_orders_monthly_atomic_mv` 查它返回 **0 行**，
> 而 `pg_attribute` 查到 16 列）。所以上面对两个 monthly **wrapper**（普通 VIEW）的检查是对的，
> 但**要验 MV 本身**必须查 `pg_attribute`：
>
> ```bash
> python -c "
> import sqlalchemy as sa
> eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
> with eng.connect() as c:
>     for t in ('fact_orders_monthly_atomic_mv','fact_analytics_monthly_atomic_mv'):
>         cols = [r[0] for r in c.execute(sa.text('''
>             select a.attname from pg_attribute a
>               join pg_class c on c.oid = a.attrelid
>               join pg_namespace n on n.oid = c.relnamespace
>              where n.nspname='semantic' and c.relname=:t
>                and a.attnum > 0 and not a.attisdropped
>                and a.attname like 'identity%' order by 1'''), {'t': t})]
>         print(t, '->', cols)
> "
> ```
> Expected: 两个 MV 都有 `identity_candidate_count` / `identity_candidates` / `identity_warning_code`。
> （若 Task 7 选了「方案 B」—— wrapper 不动 —— 则 wrapper 上的 `identity_candidate_count` /
> `identity_candidates` 不会有，**以 MV 的结果为准**；Task 8 Step 3/4 的核对查询也要相应改成直接查 MV。）

| 视图 | 改造后应有 |
|---|---|
| `semantic.fact_orders_atomic` | `['identity_candidate_count', 'identity_candidates', 'identity_warning_code']`（3 列） |
| `semantic.fact_analytics_atomic` | 同上 3 列 |
| `semantic.fact_orders_monthly_atomic` | 至少 `identity_warning_code`（新增两列是否出现在 wrapper 上，取决于 Task 7 的「方案 A / B」） |
| `semantic.fact_analytics_monthly_atomic` | 至少 `identity_warning_code` |

> **少了任何一列 = 视图定义没真正重建** → 回 Step 1 重跑 `rebuild_views.py`。
> **不要只看 Step 3 / Step 4 的数据核对** —— monthly MV 重建成功会让那些核对照样「通过」。

- [ ] **Step 2: 确认 MATVIEW 已刷新**

```bash
python scripts/bootstrap_postgresql_dashboard.py --module all --refresh-materializations
```

Expected: 打印刷新完成。若 runner 未覆盖 `semantic.fact_orders_monthly_atomic_mv`，则显式执行：

```bash
python -c "
import sqlalchemy as sa
eng = sa.create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
with eng.begin() as c:
    c.execute(sa.text('REFRESH MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv'))
    print('refreshed')
"
```

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

Expected:
- `unmatched_shop_label` 对应 `unknown`；
- `ambiguous_shop_label` 数量为 0 或极少（当前无同名店）；
- **live 原来那 88 行 `unresolved_shop_account` 不会凭空消失** —— 它们全部来自 `TK新加坡3C店`
  （实测 `store_label_raw='TK新加坡3C店'`、`raw_shop_id='xihong'`、候选集为空），
  改造后会按新口径落进 `unmatched_shop_label`。
  核对口径：**`unresolved_shop_account` + `unmatched_shop_label` + `ambiguous_shop_label` 三者之和 ≥ 88**，
  且这 88 行**不允许**变成 `identity_warning_code IS NULL`（那才是静默错配）；
- `missing_identity` 与 `missing_required_platform_shop_id` 保持原值（live 都是 0 行）；
- `semantic.fact_analytics_monthly_atomic_mv`（3541 行）也要跑同样的核对 —— 它的告警码词表
  同样被本次改造扩展过（Task 7 Step 4c）。

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


def test_resolve_file_identity_prefers_shop_account_id():
    """文件级身份必须优先用 shop_account_id（永不变化；店铺账号层 20/20 覆盖）。"""
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = "tiktok_sg_daone_mall_local"
        platform_shop_id = "123456"
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "tiktok_sg_daone_mall_local"


def test_resolve_file_identity_falls_back_to_platform_shop_id():
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = None
        platform_shop_id = "123456"
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "123456"


def test_resolve_file_identity_falls_back_to_raw_shop_id():
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = None
        platform_shop_id = None
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "xihong"
```

> **为什么不用 grep 源码树的写法**：那种断言在改动前就会通过（实测 `catalog_files` + `shop_account_id` 在
> `data_ingestion_service.py` / `data_sync.py` / `collection_tasks.py` 三个文件里都能 grep 到），
> 守不住任何东西。这里改成**抽出一个纯函数 `resolve_file_identity`** 并直接测它的优先级 ——
> 该函数今天不存在，测试**今天必然失败**，改完必然通过。

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_catalog_file_identity_backfill.py -q
```

Expected: **3 条全 FAIL**，报错是 `ImportError: cannot import name 'resolve_file_identity'`
（纯函数今天不存在；测试不再用 grep 源码树的写法）。

- [ ] **Step 4: 实现回填**

**4a. 抽出纯函数 `resolve_file_identity`**（放在 `backend/services/data_ingestion_service.py` 模块级）：

```python
def resolve_file_identity(file_record: Any) -> str:
    """文件级店铺身份编号。

    优先级：shop_account_id（永不变化，20 个 enabled 店铺账号全部有值） > platform_shop_id > shop_id。
    注意：**店铺账号层 20/20 覆盖 ≠ 文件层覆盖** —— `public.catalog_files.shop_account_id`
    实测只有 87/460 有值，文件层覆盖要靠 Task 9 补齐。
    三者都拿不到时返回 ``"none"``（与既有 ``file_record.shop_id or "none"`` 语义一致）。
    """
    shop_account_id = getattr(file_record, "shop_account_id", None)
    if shop_account_id:
        return str(shop_account_id).strip()
    platform_shop_id = getattr(file_record, "platform_shop_id", None)
    if platform_shop_id:
        return str(platform_shop_id).strip()
    shop_id = getattr(file_record, "shop_id", None)
    if shop_id:
        return str(shop_id).strip()
    return "none"
```

**4b. 在写 `catalog_files` 的位置回填。**

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


def test_hash_scope_contains_stable_identity_keys():
    """data_hash 作用域必须包含稳定身份编号。

    注：``shop_id`` 键**保留**（它的取值现在是稳定 id 优先），因为当
    ``shop_account_id`` 未知时仍需要靠它区分店铺；直接删掉会造成同平台多店撞 hash。
    """
    text = TARGET.read_text(encoding="utf-8")
    hash_scope = text.split("hash_scope_values = {", 1)[1].split("}", 1)[0]
    assert "shop_account_id" in hash_scope, "hash 作用域缺少 shop_account_id"
    assert "platform_shop_id" in hash_scope, "hash 作用域缺少 platform_shop_id"


def test_ingestion_uses_resolve_file_identity():
    """文件级身份必须走 resolve_file_identity（Task 9 抽出的纯函数）。"""
    text = TARGET.read_text(encoding="utf-8")
    assert "resolve_file_identity" in text, "入库没有使用 resolve_file_identity"
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
                # 优先级：shop_account_id（永不变化；店铺账号层 20/20 覆盖） > platform_shop_id > shop_id。
                # file_shop_id 会随改名变化，用它做 data_hash 作用域会导致同一份数据重复入库。
                file_shop_account_id = getattr(file_record, "shop_account_id", None) or None
                file_platform_shop_id = getattr(file_record, "platform_shop_id", None) or None
                file_shop_id = resolve_file_identity(file_record)
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

新建 `backend/tests/test_shop_account_unmatched_alias_hint.py`：

```python
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_unmatched_alias_item_exposes_claim_hint():
    """未匹配别名项必须给出认领提示。

    业务决定：TK新加坡3C店 暂不认领，必须说清「现有 TikTok 店已被其它标签 1:1 占满，
    需新建店账号才能认领」—— 否则运营看到 unknown 不知道下一步该做什么。
    """
    from backend.schemas.account import UnmatchedShopAliasItem

    assert "claim_hint" in UnmatchedShopAliasItem.model_fields, "未匹配别名项缺少 claim_hint"


def test_account_management_shows_unmatched_alias_row_count():
    """前端必须展示未匹配别名的出现次数 row_count。

    注：``order_count`` 已经在展示了，缺的是 ``row_count``（数据行数）。
    """
    vue = REPO_ROOT / "frontend" / "src" / "domains" / "platform" / "views" / "AccountManagement.vue"
    text = vue.read_text(encoding="utf-8")
    assert "row_count" in text, "前端未展示未匹配别名的 row_count"
```

> **现状核实（已实测）**：`_UNMATCHED_ALIAS_QUERY`（`backend/domains/collection/routers/shop_account_aliases.py:81-83`、`:92-94`）
> **已经**有 `COUNT(*) AS row_count` / `COUNT(DISTINCT order_id) AS order_count` / `SUM(paid_amount)`；
> `backend/schemas/account.py` 的 `UnmatchedShopAliasItem` **已经**暴露 `row_count` / `order_count` / `paid_amount`；
> `AccountManagement.vue:26-27` **已经**显示 `site` 与 `order_count`。
> → **剩下真正缺的只有两件**：前端补 `row_count`、补「暂不认领 / 需新建店账号」的说明与候选提示。
> 所以上面的测试只盯这两件（**不要**再断言"查询里要有 count"，那部分已经存在，断言它没有意义）。

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_shop_account_unmatched_alias_hint.py -q
```

Expected: 2 个 FAIL（`claim_hint` 不存在、前端没有 `row_count`）。

- [ ] **Step 3: 后端补认领提示**

- `backend/schemas/account.py` 的 `UnmatchedShopAliasItem` 增加 `claim_hint: str | None = None`；
- `backend/domains/collection/routers/shop_account_aliases.py` 的未匹配别名返回处填上提示文案，例如
  「该平台下 N 个店铺账号已被其它标签 1:1 占满，需新建店账号才能认领」。

> **实施者必须先确认**未匹配别名的来源表与字段。live 上 TikTok 订单的原始标签在
> `b_class.fact_tiktok_orders_monthly.raw_data->>'店铺'`，站点在 `raw_data->>'站点'`
> （**不是**物化列 —— 物化列有 191 行 NULL）。

- [ ] **Step 4: 前端展示**

在 `frontend/src/domains/platform/views/AccountManagement.vue` 的「未匹配店铺别名」告警面板里：
- 补 `row_count`（数据行数）展示（`order_count` 已在展示）；
- 展示后端返回的 `claim_hint` 认领提示。

- [ ] **Step 5: 运行测试 + 构建**

```bash
python -m pytest backend/tests/test_shop_account_unmatched_alias_hint.py backend/tests/test_shop_account_aliases_api.py -q
cd frontend; npm run build
```

Expected: 测试 PASS；构建成功。

- [ ] **Step 6: 提交**

```bash
git add backend/schemas/account.py backend/domains/collection/routers/shop_account_aliases.py frontend/src/domains/platform/views/AccountManagement.vue backend/tests/test_shop_account_unmatched_alias_hint.py
git commit -m "feat(店铺身份): 未匹配别名面板补出现次数与认领提示

TK新加坡3C店 按业务决定暂不认领，保持 unknown 并在面板可见，
说清「现有 TikTok 店已被其它标签 1:1 占满，需新建店账号才能认领」。"
```

---

## Task 12: 采集优先使用人工保存的会话（打通 A4）

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:896-1034`（`_open_runtime_bundle` 的会话短路条件，锚点 `:924`）
- Modify: `modules/apps/collection_center/executor_v2.py:245-309`（executor 版 bootstrap）
- Test: `backend/tests/test_collection_session_reuse_contract.py`（扩充）

**背景（spec D6 / §2.7）**：`executor_v2.py:924` 的短路条件

```
if (not has_persistent_profile and effective_storage_state is None and session_owner_id):
```

意味着**profile 目录非空时，`data/sessions` 下的 storage_state 根本不读** → 人工巡店保存的会话，对已有 profile 的账号无效。

**这是 spec 验收 A4 的唯一实现点，第一批不做它 A4 就不可达。**

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_collection_session_reuse_contract.py` 末尾追加：

```python
def test_manual_storage_state_wins_over_existing_profile():
    """人工巡店保存的会话必须优先于持久 profile 目录被读取。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    # profile 目录非空（has_persistent_profile=True）但人工会话存在 -> 必须读人工会话
    assert CollectionExecutorV2._should_prefer_manual_storage_state(
        has_persistent_profile=True,
        has_manual_storage_state=True,
    )
    assert not CollectionExecutorV2._should_prefer_manual_storage_state(
        has_persistent_profile=True,
        has_manual_storage_state=False,
    )
```

> **实施者必须先读** `executor_v2.py:896-1034` 里 `has_persistent_profile` / `effective_storage_state` / `session_owner_id`
> 的真实来源，再决定把判定抽成静态方法还是内联条件。上面的静态方法名是**建议名**，
> 若实际代码结构不同，可以换成等价形式 —— 但**必须有一个可单测的判定点**。

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest backend/tests/test_collection_session_reuse_contract.py -q -k "manual_storage_state"
```

Expected: FAIL（该判定点还不存在）。

- [ ] **Step 3: 实现**

在 `executor_v2.py` 的 `CollectionExecutorV2` 上新增静态方法：

```python
    @staticmethod
    def _should_prefer_manual_storage_state(
        *,
        has_persistent_profile: bool,
        has_manual_storage_state: bool,
    ) -> bool:
        """人工巡店保存的会话优先于持久 profile 目录（spec D6）。

        现状是「profile 目录非空就不读 data/sessions」，导致运营在面板里保存的会话
        对已有 profile 的账号完全无效。
        """
        return bool(has_manual_storage_state)
```

并把 `:924` 附近的短路条件改成：先探测 `data/sessions/<platform>/<owner>/storage_state.json`
（**用 SessionManager 的路径规则**，即 `_safe_filename` 净化后的目录名）是否存在，
存在则优先用它；profile 目录只作为没有人工会话时的兜底。

> **实施者必须核对**：
> - 探测用的路径规则必须与 `SessionManager.get_session_path` 一致（净化名），否则读不到（见第一批 Task 1）；
> - `runtime_session.py:458-462` 的 `_profile_contains_state` 只是「目录非空」判断，**不是**真会话检测 ——
>   profile 目录里的 Chromium 缓存文件也会让它返回 True。人工会话的探测必须走 `SessionManager`。

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest backend/tests/test_collection_session_reuse_contract.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_executor_session_alignment.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 端到端核对**

人工巡店保存一次会话后触发一次采集，确认采集用的是 `data/sessions/.../storage_state.json`：

```bash
Get-ChildItem data/sessions -Recurse -Filter storage_state.json | Select-Object FullName, LastWriteTime
```

Expected: 该账号的 `storage_state.json` mtime 是刚才保存的时间；采集日志里能看到读取该文件的记录。

- [ ] **Step 6: 提交**

```bash
git add modules/apps/collection_center/executor_v2.py backend/tests/test_collection_session_reuse_contract.py
git commit -m "fix(采集): 人工巡店保存的会话优先于持久 profile 目录被读取

现状 executor_v2 的短路条件是「profile 目录非空就不读 data/sessions」，
导致运营在巡店面板保存的会话对已有 profile 的账号完全无效（spec D6 / A4）。"
```

---

## 12. 第一批总验收

- [ ] **Step 1: 跑全量相关测试**

```bash
python -m pytest backend/tests/test_session_storage_roots.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_session_manager_protection.py backend/tests/test_shop_account_aliases_api.py backend/tests/data_pipeline/test_shop_identity_resolution_sql.py backend/tests/data_pipeline/test_refresh_runner.py backend/tests/test_semantic_alias_sql_assets.py backend/tests/test_alias_normalization_consistency.py backend/tests/test_semantic_ambiguous_identity_sql.py backend/tests/test_shop_identity_schema_migration.py backend/tests/test_catalog_file_identity_backfill.py backend/tests/test_data_ingestion_hash_identity.py backend/tests/test_pwcli_helpers_session_targeting.py backend/tests/test_pwcli_inspection_panel_reporting.py backend/tests/test_pwcli_native_sys_path_bootstrap.py backend/tests/test_shop_account_unmatched_alias_hint.py -q
```

Expected: 全部 PASS，且**不少于 Task 0 Step 2 的基线通过数**（基线 = 41 passed）。

- [ ] **Step 2: 核对 spec 第一批验收项**

| 验收项 | 验证方式 | 结果 |
|---|---|---|
| A1 会话保存写盘 | 面板点「保存会话」后检查 `data/sessions/<platform>/<净化owner>/storage_state.json` 的 `metadata.saved_at` 与 `metadata.manual_seeded` | |
| A2 失败可见 | `pwcli --session no-such-session-xyz state-save` 退出码 ≠ 0；面板日志可见 stderr | |
| A3 读写同路径 | Task 1 的测试 + 磁盘核对 | |
| A5 稳定编号落库 | Task 10 Step 6 | |
| A6 不静默错配 | Task 8 Step 3/4 | |
| A7 告警码词表（新旧并存） | Task 7 Step 4c（词表 + 优先级）+ Task 8 Step 4（新码 `unmatched_shop_label` / `ambiguous_shop_label` 与既有 `missing_identity` / `unresolved_shop_account` / `missing_required_platform_shop_id` 按固定优先级并存） | |
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

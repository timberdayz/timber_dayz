# 费用管理：店铺范围口径与分摊维度优化 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让费用管理页只显示该月真实相关的店铺（停用店不再出现在未来月份），修好「按店铺查看」空视图，并让快速拆分支持按平台/租户限定分摊范围。

**Architecture:** 四个改动分层落地 —— ① 数据层用一次 Alembic 软删清掉 2026-06~12 的「纯占位行」；② 接口层给费用接口补齐 `platform_code` 维度与店铺状态字段；③ 前端把可测的纯逻辑抽到独立 view-model 模块，组件只做接线；④ 分组与分摊范围全部在前端表达，**不改行的归属口径**（唯一约束 `uq_operating_costs_a_platform_shop_month` 不动）。

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic（`current_migrations/`）+ Vue 3 `<script setup>` + Element Plus 2.11.5 + node:test（前端单测）+ pytest（后端单测）

**Spec:** `docs/superpowers/specs/2026-11-28-expense-management-shop-scope-design.md`（v3）

---

## 0. 执行前须知（每个任务都适用）

| 事项 | 约定 |
|---|---|
| 提交 | 每个任务末尾做**本地 commit**，**不 push**（push 需用户明确要求） |
| 分支 | **在独立 worktree `feature/expense-shop-scope` 上执行**（见 Task 0）。主工作区当前有 BCostAnalysis 下线等 15 个在途改动，不得混入本次提交 |
| 编码 | 所有源文件 UTF-8 / LF（Windows 编辑后跑 `python scripts/verify_utf8_source_hygiene.py`） |
| 测试基线 | 仓库存在**预存在的失败测试基线**。任何"无新增失败"的结论必须用 junit XML diff 证明，不能只看数量：<br>`python -m pytest <target> -q --tb=no --junitxml=<file>.xml`<br>`python scripts/diff_pytest_junit.py <before.xml> <after.xml>`（退出码 1 = 出现新增失败） |
| PowerShell | 5.1，不支持 `&&`；前端命令用 `cd frontend` 分行执行 |
| 日志 | 终端与日志输出不得含 emoji |

### 文件清单

| 文件 | 动作 | 职责 |
|---|---|---|
| `current_migrations/versions/20261246_cleanup_expense_placeholder_rows.py` | 新建 | 软删 2026-06~12 的纯占位费用行（可逆） |
| `backend/tests/test_expense_placeholder_cleanup_migration.py` | 新建 | 迁移契约测试（谓词、范围、幂等、回滚） |
| `backend/domains/business/routers/expense_management.py` | 修改 | `/expenses/shops` 扩展、`/expenses` 加平台过滤与店铺状态、`/expenses/by-shop` 补平台维度、restore 清批次标记 |
| `backend/tests/test_expense_management_shops_scope.py` | 新建 | 接口层新行为的单测 |
| `frontend/src/utils/expenseViewModel.js` | 新建 | 费用页纯逻辑：店铺集合拆分、行排序、分摊范围选取、均摊计算 |
| `frontend/scripts/expenseViewModel.test.mjs` | 新建 | 上述纯逻辑的 node:test 单测 |
| `frontend/src/domains/business/views/finance/ExpenseManagement.vue` | 修改 | 接线 view-model；平台分段、租户副标题、「已停用」标签、快速拆分范围、按店铺视图修复 |
| `frontend/scripts/expenseManagementPage.test.mjs` | 新建 | 页面接线契约断言（仿 `targetRouteSplit.test.mjs` 范式） |
| `frontend/package.json` | 修改 | 新增两个 test 脚本 |
| `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` | 修改 | 记录可见性规则与分摊范围口径 |

---

## Task 0: 建立隔离 worktree

**Why:** 主工作区当前有 **15 个在途改动**（BCostAnalysis 下线 + 权限/菜单/路由调整，**不属于本次范围**），且 `scripts/ci_frontend_test_silence_gate.py` 目前退出码为 1（route ownership 用例红）。直接在这里动手会把两批改动混进同一批提交，也会让回归基线不可信。

**Files:**
- Create: `.worktrees/expense-scope/`（worktree 目录）

- [ ] **Step 1: 确认在途改动归属**

Run: `git status --short`
Expected: 看到 BCostAnalysis 下线相关改动（`frontend/src/domains/business/views/finance/BCostAnalysis.vue` 被删除、`menuGroups.js` / `rolePermissions.js` / `router/index.js` 改动等）。**这些不是本次任务的产物，不要碰、不要提交它们。**

- [ ] **Step 2: 建立 worktree**

Run:
```powershell
git worktree add .worktrees/expense-scope -b feature/expense-shop-scope
```
Expected: 创建分支 `feature/expense-shop-scope` 与工作区 `.worktrees/expense-scope`。

> 若仓库已有 `using-git-worktrees` 规范脚本，优先使用它；本步骤是等价的手工路径。

- [ ] **Step 3: 把两份文档带进 worktree**

Run:
```powershell
Copy-Item docs/superpowers/specs/2026-11-28-expense-management-shop-scope-design.md .worktrees/expense-scope/docs/superpowers/specs/
Copy-Item docs/superpowers/plans/2026-11-28-expense-management-shop-scope.md .worktrees/expense-scope/docs/superpowers/plans/
```
Expected: 两个文档复制到位。

- [ ] **Step 4: 实测当前 Alembic head，确定本迁移的 `down_revision`**

⚠️ **主工作区有在途迁移** `current_migrations/versions/20261245_drop_b_cost_analysis_views.py`（BCost 下线，**未跟踪**），它的 `down_revision` 也是 `current_schema_20261244_drop_employee_shop_assignment_role`。若本迁移也指向 20261244，合回 main 后就会出现**两个 head**，`alembic upgrade head` 会失败。

先实测当前 head：

Run:
```powershell
Get-ChildItem current_migrations/versions/*.py | ForEach-Object {
  $c = Get-Content $_.FullName -Raw
  $r = [regex]::Match($c, 'revision = "([^"]+)"').Groups[1].Value
  $d = [regex]::Match($c, 'down_revision = "([^"]+)"').Groups[1].Value
  if ($r) { "$r <- $d" }
}
```
Expected: 列出全部 revision 链；找出**没有出现在任何 `down_revision` 里**的那个 = 当前 head。

据此二选一确定 `down_revision`：

| 情况 | `down_revision` 取值 |
|---|---|
| **当前实测即此情形**：在途的 `20261245_drop_b_cost_analysis_views` 仍在主工作区（未跟踪），会与本改动一起进 main | `current_schema_20261245_drop_b_cost_analysis_views` |
| 该在途迁移被放弃（未提交也未合并） | `current_schema_20261244_drop_employee_shop_assignment_role` |

> 两种情形下 worktree 内的 revision 链都只呈现**一个 head**（在途文件不在 worktree 里），
> 契约测试「真扫 revision 链判单头」会绿；但只有第一种情形合回 main 后链路才完整。
> ⇒ **默认取第一种**（`current_schema_20261245_drop_b_cost_analysis_views`），
> 迁移只在 main 上（带完整链）执行。

> 本迁移的文件名用 **`20261246_...`**（避开在途的 20261245 编号），revision 同名 `current_schema_20261246_cleanup_expense_placeholder_rows`。
> ⚠️ 若取第二种情况，本迁移在 worktree 内是单头（可独立测试）；若取第一种，**worktree 内链会缺一环**，因此本迁移**只在带完整迁移链的 main 上执行**（发版流程），worktree 内只做代码与契约测试，不执行迁移。

- [ ] **Step 5: 后续所有任务都在 worktree 内执行**

```powershell
cd .worktrees/expense-scope
```

---

## Task 1: 建立测试基线快照

**Files:**
- Create: `output/junit_expense_base.xml`（测试产物，不提交）

- [ ] **Step 1: 确认工作区状态（在 worktree 内）**

Run: `git status --short`
Expected: **干净**（只有 Task 0 复制进来的两份未跟踪文档）。若看到 BCostAnalysis 下线相关改动，说明还在主工作区 —— 回到 Task 0 Step 4 的 worktree 目录再执行。

- [ ] **Step 2: 生成费用相关测试的基线 junit XML**

Run:
```powershell
python -m pytest backend/tests/test_expense_management_routes.py backend/tests/test_expense_management_soft_delete_contract.py backend/tests/test_operating_cost_schema_contract.py backend/tests/test_operating_cost_platform_code_migration_contract.py -q --tb=no --junitxml=output/junit_expense_base.xml
```
Expected: 生成 `output/junit_expense_base.xml`。**实测基线为 11 passed / 0 failed**（这 4 个文件当前无预存在失败）；若你本地基线不同，以你本地的实际数字为准并在 Task 10 用 diff 比对。

- [ ] **Step 3: 确认 junit diff 工具可用**

Run: `python scripts/diff_pytest_junit.py output/junit_expense_base.xml output/junit_expense_base.xml`
Expected: 输出 `COMMON` 全量、`NEW` 为空、退出码 0。（该脚本**不支持 `--help`**，直接传两个 XML 路径即可。）

---

## Task 2: D1 — 软删未来月份占位行

**Files:**
- Create: `current_migrations/versions/20261246_cleanup_expense_placeholder_rows.py`
- Create: `backend/tests/test_expense_placeholder_cleanup_migration.py`

- [ ] **Step 1: 写失败的契约测试**

Create `backend/tests/test_expense_placeholder_cleanup_migration.py`：

```python
"""费用占位行清理迁移的契约守护。

背景见 spec §D1：2026-06-09 15:51 的一次批量操作，为当时所有运营店铺预建了
2026 年 1-12 月的空费用行，并写入「每月 20,000 元人力成本」按 19 家店均摊
的结果。这些行不是业务事实，导致已停用店铺在 11 月仍出现在费用管理页。

本守护把「只清纯占位行、只清 2026-06 及以后、可逆」钉在 CI 里。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = "current_migrations/versions/20261246_cleanup_expense_placeholder_rows.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_migration_targets_only_placeholder_rows():
    source = _read(MIGRATION)
    for column in (
        "rent_amount",
        "marketing_amount",
        "utility_amount",
        "ai_token_amount",
        "other_amount",
    ):
        assert f"COALESCE({column}, 0) = 0" in source, (
            f"占位行判定必须要求 {column} 为 0，否则会误删真实费用行"
        )
    assert "COALESCE(total_amount, 0) = COALESCE(labor_amount, 0)" in source
    assert "COALESCE(remark, '') = ''" in source
    assert "attachments" in source
    assert "deleted_at IS NULL" in source


def test_migration_scope_starts_at_2026_06():
    source = _read(MIGRATION)
    assert 'CLEANUP_START = "2026-06"' in source
    assert 'CLEANUP_END = "2026-12"' in source
    assert "BETWEEN" in source


def test_migration_is_reversible_and_marked():
    source = _read(MIGRATION)
    assert "def downgrade()" in source
    assert "BATCH_MARK" in source
    assert "deleted_at = NULL" in source
    assert "deleted_at IS NOT NULL" in source, (
        "downgrade 必须限定 deleted_at IS NOT NULL，否则会误清存活行的 remark"
    )


def test_migration_revision_chain_is_single_head():
    """真扫全仓 revision/down_revision 判单头。

    字符串断言抓不到「双头」：主工作区有一个在途迁移（BCost 下线，未跟踪）可能与本迁移
    同父，合回 main 后就会出现两个 head，`alembic upgrade head` 直接失败。
    """
    import re

    versions_dir = ROOT / "current_migrations/versions"
    revisions = set()
    down_revisions = set()
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision = "([^"]+)"', text, re.M)
        down = re.search(r'^down_revision = "([^"]+)"', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            down_revisions.add(down.group(1))

    heads = revisions - down_revisions
    assert len(heads) <= 1, (
        f"迁移链出现多个 head: {sorted(heads)} —— "
        "本迁移的 down_revision 必须接在当前 head 之后（见 Task 0 Step 5）"
    )


def test_migration_declares_expected_revision_ids():
    source = _read(MIGRATION)
    assert (
        'revision = "current_schema_20261246_cleanup_expense_placeholder_rows"'
        in source
    )
    assert "down_revision = " in source


def test_restore_route_clears_batch_marker():
    source = _read("backend/domains/business/routers/expense_management.py")
    assert "BATCH_MARK_PREFIX" in source, (
        "恢复接口必须清掉占位行批次标记，否则恢复后存活行仍带假标记"
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_expense_placeholder_cleanup_migration.py -q`
Expected: FAIL —— `FileNotFoundError`（迁移文件还不存在）。

- [ ] **Step 3: 写迁移**

Create `current_migrations/versions/20261246_cleanup_expense_placeholder_rows.py`：

```python
"""清理费用管理里的「未来月份占位行」。

背景
----
2026-06-09 15:51 的一次批量操作，为当时所有运营店铺预建了 2026 年 1-12 月
共 12 个月的空费用行，并写入「每月 20,000 元人力成本」按 19 家店均摊的结果
（每店 1052.63 = 20000 / 19）。这些行：

* ``remark`` / ``attachments`` 全空 —— 没有任何人工录入痕迹；
* 六个成本科目里除 ``labor_amount`` 外全是 0；
* ``created_at`` 全部相同（同一批 INSERT）；
* 06~12 月每月金额完全相同（整 20,000），而真实工资单投影
  （``finance.employee_labor_cost_allocations`` 的 2026-07 / 2026-10）
  是 31,184.61 / 25,291.93 这类非整数值。

⇒ 它们不是业务事实，是那次批量操作的副作用。已停用店铺因此在 11 月
仍会出现在费用管理页面上（见 spec §1 P1/P2）。

本迁移做什么
------------
把 2026-06 ~ 2026-12 的**纯占位行**软删（``deleted_at`` + ``deleted_by``
+ 批次标记 ``remark``），共 113 行、labor 合计 118,947.37。

为什么不碰 2026-01 ~ 2026-05
-----------------------------
那 18 行同形态行落在历史月份，与真实录入行混在同一批数据里
（ETERNALBLOOM_SG 的 2026-01 行含真实租金 50.30）。清 06 之后已能解决
「停用店出现在未来月份」；历史月份的口径留给「店铺营业时间轴」方案
（spec §10 V2 债务）一并处理。

连带影响（已由业务签字确认）
--------------------------
看板业务概览 2026-06 / 09 / 11 / 12 的成本会从 20,000 变为 ``--``，
2026-08 从 20,027.79 变为 1,080.42 —— 这是**更真实**的状态：
那几个月本来就没有任何人工录入的费用，也没有工资单投影
（``finance.employee_labor_cost_allocations`` 只有 2026-07 / 2026-10）。
同仓库先例：``20261243_drop_legacy_profit_basis`` 同样接受"删掉后那些月份
变成空白，这是刻意的"。

可逆性
------
**可逆**：``downgrade()`` 按批次标记精确还原这 113 行。
数据可恢复性另由发版流程的迁移前备份（``perform_pre_migration_backup``）兜底。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261246_cleanup_expense_placeholder_rows"
down_revision = "current_schema_20261244_drop_employee_shop_assignment_role"
branch_labels = None
depends_on = None


#: 批次标记：写在 ``remark`` 上，让软删行在「已删除费用记录」区可识别，
#: 也让 ``downgrade()`` 能精确还原本批次。
BATCH_MARK = "[占位行清理 2026-11-28]"

CLEANUP_START = "2026-06"
CLEANUP_END = "2026-12"

#: ``core.dim_users.user_id`` = 4（xihong，超管），与既有 5 条软删行一致。
CLEANUP_BY = 4

#: 纯占位行判定：除人力费外六个科目全 0，且无备注、无附件。
PLACEHOLDER_PREDICATE = """
    deleted_at IS NULL
    AND COALESCE(rent_amount, 0) = 0
    AND COALESCE(marketing_amount, 0) = 0
    AND COALESCE(utility_amount, 0) = 0
    AND COALESCE(ai_token_amount, 0) = 0
    AND COALESCE(other_amount, 0) = 0
    AND COALESCE(total_amount, 0) = COALESCE(labor_amount, 0)
    AND COALESCE(remark, '') = ''
    AND COALESCE(attachments, '[]'::jsonb) = '[]'::jsonb
"""


def upgrade() -> None:
    statement = sa.text(
        f"""
        UPDATE a_class.operating_costs
           SET deleted_at = now(),
               deleted_by = :deleted_by,
               remark = :batch_mark,
               updated_at = now()
         WHERE year_month BETWEEN :start_month AND :end_month
           AND {PLACEHOLDER_PREDICATE}
        """
    ).bindparams(
        sa.bindparam("deleted_by", value=CLEANUP_BY),
        sa.bindparam("batch_mark", value=BATCH_MARK),
        sa.bindparam("start_month", value=CLEANUP_START),
        sa.bindparam("end_month", value=CLEANUP_END),
    )
    op.execute(statement)


def downgrade() -> None:
    statement = sa.text(
        f"""
        UPDATE a_class.operating_costs
           SET deleted_at = NULL,
               deleted_by = NULL,
               remark = '',
               updated_at = now()
         WHERE remark = :batch_mark
           AND deleted_at IS NOT NULL
           AND year_month BETWEEN :start_month AND :end_month
        """
    ).bindparams(
        sa.bindparam("batch_mark", value=BATCH_MARK),
        sa.bindparam("start_month", value=CLEANUP_START),
        sa.bindparam("end_month", value=CLEANUP_END),
    )
    op.execute(statement)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest backend/tests/test_expense_placeholder_cleanup_migration.py -q`
Expected: **4 passed / 1 failed** —— `test_restore_route_clears_batch_marker` 此时仍会失败（restore 路由还没改，那部分在 Task 5）；其余 4 条必须通过。

- [ ] **Step 5: 在本地库上验证迁移命中数（只读预演）**

Run:
```powershell
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -P pager=off -c "SELECT COUNT(*) AS hit_rows, SUM(labor_amount) AS labor FROM a_class.operating_costs WHERE deleted_at IS NULL AND year_month BETWEEN '2026-06' AND '2026-12' AND COALESCE(rent_amount,0)=0 AND COALESCE(marketing_amount,0)=0 AND COALESCE(utility_amount,0)=0 AND COALESCE(ai_token_amount,0)=0 AND COALESCE(other_amount,0)=0 AND COALESCE(total_amount,0)=COALESCE(labor_amount,0) AND COALESCE(remark,'')='' AND COALESCE(attachments,'[]'::jsonb)='[]'::jsonb;"
```
Expected: `hit_rows = 113`，`labor = 118947.37`。
**这一步只读，不执行迁移**（迁移由发版流程在带备份的环境执行）。

- [ ] **Step 6: 提交**

```powershell
git add current_migrations/versions/20261246_cleanup_expense_placeholder_rows.py backend/tests/test_expense_placeholder_cleanup_migration.py
git commit -m "feat(finance): 软删费用管理未来月份占位行"
```

---

## Task 3: D2 — `/expenses/shops` 扩展

**Files:**
- Modify: `backend/domains/business/routers/expense_management.py:219-281`
- Create: `backend/tests/test_expense_management_shops_scope.py`

- [ ] **Step 1: 写失败的测试**

Create `backend/tests/test_expense_management_shops_scope.py`：

```python
"""`GET /expenses/shops` 的店铺范围契约。

口径：``core.shop_accounts.enabled`` 是权威 SSOT（``core.dim_shops.is_active``
只是派生副本，已漂移）。接口默认只回在营店；``include_disabled=true`` 时
回全部运营店铺并带上状态与租户字段，供前端标注「已停用」与分组。
"""

import pytest

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db


def _make_user():
    from types import SimpleNamespace

    return SimpleNamespace(
        user_id=1,
        username="tester",
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((str(query), params))
        return _ScalarRows(self.rows)


def _shop(**kwargs):
    from types import SimpleNamespace

    base = dict(
        id=1,
        platform="shopee",
        shop_account_id="shopee_sg_x_local",
        platform_shop_id="123456",
        store_name="x.sg",
        internal_code="X_SG",
        enabled=True,
        business_role="operating_store",
        main_account_id="main-1",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_shops_default_excludes_disabled(monkeypatch):
    """默认路径必须过滤 enabled；只有 include_disabled=true 才放行停用店。"""
    from backend.domains.business.routers import expense_management as module

    db = _DB([_shop()])
    monkeypatch.setattr(module, "get_async_db", lambda: db)
    monkeypatch.setattr(module, "MainAccount", _shop)

    result = await module.list_expense_shops(db=db, current_user=_make_user())

    # SQLAlchemy 把枚举值渲染成绑定参数，SQL 文本里是 business_role 而非 operating_store
    shop_sql = [sql for sql, _ in db.executed if "business_role" in sql]
    assert shop_sql, "必须查询运营店铺（business_role = operating_store）"
    assert "enabled" in shop_sql[0], "默认路径必须过滤 enabled"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_shops_include_disabled_returns_status_fields(monkeypatch):
    from backend.domains.business.routers import expense_management as module

    disabled = _shop(
        id=51,
        shop_account_id="shopee_sg_eternalbloom_local",
        platform_shop_id="1292370001",
        store_name="eternalbloom.sg",
        internal_code="ETERNALBLOOM_SG",
        enabled=False,
    )

    class _DB:
        def __init__(self):
            self.sql = ""

        async def execute(self, query, params=None):
            self.sql = str(query)
            return _ScalarRows([disabled])

    db = _DB()
    monkeypatch.setattr(module, "get_async_db", lambda: db)
    monkeypatch.setattr(module, "MainAccount", _shop)

    result = await module.list_expense_shops(
        include_disabled=True, db=db, current_user=_make_user()
    )

    items = result["data"]
    assert len(items) == 1
    item = items[0]
    assert item["enabled"] is False
    assert item["internal_code"] == "ETERNALBLOOM_SG"
    assert item["main_account_id"] == "main-1"
    assert "platform_shop_id" in item
    assert "shop_account_id" in item
```

> **实施提示**：上面的第二个用例需要 `list_expense_shops` 支持 `include_disabled` 关键字参数且返回这些字段；第一个用例是占位，实施时按实际实现补全断言（重点断言 SQL 里出现 `enabled` 过滤）。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_expense_management_shops_scope.py -q`
Expected: FAIL —— `MainAccount` 未导入 / `include_disabled` 参数不存在。

- [ ] **Step 3: 改实现**

Modify `backend/domains/business/routers/expense_management.py`：

1. 导入 `MainAccount`：
```python
from modules.core.db import (
    DimUser,
    MainAccount,
    ShopAccount,
)
```

2. 替换 `list_expense_shops`（当前在 `:219-281`）：

```python
@router.get("/shops", response_model=Dict[str, Any])
async def list_expense_shops(
    include_disabled: bool = Query(
        False, description="是否包含已停用店铺（用于标注与历史查询）"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """
    获取供费用管理使用的店铺列表。

    口径：``core.shop_accounts`` 是权威 SSOT。
    - 默认只回在营店（``enabled = true`` 且 ``business_role = 'operating_store'``）；
    - ``include_disabled=true`` 时回全部运营店铺，并带上 ``enabled`` /
      ``internal_code`` / ``main_account_id`` 等字段，供前端标注「已停用」
      并按平台/租户分组。

    返回字段: platform_code、shop_id、shop_name、enabled、internal_code、
    platform_shop_id、shop_account_id、main_account_id、main_account_name
    """
    try:
        logger.info(
            f"[ExpenseManagement] 开始查询店铺列表(include_disabled={include_disabled}), "
            f"用户: {current_user.username if current_user else 'unknown'}"
        )

        query = (
            select(ShopAccount)
            .where(ShopAccount.business_role == "operating_store")
            .order_by(ShopAccount.platform, ShopAccount.store_name)
        )
        if not include_disabled:
            query = query.where(ShopAccount.enabled.is_(True))

        rows = (await db.execute(query)).scalars().all()
        logger.info(f"[ExpenseManagement] 查询到 {len(rows)} 条店铺记录")

        main_account_names = await _load_main_account_names(db)

        items = []
        for r in rows:
            try:
                items.append(
                    {
                        "platform_code": r.platform.lower() if r.platform else None,
                        "shop_id": getattr(r, "platform_shop_id", None)
                        or getattr(r, "shop_account_id", None)
                        or getattr(r, "shop_id", None)
                        or getattr(r, "account_id", None)
                        or str(r.id),
                        "shop_name": getattr(r, "store_name", None)
                        or getattr(r, "shop_account_id", None)
                        or getattr(r, "account_id", None)
                        or "",
                        "enabled": bool(getattr(r, "enabled", False)),
                        "internal_code": getattr(r, "internal_code", None),
                        "platform_shop_id": getattr(r, "platform_shop_id", None),
                        "shop_account_id": getattr(r, "shop_account_id", None),
                        "main_account_id": getattr(r, "main_account_id", None),
                        "main_account_name": main_account_names.get(
                            getattr(r, "main_account_id", None), ""
                        ),
                    }
                )
            except Exception as item_err:
                logger.warning(
                    f"[ExpenseManagement] 处理店铺记录失败 (id={r.id}): {item_err}"
                )
                continue

        logger.info(f"[ExpenseManagement] 成功返回 {len(items)} 条店铺记录")
        return {"success": True, "data": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ExpenseManagement] 查询费用用店铺列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询店铺列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500,
        )
```

3. 新增租户名辅助函数（放在 `list_expense_shops` 之前）：

```python
async def _load_main_account_names(db: AsyncSession) -> Dict[str, str]:
    """租户 ID → 租户名称。取不到就返回空表，不影响主流程。"""
    try:
        result = await db.execute(
            select(MainAccount.main_account_id, MainAccount.main_account_name)
        )
        return {
            str(row[0] or ""): str(row[1] or "")
            for row in result.fetchall()
            if row[0]
        }
    except Exception as exc:
        logger.warning(f"[ExpenseManagement] 读取租户名称失败，忽略租户维度: {exc}")
        return {}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest backend/tests/test_expense_management_shops_scope.py -q`
Expected: PASS。

- [ ] **Step 5: 跑既有费用路由测试防回归**

Run: `python -m pytest backend/tests/test_expense_management_routes.py backend/tests/test_expense_management_soft_delete_contract.py -q --tb=short`
Expected: 与 Task 1 基线一致（无新增失败）。

- [ ] **Step 6: 提交**

```powershell
git add backend/domains/business/routers/expense_management.py backend/tests/test_expense_management_shops_scope.py
git commit -m "feat(finance): 费用店铺列表支持含停用店铺并带租户维度"
```

---

## Task 4: D3 — `/expenses` 增加平台过滤与店铺状态

**Files:**
- Modify: `backend/domains/business/routers/expense_management.py:603-737`
- Modify: `backend/tests/test_expense_management_shops_scope.py`（追加用例）

- [ ] **Step 1: 写失败的测试**

追加到 `backend/tests/test_expense_management_shops_scope.py`：

```python
def test_expense_list_sql_joins_shop_accounts_with_platform_and_dual_key():
    """费用列表必须按 platform + (platform_shop_id OR shop_account_id) 关联店铺。

    只按 platform_shop_id 关联会漏掉全部 6 家 TikTok 店（其 platform_shop_id 为空，
    费用行存的是 shop_account_id）。
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/business/routers/expense_management.py"
    ).read_text(encoding="utf-8")

    assert "shop_accounts" in source
    assert "platform_shop_id" in source
    assert "shop_account_id" in source
    assert "shop_enabled" in source
    assert "main_account_id" in source
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_expense_management_shops_scope.py -q`
Expected: FAIL —— `shop_enabled` 尚未出现。

- [ ] **Step 3: 改实现**

Modify `backend/domains/business/routers/expense_management.py` 的 `list_expenses`（当前 `:603-737`）：

1. 签名加平台过滤与年度过滤（`year` 服务于 D7 的「按店铺」下拉集合：需要知道某年哪些店有记录）：

```python
@router.get("", response_model=Dict[str, Any])
async def list_expenses(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="年月筛选(YYYY-MM)"),
    year: Optional[str] = Query(None, description="年份筛选(YYYY)"),
    platform_code: Optional[str] = Query(None, description="平台筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=1000, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
```

2. `where_conditions` 增加平台与年度条件（**列名保持裸写**，因为同一段 `where_clause` 同时被 `count_query` 与 `data_query` 复用，而 `data_query` 会改表别名；`core.shop_accounts` 没有 `platform_code` / `shop_id` 列，因此裸列名不产生歧义）：

```python
        if platform_code:
            where_conditions.append("LOWER(COALESCE(platform_code, '')) = :platform_code")
            params["platform_code"] = platform_code.strip().lower()
        if year:
            where_conditions.append("year_month LIKE :year_pattern")
            params["year_pattern"] = f"{year}-%"
```

3. `data_query` 的 SELECT 段改为带店铺信息的连接（**注意：连接必须用 `DISTINCT` 兜底防止一店多行放大**）：

```sql
            SELECT DISTINCT
                oc.id,
                oc.shop_id,
                oc."platform_code" as platform_code,
                oc.year_month,
                oc.rent_amount as rent,
                oc.marketing_amount as marketing_fee,
                oc.utility_amount as utilities,
                oc.ai_token_amount as ai_token_cost,
                oc.labor_amount as labor_cost,
                oc.other_amount as other_costs,
                oc.total_amount as total_cost,
                oc.remark as note,
                oc.attachments,
                oc.is_locked as locked,
                oc.created_at,
                oc.updated_at,
                sa.enabled as shop_enabled,
                sa.internal_code as shop_internal_code,
                sa.shop_account_id as shop_shop_account_id,
                sa.platform_shop_id as shop_platform_shop_id,
                sa.main_account_id as shop_main_account_id,
                ma.main_account_name as shop_main_account_name
            FROM a_class.operating_costs oc
            LEFT JOIN core.shop_accounts sa
                   ON sa.platform = oc."platform_code"
                  AND (sa.platform_shop_id = oc.shop_id
                       OR sa.shop_account_id = oc.shop_id)
            LEFT JOIN core.main_accounts ma
                   ON ma.main_account_id = sa.main_account_id
            WHERE {where_clause}
              AND oc.deleted_at IS NULL
            ORDER BY oc.year_month DESC, oc.shop_id
            LIMIT :limit OFFSET :offset
```

> 表别名变化：`FROM a_class.operating_costs` 必须改成 `oc`，所有列前缀同步改。`count_query` 保持原样（不连接，避免计数被放大）。

4. items 构造里补字段：
```python
                    "shop_enabled": row.shop_enabled,
                    "shop_internal_code": row.shop_internal_code,
                    "shop_shop_account_id": row.shop_shop_account_id,
                    "shop_platform_shop_id": row.shop_platform_shop_id,
                    "shop_main_account_id": row.shop_main_account_id,
                    "shop_main_account_name": row.shop_main_account_name,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest backend/tests/test_expense_management_shops_scope.py backend/tests/test_expense_management_routes.py -q --tb=short`
Expected: PASS + 与基线一致。

- [ ] **Step 5: 在本地库验证连接不会放大行数（只读）**

Run:
```powershell
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -P pager=off -c "SELECT COUNT(*) AS before_rows FROM a_class.operating_costs oc WHERE oc.deleted_at IS NULL;" -c "SELECT COUNT(*) AS after_rows FROM (SELECT DISTINCT oc.id FROM a_class.operating_costs oc LEFT JOIN core.shop_accounts sa ON sa.platform = oc.platform_code AND (sa.platform_shop_id = oc.shop_id OR sa.shop_account_id = oc.shop_id) LEFT JOIN core.main_accounts ma ON ma.main_account_id = sa.main_account_id WHERE oc.deleted_at IS NULL) t;"
```
Expected: 两个数字相等（当前 228）。

- [ ] **Step 6: 提交**

```powershell
git add backend/domains/business/routers/expense_management.py backend/tests/test_expense_management_shops_scope.py
git commit -m "feat(finance): 费用列表补平台过滤与店铺状态维度"
```

---

## Task 5: D4 + restore — 按店铺查询补平台维度、恢复清批次标记

**Files:**
- Modify: `backend/domains/business/routers/expense_management.py`（`list_expenses_by_shop` 当前 `:473-600`；`restore_expense` 当前 `:1424-1471`）
- Modify: `backend/tests/test_expense_management_shops_scope.py`

- [ ] **Step 1: 写失败的测试**

追加：

```python
def test_by_shop_accepts_platform_code_and_restore_clears_marker():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/business/routers/expense_management.py"
    ).read_text(encoding="utf-8")

    assert "BATCH_MARK_PREFIX" in source
    assert "platform_code" in source
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_expense_management_shops_scope.py -q`
Expected: FAIL —— `BATCH_MARK_PREFIX` 不存在。

- [ ] **Step 3: 改 `list_expenses_by_shop`**

签名加参数：
```python
async def list_expenses_by_shop(
    shop_id: str = Query(..., description="店铺ID"),
    platform_code: Optional[str] = Query(None, description="平台筛选"),
    year: Optional[str] = Query(None, description="年份(YYYY)，不传则返回所有数据"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
```

`where_clause` 构造改为：
```python
        where_clause = "shop_id = :shop_id"
        params = {"shop_id": shop_id}

        if platform_code:
            where_clause += " AND LOWER(COALESCE(\"platform_code\", '')) = :platform_code"
            params["platform_code"] = platform_code.strip().lower()

        if year:
            where_clause += " AND year_month LIKE :year_pattern"
            params["year_pattern"] = f"{year}-%"
```

> 注意 SQL 里列名是 `"platform_code"`（带双引号），其它列是裸小写。

- [ ] **Step 4: 改 restore 路由清批次标记**

路由实现在 `backend/domains/business/routers/expense_management.py:1424-1471`（`restore_expense`）。

1. 在模块常量区加：

```python
#: 占位行清理批次标记前缀（与迁移 current_schema_20261246_cleanup_expense_placeholder_rows 的 BATCH_MARK 一致）。
BATCH_MARK_PREFIX = "[占位行清理"
```

2. 把 `restore_query`（当前 `:1449-1457`）的 SQL 改为：

```python
        restore_query = text(
            """
            UPDATE a_class.operating_costs
            SET deleted_at = NULL,
                deleted_by = NULL,
                remark = CASE
                            WHEN remark LIKE :batch_prefix THEN ''
                            ELSE remark
                          END,
                updated_at = NOW()
            WHERE id = :expense_id
        """
        )
        await db.execute(
            restore_query,
            {
                "expense_id": expense_id,
                "batch_prefix": f"{BATCH_MARK_PREFIX}%",
            },
        )
```

> ⚠️ `BATCH_MARK_PREFIX` 是模块常量，拼接进 LIKE 参数没有注入面。若后续改为用户输入，必须改用绑定参数。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest backend/tests/test_expense_management_shops_scope.py backend/tests/test_expense_placeholder_cleanup_migration.py backend/tests/test_expense_management_routes.py -q --tb=short`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/domains/business/routers/expense_management.py backend/tests/test_expense_management_shops_scope.py
git commit -m "feat(finance): 按店铺查询补平台维度并清理恢复行的批次标记"
```

---

## Task 6: 前端 view-model 抽取（TDD 核心）

**Files:**
- Create: `frontend/src/utils/expenseViewModel.js`
- Create: `frontend/scripts/expenseViewModel.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: 写失败的测试**

Create `frontend/scripts/expenseViewModel.test.mjs`：

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildExpenseRowKey,
  countSplitTargets,
  distributeEvenly,
  resolveQuickSplitTargets,
  sortExpenseRows,
  splitShopsByAvailability
} from '../src/utils/expenseViewModel.js'

const SHOPS = [
  {
    platform_code: 'shopee',
    shop_id: '1391124228',
    internal_code: 'HX_HOME_SG',
    enabled: true,
    main_account_id: 'shopee KR'
  },
  {
    platform_code: 'shopee',
    shop_id: '1292370001',
    internal_code: 'ETERNALBLOOM_SG',
    enabled: false,
    main_account_id: 'hongxikeji:main'
  },
  {
    platform_code: 'tiktok',
    shop_id: 'tiktok_sg_daone_mall_local',
    internal_code: 'FIORO SG',
    enabled: true,
    main_account_id: 'Tiktok 1店'
  }
]

test('店铺集合按启用状态拆成全部与在营两组', () => {
  const { all, operating } = splitShopsByAvailability(SHOPS)
  assert.equal(all.length, 3)
  assert.equal(operating.length, 2)
  assert.equal(operating.some((s) => s.shop_id === '1292370001'), false)
})

test('行键用 (platform_code, shop_account_id)，跨平台语义一致', () => {
  // 店铺目录行：Shopee 用平台店铺 ID 作 shop_id，但键取账号 ID
  assert.equal(
    buildExpenseRowKey({
      platform_code: 'shopee',
      shop_account_id: 'shopee_sg_a_local',
      shop_id: '1292370001'
    }),
    'shopee|shopee_sg_a_local'
  )
  // 店铺目录行：TikTok
  assert.equal(
    buildExpenseRowKey({
      platform_code: 'tiktok',
      shop_account_id: 'tiktok_sg_b_local',
      shop_id: 'tiktok_sg_b_local'
    }),
    'tiktok|tiktok_sg_b_local'
  )
  // 费用行：后端回传的 shop_shop_account_id
  assert.equal(
    buildExpenseRowKey({
      platform_code: 'shopee',
      shop_shop_account_id: 'shopee_sg_a_local',
      shop_id: '1292370001'
    }),
    'shopee|shopee_sg_a_local'
  )
  // 孤儿行回退到 shop_id，天然不与任何店铺冲突
  assert.equal(buildExpenseRowKey({ platform_code: 'shopee', shop_id: '999' }), 'shopee|999')
})

test('行按平台、租户、店铺排序', () => {
  const rows = [
    { platform_code: 'tiktok', shop_id: 'b', main_account_id: 'm1' },
    { platform_code: 'shopee', shop_id: 'z', main_account_id: 'm2' },
    { platform_code: 'shopee', shop_id: 'a', main_account_id: 'm1' }
  ]
  const sorted = sortExpenseRows(rows)
  assert.deepEqual(
    sorted.map((row) => row.shop_id),
    ['a', 'z', 'b']
  )
})

test('分摊目标只包含在营店铺', () => {
  const rows = [
    { platform_code: 'shopee', shop_id: 'a', enabled: true },
    { platform_code: 'shopee', shop_id: 'b', enabled: false }
  ]
  const targets = resolveQuickSplitTargets(rows, { platform_code: 'shopee' })
  assert.equal(targets.length, 1)
  assert.equal(targets[0].shop_id, 'a')
})

test('分摊范围可按平台或租户收窄', () => {
  const rows = SHOPS.map((shop) => ({ ...shop }))
  const byPlatform = resolveQuickSplitTargets(rows, { platform_code: 'tiktok' })
  assert.equal(byPlatform.length, 1)
  const byTenant = resolveQuickSplitTargets(rows, { main_account_id: 'Tiktok 1店' })
  assert.equal(byTenant.length, 1)
  const all = resolveQuickSplitTargets(rows, {})
  assert.equal(all.length, 2)
})

test('拆分店铺数与目标集合一致', () => {
  const rows = SHOPS.map((shop) => ({ ...shop }))
  assert.equal(countSplitTargets(rows, {}), 2)
  assert.equal(countSplitTargets(rows, { platform_code: 'tiktok' }), 1)
})

test('均摊保留分到分的尾差', () => {
  const parts = distributeEvenly(100, 3)
  assert.equal(parts.length, 3)
  assert.equal(
    parts.reduce((sum, value) => sum + value, 0),
    100
  )
})
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```powershell
cd frontend
node --test scripts/expenseViewModel.test.mjs
```
Expected: FAIL —— `Cannot find module '../src/utils/expenseViewModel.js'`。

- [ ] **Step 3: 写实现**

Create `frontend/src/utils/expenseViewModel.js`：

```javascript
/**
 * 费用管理页的纯逻辑层（可单测）。
 *
 * 为什么单独抽出来
 * ----------------
 * 费用页里最容易出错的三件事——「谁该出现在表里」「钱摊给谁」「怎么排序」——
 * 都不该埋在 .vue 模板里。这里把它们做成纯函数，由
 * `frontend/scripts/expenseViewModel.test.mjs` 直接断言。
 *
 * 口径（全站唯一）
 * ----------------
 * * 权威店铺状态：`core.shop_accounts.enabled`（`enabled === true` 才算在营）；
 * * 空白行只给在营店；已停用店若当月有费用记录则照常显示并标注，但**不参与分摊**；
 * * 分摊范围可按平台或租户收窄。
 */

/**
 * 行键：平台 + **店铺账号 ID**。
 *
 * 为什么不用 shop_id
 * -----------------
 * Shopee 的 `shop_id` 是平台店铺 ID（`1292370001`），TikTok 的是本地账号 ID
 * （`tiktok_sg_daone_mall_local`）—— **两者语义不同**。店铺账号 ID 在两个平台下
 * 语义一致且稳定，所以匹配键统一取 `(platform_code, shop_account_id)`：
 *
 * * 店铺目录行：`row.shop_account_id`（D2 新增字段）
 * * 费用行：`row.shop_shop_account_id`（D3 从连接中回传）
 * * 孤儿行（店铺账号已不存在）：回退到 `shop_id`，天然不与任何店铺冲突
 */
export function buildExpenseRowKey(row = {}) {
  const platform = row.platform_code || ''
  const account =
    row.shop_account_id || row.shop_shop_account_id || row.shop_id || ''
  return `${platform}|${account}`
}

/**
 * 店铺集合按启用状态拆分。
 * @returns {{ all: object[], operating: object[] }}
 */
export function splitShopsByAvailability(shops = []) {
  const all = []
  const operating = []
  ;(Array.isArray(shops) ? shops : []).forEach((shop) => {
    const item = { ...shop, is_operating: shop.enabled === true }
    all.push(item)
    if (item.is_operating) operating.push(item)
  })
  return { all, operating }
}

/** 行排序：平台 → 租户 → 店铺。 */
export function sortExpenseRows(rows = []) {
  return [...(Array.isArray(rows) ? rows : [])].sort((a, b) => {
    const platform = String(a.platform_code || '').localeCompare(String(b.platform_code || ''))
    if (platform !== 0) return platform
    const tenant = String(a.main_account_id || '').localeCompare(String(b.main_account_id || ''))
    if (tenant !== 0) return tenant
    return String(a.shop_id || '').localeCompare(String(b.shop_id || ''))
  })
}

/**
 * 解析快速拆分的分摊目标集合。
 * @param {object[]} rows 当前表格行
 * @param {{platform_code?: string, main_account_id?: string}} scope 范围；空对象 = 全部在营店
 */
export function resolveQuickSplitTargets(rows = [], scope = {}) {
  const platform = scope.platform_code || ''
  const tenant = scope.main_account_id || ''
  return (Array.isArray(rows) ? rows : []).filter((row) => {
    if (row.enabled !== true && row.is_operating !== true) return false
    if (platform && String(row.platform_code || '') !== platform) return false
    if (tenant && String(row.main_account_id || '') !== tenant) return false
    return true
  })
}

/** 拆分店铺数（与分摊目标集合口径一致）。 */
export function countSplitTargets(rows = [], scope = {}) {
  return resolveQuickSplitTargets(rows, scope).length
}

/**
 * 金额均摊：按分计算并把余数分给前面的行，保证总额分毫不差。
 */
export function distributeEvenly(totalAmount, count) {
  const totalCents = Math.round((Number(totalAmount) || 0) * 100)
  if (!count || count <= 0) return []
  const base = Math.floor(totalCents / count)
  let remainder = totalCents - base * count
  return Array.from({ length: count }, () => {
    const extra = remainder > 0 ? 1 : 0
    remainder -= extra
    return (base + extra) / 100
  })
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```powershell
cd frontend
node --test scripts/expenseViewModel.test.mjs
```
Expected: 7 passed。

- [ ] **Step 5: 注册 npm 脚本**

Modify `frontend/package.json` 的 `scripts`，在 `test:shop-display` 之后加：

```json
    "test:expense-view-model": "node --test scripts/expenseViewModel.test.mjs",
```

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/utils/expenseViewModel.js frontend/scripts/expenseViewModel.test.mjs frontend/package.json
git commit -m "feat(finance): 抽出费用页 view-model 纯逻辑并补单测"
```

---

## Task 7: D5 — 月度视图接线（集合拆分 / 时序 / 分段 / 租户 / 已停用标注）

**Files:**
- Modify: `frontend/src/domains/business/views/finance/ExpenseManagement.vue`
- Create: `frontend/scripts/expenseManagementPage.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: 写失败的页面契约测试**

Create `frontend/scripts/expenseManagementPage.test.mjs`：

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const pageSource = readFileSync(
  new URL('../src/domains/business/views/finance/ExpenseManagement.vue', import.meta.url),
  'utf8'
)

test('首屏先等店铺列表就绪再加载月度费用', () => {
  assert.ok(pageSource.includes('await loadShops()'), 'onMounted 必须 await loadShops()')
  assert.ok(
    !/onMounted\([\s\S]{0,400}loadShops\(\)\s*\n\s*loadMonthlyExpenses/.test(pageSource),
    '不得在 loadShops() 未完成时直接加载月度费用'
  )
})

test('店铺集合拆成全部与在营两组', () => {
  assert.ok(pageSource.includes('splitShopsByAvailability'))
  assert.ok(pageSource.includes('operatingShops'))
  assert.ok(pageSource.includes('allShops'))
})

test('月度表格支持平台分段与租户维度', () => {
  assert.ok(pageSource.includes('platformScope'))
  assert.ok(pageSource.includes('main_account_id'))
  assert.ok(pageSource.includes('租户'))
})

test('已停用店铺有明确标注', () => {
  assert.ok(pageSource.includes('已停用'))
  assert.ok(pageSource.includes('shop_enabled'))
})

test('快速拆分使用 view-model 的范围解析', () => {
  assert.ok(pageSource.includes('resolveQuickSplitTargets'))
  assert.ok(pageSource.includes('countSplitTargets'))
})
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```powershell
cd frontend
node --test scripts/expenseManagementPage.test.mjs
```
Expected: FAIL —— `splitShopsByAvailability` 未出现。

- [ ] **Step 3: 改 import 与状态**

1. `computed` 要加进 vue 的 import（`:771` 现在只有 `ref, reactive, onMounted`）：

```javascript
import { computed, ref, reactive, onMounted } from 'vue'
```

2. 加 view-model 的 import：

```javascript
import {
  buildExpenseRowKey,
  countSplitTargets,
  distributeEvenly,
  resolveQuickSplitTargets,
  sortExpenseRows,
  splitShopsByAvailability
} from '@/utils/expenseViewModel.js'
```

3. **删掉组件内已有的本地 `buildExpenseRowKey`**（当前 `:879-880`）—— 否则与 view-model 的同名导出重复声明，`vite build` 会直接失败：

```javascript
// 删除这两行（已由 @/utils/expenseViewModel.js 提供）
const buildExpenseRowKey = (row = {}) =>
  `${row.platform_code || ''}|${row.shop_id || ''}`
```

4. 状态区新增，并且**删除旧的 `const availableShops = ref([])`（`:786`）**，避免重复声明：

```javascript
const allShops = ref([])          // 全部运营店铺（含停用）：标注、按店铺下拉、查 platform_code
const operatingShops = ref([])     // 在营店铺：空白行生成、分摊范围
const platformScope = ref('all')   // 'all' | 'shopee' | 'tiktok'

// 快速拆分的分摊范围：**唯一**的范围来源（界面计数与实际应用都读它）
const quickSplitScope = reactive({
  platform_code: '',
  main_account_id: ''
})

// 租户选项（按当前分段内的在营店铺去重）
const tenantOptions = computed(() => {
  const ids = [...new Set(
    visibleMonthlyRows.value
      .filter((row) => row.enabled === true)
      .map((row) => row.main_account_id)
      .filter(Boolean)
  )]
  return ids.map((id) => ({ main_account_id: id, label: id }))
})
```

> ⚠️ 组件里原本所有 `availableShops` 引用点都要逐个替换，**不能留别名**（留别名会让 `allShops` 与 `operatingShops` 的区别在使用处丢失）：
>
> | 位置 | 改成 | 原因 |
> |---|---|---|
> | `:181` 按月份表格的店铺下拉 option | `allShops` | 允许回看停用店的历史行 |
> | `:447` 按店铺视图的店铺下拉 option | `shopViewOptions` | 见 Task 9（按年有记录的停用店也要能选） |
> | `:999` 生成空白行 | `operatingShops` | 停用店不生成空白行 |
> | `:1027` 匹配店铺显示名 | `allShops` | 否则停用店显示成裸 ID |
> | `:1107` `handleShopChange` 查平台 | **`allShops`** | 否则选到停用店时 `platform_code` 不更新，会存出错误行归属 |
> | `:1454` `handleAddMonthRow` 取 platform_code | **`allShops`** | 同上 |
>
> ⚠️ 这两处的查找**必须改用 `buildExpenseRowKey` 匹配**，不能继续用 `s.shop_id === row.shop_id`：
>
> ```javascript
> // :1107 handleShopChange
> const shop = allShops.value.find(
>   (s) => buildExpenseRowKey(s) === buildExpenseRowKey(row)
> )
>
> // :1454 handleAddMonthRow
> const shop = allShops.value.find(
>   (s) => buildExpenseRowKey(s) === buildExpenseRowKey({ ...row, shop_id: selectedShopId.value })
> )
> ```
>
> 键口径见 Task 6：`platform_code + shop_account_id`（两平台语义一致），费用行用后端回传的
> `shop_shop_account_id`，店铺目录行用 `shop_account_id`。

- [ ] **Step 4: 改 `loadShops`**

把现有的 `loadShops` 替换为（关键变化：请求 `include_disabled=true`，并拆两个集合）：

```javascript
const loadShops = async () => {
  try {
    const [expenseShopsResult, shopDirectoryResult] = await Promise.allSettled([
      api.get('/expenses/shops', { params: { include_disabled: true } }),
      api.getShopDirectory({ enabled: true })
    ])
    if (expenseShopsResult.status !== 'fulfilled') {
      throw expenseShopsResult.reason
    }
    const shopDirectory = shopDirectoryResult.status === 'fulfilled' ? shopDirectoryResult.value : []
    shopAccountLookup = buildShopAccountLookup(Array.isArray(shopDirectory) ? shopDirectory : [])
    const expenseShops = expenseShopsResult.value
    const rawShops = Array.isArray(expenseShops)
      ? expenseShops
      : (expenseShops?.data ?? expenseShops ?? [])

    const decorated = rawShops.map((shop) => {
      const displayMeta = resolveShopDisplay(shop, shopAccountLookup)
      return {
        ...shop,
        shop_name: displayMeta.display_name,
        secondary_name: displayMeta.secondary_name,
        canonical_shop_name: displayMeta.canonical_name,
        option_label: displayMeta.option_label,
        search_text: displayMeta.search_text
      }
    })

    const split = splitShopsByAvailability(decorated)
    allShops.value = split.all
    operatingShops.value = split.operating
  } catch (error) {
    console.error('加载店铺列表失败:', error)
    ElMessage.error(error.message || '加载店铺列表失败')
    allShops.value = []
    operatingShops.value = []
  }
}
```

> 注意：原 `loadShops` 里的 `availableShops.value = rawShops.map(...)` 整段替换为上面的写法；`availableShops` 状态本身已在 Step 3 删除。

- [ ] **Step 5: 改 `loadMonthlyExpenses` 的行组装**

把现有的行组装段（`:995-1032`）替换为：

```javascript
    // 处理月度数据
    const existingData = monthlyRes.items || []
    const shopKeySet = new Set(existingData.map((item) => buildExpenseRowKey(item)))

    // 为没有数据的**在营**店铺创建空白行（停用店不生成空白行）
    const newRows = operatingShops.value
      .filter((shop) => !shopKeySet.has(buildExpenseRowKey(shop)))
      .map((shop) => ({
        id: null,
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        shop_name: shop.shop_name,
        main_account_id: shop.main_account_id,
        main_account_name: shop.main_account_name,
        enabled: shop.enabled,
        year_month: selectedMonth.value,
        rent: 0,
        marketing_fee: 0,
        utilities: 0,
        ai_token_cost: 0,
        labor_cost: 0,
        other_costs: 0,
        total_cost: 0,
        total: 0,
        note: '',
        attachments: [],
        saving: false
      }))

    // 合并现有数据和空白行，只保留当月数据；平台/租户/店铺排序
    const merged = [
      ...existingData
        .filter((item) => item.year_month === selectedMonth.value)
        .map((item) => {
          const matched = allShops.value.find(
            (s) => buildExpenseRowKey(s) === buildExpenseRowKey(item)
          )
          return {
            ...normalizeExpenseRow(item),
            shop_name: matched?.shop_name || item.shop_id,
            main_account_id: item.shop_main_account_id || matched?.main_account_id || '',
            main_account_name: item.shop_main_account_name || matched?.main_account_name || '',
            enabled: item.shop_enabled,
            saving: false
          }
        }),
      ...newRows
    ]

    monthlyTableData.value = sortExpenseRows(merged)
```

- [ ] **Step 6: 模板加平台分段控件与租户副标题、已停用标签**

在月度视图的 `action-bar` 里（`快速拆分` 按钮之前）加：

```html
        <el-radio-group
          v-model="platformScope"
          size="default"
          class="erp-ml-sm"
          @change="handlePlatformScopeChange"
        >
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="shopee">Shopee</el-radio-button>
          <el-radio-button value="tiktok">TikTok</el-radio-button>
        </el-radio-group>
```

> Element Plus 2.11 的 `el-radio-button` 用 `value` 属性（`label` 已废弃）；若实测 `value` 不生效，退回 `label`。

店铺列单元格改为同时显示租户与「已停用」：

```html
            <template #default="{ row }">
              <el-select
                v-model="row.shop_id"
                placeholder="选择店铺"
                class="erp-w-full"
                :disabled="!!row.id"
                @change="handleShopChange(row)"
              >
                <el-option
                  v-for="shop in allShops"
                  :key="`${shop.platform_code}|${shop.shop_id}`"
                  :label="shop.option_label || shop.shop_name"
                  :value="shop.shop_id"
                >
                  <div>{{ shop.shop_name }}</div>
                  <div v-if="shop.secondary_name" class="shop-option-secondary">{{ shop.secondary_name }}</div>
                </el-option>
              </el-select>
              <div v-if="row.main_account_name || row.main_account_id" class="shop-option-secondary">
                租户：{{ row.main_account_name || row.main_account_id }}
              </div>
              <el-tag v-if="row.enabled === false" type="info" size="small">
                已停用
              </el-tag>
              <el-tag v-else-if="row.enabled === null" type="warning" size="small">
                状态未知
              </el-tag>
            </template>
```

> `shop_enabled` 为 `null` 表示费用行里的 `shop_id` 在 `core.shop_accounts` 里找不到对应账号（历史孤儿数据）。此时显示原始 ID +「状态未知」，**不丢弃该行**。

- [ ] **Step 7: 改 `onMounted`、分段过滤与计数口径**

1. 新增两个 computed（`monthlyTableData` 保留全量数据，分段只做视图过滤）：

```javascript
// 当前平台分段下的可见行（表格与月度汇总都用它）
const visibleMonthlyRows = computed(() => {
  const rows = monthlyTableData.value
  if (platformScope.value === 'all') return rows
  return rows.filter((row) => row.platform_code === platformScope.value)
})
```

2. 模板把表格数据源换成可见行：

```html
        <el-table
          v-if="!monthlyError"
          :data="visibleMonthlyRows"
          ...
```

3. 「拆分店铺数」与实际分摊范围**同源**（都读 `quickSplitScope` + `visibleMonthlyRows`）：

```html
          <div class="quick-split-meta">拆分店铺数：{{ countSplitTargets(visibleMonthlyRows, quickSplitScope) }}</div>
```

并把 `calculateMonthlySummary` 里的遍历源从 `monthlyTableData.value` 改为 `visibleMonthlyRows.value`（切到 TikTok 时，汇总卡只显示 TikTok 的金额）。

4. `onMounted` 改为先等店铺列表：

```javascript
onMounted(async () => {
  initTaskContext()
  const now = new Date()
  if (!selectedMonth.value) {
    selectedMonth.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  }
  selectedYear.value = `${now.getFullYear()}`
  await loadShops()
  await loadMonthlyExpenses()
})
```

5. 分段切换：

```javascript
const handlePlatformScopeChange = () => {
  // 分段只影响展示与拆分范围，不改数据；分摊范围跟随分段（唯一来源 quickSplitScope）
  quickSplitScope.platform_code = platformScope.value === 'all' ? '' : platformScope.value
  const stillValid = tenantOptions.value.some(
    (tenant) => tenant.main_account_id === quickSplitScope.main_account_id
  )
  if (quickSplitScope.main_account_id && !stillValid) {
    quickSplitScope.main_account_id = ''
  }
  calculateMonthlySummary()
}
```

> **年度累计卡保持全平台口径**（后端 `/expenses/summary/yearly` 不带平台维度，本次不改后端汇总接口）。为避免误解，卡片标题旁加一行小字「（全部平台）」；若后续要求年度汇总跟随分段，再单独扩展后端接口。

- [ ] **Step 8: 运行测试确认通过**

Run:
```powershell
cd frontend
node --test scripts/expenseManagementPage.test.mjs
node --test scripts/expenseViewModel.test.mjs
```
Expected: 全部 PASS。

同时注册第二个 npm 脚本（`frontend/package.json` 的 `scripts`，在 `test:expense-view-model` 之后）：

```json
    "test:expense-management-page": "node --test scripts/expenseManagementPage.test.mjs",
```

- [ ] **Step 9: 语法级校验**

Run:
```powershell
cd frontend
npm run build
```
Expected: 构建成功（`vite build` 无报错）。

- [ ] **Step 10: 提交**

```powershell
git add frontend/src/domains/business/views/finance/ExpenseManagement.vue frontend/scripts/expenseManagementPage.test.mjs frontend/package.json
git commit -m "feat(finance): 月度视图按平台分段与租户维度展示并标注已停用店铺"
```

---

## Task 8: D6 — 快速拆分范围选择

**Files:**
- Modify: `frontend/src/domains/business/views/finance/ExpenseManagement.vue`
- Modify: `frontend/scripts/expenseManagementPage.test.mjs`（追加契约用例）
- Modify: `frontend/scripts/expenseManagementQuickSplitUi.test.mjs`（同步旧文案断言）

- [ ] **Step 1: 扩充页面契约测试**

在 `frontend/scripts/expenseManagementPage.test.mjs` 追加：

```javascript
test('快速拆分提供范围选择且只覆盖目标集合', () => {
  assert.ok(pageSource.includes('quickSplitScope'))
  assert.ok(pageSource.includes('仅 Shopee'))
  assert.ok(pageSource.includes('仅 TikTok'))
  assert.ok(pageSource.includes('按租户'))
  assert.ok(
    pageSource.includes('resolveQuickSplitTargets'),
    '必须用 view-model 解析目标集合'
  )
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend` 后 `node --test scripts/expenseManagementPage.test.mjs`
Expected: FAIL —— `quickSplitScope` 不存在。

- [ ] **Step 3: 对话框与范围重置**

状态 `quickSplitScope` 已在 **Task 7 Step 3** 定义（唯一范围来源：界面计数与实际应用都读它）。`resetQuickSplitForm` 里加：

```javascript
  quickSplitScope.platform_code = platformScope.value === 'all' ? '' : platformScope.value
  quickSplitScope.main_account_id = ''
```

对话框（`quick-split-meta` 之后）加：

```html
        <el-form label-position="top" class="quick-split-form">
          <el-form-item label="分摊范围">
            <el-select v-model="quickSplitScope.platform_code" placeholder="全部在营店铺" class="erp-w-full">
              <el-option label="全部在营店铺" value="" />
              <el-option label="仅 Shopee" value="shopee" />
              <el-option label="仅 TikTok" value="tiktok" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="quickSplitScope.platform_code" label="按租户收窄（可选）">
            <el-select v-model="quickSplitScope.main_account_id" placeholder="该平台全部租户" clearable class="erp-w-full">
              <el-option
                v-for="tenant in tenantOptions"
                :key="tenant.main_account_id"
                :label="tenant.label"
                :value="tenant.main_account_id"
              />
            </el-select>
          </el-form-item>
```

- [ ] **Step 4: 改提示文案，并同步既有 UI 契约测试**

页面 `:376` 的提示语「平均分摊到当前全部店铺」与新口径（按范围拆分到在营店铺）矛盾，必须一起改：

```html
        <div class="quick-split-tip">
          按所选范围分摊到在营店铺。会覆盖这些店铺的现有金额，保存前仍可逐店修改。
        </div>
```

**同步更新既有契约测试** `frontend/scripts/expenseManagementQuickSplitUi.test.mjs`（当前 `:12` 断言旧文案）：

```javascript
test('ExpenseManagement page replaces add-all-shops action with quick split flow', () => {
  assert.equal(source.includes('为所有店铺添加'), false)
  assert.equal(source.includes('快速拆分'), true)
  assert.equal(source.includes('按所选范围分摊到在营店铺'), true)
  assert.equal(source.includes('handleApplyQuickSplit'), true)
})
```

> ⚠️ 这个既有测试**必须同步改**，否则 CI 的 `scripts/ci_frontend_test_silence_gate.py` 会直接阻断。

- [ ] **Step 5: 改 `handleApplyQuickSplit`**

```javascript
const handleApplyQuickSplit = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  // 行源与界面计数完全一致（同一 scope + 同一行源），杜绝「显示 N 家、实际改 M 家」
  const targets = resolveQuickSplitTargets(visibleMonthlyRows.value, quickSplitScope)

  if (targets.length === 0) {
    ElMessage.warning('当前范围没有可拆分的在营店铺')
    return
  }

  const scopeLabel = quickSplitScope.main_account_id
    ? `租户 ${quickSplitScope.main_account_id}`
    : quickSplitScope.platform_code === 'shopee'
      ? '仅 Shopee'
      : quickSplitScope.platform_code === 'tiktok'
        ? '仅 TikTok'
        : '全部在营店铺'

  try {
    await ElMessageBox.confirm(
      `将按「${scopeLabel}」共 ${targets.length} 家在营店铺平均拆分，并覆盖这些店铺的现有金额。是否继续？`,
      '确认快速拆分',
      { type: 'warning' }
    )
  } catch (error) {
    if (error === 'cancel') {
      return
    }
    throw error
  }

  const rentAllocations = distributeEvenly(quickSplitForm.rent, targets.length)
  const marketingAllocations = distributeEvenly(quickSplitForm.marketing_fee, targets.length)
  const utilityAllocations = distributeEvenly(quickSplitForm.utilities, targets.length)
  const aiTokenAllocations = distributeEvenly(quickSplitForm.ai_token_cost, targets.length)
  const otherAllocations = distributeEvenly(quickSplitForm.other_costs, targets.length)

  // ⚠️ 只覆盖目标集合的行；范围外的既有金额保持不变
  targets.forEach((row, index) => {
    row.rent = rentAllocations[index]
    row.marketing_fee = marketingAllocations[index]
    row.utilities = utilityAllocations[index]
    row.ai_token_cost = aiTokenAllocations[index]
    row.other_costs = otherAllocations[index]
    updateRowTotal(row)
  })

  quickSplitDialogVisible.value = false
  ElMessage.success(`快速拆分已应用到 ${targets.length} 家店铺，可继续逐店修改后保存`)
}
```

- [ ] **Step 6: 删掉组件里旧的 `distributeEvenly` 本地实现**

组件里原有的 `distributeEvenly`（`:1147-1157`）必须删除，改用 view-model 导入的版本，避免两套实现。

- [ ] **Step 7: 运行测试确认通过（含既有费用前端测试）**

Run:
```powershell
cd frontend
node --test scripts/expenseManagementPage.test.mjs
node --test scripts/expenseViewModel.test.mjs
node --test scripts/expenseManagementQuickSplitUi.test.mjs
node --test scripts/expenseManagementTerminologyUi.test.mjs
node --test scripts/expenseManagementCompatibilityUi.test.mjs
node --test scripts/expenseLaborCostPayload.test.mjs
npm run build
```
Expected: 全部 PASS + 构建成功。

- [ ] **Step 8: 提交**

```powershell
git add frontend/src/domains/business/views/finance/ExpenseManagement.vue frontend/scripts/expenseManagementPage.test.mjs frontend/scripts/expenseManagementQuickSplitUi.test.mjs
git commit -m "feat(finance): 快速拆分支持按平台与租户限定分摊范围"
```

---

## Task 9: D7 — 「按店铺查看」视图修复

**Files:**
- Modify: `frontend/src/domains/business/views/finance/ExpenseManagement.vue`
- Modify: `frontend/scripts/expenseManagementPage.test.mjs`（追加契约用例）

- [ ] **Step 1: 扩充页面契约测试**

在 `frontend/scripts/expenseManagementPage.test.mjs` 追加：

```javascript
test('按店铺视图默认选店且有空状态提示', () => {
  assert.ok(pageSource.includes('el-empty'))
  assert.ok(pageSource.includes('请先选择店铺'))
  assert.ok(pageSource.includes('暂无费用记录'))
  assert.ok(pageSource.includes('handleShopSelectChange'))
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend` 后 `node --test scripts/expenseManagementPage.test.mjs`
Expected: FAIL —— `el-empty` 不存在。

- [ ] **Step 3: 模板加空状态与已停用提示**

「按店铺查看」的表格外包一层：

```html
        <el-empty
          v-if="!selectedShopId"
          description="请先选择店铺"
        />
        <el-table
          v-else
          :data="shopTableData"
          ...
        >
```

「按店铺」操作栏的店铺下拉改为使用 `allShops`（含停用店，让历史店铺可查）：

```html
        <el-select
          v-model="selectedShopId"
          placeholder="选择店铺"
          class="erp-w-250"
          @change="handleShopSelectChange"
          filterable
        >
          <el-option
            v-for="shop in shopViewOptions"
            :key="`${shop.platform_code}|${shop.shop_id}`"
            :label="shop.option_label || shop.shop_name"
            :value="shop.shop_id"
          >
            <div>{{ shop.shop_name }}</div>
            <div v-if="shop.secondary_name" class="shop-option-secondary">{{ shop.secondary_name }}</div>
            <el-tag v-if="shop.enabled === false" type="info" size="small">已停用</el-tag>
          </el-option>
        </el-select>
```

新增「某年有费用记录的店铺」状态与加载函数（**不能用 `shopTableData` 推导**——它只有当前选中店的行，会导致停用店永远进不了下拉的死循环）：

```javascript
const shopViewRecordedIds = ref(new Set())

// 某年有费用记录的店铺集合：用于「按店铺」下拉把停用店也列出来
const loadShopViewRecordedShops = async (year) => {
  if (!year) {
    shopViewRecordedIds.value = new Set()
    return
  }
  try {
    const res = await api.get('/expenses', {
      params: { year, page_size: 1000 }
    })
    shopViewRecordedIds.value = new Set((res.items || []).map((item) => item.shop_id))
  } catch (error) {
    console.error('加载年度店铺费用记录失败:', error)
    shopViewRecordedIds.value = new Set()
  }
}
```

新增计算属性（只列在营店 ＋ 当年有记录的停用店）：

```javascript
const shopViewOptions = computed(() => {
  const recorded = shopViewRecordedIds.value
  return allShops.value.filter(
    (shop) => shop.enabled === true || recorded.has(shop.shop_id)
  )
})
```

> `computed` 已在 Task 7 Step 3 引入。

- [ ] **Step 4: 默认选第一家店**

在 `onMounted` 的 `await loadShops()` 之后加：

```javascript
  if (!selectedShopId.value) {
    const firstShop = operatingShops.value[0]
    if (firstShop) {
      selectedShopId.value = firstShop.shop_id
    }
  }
```

并在 `await loadShops()` 之后、`await loadMonthlyExpenses()` 之前调用 `await loadShopExpenses()`（仅当已选店）。

> ⚠️ **不要**在 `onMounted` 里单独调 `loadShopViewRecordedShops` —— `loadShopExpenses` 开头已经会调它，重复调用会让首屏多打一次全年 1000 行的请求。

- [ ] **Step 5: `loadShopExpenses` 传 platform_code，并刷新年度记录集合**

```javascript
    const selectedShop = allShops.value.find((s) => s.shop_id === selectedShopId.value)
    const params = { shop_id: selectedShopId.value }
    if (selectedShop?.platform_code) {
      params.platform_code = selectedShop.platform_code
    }
    if (selectedYear.value) {
      params.year = selectedYear.value
    }
```

**把 `await loadShopViewRecordedShops(selectedYear.value)` 放在 `loadShopExpenses` 的函数体第一行 —— 早退分支 `if (!selectedShopId.value) { ... return }` 之前**。放在早退之后会跳过刷新，停用店就永远进不了下拉（spec §D7 明令禁止的鸡生蛋）。

```javascript
const loadShopExpenses = async () => {
  await loadShopViewRecordedShops(selectedYear.value)   // ← 必须在早退之前
  if (!selectedShopId.value) {
    ElMessage.warning('请先选择店铺')
    return
  }
  ...
```

同时在 Task 9 Step 4 的首屏调用处加守卫，避免未选店时弹「请先选择店铺」：

```javascript
  if (selectedShopId.value) {
    await loadShopExpenses()
  }
```

> 年份选择器的 `@change="loadShopExpenses"` 会自动触发刷新，无需额外接线。

- [ ] **Step 6: 恢复软删行加二次确认（spec §7）**

页面有两个恢复入口（`handleRestoreRow` 与 `handleRestoreShopRow`），都要在恢复前确认 —— 恢复占位行会让它重新进入看板成本口径：

```javascript
const handleRestoreRow = async (row) => {
  if (!row.id) return
  try {
    await ElMessageBox.confirm(
      '恢复该费用记录？若这是占位行批次（备注以「[占位行清理」开头），恢复后会重新计入成本口径。',
      '确认恢复',
      { type: 'warning' }
    )
  } catch (error) {
    if (error === 'cancel') return
    throw error
  }
  // …原有恢复逻辑不变
}
```

`handleRestoreShopRow` 同样加一次确认。

- [ ] **Step 7: 运行测试确认通过（含既有费用前端测试与 CI 门禁）**

Run:
```powershell
cd frontend
node --test scripts/expenseManagementPage.test.mjs
node --test scripts/expenseViewModel.test.mjs
node --test scripts/expenseManagementQuickSplitUi.test.mjs
node --test scripts/expenseManagementTerminologyUi.test.mjs
node --test scripts/expenseManagementCompatibilityUi.test.mjs
node --test scripts/expenseLaborCostPayload.test.mjs
npm run build
```
Expected: 全部 PASS + 构建成功。

- [ ] **Step 8: 跑 CI 前端测试静默门禁**

Run:
```powershell
python scripts/ci_frontend_test_silence_gate.py
```
Expected: 退出码 0（任一前端断言失败都会被这个门禁拦下）。

- [ ] **Step 9: 提交**

```powershell
git add frontend/src/domains/business/views/finance/ExpenseManagement.vue frontend/scripts/expenseManagementPage.test.mjs
git commit -m "feat(finance): 修复按店铺查看视图的空状态与查询口径"
```

---

## Task 10: 回归验证与文档同步

**Files:**
- Modify: `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`

- [ ] **Step 1: 生成改动后的 junit XML**

Run:
```powershell
python -m pytest backend/tests/test_expense_management_routes.py backend/tests/test_expense_management_soft_delete_contract.py backend/tests/test_operating_cost_schema_contract.py backend/tests/test_operating_cost_platform_code_migration_contract.py backend/tests/test_expense_management_shops_scope.py backend/tests/test_expense_placeholder_cleanup_migration.py -q --tb=no --junitxml=output/junit_expense_after.xml
```
Expected: 生成 `output/junit_expense_after.xml`。

- [ ] **Step 2: 做失败集 diff（关键：无新增失败）**

Run: `python scripts/diff_pytest_junit.py output/junit_expense_base.xml output/junit_expense_after.xml`
Expected: 输出 `NEW` 段为空（无新增失败）。**若出现 NEW**，先按 `docs/guides/VERIFICATION_MATRIX.md` 的说明在基线版本复现同一组用例，确认是否为既有污染。

- [ ] **Step 3: 前端全量本地测试 + CI 静默门禁**

Run:
```powershell
cd frontend
npm run test:expense-view-model
npm run test:expense-management-page
npm run test:shop-display
npm run test:target-route-split
node --test scripts/expenseManagementQuickSplitUi.test.mjs
node --test scripts/expenseManagementTerminologyUi.test.mjs
node --test scripts/expenseManagementCompatibilityUi.test.mjs
node --test scripts/expenseLaborCostPayload.test.mjs
node --test scripts/shopDisplayUiContract.test.mjs
npm run build
```
Expected: 全部通过。

Run:
```powershell
python scripts/ci_frontend_test_silence_gate.py
```
Expected: 退出码 0。

- [ ] **Step 4: UTF-8 与架构 SSOT 校验**

Run:
```powershell
python scripts/verify_utf8_source_hygiene.py
python scripts/verify_architecture_ssot.py
```
Expected: 无报错（本次未改 ORM/schema，但前端模板与迁移文件有改动，跑一遍兜底）。

- [ ] **Step 5: 更新口径文档**

Modify `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`，在 §2.3「录入入口与汇总方式」下追加：

```markdown
### 2.3.1 店铺范围与分摊口径（2026-11-28 确认）

- **可见店铺**：以 `core.shop_accounts`（`enabled` + `business_role = 'operating_store'`）为权威 SSOT；`core.dim_shops.is_active` 是派生副本，不得作为显示依据。
- **显示规则**：当月有费用记录的店一律显示（已停用的加「已停用」标注）；空白行只给在营店；已停用店不参与快速拆分。
- **分摊范围**：快速拆分支持「全部在营店铺 / 仅 Shopee / 仅 TikTok / 按租户」，分摊只作用于范围内的在营店铺，范围外的既有金额不被清零。
- **分组维度**：展示按平台（一级）→ 租户 `main_account_id`（二级）分组；分组只影响展示与操作范围，**不改行的归属口径**（唯一约束仍为 `platform_code + shop_id + year_month`）。
- **历史占位行**：2026-06~12 的「纯占位行」（除人力费外全 0、无备注无附件）已由迁移 `current_schema_20261246_cleanup_expense_placeholder_rows` 软删；这使 2026-06/09/11/12 的看板成本变为缺失（`--`），属刻意结果（人力成本应由工资单链路提供）。
```

- [ ] **Step 6: 提交**

```powershell
git add docs/COST_DATA_SOURCES_AND_DEFINITIONS.md
git commit -m "docs(finance): 记录费用管理店铺范围与分摊口径"
```

- [ ] **Step 7: 人工验收清单（浏览器）**

按 `docs/guides/COLLECTION_AUTHORING_RULES.md` 的证据方式，在本地运行时逐项确认：

| # | 场景 | 期望 |
|---|---|---|
| 1 | 费用管理 → 按月份 → 2026-11 | 18 行（Shopee 12 + TikTok 6），全部为空白行，无已停用店铺 |
| 2 | 切到「仅 TikTok」分段 | 只剩 6 行，租户副标题正确 |
| 3 | 点「快速拆分」→ 选「仅 TikTok」→ 填金额 → 应用 | 只有 6 家 TikTok 行被赋值，Shopee 行金额不变 |
| 4 | 切月份到 2026-01 | 显示 CHENEWEI666_SG 历史行并带「已停用」标签 |
| 5 | 切到「按店铺查看」 | 打开即默认选中 `HX_HOME_SG`，加载出 6 行 |
| 6 | 年度累计 | 显示 244,836.52（迁移执行后；迁移未执行时为 363,783.89） |
| 7 | 「已删除费用记录」区 | 出现带 `[占位行清理 2026-11-28]` 标记的软删行，可识别 |

> ⚠️ 第 6、7 项依赖迁移在本地库执行。若本地未执行迁移，跳过并注明「迁移待发版流程执行」。

---

## 验收标准（全部任务完成后）

- [ ] `python scripts/diff_pytest_junit.py output/junit_expense_base.xml output/junit_expense_after.xml` 无 `NEW` 失败
- [ ] `cd frontend` 后 `npm run test:expense-view-model`、`npm run test:expense-management-page`、`npm run test:shop-display`、`npm run build` 全绿，且 `node --test scripts/expenseManagement*.test.mjs`、`expenseLaborCostPayload.test.mjs`、`shopDisplayUiContract.test.mjs` 全绿
- [ ] `python scripts/ci_frontend_test_silence_gate.py` 退出码 0
- [ ] `python scripts/verify_utf8_source_hygiene.py`、`python scripts/verify_architecture_ssot.py` 无报错
- [ ] 人工验收清单 7 项全部符合（迁移相关项按实际执行状态标注）
- [ ] 迁移在带备份的环境执行后，`output/junit_expense_after.xml` 仍无新增失败
- [ ] 成果落在分支 `feature/expense-shop-scope`（worktree 内），**主工作区的 BCostAnalysis 在途改动未被触碰**；是否合并回 `main` 由用户决定（仓库为 tag 驱动发版，不自动合并）

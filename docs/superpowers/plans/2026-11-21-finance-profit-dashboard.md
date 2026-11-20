# 月度利润看板 · 完整优化实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「月度利润结算中心」改造成只读月度利润看板，消灭三个金额缺陷，整体下线跟投模块。

**Architecture:** 后端**不重命名、不新建 service**（受 `docs/guides/PRE_LAUNCH_RULES.md:19-20` 约束），改造 `backend/services/monthly_profit_settlement_service.py` 内部实现：删除自算人员成本、目标比例、差异算法、快照机制与审批流；保留唯一真源读取（人力成本分摊表 + 店铺利润基数）并补版本过滤；新增只读聚合方法与人工调整项写入口。前端拆成独立只读看板组件与独立 store，删除跟投页面/路由/菜单/API/store 切片。指标登记进 `sea-metrics-language` 词典两份副本并加指纹校验脚本。

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic v2 + PostgreSQL / Vue 3 + Element Plus + Pinia + Vite / pytest + pytest-asyncio / node --test (mjs)

**设计文档：** `docs/superpowers/specs/2026-11-21-finance-profit-dashboard-design.md`（已过两轮独立审查）

**阶段编号对照**（对齐设计 §9，遵守 `docs/guides/PRE_LAUNCH_RULES.md:35`「跨不超过 3 个主要模块」）：

| Task | 阶段 | 主要模块面 |
|---|---|---|
| 1 | 2c 前置 | 词典 + 脚本 |
| 2 | 1a | 数据库 |
| 3 | 1b | 后端 |
| 4 | 1c | 前端 + 测试 + 文档 |
| 5–9 | 2a | 后端 |
| 10–11 | 2b | 前端 |
| 12 | 2c | 词典 + 文档 |
| 13 | 3 | 数据库 |
| 14 | 收尾 | 全量验证 |

---

## §0 文件地图

### 新建

| 路径 | 职责 |
|---|---|
| `current_migrations/versions/20261241_drop_follow_investment.py` | 下线跟投 3 表 + `monthly_profit_follow_details` |
| `current_migrations/versions/20261242_drop_monthly_profit_snapshots.py` | 阶段 3：drop 5 张停写快照表 + `settlements` 废弃列 |
| `backend/tests/test_finance_dashboard_service.py` | 看板聚合口径单测（版本过滤、公司池不双扣、只取提成后、每店分布） |
| `backend/tests/test_finance_dashboard_routes.py` | 看板接口契约测试（只读 GET / 调整项 POST·DELETE / 旧端点消失） |
| `backend/tests/test_follow_investment_removal_contract.py` | 下线守卫：路由、权限、角色、文件均已消失 |
| `frontend/src/stores/financeDashboard.js` | 看板专用 store（只管看板） |
| `frontend/src/domains/business/views/finance-dashboard/FinanceDashboardView.vue` | 页面壳：月份选择、as_of、导出、三区块编排 |
| `frontend/src/domains/business/views/finance-dashboard/ProfitOverviewCards.vue` | A 区：本月结果卡片 |
| `frontend/src/domains/business/views/finance-dashboard/ShopAllocationTable.vue` | B 区：各店分配分布 |
| `frontend/src/domains/business/views/finance-dashboard/AdjustmentPanel.vue` | C 区：人工调整列表 + 录入弹窗 |
| `frontend/scripts/financeDashboardView.test.mjs` | 前端看板契约测试（node --test） |
| `scripts/verify_team_skills_sync.py` | 词典两份副本 SHA256 一致性校验 |
| `docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md` | **post-launch V2 治理计划**（设计 §11 的 7 条，必须产出） |

### 修改

| 路径 | 改什么 | Task |
|---|---|---|
| `backend/services/monthly_profit_settlement_service.py` | 逐函数改造（核心，见设计 §6.3） | 3,5,6,7,8,9 |
| `backend/domains/business/routers/monthly_profit_settlement.py` | 端点增删 | 9 |
| `backend/routers/monthly_profit_settlement.py` | legacy wrapper 同步 | 9 |
| `backend/schemas/monthly_profit_settlement.py` | 新增看板 payload / 调整项契约，删 rebuild/targets 契约 | 9 |
| `backend/domains/business/routes.py` | 摘除跟投路由注册（`:24, 34`） | 3 |
| `backend/main.py` | 清理跟投注释标记（`:1349`） | 3 |
| `backend/services/approval_center_service.py` | 删跟投模板 4 处 + 月结审批 4 处 | 3 |
| `backend/services/permission_service.py` | 删 `my-follow-investment-income` 权限点（`:270-272`） | 3 |
| `backend/services/system_role_service.py` | 下线 `investor` 角色（`:98-106`） | 3 |
| `modules/core/db/schema_parts/business.py` | 删 4 张跟投/跟投明细表 ORM + 停写表标注 | 2,13 |
| `modules/core/db/schema.py` | 导出清单同步 | 3 |
| `scripts/verify_production_migration_contracts.py` | `:17-21` `DEFAULT_TESTS` 删掉被删测试文件 | 2 |
| `current_migrations/versions/20260805_current_schema_baseline.py` | 删 `:742-749` 等 34 行跟投建表语句 | 2 |
| `current_migrations/versions/20261240_hr_employee_lifecycle.py` | 清理 `:71` 跟投注释引用 | 2 |
| `frontend/src/api/finance.js` | 删 10 个跟投 API，加看板 API | 4,10 |
| `frontend/src/router/index.js` | 改标题（`:129`）、删跟投路由（`:610-620`）、修乱码标题（`:307`） | 4,11 |
| `frontend/src/config/menuGroups.js` | 改显示名（`:82, :236`）、删跟投菜单（`:110, :237`） | 4,11 |
| `frontend/src/config/rolePermissions.js` | 删 `investor` 角色（`:81`）与 `'投资人'` 映射（`:113`） | 4 |
| `frontend/src/domains/business/views/FinancialManagement.vue` | 拆成薄壳，转发到新看板视图 | 11 |
| `backend/tests/test_monthly_profit_settlement_routes.py` | 删 8 个打在被删端点上的用例 | 9 |
| `backend/tests/test_monthly_profit_settlement_service.py` | 删打在被删方法上的用例（含 2 个跟投 payload 用例） | 3,8 |
| `frontend/scripts/domainBridgeInventory.test.mjs` | 删 `:73` 路由规格元素 + 同步 `:13-19` 计数 | 4 |
| `frontend/scripts/roleMenuSnapshot.test.mjs` | 删跟投菜单快照；`:108` 那组**整行删除** | 4 |
| `docs/team-skills/sea-metrics-language/references/metrics-dictionary.md` | 登记 6 个指标 | 12 |
| `docs/team-skills/sea-metrics-language/references/metric-status.md` | 登记状态 | 12 |
| `docs/team-skills/sea-metrics-language/SKILL.md` | 写明正本规则 | 12 |
| `team-skills-bundle/sea-metrics-language/**` | 同步副本（4 个文件） | 12 |
| `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md` | 改写 `:250-270`、`:95-101`、`:333-339`（⚠️ **不动 `:19-37` 的上游利润基数公式**） | 12 |
| `docs/guides/APPROVAL_CENTER_RUNBOOK.md` | 删跟投/月结审批模板登记；删 `:93` 引用被删测试的命令 | 4,12 |
| `backend/tests/test_domain_route_registration.py` | 删跟投路由断言（`:52`） | 4 |
| `backend/tests/test_finance_schema_contract.py` | 删跟投断言；`:120-133` 删 5 个快照模型存在断言 | 4,13 |
| `backend/tests/test_financial_settlement_page_contract.py` | 删跟投断言 | 4 |
| `backend/tests/test_monthly_profit_settlement_frontend_contract.py` | 删跟投与「预算(%)」断言 | 4 |
| `backend/tests/test_investor_role_frontend_contract.py` | **整份删除** | 4 |
| `backend/tests/test_legacy_auth_permission_compat.py` | 删投资人角色断言（`:21`） | 4 |
| `backend/tests/test_system_role_service.py` | 删整个投资人角色测试函数（`:23-29`） | 4 |
| `docs/guides/FOLLOW_INVESTMENT_AND_SETTLEMENT_ACCEPTANCE_CHECKLIST_2026-05-30.md` | 整份标注作废 | 4 |
| `docs/guides/ENGINEERING_STATUS.md`、`CHANGELOG.md` | 下线与转看板登记 | 4,12 |

### 删除

`backend/services/follow_investment_service.py`、`backend/domains/business/routers/follow_investment.py`、`backend/routers/follow_investment.py`、`backend/schemas/follow_investment.py`、`frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue`、`frontend/src/domains/business/views/finance-settlement/`（2 个文件）、`frontend/src/stores/financeSettlement.js`、7 个专属跟投测试文件。

---

## §1 前置项（不写代码，先做）

- [ ] **P1** 取得业务签字：**推翻运行手册既有口径**（`docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md:252`「月结人员成本以工资单为最终结算口径」与 `:266-269`），改为「以人力成本分摊表的绩效工资+提成为准」。签字记录写进运行手册。
- [ ] **P2** 确认跟投表实际行数：`SELECT count(*) FROM finance.follow_investments;` 以及 `finance.follow_investment_settlements`、`finance.follow_investment_details`。业务已口头确认无真实投钱，仍须以库为准。
- [ ] **P3** 确认 `investor` 角色去留（本方案建议一并下线，需业务确认；定义见 `backend/services/system_role_service.py:98-106` 与 `frontend/src/config/rolePermissions.js:81`）。
- [ ] **P4** 跑只读体检脚本，产出「口径切换前后同月对比」：
  - 各店 `shop_profit_basis` 的 `basis_version` 分布（是否同月并存 legacy 行）
  - 各店 `employee_labor_cost_allocations` 的 `calculation_version` 分布（同月是否并存两版）
  - 同一月 `scope='company'` 的 `pre_commission_amount` 合计（即当前被扣第二次的公司池金额）
  - 结果归档到 `docs/reports/`，供上线说明引用
- [ ] **P5** 记录基线失败集（**须在改动前的工作区状态生成**，不是事后补）：

  ```powershell
  # 覆盖 pyproject.toml 的默认 testpaths（tests + backend/tests）
  python -m pytest -q --tb=no --junitxml="$env:TEMP\base.xml"
  ```

  ⚠️ 仓库有既存失败基线，`docs/guides/VERIFICATION_MATRIX.md:22-28` 要求用**失败集差异**而非计数证明"无新增失败"。

---

## Task 1 [阶段 2c 前置]: 指标词典副本对齐 + 指纹校验脚本

**Files:**
- Create: `scripts/verify_team_skills_sync.py`
- Modify: `team-skills-bundle/sea-metrics-language/references/{metrics-dictionary.md,metric-status.md,metric-usage-matrix.md,platform-mapping.md}`

- [ ] **Step 1: 写出差异清单**

  ```powershell
  $a=(Resolve-Path 'docs\team-skills\sea-metrics-language').Path
  $b=(Resolve-Path 'team-skills-bundle\sea-metrics-language').Path
  Get-ChildItem $a -Recurse -File | ForEach-Object {
    $rel=$_.FullName.Substring($a.Length+1)
    $other=Join-Path $b $rel
    if (Test-Path $other) {
      $h1=(Get-FileHash $_.FullName -Algorithm SHA256).Hash
      $h2=(Get-FileHash $other -Algorithm SHA256).Hash
      if ($h1 -ne $h2) { Write-Output "DIFF $rel" } else { Write-Output "SAME $rel" }
    } else { Write-Output "MISSING-IN-BUNDLE $rel" }
  }
  ```
  Expected: 4 个 `DIFF`（`references/metric-status.md`、`references/metric-usage-matrix.md`、`references/metrics-dictionary.md`、`references/platform-mapping.md`），3 个 `SAME`。

- [ ] **Step 2: 写指纹校验脚本**

  `scripts/verify_team_skills_sync.py`：
  ```python
  """校验 sea-metrics-language skill 两份副本字节一致。

  律 3 要求派生层口径机器可验证；"哪一份是正本"靠人读文档无法验证，
  因此把"两份必须一致"固化成脚本。
  """
  from __future__ import annotations

  import hashlib
  import sys
  from pathlib import Path

  REPO_ROOT = Path(__file__).resolve().parents[1]
  PAIRS = [
      (
          REPO_ROOT / "docs" / "team-skills" / "sea-metrics-language",
          REPO_ROOT / "team-skills-bundle" / "sea-metrics-language",
      ),
  ]


  def _sha256(path: Path) -> str:
      return hashlib.sha256(path.read_bytes()).hexdigest()


  def main() -> int:
      problems: list[str] = []
      for left, right in PAIRS:
          left_files = {p.relative_to(left).as_posix() for p in left.rglob("*") if p.is_file()}
          right_files = {p.relative_to(right).as_posix() for p in right.rglob("*") if p.is_file()}
          for missing in sorted(left_files - right_files):
              problems.append(f"missing in {right}: {missing}")
          for missing in sorted(right_files - left_files):
              problems.append(f"missing in {left}: {missing}")
          for rel in sorted(left_files & right_files):
              lh = _sha256(left / rel)
              rh = _sha256(right / rel)
              if lh != rh:
                  problems.append(f"content differs: {rel} ({lh[:8]} != {rh[:8]})")
      for problem in problems:
          print(f"[FAIL] {problem}")
      if problems:
          return 1
      print("[OK] sea-metrics-language 两份副本一致")
      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

- [ ] **Step 3: 运行脚本，确认它能抓到分叉**

  Run: `python scripts/verify_team_skills_sync.py`
  Expected: FAIL，列出 4 个 `content differs`。

- [ ] **Step 4: 以 `docs/team-skills/` 为真相源同步回 bundle**

  ```powershell
  Copy-Item 'docs\team-skills\sea-metrics-language\*' 'team-skills-bundle\sea-metrics-language' -Recurse -Force
  ```
  ⚠️ 先确认 `docs/team-skills/` 那份确实更全（含 2026-11「投放 ROI 边界」整节）——**反向同步会删掉已登记的 ROI 指标**。

- [ ] **Step 5: 重跑脚本确认通过**

  Run: `python scripts/verify_team_skills_sync.py`
  Expected: `[OK] sea-metrics-language 两份副本一致`

- [ ] **Step 6: Commit**

  ```bash
  git add scripts/verify_team_skills_sync.py docs/team-skills/sea-metrics-language team-skills-bundle/sea-metrics-language
  git commit -m "chore(skills): 对齐 sea-metrics-language 两份副本并加指纹校验"
  ```

---

## Task 2 [阶段 1a]: 跟投下线 · 数据库迁移与基线同步

**Files:**
- Create: `current_migrations/versions/20261241_drop_follow_investment.py`
- Modify: `scripts/verify_production_migration_contracts.py:17-21`、`current_migrations/versions/20260805_current_schema_baseline.py`、`current_migrations/versions/20261240_hr_employee_lifecycle.py`

- [ ] **Step 1: 确认外键依赖**

  `finance.monthly_profit_follow_details.source_settlement_id` → `finance.follow_investment_settlements.id`，**无 ondelete**（`modules/core/db/schema_parts/business.py:2153-2155`）。**必须先 drop 这张表。**

- [ ] **Step 2: 写迁移**

  新建 `current_migrations/versions/20261241_drop_follow_investment.py`，按该目录既有约定：
  - `revision = "current_schema_20261241_drop_follow_investment"`
  - `down_revision = "current_schema_20261240_hr_employee_lifecycle"`
  - `upgrade()` 按顺序执行：
    ```sql
    DROP TABLE IF EXISTS finance.monthly_profit_follow_details;
    DROP TABLE IF EXISTS finance.follow_investment_details;
    DROP TABLE IF EXISTS finance.follow_investment_settlements;
    DROP TABLE IF EXISTS finance.follow_investments;
    ```
  - `downgrade()` 重建四张空表（保持可回滚）

- [ ] **Step 3: 同步 current_migrations 基线**

  `current_migrations/versions/20260805_current_schema_baseline.py` 里跟投相关的语句**共 34 行，分布在 9 个位置**：
  `:742-750`、`:800-802`、`:1197-1199`、`:1215`、`:1499-1501`、`:1523`、`:2747-2752`、`:2792`、`:3148-3151`、`:3170-3172`

  ⚠️ **不能只删 `CREATE TABLE`**（那只有 9 行）。剩下的是 `ALTER SEQUENCE ... SET DEFAULT`（`:1197-1199`）、`ADD CONSTRAINT pkey`（`:1499-1501`）、`CREATE INDEX`（`:2747-2752`）、`ADD CONSTRAINT fkey`（`:3148-3172`）等，只删建表语句会让基线迁移在这些语句处**直接失败**。
  ⚠️ `:800-802` 是 `finance.monthly_profit_follow_details` 的建表语句（Task 2 的迁移要 drop 它）——**基线里也必须删**，否则基线迁移后这张表又冒出来，与下线迁移冲突。

  `current_migrations/versions/20261240_hr_employee_lifecycle.py`：清理 `:71` 提到 `finance.follow_investments` 的注释。

- [ ] **Step 4: 清理迁移契约脚本的默认测试清单**

  `scripts/verify_production_migration_contracts.py:17-21` 的 `DEFAULT_TESTS` 含 `tests/test_follow_investment_finance_schema_contract.py`；`:124` 直接 `pytest -q *DEFAULT_TESTS`。
  **删除该条目**，否则 Task 4 删掉该测试文件后脚本会因 pytest 找不到文件而 RuntimeError。

- [ ] **Step 5: 验证**

  Run: `python scripts/verify_architecture_ssot.py`
  Expected: PASS。⚠️ 该脚本检查的是 Base 定义位置、重复 ORM 模型、关键架构文件存在、未归档 legacy 文件——**它不做 ORM ↔ `modules/core/db/schema.py` 导出一致性校验**，ORM 删除的正确性由 Task 3 的 import 闸门保证。

  Run: `python scripts/verify_production_migration_contracts.py`
  ⚠️ **需要可连的 PostgreSQL**（`scripts/verify_production_migration_contracts.py:26-30, 111-122`；另有测试硬连 `127.0.0.1:15432`）。无库环境跳过并**明确记为未验证项**。

- [ ] **Step 6: Commit（与 Task 3 合并为一个提交）**

  ⚠️ **不要单独提交 Task 2**：Task 2 提交后、Task 3 提交前，路由 `/api/finance/follow-investments` 仍注册但表已 drop ⇒ 该窗口内 GET 会 500。
  本 Task 暂不 commit，等 Task 3 全部完成后一起提交（见 Task 3 Step 12）。若必须分开提交，则本 Task 只提交迁移与基线文件，**ORM 删除留到 Task 3**。

---

## Task 3 [阶段 1b]: 跟投下线 · 后端

> ⚠️ **执行顺序很重要**：先清 service 里的跟投引用，**再**删 ORM 类。顺序反了会让 `modules.core.db` 导入失败、后端整体 ImportError。

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py`、`backend/domains/business/routes.py`、`backend/main.py`、`backend/services/approval_center_service.py`、`backend/services/permission_service.py`、`backend/services/system_role_service.py`、`modules/core/db/schema_parts/business.py`、`modules/core/db/schema.py`
- Delete: `backend/services/follow_investment_service.py`、`backend/domains/business/routers/follow_investment.py`、`backend/routers/follow_investment.py`、`backend/schemas/follow_investment.py`
- Test: `backend/tests/test_follow_investment_removal_contract.py`（新建）、`backend/tests/test_monthly_profit_settlement_service.py`（删 2 个跟投 payload 用例）

- [ ] **Step 1: 清理 service 里的跟投引用（先做这一步）**

  `backend/services/monthly_profit_settlement_service.py`：
  - 删 import：`FollowInvestmentDetail`（`:13`）、`FollowInvestmentSettlement`（`:14`）、`MonthlyProfitFollowDetail`（`:18`）
  - 删方法：`_load_follow_payload`（`:224-263`）、`_load_follow_details`（`:302-324`）
  - 改 `rebuild_month`（`:755-765` 附近）：删写入 `MonthlyProfitFollowDetail` 的块
  - 改 `load_snapshot_settlement_view`（`:395-451`）：删跟投明细读取

- [ ] **Step 2: 删 ORM 类（service 不再引用之后）**

  `modules/core/db/schema_parts/business.py` 删四个类：
  - `FollowInvestment`（`:1925`）
  - `FollowInvestmentSettlement`（`:1968`）
  - `FollowInvestmentDetail`（`:2008`）
  - `MonthlyProfitFollowDetail`（`:2139`）

  ⚠️ `modules/core/db/schema.py` 是**显式 import**（不是 `import *`），必须同步删两处：
  - `:178-180` 的 `from .schema_parts.business import (...)` 块中这 4 个类名
  - `:387-392` 的 `_BUSINESS_EXPORTS` 列表中这 4 个类名

  `modules/core/db/__init__.py:14-16` 是 `from .schema import *` + `__all__ = _SCHEMA_ALL`，**只要 schema.py 同步了就自动生效**，无需单独改。
  ⚠️ 只删 `business.py` 不改 `schema.py` ⇒ `modules.core.db` 导入直接 ImportError，后端整体起不来。

- [ ] **Step 3: 验证后端仍可导入**

  Run: `python -c "import backend.services.monthly_profit_settlement_service; import modules.core.db; print('ok')"`
  Expected: 打印 `ok`。**这一步是 Task 2 删 ORM 后后端不炸的关键闸门。**

- [ ] **Step 4: 摘除路由注册与注释标记**

  `backend/domains/business/routes.py`：删 `:24` 的 `follow_investment` import 与 `:34` 的 `app.include_router(follow_investment.router, ...)`。
  `backend/main.py:1349`：删注释行 `# app.include_router(follow_investment.router, tags=["跟投收益"])`。

- [ ] **Step 5: 删审批中心跟投 4 处**

  `backend/services/approval_center_service.py`：删 `:15` 常量 `FOLLOW_INVESTMENT_SETTLEMENT_TEMPLATE_CODE`、`:65-73` 模板注册函数、`:203-239` `submit_follow_investment_settlement_approval`、`:242-271` `sync_follow_investment_settlement_approval_decision`。
  ⚠️ 月结审批的 4 处（`:14` 常量、`:54-62` 模板注册、`:139-169` submit、`:171-200` sync）**留给 Task 9**（审批制随看板化下线），本任务不动。

- [ ] **Step 6: 删权限点与投资人角色**

  `backend/services/permission_service.py:270-272` 删 `my-follow-investment-income` 权限点。
  `backend/services/system_role_service.py:98-106` 删 `investor` 角色（**须已完成前置 P3**）。同时检查该文件 `:31, 54, 79` 等按角色清单派发权限处是否需同步。

- [ ] **Step 7: 删 4 个跟投源文件**

  删除 `backend/services/follow_investment_service.py`、`backend/domains/business/routers/follow_investment.py`、`backend/routers/follow_investment.py`、`backend/schemas/follow_investment.py`。

- [ ] **Step 8: 删 service 里打在被删方法上的 2 个用例**

  `backend/tests/test_monthly_profit_settlement_service.py`：删 `test_load_follow_payload_expands_investor_level_details`（`:317`）与 `test_load_follow_payload_preserves_zero_approved_income`（`:362`）。

- [ ] **Step 9: 写下线守卫测试**

  `backend/tests/test_follow_investment_removal_contract.py`：
  ```python
  from pathlib import Path

  REPO_ROOT = Path(__file__).resolve().parents[2]


  def test_follow_investment_source_files_are_gone():
      for rel in (
          "backend/services/follow_investment_service.py",
          "backend/domains/business/routers/follow_investment.py",
          "backend/routers/follow_investment.py",
          "backend/schemas/follow_investment.py",
      ):
          assert not (REPO_ROOT / rel).exists(), f"{rel} 仍存在，跟投未下线"


  def test_follow_investment_route_not_registered():
      source = (REPO_ROOT / "backend" / "domains" / "business" / "routes.py").read_text(
          encoding="utf-8-sig"
      )
      assert "follow_investment" not in source


  def test_investor_role_and_permission_are_removed():
      role_source = (REPO_ROOT / "backend" / "services" / "system_role_service.py").read_text(
          encoding="utf-8-sig"
      )
      permission_source = (REPO_ROOT / "backend" / "services" / "permission_service.py").read_text(
          encoding="utf-8-sig"
      )
      assert '"investor"' not in role_source
      assert "my-follow-investment-income" not in permission_source


  def test_settlement_service_no_longer_imports_follow_investment():
      source = (REPO_ROOT / "backend" / "services" / "monthly_profit_settlement_service.py").read_text(
          encoding="utf-8-sig"
      )
      assert "FollowInvestment" not in source
      assert "MonthlyProfitFollowDetail" not in source
  ```

- [ ] **Step 10: 运行**

  Run: `pytest backend/tests/test_follow_investment_removal_contract.py -q`
  Expected: PASS（4 passed）

  Run: `pytest backend/tests/test_monthly_profit_settlement_service.py -q`
  Expected: 剩余用例 PASS。

- [ ] **Step 11: 确认无残留引用**

  Run: `rg -n "follow_investment|FollowInvestment" backend -g "*.py"`
  Expected: 仅剩 `backend/tests/test_follow_investment_*.py`（本任务尚未删的 5 个专属测试 + 新建的守卫测试自身）。Task 4 会删掉其中 5 个。
  ⚠️ Windows PowerShell 无原生 `grep`，用 `rg`（已确认存在于 PATH）或 `Get-ChildItem -Recurse -Filter *.py | Select-String "follow_investment"`。

- [ ] **Step 12: Commit（与 Task 2 合并为一个提交）**

  ⚠️ Task 2 的迁移与本 Task 的代码下线必须**同时生效**，否则会出现「路由还在、表已 drop」的 500 窗口。

  ```bash
  git add backend/ modules/core/db/ current_migrations/ scripts/verify_production_migration_contracts.py
  git commit -m "feat(backend): 下线跟投收益模块与投资人角色"
  ```

---

## Task 4 [阶段 1c]: 跟投下线 · 前端、测试与文档

**Files:**
- Delete: `frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue`、`frontend/scripts/myFollowInvestmentIncomeView.test.mjs`、5 个后端专属跟投测试、`tests/test_follow_investment_finance_schema_contract.py`
- Modify: `frontend/src/router/index.js`、`frontend/src/config/menuGroups.js`、`frontend/src/config/rolePermissions.js`、`frontend/src/api/finance.js`、`frontend/src/stores/financeSettlement.js`、8 个含跟投引用的测试、4 份文档

- [ ] **Step 1: 删前端页面与菜单/路由**

  删 `MyFollowInvestmentIncome.vue`；
  `frontend/src/router/index.js` 删 `:610-620` 路由块；
  `frontend/src/config/menuGroups.js` 删 `:110` 与 `:237` 两行。

- [ ] **Step 2: 删前端投资人角色**

  `frontend/src/config/rolePermissions.js`：删 `:81` 的 `investor: {` 整块与 `:113` 的 `'投资人': 'investor'` 映射。
  ⚠️ `frontend/scripts/roleMenuSnapshot.test.mjs:13` 的 `ROLE_CONFIG` 从此文件导入，**两边必须同改**。

- [ ] **Step 3: 删 API 与 store 切片**

  `frontend/src/api/finance.js` 删 `:200-237` 的 10 个跟投 API 方法。
  `frontend/src/stores/financeSettlement.js` 删 4 个跟投切片（`:21-28, 29-33, 34-38, 39-43`）与 9 个跟投 action（`:138, 153, 167, 176, 182, 188, 196, 204, 218`）。

- [ ] **Step 4: 删 7 个专属测试文件**

  `backend/tests/test_follow_investment_{service,routes,entry_contract,menu_contract,migration_contract}.py`、`tests/test_follow_investment_finance_schema_contract.py`、`frontend/scripts/myFollowInvestmentIncomeView.test.mjs`。
  ⚠️ `tests/test_follow_investment_finance_schema_contract.py` 已从 Task 2 Step 4 的 `DEFAULT_TESTS` 移除，此处才真正删文件。

- [ ] **Step 5: 改 8 个含跟投引用的测试**

  - `backend/tests/test_domain_route_registration.py:52` 删跟投路由断言
  - `backend/tests/test_investor_role_frontend_contract.py` —— **整份删除**。它的实现是 `text.split("investor:", 1)`，而 `rolePermissions.js` 的 `investor:` 与 `'投资人': 'investor'` 都要删 ⇒ 该串全库消失后 `split` 只剩 1 段、`parts[1]` 为 undefined ⇒ TypeError。且它断言的 `roles: [..., 'investor']` 随跟投路由删除而消失。
  - `backend/tests/test_system_role_service.py` —— **删除整个测试函数**（`:23-29`），不是只删 `:28` 一行。`DEFAULT_SYSTEM_ROLES` 是普通 dict（`backend/services/system_role_service.py:11`），删掉 `investor` 键后访问 `DEFAULT_SYSTEM_ROLES["investor"]` 会 KeyError。
  - `backend/tests/test_legacy_auth_permission_compat.py:21` —— 删该断言即可。`utils/auth.py:140-144` 走 `DEFAULT_SYSTEM_ROLES.get(role, {}).get("permissions", [])`，删角色后返回 False，删断言即通过。
  - `frontend/scripts/roleMenuSnapshot.test.mjs`：
    - `:73`、`:85`、`:98` 三组删 `'/my-follow-investment-income'` 元素（组内仍有其他菜单项）
    - ⚠️ `:106-110` 的 **investor 角色整块断言必须整块删除**——不能只删 `:108` 那一行。`ROLE_CONFIG['investor']` 变 undefined 后 `canAccess`（`:53`）的 `ROLE_CONFIG[role]?.permissions || []` 退化为 `[]`，`/business-overview`（`permission: 'business-overview'`）不再出现在快照里 ⇒ 期望值里若还留着 `{ title: '工作台', items: ['/business-overview'] }` 这组，`deepEqual` 必红（已实跑复现）。**正确处置是删除 `:106-110` 整个 investor 快照断言块。**
  - `frontend/scripts/domainBridgeInventory.test.mjs`：
    - `:73` 的 `EXPECTED_ROUTE_SPECIFIERS` 数组删除 `'@/domains/business/views/hr/MyFollowInvestmentIncome.vue'`（否则 `:212` 的 `deepEqual` 必红）
    - `:13-19` 的硬编码计数 `EXPECTED_DIRECT_DOMAIN_ROUTE_COUNT = 82` / `business: 29` 同步为 81 / 28
  - `backend/tests/test_finance_schema_contract.py`、`test_financial_settlement_page_contract.py`、`test_monthly_profit_settlement_frontend_contract.py` 删跟投断言
  - ⚠️ `backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py` **不需要改**：它唯一的 follow 字样是 `CURRENT_REVISION = "20260407_follow_investment_profit_basis"`（`:11`），指向**保留不删**的历史迁移

- [ ] **Step 6: 更新文档**

  `docs/guides/APPROVAL_CENTER_RUNBOOK.md`：删跟投模板登记；**并删 `:93` 引用了将被删的 `backend/tests/test_follow_investment_routes.py` 的命令**。
  `docs/guides/ENGINEERING_STATUS.md`：标注模块下线。
  `CHANGELOG.md`：追加下线记录。
  `docs/guides/FOLLOW_INVESTMENT_AND_SETTLEMENT_ACCEPTANCE_CHECKLIST_2026-05-30.md`：整份标注作废。

- [ ] **Step 7: 验证**

  Run: `python scripts/verify_utf8_source_hygiene.py`
  Run: `python scripts/verify_rules_completeness.py`
  Run: `cd frontend; npx vite build; cd ..`
  Expected: 全部 PASS / build 成功。
  ⚠️ PowerShell 的 `cd` 在同一会话内持续生效，**每条命令后必须 `cd ..` 回到仓库根**。

- [ ] **Step 8: 失败集差异**

  ```powershell
  python -m pytest -q --tb=no --junitxml="$env:TEMP\after_followdown.xml"
  python scripts/diff_pytest_junit.py "$env:TEMP\base.xml" "$env:TEMP\after_followdown.xml"
  ```
  Expected: 无 `NEW` 条目。若报出单条新失败，按 `docs/guides/VERIFICATION_MATRIX.md:29-33` 在基线修订上用相同 test set 复现后再判定。
  ⚠️ 必须覆盖 `pyproject.toml` 的默认 testpaths（`tests` + `backend/tests`），只跑 `backend/tests/` 会漏掉根 `tests/` 的 74 个文件。

- [ ] **Step 9: Commit**

  ```bash
  git add -A && git commit -m "feat(frontend): 移除跟投页面、菜单、API、角色与相关测试文档"
  ```

---

## Task 5 [阶段 2a]: 分摊表版本过滤

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py:185-222`
- Test: `backend/tests/test_finance_dashboard_service.py`（新建）

- [ ] **Step 1: 写失败测试**

  `backend/tests/test_finance_dashboard_service.py`（沿用 `backend/tests/test_monthly_profit_settlement_service.py:16-36` 的 mock 模式）：

  ```python
  from importlib import import_module
  from types import SimpleNamespace
  from unittest.mock import AsyncMock

  import pytest


  def _load_service_module():
      try:
          return import_module("backend.services.monthly_profit_settlement_service")
      except ModuleNotFoundError as exc:
          pytest.fail(f"monthly profit settlement service module missing: {exc}")


  def _make_db():
      return SimpleNamespace(
          execute=AsyncMock(),
          flush=AsyncMock(),
          commit=AsyncMock(),
          add=lambda record: None,
      )


  class _ScalarResult:
      def __init__(self, rows):
          self._rows = rows

      def scalars(self):
          return self

      def all(self):
          return self._rows

      def scalar_one_or_none(self):
          return self._rows[0] if self._rows else None


  def _capture_statements(db):
      statements = []

      async def _execute(statement, *args, **kwargs):
          statements.append(statement)
          return _ScalarResult([])

      db.execute = _execute
      return statements


  @pytest.mark.asyncio
  async def test_personnel_payload_filters_by_calculation_version():
      """人员成本必须按当前 calculation_version 过滤，否则同月两版行并存时算两遍。"""
      module = _load_service_module()
      service = module.MonthlyProfitSettlementService(_make_db())
      statements = _capture_statements(service.db)

      await service._load_personnel_payload("2026-04")

      assert statements, "应当查询人力成本分摊表"
      where_sql = str(statements[0].whereclause).lower()
      assert "calculation_version" in where_sql, (
          "WHERE 子句必须过滤 calculation_version；"
          f"当前 WHERE = {where_sql}"
      )
  ```

  ⚠️ **不能只断言整条 SQL 含 `calculation_version`**——`select(EmployeeLaborCostAllocation)` 会把该列放进 SELECT 列表，旧实现里就已经出现，测试会假绿。必须断 **whereclause**。

- [ ] **Step 2: 运行确认失败**

  Run: `pytest backend/tests/test_finance_dashboard_service.py::test_personnel_payload_filters_by_calculation_version -q`
  Expected: FAIL — 当前 WHERE 子句只有 `period_month` 与 `source_payroll_status`。

- [ ] **Step 3: 实现版本过滤**

  `backend/services/monthly_profit_settlement_service.py` 的 `_load_personnel_payload`：
  ```python
  from backend.services.labor_cost_projection_service import (
      LABOR_COST_CALCULATION_VERSION,
  )
  ...
  allocation_rows = (
      (
          await self.db.execute(
              select(EmployeeLaborCostAllocation).where(
                  EmployeeLaborCostAllocation.period_month == period_month,
                  EmployeeLaborCostAllocation.source_payroll_status.in_(
                      PAYROLL_LOCKED_STATUSES
                  ),
                  # 只认当前口径：历史版本行与同月当前版本行并存时会把人力成本算两遍
                  EmployeeLaborCostAllocation.calculation_version
                  == LABOR_COST_CALCULATION_VERSION,
              )
          )
      )
      .scalars()
      .all()
  )
  ```
  ⚠️ 该文件 `:28-30` 已有同名 import，实施时**不要重复添加**。

- [ ] **Step 4: 运行确认通过**

  Run: `pytest backend/tests/test_finance_dashboard_service.py -q`
  Expected: PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add backend/services/monthly_profit_settlement_service.py backend/tests/test_finance_dashboard_service.py
  git commit -m "fix(settlement): 人员成本查询补 calculation_version 过滤"
  ```

---

## Task 6 [阶段 2a]: 只取提成后人力成本 + 产出每店分布

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py:185-222`
- Test: `backend/tests/test_finance_dashboard_service.py`

- [ ] **Step 1: 写失败测试**

  ```python
  @pytest.mark.asyncio
  async def test_personnel_payload_returns_shop_breakdown_and_split_amounts():
      module = _load_service_module()
      service = module.MonthlyProfitSettlementService(_make_db())

      class _Row:
          def __init__(self, employee_code, scope, shop_id, performance, commission, pre):
              self.employee_code = employee_code
              self.allocation_scope = scope
              self.platform_code = "shopee"
              self.shop_id = shop_id
              self.performance_amount = performance
              self.commission_amount = commission
              self.pre_commission_amount = pre

      rows = [
          _Row("E1", "shop", "S1", 1000.0, 2000.0, 5000.0),
          _Row("E2", "company", None, 500.0, 1000.0, 8000.0),
      ]

      async def _execute(statement, *args, **kwargs):
          return _ScalarResult(rows)

      service.db.execute = _execute

      payload = await service._load_personnel_payload("2026-04")

      # 每店分布：只有 shop scope 进 breakdown
      assert payload["shop_breakdown"] == [
          {
              "platform_code": "shopee",
              "shop_id": "S1",
              "performance_amount": 1000.0,
              "commission_amount": 2000.0,
              "allocation_amount": 3000.0,
          }
      ]
      # 总额：全部 scope 的绩效工资 + 提成；pre_commission 已在利润基数扣过，不计
      assert payload["actual_amount"] == 4500.0
      assert payload["performance_salary_amount"] == 1500.0
      assert payload["commission_amount"] == 3000.0
  ```

- [ ] **Step 2: 运行确认失败**

  Run: `pytest backend/tests/test_finance_dashboard_service.py::test_personnel_payload_returns_shop_breakdown_and_split_amounts -q`
  Expected: FAIL — 当前返回键只有 `['actual_amount', 'details']`，**没有** `shop_breakdown` / `performance_salary_amount` / `commission_amount`。

- [ ] **Step 3: 实现**

  在 `_load_personnel_payload` 中：
  - 累加 `performance_amount` → `performance_salary_amount`；`commission_amount` → `commission_amount`
  - `actual_amount = performance_salary_amount + commission_amount`（**不取 `pre_commission_amount`**）
  - 按 `allocation_scope == "shop"` 按 `(platform_code, shop_id)` 聚合出 `shop_breakdown`，每项含 `platform_code` / `shop_id` / `performance_amount` / `commission_amount` / `allocation_amount`
  - ⚠️ `company` scope 的行计入 `actual_amount`（总部员工的绩效工资与提成也是真实分配），但**不进** `shop_breakdown`

  返回结构：
  ```python
  {
      "actual_amount": total,
      "performance_salary_amount": perf_total,
      "commission_amount": comm_total,
      "details": [...],
      "shop_breakdown": [...],
  }
  ```

- [ ] **Step 4: 运行确认通过**

  Run: `pytest backend/tests/test_finance_dashboard_service.py -q`
  Expected: PASS。

- [ ] **Step 5: Commit**

  ```bash
  git add backend/services/monthly_profit_settlement_service.py backend/tests/test_finance_dashboard_service.py
  git commit -m "feat(settlement): 人员成本只取提成后金额并产出每店分布"
  ```

---

## Task 7 [阶段 2a]: 删除公司池二次扣减

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py:168-183`
- Test: `backend/tests/test_finance_dashboard_service.py`

- [ ] **Step 1: 写失败测试**

  ```python
  @pytest.mark.asyncio
  async def test_net_profit_does_not_deduct_company_pool_again():
      """公司池已在各店利润基数里摊派过，月结不得再减一次。"""
      module = _load_service_module()
      service = module.MonthlyProfitSettlementService(_make_db())

      class _Basis:
          platform_code = "shopee"
          shop_id = "S1"
          basis_version = "SETTLEMENT_BASIS_V1"

          def __init__(self, amount):
              self.profit_basis_amount = amount

      results = [_ScalarResult([_Basis(80000.0)]), _ScalarResult([10000.0])]

      async def _execute(statement, *args, **kwargs):
          return results.pop(0)

      service.db.execute = _execute

      net = await service._load_net_profit_amount("2026-04")

      assert net == 80000.0, "不得再减一次公司池"
  ```

- [ ] **Step 2: 运行确认失败**

  Run: `pytest backend/tests/test_finance_dashboard_service.py::test_net_profit_does_not_deduct_company_pool_again -q`
  Expected: FAIL — 当前返回 `80000 - 10000 = 70000`。

- [ ] **Step 3: 实现**

  删 `backend/services/monthly_profit_settlement_service.py:168-183` 的公司池扣减块，`_load_net_profit_amount` 直接 `return shop_profit_amount`。
  若 `EmployeeLaborCostAllocation` import 因此不再被 `_load_personnel_payload` 使用则一并清理（Task 6 之后它仍被使用，**不要删**）。

- [ ] **Step 4: 运行确认通过**

  Run: `pytest backend/tests/test_finance_dashboard_service.py -q`
  Expected: PASS。

- [ ] **Step 5: 跑既有回归并修正固化旧口径的断言**

  Run: `pytest backend/tests/test_monthly_profit_settlement_service.py backend/tests/test_profit_basis_service.py -q`
  Expected: 40 例中固化旧口径的用例会 FAIL。逐个检查：断言的是错误行为 → 按新口径更新并注明"口径修正"；断言仍正确 → 保留。

- [ ] **Step 6: Commit**

  ```bash
  git add backend/services/monthly_profit_settlement_service.py backend/tests/
  git commit -m "fix(settlement): 公司人力成本池不再二次扣减"
  ```

---

## Task 8 [阶段 2a]: 删除快照机制、目标额与差异算法

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py`
- Test: `backend/tests/test_finance_dashboard_service.py`、`backend/tests/test_monthly_profit_settlement_service.py`

- [ ] **Step 1: 写失败测试**

  ```python
  def test_summary_has_no_budget_target_or_difference_fields():
      module = _load_service_module()
      service = module.MonthlyProfitSettlementService(_make_db())

      summary = service.build_summary(
          period_month="2026-04",
          net_profit_amount=100000.0,
          personnel_actual_amount=32000.0,
          adjustment_amount=1000.0,
          status="draft",
      )

      for banned in (
          "personnel_target_ratio", "follow_target_ratio", "company_target_ratio",
          "personnel_target_amount", "follow_target_amount", "company_target_amount",
          "difference_amount", "difference_ratio", "follow_actual_amount",
      ):
          assert banned not in summary, f"{banned} 必须随预算制下线"

      assert summary["company_retained_amount"] == 67000.0
      assert summary["allocation_ratio"] == 0.33
  ```

- [ ] **Step 2: 运行确认失败**

  Run: `pytest backend/tests/test_finance_dashboard_service.py::test_summary_has_no_budget_target_or_difference_fields -q`
  Expected: FAIL — `TypeError: build_summary() missing 4 required keyword-only arguments: 'follow_actual_amount', 'personnel_target_ratio', 'follow_target_ratio', and 'company_target_ratio'`

- [ ] **Step 3: 改写 `build_summary`（`:66-135`）**

  新签名：`period_month, net_profit_amount, personnel_actual_amount, adjustment_amount, status, settlement_id, remark`
  - **显式删除**参数 `follow_actual_amount` 与三个 `*_target_ratio`、参数 `approved_by`
  - 返回：`net_profit_amount` / `personnel_actual_amount` / `adjustment_amount` / `company_retained_amount` / `allocation_ratio` / `over_allocation_flag` / `status` / `remark` / `id`
  - `company_retained_amount = net_profit_amount - personnel_actual_amount - adjustment_amount`
  - `allocation_ratio = (personnel_actual_amount + adjustment_amount) / net_profit_amount`（净利润为 0 时取 0）
  - `over_allocation_flag = company_retained_amount < 0 or allocation_ratio > 1`

- [ ] **Step 4: 同步所有调用点（不做这步一定 TypeError / KeyError）**

  | 调用点 | 处置 |
  |---|---|
  | `load_snapshot_settlement_view`（`:395-451`） | **删除**（连同它调用的 `get_next_snapshot_version`、`mark_active_snapshots_superseded`、`_load_snapshot_personnel_details`、`_load_follow_details`） |
  | `rebuild_month`（`:685-...`） | **改造**：不再调旧 `build_summary` 的 ratio 参数、不再写跟投明细；改为"确保该月台账行存在 + 写调整项" |
  | `get_month`（`:790-862`） | **改造**：直接返回看板 payload，不再走 `load_snapshot_settlement_view` |
  | `update_targets`（`:864-923`） | **删除**（预算制下线）。⚠️ 它是**第 5 个 `build_summary` 调用点**（`:881`），不改会 TypeError |
  | `approve`（`:925-978`） | **删除**（审批制下线）。⚠️ 它调 `get_next_snapshot_version` / `build_settlement_snapshots` / `load_snapshot_settlement_view`（本步都删）→ 悬空引用；`:941-943` 读 `difference_amount` / `difference_ratio`（已废弃列） |
  | `reopen`（`:980-1013`） | **删除**（审批制下线）。⚠️ `:1006` 调被删的 `mark_active_snapshots_superseded` |
  | `invalidate_settlement_performance`（`:1015-1039`） | **删除**。⚠️ 它会**反向改写上游** `ShopProfitBasis.is_locked` 与 `PerformanceScore`——留着比删掉更危险 |
  | `_load_personnel_details`（`:276-300`） | **删除**（只服务快照与旧月结视图） |
  | `_upsert_settlement`（`:650-681`） | **改造**：字段白名单改为新口径字段。⚠️ 现状是 `setattr(record, field, payload[field])` 逐字段取值，**旧白名单里的 10 个字段会 KeyError**（9 个 target/difference 列 + `company_actual_amount` + `follow_actual_amount`），白名单应收敛为 5 项：`net_profit_amount` / `personnel_actual_amount` / `adjustment_amount` / `status` / `remark` |
  | `build_settlement_snapshots` | **删除** |

- [ ] **Step 5: 运行确认通过**

  Run: `pytest backend/tests/test_finance_dashboard_service.py -q`
  Expected: PASS。

- [ ] **Step 6: 清理固化旧行为的 service 用例**

  Run: `pytest backend/tests/test_monthly_profit_settlement_service.py -q`
  Expected: 打在被删方法（`approve` / `reopen` / 快照 / 目标额）上的用例 FAIL——**这些用例属于被下线功能的测试，直接删除对应测试函数**，commit message 注明"随审批制与快照机制下线删除"。

- [ ] **Step 7: Commit**

  ```bash
  git add backend/services/monthly_profit_settlement_service.py backend/tests/
  git commit -m "refactor(settlement): 删除快照机制、目标比例与差异算法，改为纯残差口径"
  ```

---

## Task 9 [阶段 2a]: 看板接口 · 只读 GET 与调整项写入口

**Files:**
- Modify: `backend/services/monthly_profit_settlement_service.py`、`backend/domains/business/routers/monthly_profit_settlement.py`、`backend/routers/monthly_profit_settlement.py`、`backend/schemas/monthly_profit_settlement.py`、`backend/services/approval_center_service.py`
- Delete/Modify: `backend/tests/test_monthly_profit_settlement_routes.py`（删 8 个用例）
- Test: `backend/tests/test_finance_dashboard_routes.py`（新建）

- [ ] **Step 1: 写失败测试**

  `backend/tests/test_finance_dashboard_routes.py`：
  ```python
  from importlib import import_module


  def _router_module():
      return import_module("backend.domains.business.routers.monthly_profit_settlement")


  def test_adjustment_endpoints_exist():
      module = _router_module()
      paths = {route.path for route in module.router.routes}
      assert "/api/finance/monthly-profit-settlement/adjustments" in paths


  def test_approval_endpoints_are_removed():
      module = _router_module()
      paths = {route.path for route in module.router.routes}
      for banned in (
          "/api/finance/monthly-profit-settlement/rebuild",
          "/api/finance/monthly-profit-settlement/{settlement_id}/targets",
          "/api/finance/monthly-profit-settlement/{settlement_id}/approve",
          "/api/finance/monthly-profit-settlement/{settlement_id}/reopen",
      ):
          assert banned not in paths, f"{banned} 必须随审批制下线"
  ```

- [ ] **Step 2: 运行确认失败**

  Run: `pytest backend/tests/test_finance_dashboard_routes.py -q`
  Expected: FAIL（`/adjustments` 不存在；4 条审批路径现在都在）。

- [ ] **Step 3: 改 schema**

  `backend/schemas/monthly_profit_settlement.py`：
  - 新增 `MonthlyProfitAdjustmentCreateRequest`：`period_month: str`、`adjustment_type: str`（枚举校验）、`amount: float`、`reason: str`（**min_length=1**）
  - 新增 `MonthlyProfitDashboardEnvelopeResponse`，含 `period_month` / `as_of` / `net_profit_amount` / `performance_salary_amount` / `commission_amount` / `employee_allocation_amount` / `manual_adjustment_amount` / `manual_adjustment_count` / `company_retained_amount` / `allocation_ratio` / `over_allocation_flag` / `shop_breakdown` / `adjustments`
  - 删除 `MonthlyProfitSettlementRebuildRequest`、`MonthlyProfitSettlementTargetsUpdateRequest`

- [ ] **Step 4: 实现 service 方法**

  在 `MonthlyProfitSettlementService` 新增：

  ```python
  async def _load_adjustments_by_month(self, period_month: str) -> list[dict[str, Any]]:
      """按月取人工调整项。

      ⚠️ MonthlyProfitAdjustment 没有 period_month 字段（只有 settlement_id 外键），
      必须 join MonthlyProfitSettlement 的 period_month（唯一键）。
      """
      rows = (
          (
              await self.db.execute(
                  select(MonthlyProfitAdjustment)
                  .join(
                      MonthlyProfitSettlement,
                      MonthlyProfitAdjustment.settlement_id == MonthlyProfitSettlement.id,
                  )
                  .where(MonthlyProfitSettlement.period_month == period_month)
              )
          )
          .scalars()
          .all()
      )
      return [
          {
              "id": row.id,
              "adjustment_type": row.adjustment_type,
              "amount": self._to_float(row.amount),
              "reason": row.reason,
              "created_by": row.created_by,
              "created_at": row.created_at,
          }
          for row in rows
      ]
  ```

  ```python
  async def get_dashboard(self, period_month: str) -> dict[str, Any]:
      """只读聚合：唯一口径实现处。前端不得复刻。"""
      net_profit = await self._load_net_profit_amount(period_month)
      personnel = await self._load_personnel_payload(period_month)
      adjustments = await self._load_adjustments_by_month(period_month)
      adjustment_total = sum(a["amount"] for a in adjustments)
      employee_allocation = self._to_float(personnel.get("actual_amount"))
      company_retained = net_profit - employee_allocation - adjustment_total
      allocation_ratio = (
          (employee_allocation + adjustment_total) / net_profit if net_profit else 0.0
      )
      return {
          "period_month": period_month,
          "as_of": datetime.now(timezone.utc).isoformat(),
          "net_profit_amount": net_profit,
          "performance_salary_amount": self._to_float(personnel.get("performance_salary_amount")),
          "commission_amount": self._to_float(personnel.get("commission_amount")),
          "employee_allocation_amount": employee_allocation,
          "manual_adjustment_amount": adjustment_total,
          "manual_adjustment_count": len(adjustments),
          "company_retained_amount": company_retained,
          "allocation_ratio": allocation_ratio,
          "over_allocation_flag": company_retained < 0 or allocation_ratio > 1,
          "shop_breakdown": personnel.get("shop_breakdown", []),
          "adjustments": adjustments,
      }
  ```

  以及 `add_adjustment`（`reason` 为空直接抛 `MonthlyProfitSettlementValidationError`）与 `remove_adjustment`。
  ⚠️ 写调整项前按 `period_month` upsert 一条 `MonthlyProfitSettlement` 主记录（其余字段用默认值 0），保证 `adjustments.settlement_id` 外键有指向。
  ⚠️ `performance_salary_amount` / `commission_amount` 两个键由 Task 6 产出，**不得在此处重新计算**。

- [ ] **Step 5: 改路由**

  `backend/domains/business/routers/monthly_profit_settlement.py`：
  - `GET ""` 返回 `MonthlyProfitDashboardEnvelopeResponse`，内部调 `service.get_dashboard(period_month)`
  - 新增 `POST "/adjustments"`、`DELETE "/adjustments/{adjustment_id}"`
  - 删除 `/rebuild`、`PUT /{settlement_id}/targets`、`POST /{settlement_id}/approve`、`POST /{settlement_id}/reopen`

- [ ] **Step 6: 删审批中心的月结审批 4 处**

  `backend/services/approval_center_service.py`：删 `:14` 常量 `MONTHLY_PROFIT_SETTLEMENT_TEMPLATE_CODE`、`:54-62` `_ensure_monthly_profit_settlement_template`、`:139-169` `submit_monthly_profit_settlement_approval`、`:171-200` `sync_monthly_profit_settlement_approval_decision`。

- [ ] **Step 7: 处置打在被删端点上的路由用例**

  `backend/tests/test_monthly_profit_settlement_routes.py`（共 11 个用例）：

  **① 删 9 个打在被删端点上的用例**：
  `test_rebuild_..._returns_service_payload`（`:124`）、`test_rebuild_..._returns_409_for_approved_month`（`:193`）、`test_update_..._targets_route_returns_service_payload`（`:234`）、`test_update_..._targets_route_returns_404`（`:348`）、`test_approve_..._returns_service_payload`（`:276`）、`test_approve_..._returns_409_for_duplicate_approval`（`:380`）、`test_approve_..._returns_409_when_difference_threshold_exceeded`（`:426`）、`test_reopen_..._returns_service_payload`（`:322`）、`test_reopen_..._returns_409_for_draft_settlement`（`:403`）

  **② 处置剩下 2 个 GET 用例**（`:30` 与 `:72`）：它们断言的是**旧信封结构** `body["data"]["summary"][...]` 与 `body["data"]["personnel_details"][...]`，而 GET 已改为扁平看板 payload ⇒ 必须改写为新结构断言，例如：
  ```python
  body = response.json()
  data = body["data"]
  assert data["period_month"] == "2026-04"
  assert "company_retained_amount" in data
  assert "shop_breakdown" in data
  ```
  `:72` 那个原本断言"已审批月份返回快照 payload"的用例，语义已随快照机制下线而消失 ⇒ **直接删除**，不要改写成"返回看板 payload"，否则会掩盖快照下线这一事实。

- [ ] **Step 8: 运行**

  Run: `pytest backend/tests/test_finance_dashboard_routes.py backend/tests/test_finance_dashboard_service.py backend/tests/test_monthly_profit_settlement_routes.py -q`
  Expected: PASS。
  ⚠️ 若 Step 7② 的两个用例未改写，此处必然 FAIL（断言指向已删的信封结构）。

- [ ] **Step 9: Commit**

  ```bash
  git add backend/ && git commit -m "feat(settlement): 新增只读看板接口与人工调整项写入口，移除审批端点"
  ```

---

## Task 10 [阶段 2b]: 看板前端 · store 与组件

**Files:**
- Create: `frontend/src/stores/financeDashboard.js`、`frontend/src/domains/business/views/finance-dashboard/*.vue`、`frontend/scripts/financeDashboardView.test.mjs`
- Modify: `frontend/src/api/finance.js`

- [ ] **Step 1: 写失败测试**

  `frontend/scripts/financeDashboardView.test.mjs`（路径风格参照 `frontend/scripts/myFollowInvestmentIncomeView.test.mjs:3-11` 的 `path.dirname(fileURLToPath(import.meta.url))` 写法）：

  ```javascript
  import test from 'node:test'
  import assert from 'node:assert/strict'
  import { readFileSync } from 'node:fs'
  import path from 'node:path'
  import { fileURLToPath } from 'node:url'

  const __dirname = path.dirname(fileURLToPath(import.meta.url))
  const viewSource = readFileSync(
    path.resolve(__dirname, '../src/domains/business/views/finance-dashboard/FinanceDashboardView.vue'),
    'utf-8'
  )
  const storeSource = readFileSync(
    path.resolve(__dirname, '../src/stores/financeDashboard.js'),
    'utf-8'
  )

  test('看板不提供预算比例输入', () => {
    assert.ok(!viewSource.includes('target_ratio'))
    assert.ok(!viewSource.includes('预算(%)'))
  })

  test('看板不承载口径计算', () => {
    assert.ok(!/company_retained_amount\s*=/.test(viewSource))
    assert.ok(!/allocation_ratio\s*=/.test(viewSource))
  })

  test('store 只含看板状态，不含跟投', () => {
    assert.ok(!storeSource.includes('follow'))
  })
  ```

- [ ] **Step 2: 运行确认失败**

  Run: `cd frontend; node --test scripts/financeDashboardView.test.mjs; cd ..`
  Expected: FAIL（文件不存在）。

- [ ] **Step 3: 加 API 封装**

  `frontend/src/api/finance.js`（该文件用 `api._get/_post` 风格，`:12` 是 `import api from './index.js'`；**没有名为 `request` 的标识符**）：
  ```javascript
  getFinanceDashboard: (params) => api._get('/finance/monthly-profit-settlement', { params }),
  createFinanceAdjustment: (data) => api._post('/finance/monthly-profit-settlement/adjustments', data),
  deleteFinanceAdjustment: (id) => api._delete(`/finance/monthly-profit-settlement/adjustments/${id}`),
  ```
  ⚠️ 方法签名已核对：`frontend/src/api/index.js:835-849` 提供 `_get(path, config)` / `_post(path, data, config)` / `_put(path, data)` / `_delete(path, config)`。

- [ ] **Step 4: 建 store**

  `frontend/src/stores/financeDashboard.js`：Pinia store，只有 `periodMonth` / `dashboard` / `loading` / `error` 四个状态与 `fetchDashboard` / `addAdjustment` / `removeAdjustment` 三个 action。
  ⚠️ **错误必须落到 `error` 状态并由组件渲染进 `el-alert`**。反例参考：`frontend/src/stores/financeSettlement.js:120-136` 的 `approveMonthlyProfitSettlement` / `reopenMonthlyProfitSettlement` 两个 action——它们既不 catch 也不写 `error`，失败对页面完全不可见。新 store 必须把请求异常 catch 进 `error` 并由 `FinanceDashboardView.vue` 渲染。

- [ ] **Step 5: 建 4 个组件**

  - `FinanceDashboardView.vue`：顶部月份选择器 + `as_of` 显示 + 导出按钮；编排三个区块
  - `ProfitOverviewCards.vue`：6 张卡 + 分配占比 + 超额标记（负数显红，不截断）
  - `ShopAllocationTable.vue`：每店一行：平台/店铺/利润基数/绩效工资/提成/分配额/分配占比/异常标记
  - `AdjustmentPanel.vue`：调整项列表（类型/金额/原因/操作人/时间）+ 录入弹窗（类型下拉、金额、**原因必填**）

  ⚠️ **组件只渲染后端返回的数值**，不在前端做任何加减或占比计算（设计 §7.3 原则 3）。
  ⚠️ 超额标记只渲染后端给的 `over_allocation_flag` + 两个数 + 一句中性提示，**不在前端生成判断性文案**（设计 §7.3 原则 4）。

- [ ] **Step 6: 运行确认通过**

  Run: `cd frontend; node --test scripts/financeDashboardView.test.mjs; cd ..`
  Expected: PASS。

- [ ] **Step 7: 验证**

  Run: `cd frontend; npx vite build; cd ..`
  Run: `python scripts/verify_utf8_source_hygiene.py`
  Expected: PASS。
  ⚠️ 每条命令后 `cd ..` 回仓库根。

- [ ] **Step 8: Commit**

  ```bash
  git add frontend/ && git commit -m "feat(frontend): 新增月度利润看板组件与专用 store"
  ```

---

## Task 11 [阶段 2b]: 看板前端 · 页面切换、路由与菜单

**Files:**
- Modify: `frontend/src/domains/business/views/FinancialManagement.vue`、`frontend/src/router/index.js`、`frontend/src/config/menuGroups.js`
- Delete: `frontend/src/domains/business/views/finance-settlement/`（2 个文件）、`frontend/src/stores/financeSettlement.js`

- [ ] **Step 1: 改页面壳**

  `FinancialManagement.vue` 改为薄壳，渲染 `FinanceDashboardView.vue`。

- [ ] **Step 2: 删旧组件与旧 store**

  删 `finance-settlement/MonthlySettlementPanel.vue`、`finance-settlement/SettlementWorkspacePanel.vue`、`stores/financeSettlement.js`。
  ⚠️ 先确认 `financeSettlement.js` 的 `profitBasis` 切片没有其他消费者：`rg -n "useFinanceSettlementStore" frontend/src`，若有则把该切片迁到既有 store 再删。

- [ ] **Step 3: 改路由与菜单**

  `frontend/src/router/index.js`：
  - `:129` 标题「财务管理」→「月度利润看板」
  - `:307` 乱码 `'??????'` → `'财务概览'`（该路由是 `/financial-overview`，`:303` redirect 到 `/financial-management`，**不要与看板同名**）
  - 组件路径保持 `FinancialManagement.vue`（**路由路径 `/financial-management` 不变**）
  `frontend/src/config/menuGroups.js`：`:82` 与 `:236` 的「财务结算中心」→「月度利润看板」

- [ ] **Step 4: 验证**

  Run: `cd frontend; npx vite build; cd ..`
  Run: `cd frontend; node --test scripts/roleMenuSnapshot.test.mjs scripts/domainBridgeInventory.test.mjs; cd ..`
  Expected: PASS（domainBridgeInventory 计数已在 Task 4 Step 5 同步为 81 / 28）。

- [ ] **Step 5: 人工验收**

  起本地服务 → 打开 `/financial-management` → 确认：月份可切换、六个数正确、负数显红、店铺分布有数据、调整项可录可删、`as_of` 显示、无"预算%"输入框、无审批按钮。

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/ && git commit -m "refactor(frontend): 财务结算中心切换为只读月度利润看板"
  ```

---

## Task 12 [阶段 2c]: 指标登记、运行手册改写与 post-launch V2 计划

**Files:**
- Modify: `docs/team-skills/sea-metrics-language/references/metrics-dictionary.md`、`metric-status.md`、`SKILL.md`、`team-skills-bundle/sea-metrics-language/**`、`docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`、`docs/guides/APPROVAL_CENTER_RUNBOOK.md`、`docs/guides/ENGINEERING_STATUS.md`、`CHANGELOG.md`
- Create: `docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md`

- [ ] **Step 1: 在正本登记 6 个指标**

  在 `docs/team-skills/sea-metrics-language/references/metrics-dictionary.md` 按现有格式新增设计 §4.5 表格中的 6 个指标（中文名 / 标准键 / 层级 / 业务定义 / 系统统一口径 / 公式 / 粒度 / 适用 / 不适用 / 配套指标 / 当前状态）。
  ⚠️ 命名纪律沿用该词典既有约定：必须写全称，不得用「毛利率」「人员成本」这类歧义词。

- [ ] **Step 2: 在 `metric-status.md` 登记状态**

  6 个指标状态均为 `stable`。

- [ ] **Step 3: 在 `SKILL.md` 写明正本规则**

  加一句：「本 skill 在仓库有两份副本，正本为 `docs/team-skills/sea-metrics-language/`，副本为 `team-skills-bundle/sea-metrics-language/`，两份必须字节一致，由 `python scripts/verify_team_skills_sync.py` 校验。」

- [ ] **Step 4: 同步副本并校验**

  ```powershell
  Copy-Item 'docs\team-skills\sea-metrics-language\*' 'team-skills-bundle\sea-metrics-language' -Recurse -Force
  python scripts/verify_team_skills_sync.py
  ```
  Expected: `[OK] sea-metrics-language 两份副本一致`。

- [ ] **Step 5: 改写运行手册**

  `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`：
  - `:250-270` 「月结人员成本以工资单为最终结算口径」→ **推翻**，改为「以人力成本分摊表的绩效工资+提成为准；工资单 `total_cost` 含已扣过的提成前人力成本，不得再次作为人员成本扣除」
  - `:95-101` 未落地项、`:333-339` 已知限制 → 同步更新
  - 追加业务签字记录（前置 P1）
  - ⚠️ **不动 `:19-37`**——那一节是**上游利润基数口径公式**（`profit_basis_amount = orders_profit_amount - a_class_cost_amount`、`company_net_profit = SUM(shop_profit_basis.profit_basis_amount)`），设计 §3 已把「店铺利润基数口径本身」列为非目标。需要说明看板读取口径时**只追加说明，不改上游公式**。

  `docs/guides/APPROVAL_CENTER_RUNBOOK.md`：删月结审批模板登记（`monthly_profit_settlement_approval`）——跟投部分已在 Task 4 Step 6 删除。
  `docs/guides/ENGINEERING_STATUS.md`、`CHANGELOG.md`：记录模块转看板 + 跟投下线。

- [ ] **Step 6: 产出 post-launch V2 治理计划**

  新建 `docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md`，逐条落地设计 §11 的 7 项：
  1. 后端模块重命名（方案 A）
  2. 提成链路 5 处第二实现收敛
  3. 绩效系数统一（逐店 min vs 加权平均）
  4. 提成缺失对账断言
  5. `performance_coefficient.py` / `monthly_settlement_service.py` 补单测
  6. `PERFORMANCE_RACING_POLICY.md` 第五节无实现
  7. 前端 `frontend/tests/` 未挂 npm script

  每条写明：问题、证据路径、影响面、预估范围、与其他任务的关系。

- [ ] **Step 7: 验证**

  Run: `python scripts/verify_rules_completeness.py`
  Run: `python scripts/verify_root_md_whitelist.py`
  Run: `python scripts/verify_team_skills_sync.py`
  Expected: 全部 PASS。

- [ ] **Step 8: Commit**

  ```bash
  git add docs/ team-skills-bundle/ CHANGELOG.md
  git commit -m "docs: 登记月度利润看板指标、改写过时口径并产出 post-launch V2 计划"
  ```

---

## Task 13 [阶段 3]: 旧结构清理迁移

**前置：** 旧月结历史（生产仅 2026-03 一条 approved）已导出留存。

**Files:**
- Create: `current_migrations/versions/20261242_drop_monthly_profit_snapshots.py`
- Modify: `modules/core/db/schema_parts/business.py`、`modules/core/db/schema.py`、`backend/services/monthly_profit_settlement_service.py`、`backend/domains/business/routers/hr_employee.py`
- Delete: `backend/tests/test_monthly_profit_snapshot_schema_contract.py`
- Modify（测试）: `backend/tests/test_finance_schema_contract.py:120-133`

> ⚠️ **这一步会波及一个无关模块**：`backend/domains/business/routers/hr_employee.py:48` import 了 `MonthlyProfitPayrollSnapshot`，并在 `:387-391` 使用它。跟投/看板改造完全没碰过这个 HR 路由，但删掉快照 ORM 会打爆它。**必须先决定该路由改走哪条口径**，再删表。

- [ ] **Step 1: 摸清 5 个快照类的全部引用点**

  ```powershell
  rg -n "MonthlyProfitPersonnelDetail|MonthlyProfitPayrollSnapshot|MonthlyProfitShopBasisSnapshot|MonthlyProfitEmployeeCommissionSnapshot|MonthlyProfitEmployeePerformanceSnapshot" backend modules
  ```
  预期至少命中：
  - `modules/core/db/schema_parts/business.py`（5 个类定义）
  - `modules/core/db/schema.py:182, 185-188`（显式 import）与 `:391, 394-397`（`_BUSINESS_EXPORTS`）
  - `backend/services/monthly_profit_settlement_service.py:16, 17, 19, 20, 21`（import）
  - `backend/domains/business/routers/hr_employee.py:48` 与 `:387-391`（**跨模块依赖**）
  - `backend/tests/test_monthly_profit_snapshot_schema_contract.py:2-5`
  - `backend/tests/test_finance_schema_contract.py:120-133`

  同时确认废弃列的引用点：
  ```powershell
  rg -n "personnel_target_ratio|follow_target_ratio|company_target_ratio|personnel_target_amount|follow_target_amount|company_target_amount|difference_amount|difference_ratio|follow_actual_amount|company_actual_amount" backend modules frontend
  ```

- [ ] **Step 2: 决定 `hr_employee.py` 的替代口径**

  读 `backend/domains/business/routers/hr_employee.py:380-400`，确认 `:387-391` 用 `MonthlyProfitPayrollSnapshot` 做什么。二选一并写进 commit message：
  - **选项 A（推荐）**：该处改为直接读已锁定的工资单（`PayrollRecord.total_cost` 等），不再依赖月结快照表
  - **选项 B**：保留 `MonthlyProfitPayrollSnapshot` 表不删，只删其余 4 张

  ⚠️ 若选 B，本 Task 的 drop 清单要相应缩小。

- [ ] **Step 3: 写迁移**

  - `revision = "current_schema_20261242_drop_monthly_profit_snapshots"`
  - `down_revision = "current_schema_20261241_drop_follow_investment"`
  - drop 5 张停写表：
    `finance.monthly_profit_personnel_details`、`finance.monthly_profit_payroll_snapshots`、`finance.monthly_profit_shop_basis_snapshots`、`finance.monthly_profit_employee_commission_snapshots`、`finance.monthly_profit_employee_performance_snapshots`
  - drop `finance.monthly_profit_settlements` 上的废弃列：`personnel_target_ratio`、`follow_target_ratio`、`company_target_ratio`、`personnel_target_amount`、`follow_target_amount`、`company_target_amount`、`difference_amount`、`difference_ratio`、`follow_actual_amount`
  - ⚠️ `personnel_actual_amount` / `company_actual_amount` / `adjustment_amount` 是否一并 drop，取决于 Step 1 的引用结果；看板若已不从该表读这些值则可删。

- [ ] **Step 4: 同步 ORM 与导出清单**

  `modules/core/db/schema_parts/business.py`：删 5 个类 + `MonthlyProfitSettlement` 的废弃列声明。
  `modules/core/db/schema.py`：删 `:182, 185-188` 的 5 个 import 与 `:391, 394-397` 的 `_BUSINESS_EXPORTS` 条目。
  `backend/services/monthly_profit_settlement_service.py`：删 `:16, 17, 19, 20, 21` 的 5 个 import 与相关引用。

- [ ] **Step 5: 处理跨模块依赖与测试**

  - 按 Step 2 的决定改 `backend/domains/business/routers/hr_employee.py`
  - 删 `backend/tests/test_monthly_profit_snapshot_schema_contract.py`（整份，它直接 import 这 4 个类 ⇒ 删类后 collection error）
  - 改 `backend/tests/test_finance_schema_contract.py:120-133`（断言这 5 个模型存在 ⇒ 删类后 5 条新失败）

- [ ] **Step 6: 验证**

  Run: `python -c "import backend.domains.business.routers.hr_employee; import backend.services.monthly_profit_settlement_service; import modules.core.db; print('ok')"`
  Expected: `ok`

  Run: `python scripts/verify_architecture_ssot.py`
  Run: `python -m pytest -q --tb=no --junitxml="$env:TEMP\after_cleanup.xml"`
  Run: `python scripts/diff_pytest_junit.py "$env:TEMP\base.xml" "$env:TEMP\after_cleanup.xml"`
  Expected: 无 `NEW` 条目。

- [ ] **Step 7: Commit**

  ```bash
  git add current_migrations/ modules/core/db/ backend/ && git commit -m "refactor(db): 清理月结停写快照表与废弃列"
  ```

---

## Task 14 [收尾]: 最终验收

- [ ] **Step 1: 全量失败集差异**

  ```powershell
  python -m pytest -q --tb=no --junitxml="$env:TEMP\final.xml"
  python scripts/diff_pytest_junit.py "$env:TEMP\base.xml" "$env:TEMP\final.xml"
  ```
  Expected: 无 `NEW`；`FIXED` 列出被本次修好的旧用例。

- [ ] **Step 2: 前端构建与测试**

  ```powershell
  cd frontend
  npx vite build
  node --test "scripts/*.test.mjs"
  cd ..
  ```
  Expected: build 成功，全部测试 PASS。
  ⚠️ 引号让 Node 自己展开 glob（Node ≥ 21；仓库 `frontend/package.json` 声明 `node >= 24`）。

- [ ] **Step 3: 架构与规则校验**

  ```powershell
  python scripts/verify_architecture_ssot.py
  python scripts/verify_rules_completeness.py
  python scripts/verify_root_md_whitelist.py
  python scripts/verify_utf8_source_hygiene.py
  python scripts/verify_team_skills_sync.py
  ```
  Expected: 全部 PASS。

- [ ] **Step 4: 人工业务验收**

  选一个本地库已有完整数据的月份走一遍：切换月份 → 核对净利润/绩效工资/提成/员工侧分配/公司留存 → 核对各店 breakdown 合计 == 员工侧分配额 → 录一笔人工调整 → 确认「含 N 笔人工调整」角标 → 删掉该调整 → 确认负数场景显红。

- [ ] **Step 5: 口径切换说明**

  把前置 P4 产出的「口径切换前后同月对比」写进上线说明，明确告知：**切换后所有历史月份的公司留存数字都会变化**（这是修正重复扣减与公司池双扣的结果，不是回归）。

- [ ] **Step 6: Commit**

  ```bash
  git add -A && git commit -m "docs: 补充口径切换说明与上线验收记录"
  ```

---

## §2 任务依赖与执行顺序

```
前置 P1-P5
  ↓
Task 1（词典对齐，阶段 2c 前置） ─────────────────────┐
  ↓                                                   │
Task 2（DB 迁移，1a）                                   │
  ↓                                                   │
Task 3（后端下线，1b）                                  │
  ↓                                                   │
Task 4（前端+测试+文档，1c）                            │
  ↓                                                   │
Task 5（版本过滤，2a）→ Task 6（只取提成后+breakdown）→ Task 7（公司池）→ Task 8（删快照/目标额）→ Task 9（接口，2a）
  ↓                                                                              │
Task 10（前端组件，2b）→ Task 11（页面切换，2b）                                    │
  ↓                                                                              │
Task 12（指标+文档+V2计划，2c） ←────────────────────────────────────────────────┘
  ↓
Task 13（清理迁移，3）
  ↓
Task 14（验收收尾）
```

**Task 12 依赖 Task 1**（词典必须先对齐才能登记指标）。

## §3 不在本计划范围内

见设计文档 §11（post-launch V2 治理项，由 Task 12 Step 6 产出计划文件）与 §3（非目标）。特别提醒实施者：**不要顺手改上游工资 / 提成 / 绩效 / 成本 / 利润口径链路**（`docs/guides/PRE_LAUNCH_RULES.md:39`）。

## §4 实施中需确认的开放项

| 项 | 确认时点 |
|---|---|
| `investor` 角色是否一并下线 | 前置 P3 |
| 跟投表实际行数 | 前置 P2 |
| `settlements` 表哪些列在阶段 3 一并 drop | Task 13 Step 1 |
| 历史月份口径版本并存的实际范围 | 前置 P4 |

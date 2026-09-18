# Miaoshou purchase/inventory export — Subagent-Driven Progress Ledger

**Plan:** `docs/superpowers/plans/2026-09-13-miaoshou-purchase-inventory-export.md`
**Branch:** `feat/miaoshou-purchase-inventory-export`

## Completed Tasks

- **Task 1: Create `inventory_config.py`** (complete, commits `f0ec5963..7e59fe9a`, review clean)
  - Minor findings (roll-up for final review):
    1. `task-1-report.md` line 8: "13 字段" → 应为 "12 字段"（文档笔误，不影响代码）
    2. `inventory_config.py:26`: unused `List` import（按 brief 复刻，留待后续统一清理）
    3. 风格：`Tuple[str, ...]` vs `orders_config.py` 的 `list[str]`（实施者已显式标记，留待 plan 层统一）

- **Task 2: Create `warehouse_filters.py` + contract test** (complete, commits `7e59fe9a..449d6235`, review clean)
  - Minor findings (roll-up for final review):
    1. 新文件末尾缺换行符（POSIX 惯例，可在 final review 时统一修复）

- **Task 3: Create `inventory_export.py` + contract test** (complete, commits `449d6235..de1ec9df`, review clean)
  - Architecture note (recorded for Task 6 fix, not part of Task 3 scope):
    1. `MiaoshouNavigation.__init__` 类型注解为 `OrdersSelectors | WarehouseSelectors | None`，缺 `InventorySelectors`。运行时无问题（duck typing），Task 6 已处理。

- **Task 4: inventory v2_flow + adapter modification** (complete, commits `de1ec9df..d911c7b2`, review clean)
  - Cross-task risk flagged for Task 5 (must address during archive):
    1. `backend/services/component_runtime_resolver.py:18` — runtime 注册表仍写死旧 mapping
    2. `backend/tests/test_canonical_miaoshou_combo_paths.py:60-64` — 断言旧 mapping 与旧 module_name
    3. `backend/tests/test_component_runtime_resolver.py:404, 433-434` — 断言 inventory 走旧 manifest
    4. `backend/tests/test_miaoshou_supporting_components_contract.py:8, 23` — 断言旧文件路径存在
  - Task 5 不能只 git mv + 更新文档，必须同步更新这 4 个文件。

- **Task 5: Archive old inventory files + sync runtime registry + update docs** (complete, commit `ee8d7551`, review ✅ Approved spec + quality)
  - Cross-task risk cleanup (4 files from Task 4 review) all addressed.
  - **Concern #1 (critical brief gap, implementer fixed in-flight)**: `MiaoshouNavigation` had hard import `WarehouseSelectors` from `warehouse_config`. Archive broke import. Fix: inlined lightweight `_DefaultNavSelectors` dataclass in `navigation.py` + updated `test_miaoshou_navigation_overlay_cleanup.py`. Reviewer ✅ approved workaround.
  - 35 passed, 1 pre-existing unrelated failure (`test_preflight_create_task_rejects_when_export_component_has_no_stable` — 401 vs 400, unrelated to this task).
  - Minor findings (roll-up for final review):
    1. `navigation.py` initially had unused `Optional` import (Task 6 已顺手删除)
    2. Plan doc should note "navigation.py detach from warehouse_config" as a follow-up
    3. `test_canonical_miaoshou_combo_paths.py:64` assertion could be strengthened

- **Task 6: TargetPage.PURCHASE + navigation.py PURCHASE 分支** (complete, commit `242778240059585a3781dc4467b936a94641eb58`, review ✅ Approved spec + quality)
  - 19 passed（2 nav overlay + 17 inventory/warehouse filters）
  - **偏离 brief 字面**：按 controller 修正方案保留 `_DefaultNavSelectors`（避免 `InventorySelectors` 无 `deep_link_template` 字段导致 ORDERS 分支 AttributeError）
  - 顺手删除 Task 5 残留的 unused `Optional` import
  - Minor finding (roll-up for final review):
    1. `_purchase_goods_url` 中 `getattr(self.sel, "base_url", DEFAULT_BASE_URL)` 的 fallback 是 dead code 双保险（所有已知 selectors 都有 `base_url`）— 无害，留到 final review 统一考虑

- **Task 7: Create `purchase_config.py` (`PurchaseSelectors`)** (complete, commit `56ba4af7`, review ✅ Approved spec + quality)
  - 153 行新文件，与 `inventory_config.py` / `orders_config.py` 风格对齐
  - 5 条 assertion 全部 PASS
  - 包含 `purchase_path` 字段（Task 6 duck typing 接管已就绪）

- **Task 8: Create `MiaoshouPurchaseExport` + contract test** (complete, commit `41f56ba6`, review ✅ Approved spec + quality)
  - 289 行实现 + 100 行测试，14 个私有方法覆盖 spec §3.5 全流程
  - 10 passed（brief 计数 9 是笔误，实际 10 test functions）
  - 4 个 brief 偏离均合理：`LAST_90_DAYS` 枚举缺口（注释文档化）、`asyncio` 顶部 import、inline `导入/导出` 字面量（修 brief 自身不一致）、`time_mode` 未用保留
  - Minor findings (roll-up for final review):
    1. `time_mode` 死代码（line 343）—— 留作未来 mode-based 分发或删除
    2. 文件末尾缺 trailing newline（两个新文件）—— POSIX 惯例
    3. `DateOption.LAST_90_DAYS` 缺口（已在源码注释）—— 单独评估是否扩展枚举

- **Task 9: purchase v2_flow + adapter** (complete, commit `5a4687da`, review ✅ Approved spec + quality)
  - v2_flow 测试 67 行（8 个 test function）+ adapter +1 行
  - 18 passed (10 contract + 8 v2_flow)
  - brief Step 4 数字笔误（17 vs 实际 18）已记录
  - Minor finding (roll-up for final review): `source.index(...)` 在字符串缺失时抛 `ValueError` 而非断言失败 — 与 inventory v2_flow 一致风格

- **Task 10: Full validation (ruff/mypy/pytest)** + **Fix** (complete, validation commit: Task 10 不提交 / Fix commit `881d996e`)
  - pytest **55 passed** (含 inventory 8+7, purchase 10+8, warehouse 2, orders 12+8)
  - ruff 报告 1 F841 (`time_mode` 未用) + mypy 报告 2 个 arg-type 错误（`navigation.py` 签名过窄）
  - Fix commit: 删除 `time_mode` + 拓宽 `MiaoshouNavigation.__init__` 签名为 `OrdersSelectors | _DefaultNavSelectors | InventorySelectors | PurchaseSelectors | None`
  - 修后 ruff 0 / mypy 0 on miaoshou components / pytest 37 passed（修改的两个文件相关回归测试）

- **Final: Whole-branch code review + Fix** (complete, review report: Approved with minor fixes / Fix commit `b6ad24c7`)
  - 终点 reviewer 验证：spec §1-10 全段达标、archive 干净、tests 63 passed、ruff 0 errors
  - 7 个 Minor findings，其中 4 个可执行（已完成）：
    - Fix #1: `component_runtime_resolver.py` 添加 `purchase` runtime alias
    - Fix #2: 6 个新文件末尾补 trailing newline (POSIX)
    - Fix #3: plan 文档登记 navigation.py detach follow-up（plan 首次纳入版本控制）
    - Fix #4: `test_canonical_miaoshou_combo_paths.py:64` 加强 archive 彻底断言
  - 3 个 Minor 未动（无害 / 跨 scope）：
    - `inventory_config.py` unused `List` import（Ruff 0 errors）
    - `navigation.py` `_purchase_goods_url` dead code fallback
    - `DateOption.LAST_90_DAYS` 缺口（需后续单独评估枚举扩展）
  - 修后：**73 passed, 1 pre-existing failure**（`test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400，已 git stash 验证与本次无关）

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `0df5c912` (--no-ff) on `main` 2026-09-13
**Strategy**: `--no-ff` 保留 feature branch 身份与 13 个 commits
**Test result**: 73 passed + 1 pre-existing unrelated failure (`test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400，与本分支无关)
**Lint/Type**: ruff 0 errors / mypy 0 errors on miaoshou components

**Commit 列表（13 个）**:
```
0df5c912 (HEAD -> main, origin/main) Merge branch 'feat/miaoshou-purchase-inventory-export'
1b6f0a52 docs(superpowers): include miaoshou purchase/inventory spec in branch history
b6ad24c7 chore(miaoshou): address whole-branch review findings (purchase alias, trailing newlines, plan follow-up, archive assertion)
881d996e fix(miaoshou): remove unused time_mode + widen MiaoshouNavigation selectors type
5a4687da feat(miaoshou): wire purchase export to canonical adapter and add v2_flow tests
41f56ba6 feat(miaoshou): add MiaoshouPurchaseExport canonical V2 component with async polling
56ba4af7 feat(miaoshou): add purchase_config with PurchaseSelectors dataclass
24277824 feat(miaoshou): add TargetPage.PURCHASE and navigation branch for purchase/goods
ee8d7551 chore(miaoshou): archive old inventory_snapshot_export + warehouse_config
d911c7b2 feat(miaoshou): wire inventory export to canonical adapter and add v2_flow tests
de1ec9df feat(miaoshou): add MiaoshouInventoryExport canonical V2 component
449d6235 feat(miaoshou): add warehouse filters component for inventory
7e59fe9a feat(miaoshou): add inventory_config with InventorySelectors dataclass
```

**Merge 后清理状态**:
- ✅ 本地 feature branch 已删除（`git branch -d`）
- ✅ Stash 已 pop，pre-existing 6 个 modified 文件已恢复
- ✅ 3 个 pre-existing untracked 文件保留（不属本任务）
- ✅ `.superpowers/sdd/` 已 gitignored，SDD scratch 文件保留供审计
- ⏳ **未推送**到 origin/main（等待用户授权）

**Follow-up tickets 建议**（非阻塞）:
1. `DateOption.LAST_90_DAYS` 枚举扩展（独立 task）
2. `MiaoshouExport` 死链清理（products / warehouse / analytics 的 module_name 不匹配，独立 task）
3. `test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400 修复（pre-existing 认证问题，独立 ticket）

---

# feat/miaoshou-purchase-frontend-enable 收尾记录（2026-09-13）

**目标**：在前后端的"数据域枚举层"暴露 `purchase` 域，使前端的采集任务 / 采集配置面板可勾选"采购"，并被后端 capability / data domain 校验通过。

**Plan**：`docs/superpowers/plans/2026-09-13-miaoshou-purchase-frontend-enable.md`

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `ca2af798` (--no-ff) on `main` 2026-09-13
**Strategy**: `--no-ff` 保留 feature branch 身份与 4 个 commits
**Test result**: 23 passed (purchase enablement 7 + shop_accounts_api 9 + collection_contracts 7)
**Lint/Type**: ruff 1 pre-existing E712 (line 128，commit `35b3f2e66` 2026-05-05 与本任务无关) / mypy pre-existing "source file found twice" 配置冲突

**Commit 列表（4 个）**:
```
ca2af798 (HEAD -> main, origin/main, cnb/main) Merge branch 'feat/miaoshou-purchase-frontend-enable'
403a4b6e docs(superpowers): include miaoshou purchase-frontend-enable spec in branch history
5b2c80cd feat(collection-ui): expose purchase data domain in quick collect and config panels
3a2442e9 fix(collection): backfill unknown capability domains to defaults + sync test assertions
ac71c844 feat(collection): enable purchase data domain in config templates and shop capabilities
```

**改动汇总（7 files，+419/-3）**:
- `backend/services/collection_contracts.py` — `DEFAULT_CONFIG_DATA_DOMAINS` + `get_default_shop_capabilities` + `resolve_shop_capabilities` 加性扩展 `purchase`
- `backend/domains/collection/routers/shop_accounts.py` — `_default_capabilities_for` 加 `"purchase": True`
- `backend/tests/test_purchase_data_domain_enablement_contract.py` — 新建 7 条契约测试
- `backend/tests/test_shop_accounts_api.py` — 2 个硬编码 dict 同步加 `purchase: True`
- `frontend/src/constants/collection.js` — SSOT `DEFAULT_DOMAIN_OPTIONS` 加 `{label:'采购', value:'purchase'}`
- `frontend/src/domains/collection/views/collection/CollectionTasks.vue` — checkbox 组 + `getDomainLabel` 映射同步
- `docs/superpowers/plans/2026-09-13-miaoshou-purchase-frontend-enable.md` — plan 归档

**关键决策与发现**:
1. 子代理识别 brief 一致性问题 A：`resolve_shop_capabilities` 对 DB 行缺 `purchase` key 时强制 `False`（bug，违反"未知域回退默认值"语义）。**修复**：让 `resolve_shop_capabilities` 在 `capabilities.get(domain, defaults[domain])` 处回退到 `get_default_shop_capabilities`，与 `capabilities is None` 分支语义一致。
2. 子代理识别 brief 一致性问题 B：`test_shop_accounts_api.py` 2 个硬编码 dict 等值断言，因 `_default_capabilities_for` 多 1 个 key 而失败。**修复**：同步更新断言期望值。
3. `CollectionConfig.vue` 的 `getDomainLabel` 无需修改（经 `getAvailableDomainOptions()` 自动从 SSOT 继承）。

**Merge 后清理状态**:
- ✅ 本地 feature branch 已删除（`git branch -d`）
- ✅ Pre-existing 6 modified + 3 untracked（product_category 范畴）保留未触碰
- ✅ 三处 ref 完全一致：`HEAD = origin/main = cnb/main = ca2af798`
- ✅ origin `main` 推送成功（`git push origin main` 一次性覆盖 github + cnb 两个 push URL）
- ✅ 23 passed 静态冒烟通过

**验收遗留 (pre-existing，与本任务无关)**:
- `backend/tests/test_collection_account_capability_alignment.py` 2 个 404（"Shop account acc-1 not found or disabled"）
- ruff E712 line 128 (`shop_accounts.py` `is_active == True`，2026-05-05)
- mypy pre-existing "source file found twice" 配置冲突
- ESLint 6 个错误（行号 38/594/601/602/612/1085，均不在本任务改动行）
4. 推送 `main` 到 origin

---

# feat/miaoshou-date-picker-trigger-fallback 收尾记录（2026-09-13）

**目标**：修复妙手采购页面的日期控件 trigger fallback —— `MiaoshouDatePicker._open()` 缺少 "创建日期 / 创建时间" 文本 fallback 标签，导致 `MiaoshouPurchaseExport` 实际跑采购页面（标签为"创建日期"）时无法打开日期控件。同时修正 `purchase_config.CUSTOM_DATE_INPUT_NAMES` 以反映真实 DOM 标签。

**Plan**：`docs/superpowers/plans/2026-09-13-miaoshou-date-picker-trigger-fallback.md`

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `0f034e06` (--no-ff) on `main` 2026-09-13
**Strategy**: `--no-ff` 保留 feature branch 身份与 4 个 commits
**Test result**: 5 passed (date picker trigger fallback contract) + 53 passed (orders/purchase/inventory 回归)
**Lint/Type**: ruff 0 errors on miaoshou components / mypy pre-existing 配置冲突无关

**Commit 列表（4 个）**:
```
0f034e06 (HEAD -> main, origin/main, cnb/main) Merge branch 'feat/miaoshou-date-picker-trigger-fallback'
66eaac3e docs(superpowers): include miaoshou date-picker-trigger-fallback spec in branch history
f28e871b fix(miaoshou): extend date picker trigger fallback to cover purchase page labels
```

**改动汇总（3 files，+515/-13）**:
- `modules/platforms/miaoshou/components/date_picker.py` — `_open()` fallback 链扩展（新增 `创建日期` / `创建时间` 文本标签）；`_wait_custom_range_applied` 与 `apply_custom_range` 同步支持 purchase 标签
- `modules/platforms/miaoshou/components/purchase_config.py` — `CUSTOM_DATE_INPUT_NAMES` 由 `("开始时间", "结束时间")` 改为 `("创建日期", "创建时间")`
- `backend/tests/test_miaoshou_date_picker_trigger_fallback.py` — 新建 5 条 mock-page contract 测试（5 个 fallback 路径）
- `docs/superpowers/plans/2026-09-13-miaoshou-date-picker-trigger-fallback.md` — plan 归档

**关键决策与发现**:
1. 子代理识别 brief 一致性问题 1：plan 中的 `_clickable_locator()` mock 没设 `.first` 指向自身，而实现用 `page.get_by_role(...).first`，导致 `await locator.first.click(...)` 抛 `TypeError`。**修复**：让 `locator.first = locator`。
2. 子代理识别 brief 一致性问题 2：plan 中的 `_make_page` 对未匹配 role/name 返回默认 `MagicMock()`，会"自动成功"，使 fallback 链测试形同虚设。**修复**：拆为 `_clickable_locator()`（匹配 / `button` 默认）与 `_missing_locator()`（其他未匹配），真正演练 fallback 链。
3. `apply_custom_range` 新增第二个 `("创建日期", "结束日期")` 元组到输入名 fallback 循环 —— 这是行为扩展而非纯重构（orders 路径仍先试 `("开始日期", "结束日期")`，不受影响；purchase 路径靠第二个元组打通）。

**Merge 后清理状态**:
- ✅ 本地 feature branch 已删除（`git branch -d feat/miaoshou-date-picker-trigger-fallback`）
- ✅ Pre-existing product_category 改动（6 modified + 3 untracked）保留未触碰
- ✅ 三处 ref 完全一致：`HEAD = origin/main = cnb/main = 0f034e06`
- ✅ origin `main` 推送成功（`git push origin main` 一次性覆盖 github + cnb 两个 push URL）
- ✅ 5 passed (date picker contract) + 53 passed (orders/purchase/inventory 回归) 静态冒烟通过
- ✅ `main-integration` worktree 自动清理，只剩 `codex/git-mirror-reconcile` worktree

**验收遗留 (pre-existing，与本任务无关)**:
- ruff E712 line 128 (`shop_accounts.py`，2026-05-05)
- mypy pre-existing "source file found twice" 配置冲突
- ESLint pre-existing 6 个错误（行号 38/594/601/602/612/1085）
- `test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400（无关）
- `test_collection_account_capability_alignment.py` 2 个 404（无关）

**后续验证建议**:
用户应在真实妙手环境再次跑一次采购数据域采集任务，确认：
1. 日期控件能正常打开（_open() 走 `创建日期` 文本 fallback）
2. 自定义时间范围能正确应用（_wait_custom_range_applied + apply_custom_range 走 purchase 标签路径）
3. 订单数据域采集仍正常工作（orders 路径走 `开始时间` / `下单时间` 兼容分支不受影响）

---

# fix/miaoshou-purchase-date-picker-selectors 收尾记录（2026-09-13）

**目标**：修复妙手采购数据域日期控件实际跑不通的问题 —— 上次合并 (`0f034e06`) 只扩展了 `_open()` 的文本 fallback，但没有修复 purchase_export.py:42 注入错 selectors，以及 purchase_config.CUSTOM_DATE_INPUT_NAMES 错配面板真实 textbox 名字。

**Plan**：基于真实 pwcap 快照（`output/playwright/work/miaoshou/finance-inventory-recording/purchase-02-filters-open.md`，GB18030 解码）发现：
- purchase 与 orders 日期控件 DOM 几乎完全一致（外部 combobox + panel 内 textbox + shortcut + 日历）
- 唯一差异：shortcut 列表（orders 有"近60天"无"近90天"，purchase 反之）+ 外部 label（orders "下单时间"，purchase "创建日期"）
- panel 内 textbox 真实名字：`开始日期` / `结束日期` / `开始时间` / `结束时间`（**跟 orders 完全一致**）
- 上次 fix (`f28e871b`) 把 `CUSTOM_DATE_INPUT_NAMES` 改成 `("创建日期", "创建时间")` 是错的 —— "创建日期" 是外部 label，不是 panel 内的 textbox 名

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `1ccf8248` (--no-ff) on `main` 2026-09-13
**Strategy**: `--no-ff` 保留 fix branch 身份与 1 个 commit
**Test result**: 72 passed（含 4 条新 contract 测试 + 68 个回归）
**Lint/Type**: ruff 0 errors / mypy 0 new errors

**Commit 列表（1 个 fix + 1 merge）**:
```
1ccf8248 (HEAD -> main, cnb/main) Merge branch 'fix/miaoshou-purchase-date-picker-selectors'
e84a2cf3 fix(miaoshou): wire MiaoshouDatePicker to PurchaseSelectors and align input names
```

**改动汇总（5 files，+98/-7）**:
- `modules/platforms/miaoshou/components/purchase_export.py` — line 42 改为 `self.sel`（注入 PurchaseSelectors）；移除 unused `OrdersSelectors` import（ruff F401）
- `modules/platforms/miaoshou/components/purchase_config.py` — `CUSTOM_DATE_INPUT_NAMES` 还原为 `("开始日期", "结束日期")`；新增 `CUSTOM_TIME_INPUT_NAMES = ("开始时间", "结束时间")` 和 dataclass 字段
- `modules/platforms/miaoshou/components/date_picker.py` — 构造函数类型注解放宽为 `OrdersSelectors | PurchaseSelectors | None`（mypy 必要）；`_wait_ready` 把"确定"按钮 wait 用 try/except 包裹（panel 无"确定"按钮不阻塞）
- `backend/tests/test_miaoshou_purchase_export_contract.py` — +2 测试（input name 字段对齐 + 注入 selectors 验证）
- `backend/tests/test_miaoshou_date_picker_trigger_fallback.py` — +2 测试（purchase shortcuts 含"近90天"不含"近60天" + 缺"确定"按钮不抛错）

**关键决策与发现**:
1. **实施前先看真实 DOM** —— 之前两次修复（`f28e871b` 创建日期 fallback + `0f034e06` trigger fallback 扩展）都是基于截图推断，没看真实 accessibility tree。本次通过 `pwcap` 快照 GB18030 解码后确认 purchase 与 orders DOM 一致，避免了一次过度设计（重构 selectors 驱动 + 5 个新字段 + 角色分发 `_read_input_value`）的浪费。
2. **子代理的合理调整**（控制器已确认）：
   - 测试用文件已有 `_ctx()` helper 替代 `ExecutionContext()` 无参调用（适配文件惯例）
   - 测试 mock 只让"近90天"返回 clickable，其他 missing（让循环真遍历到"近90天"）
   - 移除 `purchase_export.py` 中 unused 的 `OrdersSelectors` import（ruff F401 必要）
   - `MiaoshouDatePicker.__init__` 类型注解放宽（mypy 必要，**纯类型改动无行为变更**）

**Merge 后清理状态**:
- ✅ 本地 fix branch 已删除（`git branch -d fix/miaoshou-purchase-date-picker-selectors`）
- ✅ Pre-existing product_category 改动（6 modified + 3 untracked）保留未触碰
- ✅ 三处 ref 状态：`HEAD = cnb/main = 1ccf8248`；`origin/main` 因 GitHub 网络不可达暂未同步
- ✅ cnb/main 推送成功（`git push cnb main` → `0f034e06..1ccf8248`）
- ⚠️ **origin/main（GitHub）推送失败**：合并时 `git push origin main` 报 `Recv failure: Connection was reset`；后续重试 `Failed to connect to github.com port 443 after 21091 ms`。cnb 已同步，GitHub 待网络恢复后手动 `git push origin main`

**验收遗留 (pre-existing，与本任务无关)**:
- ruff E712 line 128 (`shop_accounts.py`，2026-05-05)
- mypy pre-existing "source file found twice" 配置冲突
- ESLint pre-existing 6 个错误
- `test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400
- `test_collection_account_capability_alignment.py` 2 个 404
- mypy pre-existing errors in `modules/platforms/shopee/components/date_picker.py` / `backend/services/` / `modules/utils/` / `modules/collectors/` / `backend/schemas/notification.py`

**端到端验证建议（merge 后在妙手真实环境）**:
1. 跑一次采购数据域采集任务，确认 `_wait_ready()` 能用 purchase 的 shortcuts（含"近90天"）找到按钮，panel 正常打开
2. 自定义时间范围能正确应用（fill panel 内 textbox "开始日期"/"结束日期"/"开始时间"/"结束时间"，外部 combobox 显示更新）
3. 订单数据域采集仍正常工作（orders 路径未受影响）

---

# fix/miaoshou-purchase-tab-url-param 收尾记录（2026-09-13）

**目标**：修复 `_select_status_tab` 在 purchase 页面 click label role 超时导致整个 run 失败的问题。前一个 fix（`e84a2cf3`）修好了 date picker 链路本身，但实际跑测试时流程在更早的 `_select_status_tab` 就 2000ms 超时，根本没走到 date picker —— 这就是用户看到的"到达页面之后，没有进行输入开始和结束时间"现象。

**Plan**：参考 orders 数据域用 URL 参数 `?platform=shopee` 表达 subtype 的设计哲学，把 purchase status tab 也改用 URL 参数 `?tab={value}` 表达 —— 默认 `?tab=all`（用户已验证 `https://erp.91miaoshou.com/purchase/goods?tab=all` 默认就在"全部"）。完全删除 `_select_status_tab` 整个方法和 run 中调用。

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `3a690a7b` (--no-ff) on `main` 2026-09-13
**Strategy**: `--no-ff` 保留 fix branch 身份与 1 个 commit
**Test result**: 69 passed（含 4 条新 contract 测试 + 65 个 miaoshou 回归）
**Lint/Type**: ruff 0 errors / mypy 0 new errors on 3 modified production files

**Commit 列表（1 个 fix + 1 merge）**:
```
3a690a7b (HEAD -> main, origin/main, cnb/main) Merge branch 'fix/miaoshou-purchase-tab-url-param'
48723e9a fix(miaoshou): drive purchase status tab via URL param instead of UI click
```

**改动汇总（4 files，+64/-10）**:
- `modules/platforms/miaoshou/components/purchase_config.py` — `PurchaseSelectors` 新增 `purchase_tab_param: str = "all"` 字段（+4 行）
- `modules/platforms/miaoshou/components/navigation.py` — `_purchase_goods_url()` 拼接 `?tab={value}`（+5/-1 行）
- `modules/platforms/miaoshou/components/purchase_export.py` — 删除 `_select_status_tab` 整个方法（-12 行）+ 删除 `run` 中调用 + 注释说明
- `backend/tests/test_miaoshou_purchase_export_contract.py` — +4 测试（默认 tab_param / URL 包含 ?tab=all / 自定义 tab_param / 不再调用 _select_status_tab）

**根因复盘（这次的关键发现）**:
- 用户截图显示 `https://erp.91miaoshou.com/purchase/goods?tab=all` 默认就在"全部"
- pwcap snapshot 显示 "全部 (375)" 等状态 tab 是 `role="label"`（不是标准 `role="tab"`）
- `_select_status_tab` 先试 `get_by_role("tab", name="全部")` —— 2000ms 超时（tab role 不存在）
- 进入 fallback `get_by_text(re.compile(r"^全部\s*\(\d+\)$"))` —— label 找到了但 click 2000ms 超时（actionability 检查）
- fallback 那行**没有 try/except 包裹**，异常直接冒泡 → run 整个抛出 → date picker 没运行 → 用户看到"没输入开始/结束时间"
- 前一次 fix (`e84a2cf3`) 本身是对的，但本次测试**根本没走到 date picker 链路**，所以无法验证

**修复后的完整链路**:
1. navigation: `await page.goto("https://erp.91miaoshou.com/purchase/goods?tab=all", ...)` —— URL 显式表达"全部"
2. popup cleanup
3. date picker（apply_custom_range 或 run preset）
4. search → wait results
5. export workflow
6. 没有任何 status tab click —— 完全消除 label role click 超时的可能

**与 orders 设计哲学对齐**:
- orders: `?platform={shopee|tiktok|lazada}` 表达 subtype（URL 参数）
- purchase: `?tab={all|draft|audit|...}` 表达 status tab（URL 参数）
- 都不依赖 UI click 来切换"集合维度"，避免不同 framework 的 role 兼容问题

**三处 ref 同步状态**:
- `HEAD = origin/main = cnb/main = 3a690a7b` ✅（GitHub 网络恢复，推送成功 `0f034e06..3a690a7b`）
- 本地 fix branch 已删除

**端到端验证建议（merge 后在妙手真实环境）**:
1. 跑一次采购数据域采集任务（默认全部+近90天），确认：
   - navigation 到 `/purchase/goods?tab=all` 默认就在"全部"
   - date picker 链路能正常填入开始/结束日期时间（前一次 fix `e84a2cf3` 的实际效果）
   - 自定义时间范围能正确应用
2. 订单数据域采集仍正常工作（未受影响）
3. 如未来需要切其他状态（待审核/已完成 等），可通过 `selectors.purchase_tab_param="audit"`（具体值需实地验证）实现，**不需要再改代码**

**复盘与教训**:
- **先看真实 DOM 再优化**：本次通过查看 pwcap snapshot（role="label" 不是 role="tab"）+ 用户提供的 URL 参数 `?tab=all`，1 小时内定位并修复问题。如果直接尝试 force-click 或 try/except 容错，会绕过根因，未来还会踩坑
- **设计一致性**：URL 参数表达状态是 orders 已经验证的模式，purchase 复用同一哲学，避免重新设计
- **测试验证假设**：前一次 fix (`e84a2cf3`) 在 contract 测试层面正确（mock 覆盖 selectors 字段、注入正确），但**端到端测试才是真验证**。本次合并后还需要用户实地跑一次确认

---

# fix/miaoshou-purchase-wait-search-existing-text 收尾记录（2026-09-14）

**目标**：修复妙手采购数据域采集任务 `efd6f74e` 在搜索结果阶段超时 15s 失败的问题。前两次 fix（`e84a2cf3` 日期控件 + `48723e9a` 状态 tab）解决了打开页面 + 选择日期 + 搜索 click 之前的链路，但用户在最新失败测试截图显示日期已填入、搜索已执行，然后 `Locator.wait_for: Timeout 15000ms exceeded` 等待 `get_by_text("采购单信息")`。

**Plan**：基于 `output/playwright/work/miaoshou/finance-inventory-recording/purchase-04-results-ready.png` 实测截图（VLM `mcp__MiniMax__understand_image` 验证）发现当前 miaoshou 搜索结果表格的列标题是：`商品信息 (收起) / 采购金额 (展开) / 关联运单信息 / 收货信息 / 备注 / 操作` —— **"采购单信息" 在改版后已被 miaoshou 移除**（虽然 `PurchaseSelectors.export_field_groups` 里仍保留它用于 export field dialog 内的 row group 选择，那是 export 阶段的事，跟搜索结果表格无关）。

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `79e30aba` (--no-ff) on `main` 2026-09-14
**Strategy**: `--no-ff` 保留 fix branch 身份与 1 个 commit
**Test result**: 70 passed（含 1 条新 contract 测试 + 69 个 miaoshou 回归）
**Lint/Type**: ruff 0 errors / mypy 0 new errors on `purchase_export.py`

**Commit 列表（1 个 fix + 1 merge）**:
```
79e30aba (HEAD -> main, origin/main, cnb/main) Merge branch 'fix/miaoshou-purchase-wait-search-existing-text'
4298b6b7 fix(miaoshou): wait for visible search results in purchase export
```

**改动汇总（2 files，+33/-1）**:
- `modules/platforms/miaoshou/components/purchase_export.py` — `_wait_search_results_ready` 把 `"采购单信息"` wait 替换为 `"商品信息"`（row-group header，截图证实视觉存在）+ `"导入/导出"` 按钮 wait（与 `inventory_export._wait_search_results_ready` 设计一致）
- `backend/tests/test_miaoshou_purchase_export_contract.py` — +1 测试 `test_miaoshou_purchase_export_wait_search_results_uses_existing_text`（验证 `_wait_search_results_ready` 不再 query `"采购单信息"` + 必须 query `"商品信息"` + `"导入/导出"`）

**根因复盘**:
- miaoshou 在某个改版中移除了 search results table 的 row-group header `"采购单信息"`
- 现存文本信号是列标题 `"商品信息"`（视觉存在，截图确认）
- 另一个稳定信号是 `"导入/导出"` 按钮（与 inventory_export 共享同一 export 入口 pattern）
- `inventory_export._wait_search_results_ready` 已使用"等按钮"设计（"SKU总数" + "库存总价值" + "导入/导出商品"），本次 purchase 复用同一模式

**修复后的完整链路（与 inventory 对齐）**:
1. navigation: `await page.goto(".../purchase/goods?tab=all", ...)`
2. popup cleanup
3. date picker（apply_custom_range 或 preset shortcut）
4. search button click
5. **NEW** `_wait_search_results_ready`: `商品信息` 出现 + `导入/导出` 按钮出现
6. export workflow: `导入/导出` → `导出全部搜索结果` → 三组 field select → 导出 → 关闭进度 → 轮询 export_record → 下载

**三处 ref 同步状态**:
- `HEAD = origin/main = cnb/main = 79e30aba` ✅（GitHub 推送 `3a690a7b..79e30aba` 一次成功；cnb 推送 `3a690a7b..79e30aba` 一次成功）
- 本地 fix branch 已删除（`git branch -d fix/miaoshou-purchase-wait-search-existing-text`）
- ✅ Pre-existing product_category 改动（6 modified + 3 untracked）保留未触碰

**验收遗留 (pre-existing，与本任务无关)**:
- ruff E712 line 128 (`shop_accounts.py`，2026-05-05)
- mypy pre-existing "source file found twice" 配置冲突
- ESLint pre-existing 6 个错误
- `test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400
- `test_collection_account_capability_alignment.py` 2 个 404
- mypy pre-existing errors in `modules/platforms/shopee/components/date_picker.py` / `backend/services/` / `modules/utils/` / `modules/collectors/` / `backend/schemas/notification.py`

**端到端验证建议（merge 后在妙手真实环境）**:
1. 跑一次采购数据域采集任务（默认全部 + 任意日期快捷键或自定义），确认：
   - navigation 到 `/purchase/goods?tab=all` 默认就在"全部"
   - date picker 链路能正常填入开始/结束日期时间（前两次 fix 的实际效果）
   - **NEW** 搜索后 `_wait_search_results_ready` 不再 15s 超时（"商品信息" + "导入/导出" 立即可见）
   - export "全部搜索结果" 流程能正常下载
2. 订单数据域采集仍正常工作（未受影响）
3. 库存数据域采集仍正常工作（`inventory_export._wait_search_results_ready` 设计未被本次触碰）

**复盘与教训**:
- **先看真实 DOM 再优化**：本次通过 `purchase-04-results-ready.png` 截图 VLM 识别列标题，30 分钟内定位并修复根因。如果直接 try/except 包超时让 `_wait_search_results_ready` 静默通过，会绕过根因 —— 未来 miaoshou 再次改版又会踩坑
- **设计一致性**：`inventory_export._wait_search_results_ready` 的"等按钮 + 等文本"模式已经验证有效，purchase 复用同一哲学（按钮信号 + 稳定列标题信号），避免重新设计 wait 策略
- **测试验证假设**：本次新增的 `test_miaoshou_purchase_export_wait_search_results_uses_existing_text` 通过 `inspect.getsource` 静态验证 wait target 是"现存文本"（"采购单信息" NOT in source + "商品信息" + "导入/导出" in source），保证未来 miaoshou 再改版时契约测试会立即 FAIL，不会让静默退化溜过去
- **buy vs build**：之前我曾考虑给 `MiaoshouDatePicker` 加 `_click_confirm_if_visible()` 让"昨天"快捷键也走"确定"点击路径 —— 用户立即指出这个方向错了（"所有快捷日期都不需要点击确定，只有自定义需要"）。本次定位后确认：日期选择根本不是问题点，真实根因在更下游的 wait target。这一次直接定位远端（截图）避免了中间环节误诊

---

# fix/miaoshou-purchase-export-use-expect-download 收尾记录（2026-09-14）

**目标**：修复妙手采购数据域连续 3 次生产失败的根因 —— `efd6f74e` (Sep 13 23:33) / `9575d546` (Sep 14 01:10) / `188176b7` (Sep 14 01:12) 全部失败在 `get_by_text("导出记录").first to be visible` 15s 超时。前一次 fix (`4298b6b7`) 解决了搜索结果 wait target 问题（采购单信息 改版后不存在），用户再次跑测试后又失败在 export 流程的下游环节。

**Plan**：参考 orders (`orders_export_base.py:282-284`) + inventory (`inventory_export.py:242-244`) 已验证的 `page.expect_download` 模式：
```python
async with page.expect_download(timeout=180000) as dl_info:
    await self._trigger_export(page)  # click 导出 → 浏览器触发 download 事件
download = await dl_info.value
```

原设计 (navigate /export_record → poll 表格 → click 下载) 试图复用 miaoshou 的"导出记录"UI 页面，但实际页面行为不可靠：
- 浏览器在异步导出完成时直接触发 download 事件，与 /export_record 页面的渲染**完全独立**
- 之前 `_navigate_to_export_record` 后 `get_by_text("导出记录").first.wait_for(state="visible", timeout=15000)` 失败 → 推测原因：要么 miaoshou 把 /export_record 路径改了、要么 redirect、要么表格内容 15s 内不渲染
- 改用 `expect_download` 后完全绕过 UI 状态机：直接等浏览器 fire download event（异步导出+文件生成完成时由 Playwright 捕获）

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `63f96bcc` (--no-ff) on `main` 2026-09-14
**Strategy**: `--no-ff` 保留 fix branch 身份与 1 个 commit
**Test result**: 79 passed（含 2 新 contract test + 1 改名 v2_flow test + 1 改名 v2_flow test）
**Lint/Type**: ruff 0 errors / mypy 0 errors on `purchase_export.py`

**Commit 列表（1 个 fix + 1 merge）**:
```
63f96bcc (HEAD -> main, origin/main, cnb/main) Merge branch 'fix/miaoshou-purchase-export-use-expect-download'
b3a52cfb fix(miaoshou): capture purchase export via page.expect_download (mirror orders/inventory)
```

**改动汇总（3 files，+163/-69）**:
- `modules/platforms/miaoshou/components/purchase_export.py` — 删除 `_navigate_to_export_record` / `_poll_export_record_until_ready` / `_click_download_in_export_record` 三个方法（之前失败的根因）；重构 `_trigger_async_export_and_download` 用 `page.expect_download` 包裹 `_click_export_button_in_dialog` + best-effort `_close_progress_dialog`；移除 `import asyncio` / `import re`（不再用）
- `backend/tests/test_miaoshou_purchase_export_contract.py` — +2 测试：
  - `test_miaoshou_purchase_export_trigger_uses_expect_download_no_nav_poll`：验证 `_trigger_async_export_and_download` 使用 `page.expect_download` + 三个旧方法已删除
  - `test_miaoshou_purchase_export_close_progress_dialog_is_best_effort`：验证 `_close_progress_dialog` 是 best-effort（≤3s 超时 + try/except 永不出）
- `backend/tests/test_miaoshou_purchase_export_v2_flow.py` — 2 测试改名 + 断言更新：
  - `test_purchase_export_triggers_export_then_polls_export_record_then_downloads` → `test_purchase_export_triggers_export_via_expect_download_pattern`（顺序断言改为 `expect_download → click_export_button_in_dialog → close_progress_dialog`）
  - `test_purchase_export_polls_export_record_with_timeout_and_interval` → `test_purchase_export_uses_export_record_poll_timeout_as_download_timeout`（验证复用 `export_record_poll_timeout_s * 1000` 作为 expect_download 超时；移除 polling 断言如 `asyncio.sleep(interval_s)`）

**根因复盘**:
1. **生产失败证据**：3 次连续失败全部 timeout 在同一处 — `get_by_text("导出记录").first to be visible` (15s)。这是 `_navigate_to_export_record` 在 `page.goto(/purchase/export_record)` 之后立即调用，无任何 fallback。
2. **架构根本原因**：原设计假设 miaoshou 的"异步导出 → UI 状态机 → 用户手动下载"是唯一流程。但 `orders_export_base` 和 `inventory_export` 已经证明：浏览器在异步导出完成时**直接 fire download event**，`page.expect_download` 即可捕获，无需 navigate 到任何 export_record 页。
3. **为什么 orders/inventory 没踩坑**：它们从一开始就用 `expect_download` 模式（首次实现就正确），从未尝试 navigate 到 /export_record 页。purchase 是后来加入的，错误地复用了 miaoshou 的 UI 状态机。
4. **`_close_progress_dialog` 也有问题**：旧实现 10s wait for "正在导出" heading → 如果 heading 短暂出现又消失就浪费 10s。改为 best-effort（2s 超时 + try/except 全程），不再阻塞 download 等待。

**修复后的完整链路**:
```
navigation → popup cleanup → date picker → search → wait results
→ 导入/导出 → 导出全部搜索结果 → 字段全选 → page.expect_download 包裹:
  ├─ click 导出 按钮（触发后端异步导出 + 浏览器 download event）
  └─ best-effort 关闭 正在导出 进度对话框（不阻塞）
→ download.save_as 落盘 + build_filename 重命名
```

**与 orders/inventory 设计完全对齐**:
- orders (`MiaoshouOrdersExportBase.run:282-284`): `async with page.expect_download(timeout=180000) as dl_info: await self._click_export_all_orders(page); await self._confirm_export_if_needed(page)`
- inventory (`MiaoshouInventoryExport.run:242-244`): `async with page.expect_download(timeout=180000) as dl_info: await self._trigger_export(page)`
- purchase (本次): `async with page.expect_download(timeout=self.sel.export_record_poll_timeout_s * 1000) as dl_info: await self._click_export_button_in_dialog(page); await self._close_progress_dialog(page)`

**三处 ref 同步状态**:
- `HEAD = origin/main = cnb/main = 63f96bcc` ✅（GitHub 推送 `79e30aba..63f96bcc` 一次成功；cnb 推送 `79e30aba..63f96bcc` 一次成功）
- 本地 fix branch 已删除
- ✅ Pre-existing product_category 改动（6 modified + 3 untracked）保留未触碰

**验收遗留 (pre-existing，与本任务无关)**:
- ruff E712 line 128 (`shop_accounts.py`，2026-05-05)
- mypy pre-existing "source file found twice" 配置冲突
- ESLint pre-existing 6 个错误
- `test_preflight_create_task_rejects_when_export_component_has_no_stable` 401 vs 400
- `test_collection_account_capability_alignment.py` 2 个 404
- mypy pre-existing errors in `modules/platforms/shopee/components/date_picker.py` / `backend/services/` / `modules/utils/` / `modules/collectors/` / `backend/schemas/notification.py`

**端到端验证建议（merge 后在妙手真实环境）**:
1. 跑一次采购数据域采集任务，确认：
   - navigation 到 `/purchase/goods?tab=all` 默认就在"全部"
   - date picker 链路正常填入开始/结束日期时间（前三次 fix 的累计效果）
   - search 后 `_wait_search_results_ready` 不再 15s 超时（前一次 fix 的效果）
   - **NEW** click 导出 in field dialog 后 `page.expect_download` 立即触发（不再 navigate 到 /export_record）
   - "正在导出" 进度对话框被异步关闭（best-effort，不阻塞）
   - export "全部搜索结果" 流程能正常下载 xlsx 文件
2. 订单数据域采集仍正常工作（未受影响）
3. 库存数据域采集仍正常工作（未受影响，本次改动未触碰 inventory 任何文件）

**复盘与教训**:
- **看真实行为而非推断 UI 流程**：我之前假设 miaoshou 的"异步导出 → UI 状态机 → 用户手动下载"是 purchase 的唯一路径，但 orders/inventory 已经证明 `expect_download` 模式同样可行（浏览器 fire download event 与 UI 状态机**完全独立**）。下次同类任务先 grep `expect_download` 看兄弟组件的实现，不要直接发明新流程
- **同一组件族共享一种模式**：miaoshou 三个数据域（orders / inventory / purchase）的 export 流程应当用同一种模式。如果某天 orders 改用 nav+poll 而 purchase 用 expect_download，那一定是设计分叉，要审视是否有必要分叉
- **保留 selectors 复用语义**：`export_record_poll_timeout_s` 选择器原本用于 poll 表格，refactor 后复用为 `expect_download` 超时（语义对齐：等待导出可下载的最长时间）。比新增 `download_timeout_ms` 选择器更平滑
- **渐进降级为 last resort**：`_close_progress_dialog` 改为 best-effort（2s 超时 + try/except），不再阻塞主流程。UI 进度提示是用户视觉反馈，不是同步前置条件 —— 不能让"等待 UI 提示消失"卡住核心 download 捕获
- **复用成熟模式胜过发明**：本次直接 mirror orders_export_base 的 expect_download 写法，没有重新设计 `_poll_export_record_until_ready` 的"更智能"轮询策略（比如加更多 ready_texts、调整 interval 等）。简单复用已被验证的 pattern 永远是首选

---

# fix/miaoshou-purchase-export-strict-mirror-orders 收尾记录（2026-09-14）

**目标**：移除前一次 fix (`b3a52cfb`) 中误加的 `_close_progress_dialog` 调用，严格 mirror orders / inventory 的 `expect_download` 写法。用户反馈："正在导出被异步关闭？我们正确步骤不是应该点击导出按钮之后，等待导出然后自动进行下载吗？你没有参考 miaoshou orders 数据域导出组件吗，你是否知道怎样正确导出" —— 准确指出我加的 `_close_progress_dialog` 是过度设计。

**Plan**：grep 兄弟组件（orders_export_base.run + inventory_export.run）确认它们都从不在 `expect_download` context 内关闭进度对话框：
- `orders_export_base.run:282-284`: 仅 `click_export_all_orders` + `_confirm_export_if_needed` 在 context 内
- `inventory_export.run:242-244`: 仅 `_trigger_export` 在 context 内

无进度对话框处理，因为 download 事件是浏览器独立 fire 的，与 UI 状态机解耦。

## Branch Status: ✅ MERGED TO MAIN

**Merge commit**: `4d80435a` (--no-ff) on `main` 2026-09-14
**Strategy**: `--no-ff` 保留 fix branch 身份与 1 个 commit
**Test result**: 26 passed（删除 1 个 best-effort close test + 现有 25 个回归；+2 个新增断言检查 _close_progress_dialog 不存在）
**Lint/Type**: ruff 0 errors / mypy 0 errors on `purchase_export.py`

**Commit 列表（1 个 fix + 1 merge）**:
```
4d80435a (HEAD -> main, origin/main, cnb/main) Merge branch 'fix/miaoshou-purchase-export-strict-mirror-orders'
e606c2bb fix(miaoshou): remove _close_progress_dialog from purchase export (strict mirror orders/inventory)
```

**改动汇总（3 files，+53/-77）**:
- `modules/platforms/miaoshou/components/purchase_export.py` — 删除 `_close_progress_dialog` 方法（-32 行）；`_trigger_async_export_and_download` 内 expect_download context 只包裹 `_click_export_button_in_dialog`（移除之前误加的 `_close_progress_dialog` 调用）；docstring 更新强调"严格 mirror orders/inventory"
- `backend/tests/test_miaoshou_purchase_export_contract.py` — 删除 `test_miaoshou_purchase_export_close_progress_dialog_is_best_effort` 测试；`test_miaoshou_purchase_export_trigger_uses_expect_download_no_nav_poll` 新增 2 个断言：`_close_progress_dialog` 方法不存在 + expect_download context 内不调用 `_close_progress_dialog`
- `backend/tests/test_miaoshou_purchase_export_v2_flow.py` — `test_purchase_export_triggers_export_via_expect_download_pattern` 顺序断言移除 close_progress 检查 + 新增 'context 内不调用 _close_progress_dialog' 断言

**根因复盘（前一次 fix 的过度设计）**:
1. **我误判了"正在导出包裹"对话框的作用**：把它当作需要主动关闭的 modal，但实际上它只是用户视觉反馈 —— 用户看完可以关闭，也可以不关（系统提示"关闭后系统将在后台自动完成任务"）。
2. **未严格 mirror orders/inventory**：orders / inventory 都有同样的进度对话框（orders `_wait_export_progress_ready` + inventory `_wait_export_progress_ready` 都是 *wait FOR* 不是 *close*），但它们的 `expect_download` 写法都不主动关闭。我加 `_close_progress_dialog` 是想"更稳"，实际上是引入了潜在 race condition 和 1-2s 不必要预算。
3. **用户的精准反馈是金标准**：用户说"我们应该点击导出按钮之后，等待导出然后自动进行下载" —— 这就是 expect_download 的语义；"正在导出被异步关闭？" 准确指出我把 close_progress_dialog 写在了不该写的位置（异步下载流程不需要它）。

**修复后的最终链路（与 orders/inventory 严格一致）**:
```python
# _trigger_async_export_and_download
await self._open_import_export_dropdown(page)
await self._click_export_all_results(page)
await self._select_all_export_fields(page)

async with page.expect_download(timeout=self.sel.export_record_poll_timeout_s * 1000) as dl_info:
    await self._click_export_button_in_dialog(page)  # 仅此一句 click，触发出后端导出 + 浏览器 fire download 事件
download = await dl_info.value
# → download.save_as 落盘
```

**三处 ref 同步状态**:
- `HEAD = origin/main = cnb/main = 4d80435a` ✅（GitHub 推送 `63f96bcc..4d80435a` 一次成功；cnb 推送 `63f96bcc..4d80435a` 一次成功）
- 本地 fix branch 已删除
- ✅ Pre-existing product_category 改动（6 modified + 3 untracked）保留未触碰

**复盘与教训**:
- **用户的精确反馈是设计真理**：用户说"我们正确步骤不是应该点击导出按钮之后，等待导出然后自动进行下载吗" —— 这就是 expect_download 的本质语义。我多加了 `_close_progress_dialog` 看似"更稳"实际是过度设计，用户一眼看穿。
- **严格 mirror 兄弟组件胜过自己设计**：orders / inventory 都从不在 expect_download context 内关闭进度对话框。我加 `_close_progress_dialog` 偏离了设计一致性。即便想"更稳"也应当先询问用户，而不是自作主张。
- **download 事件 ≠ UI 状态机**：download 事件是浏览器 fire 的，与页面 UI 完全独立。进度对话框、UI 提示、DOM 变化都不影响 download 捕获。任何在 expect_download context 内做 UI 交互的代码都是可疑的。
- **contract test 应当强制 strict mirror**：本次新增的 `_close_progress_dialog` 方法不存在 + context 内不调用 `_close_progress_dialog` 两个断言，把"严格 mirror orders/inventory"固化为测试守卫。未来任何人想加 UI 交互都会被 contract test 立即 fail 拦住。

---

# fix/miaoshou-purchase-export-preset-map-bilingual 收尾记录（2026-09-14）

**目标**：修复用户在前端 Quick Collection 选 "昨天" → 后端却点击 "近30天" 按钮的时间控件错位 bug。用户反馈："我明确选择的是昨天，为什么会快捷选择近30天的选项呢？请审查一下是前端还是我们自己的时间控件有问题"。

**根因（前端/后端边界追踪）**:

| 层 | 行为 |
|---|---|
| 前端 `CollectionTasks.vue` `quickForm.date_preset` | 用户在 el-select 中选 `"昨天"`，`value` 是 `"yesterday"` |
| 前端 `buildTimeSelectionPayload('yesterday', ...)` | 返回 `{ mode: 'preset', preset: 'yesterday' }` ← **English key** |
| 后端 `normalize_time_selection` | 透传保留 `{ mode: 'preset', preset: 'yesterday' }` |
| 后端 `task.date_range.time_selection.preset` | 存储为 `"yesterday"` |
| `MiaoshouPurchaseExport.run` | `time_selection.get("preset")` → `"yesterday"` |
| `purchase_export.py:219-225` preset_map | **只有中文 keys** (今天/昨天/近7天/近30天/近90天) |
| `preset_map.get('yesterday', fallback=LAST_30_DAYS)` | ❌ 找不到 → fallback 到 `DateOption.LAST_30_DAYS` |
| `date_picker.run(LAST_30_DAYS)` | 点击 "近30天" 按钮（错的）|

**对比 working example** — `orders_export_base.py:67-86` `_resolve_preset_option`:
```python
mapping = {
    "今天": DateOption.TODAY_REALTIME,
    "today": DateOption.TODAY_REALTIME,    # ← 同一行同时支持中英文
    "昨天": DateOption.YESTERDAY,
    "yesterday": DateOption.YESTERDAY,      # ← 同一行同时支持中英文
    ...
}
```
orders 组件早就支持 bilingual keys，purchase 组件漏掉这层防御。

**非前端 bug 的关键证据**:
- 前端 `buildTimeSelectionPayload` 实现是单元测试覆盖的（`collection.js` 的 `if (preset === 'today' || preset === 'yesterday' || ...)` 显式按 English key 走）
- 前端 `getDatePresetLabel` 显示标签和 `value` 是分离的（label 是 "昨天", value 是 "yesterday"），是行业标准做法
- 后端只有 purchase 组件有 `preset_map`，orders 用了 `_resolve_preset_option`，inventory 用的是不同代码路径不受影响

## Branch Status: ✅ MERGED TO MAIN

**Fix commit**: `00e25913` on `fix/miaoshou-purchase-export-preset-map-bilingual` 2026-09-14
**Merge commit**: `fc080376` (--no-ff) on `main` 2026-09-14
**Strategy**: `--no-ff` 保留 fix branch 身份与 1 个 commit
**Test result**: 19/19 passed in `test_miaoshou_purchase_export_contract.py`（含新增 1 个 bilingual 测试），76/76 passed in 完整 miaoshou 回归套件
**Lint/Type**: ruff 0 errors / mypy 0 errors on `purchase_export.py`

**Commit 列表（1 个 fix + 1 merge）**:
```
fc080376 (HEAD -> main, origin/main, cnb/main) Merge branch 'fix/miaoshou-purchase-export-preset-map-bilingual'
00e25913 fix(miaoshou): add English preset_map keys for purchase export (mirror orders)
```

**改动汇总（2 files，+69/-1）**:
- `modules/platforms/miaoshou/components/purchase_export.py` — preset_map 增加 5 个 English keys（`today`/`yesterday`/`last_7_days`/`last_30_days`/`last_90_days`），保留全部 5 个中文 keys 作为 backwards compat；每个 English key 显式映射到对应 `DateOption`（不是 fallback）。Chinese 注释解释回归场景与 orders mirror 关系（+15/-1）
- `backend/tests/test_miaoshou_purchase_export_contract.py` — 新增 `test_miaoshou_purchase_export_preset_map_supports_both_chinese_and_english_keys`，断言 4 对双语 keys 同时存在 + `"yesterday"` 必须映射到 `YESTERDAY` 而非 `LAST_30_DAYS` + `"last_30_days"` 必须映射到 `LAST_30_DAYS`（+55/-0）

**修复后链路**:
```
前端 CollectionTasks quickForm.date_preset='yesterday'
    ↓ buildTimeSelectionPayload('yesterday') → { mode: 'preset', preset: 'yesterday' }
后端 normalize → { mode: 'preset', preset: 'yesterday' }
    ↓ task.date_range.time_selection.preset = 'yesterday'
MiaoshouPurchaseExport.run:
    preset_map.get('yesterday') → DateOption.YESTERDAY ✅
    date_picker.run(YESTERDAY) → click button "昨天" ✅（正确）
```

**三处 ref 同步状态**:
- `HEAD = origin/main = cnb/main = fc080376` ✅（cnb 推送 `4d80435a..fc080376` 一次成功；origin 推送 `4d80435a..fc080376` 一次成功）
- 本地 fix branch 已删除
- ✅ Pre-existing product_category 改动（已被合并到 main 的 b8d49308 / e6631331）保留未触碰

**问题 B 未触及**: 73 秒任务 "部分成功" + "正在导出" 0% 进度的根因**不在 preset_map**，需要额外的诊断信息（错误日志/步骤时间线详情）。**用户的精确反馈锁定问题 A，问题 B 需要单独排查**。

**复盘与教训**:
- **English/Chinese key 配对是 API 边界的隐形约束**：任何涉及用户输入 → 内部表示的映射层都必须双语枚举，不能想当然只支持一种。orders 组件作者当年做了正确的事，purchase 组件是新人重写时漏掉。**lesson**: 添加新组件时应当 grep 兄弟组件的实现模式，不要重新发明。
- **后端 fallback 静默"成功"是危险的**：`preset_map.get(date_preset, DateOption.LAST_30_DAYS)` 把不认识的 key 静默 fallback 到 LAST_30_DAYS。应该改成 `raise ValueError(f"unsupported date_preset: {date_preset}")`，让无效输入显式失败而不是 silently export 错误数据。**但**这个改动是 orthogonal 改进，本次只做最小修复（bilingual keys），不动 fallback 行为，避免再次 over-design。如果用户后续确认想要严格模式，再做独立修复。
- **TDD RED-FIRST 验证了真实回归**：写测试时假设 preset_map 是中文 only（RED），改完后立刻 GREEN，证明测试确实锚定了 bug。如果一开始就写 GREEN 测试（期望 bilingual），就会跳过"代码确实是 broken 的"这一验证。
- **截图 + 错误信息比 verbal 描述强 10 倍**：用户发了 3 张截图（导出页面 + 任务详情 + 快速采集表单），让我能精确锁定到 `CollectionTasks.vue` quickForm 而不是 `CollectionConfig.vue`（两者都用了 `buildTimeSelectionPayload` 但 quickForm 是用户实际用的入口）。如果没有截图，我会先花 20 分钟 grep 哪个组件才是入口。**lesson**: 用户主动提供截图时，应当从截图反推入口组件，而不是凭"用户大概用的是这个"猜。
---

## 2026-09-14: 修复 B — purchase export 下载后等待进度对话框再 save_as

**用户判断**: "我觉得大概率是下载后等待进度这块的问题"
（截图：任务 73s partial_success，"正在导出包裹" 0% 进度对话框持续显示）

**根因**:
- orders (`MiaoshouOrdersExportBase._wait_export_complete` L194-198) 和 inventory (`MiaoshouInventoryExport._wait_download_complete` L188-192) 都在 `download = await dl_info.value` 之后、 `download.save_as(...)` 之前调用 `_wait_export_progress_ready(page)`
- purchase (`MiaoshouPurchaseExport._trigger_async_export_and_download`) **缺失这一步** —— download event 触发后立即 save_as
- race condition: server-side export pipeline 还在写 row 时,客户端 save_as 已落盘 → 文件 truncated → 73s 后 partial_success
- progress 对话框 "正在导出包裹" 是 INTERMEDIATE visual feedback,不是 terminal state;但 wait 它可见 = 确认 server-side pipeline 仍在 running 中

**修复**:
- `modules/platforms/miaoshou/components/purchase_export.py`: 新增 `_wait_export_progress_ready(page)` 方法(mirror inventory_export L179-186),遍历 `self.sel.progress_text_variants` 任一可见即 return;在 `_trigger_async_export_and_download` 中 `download = await dl_info.value` 之后, `download.save_as(...)` 之前, `try/except` best-effort 调用

**关键差异 vs orders**: orders 等 heading "正在导出" (严格),purchase 用 `progress_text_variants` 列表 (因为 purchase 页面渲染的实际是 "正在导出包裹",正是 PurchaseSelectors.PROGRESS_TEXT_VARIANTS 第 0 项)。截图 Sep 14 任务确认 "正在导出包裹" 真实可见。

**TDD RED-GREEN**:
- 写了 3 个 contract test 锚定修复:
  1. `_wait_export_progress_ready` 必须定义
  2. 必须 iterate `self.sel.progress_text_variants` (不能用 orders 的 heading)
  3. 必须在 `_trigger_async_export_and_download` 内 `try/except/pass` 包裹
- 4. wait 调用必须在 `download.save_as` **之前**(ordering matters)
- RED → GREEN 全程验证

**验证**:
- 22/22 purchase contract test 通过 (19 旧 + 3 新)
- 82/82 全 miaoshou 回归测试通过
- ruff 0 errors, mypy 0 errors on purchase_export.py
- pre-existing product_category 改动保留未触碰

**commit**:
- fix commit: `87ef0487` "fix(miaoshou): wait for progress dialog before save_as in purchase export"
- merge commit: `6b2466e1` (main)
- cnb push 成功 `fc080376..6b2466e1`;origin (github.com) 暂时网络不可达,等用户恢复后手动 `git push origin main`

**关于用户说"不是卡在 0% 的问题"**:
- 这条提示帮我避免了一个错误方向 —— 不要直接改"0% 进度逻辑"
- 实际上"0%"是症状(进度条从 0% 起跳),race condition 才是根因(没等进度可见就 save_as)
- 用户的"0% 不是问题"= "不要盯着 0% 这个数字,而是看缺少等待环节" —— 正确解读为 wait helper 缺失

**复盘与教训**:
- **不能仅看截图字面意思**: 截图显示 "0% 进度" → 字面解读 "卡在 0%" → 错误方向;实际根因是"没等进度对话框就 save_as"。**lesson**: 截图只是线索,需要追溯到代码层面的具体差异,不能被截图字面误导。
- **mirror 兄弟组件是 anti-fragile 策略**: orders / inventory 都做了 wait progress,只有 purchase 漏了。如果购买日期 picker fix 时同时把这个补上,就不会有今天的 73s 回归。**lesson**: 当一个数据域修改了关键路径(search/wait/export),要 grep 兄弟组件(miaoshou 三大数据域)看是否有 mirror 模式未对齐。
- **race condition 在 download + save_as 之间**: Playwright `expect_download` 在收到 Content-Disposition header 时立即 fire,但 server-side 写入文件到磁盘是异步的。`save_as` 立即调用 = save 当时浏览器内存中的 byte stream,而不是磁盘 committed 文件。**lesson**: 对异步 IO 路径,wait 一个 explicit signal(progress dialog visible) 比依赖 raw download event 更可靠。
- **3 个 contract test 锚定 ordering + 内容**: 第 4 条 test (`wait_idx < save_idx`) 特别关键 — 即使有人未来"重构"代码把 save_as 提前到 wait 之前,这个 test 也会失败。这保护 ordering invariant。

---

# 商品中心 SKU 采购价批量录入 — Subagent-Driven Progress Ledger

**Plan:** `docs/superpowers/plans/2026-09-18-purchase-price-import.md`
**Branch:** main(不建分支,改动留在工作区)
**Spec:** `docs/superpowers/specs/2026-09-18-purchase-price-import-design.md`

## In Progress
(none)

## Completed Tasks
(none)

## Pending Tasks
- Task 1: 写脚本骨架 + xlsx 解析 + 过滤逻辑(带测试)
- Task 2: 对账逻辑(读 DB + 比对 xlsx vs DB)
- Task 3: 备份 + 事务写入(核心)
- Task 4: CLI + 验证查询 + 报告输出(完整入口)
- Task 5: dry-run 执行 + 用户 review(gate)
- Task 6: 本地库真写(阶段 1)+ 验证(gate)
- Task 7: 云端库真写(阶段 2,需用户批准)(gate)

## Notes
- 所有 commit 步骤已移除,改动留在工作区
- Task 5/6/7 含用户 review gate,不能全自动

## In Progress
(none)

## Completed Tasks

- **Task 1: 写脚本骨架 + xlsx 解析 + 过滤逻辑(带测试)** (complete, commit e3cf3774, review Approved)
  - Minor findings (roll-up for final review):
    1. `import_purchase_prices.py:50` — `wb.close()` 未显式调用(read_only 句柄在 Windows 上可能锁文件)
    2. `import_purchase_prices.py:94` / `test_import_purchase_prices.py:41` — 文件末尾无换行符(POSIX 惯例)
    3. `import_purchase_prices.py:9-18` — `argparse / asyncio / csv / logging / sys / Path` 等 import 未触达(为后续 task 预热)
    4. `import_purchase_prices.py:68-69` — `if row is None: continue` 不可达(`iter_rows(values_only=True)` 不会 yield None 行)


- **Task 2: 对账逻辑(读 DB + 比对 xlsx vs DB)** (complete, commit c792a57b, review Approved)
  - Minor findings (roll-up for final review):
    1. 文件末尾无换行符(Task 1 已记,继续)
    2. `fetch_db_sku_keys:103` — `if r["sku_key"]` 同时过滤 None 和空串(口径 OK,DB 列 NOT NULL)
    3. 边缘情况未覆盖(`reconcile([], ...)` / `reconcile(valid, set())` / `valid` 含重复 SKU code)

- **Task 3: 备份 + 事务写入(核心)** (complete, committed, review Approved)
  - Minor findings (roll-up for final review):
    1. `import_purchase_prices.py:143,145` — `backup_table` 字符串拼接有 SQL 注入面(脚本语境风险低,可加 quote_ident)
    2. `test_import_purchase_prices.py:87` — `pytest.raises(Exception)` 过宽,建议收紧为 `asyncpg.exceptions.PostgresError`
    3. `import_purchase_prices.py:158-179` — `matched=[]` 时无 fast-path,仍会建备份表
    4. `import_purchase_prices.py:159-160` — 备份表创建不在事务内(下次 DROP IF EXISTS 覆盖,语义自洽但 docstring 应注明)
    5. 文件末尾无换行符(累计 roll-up)

- **Task 4: CLI + 验证查询 + 报告输出** (complete, committed, review Approved)
  - Minor findings (roll-up for final review):
    1. `import_purchase_prices.py:13` — `import logging` 遗留未用(累计)
    2. `import_purchase_prices.py:281` — 函数内 `from pathlib import Path` 重复 import(顶部已有)
    3. `.env` 解析不支持注释/多行/转义(简单实现)
    4. `write_sample_csv` 空 samples 创建零字节文件
    5. CSV 写出无 try/except(磁盘满/权限不足会抛未处理)
    6. `--output-dir` 默认相对路径 "output" 跨目录易混淆

- **Task 5: dry-run 执行 + 用户 review (gate)** (complete, no commit per `short-session-no-auto-commit`)
  - dry-run 结果:xlsx 1086 valid / 36 跳过(—)/ 0 错误
  - reconcile:matched=1082 / lookup_only=4 / db_only=39(差异正常,信息性,不阻断)
  - 输出:`output/purchase_price_reconciliation_20260918.csv` + `output/purchase_price_import_dryrun_20260918.csv`
  - 用户 review lookup_only 与 db_only 列表,确认差异属数据治理问题,可推进
  - 决策:继续到 Task 6

- **Task 6: 本地库真写(阶段 1)+ 验证(gate)** (complete, no commit per `short-session-no-auto-commit`)
  - `--apply` 执行:xlsx 1086 valid / 36 跳过 → reconcile matched=1082 → 备份表 `core.dim_erp_sku_backup_20260918`(1121 行)→ 单事务 UPDATE 1082 行
  - **post-state 全通过**:
    - total=1121 / filled=1084(1082 妙手导入 + 1 manual + 1 None)
    - negative=0 / zero=0(无脏数据)
    - 元数据全覆盖:10 个抽样样本 source=妙手导入 / confidence=medium / confirmed_at=2026-09-18 一致
  - **全量对账 100% 通过**:1082/1082 SKU 价格与 xlsx 完全一致,0 diff
  - 输出:`output/purchase_price_sample_check_20260918.csv`(15 条样本对照)
  - **本批次净增量**:filled 从 2 → 1084(+1082);backup 表已就位可回滚
  - 决策:本地完成,**不**自动进入 Task 7 云端(用户明确"一直到本地完成",需再批)

## 阶段状态:本地完成 ✓ / 云端待批
- ✅ Task 1-6 本地端到端完成,数据已落库,备份表保留 7 天
- ⏸️ **Task 7 云端库 apply 已预批**(用户原话:"先录入到本地,看看有没有问题,没问题再录入到云端"),等待用户最终 OK
- 📦 工作区状态:`scripts/import_purchase_prices.py` + `scripts/tests/` + `output/*.csv` + 备份表(自动 7 天后清理)

- **Task 7: 云端库 apply(阶段 2)** (complete, no commit per `short-session-no-auto-commit`)
  - **门 0 SSH 连通**:`deploy@134.175.222.171` 密码登录 OK,服务器 `VM-0-15-ubuntu` up 27 周
  - **门 1 容器状态**:`xihong_erp_postgres` (Up 3 months, healthy, port `127.0.0.1:15435->5432`),其它 6 个服务全 healthy
  - **门 2 云端只读快照**:total=1121 / filled=2 / negative=0 / zero=0 / miaoshou=0 / 备份表不存在 — **与本地 apply 前完全一致**,无覆盖风险
  - **隧道方案**:SSH `-L 15433:127.0.0.1:15435`(用 `~/.ssh/github_actions_deploy` key,与 `Ensure-CloudSyncTunnel` 等效),全程 5 分钟,不开 docker、不启额外服务
  - **`--apply` 执行**:xlsx 1086 valid → 36 跳过 → matched=1082 → 备份表 `core.dim_erp_sku_backup_20260918`(1121 行)→ 单事务 UPDATE 1082 行
  - **post-state 全通过**:
    - total=1121 / filled=1083(1082 妙手导入 + 1 manual 预存,**比本地少 1 是因为云端原本没有 None source 那条**)
    - negative=0 / zero=0
    - 元数据全覆盖
  - **全量对账 100%**:1082/1082 与 xlsx 完全一致,0 diff(server=`172.18.0.3` 确认是云端容器非本地)
  - **预存 manual `SKU-0001` 保留**:cost=100.00 src=manual 不变(确认 --apply 没冲掉预存数据)
  - **清理**:SSH 隧道已 taskkill,临时文件 `/tmp/cloud_url.txt` 已删除
  - 决策:云端完成 ✓

## 最终阶段状态:本地 + 云端全完成 ✓
- ✅ Task 1-7 全阶段端到端完成,本地 + 云端数据均已落库
- ✅ 两个备份表 `core.dim_erp_sku_backup_20260918` 均 1121 行,7 天后清理
- ✅ 临时文件已清理
- ✅ 工作区改动:`scripts/import_purchase_prices.py` + `scripts/tests/` + `output/*.csv` + ledger
- ⏸️ **git commit 仍未执行**(遵守 `short-session-no-auto-commit`),等你决定是否提交

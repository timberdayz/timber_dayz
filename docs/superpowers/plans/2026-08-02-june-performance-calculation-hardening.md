# June Performance Calculation Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 2026 年 6 月绩效计算链路的事务、数据完整性和前端反馈问题，使店铺绩效、个人绩效、提成和工资单在正式计算中保持一致，并能明确区分正式结果、观察结果和未就绪状态。

**Architecture:** 以 `POST /api/performance/scores/calculate` 作为月度计算编排入口，所有正式计算写入共享一个 `AsyncSession` 事务；只读兼容查询使用 savepoint 或无副作用 fallback，不得回滚外层事务。店铺目标、月度订单、利润基数和运营目标先经过就绪性判断；正式模式缺少必需口径时不生成任何下游收入结果，观察模式只保存可解释的店铺诊断结果。前端根据结构化状态展示“完成、部分/观察、阻断、完成但有锁定冲突”等结果。

**Tech Stack:** FastAPI, SQLAlchemy async `AsyncSession`, PostgreSQL, Pydantic, pytest/pytest-asyncio, Vue 3, Element Plus, Pinia, Vite, Node test runner.

---

**Implementation skills:** Use `@superpowers:test-driven-development` for each code task, `@superpowers:subagent-driven-development` when subagents are available (otherwise `@superpowers:executing-plans`), and `@superpowers:verification-before-completion` before declaring the work complete.

## 已确认的 2026-06 基线与问题

实现前必须保留以下事实作为验收基线，不要把本地当前残留的测试结果当作正确结果：

- 本地 6 月月粒度订单：Shopee 4034 行，TikTok 629 行；本地与云端 5、6 月订单 `data_hash` 集合一致。
- 6 月店铺目标分解覆盖 20 个店铺。
- 云端和本地都没有 6 月运营目标；不能在系统内伪造业务目标。
- 6 月利润基数已补齐 20 个店铺，汇总为：订单利润 19341.46，A 类运营成本 20000.00，利润基数 -658.54。
- 复现问题时接口返回 `upserts=20`，但 `c_class.performance_scores` 为 0；下游仍生成 4 条个人绩效、4 条提成和 7 条 draft 工资单。
- 根因是 `backend/services/hr_income_calculation_service.py` 的考勤 ORM 查询失败后调用 `await self.db.rollback()`，清掉了路由中已经 `flush` 的店铺绩效；后续 fallback 和下游服务又继续写入并提交。
- 另有 `EMP260005` 未关联用户账号的警告。该问题不应伪造账号，也不应悄悄吞掉；应作为结构化非阻断警告返回。

## 设计决策

1. 正式计算默认使用 `mode=formal`。销售、利润、运营三项正式口径未全部就绪时返回结构化未就绪结果，并且不写入个人绩效、提成或工资单。
2. 增加 `mode=observation` 供诊断使用。运营目标缺失时可以保存店铺观察结果，但必须标记 `ranking_pool=observation`、`calculation_status=partial`，不参与正式排名、系数、提成和工资单。
3. 负利润基数允许保存为快照，但可分配提成基数按 `max(profit_basis, 0)` 处理，不能产生正提成。
4. 已确认/已发放工资单的锁定冲突不是事务失败；正式计算完成后作为 `completed_with_warnings` 返回，并列出员工和变化字段。
5. 本地数据库不做备份、不作为事实源；6 月数据验收只验证本地覆盖后的结构、hash、数量和计算结果，云端仍是 B 类数据事实源。

### 状态字段 SSOT

- 顶层响应唯一状态字段为 `status`；唯一枚举为 `completed`、`completed_with_warnings`、`observation`、`not_ready`、`failed`。
- `readiness` 唯一承载 `formal_ready`、维度状态、`missing_dimensions` 和恢复建议；不得再从多个字符串字段推断是否正式。
- `PerformanceScore.score_details.summary` 唯一写入 `calculation_status`、`ranking_pool`、`formal_ready`。旧的 `summary.status` 或 `ranking_pool_status` 只允许作为读取兼容，不得作为正式结果判断依据；字段缺失一律视为非正式。
- 顶层锁定结果沿用现有命名 `payroll_locked_conflicts` 和 `payroll_locked_conflict_details`；`warnings` 是结构化 warning 列表，不再另造 `locked_conflicts` 顶层字段。
- `persistence` 必须出现在每次计算响应中，包含 `expected_shop_count`、`actual_shop_count`、`verified`；`verified=false` 不得返回 `completed`。

## 文件范围总览

- Modify: `backend/domains/business/routers/performance_management.py` — 月度计算编排、模式参数、最终持久化校验和结构化响应。
- Modify: `backend/services/hr_income_calculation_service.py` — 兼容查询的 savepoint/fallback、负利润提成边界、事务契约。
- Modify: `backend/services/payroll_generation_service.py` — 无绩效主结果时禁止生成绩效工资，保持服务不自行提交事务。
- Modify: `backend/schemas/performance.py` and `backend/schemas/__init__.py` — 计算响应和状态字段的类型契约。
- Modify: `frontend/src/api/index.js` — 传递 `mode` 并统一解析计算结果。
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagement.vue` — 计算按钮、状态提示和数据刷新。
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagementShop.vue` — 店铺维度展示观察池/阻断原因/运营目标缺失。
- Modify: `frontend/src/domains/business/views/hr/PerformanceDisplay.vue` — 展示正式结果与诊断结果的状态说明。
- Create: `backend/tests/test_performance_calculation_transaction.py` — 事务原子性和持久化校验。
- Create: `backend/tests/test_performance_calculation_readiness.py` — 运营目标、利润基数和观察模式契约。
- Modify: `backend/tests/test_hr_income_calculation_service.py` — fallback 不回滚外层事务、负基数提成边界。
- Modify: `backend/tests/test_payroll_generation_service.py` — 缺少正式绩效时不得生成工资单。
- Modify: `backend/tests/test_performance_management_runtime_contract.py` and `backend/tests/test_add_performance_income_acceptance.py` — 新响应状态和模式参数。
- Create: `frontend/scripts/performanceCalculationFeedback.test.mjs` — 前端响应状态映射的纯函数测试。
- Modify: `frontend/package.json` — 注册前端纯函数测试命令（如果现有脚本结构需要）。
- Modify: `scripts/verify_performance_regression.py` — 将新的后端事务/就绪性测试纳入回归入口。

### Task 1: 固化计算状态和响应契约

**Files:**
- Modify: `backend/schemas/performance.py`
- Modify: `backend/schemas/__init__.py`
- Modify: `backend/domains/business/routers/performance_management.py`
- Test: `backend/tests/test_performance_calculation_readiness.py`

- [ ] **Step 1: 写失败测试，定义正式/观察/警告响应。**

覆盖以下响应字段：`period`、`mode`、`status`、`readiness`、`persistence`、`shop_performance_upserts`、`employee_performance_upserts`、`commission_upserts`、`payroll_upserts`、`payroll_locked_conflicts`、`payroll_locked_conflict_details`、`warnings`。`status` 至少支持 `completed`、`completed_with_warnings`、`observation`、`not_ready`、`failed`；`formal_ready` 只存在于 `readiness` 对象中。

- [ ] **Step 2: 运行定向测试确认当前接口不满足契约。**

Run: `python -m pytest backend/tests/test_performance_calculation_readiness.py -q`

Expected: FAIL，当前接口只返回通用成功消息，无法表达运营目标缺失和最终持久化状态。

- [ ] **Step 3: 在 `backend/schemas/performance.py` 增加 typed response。**

提供 `PerformanceCalculationReadiness`、`PerformanceCalculationWarning`、`PerformanceCalculationResponse`；将缺失维度、缺失数量、来源表和建议动作作为结构化字段，不把诊断信息塞进单一字符串。

- [ ] **Step 4: 为计算路由增加 `mode: Literal["formal", "observation"] = "formal"`，并让成功响应使用新 schema。**

保留已有错误码兼容性；正式模式的未就绪使用现有 `PERF_CALC_NOT_READY` 语义并补充 `data.status=not_ready`，观察模式允许返回 `status=observation`。

- [ ] **Step 5: 运行测试确认契约通过。**

Run: `python -m pytest backend/tests/test_performance_calculation_readiness.py -q`

Expected: PASS。

- [ ] **Step 6: Commit。**

```bash
git add backend/schemas/performance.py backend/schemas/__init__.py backend/domains/business/routers/performance_management.py backend/tests/test_performance_calculation_readiness.py
git commit -m "feat: define performance calculation status contract"
```

### Task 2: 修复共享事务和兼容查询 rollback

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/domains/business/routers/performance_management.py`
- Test: `backend/tests/test_performance_calculation_transaction.py`
- Test: `backend/tests/test_hr_income_calculation_service.py`

- [ ] **Step 1: 写失败测试验证 rollback 会删除外层已写入的 `PerformanceScore`。**

使用一个能模拟考勤英文列不存在的 `AsyncSession`/事务 fixture：先加入店铺绩效，触发考勤查询失败，再执行 fallback；断言 fallback 不调用外层 `rollback`，并且后续 `flush`/查询仍然可用。增加路由级测试：收入或工资服务失败时，`PerformanceScore`、`EmployeePerformance`、`EmployeeCommission`、`PayrollRecord` 均不应提交；对领域异常和 `ValueError` 错误返回也要断言先调用 `rollback`。

- [ ] **Step 2: 运行失败测试。**

Run: `python -m pytest backend/tests/test_performance_calculation_transaction.py backend/tests/test_hr_income_calculation_service.py -q`

Expected: FAIL，当前考勤 fallback 会调用 `db.rollback()`，且部分 fallback 方法仍有相同风险。

- [ ] **Step 3: 为只读 ORM/fallback 查询使用 savepoint 或无破坏事务方式。**

在 `HRIncomeCalculationService` 中将 `_load_attendance_adjustment_by_employee` 的英文 ORM 探测放进 `async with self.db.begin_nested():`；异常只回滚 savepoint，然后执行中文列原生 SQL fallback，禁止调用外层 `db.rollback()`。对同文件中仍存在的 `_load_*` fallback 采用同一规则，删除重复的会回滚外层事务的旧实现，保留当前英文 ORM 优先路径。

- [ ] **Step 4: 统一工资服务的事务职责。**

确认 `PayrollGenerationService.generate_month()` 只在当前 session 中 add/update/flush，不调用 `commit` 或 `rollback`；如兼容查询仍需要 fallback，也使用 savepoint。路由负责唯一一次正式提交，异常统一由路由 rollback。

- [ ] **Step 5: 保持路由单事务编排。**

在 `performance_management.py` 中明确顺序：准备数据 → 写店铺绩效 → `flush` → 写个人绩效/提成（`commit=False`）→ 写工资单 → 统一 `flush` → 最终校验 → 单次 `commit`。任何步骤抛出异常，或任一错误响应分支（包括 `ValueError`）返回前，都必须先 `await db.rollback()`；不能在下游服务中独立提交，也不能让依赖注入层在错误响应后自动提交半成品。

- [ ] **Step 6: 运行定向测试。**

Run: `python -m pytest backend/tests/test_performance_calculation_transaction.py backend/tests/test_performance_management_runtime_contract.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_payroll_generation_service.py -q`

Expected: PASS；同时保留已有“工资生成失败时回滚”的测试。

- [ ] **Step 7: Commit。**

```bash
git add backend/services/hr_income_calculation_service.py backend/services/payroll_generation_service.py backend/domains/business/routers/performance_management.py backend/tests/test_performance_calculation_transaction.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_payroll_generation_service.py
git commit -m "fix: keep performance calculation in one transaction"
```

### Task 3: 增加最终持久化校验，禁止虚假的成功响应

**Files:**
- Modify: `backend/domains/business/routers/performance_management.py`
- Test: `backend/tests/test_performance_calculation_transaction.py`
- Modify: `backend/tests/test_performance_management_runtime_contract.py`

- [ ] **Step 1: 写失败测试。**

模拟 `upserts=20` 但实际查询不到 `c_class.performance_scores` 的场景；断言接口返回 `failed`/HTTP 500 或明确的持久化错误，且不返回“绩效计算完成”。同时覆盖重复计算：20 个目标只产生 20 条 `(platform_code, shop_id, period)` 结果，不产生重复行。

- [ ] **Step 2: 运行测试确认当前误报成功。**

Run: `python -m pytest backend/tests/test_performance_calculation_transaction.py::test_calculation_rejects_unpersisted_shop_scores -q`

Expected: FAIL，当前只使用内存中的 `upserts` 计数。

- [ ] **Step 3: 实现 `flush` 后的实际行校验。**

按本次 `calc_list` 的业务键查询 `PerformanceScore`，验证行数、周期、店铺键集合和必需状态字段；验证正式模式下不存在 `pending_design` 的必需维度。把校验结果放入 `persistence` 字段，至少包含 `expected_shop_count`、`actual_shop_count`、`verified`。

- [ ] **Step 4: 将持久化校验失败纳入统一异常处理。**

校验失败时 rollback，禁止调用收入和工资生成，或在已调用的情况下确保所有写入一并回滚；包括 `ValueError` 在内的所有错误响应路径都先 rollback，再返回可定位的错误码和恢复建议。

- [ ] **Step 5: 运行测试。**

Run: `python -m pytest backend/tests/test_performance_calculation_transaction.py backend/tests/test_performance_management_runtime_contract.py -q`

Expected: PASS。

- [ ] **Step 6: Commit。**

```bash
git add backend/domains/business/routers/performance_management.py backend/tests/test_performance_calculation_transaction.py backend/tests/test_performance_management_runtime_contract.py
git commit -m "fix: verify performance rows before reporting success"
```

### Task 4: 明确运营目标缺失和正式/观察计算边界

**Files:**
- Modify: `backend/domains/business/routers/performance_management.py`
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/services/payroll_generation_service.py`
- Test: `backend/tests/test_performance_calculation_readiness.py`
- Test: `backend/tests/test_add_performance_income_acceptance.py`

- [ ] **Step 1: 写失败测试覆盖 6 月无运营目标。**

正式模式下使用 20 个店铺目标和利润基数、但运营目标为空：断言返回 `status=not_ready`，`formal_ready=false`，缺失维度包含 `operation`，并且四张绩效/收入/工资结果表没有本次新写入。观察模式下断言只生成店铺观察结果，`employee_performance_upserts=0`、`commission_upserts=0`、`payroll_upserts=0`。

- [ ] **Step 2: 运行失败测试。**

Run: `python -m pytest backend/tests/test_performance_calculation_readiness.py backend/tests/test_add_performance_income_acceptance.py -q`

Expected: FAIL，当前无运营目标仍会继续调用 HR 收入和工资服务。

- [ ] **Step 3: 实现就绪性判定。**

在写入前形成 `readiness`：销售目标/达成、利润目标/达成、运营目标/达成和利润基数来源。将结果统一写入 `score_details.summary.calculation_status`、`ranking_pool`、`formal_ready`；缺少运营目标时不伪造目标、不把 `pending_design` 当作正式得分；正式模式提前返回，观察模式才允许保存部分店铺诊断结果。

- [ ] **Step 4: 让下游服务拒绝非正式店铺结果。**

`HRIncomeCalculationService` 只读取 `PerformanceScore.score_details.summary.calculation_status` 和 `formal_ready`；旧字段缺失或状态未知一律视为非正式，直接返回零写入的明确结果或抛出领域异常。`PayrollGenerationService` 在没有对应正式 `EmployeePerformance` 时，不得仅凭工资结构创建包含绩效字段的当月工资单；调用方应在正式计算未就绪时不调用它。

- [ ] **Step 5: 保留锁定冲突的非阻断语义。**

确认/已发放工资单与新计算值不一致时不覆盖，计入 `warnings.locked_payroll_conflicts`，整体状态为 `completed_with_warnings`，而不是丢失其他未锁定员工结果。

- [ ] **Step 6: 运行测试。**

Run: `python -m pytest backend/tests/test_performance_calculation_readiness.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_performance_management_runtime_contract.py -q`

Expected: PASS。

- [ ] **Step 7: Commit。**

```bash
git add backend/domains/business/routers/performance_management.py backend/services/hr_income_calculation_service.py backend/services/payroll_generation_service.py backend/tests/test_performance_calculation_readiness.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_performance_management_runtime_contract.py
git commit -m "feat: block formal performance calculation without operation targets"
```

### Task 5: 固化利润基数、成本 fallback 和提成口径

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Test: `backend/tests/test_hr_income_calculation_service.py`
- Test: `backend/tests/test_performance_calculation_readiness.py`
- Reference: `backend/services/profit_basis_service.py`（仅在实际实现需要调整利润基数读取时修改）

- [ ] **Step 1: 写失败测试覆盖 6 月成本来源。**

验证当 `finance.fact_expenses_allocated_day_shop_sku` 为空时，系统明确 fallback 到 `a_class.operating_costs`；验证 20 个店铺的快照覆盖、店铺键匹配和汇总值为订单利润 19341.46、A 类运营成本 20000.00、利润基数 -658.54（允许金额按既有舍入规则比较）。

- [ ] **Step 2: 写失败测试覆盖锁定快照和重建。**

未锁定快照可重建；已锁定快照不得被重新计算覆盖，返回冲突明细；云端覆盖本地 B 类订单后再次重建应使用新的 hash 和月度订单聚合。

- [ ] **Step 3: 写失败测试覆盖负基数提成。**

使用公式：

```text
commission = max(profit_basis, 0)
              × allocatable_profit_rate
              × commission_ratio
              × shop_performance_coefficient
```

负利润基数的提成必须为 0；混合正负店铺时只累加正利润基数。性能系数缺失时不能默默把观察结果按正式系数参与提成。

- [ ] **Step 4: 实现/校准数据来源和公式边界。**

保留云端覆盖本地的 B 类数据事实源，不新增本地备份流程；将成本来源、匹配店铺数、缺失店铺数写入利润基数诊断信息。所有金额在服务边界统一为 `Decimal`/既有货币舍入规则。

- [ ] **Step 5: 运行服务测试。**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py backend/tests/test_performance_calculation_readiness.py -q`

Expected: PASS。

- [ ] **Step 6: Commit。**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_performance_calculation_readiness.py
git commit -m "test: lock performance profit basis and commission semantics"
```

### Task 6: 统一下游工资与个人绩效输入输出

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/services/payroll_generation_service.py`
- Modify: `backend/domains/business/routers/performance_management.py`
- Test: `backend/tests/test_payroll_generation_service.py`
- Test: `backend/tests/test_performance_calculation_transaction.py`

- [ ] **Step 1: 写失败测试验证输入输出链路。**

正式结果存在时，验证：

```text
performance_salary = performance_package_amount × personal_performance_coefficient
commission = profit_basis × allocatable_profit_rate × commission_ratio × shop_performance_coefficient
```

验证每个下游行都能追溯到 `period/year_month`、员工和店铺分配；正式店铺绩效缺失时不得生成新的绩效工资或工资单。

- [ ] **Step 2: 运行失败测试。**

Run: `python -m pytest backend/tests/test_payroll_generation_service.py backend/tests/test_performance_calculation_transaction.py -q`

Expected: FAIL，当前工资服务可能在没有正式绩效主结果时按默认值继续生成 draft。

- [ ] **Step 3: 实现正式绩效前置条件。**

在编排层调用工资生成前验证正式个人绩效数量与可纳入员工集合；在工资服务中保持已有 `performance_score`/系数规范化逻辑，但拒绝来源状态为观察或部分结果的输入。无绩效工资员工可以按现有业务规则保留，但不能由一次失败的绩效计算新建伪绩效工资单。

- [ ] **Step 4: 保持人工工资字段和锁定状态。**

draft 工资单重算时保留人工字段；confirmed/paid 工资单不自动覆盖，返回变化字段。所有自动字段重新计算后执行既有总额/净额/总成本核算。

- [ ] **Step 5: 运行测试。**

Run: `python -m pytest backend/tests/test_payroll_generation_service.py backend/tests/test_performance_calculation_transaction.py -q`

Expected: PASS。

- [ ] **Step 6: Commit。**

```bash
git add backend/services/hr_income_calculation_service.py backend/services/payroll_generation_service.py backend/domains/business/routers/performance_management.py backend/tests/test_payroll_generation_service.py backend/tests/test_performance_calculation_transaction.py
git commit -m "fix: align personal performance and payroll inputs"
```

### Task 7: 修复前端计算反馈和结果展示

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagement.vue`
- Modify: `frontend/src/domains/business/views/hr/PerformanceManagementShop.vue`
- Modify: `frontend/src/domains/business/views/hr/PerformanceDisplay.vue`
- Create: `frontend/scripts/performanceCalculationFeedback.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: 写前端纯函数测试。**

覆盖以下映射：`completed` 显示成功；`completed_with_warnings` 显示成功但有锁定冲突；`observation` 显示观察结果且明确“不参与正式排名/提成/工资”；`not_ready` 显示运营目标或利润基数缺失；HTTP 500/持久化校验失败显示真实失败原因。

- [ ] **Step 2: 运行前端失败测试。**

Run: `npm --prefix frontend run test:performance-calculation-feedback`

Expected: FAIL，当前没有对应的状态映射测试和结构化提示。

- [ ] **Step 3: 在 API 层传递 `mode` 并保留后端错误体。**

`calculatePerformanceScores(period, { mode: 'formal' })` 默认正式模式；不要只弹出固定“计算完成”。将 `response.data.status`、`readiness.missing_dimensions`、`warnings` 和 `persistence` 原样交给视图层。

- [ ] **Step 4: 更新绩效管理页。**

点击“重新计算”后根据状态刷新列表；正式未就绪时显示缺失维度和恢复动作；支持管理员明确触发观察模式（如增加“生成诊断结果”按钮或等价入口），并说明观察结果不会生成收入和工资。

- [ ] **Step 5: 更新店铺/展示页。**

店铺行显示正式池/观察池、计算状态、运营目标状态和利润基数来源；没有 `performance_scores` 时显示后端错误原因，而不是泛化为“暂无数据”。

- [ ] **Step 6: 运行前端检查。**

Run: `npm --prefix frontend run test:performance-calculation-feedback`

Run: `npm --prefix frontend run type-check`

Run: `python scripts/verify_utf8_source_hygiene.py`

Expected: 三项 PASS；Windows 输出不得新增编码损坏或 emoji 日志。

- [ ] **Step 7: Commit。**

```bash
git add frontend/src/api/index.js frontend/src/domains/business/views/hr/PerformanceManagement.vue frontend/src/domains/business/views/hr/PerformanceManagementShop.vue frontend/src/domains/business/views/hr/PerformanceDisplay.vue frontend/scripts/performanceCalculationFeedback.test.mjs frontend/package.json
git commit -m "feat: show performance calculation readiness in frontend"
```

### Task 8: 处理员工身份警告和确认任务同步

**Files:**
- Modify: `backend/domains/business/routers/performance_management.py`
- Modify: `backend/services` 中负责确认任务同步的现有服务（以实际 import 定位，不新建重复服务）
- Test: `backend/tests/test_performance_calculation_transaction.py`
- Test: `backend/tests/test_performance_management_runtime_contract.py`

- [ ] **Step 1: 写失败测试覆盖未关联用户员工。**

使用 `EMP260005` 场景：绩效计算本身可以完成，但响应的 `warnings` 必须包含员工编号和 `user_link_missing`；确认任务不能伪造用户，也不能让整个已提交的绩效结果回滚。

- [ ] **Step 2: 实现结构化警告。**

将任务同步结果从日志-only 改为可聚合的 warning；同步失败仍在提交后处理，避免通知/任务系统故障破坏已验证的计算事务。区分“计算失败”和“任务同步警告”。

- [ ] **Step 3: 运行测试并提交。**

Run: `python -m pytest backend/tests/test_performance_calculation_transaction.py backend/tests/test_performance_management_runtime_contract.py -q`

Expected: PASS。

```bash
git add backend/domains/business/routers/performance_management.py backend/services backend/tests/test_performance_calculation_transaction.py backend/tests/test_performance_management_runtime_contract.py
git commit -m "feat: expose performance confirmation warnings"
```

### Task 9: 6 月数据补齐与端到端回归验收

**Files:**
- Modify: `scripts/verify_performance_regression.py`
- Create: `backend/tests/test_june_performance_calculation_acceptance.py`
- Reference: `docs/guides/ENVIRONMENT_MODEL.md`, `docs/guides/DEVELOPMENT_ENVIRONMENT.md`, `docs/guides/VERIFICATION_MATRIX.md`

- [ ] **Step 1: 建立只读验收前置检查。**

在本地 Docker PostgreSQL 上检查 2026-05、2026-06 的月粒度订单数量、`data_hash` 集合、店铺目标分解覆盖和利润基数快照覆盖；不做本地备份，不把本地生成的 draft 结果当成基线。检查失败先停止计算。

- [ ] **Step 2: 只读盘点残留结果，禁止在本次验收中直接清理本地业务数据。**

使用开发数据库的只读连接盘点 `2026-06` 的 `c_class.performance_scores`、`c_class.employee_performance`、`c_class.employee_commissions` 和 `a_class.payroll_records`，按 `(period/year_month, employee_code/shop_id, status)` 输出现有行数；不要执行 `DELETE`，不要删除 confirmed/paid，也不要假设本地 draft 可以安全删除。已知的 4 条个人绩效、4 条提成和 7 条 draft 工资单只作为“历史残留基线”记录。

验收中的故障注入、回滚和清理场景全部使用隔离数据库或 pytest 事务回滚 fixture。若需要本地真实端到端验证，先使用 `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T postgres psql` 执行只读查询，并通过唯一测试标记/隔离 schema 生成测试数据；本计划不新增本地备份，也不提供未经确认的删除命令。

- [ ] **Step 3: 执行 6 月正式模式。**

当前云端没有 6 月运营目标，因此预期正式模式为 `not_ready`：无新增个人绩效、提成、工资单，前端显示缺失运营目标。该结果是正确的阻断，不是失败。

- [ ] **Step 4: 执行 6 月观察模式。**

预期得到 20 个店铺的观察结果，销售/利润维度可解释，运营维度为 `pending_design`；不得生成正式排名系数、个人收入、提成或工资单。

- [ ] **Step 5: 使用测试夹具补充一个已确认运营目标的正式场景。**

不向真实 6 月业务数据伪造运营目标；使用隔离测试数据或事务回滚 fixture，验证 20 个店铺（或最小代表集）全部正式就绪后，店铺绩效、个人绩效、提成和工资单数量与金额一致。

- [ ] **Step 6: 验证故障原子性。**

故意让考勤 ORM 查询失败、收入服务失败、工资服务失败和持久化校验失败，分别验证四类结果不会出现“店铺绩效回滚但下游已提交”的半成功状态。

- [ ] **Step 7: 运行完整回归。**

Run: `python -m pytest backend/tests/test_june_performance_calculation_acceptance.py backend/tests/test_performance_calculation_transaction.py backend/tests/test_performance_calculation_readiness.py backend/tests/test_performance_management_runtime_contract.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_payroll_generation_service.py -q`

Run: `python scripts/verify_performance_regression.py --mode ci`

Run: `npm --prefix frontend run build`

Expected: 全部 PASS；6 月正式模式明确未就绪，观察模式仅有观察结果，补充运营目标的隔离正式场景完整落库。

- [ ] **Step 8: 记录验收输出并提交。**

在现有文档目录或测试输出中记录数量、hash、来源、状态和已知警告；不要新增根目录一次性报告。验收记录必须明确区分云端基线、本地覆盖后 hash、历史残留行和本次隔离测试行。提交回归脚本和验收测试：

```bash
git add scripts/verify_performance_regression.py backend/tests/test_june_performance_calculation_acceptance.py
git commit -m "test: add June performance end-to-end acceptance"
```

## 完成定义

- 正式计算成功时，`c_class.performance_scores` 实际行数与目标店铺数一致，且同一月度业务键无重复。
- 任一计算步骤失败时，店铺绩效、个人绩效、提成和工资单不会出现跨事务半成功。
- 6 月无运营目标时，系统不伪造目标、不生成正式收入结果；观察模式可解释但不参与奖惩。
- 利润基数来源、成本匹配、负基数提成和快照锁定行为均有自动化测试。
- 绩效工资、提成公式与输入输出可追溯，draft 的人工字段和 confirmed/paid 的锁定语义保持不变。
- 前端不会再把“接口返回 upserts”当成“数据库已成功落库”；所有状态、缺失维度和警告可见。
- `EMP260005` 的用户关联问题以警告呈现，不伪造账号、不吞错、不影响已验证的核心计算结果。
- 6 月月度订单与云端 hash 一致性、20 个店铺目标分解和 20 个利润基数快照都有回归验收证据。

## 不在本次范围内

- 不修改云端 B 类数据事实源，不新增本地备份链路。
- 不凭业务猜测创建 2026-06 运营目标；运营指标和目标值必须由业务确认后再配置。
- 不借机重构整个绩效域、工资域或历史 Metabase/OpenSpec 代码。
- 不删除 confirmed/paid 工资单，不修改已锁定财务结果。
- 不处理与本链路无关的前端视觉重构或非阻断技术债；记录到 post-launch V2 清单。

## 实施顺序与交付节奏

按 Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 顺序执行。Task 2、3 是发布阻断项；Task 4 决定 6 月正式计算是否允许落库；Task 5、6 负责金额正确性；Task 7、8 负责可操作性和审计可见性；Task 9 是最终放行门槛。每个 Task 使用独立小提交，执行阶段完成一个 Task 后先运行其定向测试再进入下一项。

# 月度利润看板 · 完整优化设计

- 日期：2026-11-21
- 范围：财务结算中心（前端路由 `/financial-management`，后端 `backend/services/monthly_profit_settlement_service.py` + `backend/domains/business/routers/monthly_profit_settlement.py`）的前后端完整优化 + 跟投模块整体下线
- 业务负责人：Walter
- 状态：待评审（本文档只做设计，不含代码实施）
- 修订记录：2026-11-21 第二版 —— 按独立审查结论修正事实错误、SSOT 判定与变更范围（详见 §12）

---

## 0. 一句话结论

把「月度利润结算中心」从**会自己算钱的审批表单**，改成**只呈现已发生事实的月度利润看板**；同时把没有商业规则的跟投模块整体下线。

改动后，这块页面不再生产任何金额，只回答一句话：**这个月赚了多少、分给员工多少、人工调整多少、留下多少。**

**本期不重命名后端模块**（受上线前规则约束），改的是概念、职责与前端形态；重命名降级为 post-launch V2。

---

## 1. 今天这块页面到底在做什么

现状是 2026-04-10 设计稿（`docs/superpowers/specs/2026-04-10-monthly-profit-settlement-center-design.md`）的产物。那时的假设是：上游没有统一口径，结算中心负责自己汇总人力成本，再按公司政策比例分配并审批。

但 2026-08 至 2026-11 上游已经自己长出了完整闭环：

```
店铺利润基数 → 提成 → 绩效工资 → 工资单 total_cost
```

于是结算中心今天同时扮演两个角色：**汇总上游已算好的数**（该保留）+ **自己再算一遍人员成本**（该删）。后者是三个金额缺陷的共同来源。

---

## 2. 三个必须先解决的业务事实

### 2.1 人员成本被重复扣减（确定的金额错误）

逐项对账可得出精确恒等式：

```
利润基数 profit_basis_amount
  = 店铺经营利润 − (其他经营成本 + 提成前人力成本)
  提成前人力成本 = 底薪 + 岗位工资 + 津贴 + 加班 + 奖金 + 公司社保 + 公司公积金
  （backend/services/labor_cost_projection_service.py:52-60）

工资单 total_cost
  = 毛薪 + 公司社保 + 公司公积金
  毛薪 = 底薪 + 岗位工资 + 绩效工资 + 加班 + 提成 + 津贴 + 奖金
  （backend/services/payroll_generation_service.py:229-256）

⇒ total_cost = 提成前人力成本 + 绩效工资 + 提成
```

即 **`total_cost − (绩效工资 + 提成) = 提成前人力成本`**，而这笔钱在利润基数里已经扣过一次。

结算中心审批后按 `total_cost` 再扣一次人员成本，等于把底薪那部分固定工资又扣了一遍。

模拟验证（1 人 1 店，底薪 2000 / 绩效工资 1000 / 提成 500）：

| 口径 | 扣掉的人员成本 | 公司留存 |
|---|---|---|
| 草稿口径（分摊表 `performance_amount + commission_amount`） | 1,500 | **6,500** ✅ 与业务正确值一致 |
| 快照口径（工资单 `total_cost`） | 3,500 | 4,500 ❌ 少 2,000 |
| 差额 | — | **正好等于底薪 2,000** |

位置：`backend/services/monthly_profit_settlement_service.py:362-393`（快照取 `total_cost`）、`:185-222`（草稿口径）。

> ⚠️ **前提条件（必须写进纸面）**：上述"重复扣减"成立的前提是**人力成本分摊表已按当前口径生成**。生产现状该表 0 行（`docs/superpowers/plans/2026-11-19-hr-user-management-optimization.md:35-44`），此时分摊表为空 ⇒ 草稿口径人员成本恒为 0，而快照口径仍按 `total_cost` 扣 ⇒ **生产当前可见症状是"快照口径独扣"，而不是"重复扣减"**。两个缺陷同时存在，只是谁先被看见取决于上游数据是否就绪。

### 2.2 公司人力成本池被扣两次

利润基数已把公司池二次分摊进各店成本（`backend/services/profit_basis_service.py:246-258, 302-306`），月结又减一次整池（`monthly_profit_settlement_service.py:168-183`）。

模拟：总部 1 万 + 店铺 5 万 ⇒ 真实成本 6 万、实际扣 7 万、**公司留存低估 1 万**。

> 该扣减本身**已有版本过滤**（`:178-179`，注释明写"历史 V1 行与同月 V2 行并存时会把人力成本算两遍"），所以它是**纯口径重复**，不是版本缺陷。

### 2.3 审批门槛用一套口径校验、落库用另一套

`approve()` 先用草稿口径（分摊表 `performance + commission`）校验阈值（`:940-946`），再按快照口径（`total_cost`）重算并回写（`:958-976`）。

⇒ **超阈值可以放行，审批后落库反而超标。门槛形同虚设。**

### 2.4 人员成本查询缺版本过滤

`_load_personnel_payload`（`:186-199`）查询分摊表时**没有 `calculation_version` 过滤**，而同文件的公司池扣减路径有（`:178-179`）。

分摊表唯一约束含 `calculation_version`（`modules/core/db/schema_parts/business.py:1903-1920`），两版可并存 ⇒ 同月两版行并存时人员成本最高虚高一倍。

**上游标准做法是严格等值过滤**：`profit_basis_service.py:231-241` 与 `sql/mart/shop_month_labor_cost.sql:8-14` 都用 `calculation_version = LABOR_COST_CALCULATION_VERSION`，后者注释明写"不加这个过滤 ⇒ 同一个人力成本被计入两次 ⇒ 看板经营指标里的「人力成本」虚高"。看板必须照此办理。

### 2.5 跟投：机制建好了，商业规则没定

机制侧其实完整：投入额 → 占用天数 → 加权资本 → 份额比例 → 收益（`backend/services/follow_investment_service.py:46-80`）。

但决定成败的一环是空的：**跟投分配比例没有任何配置、没有政策、没有 SSOT**，纯靠每次调 API 手工传参（`backend/domains/business/routers/follow_investment.py:61`）。另外两处业务规则也空白：跟投本金在亏损时如何处理（`profit_basis_amount <= 0` 时收益直接算 0，本金去向无规则）、退出机制无结算后果设计。

2026-05-30 设计稿自身的判断也是一致的：跟投是「当前脆弱性最高的区域」「对利润口径边界的污染风险最大」（`docs/superpowers/specs/2026-05-30-follow-investment-and-settlement-safe-rebuild-design.md:116-117`）。

**业务已确认：目前没有真实跟投人投钱 ⇒ 整个模块可删除。**

---

## 3. 目标与非目标

### 目标

1. 消灭 2.1 / 2.2 / 2.3 三个金额缺陷与 2.4 的版本缺陷，且**不改动上游任何一行代码**
2. 模块从「生产金额 + 审批」转为「呈现金额 + 一处人工调整」
3. 删除跟投模块（含三张表、审批模板、权限点、角色、前端页面与菜单）
4. 前端从「编辑表单」重做为主流信息架构下的只读看板
5. 把这块业务的核心指标登记进指标词典，消除「页面标签即定义」

### 非目标（本次明确不做）

| 不做 | 原因 |
|---|---|
| 提成链路 5 处第二实现收敛 | 属上游提成域，超出财务看板业务范围（`docs/guides/PRE_LAUNCH_RULES.md` 变更范围约束） |
| 绩效系数 min vs 加权平均的统一 | 属上游绩效/工资域，会改动已发工资金额，需单独拍板与迁移 |
| 店铺利润基数口径本身 | 已是上游口径 SSOT（`backend/services/labor_cost_policy_service.py`） |
| 工资单 / 提成 / 绩效链路 | 5-30 设计稿列为「禁止顺手改动的区域」 |
| 预算编制功能 | 业务已确认预算在系统外人工做 |
| **后端模块重命名** | `PRE_LAUNCH_RULES.md:19-20` 禁止 cross-module renames；重命名与消灭金额缺陷无因果关系，属 `PRE_LAUNCH_RULES.md:39` 禁止的"顺手清理" |

以上列为 **post-launch V2 治理项**，写入 `docs/superpowers/plans/`，不在本次实施。

---

## 4. 新的业务概念

### 4.1 概念定义

**月度利润看板**：公司管理层每月查看的一张只读事实表。

它的业务边界是**三读一写**：

| | 内容 | 性质 |
|---|---|---|
| 读 1 | 店铺利润基数（来自财务侧） | 只读 |
| 读 2 | 员工侧分配额（绩效工资 + 提成，来自人力成本分摊表） | 只读 |
| 读 3 | 人工调整项（看板自身唯一可写表） | 读 + 写 |
| 写 | 人工调整项录入（带类型、必填原因、操作人） | 唯一写入口 |

**看板不是**审批台账、**不是**预算工具、**不是**分配计算器、**不是**任何金额的来源。

### 4.2 唯一真源表（SSOT 律 1：一次写死）

| 业务概念 | 唯一真源表 | 唯一口径与过滤规则 |
|---|---|---|
| 店铺利润基数 | `finance.shop_profit_basis` | 同店多行时**非 legacy A_ONLY 行优先**（复用 `LaborCostPolicyService.is_legacy_a_only_basis_version`，见 `monthly_profit_settlement_service.py:149-164`）。**不在看板里另写一套版本判定** |
| **员工侧分配额（总额与每店）** | **`finance.employee_labor_cost_allocations`** | **`calculation_version = LABOR_COST_CALCULATION_VERSION` 严格等值过滤**（`profit_basis_service.py:231-241` 的既有做法）。取 `performance_amount + commission_amount`；**`pre_commission_amount` 一律不取**（已在利润基数里扣过） |
| 人工调整 | `finance.monthly_profit_adjustments` | 经 `finance.monthly_profit_settlements` 关联到 `period_month`；类型 + 金额 + **必填**原因 + 操作人 |

**关键更正**：`c_class.employee_commissions`（`business.py:4853-4884`，唯一键 `employee_code + year_month`）与 `a_class.payroll_records`（`business.py:4610`）**都没有店铺维度**，无法支撑每店 breakdown。它们只能作为**员工粒度的交叉校验源**，不是看板取数源。

⇒ **每店维度的员工侧分配额，唯一合法来源是人力成本分摊表**（`business.py:1853-1922`，含 `platform_code` / `shop_id` / `allocation_scope` / `performance_amount` / `commission_amount`）。

**看板禁止计算**：人员成本、提成、绩效工资、公司成本池、利润基数。**看板只读取分摊表已投影好的金额，不自己重算。**

### 4.3 看板允许的唯一三条算术（SSOT 律 3：派生层只有一份口径）

```
净利润       = Σ 各店 profit_basis_amount（按 §4.2 规则去重）
员工侧分配额 = Σ(所有 allocation_scope) 的 (performance_amount + commission_amount)
               且 calculation_version = LABOR_COST_CALCULATION_VERSION
公司留存     = 净利润 − 员工侧分配额 − 人工调整额
```

**关于 `allocation_scope` 的处理**：`company` scope 的行同样要计入员工侧分配额——因为总部/仓库/客服的**绩效工资与提成**也是真实从公司利润里分出去的钱。只有 `pre_commission_amount`（无论 shop 还是 company scope）已经在利润基数里扣过，一律不再计入。

这三条算术**只在一个文件里存在**：`backend/services/monthly_profit_settlement_service.py`（本期不新建 service、不改名，见 §6.1）。前端不得复刻（5-30 设计稿：「展示层不得承载口径计算逻辑」）。

### 4.4 唯一由人落笔的东西（SSOT 律 2）

- **人工调整项**是看板唯一的可写对象，由人录入，带必填原因；看板必须显式标记「含 N 笔人工调整」并显示总额，**不允许把调整藏在数字里**。
- **服务端的 default 兜底必须拆掉**。现状：`monthly_profit_settlement_service.py:773`、`:907-908` 用 `reason=adjustment_reason or "monthly settlement adjustment"` 兜底——这是**系统代填原因**，违反律 2。新写入路径缺 `reason` 直接返回 400。
- 看板不再反向改写上游：随审批流一起删除的 `invalidate_settlement_performance()`（`:1015-1039`，其中 `:1029` 改写 `ShopProfitBasis.is_locked = False`）一并消失。跟投模块守住了这条规矩（它不回写 `ShopProfitBasis`），看板应当向它看齐。

### 4.5 指标登记（`sea-metrics-language` 强制流程）

现有词典只有笼统的 `profit`，**没有 `profit_basis_amount` / 公司留存 / 员工侧分配额**。本次新增 6 个指标，登记进 `references/metrics-dictionary.md` 与 `references/metric-status.md`：

| 标准键 | 中文名 | 系统统一口径 | 公式 | 粒度 | 状态 |
|---|---|---|---|---|---|
| `profit_basis_amount` | 店铺利润基数 | `finance.shop_profit_basis`，非 legacy A_ONLY 行优先 | 订单利润 − (其他经营成本 + 提成前人力成本) | 平台 × 店铺 × 月 | stable |
| `employee_allocation_amount` | 员工侧分配额 | `finance.employee_labor_cost_allocations`，当前 `calculation_version` | Σ(performance_amount + commission_amount) | 月（可下钻到店/人） | stable |
| `manual_adjustment_amount` | 人工调整额 | `finance.monthly_profit_adjustments` | Σ 调整行金额 | 月 | stable |
| `company_retained_amount` | 公司留存 | 看板聚合层 | 净利润 − 员工侧分配额 − 人工调整额 | 月 | stable |
| `allocation_ratio` | 分配占比 | 看板聚合层 | (员工侧分配额 + 人工调整额) ÷ 净利润 | 月 | stable |
| `over_allocation_flag` | 超额分配标记 | 看板聚合层 | 公司留存 < 0 或 分配占比 > 1 | 月 | stable |

⚠️ **副本分叉必须先解决（前置阻塞项）**：该 skill 有两份副本，2026-10-24 规格写明「正本 `team-skills-bundle/`、副本 `docs/team-skills/`，改这个 skill 一律改正本再同步副本」。**但实测（2026-11-21）两份已分叉**，且分叉范围比预想大：

| 文件 | 状态 |
|---|---|
| `SKILL.md` / `agents/openai.yaml` / `meeting-output-template.md` | 一致 |
| `metric-status.md` / `metric-usage-matrix.md` / `metrics-dictionary.md` / `platform-mapping.md` | **不同** |

行数实测 481 行（`docs/team-skills/`）vs 360 行（`team-skills-bundle/`）；`docs/team-skills/` 那份多出整节「投放 ROI 边界（商品中心，2026-11 起登记）」（`break_even_roi` / `suggested_roi` 等）。**若机械地"改正本再同步"，会把 2026-11 新登记的 ROI 指标删掉。**

处理方式（三步）：
1. 以内容更全的 `docs/team-skills/` 为**当前实际真相源**，同步回 `team-skills-bundle/`
2. 跑 SHA256 校验两份 skill 目录 7/7 一致
3. **机器可验证**：新增一个指纹校验脚本（参照 `scripts/verify_architecture_ssot.py` 形态）固化"两份字节一致"这一条。律 3 要求"机器可验证"，靠人读文档判断哪份是正本不满足

---

## 5. 跟投下线

### 5.1 删除清单

**数据库（3 张表，均在 `finance` schema）**

| 表 | 用途 |
|---|---|
| `finance.follow_investments` | 跟投本金记录 |
| `finance.follow_investment_settlements` | 月度跟投结算头 |
| `finance.follow_investment_details` | 月度跟投结算明细 |

⚠️ **外键阻塞点**：`finance.monthly_profit_follow_details.source_settlement_id` → `finance.follow_investment_settlements.id`，**无 ondelete**（`business.py:2153-2155`）。**直接 drop 跟投表会因依赖失败**，必须先 drop `finance.monthly_profit_follow_details`（它本身也因跟投下线而废弃，见 §6.4）。

已上线的历史迁移**不删**（`migrations/versions/20260407_follow_investment_profit_basis.py` 等），另写一份**下线迁移** drop 表。同步更新 `current_migrations/versions/20260805_current_schema_baseline.py`、`20261240_hr_employee_lifecycle.py` 与 `scripts/verify_production_migration_contracts.py`。

**后端**

- 删除 `backend/services/follow_investment_service.py`
- 删除 `backend/domains/business/routers/follow_investment.py`、`backend/routers/follow_investment.py`（legacy wrapper）、`backend/schemas/follow_investment.py`
- 摘除路由注册 `backend/domains/business/routes.py:24,34`；清理 `backend/main.py:1349` 的注释标记（source-contract 测试依赖它）
- 摘除审批中心模板与提交/同步逻辑 `backend/services/approval_center_service.py:15`（模板常量）、`:65-73`（模板注册）、`:203-239`（`submit_follow_investment_settlement_approval`）、`:242-271`（`sync_follow_investment_settlement_approval_decision`）
- 摘除权限点 `backend/services/permission_service.py:270-272`
- **处理 `investor` 系统角色**：`backend/services/system_role_service.py:98-106` 定义了 `investor` 角色，权限只有 `business-overview` + `my-follow-investment-income`。跟投下线后该角色只剩一个权限。
  - **决定**：本次**一并下线 `investor` 角色**（它存在的唯一理由是看跟投收益；当前无真实投资人）。历史用户记录保留，仅不再授予该角色。需同步改 `backend/tests/test_system_role_service.py:28`、`test_investor_role_frontend_contract.py:11`、`test_legacy_auth_permission_compat.py:21`
- 摘除月结服务内的跟投读取：`_load_follow_payload`、`_load_follow_details` 及快照中的跟投明细

**前端**

- 删除 `frontend/src/domains/business/views/hr/MyFollowInvestmentIncome.vue`
- 摘除路由 `frontend/src/router/index.js:610-620`、菜单 `frontend/src/config/menuGroups.js:110, 237`、API `frontend/src/api/finance.js:200-237`（10 个跟投 API 方法）、store `frontend/src/stores/financeSettlement.js` 的 **4 个跟投切片**（`:21-28, 29-33, 34-38, 39-43`）与 **9 个跟投 action**（`:138, 153, 167, 176, 182, 188, 196, 204, 218`，全 store 16 个 action，跟投占 9/16 ≈ 56%）
- 摘除结算中心内的跟投子视图（`SettlementWorkspacePanel.vue` 中的跟投试算 / 跟投记录）

**测试（≥17 个文件）**

- 专属 7 个，直接删除：`backend/tests/test_follow_investment_service.py`、`test_follow_investment_routes.py`、`test_follow_investment_entry_contract.py`、`test_follow_investment_menu_contract.py`、`test_follow_investment_migration_contract.py`、`tests/test_follow_investment_finance_schema_contract.py`、`frontend/scripts/myFollowInvestmentIncomeView.test.mjs`
- 含跟投引用需改写 10 个：`backend/tests/test_finance_schema_contract.py`、`test_financial_settlement_page_contract.py`、`test_monthly_profit_settlement_frontend_contract.py`、`backend/tests/test_domain_route_registration.py:52`（断言 `/api/finance/follow-investments` 在路由表里）、`backend/tests/test_legacy_auth_permission_compat.py:21`、`frontend/scripts/domainBridgeInventory.test.mjs`（**两处都要改**：`:73` 的 `EXPECTED_ROUTE_SPECIFIERS` 数组含 `'@/domains/business/views/hr/MyFollowInvestmentIncome.vue'` 必须删除该元素，否则 `:212` 的 `deepEqual` 必红；硬编码路由计数 `:13-19` 的 `EXPECTED_DIRECT_DOMAIN_ROUTE_COUNT = 82` / `business: 29` 需同步为 81 / 28）、`frontend/scripts/roleMenuSnapshot.test.mjs`（`:73/:85/:98` 三组删元素；⚠️ **`:106-110` 的 investor 角色整块断言必须整块删除**——`ROLE_CONFIG['investor']` 变 undefined 后 `canAccess`（`:53`）的 `ROLE_CONFIG[role]?.permissions || []` 退化为 `[]`，`/business-overview` 不再出现，期望值里留着必红）

- **投资人角色相关测试须整份/整函数删除，不能只删单行**：
  - `backend/tests/test_investor_role_frontend_contract.py` —— **整份删除**。它用 `text.split("investor:", 1)` 取值，而 `frontend/src/config/rolePermissions.js` 的 `investor:` 与 `'投资人': 'investor'` 都要删 ⇒ 该串全库消失后 `parts[1]` 为 undefined ⇒ TypeError
  - `backend/tests/test_system_role_service.py:23-29` —— **删整个测试函数**。`DEFAULT_SYSTEM_ROLES` 是普通 dict（`backend/services/system_role_service.py:11`），删掉 `investor` 键后访问会 KeyError

  > ⚠️ `backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py` **不需要改**：它唯一的 follow 字样是 `CURRENT_REVISION = "20260407_follow_investment_profit_basis"`（`:11`），指向的是**保留不删**的历史迁移（§5.1 明示已上线迁移不删）。

- **月结快照 ORM 有一个跨模块依赖**：删 `MonthlyProfitPayrollSnapshot` 会打爆 `backend/domains/business/routers/hr_employee.py:48`（import）与 `:387-391`（使用）——**跟投/看板改造完全没碰过这个 HR 路由**。阶段 3 删表前必须先决定该路由改走哪条口径（或保留该表不删）。

**必须同步修改的"隐藏依赖点"**（不改会直接让验证脚本或运行时报错）：

| 文件 | 位置 | 必须做什么 |
|---|---|---|
| `scripts/verify_production_migration_contracts.py` | `:17-21` 的 `DEFAULT_TESTS` 含 `tests/test_follow_investment_finance_schema_contract.py`；`:124` 直接 `pytest -q *DEFAULT_TESTS` | 删掉该测试文件项，否则脚本因 pytest 找不到文件而 RuntimeError |
| `current_migrations/versions/20260805_current_schema_baseline.py` | `:742-749` 等 34 行直接 `CREATE TABLE finance.follow_investment_details / _settlements / _investments` | 删掉这三张表的建表语句 |
| `current_migrations/versions/20261240_hr_employee_lifecycle.py` | `:71` 注释提到 `finance.follow_investments` | 清理注释引用 |
| `frontend/src/config/rolePermissions.js` | `:81` 定义 `investor: {`；`:113` `'投资人': 'investor'` | 删投资人角色（后端 `system_role_service.py` 与前端必须同改，否则前端留死角色；`frontend/scripts/roleMenuSnapshot.test.mjs:13` 的 `ROLE_CONFIG` 正是从此文件导入） |
| `docs/guides/APPROVAL_CENTER_RUNBOOK.md` | `:93` 引用了将被删的 `backend/tests/test_follow_investment_routes.py` | 一并删掉该命令引用 |

**文档**

- 归档保留不动：`docs/superpowers/specs/2026-04-06-follow-investment-profit-sharing-design.md`、`docs/superpowers/plans/2026-04-06-follow-investment-profit-sharing.md`、`docs/superpowers/specs/2026-05-30-follow-investment-and-settlement-safe-rebuild-design.md`、`docs/superpowers/plans/2026-05-30-follow-investment-safe-rebuild-phase1.md`
- 必须更新：`docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`、`docs/guides/APPROVAL_CENTER_RUNBOOK.md`、`docs/guides/ENGINEERING_STATUS.md`、`docs/guides/FOLLOW_INVESTMENT_AND_SETTLEMENT_ACCEPTANCE_CHECKLIST_2026-05-30.md`（整份作废）、`CHANGELOG.md`（记一条下线）

### 5.2 下线前必做

生产库三张跟投表的实际行数需先确认（`SELECT count(*)`）。业务已口头确认无真实投钱，但仍以库为准。

---

## 6. 后端设计

### 6.1 命名方案（**本期选 B**）

| | 方案 A：同域改名 + 概念重置 | **方案 B：本期执行——保留原路径** |
|---|---|---|
| service | `monthly_profit_settlement_service.py` → `finance_dashboard_service.py` | **文件名不变** |
| schema | `schemas/monthly_profit_settlement.py` → `schemas/finance_dashboard.py` | **文件名不变**（扩展现有契约） |
| router | `domains/business/routers/monthly_profit_settlement.py` → `finance_dashboard.py` | **文件名不变** |
| legacy wrapper | `backend/routers/monthly_profit_settlement.py` | **文件名不变**（内容随主 router 调整） |
| URL | `/api/finance/monthly-profit-settlement` → `/api/finance/dashboard` | **不变** |
| 前端路由 | `/financial-management` | **不变**（仅改标题文案） |
| 前端组件 | `views/finance-settlement/` → `views/finance-dashboard/` | **允许新建目录**（前端完整优化是用户明确要求的范围；5-30 设计稿已授权"删除并重做旧前端壳层"） |
| 前端 store | `stores/financeSettlement.js` → `stores/financeDashboard.js` | **允许新建**（跟投切片删除后剩余两个域仍混域，需拆） |

**为什么本期选 B**：`docs/guides/PRE_LAUNCH_RULES.md:19-20` 禁止 "Broad refactors that are not required for launch" 与 "Large directory moves or cross-module renames"；`AGENTS.md:36` 同义。方案 A 跨后端 5 个文件、前端 4 处、测试 17+ 个、文档 5+ 份，属禁止项；而重命名与"消灭三个金额缺陷"之间**没有因果关系**，正是 `PRE_LAUNCH_RULES.md:39` 所说的 "opportunistic cleanup"。

方案 A 降级为 post-launch V2 治理项（与 §11 体例一致）。

> **概念重置不靠文件名，靠纸面与文案**：§4 的口径写死、指标词典登记、运行手册更新、页面标题改为「月度利润看板」，这四处足以消除认知偏差。

### 6.2 接口清单

| 方法 | 路径 | 作用 | 状态 |
|---|---|---|---|
| GET | `/api/finance/monthly-profit-settlement?period_month=YYYY-MM` | 看板聚合数据（结果区 + 店铺分布 + 调整项） | 改造（原返回 summary+details，改为看板 payload） |
| POST | `/api/finance/monthly-profit-settlement/adjustments` | 新增人工调整项（**唯一写入口**，reason 必填） | 新增 |
| DELETE | `/api/finance/monthly-profit-settlement/adjustments/{id}` | 删除人工调整项 | 新增 |
| — | `/rebuild`、`PUT /{id}/targets`、`POST /{id}/approve`、`POST /{id}/reopen` | 自算 + 目标比例 + 审批 + 回退 | **删除** |

所有端点声明 `response_model`，Pydantic 契约放 `backend/schemas/monthly_profit_settlement.py`（AGENTS.md 要求）。

### 6.3 service 内部改造（逐函数）

| 函数 | 处置 |
|---|---|
| `_load_net_profit_amount`（`:137-183`） | **改造**：保留利润基数去重逻辑（`:149-164`）；**删除 `:168-183` 的公司池二次扣减**（公司在利润基数里已扣过） |
| `_load_personnel_payload`（`:185-222`） | **改造（不是删除）**：加 `calculation_version = LABOR_COST_CALCULATION_VERSION` 过滤；只取 `performance_amount + commission_amount`；**同时产出总额与每店 breakdown**（`allocation_scope='shop'`）；`pre_commission_amount` 不取 |
| `_load_snapshot_personnel_details`（`:362-393`） | **删除**（快照口径的重复扣减来源） |
| `load_snapshot_settlement_view`（`:395-451`）、`get_next_snapshot_version`（`:452-467`）、`mark_active_snapshots_superseded`（`:468-...`）、`_load_personnel_details`（`:276-300`） | **删除**（快照机制整体下线后全部悬空） |
| `_load_follow_payload`（`:224-263`）、`_load_follow_details`（`:302-324`） | **删除**（跟投下线） |
| `build_summary`（`:66-135`） | **改造**：删除三个 `*_target_ratio` / 三个 `*_target_amount` / `difference_amount` / `difference_ratio` / `follow_actual_amount` / `approved_by`；保留 `net_profit_amount`、三个 `*_actual_amount`、新增 `company_retained_amount` 与 `allocation_ratio` |
| `approve`（`:925-978`）、`reopen`（`:980-1013`）、`invalidate_settlement_performance`（`:1015-1039`） | **删除**（审批制下线；同时消除反向改写上游） |
| `update_targets`（`:864-923`） | **删除** |
| `rebuild_month`（`:685-...`） | **改造**：不再重算人员成本、不再写目标比例、不再写跟投明细；改为"确保该月台账行存在 + 写调整项" |
| `get_month`（`:790-862`） | **改造**：改为直接返回看板 payload，不再读快照、不再调 `load_snapshot_settlement_view` |
| `_upsert_settlement`（`:650-681`） | **改造**：字段白名单改为新口径字段（去掉 9 个已废弃列），否则 `payload[field]` 会 KeyError |
| `build_settlement_snapshots` | **删除**（快照机制整体下线，见 §6.5） |
| `get_dashboard(period_month)` | **新增**：只读聚合，唯一算术实现处 |
| `add_adjustment` / `remove_adjustment` | **新增**：唯一写入口，`reason` 缺失直接 400。⚠️ `MonthlyProfitAdjustment` ORM **没有 `period_month` 字段**（`business.py:2175-2197`，只有 `settlement_id` 外键），按月取调整项必须 join `MonthlyProfitSettlement`（`period_month` 唯一键 `:2098`） |

### 6.4 数据表处置（**零表结构变更**）

`finance.monthly_profit_settlements`（`business.py:2056-2101`）全部字段都有 `default=0.0` 且 `nullable=False`，唯一约束是 `period_month`（`:2098`）。

⇒ **保留该表作为"月度台账主记录"**：看板写调整项前，按 `period_month` upsert 一条主记录（其余字段取默认 0），调整项继续挂 `settlement_id` 外键。**无需任何表结构变更，也不存在 NOT NULL 外键断裂问题。**

| 表 | 处置 | 阶段 |
|---|---|---|
| `finance.monthly_profit_settlements` | **保留**，语义改为"月度台账主记录"，只写 `period_month` 与调整汇总 | 一 |
| `finance.monthly_profit_adjustments` | **保留**，继续用 `settlement_id`；新增写入路径 `reason` 必填、拆掉 default 兜底 | 一 |
| `finance.monthly_profit_personnel_details` | 停止写入 | 一 |
| `finance.monthly_profit_payroll_snapshots` | 停止写入 | 一 |
| `finance.monthly_profit_shop_basis_snapshots` | 停止写入 | 一 |
| `finance.monthly_profit_employee_commission_snapshots` | 停止写入 | 一 |
| `finance.monthly_profit_employee_performance_snapshots` | 停止写入 | 一 |
| `finance.monthly_profit_follow_details` | **drop**（跟投 FK 阻塞点） | 一（随跟投下线） |
| `finance.follow_investments` / `follow_investment_settlements` / `follow_investment_details` | **drop** | 一（随跟投下线） |
| 上述 5 张停止写入的快照表 | **drop** | 三（历史导出确认后） |
| `settlements` 表的 9 个 target/actual/difference 列 | **drop**（语义已废弃） | 三 |

**调整项字段契约**（`adjustment_type` 取值域必须定义清楚，现仅有 `"manual_adjustment"`）：

| 字段 | 契约 |
|---|---|
| `adjustment_type` | 枚举：`manual_adjustment`（人工调整）/ `cross_period_expense`（跨期费用）/ `one_off_gain_loss`（一次性损益）/ `correction`（错账更正）。**新增取值必须同时更新此处与词典** |
| `amount` | 有符号。正数 = 从公司留存中扣减（减少留存），负数 = 追加（增加留存）。看板展示时明示符号含义 |
| `reason` | **服务端禁止 default 兜底**；缺失直接 400。历史行由人工补齐（迁移不加 NOT NULL，应用层禁写空值） |
| `created_by` | 取当前登录用户标识，服务端写入，不接受前端传值 |

### 6.5 快照与归档：本期不做

看板读的是**历史月份的事实行**（利润基数、工资单、提成、分摊表都是按月存的），所以历史月份天然可复现，**不需要额外归档机制**。

唯一代价：若上游事后修正了某月数据，该月看板数字会随之变化。

> ⚠️ **但本设计自身会改变历史数字**（因为修正了重复扣减与公司池双扣）。因此上线时必须附一份「口径切换前后同月对比」（用 §10 风险 #1 的只读体检脚本产出），并在上线说明里写明：**切换后所有历史月份的公司留存数字都会变化**。这是修正，不是回归，必须提前向管理层说明。

若将来业务明确要求"关账后数字不可变"，再单独设计归档快照（可复用 `monthly_profit_payroll_snapshots` 结构）。本期 YAGNI。

---

## 7. 前端设计

### 7.1 现状问题（具体到代码）

| 问题 | 位置 |
|---|---|
| 一个页面混了公司月结、店铺利润口径、跟投试算、跟投记录、结算台账、异常提示、店铺概览 | `frontend/src/domains/business/views/FinancialManagement.vue`（541 行） |
| store 混两个域，跟投占约 56% | `frontend/src/stores/financeSettlement.js`（215 行，16 个 action，跟投 9 个；4 个跟投切片） |
| 「预算(%)」文案绑定的是 0–1 小数，UI 语义与数据单位不一致 | `frontend/src/domains/business/views/finance-settlement/MonthlySettlementPanel.vue:14-22` |
| 调整项前端是「总额 + 原因」两字段，后端是**明细行**（类型 + 金额 + 原因 + 操作人） | `MonthlySettlementPanel.vue:23-28` vs `MonthlyProfitAdjustment`（`business.py:2175-2192`） |
| 审批 / 回退失败不进 `el-alert` | `frontend/src/stores/financeSettlement.js:120-136` |
| 阈值 3000 元 / 1% 前端后端各硬编码一份 | `frontend/src/domains/business/views/FinancialManagement.vue:143` / `backend/services/monthly_profit_settlement_service.py:48-49` |
| 跳转路由标题乱码 | `frontend/src/router/index.js:307` `'??????'` |
| 页面标题与菜单显示名仍是旧概念 | `frontend/src/router/index.js:129`「财务管理」、`frontend/src/config/menuGroups.js:82` 与 `:236`「财务结算中心」 |

### 7.2 新信息架构

```
/financial-management   （标题改为「月度利润看板」，路径不变）
└─ FinanceDashboardView.vue
   ├─ 顶部工具条：月份选择器 · 数据截止时间(as_of) · 导出
   ├─ A 区 本月结果（ProfitOverviewCards.vue）
   │    净利润 / 绩效工资 / 提成 / 员工侧分配 / 人工调整 / 公司留存
   │    + 分配占比 + 超额分配标记
   ├─ B 区 店铺分布（ShopAllocationTable.vue）
   │    每店：利润基数 · 绩效工资 · 提成 · 分配额 · 分配占比 · 异常标记
   └─ C 区 人工调整（AdjustmentPanel.vue）
        调整项列表 + 录入弹窗（类型 · 金额 · 必填原因）
```

**明确移除的交互**：三个「预算(%)」输入框、目标额保存、审批通过、回退草稿、跟投试算、跟投记录、差异告警。

### 7.3 前端设计原则

1. **只读优先**——唯一输入是人工调整项；其余全部是展示
2. **负数必须可见**——结算系数最高 1.2（`performance_coefficient.py:35-51`），在「可分配利润率 = 1、员工在该店提成比合计 = 1」的极端配置下，单店分配额理论上可达利润基数的 1.2 倍；再叠加不占利润基数的绩效工资，公司留存为负是设计内可能。看板不能把负数截断为 0，必须显红
3. **不承载口径**——前端不重算任何金额（不重算留存、不重算占比），只渲染后端给的数
4. **不替人下结论**——超额标记只渲染后端给的两个数 + 一句中性提示（如"本月分配已超过利润"），**不在前端生成判断性文案**
5. **状态统一**——加载 / 空态 / 错误一律进 `el-alert`，中文文案
6. **单位一致**——金额统一千分位 + 币种符号；百分比字段一律 0–1 存储、展示时统一格式（不再出现"标签写 %、值域 0–1"的不一致）
7. **人工调整可见**——只要调整项数 > 0，结果区必须显示「含 N 笔人工调整」角标与总额

---

## 8. SSOT 三律合规审查

依据 `docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md:344-348`。

### 律 1｜真源只能有一个，而且必须写在纸上

| 检查项 | 判定 | 说明 |
|---|---|---|
| 各类金额的唯一真源表 | ✅ | §4.2 表格逐项写死，含 `finance.employee_labor_cost_allocations` |
| 口径版本由既有常量/规则决定，不另写一套 | ✅ | 分摊表用 `LABOR_COST_CALCULATION_VERSION` 等值过滤；利润基数复用 `is_legacy_a_only_basis_version` 去重规则 |
| 「谁是台账 / 谁是派生 / 谁只是快照」写死 | ✅ | §4.2 + §4.3 + §6.4 三张表分别标注 |
| 指标进入指标词典 | ⚠️ **需先解决副本分叉** | §4.5 实测 7 文件中 4 个不一致，必须先对齐再登记 |
| **成文口径冲突已消除** | ⚠️ **需业务签字** | `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md:252` 现写着「月结人员成本以工资单为最终结算口径」、`:266-269` 写着「payroll_records.total_cost 已包含底薪、绩效、提成…因此月结人员成本不应再单独汇总…当前是公司级总成本直接入账」。**本设计判定该口径为重复扣减并推翻它**——这是口径反转，必须由业务签字并在运行手册改写，不能当实现细节处理 |

**结论：满足，但有两个前置项——词典副本对齐 + 口径反转签字。**

### 律 2｜真源只能由「人」落笔，自动流程只能提案

| 检查项 | 判定 | 说明 |
|---|---|---|
| 看板不反向改写上游 | ✅ | `invalidate_settlement_performance()`（`:1029` 改写 `is_locked`）随审批删除一并移除 |
| 唯一可写对象由人录入且带原因 | ✅ | §4.4：拆掉 `reason` 的 default 兜底（现状 `:773`、`:907-908`），缺 reason 直接 400 |
| 自动流程不产生"人该确认"的结论 | ✅ | 看板只呈现事实与标记，超额只标记不代替人决策 |

**结论：满足。**

### 律 3｜派生层只能有一份口径，且机器可验证

| 检查项 | 判定 | 说明 |
|---|---|---|
| 看板聚合唯一实现 | ✅ | 三条算术只在 `monthly_profit_settlement_service.py`，前端不复刻 |
| 删除重复口径 | ✅ | `_load_snapshot_personnel_details`（快照口径）与 `build_summary` 的目标额/差异算法双双删除 |
| 每店 breakdown 有合法来源 | ✅ | 唯一来源是人力成本分摊表（`business.py:1853-1922`），已写入 §4.2 |
| 机器可验证 | ✅ | 对账断言：**看板各店 breakdown 的 `profit_basis_amount` 之和 == `net_profit_amount`**（每店利润基数与净利润取自同一份去重后的利润基数行）。员工侧分配额 == Σ分摊表(`performance_amount + commission_amount`)，**含 `company` scope**；而 breakdown **只收 `shop` scope** ⇒ breakdown 的分配额之和 **≤** 员工侧分配额，差额即总部/仓库人员分走的那部分（不可按店归属）。⚠️ 注意 `c_class.employee_commissions` 是员工粒度唯一键（`business.py:4878-4880`），**无法按店汇总**，只能做员工维度总额交叉校验 |

**结论：满足。**

### 合规总评

方案满足 SSOT 三律。**两个前置阻塞项**：①指标词典两份副本已分叉，必须先对齐再登记；②运行手册的既有成文口径被本设计推翻，需业务签字后改写。

---

## 9. 变更范围与验证路径

依 `PRE_LAUNCH_RULES.md:28-33`「每任务声明四要素」与 `:35`「跨不超过 3 个主要模块，否则拆分」。

### 阶段 1a｜跟投下线 · 数据库

- **解决**：移除三张跟投表与被其外键卡住的 `monthly_profit_follow_details`
- **变更**：新增下线迁移（drop 4 张表）；更新 `current_migrations` 基线与 `scripts/verify_production_migration_contracts.py`
- **不动**：其余全部 `finance.*` 表、上游各链路
- **验证**：`python scripts/verify_production_migration_contracts.py`（⚠️ 需可连 PostgreSQL，见前置条件）；`python scripts/verify_architecture_ssot.py`（ORM 变更）

### 阶段 1b｜跟投下线 · 后端

- **解决**：移除跟投服务 / 路由 / schema / 审批模板 / 权限点 / 投资人角色 / 月结内跟投读取
- **变更**：§5.1 后端清单；`backend/services/approval_center_service.py` 删跟投 4 处 + 月结审批 4 处（见阶段 2b）
- **不动**：工资 / 提成 / 绩效 / 成本 / 利润口径链路
- **验证**：`pytest backend/tests/ -q -k follow_investment`（应无匹配用例）；后端失败集差异（junit）

### 阶段 1c｜跟投下线 · 前端 + 测试 + 文档

- **解决**：移除跟投页面 / 路由 / 菜单 / API / store 切片 / 测试 / 文档登记
- **变更**：§5.1 前端 + 测试 + 文档清单
- **不动**：看板本身（阶段 2）
- **验证**：`vite build`；`python scripts/verify_utf8_source_hygiene.py`（Windows 下改前端模板）；`python scripts/verify_rules_completeness.py`（文档变更）；前端 menu 快照测试

### 阶段 2a｜看板化 · 后端

- **解决**：三个金额缺陷 + 版本过滤缺陷
- **变更**：`backend/services/monthly_profit_settlement_service.py`（§6.3）、`backend/domains/business/routers/monthly_profit_settlement.py`（§6.2）、`backend/schemas/monthly_profit_settlement.py`（新增看板 payload 与调整项契约，删 rebuild/targets 契约）、`backend/routers/monthly_profit_settlement.py`（legacy wrapper 同步）
- **不动**：上游工资 / 提成 / 绩效 / 成本 / 利润口径链路（**一行不改**）
- **验证**：`pytest backend/tests/test_monthly_profit_settlement_service.py -q`（现有 18 例）+ 新增 `backend/tests/test_finance_dashboard_service.py`；`pytest backend/tests/test_profit_basis_service.py -q`（现有 22 例）；失败集差异 `python -m pytest <target> -q --tb=no --junitxml=after.xml` + `python scripts/diff_pytest_junit.py before.xml after.xml`（仓库有既存失败基线，**必须用差异集证明无新增失败**）；若差异报出单条新失败，须按 `VERIFICATION_MATRIX.md:29-33` 在基线修订上用相同 test set 复现后再判定

### 阶段 2b｜看板化 · 前端

- **解决**：前端老旧设计（表单→看板、拆巨石页、拆 store）
- **变更**：`frontend/src/domains/business/views/finance-dashboard/`（新建）、`frontend/src/stores/financeDashboard.js`（新建）、`frontend/src/api/finance.js`、`frontend/src/router/index.js`、`frontend/src/config/menuGroups.js`、删除 `frontend/src/domains/business/views/finance-settlement/` 与 `frontend/src/stores/financeSettlement.js`
- **不动**：后端接口契约（阶段 2a 已定）、上游各链路
- **验证**：`vite build`；`python scripts/verify_utf8_source_hygiene.py`；前端 store / 组件单测

### 阶段 2c｜看板化 · 指标词典与文档

- **解决**：口径写在纸上（律 1）
- **变更**：`docs/team-skills/sea-metrics-language/`（6 个指标登记）→ 同步 `team-skills-bundle/sea-metrics-language/` → 跑 SHA256 校验 7/7 一致 → 新增指纹校验脚本；`docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md` 改写三处过时口径；`docs/guides/APPROVAL_CENTER_RUNBOOK.md`、`docs/guides/ENGINEERING_STATUS.md`、`CHANGELOG.md`
- **不动**：历史归档文档（`docs/superpowers/specs|plans/` 下 2026-04/05 的设计稿）
- **验证**：`python scripts/verify_rules_completeness.py`；`python scripts/verify_root_md_whitelist.py`（文档政策变更时）；SHA256 比对脚本

### 阶段 3｜旧结构清理

- **解决**：移除已停写的 5 张快照表与废弃列
- **变更**：drop `monthly_profit_personnel_details` / `monthly_profit_payroll_snapshots` / `monthly_profit_shop_basis_snapshots` / `monthly_profit_employee_commission_snapshots` / `monthly_profit_employee_performance_snapshots`；drop `settlements` 表 9 个废弃列
- **前置**：旧月结历史（生产仅 2026-03 一条 approved）已导出留存
- **不动**：全部上游链路
- **验证**：`python scripts/verify_architecture_ssot.py`；迁移契约脚本；后端全量失败集差异

---

## 10. 风险与未决项

| # | 风险 / 未决 | 处置 |
|---|---|---|
| 1 | **未连库**：生产哪些月份存在新旧双份行、重复扣减的实际金额规模，均未实测 | 阶段 2a 前先跑只读体检（各店利润基数版本分布、重复扣减金额），并产出"口径切换前后同月对比" |
| 2 | **生产数据不可验金额**：生产人力成本分摊表与归属表 0 行、工资单 31 张中 23 张卡 draft | 金额口径验证以本地库为准；生产只验结构。**当前生产可见症状是"快照口径独扣"而非"重复扣减"**（见 §2.1 前提条件） |
| 3 | **词典副本分叉**（7 文件中 4 个不一致） | 阶段 2c 前置项，先对齐 + 加指纹脚本 |
| 4 | **运行手册成文口径被推翻**（`MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md:252, 266-269`） | 需业务签字；签字后改写运行手册 |
| 5 | **跟投表实际行数未知** | 下线迁移前 `SELECT count(*)` 确认 |
| 6 | **旧月结历史**（生产仅 2026-03 一条 approved） | 阶段 3 drop 前先导出留存 |
| 7 | **`MonthlyProfitAdjustment.reason` 改必填** | 拆 default 兜底；历史行人工补（迁移不加 NOT NULL，应用层禁写空值） |
| 8 | **`investor` 角色去留** | 本方案建议一并下线（见 §5.1），需业务确认 |
| 9 | **看板数与 HR 页面数可能不一致** | `backend/domains/business/routers/hr_commission.py:1576-1578`（漏乘结算系数）与 `backend/services/monthly_settlement_service.py:239-255` 各自按同一公式重算提成，与真源算法不同。**画界后仍有两份口径在上线展示**——登记为已知风险，随 §11 治理项一并收敛 |
| 10 | **看板 GET 一次返回全店 breakdown** | 需在一次 `READ COMMITTED` 事务内读三张表，保证 `as_of` 一致；总额与 breakdown 必须对账相等；给 breakdown 行数上限或按平台过滤参数 |
| 11 | **`/financial-overview` 路由标题乱码**（`frontend/src/router/index.js:307`） | 阶段 2b 顺手修（一行） |

---

## 11. 遗留待办（post-launch V2）

**交付物：** 本节 7 条须写成独立计划文件 `docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md`（**本次实施必须产出该文件**，否则等于把治理项丢进虚空）。本次不实施以下内容：

1. **后端模块重命名**（本设计的方案 A）：`monthly_profit_settlement_*` → `finance_dashboard_*`，URL 改名
2. 提成链路 5 处第二实现收敛（`backend/domains/business/routers/hr_commission.py:1468-1603`、`:2170-2427`、`backend/services/monthly_settlement_service.py:217-255`、`backend/services/payroll_confirmation_service.py:110-117`、两个利润基数加载器）
3. 绩效系数统一（逐店 min vs 加权平均；`backend/services/performance_coefficient.py:1-26` 的 SSOT 声明与实现不符）
4. 提成缺失对账断言（人维度总额 == 店维度合计）
5. 补 `backend/services/performance_coefficient.py`、`backend/services/monthly_settlement_service.py` 的单测（当前零测试）
6. `docs/guides/PERFORMANCE_RACING_POLICY.md` 第五节「个人销售目标 = Σ(店铺目标×目标分配比例)」无对应实现
7. 前端 `frontend/tests/` 未挂 npm script

---

## 12. 审查修订记录

2026-11-21 独立审查（verifier）发现 13 处事实问题 + 5 处 SSOT 判定问题 + 5 处仓库规则问题 + 11 处设计缺口。第二版已全部处理：

**事实更正**：提成真源 schema `a_class` → **`c_class`**（`business.py:4846, 4883`）；旧表清单 5 张 → **8 张**（补 `follow_details` / `shop_basis_snapshots` / `employee_commission_snapshots` / `employee_performance_snapshots`）；跟投服务"只读"表述 → **"不回写上游利润基数"**；阶段编号矛盾 → 统一为 §9 的 1a/1b/1c/2a/2b/2c/3；测试清单 12 → **≥17 个文件**；store 切片/动作 5+11 → **4 切片 / 9 action**；词典分叉范围 → **7 文件中 4 个不一致**，行数 481/360；审批中心行号 → **补 `:242-271`**；后端文件数 → **5 个**（补 legacy wrapper）；"1.2 倍"改为**带前提的理论上界**；文件路径补全前缀。

**设计更正（最重要）**：**每店 breakdown 原方案无源**——`c_class.employee_commissions` 与 `a_class.payroll_records` 均无店铺维度。改为：`finance.employee_labor_cost_allocations` 是员工侧分配额（总额 + 每店）的**唯一真源**，`_load_personnel_payload` 由"删除"改为"**改造**"（加版本过滤 + 只取 performance/commission + 产出 breakdown）。

**合规更正**：方案 A 由"推荐"降级为 **post-launch V2**，本期走方案 B；阶段按 `PRE_LAUNCH_RULES.md:35` 拆为 7 个子阶段；补齐 `verify_architecture_ssot.py` / `verify_utf8_source_hygiene.py` / `verify_rules_completeness.py` 等验证项；新增"运行手册口径反转需业务签字"风险；`reason` 必填改为"拆 default 兜底 + 缺失即 400"；超额标记文案改为"只渲染后端数值 + 中性提示"。

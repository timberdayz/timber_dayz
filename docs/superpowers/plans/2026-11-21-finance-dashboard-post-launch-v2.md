# 月度利润看板 · Post-Launch V2 治理计划

> 起草：2026-11-21 ｜ 状态：**未来工作清单，本轮一律不做**
> 关联实施计划：`docs/superpowers/plans/2026-11-21-finance-profit-dashboard.md`
> 关联设计：`docs/superpowers/specs/2026-11-21-finance-profit-dashboard-design.md`
> 关联运行手册：`docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`

本文件**不是本轮要做的活**。它是「月度利润看板」改造过程中被识别出来、
但**故意不在本轮做**的技术债清单。目的是让这些债**有出处、有证据、有范围**，
避免它们在后续迭代里被人「顺手改掉」或者悄悄继续腐化。

⚠️ **本轮为什么不做的统一依据**：

- `docs/guides/PRE_LAUNCH_RULES.md:19-20` —— 「Broad refactors that are not required for launch.」
  /「Large directory moves or cross-module renames.」
- `docs/guides/PRE_LAUNCH_RULES.md:39` —— 「Record non-blocking technical debt for the post-launch V2 rebuild.
  Do not hide opportunistic cleanup inside launch fixes.」
- `docs/guides/PRE_LAUNCH_RULES.md:41-45` —— 指定的归档去处就是 `docs/superpowers/plans/`（**本文件**）。

---

## 0. 一页摘要

| # | 主题 | 一句话 | 严重度 | 本轮为什么不做 | 预估范围 |
|---|---|---|---|---|---|
| V2-01 | 后端 / 前端模块重命名 | 模块名仍叫 `monthly_profit_settlement`，但它已经是一块只读看板 | 低 | `PRE_LAUNCH_RULES.md:19-20` 禁止跨模块改名；且改名与消灭金额缺陷无因果关系 | 1 个迭代 |
| V2-02 | 提成链路 5 处第二实现 | 同一笔提成有 5 套算法，其中 1 套漏乘结算系数 | **高** | 属架构收敛，不阻塞看板上线 | 2-3 个迭代 |
| V2-03 | 绩效系数统一 | SSOT 声称「一个系数同时决定绩效工资和提成」，实际两边算法不同 | **高** | 改动会直接动工资单金额，需业务拍板 + 单测兜底 | 1 个迭代（+ 业务确认） |
| V2-04 | 提成缺失对账断言 | 全仓没有「人维度总额 == 店维度总额」的断言 | 中 | 断言要挂在收敛后的实现上（见 V2-02） | 小（0.5 天） |
| V2-05 | 补单测 | 系数 SSOT 与月度结算单服务都**没有直接单测** | 中 | 本轮只补看板相关测试 | 小（1 天） |
| V2-06 | 个人销售目标公式无实现 | 赛马政策第五节写的公式在代码里找不到对应实现 | 中 | 需要业务先决定「要不要按比例分」 | 中（2-3 天 + 业务确认） |
| V2-07 | 前端 `frontend/tests/` 未挂脚本 | 20 个前端测试文件没有任何 npm 入口能跑它们 | 中 | 纯工程基建，可独立排期 | 小（0.5 天） |

**执行顺序建议**：`V2-05` → `V2-02` → `V2-04` → `V2-03` → `V2-01` → （`V2-06`、`V2-07` 可并行）。

> **执行计划已落地（2026-11-21）**：`V2-02` / `V2-03` / `V2-04` / `V2-05` 四条
> 已合并为一份带批次与守护测试的执行计划
> —— `docs/superpowers/plans/2026-11-21-commission-and-performance-caliber-unification.md`
> （含 ADR：`docs/adr/2026-11-21-commission-and-performance-caliber-layering.md`）。
> 业务已拍板口径：**提成零系数、绩效工资用纯个人分数档位系数、赛马不参与任何金额**。
> 该计划补上了本文件末尾所缺的**实测金额影响面**（2026-10 员工侧分配额 +425.20，已按生产公式校准）。

---

## 1. V2-01 后端 / 前端模块重命名

### 1.1 问题描述

「月度利润结算中心」被改造成只读的「月度利润看板」之后，**后端代码里的名字全都没动**：
service、schema、router、URL 仍叫 `settlement`。
后果是：新人搜「dashboard」找不到看板，看板后端代码里却全是「结算 / settlement」；
文档与代码名长期不一致，二次交接成本高。

> **本轮改造后的消解情况**：**前端**那部分已经顺手做掉了 —— 目录改成
> `frontend/src/domains/business/views/finance-dashboard/`（4 个新组件），
> store 改成 `frontend/src/stores/financeDashboard.js`，
> 旧的 `finance-settlement/` 与 `financeSettlement.js` 已删除。
> ⇒ **V2-01 现在只剩「后端 3 个文件 + URL 前缀」这一项**（见 §1.2 表末两行）。

### 1.2 证据路径（带行号）

| 现状路径 | 目标路径 | 证据 |
|---|---|---|
| `backend/services/monthly_profit_settlement_service.py`（559 行） | `backend/services/finance_dashboard_service.py` | 文件存在，559 行 |
| `backend/schemas/monthly_profit_settlement.py`（109 行） | `backend/schemas/finance_dashboard.py` | 文件存在，109 行 |
| `backend/domains/business/routers/monthly_profit_settlement.py`（95 行） | `backend/domains/business/routers/finance_dashboard.py` | `:21-22` `APIRouter(prefix="/api/finance/monthly-profit-settlement", tags=["monthly-profit-settlement"])` |
| URL `/api/finance/monthly-profit-settlement` | `/api/finance/dashboard` | 同上 `:21-22` |
| `frontend/src/domains/business/views/finance-dashboard/` | `frontend/src/domains/business/views/finance-dashboard/`（**已改名，V2-01 只剩后端与 URL 改名**） | 现含 `FinanceDashboardView.vue`、`ProfitOverviewCards.vue`、`ShopAllocationTable.vue`、`AdjustmentPanel.vue`（旧 `finance-settlement/` 与 `MonthlySettlementPanel.vue` / `SettlementWorkspacePanel.vue` 已随看板化删除） |
| `frontend/src/stores/financeDashboard.js` | `frontend/src/stores/financeDashboard.js`（**已改名，V2-01 前端项已消解**） | 文件存在（旧 `financeSettlement.js` 已随看板化删除并由本文件替代） |

> ⚠️ **行数/行号口径**：上表行数与行号是 **2026-11-21 实测快照**（行数按 UTF-8 换行计）。
> 本轮改造做过 ORM 清理与 `black` 格式化，**行号已随之漂移** —— 执行 V2 前请以代码为准重新定位，
> 不要直接拿本表行号当锚点。

### 1.3 影响面

- 后端：service / schema / router / URL 前缀 / `tags`；引用方 `backend/domains/business/routes.py`、
  `backend/routers/monthly_profit_settlement.py`（legacy wrapper）。
- 前端：API 层 `frontend/src/api/finance.js`、菜单 `frontend/src/config/menuGroups.js`、
  路由 `frontend/src/router/index.js`、编排页 `frontend/src/domains/business/views/FinancialManagement.vue`。
- **URL 改名会破坏**：已收藏的旧链接、外部调用方、可能的权限点键名。
- 测试：`backend/tests/test_monthly_profit_settlement_*.py`、`backend/tests/test_financial_settlement_page_contract.py`
  等需要同步改名。

### 1.4 预估范围

3 个后端文件 + 1 个 URL 前缀 + API / 菜单 / 路由 / 权限点核对 + 相关测试改名与回归
（**前端目录与 store 已在本轮完成改名，不在 V2-01 范围内**）。
**约 1 个迭代**，且必须安排**旧 URL 的过渡期**（保留旧路由一段时间并转发/告警），否则会打断在用页面。

### 1.5 与其他条目的关系

- 与 V2-02 **有顺序依赖**：先收敛提成第二实现，再改名；否则要在 5 套实现里挑一套搬家，
  搬错了还要再搬一次。
- 与 V2-07 **有交叉**：前端测试放 `frontend/tests/` 还是 `frontend/scripts/`，改名时要一起定。
- **本轮不做的原因**：`PRE_LAUNCH_RULES.md:19-20` 明令禁止「Large directory moves or cross-module renames」；
  且重命名与本轮要消灭的**金额缺陷**没有因果关系，属于 `PRE_LAUNCH_RULES.md:39` 所说
  「Do not hide opportunistic cleanup inside launch fixes」的那类活。

---

## 2. V2-02 提成链路 5 处第二实现收敛

### 2.1 问题描述

「员工提成 = 利润基数 × 可分配率 × 提成比 × 结算系数」这一条公式，在仓库里被**独立实现了 5 遍**。
5 遍之间并不完全等价：其中 1 遍漏乘结算系数，1 遍在同一个响应里同时给出两个口径，
还有 1 遍在自称「不做任何二次计算」的模块里又算了一遍。任何一处漂移都会直接变成工资单上的错数。

### 2.2 证据路径（带行号）

**第 1 处 —— `backend/domains/business/routers/hr_commission.py:1468-1603`（`GET /commissions/shop`）漏乘结算系数**

```text
backend/domains/business/routers/hr_commission.py:1576-1578
    commission_amount = (
        max(profit_basis_amount, 0.0) * allocatable_rate * total_ratio
    )
```

对照 SSOT（`backend/services/performance_coefficient.py:93-101` 的 `calculate_settlement_coefficient`）
与工资单实发口径（`backend/services/hr_income_calculation_service.py:1657-1662`，**乘了** `settlement_coefficient`），
这一处少乘一个因子 ⇒ 该接口返回的「店铺提成」与工资单实发对不上。

**第 2 处 —— `backend/domains/business/routers/hr_commission.py:2170-2427`（`GET /shop-profit-statistics`）同响应并列两套口径**

```text
backend/domains/business/routers/hr_commission.py:2267-2284   取含结算系数的 settlement_commission_by_shop
backend/domains/business/routers/hr_commission.py:2350-2358   另算不含结算系数的 estimated_total_commission
backend/domains/business/routers/hr_commission.py:2382-2388   同一响应里两个字段并列返回 + 一句 note 解释
```

注释 `:2268-2269` 自己承认：「上面那两个『主管/操作员提成』是**不含结算系数**的分摊额，
和工资单实发对不上 —— 页面必须同时能看到两个口径，别让运营去猜。」
**把两套口径并列塞进同一个响应，是把口径分歧转嫁给使用者**，不是收敛。

**第 3 处 —— `backend/services/monthly_settlement_service.py:217-255`（第 4 套，自称不二次计算却做了二次 min + 重算提成）**

```text
backend/services/monthly_settlement_service.py:15-17
    **这里不做任何二次计算**：所有金额直接取已落库的结果，
backend/services/monthly_settlement_service.py:367
    # 这里不做任何二次计算 —— 页面上看到的每一分钱都能对上账。
backend/services/monthly_settlement_service.py:239-246
    settlement_coefficient = min(shop_coefficient, score_coefficient)   # 自行再算一次 min
backend/services/monthly_settlement_service.py:249-255
    expected_commission_by_shop[key] = ... max(profit_basis_amount, 0.0) * alloc_rate * ratio * settlement_coefficient
```

模块自己声明「不做任何二次计算」，函数体里却把**系数与提成金额都重算了一遍**。
而且它自己那份 `min(...)` 没有复用 `performance_coefficient.py` 的 SSOT 函数，
将来 SSOT 改档位表，这里不会跟着改。

**第 4 处 —— `backend/services/payroll_confirmation_service.py:110-117`（归属提成比聚合的第 N 套）**

```text
backend/services/payroll_confirmation_service.py:110-117
    ratio_by_shop: Dict[tuple[str, str], float] = {}
    for assignment in month_assignments:
        ...
        ratio_by_shop[shop_key] = ratio_by_shop.get(shop_key, 0.0) + float(
            getattr(assignment, "commission_ratio", 0) or 0
        )
```

同一件事（按店聚合「归属提成比合计」）在
`backend/domains/business/routers/hr_commission.py:1559-1564`、
`backend/services/hr_income_calculation_service.py` 内部也各写了一遍。

**第 5 处 —— 两个「利润基数加载器」口径不一致**

| 加载器 | 过滤条件 | 缺行时行为 |
|---|---|---|
| `backend/domains/business/routers/hr_commission.py:1060-1125` | `:1074` `basis_version == basis_version`（等值）；`:1083-1084` **要求 `is_locked=True`** | `:1106-1111` 调 `build_profit_basis` **现算**一个 |
| `backend/services/hr_income_calculation_service.py:501-553` | `:520-522` `basis_version ∈ KNOWN_BASIS_VERSIONS`；`:532-535` 排除 legacy `A_ONLY_V1`；**不要求 `is_locked`** | 缺行就是缺行（`:548` 标 `missing_labor_allocation`） |

同一个「当月利润基数」，两处一个要锁定、一个不要锁定；一个缺行现算、一个缺行报错。
**这是看板「店铺利润基数」口径的前置分歧点** —— 看板读的是 `finance.shop_profit_basis`，
而这张表的写入时机受这两套加载器影响。

### 2.3 影响面

- 工资单提成金额（`PayrollRecord.commission`）
- `finance.employee_labor_cost_allocations.commission_amount`
  → 直接决定看板的 `employee_allocation_amount`（员工侧分配额）
- 店铺提成页（`GET /commissions/shop`）
- 店铺利润统计页（`GET /shop-profit-statistics`）
- 月度结算单页（`MonthlySettlementService.build`）
- 工资单确认（提成比合计 ≤ 100% 的校验）

### 2.4 预估范围

抽出一个**提成计算 SSOT**（放在 `backend/services/` 下，函数级纯函数优先），
5 处调用点全部改为调用它，删除第 2 处的双口径并列；补跨实现对账测试。
**约 2-3 个迭代**（第 3、4 处改动面比看上去大，因为它们在关键路径上）。

### 2.5 与其他条目的关系

- 是 **V2-03 的前置**：先把「提成到底怎么算」定死，再讨论「系数该不该统一」。
- 是 **V2-04 的载体**：收敛后才有地方挂总额守恒断言。
- 与 **V2-01 有顺序依赖**：先收敛，再改名。

---

## 3. V2-03 绩效系数统一

### 3.1 问题描述

`backend/services/performance_coefficient.py` 是明面上的**系数 SSOT**，
它的 docstring 第一句就写：「业务口径：**一个系数，同时决定「绩效工资」和「提成」**」。
但实际实现里，**绩效工资与提成用的是两套不同的算法**，数值可以不同：

| 用途 | 算法 | 证据 |
|---|---|---|
| 提成 | **逐店 min**（`min(店铺结算系数, 个人分数档位系数)`） | `backend/services/hr_income_calculation_service.py:1642-1646` |
| 绩效工资 | **按店铺销售额加权平均** | `backend/services/hr_income_calculation_service.py:1698-1702`，消费点 `:1810-1818` |

一个多店员工，逐店 min 的结果与加权平均的结果**必然不同**
（只有当各店系数全相等时才相等）⇒ SSOT 的承诺与实现不符。

### 3.2 证据路径（带行号）

```text
backend/services/performance_coefficient.py:1-26
    """统一结算系数（SSOT）。
    业务口径：**一个系数，同时决定「绩效工资」和「提成」**。
    ...
    员工结算系数 = min(该店结算系数, 员工分数档位系数)
    ...
    现在统一成一条链路：**页面看到的系数，就是工资单拿到的系数**。

backend/services/hr_income_calculation_service.py:1642-1646   # 提成：逐店 min
    settlement = describe_settlement_coefficient(
        shop_coefficient=shop_coefficient,
        score_coefficient=employee_score_coefficient,
    )
    settlement_coefficient = settlement["settlement_coefficient"]

backend/services/hr_income_calculation_service.py:1698-1702   # 绩效工资：加权平均
    employee_settlement_coefficient[employee_code] = (
        coefficient_num / coefficient_den
        if coefficient_den > 0
        else calculate_settlement_coefficient(employee_score_coefficient)
    )

backend/services/hr_income_calculation_service.py:1810-1818   # 加权平均值被当作绩效工资的结算系数
    settlement_coefficient = employee_settlement_coefficient.get(employee_code)
```

**列注释与实现不符**：

```text
modules/core/db/schema_parts/business.py:4660-4664
    performance_coefficient = Column(
        Float,
        nullable=True,
        comment="Unified settlement coefficient = min(rank band, score band)",
    )
```

注释写的是 `min(rank band, score band)`，描述的是**店铺级**的 min；
而绩效工资侧实际消费的是**员工级销售额加权平均**。注释与两处实现都对不上。

> ⚠️ **与任务描述的偏差**：任务描述把这条注释定位在
> `modules/core/db/schema_parts/business.py:4827`。初稿实测 `:4827` 是
> `user_notification_preferences.user_id` 列（`UserNotificationPreference` 表），
> 与系数无关。本条先更正为 `:4660-4664`；**2026-11-21 改造后（ORM 清理 + `black` 格式化）
> 该行号再次漂移** ⇒ 实测当前正确位置为 `:4426-4430`
> （`EmployeePerformance` 表 / `employee_performance` 的 `performance_coefficient` 列，
> 注释 `Unified settlement coefficient = min(rank band, score band)`）。
> 执行本条前请以代码为准重新定位。

### 3.3 影响面

- 工资单 `performance_salary`（绩效工资）金额
- 工资单 `commission`（提成）金额
- 店铺赛马系数 → 提成基数
- 看板 `employee_allocation_amount`（员工侧分配额）的绩效工资部分

### 3.4 预估范围

**需要业务先拍板**：绩效工资到底应该用「逐店 min」还是「销售额加权平均」？
拍板后：改 `backend/services/performance_coefficient.py` + `backend/services/hr_income_calculation_service.py`
的系数产出路径 + 修正列注释 + 补单测。
**约 1 个迭代 + 一次业务确认**。改这一条会**直接改变历史工资单金额**，必须配数据迁移/重算说明。

### 3.5 与其他条目的关系

- 依赖 **V2-02** 先收敛第二实现，否则改完 SSOT 仍有 5 处旧算法在跑。
- 依赖 **V2-05** 先有单测兜底 —— 这两个模块现在**一个测试都没有**（见 V2-05）。
- 与 V2-06 无关（那是个人目标，不是系数）。

---

## 4. V2-04 提成缺失对账断言

### 4.1 问题描述

**全仓没有任何一处断言**校验「按人汇总的提成总额 == 按店汇总的提成总额」。
两边各自算、算完就写库，中间没有任何交叉校验。
一旦某条路径漏算 / 多算，只能靠人工翻工资单才发现 —— 而看板的
`employee_allocation_amount` 正是直接建立在这些数字上的。

### 4.2 证据路径（带行号）

- 全仓搜索 `人维度|店维度|reconcil|对账`（`.py` / `.mjs` / `.js`）只命中
  库存对账（`backend/domains/business/routers/inventory_overview.py:101-113`、
  `inventory_domain.py:213-224`）、店铺身份对账（`backend/services/cloud_sync_identity_guard_service.py`）、
  云同步对账 —— **没有一处与提成总额有关**。
- 现有最接近的保护是**舍入尾差吸收**，它只保证「逐店明细加起来 == 员工总额」：

```text
backend/services/hr_income_calculation_service.py:1691-1696
    # 尾差吸收：提成**总额**是「各店未舍入金额累加后统一舍入一次」...
    _absorb_commission_rounding_residue(shop_coefficients, commission_amount)
```

- 断言应该落的位置（收敛后）：

```text
backend/services/hr_income_calculation_service.py:1663   commission_amount += allocation_amount
backend/services/hr_income_calculation_service.py:1696   _absorb_commission_rounding_residue(...)
```

在这两步之后断言「Σ 逐店明细 == 员工总额」，
再在跨员工维度断言「Σ 员工总额 == 当月落库提成总额」。

### 4.3 影响面

- `PayrollRecord.commission`
- `finance.employee_labor_cost_allocations.commission_amount`
- 看板 `employee_allocation_amount` 与 `company_retained_amount`

### 4.4 预估范围

**小**（约 0.5 天）：一个纯函数级的断言 + 一个跨实现的对账测试。
需要先定**差额容差**（建议 `0.01 元 / 人月`，与现有尾差吸收的舍入粒度对齐）。

### 4.5 与其他条目的关系

- 依赖 **V2-02**（断言要挂在收敛后的唯一实现上，否则会对着 5 套实现各断言一次）。
- 建议与 V2-02 **同一个 PR** 落地。

---

## 5. V2-05 补单测（系数 SSOT 与月度结算单服务）

### 5.1 问题描述

两个**被多处依赖、但没有一直接单测**的模块：

| 模块 | 行数 | 现状 |
|---|---|---|
| `backend/services/performance_coefficient.py` | 128 行 | `backend/tests/` 下**无** `test_performance_coefficient.py` |
| `backend/services/monthly_settlement_service.py` | 463 行 | `backend/tests/` 下**无** `test_monthly_settlement_service.py` |

⚠️ 注意别看错：`backend/tests/test_monthly_profit_settlement_service.py` 测的是
**另一个模块** `backend/services/monthly_profit_settlement_service.py`，
不是 `monthly_settlement_service.py`。

### 5.2 证据路径（带行号）

现有引用点（全部是「被调用」，没有一处在测）：

```text
backend/domains/business/routers/performance_management.py:80,83   from backend.services.performance_coefficient import (...)
backend/services/hr_income_calculation_service.py:47               from backend.services.performance_coefficient import (...)
backend/services/monthly_settlement_service.py:480                 from backend.services.performance_coefficient import calculate_score_coefficient
backend/domains/business/routers/hr_salary.py:67                   from backend.services.monthly_settlement_service import MonthlySettlementService
```

`performance_coefficient.py` 里全是**纯函数**（无 IO、无 DB），单测成本极低：

```text
backend/services/performance_coefficient.py:54-62    calculate_rank_band_coefficient
backend/services/performance_coefficient.py:65-71    calculate_score_coefficient
backend/services/performance_coefficient.py:83-90    calculate_ranked_performance_coefficient
backend/services/performance_coefficient.py:93-101   calculate_settlement_coefficient
backend/services/performance_coefficient.py:104-123  describe_settlement_coefficient
```

### 5.3 影响面

无直接运行时影响 —— 本条是**纯保护网**，目的是让 V2-03 / V2-02 改动有兜底。

### 5.4 预估范围

**小**（约 1 天）：档位表边界值 + `min` 组合 + `describe` 的 `limited_by` 归因；
月度结算单服务补「缺行 / 缺配置 / 系数缺失」三类降级路径测试。

### 5.5 与其他条目的关系

- 是 **V2-03 的前置**（改系数逻辑前必须先有单测）。
- 是 **V2-02 的验收凭据**（收敛后要能证明 5 处调用点行为一致）。

---

## 6. V2-06 个人销售目标公式在代码中无对应实现

### 6.1 问题描述

赛马政策第五节写了个人目标的计算公式，但**代码里找不到按这个公式算的实现**；
比例字段虽然存在，却被**硬锁成 100%**，且聚合时根本没乘它。

### 6.2 证据路径（带行号）

**文档侧**：

```text
docs/guides/PERFORMANCE_RACING_POLICY.md:55-62
    ## 五、个人绩效、提成和工资
    个人目标由员工承接的经营店铺目标汇总而来：
    个人销售目标 = Σ（负责店铺销售目标 × 目标分配比例）
    个人毛利目标 = Σ（负责店铺毛利目标 × 目标分配比例）
```

**代码侧 —— 比例被硬锁成 1.0**：

```text
backend/schemas/hr.py:999-1004        # EmployeeShopAssignmentCreate
    @field_validator("target_allocation_ratio")
    def target_allocation_must_be_shared(cls, v):
        if abs(v - 1.0) > 1e-9:
            raise ValueError("当前仅支持共同承接店铺目标，目标分配比例必须为100%")

backend/schemas/hr.py:1025-1030       # EmployeeShopAssignmentUpdate，同样限制
```

**代码侧 —— 快照时确实记了比例**：

```text
backend/services/personal_performance_workbench_service.py:389-394
    for assignment in employee_assignments:
        ...
        if float(getattr(assignment, "target_allocation_ratio", 0) or 0) <= 0 or target is None:
            continue
        self.db.add(PersonalPerformanceAssignmentSnapshot(
            ..., assignment_ratio_snapshot=assignment.target_allocation_ratio,
            ..., sales_target_amount_snapshot=target.target_amount))
```

**代码侧 —— 聚合时没有乘这个比例**：

```text
backend/services/hr_income_calculation_service.py:148-163
    for assignment in assignments:
        target = cls._to_float(cls._field(assignment, "sales_target_amount_snapshot", 0), 0.0)
        ...
        target_weight_total += target
        weighted_score_numerator += cls._to_float(score) * target
```

个人得分只把 `sales_target_amount_snapshot` 当**权重**用，
**从头到尾没有读 `assignment_ratio_snapshot`**。

⇒ 结论：文档公式 **没有对应实现**；而且比例恒为 1，即使乘了也是空转。
两个问题叠在一起：要么实现缺失，要么文档写了个永远等于恒等变换的公式。

### 6.3 影响面

- 个人绩效得分（`PersonalPerformanceEntry`）
- 绩效工资基数
- 个人目标展示（「我负责的店铺销售目标完成了多少」）

### 6.4 预估范围

**中**（2-3 天 + 业务确认）。两条路，必须业务选一条：

- **路线 A（改文档）**：业务确认「个人就是 100% 承接，不分摊」⇒ 把
  `docs/guides/PERFORMANCE_RACING_POLICY.md:60-61` 改成直接求和，并考虑下线
  `target_allocation_ratio` 字段（会牵动 `current_migrations`）。
- **路线 B（改代码）**：业务确认「要支持按比例分」⇒ 解锁 `backend/schemas/hr.py:999-1004` 的校验，
  在 `backend/services/hr_income_calculation_service.py:148-163` 真正乘上比例，
  并补「多员工共同承接同一店铺」的边界测试。

### 6.5 与其他条目的关系

- 与 V2-03 **无关**（一个讲系数、一个讲目标分摊），可独立排期。
- 与 V2-02 **弱相关**：都涉及「归属配置」这一层的语义，但改动面不重叠。

---

## 7. V2-07 前端 `frontend/tests/` 未挂 npm script

### 7.1 问题描述

`frontend/tests/` 下有 **20 个** `*.test.mjs` 测试文件，
但 `frontend/package.json` 的 `scripts` 里**没有任何一条**指向这个目录。
现有 `test:*` 脚本全部指向 `frontend/scripts/*.test.mjs`。

⇒ 这 20 个测试**跑不到**。CI 里执行的前端测试也不是它们。

### 7.2 证据路径（带行号）

```text
frontend/package.json  scripts 段
    "test:smoke-shared":              "node --test scripts/frontendSmokeShared.test.mjs",
    "test:shop-assignment-rules":     "node --test scripts/shopAssignmentRules.test.mjs",
    "test:my-income-view-model":      "node --test scripts/myIncomeViewModel.test.mjs",
    "test:target-route-split":        "node --test scripts/targetRouteSplit.test.mjs",
    "test:operation-target-formula":  "node --test scripts/operationTargetFormula.test.mjs",
    "test:performance-route-split":   "node --test scripts/performanceRouteSplit.test.mjs",
    "test:performance-payroll-lock":  "node --test scripts/performancePayrollLock.test.mjs",
    "test:collection-task-errors":    "node --test scripts/collectionTaskErrors.test.mjs",
    "test:shop-display":              "node --test scripts/shopDisplay.test.mjs"
    # 全部指向 scripts/，没有一条指向 tests/
```

`frontend/tests/` 实有 20 个文件（节选）：

```text
frontend/tests/authFlowSource.test.mjs
frontend/tests/authRecovery.test.mjs
frontend/tests/authSession.test.mjs
frontend/tests/businessOverviewInventoryBacklogUi.test.mjs
frontend/tests/hrMonthlySettlement.test.mjs
frontend/tests/hrSettlementDisplayRules.test.mjs
frontend/tests/hrShopAssignmentSettlementPreview.test.mjs
frontend/tests/hrShopCommissionConfigApi.test.mjs
...（共 20 个）
```

`frontend/package.json` 全文检索 `tests` → **0 命中**。

### 7.3 影响面

- 前端回归保护：20 个测试实际处于「写了但没人跑」的状态。
- **与本轮看板直接相关**：看板前端新增的契约测试若放进 `frontend/tests/`，
  默认不会被任何 npm 脚本执行 —— 容易误以为「有测试就等于有保护」。

### 7.4 预估范围

**小**（约 0.5 天）：加一条聚合脚本（例如 `test:unit` → `node --test tests/*.test.mjs`），
接进 CI；顺带确认这 20 个文件在当前代码下**是否真的全绿**（很可能会暴露存量失败，
那属于另一个独立问题）。

### 7.5 与其他条目的关系

- 与 V2-01 **有交叉**：前端目录重命名时要一并定「测试放 `frontend/tests/` 还是 `frontend/scripts/`」。
- 可与 V2-06 **并行**，互不依赖。

---

## 8. 本轮明确不做、也不许「顺手做」的部分

以下内容在 V2 落地前**不许**出现在本轮看板改造里：

- 任何模块 / 目录 / URL 的重命名（V2-01）
- 在看板层**新写**一套提成计算（会变成第 6 套实现，比现在更糟）
- 修改 `backend/services/performance_coefficient.py` 的档位表或算法（V2-03）
- 修改 `backend/schemas/hr.py` 的 `target_allocation_ratio` 校验（V2-06）
- 解锁 `target_allocation_ratio` 的 100% 限制（V2-06）

看板层的**唯一正确做法**是**只读**：读 `finance.shop_profit_basis`（过滤口径）、
读 `finance.employee_labor_cost_allocations`（按 `calculation_version` 严格等值过滤）、
读 `finance.monthly_profit_adjustments`，**自己一个数都不重算**。

---

## 9. 未验证项与残余风险

- 本文件所有行号均按 **2026-11-21 工作区**的代码状态记录；后续代码变动会使行号漂移，
  引用时请同时核对符号名（函数名 / 常量名 / 列名）。
- 「全仓无对账断言」（V2-04）与「无直接单测」（V2-05）是**搜索结论**，不是形式化证明：
  若存在通过字符串拼接、动态导入或配置驱动的间接覆盖，本次搜索未必命中。
- 各条的**业务影响面**未做生产数据实测（当前环境无生产只读连接），
  严重度评级是**基于代码路径的结构判断**，不是实测金额损失。
- V2-03 与 V2-06 都需要业务拍板；在拍板前动手会直接改变工资单金额，
  属于「不可逆」类改动。

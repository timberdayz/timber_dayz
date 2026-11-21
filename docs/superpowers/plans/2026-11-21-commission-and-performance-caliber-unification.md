# 提成与绩效工资口径归一计划（V2 重建批次）

> 起草：2026-11-21 ｜ 状态：**待执行计划**
> 上游：看板化改造已上线生产（v7.36.0，2026-11-21）⇒ 本批进入 **V2 Rebuild Phase**
> 阶段依据：`docs/guides/CHANGE_CONTROL.md` §V2 Rebuild Phase
> 关联文档：`docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md`（V2 治理清单）
> 关联 ADR：`docs/adr/2026-11-21-commission-and-performance-caliber-layering.md`
> 业务确认：Walter 2026-11-21 ——「提成分多少给多少，只有绩效工资乘绩效系数」；**历史数据可删除或重算，历史数据不重要**

---

## 0. 一句话结论

把「员工提成 = 利润基数 × 可分配率 × 归属提成比 × **结算系数**」里的**结算系数拿掉**，
把「绩效工资 = 绩效包 × 系数」里的系数换成**纯个人的绩效分数档位系数**（不含店铺排名），
**赛马排名彻底不参与任何金额**、只做考核与预警信号。

结果：提成回到业务方记忆中的样子（**分多少，给多少**）；绩效工资保留激励；
每个数字只剩**一个真源**；同一句公式不再被抄 5 遍。

---

## 1. 现状核对（全部为本地库/代码实测，非转述）

### 1.1 同一句提成公式被独立实现 5 处

SSOT 公式（工资单实发口径，`backend/services/hr_income_calculation_service.py:1657-1662`）：

```
allocation_amount = max(profit_basis_amount, 0.0) * alloc_rate * ratio * settlement_coefficient
```

5 处实现及其偏差：

| # | 位置 | 偏差 | 是否有页面在用 |
|---|---|---|---|
| 1 | `backend/domains/business/routers/hr_commission.py:1576-1578`（`GET /commissions/shop`） | **漏乘** `settlement_coefficient` | **无**（全仓仅 `frontend/src/api/index.js` 有方法定义，无组件调用；且迁移 `20261212` 与 ORM `business.py:4491` 注释均记录「该接口在当前库上会抛 UndefinedColumn」） |
| 2 | `backend/domains/business/routers/hr_commission.py:2267-2388`（`GET /shop-profit-statistics`） | 同一响应并列两个口径（含系数 / 不含系数） | **有**（`frontend/src/domains/business/views/hr/ShopAssignment.vue:1062`） |
| 3 | `backend/services/monthly_settlement_service.py:239-255` | 自称「不做任何二次计算」，却自行再算一次 min 并重算提成 | **有**（`frontend/src/domains/business/views/hr/MonthlySettlement.vue`） |
| 4 | `backend/services/payroll_confirmation_service.py:110-117` | 「按店聚合归属提成比合计」独立实现 | **有**（工资单确认链路） |
| 5 | 两个「利润基数加载器」口径不一致 | 一个要求 `is_locked=True`、缺行现算；一个不要求、缺行报错 | **有** |

> 第 3 处的算法与第 1 处**数学等价**（都是 `min(店铺系数, 个人分数系数)`），
> 所以月度结算单页当前**没有算错**，只是「同一件事写了两遍」⇒ 属**收敛对象**，不是 bug 修复对象。
> 但它少了 `hr_income_calculation_service` 的 `_is_formal_store_performance` 过滤，
> 非正式店铺的系数可能被算进去 ⇒ **这是一处真实的口径差异，必须收敛**。

### 1.2 三个系数混在一起用

`backend/services/performance_coefficient.py`（明面上的系数 SSOT，128 行）：

| 系数 | 定义 | 当前参与金额的地方 |
|---|---|---|
| 排名档位系数 `RANK_BAND_COEFFICIENTS` | 店铺赛马名次占比 → 前20%=1.2 / 前50%=1.0 / 前80%=0.9 / 其余=0.8 | 提成、绩效工资 |
| 分数档位系数 `SCORE_BAND_COEFFICIENTS` | 绩效分数 → ≥90=1.2 / ≥80=1.0 / ≥70=0.9 / ≥60=0.8 / <60=0.5 | 提成、绩效工资 |
| 结算系数 `calculate_settlement_coefficient` | 上面两者的 min | 提成、绩效工资 |

该文件 docstring 记录的历史账（原文）：

> 改造前这两件事是分开的：提成乘「店铺排名系数」（0.5 ~ 1.2），绩效工资乘「绩效分数 ÷ 100」（0 ~ 1）。
> 于是同一个人同一个月有两套系数，页面显示的和工资单实发对不上
> （2026-10 实测：页面 1002.56 / 后端统计 1002.55 / 实发 979.46）。
> 现在统一成一条链路：页面看到的系数，就是工资单拿到的系数。

**但「统一」没有做干净** —— 实测数据证明：

| 月份 | 绩效工资实际用的系数 | 口径 |
|---|---|---|
| 2026-07 | `EmployeePerformance.performance_coefficient` 为 NULL ⇒ 回退取 `performance_score` ⇒ 分数 ÷ 100 | **纯个人**（老口径） |
| 2026-10 | 逐店系数的销售额加权平均（0.7655 / 0.7853 / 0.7791 / 0.5） | **含店铺排名**（新口径） |

⇒ 绩效工资的口径在历史月份之间**已经漂移过一次**，不是"现在是统一的"。

> 校准补充（§1.7 同批实测）：2026-10 那四个加权平均系数
> （0.7655 / 0.7853 / 0.7791 / 0.5）**都 ≤ 同月对应的纯个人分数档位系数**
> （0.8 / 0.8 / 0.8 / 0.5）⇒ 含店铺排名的加权平均**只会把绩效工资压低、不会抬高**。
> 这正是"提成被赛马压低"在绩效侧的同一份账单。

### 1.3 赛马系数确实参与提成（证据链）

```
店铺绩效管理页「绩效系数」列
  → `performance_management.py:958` 写 `c_class.performance_scores.performance_coefficient`
  → `hr_income_calculation_service._load_store_performance_by_shop()` 读入 `performance_by_shop`
  → 提成逐店计算 `... * settlement_coefficient`
  → 工资单 `PayrollRecord.commission`
```

⇒ **店铺赛马排名会直接改变员工提成金额**，这不是"只作用于绩效"。

### 1.4 历史月份的口径本身是漂移的

`finance.shop_profit_basis` 的口径版本分布（本地库全量）：

| 月份 | `basis_version` | 行数 | 利润基数合计 | 今天的代码还能算吗 |
|---|---|---|---|---|
| 2026-03 | `A_ONLY_V1` | 17 | 24,987.22 | 否（legacy 被跳过） |
| 2026-04 | `A_ONLY_V1` | 1 | 0.00 | 否 |
| 2026-05 | `A_ONLY_V1` | 8 | 0.00 | 否 |
| 2026-06 | `A_ONLY_V1` | 2 | 0.00 | 否 |
| 2026-07 | `A_ONLY_V1` | 19 | 13,347.36 | 否 |
| 2026-08 | `A_ONLY_V1` | 10 | -10,526.33 | 否 |
| 2026-09 | `A_PRE_COMMISSION_LABOR_V2` | 1 | 0.00 | 否 |
| 2026-10 | `SETTLEMENT_BASIS_V1` | 18 | 22,337.41 | **是**（唯一现行口径） |

⇒ **只有 2026-10 能用现行代码完整复算**；其余月份的利润基数是用旧口径写的，
今天的代码读不到 ⇒ 历史工资单**无法用今天的代码复现**。
这是「口径漂移」的实证，也是本批必须先做归一的原因。

### 1.5 利润基数的公式（已核准）

`backend/services/profit_basis_service.py:260-300`（`build_profit_basis`）：

```
profit_basis_amount = orders_profit_amount（店铺经营利润）
                     - other_a_class_cost_amount（其他经营成本）
                     - pre_commission_labor_cost_amount（提成前人力成本）  ← 非 legacy 才扣
```

⇒ **利润基数里不含可分配率** ⇒「提成池 = 利润基数 × 可分配率」成立。

### 1.6 可分配率只有一个人工配置来源

`a_class.shop_commission_config.allocatable_profit_rate`，由「人员店铺归属和提成比」页面维护。
**没有任何系统自动推导** ⇒ 若让赛马去改它，就凭空多出第二个来源。

### 1.7 改造后的金额影响（本地库实测，**已按生产公式校准**）

只有 2026-10 是可用现行代码完整复算的月份（§1.4），故只在该月做实测。

**校准方法**（先证伪自己的模型，再谈影响面）：
按 `hr_income_calculation_service.py:1634-1662` 的生产公式逐店逐人重算 ——
`结算系数 = min(店铺结算系数, 个人分数档位系数)`，`提成 = max(基数,0) × 率 × 比 × 结算系数`；
重算结果与 `a_class.payroll_records` 实存比对：

| 项 | 真实公式重算 | 工资单实存 | 校准差 |
|---|---|---|---|
| 2026-10 提成 | 875.94 | 875.95 | **0.01（尾差）** |

⇒ 模型与生产公式一致，后续差额可信。

**改造前后（2026-10）**：

| 项 | 现状（实存） | 新口径 | 差额 |
|---|---|---|---|
| 员工提成 | 875.95 | 1,231.08 | **+355.13** |
| 员工绩效工资 | 2,829.93 | 2,900.00 | **+70.07** |
| 看板「员工侧分配额」 | 3,705.88 | 4,131.08 | **+425.20** |

**逐人明细（提成）**：

| 员工 | 绩效分数 | 生效系数 | 现状 | 新口径 | 差额 |
|---|---|---|---|---|---|
| EMP260001 | 60.73 | 0.8 | 240.69 | 307.77 | +67.08 |
| EMP260005 | 66.61 | 0.8 | 240.69 | 307.77 | +67.08 |
| EMP260006 | 66.91 | 0.8 | 240.69 | 307.77 | +67.08 |
| EMP260007 | 53.27 | 0.5 | 153.88 | 307.77 | +153.89 |

**业务结论**：2026-10 实际生效的结算系数只有 0.5 与 0.8（**均 ≤ 1.0**），
⇒ **去掉系数后没有任何一个员工少拿钱**，全部为增。
但这**只是本月观测**，不构成"永远只会增加"的保证 ——
若某月存在系数 > 1.0 的店铺（如 2026-10 的 `1308200825`=1.2、`tiktok_my_flora_mall_local`=0.5 等），
该店员工在新口径下会**减少**。真正的影响面必须以生产库 `--dry-run` 为准（§11）。

> 绩效工资逐人：EMP260001 765.53→800.00、EMP260005 785.30→800.00、
> EMP260006 779.10→800.00、EMP260007 500.00→500.00（系数本就等于纯个人档位，无变化）。

---

## 2. 问题清单与定级

| # | 问题 | 定级 | 影响 |
|---|---|---|---|
| P1 | 提成公式 5 处独立实现，其中 1 处漏乘系数 | 高 | 口径漂移的根源；1 处已坏且无人用 |
| P2 | 绩效工资系数在历史月份之间换过口径 | 高 | 历史工资单之间不可比 |
| P3 | 赛马排名直接乘在员工提成上 | 中高 | 业务方认知与实现不符；分配特征难解释 |
| P4 | 历史月份利润基数是 legacy 版本，今天的代码算不出 | 高 | 看板历史月份无法与新月份比较 |
| P5 | 月度结算单页与工资单的过滤条件不同（少 formal 过滤） | 中 | 该页数字可能与工资单不一致 |
| P6 | 「结算系数」列在页面上无解释来源 | 中 | 运营无法理解自己的钱为什么变 |
| P7 | 页面并列两个提成口径 | 低 | 已用列名+tooltip 标注，暂不造成困惑 |

---

## 3. 目标业务规则（唯一口径）

### 3.1 提成公式（最终形态）

```
某员工从某店分到的提成 = max(该店可分配利润, 0) × 该员工的归属提成比

其中：该店可分配利润 = max(该店利润基数, 0) × 该店可分配利润率
```

**三个因子，零系数。分多少，给多少。**

### 3.2 绩效工资公式（最终形态）

```
绩效工资 = 绩效包金额 × 绩效分数档位系数(该员工的绩效分数)
```

**纯个人的分数档位系数（0.5 ~ 1.2），与店铺排名无关。**

### 3.3 三个系数的职责划分（最终形态）

| 系数 | 保留？ | 作用域 | 理由 |
|---|---|---|---|
| 绩效分数档位系数 | 保留 | **只作用于绩效工资** | 名实相符：个人绩效分档 |
| 排名档位系数（赛马） | 保留 | **不参与任何金额**，只做考核/预警/展示 | 赛马是**店铺级**评价；让它进员工分配环节，就会制造员工之间的钱差异，与「分多少给多少」直接冲突 |
| 结算系数（min 混合体） | 从金额链路移除 | — | 它把两个维度混成一个数，是复杂化的根源 |

> **与 2026-11-21 早先建议的差异（必须记录）**
> 早先建议「赛马上移到可分配利润率层」。**本计划不采用该方案**，理由：
> `allocatable_profit_rate` 当前唯一来源是人工配置；让赛马去改它 ⇒ 该字段出现
> 「人工配置」与「赛马推导」两个来源与优先级语义 ⇒ **制造新的口径分歧，违反 SSOT**。
> 若业务上确需"赛马影响提成"，正确做法是**单独一列**（如 `racing_adjusted_rate`）并写死优先级，
> 不得复用 `allocatable_profit_rate`。本批不做，留作后续独立批次。

### 3.4 赛马保留下来的部分

店铺绩效管理页继续提供：总分、排名、赛马池、预警（红黄牌、连续 7 班海灾升级）、
以及一个**纯展示**的赛马评级系数。页面须明确标注：

> 「赛马评级只用于考核与预警，**不参与提成计算**。」

### 3.5 每个数字的 SSOT 归属表（本批的核心交付）

| 数字 | 唯一真源 | 落点 | 消费方 |
|---|---|---|---|
| 店铺当月经营利润 | `fact_orders` 聚合 | `profit_basis_service._load_orders_profit_amount` | 利润基数 |
| 其他经营成本 | a_class 成本 | `profit_basis_service._load_other_a_class_cost_amount` | 利润基数 |
| 提成前人力成本 | `finance.employee_labor_cost_allocations` | `profit_basis_service._load_pre_commission_labor_amount` | 利润基数 |
| **店铺利润基数** | `finance.shop_profit_basis`（`SETTLEMENT_BASIS_V1`） | `profit_basis_service.build_profit_basis` | 利润基数 / 可分配利润 / 看板 |
| **可分配利润率** | `a_class.shop_commission_config` | 人工配置（唯一来源，本批不动） | 可分配利润 |
| **归属提成比** | `a_class.employee_shop_assignments.commission_ratio` | 人工配置（唯一来源，本批不动） | 员工分摊额 |
| **绩效包金额** | `a_class.salary_structures.performance_package_amount` | 人工配置（唯一来源，本批不动） | 绩效工资 |
| **员工绩效分数** | `c_class.employee_performance.performance_score` | 系统计算 | 绩效分数档位系数 |
| **绩效分数档位系数** | `performance_coefficient.SCORE_BAND_COEFFICIENTS` | **唯一档位表** | 绩效工资 |
| **排名档位系数** | `performance_coefficient.RANK_BAND_COEFFICIENTS` | **唯一档位表** | 仅考核/预警展示 |
| 店铺赛马评级 | `c_class.performance_scores.performance_coefficient` | 考核展示 | 页面 + 预警 |
| **员工提成金额** | **新纯函数模块**（见 §4.2） | 计算 | 工资单 / 人力成本分摊 / 看板 |
| **员工绩效工资** | `payroll_generation_service`（改用纯个人系数） | 计算 | 工资单 / 人力成本分摊 / 看板 |
| 看板三条算术 | `monthly_profit_settlement_service.get_dashboard` | 已唯一（v7.36.0） | 前端**只渲染，不复刻** |

---

## 4. SSOT 落点设计

### 4.1 档位表真源

`backend/services/performance_coefficient.py` 保持为**唯一档位表**。本批改动：

- `calculate_score_coefficient(score)` —— **绩效工资侧唯一入口**（新增使用）
- `calculate_rank_band_coefficient(rank, total)` —— **仅考核展示侧使用**（从金额链路摘出）
- `calculate_settlement_coefficient(...)` —— **从金额链路移除**（保留函数本体但不再被金额路径调用，
  或直接删除，由 §6 批次 2 决定；删除前须确认无其它调用方）
- `describe_settlement_coefficient(...)` —— 仅保留在「结算预览」用于展示"谁把系数压下来了"，
  但其入参改为纯个人分数系数

### 4.2 提成计算真源（新模块）

新建 `backend/services/commission_caliber.py`，**纯函数、无 DB 依赖**，对外只暴露：

```python
def calculate_shop_allocatable_profit(profit_basis_amount, allocatable_rate) -> Decimal
def calculate_employee_shop_commission(allocatable_profit, commission_ratio) -> Decimal
def calculate_employee_performance_salary(package_amount, performance_score) -> Decimal
```

规则：
- **不得**在函数内查库、读配置、取系数 —— 入参即全部输入；
- 所有调用点（含路由、服务、确认校验）改为调用它；
- 函数体与 docstring 必须写明「这里是提成公式的唯一实现处」。

> 放置位置依据 `AGENTS.md`：服务层放 `backend/services/`；这是纯计算模块，
> 不适用 `AsyncCRUDService`（那是对 CRUD 场景的要求）。

### 4.3 利润基数真源

`finance.shop_profit_basis` 只保留**一个** `basis_version`（`SETTLEMENT_BASIS_V1`）。
`is_legacy_a_only_basis_version` 的判定逻辑保留在 `labor_cost_policy_service`（历史数据清理后
不再需要分支，但**判定函数本身不能删** —— 它是"什么算 legacy"的唯一判定处，删了将来无法解释旧数据）。

### 4.4 前端禁止复刻（硬约束）

- 前端**只渲染后端下发的数值**，不重算提成、不重算绩效工资、不重算系数；
- 「人员店铺归属和提成比」页当前已有一次本地试算（仅对"改了还没保存"的临时编辑），
  该试算必须调用**后端预览接口**或使用**后端下发的系数**，不得在前端复制公式；
- 新增守护测试扫描前端源码，命中提成/绩效公式关键字即失败。

### 4.5 指标词典登记

`docs/team-skills/sea-metrics-language/`（正本）新增/修订：

- `commission_amount`（员工提成）的口径改为「可分配利润 × 归属提成比，不含系数」
- `performance_salary_amount`（绩效工资）的口径改为「绩效包 × 绩效分数档位系数」
- 新增 `performance_score_coefficient`（绩效分数档位系数）与
  `ranking_coefficient`（赛马评级系数，**不参与金额**）两个指标的区分说明

---

## 5. 历史数据处置（业务已授权：可删除或重算）

### 5.1 处置原则

**选"重算"而非"删除"**：删除会让看板历史断档、无法验证新旧口径差异。
重算后所有历史月份与新月份**可比**。

### 5.2 处置清单

| 对象 | 现状 | 处置 | 不可逆 |
|---|---|---|---|
| `finance.shop_profit_basis` 中 `A_ONLY_V1` / `A_PRE_COMMISSION_LABOR_V2` 行 | 2026-03~09 共 58 行 | **删除后按现行口径重算** | 是（有备份兜底） |
| `a_class.employee_performance.performance_coefficient` | 2026-07 为 NULL（老口径回退）、2026-10 为加权平均 | **统一重算为纯个人分数档位系数** | 是 |
| `a_class.payroll_records`（2026-03~11） | 提成含系数、绩效工资口径不一 | **重算**（提成去系数 + 绩效工资换系数） | 是 |
| `finance.employee_labor_cost_allocations` | 由旧工资单派生 | **随工资单重算后重建** | 是 |
| `c_class.performance_scores.performance_coefficient` | 店铺赛马评级 | **保留**（仍用于考核展示） | 否 |
| 2025-09 的 0.2 系数 | 旧档位遗留（现行档位表 0.5~1.2 没有 0.2） | 重算时按现行档位重新评级；若该月无正式数据则标记为「不参与考核」 | 是 |

### 5.3 重算脚本设计

新建 `scripts/recalibrate_commission_history.py`（**不放仓库根目录** —— `AGENTS.md` 禁止根级一次性脚本）：

```
用法: python scripts/recalibrate_commission_history.py --year-month 2026-07 --dry-run
      python scripts/recalibrate_commission_history.py --from 2026-03 --to 2026-11 --apply
```

要求：
- 默认 `--dry-run`，只打印"将改什么"，不写库；
- `--apply` 时逐月重算并输出「月份 / 员工 / 项目 / 旧值 → 新值 / 差额」明细；
- **幂等**：重复执行结果不变；
- 写库前必须打印汇总并要求 `--apply`；
- 每步失败即停，不做部分写入（事务包裹）。

### 5.4 不可逆点与备份

- 删除 legacy 利润基数行、重算工资单**均不可逆**（downgrade 只能重建空表结构）；
- 执行前必须完成**可恢复性验证**的备份（生产走发版流程自带的
  `perform_pre_migration_backup`，`pg_restore --list` 退出码 0）；
- 本地执行前先在隔离库跑通全流程。

---

## 6. 改造批次

### 批次 1 · 零风险清理与安全网（不改任何金额）

**做什么**
1. 删僵尸接口 `GET /hr/commissions/shop`：后端 router 函数 + `ShopCommissionResponse` +
   前端 `api/index.js` 的 `getHrShopCommissions` 方法；
2. 核查 `GET /hr/commissions/employee` 是否有页面在用，无则一并清理；
3. 新建 `backend/services/commission_caliber.py`（**先只定义，不接管调用**）；
4. 补单元测试（见 §7）；
5. 产出「现状基线快照」脚本 `scripts/snapshot_commission_baseline.py`，
   把当前各月提成/绩效工资/系数落成存档，供后续批次逐项比对。

**验收**：后端全量 4 failed / 7146 passed（零新增）；前端 364/364；`vite build` 成功；
生产 OpenAPI 中 `/api/hr/commissions/shop` 消失且其余路由不变。

### 批次 2 · 提成计算收敛（改金额，但只改这一项）

**做什么**
1. `commission_caliber.py` 接管 **5 处调用点**：
   - `hr_income_calculation_service` 提成循环（**权威实现**）
   - `hr_commission.py` 的 `shop-profit-statistics`（删掉"不含系数"那一套口径与并列字段）
   - `monthly_settlement_service`（删掉自行重算，改为调用真源）
   - `payroll_confirmation_service` 的按店聚合（改用真源）
   - 统一「利润基数加载器」：两处合并为一处，**且加上 `_is_formal_store_performance` 过滤**
2. **提成去掉 `settlement_coefficient`**；
3. 结算预览接口（`/hr/commissions/settlement-preview`）同步去系数。

**验收**
- 单元测试：同一输入在 5 条路径产出**完全相同**的金额；
- 对账断言：Σ(各店员工分摊额) == 员工提成总额（新增守护，V2-04）；
- 基线快照比对：差异只在"去系数"这一项，且幅度与 §1.7 实测一致
  （本地 2026-10：提成 +355.13、绩效工资 +70.07、员工侧分配额 +425.20）。

### 批次 3 · 绩效工资口径归一（改金额）

**做什么**
1. `payroll_generation_service` 的绩效工资系数改为**纯个人分数档位系数**，
   不再读 `EmployeePerformance.performance_coefficient`（该字段语义随之变更）；
2. `EmployeePerformance.performance_coefficient` 的语义从"加权平均结算系数"改为
   **"绩效分数档位系数"**（0.5~1.2，纯个人）；
3. `hr_income_calculation_service` 里产生 `employee_settlement_coefficient` 的加权平均逻辑**删除**；
4. `performance_coefficient.py`：`calculate_settlement_coefficient` / `describe_settlement_coefficient`
   从金额路径摘除（若确认无其它调用方则删除）。

**验收**
- 多店员工：绩效工资 == 绩效包 × `calculate_score_coefficient(performance_score)`（逐人断言）；
- 不再存在任何"按店取 min 后加权"的绩效系数计算。

### 批次 4 · 历史数据重算

**做什么**
1. 迁移：删除 legacy `basis_version` 的利润基数行（**走 Alembic**，schema 变更的 SSOT 是迁移脚本）；
2. `scripts/recalibrate_commission_history.py` 重算 2026-03 ~ 2026-11：
   利润基数 → 工资单（提成 + 绩效工资）→ 人力成本分摊表；
3. 2025-09 的 0.2 旧系数按现行档位重新评级，或标记「不参与考核」；
4. 产出《历史口径归一说明》（放 `docs/guides/`，随发版归档）。

**验收**
- **【前置关卡，不可跳过】** 在**生产库**跑 `scripts/recalibrate_commission_history.py --dry-run`，
  产出**逐人新旧对照表**（旧金额 → 新金额 → 差额），**交业务确认后方可 `--apply`**；
  ⚠️ 本地 2026-10 是「4 人全部为增」，但历史月存在 1.2 档系数 ⇒ **必然有人减发**，
  不能拿本地单月数据替代生产核验；
- 重算后本地库 `scripts/diff_pytest_junit.py` 基线仍零新增失败；
- 重算后**看板三个月数字可与历史对比**（口径一致）；
- 重算脚本 `--dry-run` 与 `--apply` 输出金额一致（幂等）。

### 批次 5 · 页面收敛

**做什么**
1. 「人员店铺归属和提成比」页：
   - 「主管提成（未含结算系数）」+「操作员提成（未含结算系数）」+「预计提成（结算口径）」
     **三列合并为一列**「预计提成（实发口径）」；
   - 「结算系数」列**改名**为「绩效系数（仅影响绩效工资）」，取员工个人分数档位系数；
   - 移除前端本地试算公式，改为调用后端预览；
2. 「店铺绩效管理」页：「绩效系数」列改名为「赛马评级（不参与提成计算）」，
   并在口径说明里写明赛马只用于考核与预警；
3. 「月度结算单」页：只读真源，删除自行计算。

**验收**：前端 364/364；`vite build` 成功；新增前端契约守护测试。

### 批次 6 · 词典与文档同步

**做什么**
1. 指标词典（正本 + 副本单向同步）登记新口径与两个系数的区分；
2. `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md` 更新提成/绩效口径；
3. `docs/guides/ENGINEERING_STATUS.md` 登记；
4. `docs/adr/2026-11-21-commission-and-performance-caliber-layering.md` 落地 ADR；
5. `docs/superpowers/plans/STATUS.md` 登记本批次。

### 批次 7 · 发布与验收

走既有发布链路：PR → CI → 合并 main → 双镜像同步 → tag → 部署 → 生产验收。
生产验收清单：

- `/api/healthz/ready` → 版本号与 tag 一致；
- 迁移链头正确、`missing_tables=[]`、`missing_columns=[]`；
- 生产 OpenAPI：提成/绩效相关路由与方法符合新契约；
- 迁移前备份已通过 `pg_restore --list`；
- 看板页可访问，「员工侧分配额」与重算后预期一致；
- 抽查若干员工：新提成 == 可分配利润 × 提成比（逐人核对）。

---

## 7. 防回归守护测试（随每批一起提交）

| 守护 | 断言 | 批次 |
|---|---|---|
| `backend/tests/test_commission_caliber.py` | 纯函数：三个因子相乘、负利润归零、比例边界 | 1 |
| `backend/tests/test_commission_single_source.py` | 源码扫描：提成公式字面量只允许出现在 `commission_caliber.py` | 2 |
| `backend/tests/test_commission_path_parity.py` | 同一组输入，5 条路径产出相同金额 | 2 |
| `backend/tests/test_commission_conservation.py` | **V2-04**：Σ(人维度) == Σ(店维度) == 员工提成总额 | 2 |
| `backend/tests/test_performance_salary_caliber.py` | 绩效工资 == 绩效包 × 个人分数档位系数（多店员工也成立） | 3 |
| `backend/tests/test_no_settlement_coefficient_in_payroll.py` | 源码扫描：工资单/提成路径不得出现 `settlement_coefficient` | 3 |
| `backend/tests/test_profit_basis_single_version.py` | 利润基数只允许现行 `basis_version`；legacy 行必须为 0 | 4 |
| `frontend/tests/commissionFrontendNoRecompute.test.mjs` | 前端源码不得出现提成/绩效公式字面量 | 5 |
| `backend/tests/test_racing_coefficient_not_in_payroll.py` | 赛马评级字段不得进入任何金额计算路径 | 5 |

> 全部守护必须进 CI 根契约清单（`ci.yml`），否则等于没有。

**挂载方式必须区分（`ci.yml` 的两条 pytest 步骤不是一锅端）**：

| 挂载点 | 位置 | 适合 | 禁忌 |
|---|---|---|---|
| **根契约清单**（无 DB） | `ci.yml` 的 "Run root contract tests (no DB)" 步骤 | 纯函数单测、**源码扫描类**守护 | **不得放 async 用例** |
| **改动触发的 pytest** | "Run pytest (if test files exist)" | 依赖 DB / 多服务的集成型守护 | 漏改文件时不跑 |
| **PG 服务容器 job** | `ci.yml` 里带 `db_test_config` 的 job | 真 PG 断言（历史重算、库内行数） | 需要 PG 可达 |

⚠️ **已知坑（`ci.yml` 注释已记录，务必照抄那条约束）**：
CI 钉 `pytest==7.4.3` / `pytest-asyncio==0.21.1`，而 `backend/tests/conftest.py` 覆盖了
session 级 `event_loop`（1.x 会忽略它）⇒ **凡是被放进根契约清单的文件若有 async 用例，
会拿到已关闭的事件循环并报 `RuntimeError: Event loop is closed`**。
本批 9 条守护中，`test_commission_conservation.py` 与 `test_profit_basis_single_version.py`
**必须写成同步断言**（或改挂 PG job），否则会把流水线打红。

---

## 8. 明确不做的事（防误伤清单）

| 不做 | 原因 |
|---|---|
| 不把赛马接到可分配利润率上 | 会让该字段出现两个来源，违反 SSOT（§3.3） |
| 不重命名 `monthly_profit_settlement_*` 模块 | 受上线前规则约束，属 V2-01，另批处理 |
| 不改 `allocatable_profit_rate` / `commission_ratio` / `performance_package_amount` 的**语义与来源** | 它们已经是各自唯一真源，本批只消费不新增 |
| 不动 `c_class.performance_scores` 的考核与预警逻辑 | 赛马本身要保留，只是不再进金额 |
| 不改利润基数的成本构成 | `build_profit_basis` 的公式不在本批范围 |
| 不新增根级临时脚本 | `AGENTS.md` 明令禁止；脚本一律放 `scripts/` |
| 不在生产直连写库 | 历史重算必须走发版流程 |

---

## 9. 建议执行顺序与理由

```
批次1（零风险安全网 + 删僵尸）
   ↓ 理由：先有测试与基线快照，后面每一步都有对照物
批次2（提成收敛 + 去系数）
   ↓ 理由：这是本批的主目标；先单独一步，改动面最小、可独立验收
批次3（绩效工资口径归一）
   ↓ 理由：依赖批次2 的真源模块已就位
批次4（历史数据重算）—— **先生产 dry-run 逐人对照表 → 业务确认 → 才 apply**
   ↓ 理由：必须等 2、3 的计算口径定稿，否则要重算两遍；且不可逆，必须有业务确认这一关
批次5（页面收敛）
   ↓ 理由：页面消费的是新口径，必须在口径定稿后做
批次6（词典/文档同步）
批次7（发布与验收）
```

> 批次 6 中的 **ADR 与台账登记已随本计划提前落地**
> （`docs/adr/2026-11-21-commission-and-performance-caliber-layering.md`、
> `docs/superpowers/plans/STATUS.md`），批次 6 剩下的是指标词典与运行手册同步。

**若要更快**：批次 1、2、3 可合并为一次 PR（它们共享同一个纯函数模块），
但批次 4（历史重算）**必须独立** —— 不可逆数据操作要与代码改动分开，便于定位问题与回滚。

---

## 10. 业务侧已确认的结论（2026-11-21）

1. **提成 = 对应店铺分多少给多少，不乘任何系数**；只有绩效工资（绩效包）乘绩效系数。
2. **历史数据不重要**，可删除或重算 ⇒ 选重算（保留可比性）。
3. **方案按"赛马不参与任何金额、只做考核与预警"落地**（本计划采纳；
   早先讨论的"赛马上移到可分配利润率层"因违反 SSOT 未采用，理由见 §3.3）。

---

## 11. 风险与回滚

| 风险 | 影响 | 缓解 | 回滚 |
|---|---|---|---|
| 去掉系数后分配特征变化（系数 0.5 的店员工提成变多、1.2 的变少） | 员工收入变化 | 业务已确认接受；2026-10 实测员工侧分配额 +425.20（4 人，全部为增） | 按备份恢复工资单，或用重算脚本反向参数化 |
| **系数 > 1.0 的店铺，其员工在新口径下会少拿钱** | 员工收入减少 | 2026-10 生效系数仅 0.5/0.8（无人减少），但 2026-07 等历史月存在 1.2 档 ⇒ **必须以生产库 `--dry-run` 逐人留档并提前告知** | 同上；重算前可按人出具新旧对照表交业务确认 |
| 绩效工资系数换成纯个人后，历史月份金额变化 | 员工收入变化 | 同上；差异逐人留档 | 同上 |
| 历史重算不可逆 | 数据丢失 | 发版流程自带可恢复性验证的备份；本地先在隔离库跑通 | 从备份恢复 |
| 口径归一后看板历史数字变化 | 对外解释成本 | 随发布归档《历史口径归一说明》 | 看板本身是只读聚合，数据正确即可 |
| 新增真源模块被后续代码绕开 | 口径再次分裂 | 源码扫描守护（`test_commission_single_source.py`） | 守护失败即阻断合并 |

---

## 12. 验收总口径（发布前必须全部满足）

1. 后端全量：**零新增失败**（`scripts/diff_pytest_junit.py` 对基线）；
2. 前端：`node --test "scripts/*.test.mjs"` **全绿** + `vite build` 成功；
3. §7 全部守护进 CI 根契约清单并通过；
4. 5 个校验脚本 + 6 个发布门禁脚本全过；
5. 提成公式字面量在仓库中**只出现在 `commission_caliber.py`**；
6. 利润基数只存在现行 `basis_version`；
7. 赛马评级不进入任何金额计算路径；
8. 看板「员工侧分配额」与重算后的工资单实发一致（抽样逐人核对）；
9. 变更已记入 ADR 与 `STATUS.md`；
10. **历史重算前**：生产库 `--dry-run` 逐人新旧对照表**已交业务确认签字**（不可逆操作的前置关卡）。

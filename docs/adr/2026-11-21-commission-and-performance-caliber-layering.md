# ADR-2026-11-21：提成与绩效工资口径分层（SSOT）

- 状态：**已接受**
- 日期：2026-11-21
- 影响域：人力（提成、绩效工资、工资单）与财务（利润看板）的口径归属
- 业务确认：Walter 2026-11-21 ——「提成分多少给多少，只有绩效工资乘绩效系数」；历史数据可删除或重算
- 实施计划：`docs/superpowers/plans/2026-11-21-commission-and-performance-caliber-unification.md`

## 背景

2026-11-21 的月度利润看板改造上线（v7.36.0）后，对「员工提成与绩效工资到底怎么算」
做了一次全链路核对，暴露出三类问题：

### 1. 同一句提成公式被独立实现 4 处（第 5 处是口径不一致的加载器）

SSOT 公式在 `backend/services/hr_income_calculation_service.py:1657-1662`（工资单实发口径）：

```
allocation_amount = max(profit_basis_amount, 0) * alloc_rate * ratio * settlement_coefficient
```

但同样一句话在另外 3 处各写了一遍：结算统计接口、月度结算单服务、工资单确认聚合。
其中一处（`GET /hr/commissions/shop`）还**漏乘了系数** —— 幸好它没有页面在用，
且在当前库上会直接抛 `UndefinedColumn`，从未生效。

第 3 处（月度结算单）与权威实现**数学等价**，只是抄了第二遍；但它少了
`_is_formal_store_performance` 过滤 ⇒ 非正式店铺的系数会被算进去 ⇒ 这是一处真实的口径差异。

> 📌 计数更正（2026-11-21 实施过程中查实）：最初记为「5 处公式」，
> 实际是 **4 处公式实现 + 1 处加载器口径不一致** ——
> `_load_profit_basis_map`（要求 `is_locked=True` 且按 `basis_version` 过滤）与
> `_load_profit_basis_by_shop`（不要求 locked、跳过 legacy）行为不同，
> 同样属于必须统一的 SSOT 问题，但形态不是「又抄了一遍公式」。

### 2. 三个系数混在一个文件里、同时作用于两个金额

`backend/services/performance_coefficient.py` 声明自己是"统一结算系数 SSOT"，
实际承载三件事：

| 系数 | 含义 |
|---|---|
| `RANK_BAND_COEFFICIENTS` | 店铺赛马名次档位（前20%=1.2 … 其余=0.8） |
| `SCORE_BAND_COEFFICIENTS` | 绩效分数档位（≥90=1.2 … <60=0.5） |
| `calculate_settlement_coefficient` | 上面两者的 `min`（"结算系数"） |

三者**同时乘在提成和绩效工资上**。这导致：

- **店铺赛马排名会直接改变员工提成金额** —— 业务方认知里"赛马只管考核"，实现里它进了分配环节；
- **绩效工资的口径在历史月份之间已经漂移过一次**：2026-07 的
  `EmployeePerformance.performance_coefficient` 为 NULL ⇒ 回退取 `performance_score` ⇒
  分数÷100（纯个人）；2026-10 则是逐店系数的销售额加权平均（含店铺排名）
  ⇒ 同一项工资单字段，跨月不可比。

### 3. 历史月份用今天的代码算不出来

`finance.shop_profit_basis` 里 2026-03~09 共 58 行是旧口径版本
（`A_ONLY_V1` / `A_PRE_COMMISSION_LABOR_V2`），现行代码会跳过它们
⇒ **只有 2026-10 能完整复算**，历史工资单无法用今天的代码复现。

## 决策

### 1. 口径分层：三个系数各归其位

| 系数 | 作用域 | 结论 |
|---|---|---|
| 绩效分数档位系数 | **只作用于绩效工资** | 保留 —— 名实相符：个人绩效分档 |
| 排名档位系数（赛马） | **不参与任何金额**，只做考核 / 预警 / 展示 | 保留但降级 —— 赛马是**店铺级**评价 |
| 结算系数（`min` 混合体） | 从金额链路移除 | 退役 —— 它把两个维度混成一个数，是复杂化的根源 |

最终口径：

```
某员工从某店分到的提成 = max(该店可分配利润, 0) × 该员工的归属提成比
    其中 该店可分配利润 = max(该店利润基数, 0) × 该店可分配利润率
                            # 三个因子，零系数。分多少，给多少。

绩效工资 = 绩效包金额 × 绩效分数档位系数(该员工的绩效分数)
                            # 纯个人档位，与店铺排名无关。
```

### 2. 赛马彻底不参与金额 —— **并记录被推翻的备选方案**

早先讨论过"把赛马系数上移到可分配利润率层"（即赛马去影响 `allocatable_profit_rate`）。
**本 ADR 不采用该方案**，理由是它违反 SSOT：

`a_class.shop_commission_config.allocatable_profit_rate` 当前**唯一来源是人工配置**
（无任何系统推导）。让赛马去改它 ⇒ 该字段出现「人工配置」与「赛马推导」两个来源与优先级语义
⇒ 制造新的口径分歧，恰恰是本 ADR 要消除的问题。

若业务上确需"赛马影响提成"，正确做法是**单独一列**（如 `racing_adjusted_rate`）并写死优先级，
**不得复用 `allocatable_profit_rate`**。本批不做，留作后续独立批次。

### 3. 提成公式收敛为唯一实现处

新建 `backend/services/commission_caliber.py`（**纯函数、无 DB 依赖**，入参即全部输入），
作为提成与绩效工资公式的唯一实现处；4 处公式调用点 + 2 处利润基数加载器口径全部收敛。

`performance_coefficient.py` 保持为**唯一档位表真源**；
`calculate_settlement_coefficient` / `describe_settlement_coefficient` 从金额路径摘除
（函数体保留，仅用于**展示拆解**，不参与任何金额）。

`EmployeePerformance.performance_coefficient` 的语义由「加权平均结算系数」
改为「绩效分数档位系数」；产生加权平均的逻辑删除。

### 4. 利润基数只保留一个口径版本

`finance.shop_profit_basis` 只保留 `SETTLEMENT_BASIS_V1`。
`is_legacy_a_only_basis_version` 的**判定函数保留不删** —— 它是"什么算 legacy"的唯一判定处，
删了将来无法解释旧数据。

### 5. 前端禁止复刻

前端只渲染后端下发的数值，不重算提成 / 绩效工资 / 系数。
「人员店铺归属和提成比」页的本地试算已改为调用**后端试算接口**
`POST /api/hr/commissions/settlement-preview/estimate`：
前端只把「待保存的输入」（可分配率、归属提成比）送上去，金额由后端按唯一口径算。
新增源码扫描守护：命中提成 / 绩效公式关键字即失败。

### 6. 历史数据：删除 legacy 行，接受历史空白

业务已授权历史数据可删除或重算。

> ✅ **最终决策（Walter，2026-11-21，实施中拍板）：删除所有 legacy 行，接受历史空白。**
>
> 原方案是「删除后按现行口径重算」，但**实测不可行**：
> `finance.employee_labor_cost_allocations` 只有 2026-07 与 2026-10 两个月有数据，
> 2026-03~06、08~09、11~12 **完全没有** ⇒ 现行口径算不出那些月的利润基数
> （`_require_complete_profit_basis` fail-closed 抛
> `missing labor allocation for V2 profit basis`）。
>
> 取舍理由：**口径统一优先于历史可比**。
> 留着两套口径的数字并存，看板上同一个月的数字会有两种解释 —— 比空白更难解释。

连带处置：

- 迁移 `20261243_drop_legacy_profit_basis` 删除 `A_ONLY_V1` /
  `A_PRE_COMMISSION_LABOR_V2` 行，删除前按月打印待删行数供生产核验；
- 看板接口新增 `data_status`（`ready` / `no_profit_basis`）+ `data_status_note`，
  让「空白属预期」有明确解释，而不是看起来像 bug；
- 历史重算脚本 `scripts/recalibrate_commission_history.py` 保留（默认 dry-run、
  幂等），供有完整人力成本分摊的月份使用；**生产 apply 需单独授权**。

历史重算**必须独立 PR**（不可逆数据操作与代码改动分开），且必须走发版流程
（生产不可直连写库），执行前依赖发版流程自带的可恢复性验证备份。

## 后果

**正面**

- 提成回到业务方记忆中的样子："分多少，给多少"；
- 每个数字只剩一个真源，同一句公式不再被抄 4 遍；
- 绩效工资跨月可比，不再因口径漂移而失真；
- 赛马回归"考核与预警"的本职，不再制造员工之间的收入差异。

**代价与约束**

- **员工收入会变**：2026-10 实测（已按生产公式校准，重算 875.94 vs 工资单实存 875.95，尾差 0.01）
  提成 +355.13、绩效工资 +70.07、看板员工侧分配额 +425.20，4 人**全部为增**
  （该月生效系数仅 0.5 / 0.8，均 ≤ 1.0）。
  但**历史月份存在 1.2 档系数，其员工在新口径下会少拿钱** ⇒ 影响面必须以生产库
  `--dry-run` 逐人留档后交业务确认，不可仅凭本地单月数据承诺"只会增加"。
- **赛马压低收入是双向的**：含店铺排名的绩效工资加权平均系数
  （2026-10：0.7655 / 0.7853 / 0.7791 / 0.5）**均 ≤ 同月纯个人分数档位系数**
  （0.8 / 0.8 / 0.8 / 0.5）⇒ 赛马参与金额时，只会**压低**员工收入，不会抬高。
- 口径变更属行为变更，必须用失败集 diff 证明无回归（`scripts/diff_pytest_junit.py`）。
- 档位表变更必须改 `performance_coefficient.py`，并同步更新守护测试
  （`test_commission_single_source.py` / `test_no_settlement_coefficient_in_payroll.py`
  / `test_racing_coefficient_not_in_payroll.py`）。
- `commission_caliber.py` 是新的真源落点，**后续任何新增提成计算必须调用它**
  —— 守护测试会在绕开时阻断合并。

## 实施结果（2026-11-21 落地）

按批次 1~7 执行完毕，落地物如下：

| 批次 | 落地物 |
|---|---|
| 1 | 新建 `backend/services/commission_caliber.py`（唯一真源）；下线僵尸接口 `GET /hr/commissions/shop`；新增 5 个守护测试文件 |
| 2 | 提成收敛去系数（权威实现 / 结算预览 / 月度结算单 / 统计接口 4 处调用点）；`test_commission_single_source.py` 当场抓出并修掉 2 处真实遗漏 |
| 3 | 绩效工资改为纯个人档位系数；删除 `EmployeePerformance.performance_coefficient` 的加权平均写法 |
| 4 | 迁移 `current_migrations/versions/20261243_drop_legacy_profit_basis.py`；重算脚本 `scripts/recalibrate_commission_history.py`（默认 dry-run、幂等） |
| 5 | 页面收敛：归属页三列合一为「预计提成（实发口径）」、「结算系数」改名「绩效系数（仅影响绩效工资）」；本地试算改调后端 `POST /hr/commissions/settlement-preview/estimate`；绩效页「绩效系数」改名「赛马评级（不参与提成计算）」；看板新增 `data_status` |
| 6 | 指标词典登记 `commission_amount` / `performance_salary_amount` / `performance_score_coefficient` / `ranking_coefficient`；运行手册与本 ADR 同步 |
| 7 | 提交 → 双镜像 → tag → 部署 → 生产验收 |

守护清单（随批提交，进 CI 根契约清单）：

- `backend/tests/test_commission_caliber.py`（纯函数）
- `backend/tests/test_commission_single_source.py`（源码扫描：公式只在真源）
- `backend/tests/test_commission_path_parity.py`（多路径产出同额）
- `backend/tests/test_performance_salary_caliber.py`（绩效工资 = 绩效包 × 个人档位）
- `backend/tests/test_racing_coefficient_not_in_payroll.py`（赛马不入金额）
- `backend/tests/test_commission_estimate_preview.py`（试算走后端、零系数）
- `frontend/tests/commissionFrontendNoRecompute.test.mjs`（前端不复刻公式）

## 后续（不属于本 ADR）

- 若业务仍要求赛马影响提成：另开独立列 `racing_adjusted_rate` 并写死优先级，不复用现有字段；
- `monthly_profit_settlement_*` 模块重命名：受上线前规则约束，属 V2-01，另批处理；
- `profit_basis_service.build_profit_basis` 的成本构成调整：不在本批范围；
- 补齐历史月份的人力成本分摊数据后，可用 `scripts/recalibrate_commission_history.py`
  回填历史空白（需单独授权）。

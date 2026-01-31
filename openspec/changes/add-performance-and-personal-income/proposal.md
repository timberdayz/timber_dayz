# Change: 绩效公示优化、我的收入与 Public 表 Schema 迁移

## Why

西虹ERP作为**决策支撑系统**，主打**数据公开透明**。当前存在以下问题：

1. **绩效公示**：页面显示「查询绩效评分列表失败」，`performance_scores` 表可能无数据或计算逻辑未完善；`db.execute` 缺少 `await` 导致异步查询失败
2. **个人收入缺失**：员工无法自助查看本人收入明细（底薪、绩效、提成、实发等）
3. **数据割裂**：存在 `c_class.employee_performance`、`c_class.employee_commissions` 等员工级 C 类表，但无前端入口；这两张表当前无写入逻辑，需明确数据来源
4. **Schema 分类不规范**：大量具有「计算功能」的表仍在 `public` 中，应按三层数据分类迁移至 `a_class` 或 `c_class`

需要：优化绩效公示、新增「我的收入」、**将 public 中具备计算功能的表迁移至 A/C 类 schema**，并确保迁移后目标管理、各 Question、绩效公示等功能正常运行。

## What Changes

### Phase 0: Public 表迁移至 A/C 类 Schema（优先执行）

**迁移清单**（迁移后需更新所有引用，保证原功能可用）：

| 当前位置 | 目标 Schema | 说明 |
|----------|-------------|------|
| `public.performance_scores` | `c_class` | 店铺绩效（100% 计算得出），合并或替换现有 `c_class.performance_scores_c` |
| `public.shop_health_scores` | `c_class` | 店铺健康度（100% 计算得出） |
| `public.shop_alerts` | `c_class` | 店铺预警（由 shop_health_scores 派生） |
| `public.sales_targets` | `a_class` | 目标主表（用户配置 + 达成缓存），与 `a_class.target_breakdown` 同属目标管理 |

**迁移后需更新的引用**：

- **目标管理**：`backend/routers/target_management.py`、`backend/services/target_sync_service.py`、`backend/routers/config_management.py`（若有）
- **Metabase Question SQL**：`business_overview_comparison.sql`、`business_overview_shop_racing.sql` 等中的 `public.sales_targets` → `a_class.sales_targets`
- **绩效管理**：`backend/routers/performance_management.py` 中 `PerformanceScore` 的 schema 引用、ORM 模型
- **target_breakdown 外键**：`a_class.target_breakdown.target_id` 原指向 `public.sales_targets.id`，迁移后改为 `a_class.sales_targets.id`
- **schema.py**：为上述模型添加 `{"schema": "a_class"}` 或 `{"schema": "c_class"}`，并调整 `__table_args__` 中的 FK 引用

**不迁移**：

- `public.fact_product_metrics`：B 类采集数据，非 C 类计算表
- `public.performance_config`：A 类权重配置，可保留 public 或迁移至 a_class（本阶段暂不迁移）

### Phase 1: 绩效公示优化

- 修复 `list_performance_scores` 中 `db.execute` 缺少 `await` 的问题（async 函数中必须 `await db.execute(...)`）
- 完善 `POST /api/performance/scores/calculate` 计算逻辑：
  - **数据源**：`a_class.target_breakdown`、`a_class.sales_targets`、Orders Model（或 b_class 订单表）、`fact_product_metrics`（或 Products Model）、`c_class.shop_health_scores`
  - **禁止**：引用已删除的 `fact_orders`
- 绩效计算完成后写入 `c_class.performance_scores`（迁移后）
- 无数据时返回空列表而非抛错

### Phase 2: 我的收入（员工自助）

- 新增「我的收入」页面，仅已关联员工的用户可访问
- **数据源优先级**：
  1. `a_class.payroll_records`（若有完整工资单，优先展示）
  2. `a_class.salary_structures`（底薪、岗位工资、津贴）+ `c_class.employee_commissions`（提成）+ `c_class.employee_performance`（绩效得分、达成率）
- **员工 C 类表数据来源**：`c_class.employee_commissions`、`c_class.employee_performance` 需由后端定时任务或 `POST /api/performance/scores/calculate` 等逻辑写入；若当前无写入逻辑，需在本次实现中新增（从 b_class 订单/员工-店铺关联计算提成与绩效）
- 未关联员工时显示「您尚未关联员工档案，请联系管理员」
- 可下钻到「绩效公示」查看绩效依据

### Phase 3: 菜单与入口

- 人力资源分组下新增「我的收入」菜单项
- 绩效公示、我的收入均可见

### 依赖关系

- **前置依赖**：`add-link-user-employee-management` 需先完成（Employee.user_id、我的档案）
- Phase 0 迁移需在 Phase 1 绩效计算逻辑完善之前完成，确保写入目标表为 `c_class.performance_scores`

## Impact

### 受影响的规格

- **hr-management**：ADDED - 绩效公示修复与优化、我的收入员工自助能力
- **database-design**：MODIFIED - public 表迁移至 a_class/c_class

### 受影响的代码与数据

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| Schema | `modules/core/db/schema.py` | 为 PerformanceScore、ShopHealthScore、ShopAlert、SalesTarget 添加 schema；更新 target_breakdown FK |
| 迁移 | `migrations/versions/` | 新建迁移：创建 a_class.sales_targets、c_class.performance_scores 等，迁移数据，删除 public 旧表 |
| 目标管理 | `backend/routers/target_management.py` | 更新 SalesTarget 引用为 a_class.sales_targets |
| 目标同步 | `backend/services/target_sync_service.py` | 更新 sales_targets、target_breakdown 引用 |
| 绩效管理 | `backend/routers/performance_management.py` | 添加 await、更新 PerformanceScore 引用、完善 calculate 数据源 |
| 配置管理 | `backend/routers/config_management.py` | 若有 list_sales_targets 等，更新为 a_class.sales_targets |
| SQL | `sql/metabase_questions/*.sql` | `public.sales_targets` → `a_class.sales_targets` |
| 我的收入 | `backend/routers/hr_management.py` | 新增 `GET /api/hr/me/income` |
| 前端 | `frontend/src/views/hr/MyIncome.vue` 等 | 新建我的收入页面、菜单、路由 |

### 数据源汇总（迁移后）

| 能力 | 数据表 | 关键字段 |
|------|--------|----------|
| 绩效公示（读） | `c_class.performance_scores` | platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score, operation_score, rank, performance_coefficient |
| 绩效公示（配置） | `public.performance_config` | sales_weight, profit_weight, key_product_weight, operation_weight |
| 绩效计算（写） | `c_class.performance_scores` | 同上 |
| 绩效计算（数据源） | `a_class.sales_targets`、`a_class.target_breakdown`、Orders Model、fact_product_metrics、`c_class.shop_health_scores` | 目标、达成、健康度 |
| 目标管理 | `a_class.sales_targets`、`a_class.target_breakdown` | 目标 CRUD、分解 |
| 我的收入 | `c_class.employee_commissions`、`c_class.employee_performance`、`a_class.salary_structures`、`a_class.payroll_records` | employee_code, year_month, commission_amount, performance_score, base_salary, net_salary |

### 非目标（Non-Goals）

- Phase 1 不实现员工-店铺关联表
- 不实现薪资条 PDF 导出、邮件推送
- `fact_product_metrics` 不迁移（B 类数据）

## 成功标准

- [ ] `public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts`、`public.sales_targets` 已迁移至对应 schema
- [ ] 目标管理 CRUD、目标分解、TargetSyncService 同步至 `a_class.sales_targets_a` 正常
- [ ] Metabase Question（business_overview_comparison、business_overview_shop_racing、business_overview_operational_metrics 等）引用 `a_class.sales_targets` 后正常
- [ ] 绩效公示页面可正常加载，无「查询绩效评分列表失败」报错
- [ ] 绩效计算可产出 `c_class.performance_scores` 记录
- [ ] 「我的收入」页面可用，已关联员工可查看本人收入
- [ ] 未关联员工访问「我的收入」时显示引导文案
- [ ] 菜单中人力资源下可见「绩效公示」「我的收入」

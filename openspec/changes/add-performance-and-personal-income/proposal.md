# Change: 绩效公示优化、我的收入与 Public 表 Schema 迁移

## Why

西虹ERP作为**决策支撑系统**，主打**数据公开透明**。当前存在以下问题：

1. **绩效公示**：页面显示「查询绩效评分列表失败」，`performance_scores` 表可能无数据或计算逻辑未完善；`db.execute` 缺少 `await` 导致异步查询失败
2. **个人收入缺失**：员工无法自助查看本人收入明细（底薪、绩效、提成、实发等）
3. **数据割裂**：存在 `c_class.employee_performance`、`c_class.employee_commissions` 等员工级 C 类表，但无前端入口；这两张表当前无写入逻辑，需明确数据来源
4. **Schema 分类不规范**：大量具有「计算功能」或「用户配置」的表仍在 `public` 中，应按三层数据分类迁移至 `a_class` 或 `c_class`

需要：优化绩效公示、新增「我的收入」、**将 public 中相关表完全迁移至 A/C 类 schema**，迁移后删除原表，确保目标管理、各 Question、绩效公示等功能正常运行。

## What Changes

### Phase 0: Public 表完全迁移至 A/C 类 Schema（优先执行）

**迁移清单**：

| 当前位置 | 目标 Schema | 目标表名 | 说明 |
|----------|-------------|----------|------|
| `public.sales_targets` | `a_class` | `a_class.sales_targets` | 目标主表（用户配置），迁移后更新 target_breakdown 外键，删除原表 |
| `public.performance_scores` | `c_class` | `c_class.performance_scores` | 店铺绩效（计算得出），合并或替换现有 `performance_scores_c`，删除原表 |
| `public.shop_health_scores` | `c_class` | `c_class.shop_health_scores` | 店铺健康度（计算得出），删除原表 |
| `public.shop_alerts` | `c_class` | `c_class.shop_alerts` | 店铺预警（派生自 shop_health_scores），删除原表 |

**重要说明**：
- `a_class.sales_targets`（新建）与 `a_class.sales_targets_a`（现有聚合表）是**两张不同的表**：
  - `sales_targets`：目标主表，含 target_name, target_type, period_start, period_end, status 等元数据
  - `sales_targets_a`：店铺月度聚合表，由 TargetSyncService 从 sales_targets + target_breakdown 同步，含 shop_id, year_month, 目标销售额
- 迁移不影响 `sales_targets_a`，TargetSyncService 继续正常工作

**迁移后需更新的引用**：

| 类型 | 涉及文件/对象 | 修改内容 |
|------|---------------|----------|
| 外键 | `a_class.target_breakdown.target_id` | 从 `public.sales_targets.id` 改为 `a_class.sales_targets.id` |
| ORM | `modules/core/db/schema.py` | SalesTarget 添加 `{"schema": "a_class"}`；TargetBreakdown 外键引用更新 |
| 后端 | `backend/routers/target_management.py` | 确保 SalesTarget 使用 a_class |
| 后端 | `backend/services/target_sync_service.py` | 更新 sales_targets 引用 |
| 后端 | `backend/routers/config_management.py` | 若有 sales_targets SQL，更新为 a_class.sales_targets |
| 后端 | `backend/routers/performance_management.py` | PerformanceScore 使用 c_class |
| SQL | `sql/metabase_questions/business_overview_comparison.sql` | `public.sales_targets` → `a_class.sales_targets` |
| SQL | `sql/metabase_questions/business_overview_shop_racing.sql` | `public.sales_targets` → `a_class.sales_targets` |
| SQL | 其他引用上述表的 SQL | 更新 schema 引用 |

**不迁移**：
- `public.fact_product_metrics`：B 类采集数据
- `public.performance_config`：A 类权重配置，本阶段暂不迁移（可后续迁移至 a_class）

### Phase 1: 绩效公示优化

- 修复 `list_performance_scores` 中 `db.execute` 缺少 `await` 的问题
- 完善 `POST /api/performance/scores/calculate` 计算逻辑：
  - **数据源**：`a_class.target_breakdown`、`a_class.sales_targets`、Orders Model（或 b_class 订单表）、`fact_product_metrics`、`c_class.shop_health_scores`
  - **禁止**：引用已删除的 `fact_orders`
- 绩效计算完成后写入 `c_class.performance_scores`（迁移后）
- 无数据时返回空列表而非抛错

### Phase 2: 我的收入（员工自助）

- 新增「我的收入」页面，仅已关联员工的用户可访问
- **数据源优先级**：
  1. `a_class.payroll_records`（若有完整工资单，优先展示）
  2. `a_class.salary_structures`（底薪、岗位工资、津贴）+ `c_class.employee_commissions`（提成）+ `c_class.employee_performance`（绩效得分、达成率）
- **员工 C 类表数据来源**：需由后端定时任务或 `POST /api/performance/scores/calculate` 写入
- 未关联员工时显示「您尚未关联员工档案，请联系管理员」
- 可下钻到「绩效公示」查看绩效依据

### Phase 3: 菜单与入口

- 人力资源分组下新增「我的收入」菜单项
- 绩效公示、我的收入均可见

### 依赖关系

- **前置依赖**：`add-link-user-employee-management` 需先完成（Employee.user_id、我的档案）
- Phase 0 迁移需在 Phase 1 绩效计算逻辑完善之前完成

## Impact

### 受影响的规格

- **hr-management**：ADDED - 绩效公示修复与优化、我的收入员工自助能力
- **database-design**：MODIFIED - public 表完全迁移至 a_class/c_class，迁移后删除原表

### 受影响的代码与数据

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| Schema | `modules/core/db/schema.py` | SalesTarget、PerformanceScore、ShopHealthScore、ShopAlert 添加 schema；TargetBreakdown 外键更新 |
| 迁移 | `migrations/versions/` | 新建迁移：创建 a_class.sales_targets、c_class.performance_scores 等，迁移数据，更新外键，删除 public 旧表 |
| 目标管理 | `backend/routers/target_management.py` | 更新 SalesTarget 引用 |
| 目标同步 | `backend/services/target_sync_service.py` | 更新 sales_targets 引用 |
| 绩效管理 | `backend/routers/performance_management.py` | 添加 await、更新 PerformanceScore 引用、完善 calculate 数据源 |
| SQL | `sql/metabase_questions/*.sql` | 更新所有 public 表引用 |
| 我的收入 | `backend/routers/hr_management.py` | 新增 `GET /api/hr/me/income` |
| 前端 | `frontend/src/views/hr/MyIncome.vue` 等 | 新建我的收入页面、菜单、路由 |

### 数据源汇总（迁移后）

| 能力 | 数据表 | 关键字段 |
|------|--------|----------|
| 目标管理 | `a_class.sales_targets`、`a_class.target_breakdown` | target_name, target_type, period_start, period_end, target_amount, status |
| 目标聚合 | `a_class.sales_targets_a` | shop_id, year_month, 目标销售额（由 TargetSyncService 同步） |
| 绩效公示（读） | `c_class.performance_scores` | platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score, operation_score, rank, performance_coefficient |
| 绩效公示（配置） | `public.performance_config` | sales_weight, profit_weight, key_product_weight, operation_weight |
| 绩效计算（数据源） | `a_class.sales_targets`、`a_class.target_breakdown`、Orders Model、fact_product_metrics、`c_class.shop_health_scores` | 目标、达成、健康度 |
| 我的收入 | `c_class.employee_commissions`、`c_class.employee_performance`、`a_class.salary_structures`、`a_class.payroll_records` | employee_code, year_month, commission_amount, performance_score, base_salary, net_salary |

### 非目标（Non-Goals）

- Phase 1 不实现员工-店铺关联表
- 不实现薪资条 PDF 导出、邮件推送
- `fact_product_metrics` 不迁移（B 类数据）
- `performance_config` 本阶段不迁移

## 成功标准

- [ ] `public.sales_targets` 已迁移至 `a_class.sales_targets`，原表已删除
- [ ] `a_class.target_breakdown.target_id` 外键指向 `a_class.sales_targets.id`
- [ ] `public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 已迁移至 c_class，原表已删除
- [ ] 目标管理 CRUD、目标分解、TargetSyncService 同步正常
- [ ] Metabase Question（business_overview_comparison、business_overview_shop_racing 等）使用 `a_class.sales_targets` 后正常
- [ ] 绩效公示页面可正常加载，无「查询绩效评分列表失败」报错
- [ ] 绩效计算可产出 `c_class.performance_scores` 记录
- [ ] 「我的收入」页面可用，已关联员工可查看本人收入
- [ ] 未关联员工访问「我的收入」时显示引导文案
- [ ] 菜单中人力资源下可见「绩效公示」「我的收入」

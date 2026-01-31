# Change: 绩效公示优化、我的收入与 Public 表 Schema 迁移

## Why

西虹ERP作为**决策支撑系统**，主打**数据公开透明**。当前存在以下问题：

1. **绩效公示**：页面显示「查询绩效评分列表失败」，`performance_scores` 表可能无数据或计算逻辑未完善；`db.execute` 缺少 `await` 导致异步查询失败
2. **个人收入缺失**：员工无法自助查看本人收入明细（底薪、绩效、提成、实发等）
3. **数据割裂**：存在 `c_class.employee_performance`、`c_class.employee_commissions` 等员工级 C 类表，但无前端入口；这两张表当前无写入逻辑，需明确数据来源
4. **Schema 分类不规范**：大量具有「计算功能」或「用户配置」的表仍在 `public` 中，应按三层数据分类迁移至 `a_class` 或 `c_class`

需要：优化绩效公示、新增「我的收入」、**将 public 中相关表完全迁移至 A/C 类 schema**，迁移后删除原表，确保目标管理、各 Question、绩效公示等功能正常运行。

## 前置依赖（已完成）

**add-link-user-employee-management** 已闭环（已归档至 `archive/2026-01-31-add-link-user-employee-management`）：
- `a_class.employees` 已有 `user_id` 列（关联 dim_users.user_id）
- `GET /api/hr/me/profile`、`PUT /api/hr/me/profile` 已实现
- 我的档案页面已就绪

本提案的「我的收入」可直接基于上述能力实现。

## What Changes

### Phase 0: Public 表完全迁移至 A/C 类 Schema（优先执行）

**迁移清单**：

| 当前位置 | 目标 Schema | 目标表名 | 说明 |
|----------|-------------|----------|------|
| `public.sales_targets` | `a_class` | `a_class.sales_targets` | 目标主表（用户配置），迁移后更新 target_breakdown 外键，删除原表 |
| `public.performance_scores` | `c_class` | `c_class.performance_scores` | 店铺绩效（计算得出），以 PerformanceScore 完整字段为准，合并/替换 performance_scores_c 后删除原表 |
| `public.shop_health_scores` | `c_class` | `c_class.shop_health_scores` | 店铺健康度（计算得出），删除原表 |
| `public.shop_alerts` | `c_class` | `c_class.shop_alerts` | 店铺预警（派生自 shop_health_scores），删除原表 |

**重要说明**：
- `a_class.sales_targets`（新建）与 `a_class.sales_targets_a`（现有聚合表）是**两张不同的表**：
  - `sales_targets`：目标主表，含 target_name, target_type, period_start, period_end, status 等元数据
  - `sales_targets_a`：店铺月度聚合表，由 TargetSyncService 从 sales_targets + target_breakdown 同步，含 shop_id, year_month, 目标销售额
- 迁移不影响 `sales_targets_a`，TargetSyncService 继续正常工作

**sales_targets 专项（高优先级）**：
- **依赖链**：目标管理前端 → target_management API → SalesTarget ORM；TargetSyncService 读取 sales_targets + target_breakdown → 写入 sales_targets_a；Metabase Question（comparison、shop_racing）直接引用 sales_targets；operational_metrics 引用 sales_targets_a（间接依赖）
- **迁移顺序**：Phase 0 中 sales_targets 应**最先**迁移（target_breakdown 外键依赖它，TargetSyncService、多个 Question 依赖它）
- **原子性部署**：迁移脚本 + schema.py + target_sync_service + target_management + Metabase SQL + init_metabase 必须**同批次**部署，不可分批
- **验证清单**：目标管理 CRUD → TargetSyncService 同步 → 业务概览（数据对比、店铺赛马、经营指标）→ 确认 sales_targets_a 有数据

**PerformanceScore 合并策略**：
- 以 `public.performance_scores`（PerformanceScore）的完整字段为准：platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score, operation_score, rank, performance_coefficient
- `c_class.performance_scores_c`（PerformanceScoreC）字段较少（shop_id, period, total_score, sales_score, quality_score），迁移时合并到 `c_class.performance_scores`；**映射规则**：quality_score → operation_score（运营相关）；platform_code 需通过 dim_shops（shop_id）关联获取

**config_management.py 特别说明**：
- `backend/routers/config_management.py` 的 `/api/config/sales-targets` 使用原始 SQL 引用 `sales_targets`，其字段结构（shop_id, year_month, target_sales_amount, target_order_count）与 `public.sales_targets` ORM 定义不同
- 实施前需确认：若该 API 操作的是店铺月度目标（与 `sales_targets_a` 概念一致），应改为 `a_class.sales_targets_a` 并适配中文字段名；若为独立配置表，迁移时需单独处理

**迁移后需更新的引用**：

| 类型 | 涉及文件/对象 | 修改内容 |
|------|---------------|----------|
| 外键 | `a_class.target_breakdown.target_id` | 从 `public.sales_targets.id` 改为 `a_class.sales_targets.id` |
| ORM | `modules/core/db/schema.py` | SalesTarget、PerformanceScore、ShopHealthScore、ShopAlert 添加 schema；TargetBreakdown 外键更新；删除 PerformanceScoreC（若合并） |
| 后端 | `backend/routers/target_management.py` | 确保 SalesTarget 使用 a_class；错误提示「sales_targets 表不存在」→「a_class.sales_targets 表不存在」 |
| 后端 | `backend/services/target_sync_service.py` | 更新 sales_targets 引用为 a_class.sales_targets |
| 后端 | `backend/routers/config_management.py` | 根据调查结果：更新为 a_class.sales_targets 或 a_class.sales_targets_a |
| 后端 | `backend/routers/performance_management.py` | PerformanceScore 使用 c_class |
| 脚本 | `scripts/diagnose_targets_db.py` | check_table_exists 增加 schema 参数 |
| 脚本 | `scripts/diagnose_target_sync.py` | 检查 a_class.sales_targets |
| 脚本 | `scripts/check_database_health.py` | 表清单 schema 更新 |
| 脚本 | `scripts/verify_migration_status.py` | 期望表及 schema 列表更新 |
| 脚本 | `scripts/init_v4_11_0_tables.py` | check_table_exists 支持多 schema |
| 脚本 | 其他引用上述表的脚本 | 更新 schema 或表名引用 |
| SQL | `sql/metabase_questions/*.sql` | `public.sales_targets` → `a_class.sales_targets` |
| SQL | `sql/migrate_tables_to_schemas.sql` | 与本提案冲突（sales_targets 置 core），需更新为 a_class 或标注已废弃 |

**跨 schema 外键**：
- `c_class.performance_scores`、`c_class.shop_health_scores` 有外键指向 `public.dim_shops`，PostgreSQL 支持跨 schema 外键，迁移后需验证

**回滚与数据安全**：
- 迁移脚本应在删除原表前完成数据迁移与校验；sales_targets 影响面大，建议迁移前备份
- 建议在 downgrade 中实现反向迁移（从 a_class/c_class 回迁至 public）

**不迁移**：
- `public.fact_product_metrics`：B 类采集数据
- `public.performance_config`：A 类权重配置，本阶段暂不迁移

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

## Impact

### 受影响的规格

- **hr-management**：ADDED - 绩效公示修复与优化、我的收入员工自助能力
- **database-design**：MODIFIED - public 表完全迁移至 a_class/c_class，迁移后删除原表

### 受影响的代码与数据

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| Schema | `modules/core/db/schema.py` | SalesTarget、PerformanceScore、ShopHealthScore、ShopAlert 添加 schema；TargetBreakdown 外键更新；PerformanceScoreC 合并后删除 |
| 迁移 | `migrations/versions/` | 新建迁移：创建 a_class.sales_targets、c_class.performance_scores 等，迁移数据，更新外键，删除 public 旧表 |
| 目标管理 | `backend/routers/target_management.py` | 确保 SalesTarget 使用 a_class；错误提示「sales_targets 表不存在」→「a_class.sales_targets 表不存在」 |
| 目标同步 | `backend/services/target_sync_service.py` | 更新 sales_targets 引用 |
| 配置管理 | `backend/routers/config_management.py` | 根据调查结果更新 sales_targets 或 sales_targets_a 引用 |
| 绩效管理 | `backend/routers/performance_management.py` | 添加 await、更新 PerformanceScore 引用、完善 calculate 数据源 |
| 脚本 | `scripts/` 中相关脚本 | 更新 schema/表名引用 |
| SQL | `sql/metabase_questions/*.sql` | 更新 public 表引用 |
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
- [ ] config_management 的 sales-targets API（若有）迁移后可用
- [ ] 绩效公示页面可正常加载，无「查询绩效评分列表失败」报错
- [ ] 绩效计算可产出 `c_class.performance_scores` 记录
- [ ] 「我的收入」页面可用，已关联员工可查看本人收入
- [ ] 未关联员工访问「我的收入」时显示引导文案
- [ ] 菜单中人力资源下可见「绩效公示」「我的收入」

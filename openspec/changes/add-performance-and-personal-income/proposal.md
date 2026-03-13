# Change: 绩效公示优化、我的收入与 Public 表 Schema 迁移

## Why

西虹ERP作为**决策支撑系统**，主打**数据公开透明**。当前存在以下问题：

1. **绩效公示与绩效配置**：页面显示「查询绩效评分列表失败」，`performance_scores` 表可能无数据或计算逻辑未完善；**绩效相关 async 路由内** `db.execute` 缺少 `await` 导致异步查询失败（含绩效公示列表与绩效配置 CRUD 接口）
2. **个人收入缺失**：员工无法自助查看本人收入明细（底薪、绩效、提成、实发等）
3. **数据割裂**：存在 `c_class.employee_performance`、`c_class.employee_commissions` 等员工级 C 类表，但无前端入口；这两张表当前无写入逻辑，需明确数据来源
4. **Schema 分类不规范**：大量具有「计算功能」或「用户配置」的表仍在 `public` 中，应按三层数据分类迁移至 `a_class` 或 `c_class`

需要：优化绩效公示、新增「我的收入」、**将 public 中相关表完全迁移至 A/C 类 schema**，迁移后删除原表，确保目标管理、各 Question、绩效公示等功能正常运行。

## 实现顺序（与 add-performance-calculation-via-metabase 的关系）

- **本提案 Phase 0（表迁移）须先于 add-performance-calculation-via-metabase 完成**：Metabase 绩效计算方案依赖 `a_class.sales_targets`、`c_class.performance_scores`、`c_class.shop_health_scores` 已存在；若先做 Metabase 方案而迁移未执行，则 SQL 引用的表不存在。
- **推荐顺序**：1）本提案 Phase 0（迁移 + 引用更新 + 验证）→ 2）add-performance-calculation-via-metabase（实现 calculate 逻辑）→ 3）本提案 Phase 1–6（await 修复、我的收入、菜单与验证）。

## 前置依赖（已完成）

**add-link-user-employee-management** 已闭环（已归档至 `archive/2026-01-31-add-link-user-employee-management`）：
- `a_class.employees` 已有 `user_id` 列（关联 dim_users.user_id）
- `GET /api/hr/me/profile`、`PUT /api/hr/me/profile` 已实现
- 我的档案页面已就绪

本提案的「我的收入」可直接基于上述能力实现。

## What Changes

### Phase 0: Public 表完全迁移至 A/C 类 Schema（优先执行）

**实施注意**：若仓库中已存在迁移脚本（如 `20260131_migrate_public_tables_to_a_c_class.py`），则以执行 `alembic upgrade head`、验证结果、以及更新后端/脚本/SQL 引用为主，无需重复编写迁移；若为新环境则按 tasks 0.3–0.4 编写并执行迁移。

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

**config_management.py 说明（已明确）**：
- `backend/routers/config_management.py` 的销售目标 API 已使用 `a_class.sales_targets_a`（店铺月度聚合表），与 `public.sales_targets` 目标主表为不同概念；迁移 `public.sales_targets` 至 `a_class.sales_targets` 不影响该 API，**无需因本迁移再改** config_management。

**迁移后需更新的引用**：

| 类型 | 涉及文件/对象 | 修改内容 |
|------|---------------|----------|
| 外键 | `a_class.target_breakdown.target_id` | 从 `public.sales_targets.id` 改为 `a_class.sales_targets.id` |
| ORM | `modules/core/db/schema.py` | SalesTarget、PerformanceScore、ShopHealthScore、ShopAlert 添加 schema；TargetBreakdown 外键更新；删除 PerformanceScoreC（若合并） |
| 后端 | `backend/routers/target_management.py` | 确保 SalesTarget 使用 a_class；错误提示「sales_targets 表不存在」→「a_class.sales_targets 表不存在」 |
| 后端 | `backend/services/target_sync_service.py` | 更新 sales_targets 引用为 a_class.sales_targets |
| 后端 | `backend/routers/config_management.py` | 已使用 a_class.sales_targets_a，无需因本迁移修改 |
| 后端 | `backend/routers/performance_management.py` | PerformanceScore 使用 c_class；**所有 async 路由内** db.execute 改为 await db.execute（含绩效公示与绩效配置接口） |
| 脚本 | `scripts/diagnose_targets_db.py` | check_table_exists 增加 schema 参数 |
| 脚本 | `scripts/diagnose_target_sync.py` | 检查 a_class.sales_targets |
| 脚本 | `scripts/check_database_health.py` | 表清单 schema 更新 |
| 脚本 | `scripts/verify_migration_status.py` | 期望表及 schema 列表更新 |
| 脚本 | `scripts/init_v4_11_0_tables.py` | check_table_exists 支持多 schema |
| 脚本 | 其他引用上述表的脚本 | 更新 schema 或表名引用 |
| SQL | `sql/metabase_questions/*.sql` | `public.sales_targets` → `a_class.sales_targets` |
| SQL | `sql/migrate_tables_to_schemas.sql` | 已标注 DEPRECATED（sales_targets 由 Alembic 迁至 a_class），实施时确认即可 |

**跨 schema 外键**：
- `c_class.performance_scores`、`c_class.shop_health_scores` 有外键指向 `public.dim_shops`，PostgreSQL 支持跨 schema 外键，迁移后需验证

**回滚与数据安全**：
- 迁移脚本应在删除原表前完成数据迁移与校验；sales_targets 影响面大，建议迁移前备份
- 建议在 downgrade 中实现反向迁移（从 a_class/c_class 回迁至 public）

**其他说明**：
- `backend/routers/dashboard_api.py` 仅引用 `a_class.sales_targets_a`，不引用 `sales_targets`，迁移无需修改该文件。

**不迁移**：
- `public.fact_product_metrics`：B 类采集数据
- `public.performance_config`：A 类权重配置，本阶段暂不迁移

### Phase 1: 绩效公示与绩效配置优化

- 修复 **所有** `backend/routers/performance_management.py` 中 async 路由内 `db.execute` 缺少 `await` 的问题（含：`list_performance_scores`、`get_shop_performance`、`list_performance_configs`、`get_performance_config`、`update_performance_config`、`delete_performance_config`）
- **`POST /api/performance/scores/calculate` 计算逻辑**：**具体实现**由 **add-performance-calculation-via-metabase** 负责（Metabase SQL + 后端调用并写入 `c_class.performance_scores`）。本提案仅确保：接口可调用、无 await 问题、数据源表（a_class/c_class）已就绪；若先于 Metabase 方案实施，可采用占位实现（如返回成功或写入占位值）以保证流程可跑通。
- 无数据时返回空列表而非抛错

### Phase 2: 我的收入（员工自助）

- 新增 `GET /api/hr/me/income`，**契约**：请求/响应 Pydantic 模型须定义在 `backend/schemas/`（禁止在 routers 内定义），路由使用 `response_model` 引用（符合 Contract-First）。
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

- **hr-management**：ADDED - 绩效公示修复与优化、我的收入员工自助能力（本 change 含 `specs/hr-management/spec.md` 增量）
- **database-design**：MODIFIED - public 表完全迁移至 a_class/c_class，迁移后删除原表；变更以本提案与 Alembic 迁移脚本为准（若项目无独立 database-design spec，可不新增 delta 文件）

### 受影响的代码与数据

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| Schema | `modules/core/db/schema.py` | SalesTarget、PerformanceScore、ShopHealthScore、ShopAlert 添加 schema；TargetBreakdown 外键更新；PerformanceScoreC 合并后删除 |
| 迁移 | `migrations/versions/` | 新建迁移：创建 a_class.sales_targets、c_class.performance_scores 等，迁移数据，更新外键，删除 public 旧表 |
| 目标管理 | `backend/routers/target_management.py` | 确保 SalesTarget 使用 a_class；错误提示「sales_targets 表不存在」→「a_class.sales_targets 表不存在」 |
| 目标同步 | `backend/services/target_sync_service.py` | 更新 sales_targets 引用 |
| 配置管理 | `backend/routers/config_management.py` | 已使用 a_class.sales_targets_a，无需因本迁移修改 |
| 绩效管理 | `backend/routers/performance_management.py` | 所有 async 路由内 db.execute 改为 await；PerformanceScore 使用 c_class；calculate 具体实现由 add-performance-calculation-via-metabase 负责 |
| 脚本 | `scripts/` 中相关脚本 | 更新 schema/表名引用 |
| SQL | `sql/metabase_questions/*.sql` | 更新 public 表引用 |
| 我的收入 | `backend/schemas/` | 定义 MyIncomeResponse 等（Contract-First）；若已实现在 router 中则迁移至 schemas 并更新引用 |
| 我的收入 | `backend/routers/hr_management.py` | 新增 `GET /api/hr/me/income`，从 schemas 导入响应模型 |
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
- [ ] 绩效公示与绩效配置相关接口在异步环境下均使用 `await db.execute`，无同步 `db.execute`；绩效公示页面可正常加载，无「查询绩效评分列表失败」报错
- [ ] 绩效计算可产出 `c_class.performance_scores` 记录（完整计算依赖 add-performance-calculation-via-metabase；本提案可先以占位写入验证链路）
- [ ] 「我的收入」页面可用，已关联员工可查看本人收入
- [ ] 未关联员工访问「我的收入」时显示引导文案
- [ ] 菜单中人力资源下可见「绩效公示」「我的收入」

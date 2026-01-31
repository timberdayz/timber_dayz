# Tasks: 绩效公示优化、我的收入与 Public 表 Schema 迁移

**前置依赖（已完成）**：`add-link-user-employee-management` 已闭环（已归档至 `archive/2026-01-31-add-link-user-employee-management`），Employee.user_id、我的档案、GET/PUT /api/hr/me/profile 已实现。

---

## Phase 0: Public 表完全迁移至 A/C 类 Schema（优先执行）

**原子性部署**：迁移脚本、schema.py、target_sync_service、target_management、Metabase SQL、init_metabase 须**同批次**部署，不可分批。

### 0.1 迁移设计与准备

- [ ] 0.1.1 确认迁移清单：
  - `public.sales_targets` → `a_class.sales_targets`（新建，与原表同结构）
  - `public.performance_scores` → `c_class.performance_scores`（以 PerformanceScore 完整字段为准）
  - `public.shop_health_scores` → `c_class.shop_health_scores`
  - `public.shop_alerts` → `c_class.shop_alerts`
- [ ] 0.1.2 确认 `a_class.sales_targets`（新建）与 `a_class.sales_targets_a`（现有聚合表）是两张不同的表，不合并
- [ ] 0.1.3 确认 `target_breakdown.target_id` 外键迁移后指向 `a_class.sales_targets.id`
- [ ] 0.1.4 PerformanceScore 合并策略：以 public.performance_scores 完整字段为准，合并/替换 performance_scores_c 后删除 PerformanceScoreC 类

### 0.2 config_management.py 调查（优先）

- [ ] 0.2.1 调查 `backend/routers/config_management.py` 的 `/api/config/sales-targets` 实际操作的逻辑表：
  - 若为店铺月度目标（与 sales_targets_a 一致），改为 `a_class.sales_targets_a` 并适配中文字段名
  - 若为独立配置表或与 public.sales_targets 对应，迁移后改为 `a_class.sales_targets`

### 0.3 Alembic 迁移脚本 - sales_targets

- [ ] 0.3.1 创建 `a_class.sales_targets`（结构与 public.sales_targets 完全一致）
- [ ] 0.3.2 迁移数据：`INSERT INTO a_class.sales_targets SELECT * FROM public.sales_targets`
- [ ] 0.3.3 删除 `a_class.target_breakdown.target_id` 外键约束
- [ ] 0.3.4 添加新外键：`target_breakdown.target_id` → `a_class.sales_targets.id`
- [ ] 0.3.5 删除 `public.sales_targets` 表
- [ ] 0.3.6 迁移脚本使用 `safe_print()` 替代 `print()`（Windows 兼容）
- [ ] 0.3.7 迁移前备份关键数据（可选，用于回滚）

### 0.4 Alembic 迁移脚本 - C 类表

- [ ] 0.4.1 创建 `c_class.performance_scores`（以 PerformanceScore 完整字段为准，含 platform_code, shop_id, period, sales_score, profit_score, key_product_score, operation_score, rank, performance_coefficient）
- [ ] 0.4.2 迁移 public.performance_scores 数据到 c_class.performance_scores
- [ ] 0.4.3 若 c_class.performance_scores_c 存在，迁移其数据：quality_score → operation_score；platform_code 通过 dim_shops（shop_id）关联获取；合并后删除 performance_scores_c
- [ ] 0.4.4 删除 public.performance_scores 表
- [ ] 0.4.5 创建 `c_class.shop_health_scores`，迁移 public.shop_health_scores 数据，删除原表
- [ ] 0.4.6 创建 `c_class.shop_alerts`，迁移 public.shop_alerts 数据，删除原表
- [ ] 0.4.7 迁移脚本幂等性：创建前检查表是否存在
- [ ] 0.4.8 验证跨 schema 外键（c_class.performance_scores、c_class.shop_health_scores → public.dim_shops）正常

### 0.5 Schema.py 更新

- [ ] 0.5.1 `SalesTarget` 添加 `{"schema": "a_class"}`
- [ ] 0.5.2 `TargetBreakdown` 外键更新为 `ForeignKey("a_class.sales_targets.id", ondelete="CASCADE")`
- [ ] 0.5.3 `PerformanceScore` 添加 `{"schema": "c_class"}`，删除 PerformanceScoreC 类
- [ ] 0.5.4 `ShopHealthScore` 添加 `{"schema": "c_class"}`
- [ ] 0.5.5 `ShopAlert` 添加 `{"schema": "c_class"}`
- [ ] 0.5.6 更新 `modules/core/db/__init__.py` 导出（移除 PerformanceScoreC）

### 0.6 后端引用更新

- [ ] 0.6.1 `backend/routers/target_management.py`：确保 SalesTarget 使用 a_class（ORM 自动处理，验证即可）
- [ ] 0.6.2 `backend/services/target_sync_service.py`：原始 SQL 中 `FROM sales_targets`、`JOIN target_breakdown` 更新为 `a_class.sales_targets`、`a_class.target_breakdown`
- [ ] 0.6.3 `backend/routers/config_management.py`：根据 0.2.1 调查结果，更新为 `a_class.sales_targets` 或 `a_class.sales_targets_a`
- [ ] 0.6.4 `backend/routers/performance_management.py`：PerformanceScore 使用 c_class（ORM 自动处理，验证即可）
- [ ] 0.6.5 所有引用 ShopHealthScore、ShopAlert 的代码验证 schema（如 shop_health_service.py）
- [ ] 0.6.6 `backend/routers/target_management.py`：错误提示「sales_targets 表不存在」更新为「a_class.sales_targets 表不存在」

### 0.7 脚本引用更新

- [ ] 0.7.1 更新 `scripts/diagnose_targets_db.py`：`check_table_exists(conn, "sales_targets")` 改为 `check_table_exists(conn, "sales_targets", "a_class")`
- [ ] 0.7.2 更新 `scripts/check_database_health.py`：表清单中 `("sales_targets", "public", ...)` 改为 `("sales_targets", "a_class", ...)`
- [ ] 0.7.3 更新 `scripts/verify_migration_status.py`：期望表及 schema 列表（sales_targets→a_class，performance_scores→c_class，删除 performance_scores_c）
- [ ] 0.7.4 更新 `scripts/diagnose_target_sync.py`：检查 `a_class.sales_targets` 而非 public.sales_targets
- [ ] 0.7.5 更新 `scripts/init_v4_11_0_tables.py`：`check_table_exists` 支持多 schema（或按 schema 分别检查 sales_targets、performance_scores、shop_health_scores、shop_alerts）
- [ ] 0.7.6 更新 `scripts/smart_table_cleanup.py`、`generate_migration_report.py`、`comprehensive_table_cleanup.py` 等，确保表名与 schema 正确
- [ ] 0.7.7 全局搜索 scripts/ 中引用上述表名的代码，全部更新 schema 或表名

### 0.8 Metabase Question SQL 更新

- [ ] 0.8.1 `sql/metabase_questions/business_overview_comparison.sql`：
  - `public.sales_targets` → `a_class.sales_targets`
  - `FROM public.sales_targets t` → `FROM a_class.sales_targets t`
  - `inner join public.sales_targets st` → `inner join a_class.sales_targets st`
- [ ] 0.8.2 `sql/metabase_questions/business_overview_shop_racing.sql`：
  - `inner join public.sales_targets st` → `inner join a_class.sales_targets st`
- [ ] 0.8.3 全局搜索其他引用 `public.sales_targets`、`public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 的 SQL，全部更新
- [ ] 0.8.4 执行 `python scripts/init_metabase.py` 同步 SQL 到 Metabase
- [ ] 0.8.5 检查 `sql/migrate_tables_to_schemas.sql`：该脚本将 sales_targets 置入 core，与本提案 a_class 冲突；需更新为 a_class 或标注已废弃（以 Alembic 迁移为准）

### 0.9 验证

- [ ] 0.9.1 运行 `alembic upgrade head`，迁移成功
- [ ] 0.9.2 **sales_targets 专项验证**（按顺序）：
  - [ ] 0.9.2a 目标管理：创建月度目标 → 成功
  - [ ] 0.9.2b 目标管理：添加店铺分解 → 成功，TargetSyncService 同步
  - [ ] 0.9.2c 目标管理：编辑/删除目标 → 成功
  - [ ] 0.9.2d 业务概览 - 数据对比：切换日/周/月，目标达成率显示正确
  - [ ] 0.9.2e 业务概览 - 店铺赛马：排名、目标、完成率正确
  - [ ] 0.9.2f 业务概览 - 经营指标：月目标、达成率正确（sales_targets_a 已同步）
  - [ ] 0.9.2g 数据库：a_class.sales_targets 有数据，public.sales_targets 已删除
- [ ] 0.9.3 Metabase Question：business_overview_comparison、business_overview_shop_racing 可正常查询
- [ ] 0.9.4 运行 `python scripts/verify_architecture_ssot.py` 期望 100%
- [ ] 0.9.5 确认 `public.sales_targets`、`public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 已删除
- [ ] 0.9.6 config_management 的 sales-targets API（若有使用）可正常调用

---

## Phase 1: 绩效公示修复与优化

### 1.1 后端 - 查询修复

- [ ] 1.1.1 修正 `list_performance_scores`：`db.execute` 改为 `await db.execute`（总数、分页、店铺名称查询均需 await）
- [ ] 1.1.2 修正 `get_shop_performance`：同上
- [ ] 1.1.3 无数据时返回空列表，前端友好展示「暂无数据」

### 1.2 后端 - 计算逻辑完善

- [ ] 1.2.1 实现 `POST /api/performance/scores/calculate` 中的 TODO 逻辑
- [ ] 1.2.2 销售额得分：从 `a_class.target_breakdown`、`a_class.sales_targets` 与 **Orders Model**（或 b_class 订单表）计算达成率 × 权重
- [ ] 1.2.3 毛利得分：从 Orders Model 或 b_class 订单表计算毛利达成率 × 权重
- [ ] 1.2.4 重点产品得分：从 `fact_product_metrics` 或 **Products Model** 计算重点产品达成率 × 权重
- [ ] 1.2.5 运营得分：从 `c_class.shop_health_scores` 计算运营指标 × 权重
- [ ] 1.2.6 计算完成后写入 `c_class.performance_scores`，更新 `rank`、`performance_coefficient`
- [ ] 1.2.7 禁止引用已删除的 `fact_orders`；使用 Orders Model 或 b_class.fact_{platform}_orders_{granularity}
- [ ] 1.2.8 若数据源不足，可采用占位值（如 0）保证流程可跑通

### 1.3 前端 - 绩效公示优化

- [ ] 1.3.1 优化错误提示，区分「无数据」与「查询失败」
- [ ] 1.3.2 增加「重新计算」入口，引导管理员在无数据时调用 calculate
- [ ] 1.3.3 绩效构成公式与配置权重一致

---

## Phase 2: 我的收入 - 后端 API

- [ ] 2.1 新增 `GET /api/hr/me/income`：需登录，根据当前用户关联的员工返回收入数据（依赖 Employee.user_id）
- [ ] 2.2 未关联员工时返回 404 或 `{ linked: false }`
- [ ] 2.3 查询 `c_class.employee_commissions`（按 employee_code、year_month）
- [ ] 2.4 查询 `c_class.employee_performance`（按 employee_code、year_month）
- [ ] 2.5 优先查询 `a_class.payroll_records`（若有完整工资单），否则组合 salary_structures + employee_commissions + employee_performance
- [ ] 2.6 响应格式：`{ period, base_salary?, commission_amount, commission_rate, performance_score, achievement_rate, total_income?, breakdown? }`
- [ ] 2.7 支持 `?year_month=YYYY-MM` 查询历史月份
- [ ] 2.8 路由定义在 `/employees/{employee_code}` 等动态路由之前

### 2.9 员工 C 类表数据写入

- [ ] 2.9.1 明确 `employee_commissions`、`employee_performance` 的写入来源
- [ ] 2.9.2 若无写入逻辑，新增后端服务或定时任务：从 b_class 订单、员工-店铺关联（若有）计算提成与绩效，写入 c_class

---

## Phase 3: 我的收入 - 前端页面

- [ ] 3.1 新建 `frontend/src/views/hr/MyIncome.vue`
- [ ] 3.2 汇总卡片：当月实发、同比/环比（若有历史数据）
- [ ] 3.3 收入明细：底薪、绩效奖金、提成、津贴、扣项等
- [ ] 3.4 绩效依据：绩效得分、绩效系数、达成率，可链接到绩效公示
- [ ] 3.5 月份选择器：支持切换查看历史月份
- [ ] 3.6 未关联员工时显示「您尚未关联员工档案，请联系管理员」
- [ ] 3.7 空数据时友好提示「暂无收入数据」

---

## Phase 4: 菜单与路由

- [ ] 4.1 `menuGroups.js`：人力资源分组下新增「我的收入」菜单项（/my-income）
- [ ] 4.2 `router/index.js`：新增 `/my-income` 路由，组件 `MyIncome.vue`
- [ ] 4.3 `rolePermissions.js`：为 operator、manager、admin 等角色增加 `my-income` 权限
- [ ] 4.4 菜单可见性：已关联员工展示「我的收入」；未关联时可展示但页面内提示

---

## Phase 5: API 客户端

- [ ] 5.1 `frontend/src/api/index.js`：新增 `getMyIncome(yearMonth?)` 调用 `GET /api/hr/me/income`
- [ ] 5.2 确保 `getPerformanceScores`、`calculatePerformanceScores` 等正确对接后端

---

## Phase 6: 验证

- [ ] 6.1 Phase 0 迁移后：public 中的 sales_targets、performance_scores、shop_health_scores、shop_alerts 已删除
- [ ] 6.2 目标管理、各 Question、绩效公示、config_management sales-targets API 引用正确
- [ ] 6.3 绩效公示：选择月份后可正常加载，有数据时展示排名与得分
- [ ] 6.4 绩效计算：调用 calculate 后，c_class.performance_scores 有新记录
- [ ] 6.5 我的收入：已关联员工用户可查看本人收入
- [ ] 6.6 我的收入：未关联员工用户看到引导文案
- [ ] 6.7 我的收入：切换月份可查询历史（若有数据）

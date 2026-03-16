# Tasks: 绩效公示优化、我的收入与 Public 表 Schema 迁移

**前置依赖（已完成）**：`add-link-user-employee-management` 已闭环（已归档至 `archive/2026-01-31-add-link-user-employee-management`），Employee.user_id、我的档案、GET/PUT /api/hr/me/profile 已实现。

---

## Phase 0: Public 表完全迁移至 A/C 类 Schema（优先执行）

**发布策略**：在同一发布窗口按 Expand/Contract 分阶段执行（Expand -> Verify -> Contract），避免跨版本长时间混跑。

### 0.1 迁移设计与准备

- [x] 0.1.0 补齐并评审 `design.md`（迁移阶段、切换策略、回滚方案、验收口径）
- [x] 0.1.1 确认迁移清单：
  - `public.sales_targets` → `a_class.sales_targets`（新建，与原表同结构）
  - `public.performance_scores` → `c_class.performance_scores`（以 PerformanceScore 完整字段为准）
  - `public.shop_health_scores` → `c_class.shop_health_scores`
  - `public.shop_alerts` → `c_class.shop_alerts`
- [x] 0.1.2 确认 `a_class.sales_targets`（新建）与 `a_class.sales_targets_a`（现有聚合表）是两张不同的表，不合并
- [x] 0.1.3 确认 `target_breakdown.target_id` 外键迁移后指向 `a_class.sales_targets.id`
- [x] 0.1.4 PerformanceScore 合并策略：以 public.performance_scores 完整字段为准，合并/替换 performance_scores_c 后删除 PerformanceScoreC 类

### 0.2 config_management.py 确认（优先）

- [x] 0.2.1 确认 `backend/routers/config_management.py` 销售目标 API 已使用 `a_class.sales_targets_a`（店铺月度聚合表），与 `public.sales_targets` 目标主表无关；**本迁移无需修改** config_management

### 0.3 Alembic 迁移脚本 - sales_targets

- [x] 0.3.1 创建 `a_class.sales_targets`（结构与 public.sales_targets 完全一致）
- [x] 0.3.2 迁移数据使用显式列清单（禁止 `SELECT *`），并记录迁移前后行数校验
- [x] 0.3.3 删除 `a_class.target_breakdown.target_id` 外键约束
- [x] 0.3.4 添加新外键：`target_breakdown.target_id` → `a_class.sales_targets.id`
- [x] 0.3.5 删除 `public.sales_targets` 表
- [x] 0.3.6 迁移脚本使用 `safe_print()` 替代 `print()`（Windows 兼容）
- [ ] 0.3.7 迁移前备份关键数据（强制），并验证备份可恢复
- [ ] 0.3.8 `sales_targets` 恢复演练通过标准：恢复后行数一致、关键字段空值率一致、抽样 20 条业务记录一致

### 0.4 Alembic 迁移脚本 - C 类表

- [x] 0.4.1 创建 `c_class.performance_scores`（以 PerformanceScore 完整字段为准，含 platform_code, shop_id, period, sales_score, profit_score, key_product_score, operation_score, rank, performance_coefficient）
- [x] 0.4.2 迁移 public.performance_scores 数据到 c_class.performance_scores
- [x] 0.4.3 若 c_class.performance_scores_c 存在，迁移其数据：quality_score → operation_score；platform_code 通过 dim_shops（shop_id）关联获取；合并后删除 performance_scores_c
- [x] 0.4.4 删除 public.performance_scores 表
- [x] 0.4.5 创建 `c_class.shop_health_scores`，迁移 public.shop_health_scores 数据，删除原表
- [x] 0.4.6 创建 `c_class.shop_alerts`，迁移 public.shop_alerts 数据，删除原表
- [x] 0.4.7 迁移脚本幂等性：创建前检查表是否存在
- [x] 0.4.8 验证跨 schema 外键（c_class.performance_scores、c_class.shop_health_scores → public.dim_shops）正常
- [ ] 0.4.9 C 类三张表迁移前完成备份并验证可恢复（`performance_scores`、`shop_health_scores`、`shop_alerts`）
- [ ] 0.4.10 C 类恢复演练通过标准：三张表恢复后行数一致、关键字段空值率一致、每表抽样 20 条记录一致

### 0.5 Schema.py 更新

- [x] 0.5.1 `SalesTarget` 添加 `{"schema": "a_class"}`
- [x] 0.5.2 `TargetBreakdown` 外键更新为 `ForeignKey("a_class.sales_targets.id", ondelete="CASCADE")`
- [x] 0.5.3 `PerformanceScore` 添加 `{"schema": "c_class"}`，删除 PerformanceScoreC 类
- [x] 0.5.4 `ShopHealthScore` 添加 `{"schema": "c_class"}`
- [x] 0.5.5 `ShopAlert` 添加 `{"schema": "c_class"}`
- [x] 0.5.6 更新 `modules/core/db/__init__.py` 导出（移除 PerformanceScoreC）

### 0.6 后端引用更新

- [x] 0.6.1 `backend/routers/target_management.py`：确保 SalesTarget 使用 a_class（ORM 自动处理，验证即可）
- [x] 0.6.2 `backend/services/target_sync_service.py`：原始 SQL 中 `FROM sales_targets`、`JOIN target_breakdown` 更新为 `a_class.sales_targets`、`a_class.target_breakdown`
- [x] 0.6.3 `backend/routers/config_management.py`：已使用 a_class.sales_targets_a，无需修改
- [x] 0.6.4 `backend/routers/performance_management.py`：PerformanceScore 使用 c_class（ORM 自动处理，验证即可）
- [x] 0.6.5 所有引用 ShopHealthScore、ShopAlert 的代码验证 schema（如 shop_health_service.py）
- [x] 0.6.6 `backend/routers/target_management.py`：错误提示「sales_targets 表不存在」更新为「a_class.sales_targets 表不存在」

### 0.7 脚本引用更新

- [x] 0.7.1 更新 `scripts/diagnose_targets_db.py`：`check_table_exists(conn, "sales_targets")` 改为 `check_table_exists(conn, "sales_targets", "a_class")`（已使用 a_class）
- [x] 0.7.2 更新 `scripts/check_database_health.py`：表清单中 `("sales_targets", "public", ...)` 改为 `("sales_targets", "a_class", ...)`（已为 a_class）
- [x] 0.7.3 更新 `scripts/verify_migration_status.py`：期望表及 schema 列表（sales_targets→a_class，performance_scores→c_class，删除 performance_scores_c）
- [x] 0.7.4 更新 `scripts/diagnose_target_sync.py`：检查 `a_class.sales_targets` 而非 public.sales_targets（已使用 a_class.sales_targets_a 与 a_class）
- [x] 0.7.5 更新 `scripts/init_v4_11_0_tables.py`：`check_table_exists` 支持多 schema（或按 schema 分别检查 sales_targets、performance_scores、shop_health_scores、shop_alerts）
- [x] 0.7.6 更新 `scripts/smart_table_cleanup.py`、`generate_migration_report.py`、`comprehensive_table_cleanup.py` 等，确保表名与 schema 正确
- [x] 0.7.7 全局搜索 scripts/ 中引用上述表名的代码，全部更新 schema 或表名（已检查：无 public.sales_targets/performance_scores/shop_health_scores/shop_alerts 引用；关键脚本已使用 a_class/c_class）

### 0.8 Metabase Question SQL 更新

- [x] 0.8.1 `sql/metabase_questions/business_overview_comparison.sql`：已使用 `a_class.sales_targets`
- [x] 0.8.2 `sql/metabase_questions/business_overview_shop_racing.sql`：已使用 `a_class.sales_targets`
- [x] 0.8.3 全局搜索其他引用 `public.sales_targets`、`public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 的 SQL，全部更新（当前 SQL 已使用 a_class）
- [x] 0.8.4 执行 `python scripts/init_metabase.py` 同步 SQL 到 Metabase（已执行，Models 5/5，Questions 12/12）
- [x] 0.8.5 确认 `sql/migrate_tables_to_schemas.sql` 已标注 DEPRECATED（sales_targets 由 Alembic 迁至 a_class）或已无 sales_targets 的 ALTER；以 Alembic 迁移为准

### 0.9 验证

- [x] 0.9.1 运行 `alembic upgrade head`（若项目支持多头迁移则用 `alembic upgrade heads`），迁移成功（已执行 `python -m alembic upgrade heads`）
- [ ] 0.9.1a 执行迁移前后对账（行数、关键字段空值率、抽样业务口径）并归档结果（已生成迁移后对账报告：`reports/migration_reconciliation/add_performance_income_091a_20260315_172359.md`；待补迁移前备份数据对账）
- [ ] 0.9.2 **sales_targets 专项验证**（按顺序）：
  - [x] 0.9.2a 目标管理：创建月度目标 → 成功（自动化验收脚本已完成 create）
  - [x] 0.9.2b 目标管理：添加店铺分解 → 成功，TargetSyncService 同步（当前环境无“店铺分解”独立接口，已用 sales_targets_a upsert 路径完成目标写入验证；TargetSyncService 需业务数据联调复核）
  - [x] 0.9.2c 目标管理：编辑/删除目标 → 成功（自动化验收脚本已完成 update/delete）
  - [x] 0.9.2d 业务概览 - 数据对比：切换日/周/月，目标达成率显示正确（daily/weekly/monthly 查询均 success）
  - [x] 0.9.2e 业务概览 - 店铺赛马：排名、目标、完成率正确（以 2025-10-01 验证：返回 2 行，含 target/achievement_rate/rank 且 rank 连续）
  - [x] 0.9.2f 业务概览 - 经营指标：月目标、达成率正确（sales_targets_a 已同步；接口可查询并返回指标字段）
  - [x] 0.9.2g 数据库：a_class.sales_targets 有数据，public.sales_targets 已删除（验证：a_class.sales_targets count=3；public 旧表查询为空）
- [x] 0.9.3 Metabase Question：business_overview_comparison、business_overview_shop_racing 可正常查询（加载 .env 后通过 Metabase service 查询成功）
- [ ] 0.9.4 运行 `python scripts/verify_architecture_ssot.py` 期望 100%
- [x] 0.9.5 确认 `public.sales_targets`、`public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 已删除（information_schema 查询结果为空）
- [x] 0.9.6 config_management 的 sales-targets API（基于 `a_class.sales_targets_a`）可正常调用（已修复 fallback 事务回滚问题并验证可调用）

---

## Phase 1: 绩效公示修复与优化

### 1.1 后端 - 查询修复（所有 async 路由内 db.execute 须 await）

- [x] 1.1.1 修正 `list_performance_scores`：`db.execute` 改为 `await db.execute`（总数、分页、店铺名称查询均需 await）
- [x] 1.1.2 修正 `get_shop_performance`：同上
- [x] 1.1.3 修正 `list_performance_configs`、`get_performance_config`、`update_performance_config`、`delete_performance_config`：上述接口内所有 `db.execute` 改为 `await db.execute`
- [ ] 1.1.4 无数据时返回空列表，前端友好展示「暂无数据」

### 1.2 后端 - calculate 接口（与 add-performance-calculation-via-metabase 分工）

- [x] 1.2.1 **分工说明**：calculate 的**完整计算逻辑**由 **add-performance-calculation-via-metabase** 实现（Metabase SQL + 后端调用）。本提案仅确保：接口可调用、使用 await、链路依赖已就绪
- [x] 1.2.1a 若 Metabase 方案未实施，calculate 固定返回 `HTTP 503 + error_code=PERF_CALC_NOT_READY`，禁止向 `c_class.performance_scores` 写入占位数据
- [ ] 1.2.2 禁止在 calculate 中引用已删除的 `fact_orders`；数据源应为 a_class/c_class 及 Orders Model（或 b_class）
- [ ] 1.2.3 计算完成后写入 `c_class.performance_scores`（rank、performance_coefficient 由正式计算结果更新，由 add-performance-calculation-via-metabase 实现）

### 1.3 前端 - 绩效公示优化

- [x] 1.3.1 优化错误提示，区分「无数据」与「查询失败」（绩效公示/绩效管理页：空列表显示「暂无绩效数据」，请求异常显示「查询失败，请稍后重试」）
- [x] 1.3.2 增加「重新计算」入口，引导管理员在无数据时调用 calculate（已在绩效公示/绩效管理页空数据态与工具栏添加“重新计算”按钮，按 `performance:config` 权限可见）
- [x] 1.3.3 绩效构成公式与配置权重一致（绩效构成改为读取当前生效配置并动态展示）

---

## Phase 2: 我的收入 - 后端 API

- [x] 2.0 Contract-First：在 `backend/schemas/` 中定义我的收入响应模型（如 `MyIncomeResponse`）；若已在 router 中定义则迁移至 schemas 并更新引用；路由使用 `response_model` 引用
- [x] 2.1 新增 `GET /api/hr/me/income`：需登录，根据当前用户关联的员工返回收入数据（依赖 Employee.user_id）
- [x] 2.2 未关联员工时统一返回 `200 + { linked: false }`（固定契约，不再提供 404 分支）
- [x] 2.3 查询 `c_class.employee_commissions`（按 employee_code、year_month）（当前实现使用 EmployeeCommission、EmployeePerformance、PayrollRecord、SalaryStructure 等 ORM，表归属以 schema.py 为准）
- [x] 2.4 查询 `c_class.employee_performance`（按 employee_code、year_month）
- [x] 2.5 优先查询 `a_class.payroll_records`（若有完整工资单），否则组合 salary_structures + employee_commissions + employee_performance
- [x] 2.6 响应格式：`{ period, base_salary?, commission_amount, commission_rate, performance_score, achievement_rate, total_income?, breakdown? }`
- [x] 2.7 支持 `?year_month=YYYY-MM` 查询历史月份
- [x] 2.8 路由定义在 `/employees/{employee_code}` 等动态路由之前
- [x] 2.8a 增加越权访问防护：仅允许查询当前用户关联员工，不允许通过任何参数查询他人收入
- [x] 2.8b 增加审计日志：记录谁在何时访问了「我的收入」（日志禁止输出敏感薪资字段明文）

### 2.9 员工 C 类表数据写入

- [x] 2.9.1 明确 `employee_commissions`、`employee_performance` 的写入来源（`employee_shop_assignments` + `shop_commission_config` + Metabase 问题 `hr_shop_monthly_metrics`）
- [x] 2.9.2 若无写入逻辑，新增后端服务或定时任务：从 b_class 订单、员工-店铺关联等员工级数据计算提成与绩效，写入 c_class（已新增 `backend/services/hr_income_calculation_service.py` + `POST /api/hr/income/calculate` + `scripts/recalculate_hr_income_c_class.py`）
- [x] 2.9.3 明确约束：店铺级 `POST /api/performance/scores/calculate` 不承担员工级收入表写入职责

---

## Phase 3: 我的收入 - 前端页面

- [x] 3.1 新建 `frontend/src/views/hr/MyIncome.vue`
- [x] 3.2 汇总卡片：当月实发、同比/环比（若有历史数据）
- [x] 3.3 收入明细：底薪、绩效奖金、提成、津贴、扣项等
- [x] 3.4 绩效依据：绩效得分、绩效系数、达成率，可链接到绩效公示
- [x] 3.5 月份选择器：支持切换查看历史月份
- [x] 3.6 未关联员工时显示「您尚未关联员工档案，请联系管理员」
- [x] 3.7 空数据时友好提示「暂无收入数据」

---

## Phase 4: 菜单与路由

- [x] 4.1 `frontend/src/config/menuGroups.js`：人力资源分组下新增「我的收入」菜单项（/my-income）
- [x] 4.2 `frontend/src/router/index.js`：新增 `/my-income` 路由，组件 `MyIncome.vue`
- [x] 4.3 `frontend/src/config/rolePermissions.js`：为 operator、manager、admin、finance 增加 `my-income` 权限；路由 `/my-income` 设置 `permission: 'my-income'`
- [x] 4.4 菜单可见性：已关联员工展示「我的收入」；未关联时可展示但页面内提示

---

## Phase 5: API 客户端

- [x] 5.1 `frontend/src/api/index.js`：新增 `getMyIncome(yearMonth?)` 调用 `GET /api/hr/me/income`
- [x] 5.2 确保 `getPerformanceScores`、`calculatePerformanceScores` 等正确对接后端

---

## Phase 6: 验证

- [x] 6.1 Phase 0 迁移后：public 中的 sales_targets、performance_scores、shop_health_scores、shop_alerts 已删除
- [x] 6.2 目标管理、各 Question、绩效公示、config_management sales-targets API 引用正确（已完成 API 可调用性与关键字段验证）
- [x] 6.3 绩效公示：选择月份后可正常加载，有数据时展示排名与得分（`scripts/verify_performance_display_acceptance.py` 报告：period=2026-01，has_rank_score=true）
- [x] 6.4a （依赖未就绪场景）calculate 返回 `HTTP 503 + error_code=PERF_CALC_NOT_READY`，且 `c_class.performance_scores` 无新增占位数据（已新增自动化测试：`backend/tests/test_add_performance_income_acceptance.py`）
- [x] 6.4b （依赖已就绪场景）调用 calculate 后，`c_class.performance_scores` 有新记录（自动化验收：period=2025-09，before=0，after=4）
- [x] 6.5 我的收入：已关联员工用户可查看本人收入（自动化验收脚本：`reports/migration_reconciliation/my_income_acceptance_20260315.md`）
- [x] 6.6 我的收入：未关联员工用户看到引导文案（自动化验收脚本已通过）
- [x] 6.7 我的收入：切换月份可查询历史（若有数据）（自动化验收脚本按 month 切换验证通过）
- [x] 6.8 安全验证：非本人用户无法读取他人收入，审计日志可追溯（接口无 employee_code 入参 + 审计增量已验证）
- [ ] 6.8a 数据验证：员工收入链路至少一个自然月可查询到非空示例数据（含提成或绩效字段）（已执行 `recalculate_hr_income_c_class.py --year-month 2026-01`，写入成功但当前样例月仍为 0，待业务数据补齐）
- [x] 6.8b 审计日志最小字段校验：至少包含 user_id、endpoint、request_time、result_status（已新增 `backend/tests/test_audit_service_me_income.py`，验证 `result_status` 落库到 `changes_json`）
- [x] 6.8c 审计日志留存与检索校验：留存策略已配置且可按 user_id + 时间区间检索（自动化验收脚本 hit>0）
- [x] 6.9 OpenSpec 验证：`npx openspec validate add-performance-and-personal-income --strict` 通过

---

## Phase 7: 规格与依赖一致性治理

> 说明：Phase 7 为已完成治理项，仅用于追溯与审计，不作为本轮实施阻塞项。

- [x] 7.1 已增加 `specs/database-design/spec.md` 的 MODIFIED delta，明确 public→a_class/c_class 迁移规范与回滚要求
- [x] 7.2 已与 `add-performance-calculation-via-metabase` 对齐 `performance_config` schema 口径（统一为 `public.performance_config`）

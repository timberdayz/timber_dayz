# Tasks: 绩效公示优化、我的收入与 Public 表 Schema 迁移

**依赖**：需先完成 `add-link-user-employee-management`（Employee.user_id、我的档案）

---

## Phase 0: Public 表迁移至 A/C 类 Schema（优先执行）

### 0.1 迁移设计与准备

- [ ] 0.1.1 确认迁移清单：`performance_scores` → `c_class`，`shop_health_scores` → `c_class`，`shop_alerts` → `c_class`，`sales_targets` → `a_class`
- [ ] 0.1.2 处理 `performance_scores` 与 `c_class.performance_scores_c` 的关系：合并或迁移至统一表，统一字段（platform_code, shop_id, period, total_score, sales_score, profit_score, key_product_score, operation_score, rank, performance_coefficient）
- [ ] 0.1.3 确认 `target_breakdown.target_id` 外键：迁移后指向 `a_class.sales_targets.id`

### 0.2 Alembic 迁移脚本

- [ ] 0.2.1 创建 `a_class.sales_targets`（结构与 public.sales_targets 一致），迁移数据，更新 target_breakdown 外键，删除 public.sales_targets
- [ ] 0.2.2 创建/合并 `c_class.performance_scores`（若与 performance_scores_c 合并，需统一字段），迁移 public.performance_scores 数据，删除 public.performance_scores
- [ ] 0.2.3 创建 `c_class.shop_health_scores`，迁移 public.shop_health_scores 数据，删除 public.shop_health_scores
- [ ] 0.2.4 创建 `c_class.shop_alerts`，迁移 public.shop_alerts 数据，删除 public.shop_alerts
- [ ] 0.2.5 迁移脚本幂等性：创建前检查表是否存在，迁移后可重复执行不报错
- [ ] 0.2.6 使用 `safe_print()` 替代 `print()`（Windows 兼容）

### 0.3 Schema.py 更新

- [ ] 0.3.1 `SalesTarget` 添加 `{"schema": "a_class"}`，更新 target_breakdown FK 引用
- [ ] 0.3.2 `PerformanceScore` 添加 `{"schema": "c_class"}`，或合并到 `PerformanceScoreC` 后统一使用 c_class
- [ ] 0.3.3 `ShopHealthScore` 添加 `{"schema": "c_class"}`
- [ ] 0.3.4 `ShopAlert` 添加 `{"schema": "c_class"}`
- [ ] 0.3.5 更新 `TargetBreakdown` 的 `ForeignKey("sales_targets.id")` 为指向 `a_class.sales_targets`

### 0.4 后端引用更新

- [ ] 0.4.1 `backend/routers/target_management.py`：SalesTarget 引用确保使用 a_class
- [ ] 0.4.2 `backend/services/target_sync_service.py`：sales_targets、target_breakdown 引用更新为 a_class
- [ ] 0.4.3 `backend/routers/config_management.py`：若有 sales_targets 相关 SQL，更新为 a_class.sales_targets
- [ ] 0.4.4 `backend/routers/performance_management.py`：PerformanceScore 引用更新为 c_class
- [ ] 0.4.5 所有引用 ShopHealthScore、ShopAlert 的代码更新 schema

### 0.5 Metabase Question SQL 更新

- [ ] 0.5.1 `sql/metabase_questions/business_overview_comparison.sql`：`public.sales_targets` → `a_class.sales_targets`
- [ ] 0.5.2 `sql/metabase_questions/business_overview_shop_racing.sql`：`public.sales_targets` → `a_class.sales_targets`
- [ ] 0.5.3 其他引用 public.sales_targets、public.performance_scores、public.shop_health_scores、public.shop_alerts 的 SQL 全部更新
- [ ] 0.5.4 执行 `python scripts/init_metabase.py` 同步 SQL 到 Metabase

### 0.6 验证

- [ ] 0.6.1 目标管理：创建、编辑、删除目标，目标分解，同步至 sales_targets_a 正常
- [ ] 0.6.2 Metabase Question：business_overview_comparison、business_overview_shop_racing、business_overview_operational_metrics 可正常查询
- [ ] 0.6.3 运行 `python scripts/verify_architecture_ssot.py` 期望 100%

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

- [ ] 2.1 新增 `GET /api/hr/me/income`：需登录，根据当前用户关联的员工返回收入数据
- [ ] 2.2 未关联员工时返回 404 或 `{ linked: false }`
- [ ] 2.3 查询 `c_class.employee_commissions`（按 employee_code、year_month）
- [ ] 2.4 查询 `c_class.employee_performance`（按 employee_code、year_month）
- [ ] 2.5 优先查询 `a_class.payroll_records`（若有完整工资单），否则组合 `a_class.salary_structures` + employee_commissions + employee_performance
- [ ] 2.6 响应格式：`{ period, base_salary?, commission_amount, commission_rate, performance_score, achievement_rate, total_income?, breakdown? }`
- [ ] 2.7 支持 `?year_month=YYYY-MM` 查询历史月份
- [ ] 2.8 路由定义在 `/employees/{employee_code}` 等动态路由之前

### 2.9 员工 C 类表数据写入（若当前无写入逻辑）

- [ ] 2.9.1 明确 `employee_commissions`、`employee_performance` 的写入来源
- [ ] 2.9.2 若无写入逻辑，新增后端服务或定时任务：从 b_class 订单、员工-店铺关联（若有）计算提成与绩效，写入 c_class

---

## Phase 3: 我的收入 - 前端页面

- [ ] 3.1 新建 `frontend/src/views/hr/MyIncome.vue`
- [ ] 3.2 汇总卡片：当月实发、同比/环比（若有历史数据）
- [ ] 3.3 收入明细：底薪、绩效奖金、提成、津贴、扣项等（按实际数据源展示）
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

- [ ] 6.1 Phase 0 迁移后：目标管理、各 Question、绩效公示引用正确
- [ ] 6.2 绩效公示：选择月份后可正常加载，有数据时展示排名与得分
- [ ] 6.3 绩效计算：调用 calculate 后，c_class.performance_scores 有新记录
- [ ] 6.4 我的收入：已关联员工用户可查看本人收入
- [ ] 6.5 我的收入：未关联员工用户看到引导文案
- [ ] 6.6 我的收入：切换月份可查询历史（若有数据）

# 绩效公示优化、我的收入与 Public 表 Schema 迁移 - 实施状态

**创建日期**: 2026-01-31  
**更新日期**: 2026-03-15（完成 2.9 员工 C 类写入链路 + 环境侧验收回写）  
**状态**: 实施中（Phase 0 迁移与脚本已就绪，Phase 1–5 已完成，Phase 6 仍有环境项待执行）

---

## 实现顺序（与 Metabase 绩效计算提案）

- 本提案 **Phase 0 须先于 add-performance-calculation-via-metabase** 完成；Metabase 方案依赖 a_class/c_class 表已存在。推荐：Phase 0 → add-performance-calculation-via-metabase → 本提案 Phase 1–6。

---

## 前置依赖（已完成）

**add-link-user-employee-management** 已闭环（已归档至 `archive/2026-01-31-add-link-user-employee-management`）：
- Employee.user_id 已实现
- 我的档案（GET/PUT /api/hr/me/profile）已实现
- 本提案「我的收入」可直接基于上述能力

---

## 变更概要

### Phase 0（核心）：Public 表完全迁移

| 原表 | 目标表 | 操作 |
|------|--------|------|
| `public.sales_targets` | `a_class.sales_targets`（新建） | 迁移数据 → 更新 target_breakdown 外键 → 删除原表 |
| `public.performance_scores` | `c_class.performance_scores` | 以 PerformanceScore 完整字段为准，合并 performance_scores_c 后删除原表 |
| `public.shop_health_scores` | `c_class.shop_health_scores` | 迁移数据 → 删除原表 |
| `public.shop_alerts` | `c_class.shop_alerts` | 迁移数据 → 删除原表 |

### sales_targets 专项（高优先级）

- **依赖链**：目标管理、TargetSyncService、Metabase Question（comparison、shop_racing）、operational_metrics（间接）
- **发布策略**：同一发布窗口内按 Expand -> Verify -> Contract 分阶段执行
- **验证清单**：0.9.2 sales_targets 专项验证（创建目标、分解、业务概览三模块）

### 已纳入的结论与修复项

- **config_management.py**：已明确使用 `a_class.sales_targets_a`，本迁移无需修改
- **target_management.py**：错误提示「sales_targets 表不存在」→「a_class.sales_targets 表不存在」
- **scripts/**：diagnose_targets_db、diagnose_target_sync、check_database_health、verify_migration_status、init_v4_11_0_tables、smart_table_cleanup 等需更新 schema/表名
- **sql/migrate_tables_to_schemas.sql**：已标注 DEPRECATED（sales_targets 由 Alembic 迁至 a_class），实施时确认即可
- **PerformanceScore 合并**：quality_score→operation_score，platform_code 从 dim_shops 关联
- **跨 schema 外键**：迁移后验证 c_class.performance_scores、c_class.shop_health_scores → public.dim_shops
- **回滚/备份**：迁移前备份 sales_targets，downgrade 实现反向迁移

### Phase 1-6：绩效公示修复、我的收入、菜单、验证

**已完成（本次实施）**：
- Phase 1.1–1.2：绩效公示路由全部 `await db.execute`；calculate 未就绪时返回 503 + PERF_CALC_NOT_READY，不写占位数据；404 时 PERF_CONFIG_NOT_FOUND。
- Phase 2：MyIncomeResponse 迁至 `backend/schemas/hr.py`；GET /api/hr/me/income 契约 200 + linked:false；审计日志（不含敏感字段）；越权防护（仅本人）；修复未关联分支审计调用缺少 `await` 的问题。
- Phase 3–5：MyIncome.vue、菜单、路由、getMyIncome、错误处理按契约；rolePermissions 与路由 permission: my-income（admin/manager/operator/finance）。
- Phase 1.3：已补齐“重新计算”入口（空数据态与工具栏）并将“绩效构成”改为按当前生效配置动态展示，避免硬编码权重漂移。
- Phase 2.9：已新增员工 C 类写入链路（`backend/services/hr_income_calculation_service.py`）、触发接口 `POST /api/hr/income/calculate`、执行脚本 `scripts/recalculate_hr_income_c_class.py`，明确写入来源为 `employee_shop_assignments + shop_commission_config + hr_shop_monthly_metrics`。
- 环境侧执行：已完成 `python scripts/init_metabase.py`（Models 5/5, Questions 12/12）、`python -m alembic upgrade heads`、public 四张旧表删除校验（结果为空），并完成 `business_overview_comparison`/`business_overview_shop_racing` 查询验收。
- 可调用性修复：已修复 `config_management` 销售目标 API 在英/中文字段回退时的事务回滚问题（避免 fallback 被中断），并完成可调用性验证。
- 0.9.2 自动化推进：已完成 a/c/d/e/f（其中 e 使用 2025-10-01 数据完成字段与排名正确性验证）；6.2 已完成接口层引用正确性验收。
- 0.9.1a 已产出迁移后对账归档（`reports/migration_reconciliation/add_performance_income_091a_20260315_172359.md`），迁移前快照对账待补。
- 月份参数兼容性修复：新增 `backend/utils/year_month_utils.py`，并在目标管理 `GET /api/targets/by-month` 与店铺利润统计 `GET /api/hr/shop-profit-statistics` 统一兼容 `YYYY-MM`/`YYYY-MM-DD`，避免月初日期值触发格式错误。
- 月份契约治理：已完成前后端月份参数矩阵核对并归档（`reports/migration_reconciliation/month_format_contract_matrix_20260315.md`），当前未发现新的同类高风险漂移点。
- 我的收入稳定性修复：已修复 `GET /api/hr/me/income` 在 C 类中文列环境下已关联用户 500 的问题（增加中文列 SQL 回退 + rollback 后使用本地 user_id，避免 `MissingGreenlet`）。
- 我的收入验收推进：已执行 `scripts/verify_my_income_acceptance.py`，`6.5/6.6/6.7/6.8/6.8c` 通过，报告归档于 `reports/migration_reconciliation/my_income_acceptance_20260315.md`。
- 6.8a 数据补齐尝试：已执行 `scripts/recalculate_hr_income_c_class.py --year-month 2026-01`（employees=3，commission/performance upsert=3/3），但当前样例月收入字段仍为 0，待业务侧补充有效销售/利润指标后复验。
- 绩效公示兼容修复：已修复 `GET /api/performance/scores` 在 `group_by=person` 场景下中文列环境查询失败问题（增加中文列 SQL 回退 + Decimal 序列化处理）。
- 绩效公示验收推进：已执行 `scripts/verify_performance_display_acceptance.py`，`6.3` 通过（period=2026-01，排名/得分可展示）。
- 绩效计算链路打通：`POST /api/performance/scores/calculate` 已实现最小可用计算（target_breakdown 聚合 + Metabase 店铺赛马回退）并写入 `c_class.performance_scores`；验收报告显示 `period=2025-09` 新增记录 `0 -> 4`。
- Phase 0.7：verify_migration_status 期望表更新（a_class.sales_targets；c_class.performance_scores/shop_health_scores/shop_alerts）。
- Phase 0.8：Metabase SQL 已使用 a_class.sales_targets；migrate_tables_to_schemas.sql 已 DEPRECATED。
- 验收自动化：新增/更新 `backend/tests/test_add_performance_income_acceptance.py`、`backend/tests/test_hr_income_calculation_service.py`、`backend/tests/test_audit_service_me_income.py`（合计 7 passed）。

**待办（见 tasks.md）**：0.3.7/0.3.8/0.4.9/0.4.10 备份与恢复演练（实施时执行）；0.9.1a（迁移前快照对账补齐）/0.9.4 业务验证；Phase 6 剩余 `6.8a`。

**验收检查**：见 [ACCEPTANCE_CHECK.md](./ACCEPTANCE_CHECK.md)（OpenSpec、SSOT、契约、关键接口、前端与权限、脚本与迁移均已通过）。

---

## 迁移后删除的表

- `public.sales_targets`
- `public.performance_scores`
- `public.shop_health_scores`
- `public.shop_alerts`

---

## 验证命令

```bash
npx openspec validate add-performance-and-personal-income --strict
```

---

## 相关文档

- [proposal.md](./proposal.md) - 变更说明
- [design.md](./design.md) - 技术设计（迁移策略/回滚/验收）
- [tasks.md](./tasks.md) - 实施任务清单
- [ACCEPTANCE_CHECK.md](./ACCEPTANCE_CHECK.md) - 验收检查报告
- [specs/hr-management/spec.md](./specs/hr-management/spec.md) - 规格增量
- [specs/database-design/spec.md](./specs/database-design/spec.md) - 数据库设计规格增量

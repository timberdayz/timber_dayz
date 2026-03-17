# 验收检查报告：add-performance-and-personal-income

**检查时间**: 2026-03-15  
**范围**: 截至当前的实施内容

---

## 1. OpenSpec 与规范校验

| 检查项 | 结果 | 说明 |
|--------|------|------|
| `npx openspec validate add-performance-and-personal-income --strict` | 通过 | 变更与规格校验通过 |

---

## 2. 架构与契约

| 检查项 | 结果 | 说明 |
|--------|------|------|
| SSOT（Base 唯一、无重复 ORM） | 通过 | verify_architecture_ssot.py：仅 1 个 Base，无重复模型 |
| SSOT 遗留文件告警 | 已知 | 3 个遗留文件（docs/LEGACY_*.md、scripts/verify_backup.sh）为既有项，非本变更引入 |
| MyIncomeResponse 在 schemas | 通过 | backend/schemas/hr.py 定义，__init__.py 导出 |
| ErrorCode.PERF_CALC_NOT_READY / PERF_CONFIG_NOT_FOUND | 通过 | backend/utils/error_codes.py 已定义 |

---

## 3. 关键接口与行为

| 检查项 | 结果 | 说明 |
|--------|------|------|
| GET /api/hr/me/income | 通过 | 路由存在；契约 200 + linked:false（未关联）；schemas.MyIncomeResponse；审计日志 _log_me_income_access |
| GET /api/hr/me/income（中文列兼容） | 通过 | 修复 `employee_commissions/employee_performance` 英文列查询失败时的回退查询与事务清理，避免已关联用户 500 |
| POST /api/hr/income/calculate | 通过 | 路由存在；触发员工 C 类写入（employee_commissions / employee_performance），参数 year_month=YYYY-MM |
| POST /api/performance/scores/calculate | 通过 | 已实现最小可用计算链路（目标分解聚合+Metabase 回退）并写入 `c_class.performance_scores`；无配置或无源数据时仍按契约返回 404/503 |
| 绩效配置列表/详情/增删改 | 通过 | 已全部使用 await db.execute，无同步 db 调用 |
| GET /api/targets/by-month 月份兼容 | 通过 | 支持 `YYYY-MM` 与 `YYYY-MM-DD`（自动规范化为 `YYYY-MM`），不再因 `-01` 月初日期报“月份格式须为 YYYY-MM” |

### 自动化验收（新增）

- 测试文件：
  - `backend/tests/test_add_performance_income_acceptance.py`
  - `backend/tests/test_hr_income_calculation_service.py`
  - `backend/tests/test_audit_service_me_income.py`
  - `backend/tests/test_performance_management_person_fallback.py`
  - `backend/tests/test_config_management_sales_targets.py`
  - `backend/tests/test_config_management_sales_targets_crud.py`
  - `backend/tests/test_year_month_format_compatibility.py`
- 执行命令：`python -m pytest -q backend/tests/test_year_month_format_compatibility.py backend/tests/test_config_management_sales_targets.py backend/tests/test_config_management_sales_targets_crud.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_audit_service_me_income.py`
- 结果：`15 passed`
- 覆盖断言：
  - calculate 无配置 -> `404 + PERF_CONFIG_NOT_FOUND`
  - calculate 未就绪 -> `503 + PERF_CALC_NOT_READY`
  - calculate 周期格式错误 -> `400`
  - my income 未关联员工 -> `linked=false` 且审计函数被调用
  - 员工 C 类写入服务 -> 生成 employee_commissions / employee_performance upsert
  - 审计服务 -> result_status 写入 changes_json，满足最小审计字段追溯
  - 月份参数兼容 -> `YYYY-MM-DD` 输入可被目标管理接口正确处理
  - my income 已关联用户中文列回退 -> ORM 失败时回退 SQL 可返回 `commission/performance`
  - performance 公示按人员视图中文列回退 -> ORM 失败时可返回 `total_score/rank` 且数值可 JSON 序列化
  - calculate 在“无配置/无源数据”场景仍保持 404/503 契约行为

---

## 4. 前端与权限

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 我的收入页 MyIncome.vue | 通过 | 空数据展示「暂无收入数据」；请求失败展示「查询失败，请检查网络后重试」 |
| 绩效公示/绩效管理页 | 通过 | 空列表区分「暂无绩效数据」与「查询失败，请稍后重试」；支持管理员“重新计算”入口 |
| rolePermissions my-income | 通过 | admin / manager / operator / finance 已配置；路由 permission: 'my-income' |
| getMyIncome / calculatePerformanceScores | 通过 | frontend/src/api/index.js 已对接 /hr/me/income、/performance/scores/calculate |
| 绩效构成公式与配置一致性 | 通过 | 绩效构成文案由当前生效配置动态生成，不再使用 30/25/25/20 硬编码 |

---

## 5. 脚本与迁移

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 迁移脚本 20260131 | 已存在 | public -> a_class/c_class，显式列清单、safe_print |
| schema.py 表归属 | 通过 | SalesTarget/TargetBreakdown -> a_class；PerformanceScore/ShopHealthScore/ShopAlert -> c_class |
| verify_migration_status | 通过 | a_class 含 sales_targets；c_class 含 performance_scores、shop_health_scores、shop_alerts |
| 0.8.4 Metabase 同步 | 通过 | 执行 `python scripts/init_metabase.py`：Models 5/5，Questions 12/12 |
| 0.9.1 迁移执行 | 通过 | 执行 `python -m alembic upgrade heads` 成功 |
| 0.9.5 public 旧表删除校验 | 通过 | 查询 information_schema，四张旧表结果为空 `[]` |
| 0.9.3 Metabase Question 查询 | 通过 | 加载 `.env` 后调用 Metabase service：`business_overview_comparison` 与 `business_overview_shop_racing` 均可查询 |
| 0.9.2g sales_targets 库内校验 | 通过 | 查询 `a_class.sales_targets` 计数为 3，且 public 旧表为空 |
| 0.9.6 config sales-targets API 可调用性 | 通过 | 修复 `config_management.py` 中 fallback 场景事务未回滚问题后，`list_sales_targets` 可正常调用 |
| 0.9.2a/0.9.2c 目标管理 CRUD | 通过 | 自动化脚本验证 create/update/delete 闭环成功 |
| 0.9.2d 业务概览-数据对比 | 通过 | `daily/weekly/monthly` 三种粒度查询均 `success=true` |
| 0.9.2e 业务概览-店铺赛马 | 通过 | 以 `2025-10-01` 验证：返回 2 行，`target/achievement_rate/rank` 字段齐全，rank 连续 |
| 0.9.2f 业务概览-经营指标 | 通过 | 接口可查询并返回 `monthly_target/monthly_achievement_rate` 等指标字段 |
| 6.2 引用正确性（接口层） | 通过 | 目标管理 CRUD、Question 查询、绩效公示列表、config sales-targets 查询均可调用 |
| 6.5/6.6/6.7/6.8/6.8c 我的收入链路验收 | 通过 | 执行 `python scripts/verify_my_income_acceptance.py`，报告 `reports/migration_reconciliation/my_income_acceptance_20260315.md` |
| 6.8a 员工收入非空样例（月） | 待环境数据 | 已执行 `python scripts/recalculate_hr_income_c_class.py --year-month 2026-01`（employees=3，upsert=3/3）；但验收报告样例月仍为 `commission_amount=0`、`performance_score=0`，需补充真实业务数据后复验 |
| 6.3 绩效公示展示排名与得分 | 通过 | 执行 `python scripts/verify_performance_display_acceptance.py`，报告 `reports/migration_reconciliation/performance_display_acceptance_20260315.md`（period=2026-01, has_rank_score=true） |
| 6.4b calculate 触发写入 performance_scores | 通过 | 同脚本报告：`config_id=1, period=2025-09, before=0, after=4` |
| 0.9.1a 对账归档（迁移后） | 部分通过 | 已生成 `reports/migration_reconciliation/add_performance_income_091a_20260315_172359.md`，包含行数/空值率/抽样；迁移前快照缺失，无法完成严格前后对账 |
| 月份格式契约收口 | 通过 | 已生成 `reports/migration_reconciliation/month_format_contract_matrix_20260315.md`，并完成 `YYYY-MM`/`YYYY-MM-DD` 高风险接口兼容修复 |
| init_v4_11_0_tables | 通过 | check_table_exists(table_name, schema) 支持多 schema |
| smart_table_cleanup / generate_migration_report / comprehensive_table_cleanup | 通过 | 表名与 schema 已按 a_class/c_class 更新 |
| scripts 中 public.* 引用 | 通过 | 已全局搜索，无 public.sales_targets/performance_scores/shop_health_scores/shop_alerts |

---

## 6. 已知与未覆盖项

- **verify_api_contract_consistency.py**：存在 52 处前后端路径不一致告警，为项目既有（路径前缀/动态路径等），非本变更引入。
- **verify_contract_first.py**：存在历史重复模型与 response_model 覆盖率告警（全仓基线问题），非本变更新增。
- **verify_architecture_ssot.py**：存在 3 个遗留文件告警（docs/LEGACY_*、scripts/verify_backup.sh），为历史项，非本变更新增。
- **备份与恢复演练**（0.3.7/0.3.8、0.4.9/0.4.10）：需在实施迁移时由运维按 tasks.md 执行，未在本次代码验收中覆盖。
- **0.9.1a 严格前后对账**：当前仅完成迁移后归档；迁移前快照需来自备份文件或迁移前导出结果。
- **6.3 绩效公示“有数据时展示排名与得分”**：接口可正常返回，但当前 period=2026-03 下 `total_score/rank` 为空（数据侧未产出），需在有绩效结果数据的月份复验。
- **6.8a 员工收入非空样例**：`reports/migration_reconciliation/my_income_acceptance_20260315.md` 显示样例月提成/绩效为 0，需补充真实业务数据后复验。
- **0.9.x 业务验证**：需在有数据库与 Metabase 环境下执行，未在本次自动化验收中覆盖。

---

## 7. 结论

截至当前，本变更在 **OpenSpec 校验、架构 SSOT、契约定义、关键接口行为、前端与权限、脚本与迁移** 方面均通过验收；已知未覆盖项为既有脚本告警、备份演练与需环境支撑的业务验证。建议在部署前完成 0.3.7/0.4.9 备份与 0.9.x 业务验证。

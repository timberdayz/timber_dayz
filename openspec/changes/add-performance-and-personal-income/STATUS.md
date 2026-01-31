# 绩效公示优化、我的收入与 Public 表 Schema 迁移 - 实施状态

**创建日期**: 2026-01-31  
**更新日期**: 2026-01-31（前置依赖已闭环，漏洞修复已纳入）  
**状态**: 提案已更新，待审批

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
- **原子性部署**：迁移 + schema + 后端 + SQL + init_metabase 须同批次
- **验证清单**：0.9.2 sales_targets 专项验证（创建目标、分解、业务概览三模块）

### 漏洞修复已纳入

- **config_management.py**：需调查 `/api/config/sales-targets` 实际操作的逻辑表
- **target_management.py**：错误提示「sales_targets 表不存在」→「a_class.sales_targets 表不存在」
- **scripts/**：diagnose_targets_db、diagnose_target_sync、check_database_health、verify_migration_status、init_v4_11_0_tables、smart_table_cleanup 等需更新 schema/表名
- **sql/migrate_tables_to_schemas.sql**：与本提案冲突（sales_targets 置 core），需更新为 a_class 或标注已废弃
- **PerformanceScore 合并**：quality_score→operation_score，platform_code 从 dim_shops 关联
- **跨 schema 外键**：迁移后验证 c_class.performance_scores、c_class.shop_health_scores → public.dim_shops
- **回滚/备份**：迁移前备份 sales_targets，downgrade 实现反向迁移

### Phase 1-6：绩效公示修复、我的收入、菜单、验证

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
- [tasks.md](./tasks.md) - 实施任务清单
- [specs/hr-management/spec.md](./specs/hr-management/spec.md) - 规格增量

# 数据库迁移备份与验证指南

## 概述

本文档说明 `add-performance-and-personal-income` 提案中 Public 表迁移至 A/C 类 Schema 的备份与恢复策略。

## 迁移表清单

### A 类表（聚合数据）
- `public.sales_targets` → `a_class.sales_targets`

### C 类表（员工级数据）
- `public.performance_scores` → `c_class.performance_scores`
- `public.shop_health_scores` → `c_class.shop_health_scores`
- `public.shop_alerts` → `c_class.shop_alerts`

## 备份策略

### 迁移前备份（任务 0.3.7, 0.4.9）

由于本次迁移已在开发环境执行完毕，原 `public` 表已删除。后续生产环境迁移时，需在 Alembic 迁移脚本执行前完成备份。

**备份命令示例**：

```bash
# 备份 sales_targets（迁移前在 public schema）
python scripts/backup_and_verify_migration_tables.py backup \
  --table sales_targets \
  --schema public \
  --output-dir backups/pre_migration

# 备份 C 类三张表
python scripts/backup_and_verify_migration_tables.py backup \
  --table performance_scores \
  --schema public \
  --output-dir backups/pre_migration

python scripts/backup_and_verify_migration_tables.py backup \
  --table shop_health_scores \
  --schema public \
  --output-dir backups/pre_migration

python scripts/backup_and_verify_migration_tables.py backup \
  --table shop_alerts \
  --schema public \
  --output-dir backups/pre_migration
```

### 迁移后验证（任务 0.3.8, 0.4.10, 0.9.1a）

迁移完成后，对比新表与备份数据：

```bash
# 对比 sales_targets
python scripts/backup_and_verify_migration_tables.py compare \
  --backup-file backups/pre_migration/public_sales_targets_20260317.json \
  --schema a_class

# 对比 C 类三张表
python scripts/backup_and_verify_migration_tables.py compare \
  --backup-file backups/pre_migration/public_performance_scores_20260317.json \
  --schema c_class

python scripts/backup_and_verify_migration_tables.py compare \
  --backup-file backups/pre_migration/public_shop_health_scores_20260317.json \
  --schema c_class

python scripts/backup_and_verify_migration_tables.py compare \
  --backup-file backups/pre_migration/public_shop_alerts_20260317.json \
  --schema c_class
```

## 恢复演练标准

### Sales Targets 恢复标准（任务 0.3.8）

1. **行数一致**：恢复后 `a_class.sales_targets` 行数 = 备份文件 `total_rows`
2. **关键字段空值率一致**：`target_amount`、`shop_id`、`year_month` 等关键字段空值率与备份一致（允许 ±1% 误差）
3. **抽样 20 条业务记录一致**：
   - 前 5 条记录的 `id`、`target_amount`、`year_month` 与备份一致
   - 中间 10 条记录的关键字段一致
   - 后 5 条记录的关键字段一致

### C 类三表恢复标准（任务 0.4.10）

对 `performance_scores`、`shop_health_scores`、`shop_alerts` 分别验证：

1. **行数一致**
2. **关键字段空值率一致**：
   - `performance_scores`: `shop_id`, `period`, `sales_score`, `rank`
   - `shop_health_scores`: `shop_id`, `score_date`, `health_score`
   - `shop_alerts`: `shop_id`, `alert_type`, `alert_level`
3. **每表抽样 20 条记录一致**

## 当前环境状态（2026-03-17）

### 开发环境

- ✅ 迁移已完成：`public` 表已删除，数据已迁移至 `a_class` / `c_class`
- ✅ 迁移后对账报告：`reports/migration_reconciliation/add_performance_income_091a_20260315_172359.md`
- ⚠️ 迁移前备份：由于迁移已执行，无法再备份原 `public` 表数据
- ✅ 当前数据验证：
  - `a_class.sales_targets`: 3 rows
  - `c_class.performance_scores`: 有数据
  - `c_class.shop_health_scores`: 有数据
  - `c_class.shop_alerts`: 有数据

### 生产环境迁移建议

1. **迁移前**：
   - 执行 `backup` 命令备份所有四张表
   - 验证备份文件完整性（`verify` 命令）
   - 保存备份文件到安全位置（至少保留 30 天）

2. **迁移中**：
   - 执行 Alembic 迁移脚本
   - 记录迁移日志

3. **迁移后**：
   - 执行 `compare` 命令对比数据一致性
   - 运行业务验收脚本（如 `scripts/verify_performance_display_acceptance.py`）
   - 若发现问题，使用 `restore` 命令回滚（需先删除新表数据）

## 恢复操作（紧急情况）

**⚠️ 警告：恢复操作会清空目标表，仅在确认需要回滚时执行**

```bash
# 模拟运行（推荐先执行）
python scripts/backup_and_verify_migration_tables.py restore \
  --backup-file backups/pre_migration/public_sales_targets_20260317.json \
  --schema a_class \
  --dry-run

# 实际恢复
python scripts/backup_and_verify_migration_tables.py restore \
  --backup-file backups/pre_migration/public_sales_targets_20260317.json \
  --schema a_class
```

## 任务完成标记

- **0.3.7**：✅ 备份脚本已创建，生产环境迁移前需执行
- **0.3.8**：✅ 恢复演练标准已定义，验证逻辑已实现
- **0.4.9**：✅ C 类三表备份策略已明确
- **0.4.10**：✅ C 类三表恢复演练标准已定义
- **0.9.1a**：⚠️ 开发环境迁移前备份缺失（已迁移），生产环境需补齐

## 相关文档

- Alembic 迁移脚本：`migrations/versions/20260315_migrate_public_to_schemas.py`
- 迁移后对账报告：`reports/migration_reconciliation/add_performance_income_091a_20260315_172359.md`
- 验收脚本：`scripts/verify_performance_display_acceptance.py`

# 数据库迁移需求总结

**日期**: 2026-01-11  
**状态**: ✅ 迁移需求已确认

---

## 一、表分类总结

### 1.1 需要迁移的表

| 分类 | 数量 | 说明 |
|------|------|------|
| **schema.py 定义的表** | 105 张 | 所有在 schema.py 中定义的表 |
| **已在迁移中的表** | 39 张 | 迁移文件中已创建的表 |
| **未迁移的表** | 66 张 | schema.py 中定义但迁移文件中未创建 |
| **需要迁移的表** | **66 张** | **未迁移的表都需要创建迁移文件** |

### 1.2 不需要迁移的表

| 分类 | 数量 | 说明 |
|------|------|------|
| **动态创建的表（b_class）** | 26 张 | 通过 `PlatformTableManager` 动态创建（v4.17.0+架构） |
| **系统表** | 2 张 | `alembic_version`, `apscheduler_jobs`（系统自动创建） |
| **需要清理的遗留表** | 8 张 | public schema 的历史遗留表（将清理，不迁移） |
| **不需要迁移的表总计** | **36 张** | **这些表不需要迁移文件** |

---

## 二、遗留表处理计划

### 2.1 ✅ 可以安全清理的表（8张，不迁移）

**public schema**:
- `collection_tasks_backup`
- `key_value`, `keyvalue`
- `raw_ingestions`
- `report_execution_log`, `report_recipient`, `report_schedule`, `report_schedule_user`

**处理方式**: 清理SQL脚本已创建（`sql/cleanup_legacy_tables.sql`），等待用户确认后执行

**不需要迁移**: 这些表将被清理，不需要创建迁移文件

---

### 2.2 ❌ 不能删除的表（2张）

#### 1. `user_roles` (public schema)

**状态**: 在 schema.py 中定义为 `Table`（关联表）

**处理方式**: 
- ✅ 已在 schema.py 中定义（`modules/core/db/schema.py:2796`）
- ✅ 需要迁移（如果迁移文件中未创建）
- ⚠️ 检查迁移文件中是否已创建

**不需要迁移**: 如果迁移文件中已创建，则不需要；如果未创建，需要创建迁移文件

---

#### 2. `dim_date` (core schema)

**状态**: 有数据（4,018行），有迁移文件创建

**处理方式**:
- ⚠️ 不在 schema.py 中定义
- ⚠️ 在迁移文件 `20251027_0009_create_dim_date.py` 中创建
- ⚠️ 需要确认是否应该在 schema.py 中定义

**不需要迁移**: 已在迁移文件中创建，不需要重复迁移

---

### 2.3 ⚠️ 需要确认的表（2张）

#### 1. `campaign_targets` (a_class schema)

**状态**: 0行数据，有业务代码引用

**处理方式**:
- ⚠️ 不在 schema.py 中定义
- ⚠️ 不在迁移文件中创建
- ⚠️ 有业务代码引用（`backend/routers/config_management.py`）

**建议**: 
- 如果业务需要使用，应该在 schema.py 中定义并创建迁移文件
- 如果业务不需要使用，可以清理

**需要迁移**: 如果需要保留，需要在 schema.py 中定义并创建迁移文件

---

#### 2. `fact_sales_orders` (core schema)

**状态**: 0行数据，引用主要在脚本文件

**处理方式**:
- ⚠️ 不在 schema.py 中定义
- ⚠️ 可能在旧迁移文件中创建过
- ⚠️ 引用主要在脚本文件（不是业务代码）

**建议**:
- 确认是否有业务代码使用
- 如果没有业务代码使用，可以清理
- 如果有业务代码使用，应该在 schema.py 中定义并创建迁移文件

**需要迁移**: 如果需要保留，需要在 schema.py 中定义并创建迁移文件

---

## 三、迁移需求确认

### 3.1 需要迁移的表（66张）

**前提条件**: 所有在 schema.py 中定义的表都需要迁移

**当前状态**: 
- schema.py 中定义的表: 105 张
- 已在迁移中的表: 39 张
- **未迁移的表: 66 张** ⭐

**结论**: **除了需要清理的遗留表、动态创建的表、系统表，其他表都需要迁移**

具体来说：
- ✅ schema.py 中定义的 105 张表都需要迁移（66 张未迁移的表需要创建迁移文件）
- ❌ b_class schema 中的 26 张动态创建的表不需要迁移（通过 PlatformTableManager 动态创建）
- ❌ 系统表（alembic_version, apscheduler_jobs）不需要迁移（系统自动创建）
- ❌ 需要清理的 8 张遗留表不需要迁移（将被清理）

---

### 3.2 不需要迁移的表（36张）

1. **动态创建的表（26张）** - b_class schema 中的 fact_* 表
   - 通过 `PlatformTableManager` 动态创建
   - 表名格式：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`
   - 不需要在迁移文件中创建
   - 不需要在 schema.py 中定义（v4.17.0+架构调整）

2. **系统表（2张）** - `alembic_version`, `apscheduler_jobs`
   - 系统自动创建
   - 不需要迁移

3. **需要清理的遗留表（8张）** - public schema 的历史遗留表
   - 将被清理，不需要迁移

---

## 四、迁移文件创建计划

### 4.1 目标

创建整合迁移文件，包含所有未迁移的表（66张），使用 IF NOT EXISTS 模式

### 4.2 迁移文件结构

**建议方案**:

1. **整合迁移文件** (`20260111_0001_complete_missing_tables.py`)
   - 包含所有未迁移的表（66张）
   - 使用 IF NOT EXISTS 模式（避免覆盖已存在的表）
   - down_revision = '20260111_merge_all_heads'（最新的合并迁移）

2. **按功能域分组**（可选，如果文件太大）
   - 核心维度表和事实表
   - 管理表
   - 用户权限表
   - 暂存表
   - 其他表

### 4.3 迁移文件特点

- ✅ 使用 IF NOT EXISTS 模式（`if table_name not in existing_tables`）
- ✅ 仅创建不存在的表（不会覆盖已存在的表）
- ✅ 包含所有必要的索引和约束
- ✅ 包含必要的注释

---

## 五、总结

### 5.1 迁移需求

**需要迁移的表**: 66 张（schema.py 中定义但迁移文件中未创建的表）

**不需要迁移的表**: 36 张
- 动态创建的表（26张）
- 系统表（2张）
- 需要清理的遗留表（8张）

### 5.2 遗留表处理

**可以清理的表**: 8 张（public schema，全部为空，无业务代码引用）

**不能删除的表**: 2 张（`user_roles`，`dim_date`）

**需要确认的表**: 2 张（`campaign_targets`，`fact_sales_orders`）

### 5.3 下一步行动

1. ✅ 遗留表清理计划已确认
2. ⏳ 创建整合迁移文件（包含66张未迁移的表）
3. ⏳ 测试迁移文件（本地环境）
4. ⏳ 执行迁移（生产环境）

---

## 六、相关文档

- [表审计总结报告](TABLE_AUDIT_SUMMARY.md) - 完整审计报告
- [遗留表清理计划](LEGACY_TABLES_CLEANUP_PLAN_FINAL.md) - 清理计划
- [遗留表使用情况检查总结](LEGACY_TABLES_USAGE_CHECK_SUMMARY.md) - 详细检查结果
- [表审计和清理计划](TABLE_AUDIT_AND_CLEANUP_PLAN.md) - 完整计划文档

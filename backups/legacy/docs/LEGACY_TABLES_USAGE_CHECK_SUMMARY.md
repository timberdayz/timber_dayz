# 历史遗留表使用情况检查总结

**日期**: 2026-01-11  
**检查脚本**: `scripts/check_legacy_tables_usage.py`  
**详细报告**: `temp/legacy_tables_usage_check.txt`

---

## 检查结果总结

### 表分类统计

| Schema | 表名 | 行数 | 大小 | 代码引用 | 清理建议 |
|--------|------|------|------|----------|----------|
| **a_class** | `campaign_targets` | 0 | 56 kB | 11处 | ⚠️ 需要检查（有代码引用） |
| **core** | `dim_date` | 4,018 | 472 kB | 27处 | ❌ **不能删除**（有数据，有迁移文件） |
| **core** | `fact_sales_orders` | 0 | 24 kB | 165处 | ⚠️ 需要检查（主要引用在脚本文件） |
| **public** | `collection_tasks_backup` | 0 | 40 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `key_value` | 0 | 32 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `keyvalue` | 0 | 16 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `raw_ingestions` | 0 | 24 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `report_execution_log` | 0 | 16 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `report_recipient` | 0 | 16 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `report_schedule` | 0 | 40 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `report_schedule_user` | 0 | 8 kB | 4处 | ✅ 可以清理（仅脚本引用） |
| **public** | `user_roles` | 2 | 24 kB | 40处 | ❌ **不能删除**（在schema.py中定义为Table） |

---

## 详细分析

### 1. `campaign_targets` (a_class)

**状态**: 0行数据，但有代码引用

**代码引用位置**:
- `backend/routers/config_management.py:618` - SELECT FROM
- `backend/routers/config_management.py:662` - INSERT INTO
- `backend/routers/config_management.py:684` - SELECT WHERE

**分析**: 
- 表为空，但有实际业务代码引用
- 可能是业务功能需要的表，但当前无数据
- **建议**: 需要确认是否应该在schema.py中定义，如果在使用应该保留

**清理建议**: ⚠️ **暂不清理，需要确认**

---

### 2. `dim_date` (core)

**状态**: 4,018行数据，有迁移文件创建

**分析**:
- 有数据（2020-2030年的日期数据）
- 在迁移文件 `20251027_0009_create_dim_date.py` 中创建
- 不在schema.py中定义
- **建议**: 如果需要使用，应该在schema.py中定义；如果未使用，可以考虑清理

**清理建议**: ❌ **不能删除（有数据）**，需要确认是否应该在schema.py中定义

---

### 3. `fact_sales_orders` (core)

**状态**: 0行数据，有大量代码引用（主要在脚本文件）

**代码引用位置**:
- `backend/alter_fact_sales_orders.py` - 修改表脚本
- `backend/analysis_current_schema.py` - 分析脚本
- `backend/apply_migrations.py` - 迁移脚本
- 大部分引用在脚本文件中，不是业务代码

**分析**:
- 表为空
- 大部分引用在脚本文件中（不是实际业务代码）
- 不在schema.py中定义
- 可能有旧的迁移文件创建过

**清理建议**: ✅ **可以清理**（主要引用在脚本文件，不是业务代码）

---

### 4. `user_roles` (public)

**状态**: 2行数据，有40处代码引用

**代码引用位置**:
- `modules/core/db/schema.py:2796` - **在schema.py中定义为Table（关联表）**
- `backend/routers/auth.py` - 认证路由
- `backend/routers/roles.py` - 角色管理路由
- `backend/routers/notifications.py` - 通知路由
- `backend/models/users.py` - 用户模型

**分析**:
- **在schema.py中定义为Table（关联表）**，这是正确的定义方式
- 有实际业务代码引用
- 有2行数据（实际使用中）
- **不应该删除**

**清理建议**: ❌ **不能删除**（在schema.py中定义，有业务代码引用，有数据）

---

### 5. 其他表（public schema，9张）

**状态**: 全部0行数据，代码引用仅在本检查脚本中

**表列表**:
- `collection_tasks_backup`
- `key_value`
- `keyvalue`
- `raw_ingestions`
- `report_execution_log`
- `report_recipient`
- `report_schedule`
- `report_schedule_user`

**分析**:
- 全部为空表
- 代码引用仅在本检查脚本中（不是实际业务代码）
- 可能是旧系统的遗留表
- **可以安全清理**

**清理建议**: ✅ **可以清理**（全部为空，无实际业务代码引用）

---

## 清理建议总结

### ❌ 不能删除的表（2张）

1. **`dim_date`** (core)
   - 有数据（4,018行）
   - 有迁移文件创建
   - **建议**: 如果代码中使用，应该在schema.py中定义；如果未使用，需要确认后清理

2. **`user_roles`** (public)
   - 在schema.py中定义为Table（关联表）
   - 有业务代码引用
   - 有数据（2行）
   - **必须保留**

---

### ⚠️ 需要确认的表（2张）

1. **`campaign_targets`** (a_class)
   - 表为空，但有业务代码引用
   - **建议**: 检查是否应该在schema.py中定义，如果在使用应该保留

2. **`fact_sales_orders`** (core)
   - 表为空，引用主要在脚本文件
   - **建议**: 确认后可以清理

---

### ✅ 可以安全清理的表（8张）

**public schema**:
- `collection_tasks_backup`
- `key_value`
- `keyvalue`
- `raw_ingestions`
- `report_execution_log`
- `report_recipient`
- `report_schedule`
- `report_schedule_user`

**清理SQL**:
```sql
-- public schema（需要确认后执行）
DROP TABLE IF EXISTS collection_tasks_backup CASCADE;
DROP TABLE IF EXISTS key_value CASCADE;
DROP TABLE IF EXISTS keyvalue CASCADE;
DROP TABLE IF EXISTS raw_ingestions CASCADE;
DROP TABLE IF EXISTS report_execution_log CASCADE;
DROP TABLE IF EXISTS report_recipient CASCADE;
DROP TABLE IF EXISTS report_schedule CASCADE;
DROP TABLE IF EXISTS report_schedule_user CASCADE;
```

---

## 下一步行动

### 1. 确认需要保留的表

- [ ] 确认 `campaign_targets` 是否应该在schema.py中定义
- [ ] 确认 `dim_date` 是否在使用（如果使用，需要在schema.py中定义）
- [ ] 确认 `fact_sales_orders` 是否可以清理

### 2. 执行清理（用户确认后）

- [ ] 备份数据库（重要！）
- [ ] 确认可以清理的表列表
- [ ] 执行清理SQL
- [ ] 验证清理结果

---

## 注意事项

1. **备份数据库**: 执行清理前必须备份数据库
2. **代码引用检查**: 已检查代码引用，但建议再次确认
3. **数据重要性**: 对于有数据的表（`dim_date`），需要确认数据是否重要
4. **业务影响**: 清理前需要确认是否会影响业务功能

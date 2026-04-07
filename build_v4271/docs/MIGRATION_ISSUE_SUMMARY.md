# 迁移问题总结

**日期**: 2026-01-11  
**状态**: 遇到复杂的迁移问题，需要用户确认下一步操作

---

## 一、当前状态

**数据库迁移版本**: `20251126_132151`  
**目标版本**: `20260111_0001_complete_missing_tables` (head)

**阻塞迁移**: `collection_module_v460` (20251209_v4_6_0_collection_module_tables.py)

## 二、问题描述

迁移文件 `20251209_v4_6_0_collection_module_tables.py` 尝试添加已存在的列 `sub_domains` 到 `collection_configs` 表，导致 `DuplicateColumn` 错误。

**已确认**:
- `collection_configs` 表已存在
- `collection_task_logs` 表已存在
- `sub_domains` 列已存在于 `collection_configs` 表中

## 三、已尝试的修复方案

1. ✅ 修复了 7 个旧迁移文件，使其具有幂等性
2. ✅ 禁用了 `20251105_204106_create_mv_product_management.py` (SQL语法问题)
3. ✅ 修复了 `20251204_151142_add_currency_code_to_fact_raw_data_tables.py`
4. ⚠️ 尝试修复 `20251209_v4_6_0_collection_module_tables.py`，但遇到 Python 缓存问题

## 四、根本原因

迁移文件中的代码修改没有在 Docker 容器中生效，可能原因：
- Python 字节码缓存 (`.pyc` 文件)
- Docker 卷挂载问题
- Alembic 内部缓存

## 五、建议的解决方案

### 方案 A：手动标记迁移为完成（推荐）

直接更新数据库中的 `alembic_version` 表，跳过问题迁移：

```sql
UPDATE alembic_version SET version_num = '20260111_0001_complete_missing_tables';
```

### 方案 B：删除并重建 Docker 容器

```bash
docker-compose down
docker-compose up -d
```

### 方案 C：手动删除 `sub_domains` 列，然后重新迁移

```sql
ALTER TABLE collection_configs DROP COLUMN IF EXISTS sub_domains;
```

## 六、后续步骤

1. 用户选择解决方案
2. 执行选择的方案
3. 验证迁移完成
4. 确认所有表结构完整性


# 数据迁移指南

## 概述

本文档介绍如何在本地和云端数据库之间迁移数据，包括完整数据库迁移、选择性表迁移和 API 导出/导入。

## 迁移方式对比

| 方式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| 完整数据库迁移 | 初始部署、完整数据迁移 | 数据一致性高、操作简单 | 需要维护窗口、数据量大时耗时 |
| 选择性表迁移 | 日常同步、增量更新 | 灵活、可指定表 | 需要手动指定表、外键关系需注意 |
| API 导出/导入 | 小数据量配置类数据 | 快速、通过 HTTP API | 数据量限制（默认 10000 条） |

## 完整数据库迁移

### 使用场景

- 初始部署：将本地开发数据迁移到云端
- 完整备份：完整备份和恢复数据库
- 环境迁移：从一个环境完整迁移到另一个环境

### 使用方法

```bash
# 从本地迁移到云端
./scripts/migrate_data.sh --mode full --source local --target cloud

# 从云端迁移到本地
./scripts/migrate_data.sh --mode full --source cloud --target local

# 预览模式（不执行实际迁移）
./scripts/migrate_data.sh --mode full --source local --target cloud --dry-run
```

### 流程说明

1. **停止目标数据库应用**（防止数据不一致）
2. **备份目标数据库**（防止失败）
3. **导出源数据库**（使用 `pg_dump`）
4. **传输备份文件到目标服务器**（如果需要）
5. **恢复目标数据库**（使用 `pg_restore`）
6. **验证数据完整性**
7. **启动目标数据库应用**

### 注意事项

- ⚠️ **维护窗口**：完整迁移会锁定数据库，建议在维护窗口期间执行
- ⚠️ **数据量**：大数据量迁移可能需要较长时间
- ⚠️ **网络**：如果源和目标不在同一网络，需要确保网络连接稳定

## 选择性表迁移

### 使用场景

- 日常同步：定期同步特定表的数据
- 增量更新：只迁移新增或更新的数据
- 表级备份：备份特定表的数据

### 使用方法

```bash
# 迁移指定表
python scripts/migrate_selective_tables.py \
  --source <source_db_url> \
  --target <target_db_url> \
  --tables "table1,table2,table3"

# 增量迁移（只迁移新数据）
python scripts/migrate_selective_tables.py \
  --source <source_db_url> \
  --target <target_db_url> \
  --incremental

# 带 WHERE 条件迁移
python scripts/migrate_selective_tables.py \
  --source <source_db_url> \
  --target <target_db_url> \
  --tables "table1" \
  --where "created_at > '2026-01-01'"

# 验证迁移结果
python scripts/migrate_selective_tables.py \
  --source <source_db_url> \
  --target <target_db_url> \
  --tables "table1,table2" \
  --verify-only
```

### 流程说明

1. **连接源数据库和目标数据库**
2. **对每个表执行迁移**：
   - 检查表是否存在
   - 导出数据（支持增量）
   - 导入数据（使用 `ON CONFLICT DO NOTHING` 处理冲突）
   - 验证数据
3. **报告迁移结果**

### 注意事项

- ⚠️ **外键关系**：如果表有外键关系，需要按依赖顺序迁移
- ⚠️ **增量迁移**：需要表有 `updated_at` 或 `created_at` 字段
- ⚠️ **冲突处理**：默认使用 `ON CONFLICT DO NOTHING`，不会更新已存在的记录

## API 导出/导入

### 使用场景

- 小数据量配置类数据（< 10000 条）
- 快速同步：通过 HTTP API 快速同步数据
- 配置迁移：迁移系统配置、用户配置等

### 使用方法

#### 导出数据

```bash
# 使用 curl
curl -X POST "http://localhost:8001/api/data/export" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tables": ["dim_platforms", "dim_shops"],
    "limit": 1000,
    "offset": 0
  }'
```

#### 导入数据

```bash
# 使用 curl
curl -X POST "http://localhost:8001/api/data/import" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "dim_platforms": [
        {"platform_code": "shopee", "name": "Shopee", "is_active": true}
      ]
    },
    "on_conflict": "skip"
  }'
```

### 安全措施

- ✅ **权限验证**：仅管理员可访问
- ✅ **表名白名单**：只允许导出/导入 ORM 定义的表
- ✅ **列名白名单**：只允许导入表中存在的列
- ✅ **参数化查询**：防止 SQL 注入
- ✅ **分页支持**：默认最多 10000 条，防止内存溢出

### 冲突处理策略

- **skip**：跳过冲突记录（`ON CONFLICT DO NOTHING`）
- **update**：更新冲突记录（真正的 UPSERT，自动检测主键列）
  - 自动获取表的主键列（支持单列和复合主键）
  - 如果主键冲突，更新所有非主键列
  - 如果表没有主键或主键列不在导入数据中，会报错
- **error**：遇到冲突时报错

### 注意事项

- ⚠️ **数据量限制**：默认最多 10000 条，大数据量请使用选择性表迁移
- ⚠️ **权限要求**：需要管理员权限
- ⚠️ **网络**：需要确保 API 服务器可访问

## 数据验证

### 验证方法

所有迁移工具都支持数据验证：

```bash
# 完整数据库迁移后验证
./scripts/migrate_data.sh --mode full --source local --target cloud
# 脚本会自动调用验证

# 选择性表迁移后验证
python scripts/migrate_selective_tables.py \
  --source <source_db_url> \
  --target <target_db_url> \
  --tables "table1,table2" \
  --verify

# 仅验证（不迁移）
python scripts/migrate_selective_tables.py \
  --source <source_db_url> \
  --target <target_db_url> \
  --tables "table1,table2" \
  --verify-only
```

### 验证内容

- 表记录数对比
- 关键字段完整性
- 外键关系完整性

## 最佳实践

### 1. 迁移前准备

- ✅ **备份目标数据库**：防止迁移失败
- ✅ **检查表结构一致性**：确保源和目标表结构一致
- ✅ **检查外键关系**：确保按依赖顺序迁移
- ✅ **测试迁移**：在测试环境先测试

### 2. 迁移执行

- ✅ **使用维护窗口**：完整迁移建议在维护窗口期间执行
- ✅ **监控迁移进度**：关注迁移日志和进度
- ✅ **验证数据**：迁移后立即验证数据完整性

### 3. 迁移后检查

- ✅ **数据验证**：验证记录数、关键字段
- ✅ **功能测试**：测试关键功能是否正常
- ✅ **性能检查**：检查数据库性能是否正常

## 常见问题

### Q1: 迁移失败怎么办？

**A**: 
1. 检查迁移日志，找出失败原因
2. 如果目标数据库已部分更新，可以：
   - 恢复备份（如果有）
   - 手动修复数据
   - 重新执行迁移（幂等性保证）

### Q2: 如何迁移有外键关系的表？

**A**: 
1. 按依赖顺序迁移（先迁移被引用的表）
2. 或者暂时禁用外键约束，迁移后再启用

### Q3: 增量迁移如何工作？

**A**: 
1. 增量迁移基于 `updated_at` 或 `created_at` 字段
2. 只迁移最近更新的记录
3. 需要表有这些时间戳字段

### Q4: API 导出/导入的数据量限制是多少？

**A**: 
- 默认最多 10000 条
- 可以通过 `limit` 参数调整
- 大数据量请使用选择性表迁移

### Q5: 如何确保迁移的数据一致性？

**A**: 
1. 使用事务（API 导入自动使用事务）
2. 迁移后验证数据
3. 检查外键关系完整性

## 相关文档

- [数据库迁移规范](../../DEVELOPMENT_RULES/DATABASE_MIGRATION.md)
- [数据库设计规范](../../DEVELOPMENT_RULES/DATABASE.md)
- [部署指南](CI_CD_DEPLOYMENT_GUIDE.md)

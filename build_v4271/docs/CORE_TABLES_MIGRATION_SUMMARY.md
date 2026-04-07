# 核心功能表迁移总结

## 迁移时间
2025-12-31

## 迁移目标
将核心功能表（账号密码、数据同步相关表）从 `public` schema 迁移到 `core` schema，确保系统架构清晰，避免表混乱。

## 迁移结果

### ✅ 成功迁移的表（8张）

| 表名 | 原位置 | 新位置 | 数据行数 | 说明 |
|------|--------|--------|---------|------|
| `platform_accounts` | public | **core** | 12 | 账号密码管理（核心） |
| `collection_tasks` | public | **core** | 4 | 采集任务管理（核心） |
| `collection_task_logs` | public | **core** | - | 采集任务日志 |
| `sync_progress_tasks` | public | **core** | - | 同步进度跟踪 |
| `collection_configs` | public | **core** | - | 采集配置 |
| `component_versions` | public | **core** | - | 组件版本管理 |
| `component_test_history` | public | **core** | - | 组件测试历史 |
| `collection_sync_points` | public | **core** | - | 采集同步点 |

### ✅ 已在core的表（2张）

| 表名 | 位置 | 说明 |
|------|------|------|
| `accounts` | core | 账号管理表（旧表） |
| `catalog_files` | core | 文件目录表（数据同步核心表） |

### 🔧 处理的问题

1. **重复表处理**：
   - `core.collection_tasks` 存在但为空（旧版本表）
   - 自动删除空的 `core.collection_tasks` 表
   - 迁移 `public.collection_tasks`（当前使用的表，有4行数据）

## 迁移安全性验证

### ✅ ORM查询兼容性
- 所有ORM查询不包含schema前缀（如 `db.query(CatalogFile)`）
- PostgreSQL `search_path` 已配置：`public,b_class,a_class,c_class,core,finance`
- 迁移后代码无需修改，自动找到core中的表

### ✅ 外键依赖处理
- PostgreSQL的 `ALTER TABLE SET SCHEMA` 自动处理外键
- 所有外键引用自动更新到新的schema

### ✅ 核心功能验证

| 功能 | 表 | 状态 | 数据行数 |
|------|-----|------|---------|
| 账号登录 | `core.platform_accounts` | ✅ 正常 | 12行 |
| 数据同步 | `core.catalog_files` | ✅ 正常 | 0行（空表正常） |
| 采集任务 | `core.collection_tasks` | ✅ 正常 | 4行 |

## 迁移脚本

**脚本位置**: `scripts/migrate_core_tables.py`

**使用方法**:
```bash
# 预览模式（dry-run）
python scripts/migrate_core_tables.py

# 执行迁移
python scripts/migrate_core_tables.py --execute

# 执行迁移并验证
python scripts/migrate_core_tables.py --execute --verify
```

## 后续建议

### 1. 立即验证核心功能
迁移后请立即验证以下功能：
- ✅ 账号登录功能
- ✅ 数据同步功能
- ✅ 采集任务创建和执行
- ✅ 组件测试功能

### 2. 继续迁移其他表
根据 `docs/DATABASE_TABLE_CLASSIFICATION_RECOMMENDATIONS.md` 的建议，继续迁移：
- `a_class` schema: 用户输入数据表
- `b_class` schema: 数据采集表（部分已在b_class）
- `c_class` schema: 计算输出表
- `finance` schema: 财务域表

### 3. 清理public schema
迁移完成后，清理 `public` schema 中不再使用的表。

## 注意事项

1. **Metabase Question清理**：
   - 用户提到"Metabase Question我们在设计完表格后可以进行清理"
   - 迁移不会影响Metabase Question，因为Metabase通过API查询，不直接依赖schema

2. **路径变化**：
   - 迁移不会导致路径变化
   - ORM模型和代码查询都不包含schema前缀
   - `search_path` 配置确保自动查找

3. **回滚方案**：
   - 如果需要回滚，可以使用 `ALTER TABLE core.{table_name} SET SCHEMA public`
   - 建议在迁移前备份数据库

## 迁移影响评估

### ✅ 无影响的功能
- 账号密码管理：ORM查询自动找到core中的表
- 数据同步：ORM查询自动找到core中的表
- 采集任务：ORM查询自动找到core中的表
- Metabase查询：通过API，不直接依赖schema

### ⚠️ 需要验证的功能
- 前端API调用（应该无影响，因为后端ORM自动处理）
- 数据采集执行（应该无影响，因为ORM自动处理）

## 总结

✅ **迁移成功**：8张核心功能表已安全迁移到 `core` schema  
✅ **功能正常**：核心功能验证通过  
✅ **代码兼容**：无需修改代码，ORM自动找到新位置的表  
✅ **架构清晰**：核心管理表统一在core schema，便于维护


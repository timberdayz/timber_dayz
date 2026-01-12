# 数据库迁移规范

## 概述

本文档定义了数据库迁移的开发规范、最佳实践和常见问题解决方案。

## 核心原则

### 幂等性强制

**所有迁移必须可重复执行，不报错。**

这意味着：
- 创建表前必须检查表是否存在
- 添加字段前必须检查字段是否存在
- 创建索引前必须检查索引是否存在
- 迁移可以多次执行而不产生错误

### 存在性检查模式

```python
# 表创建
if 'table_name' not in existing_tables:
    op.create_table(...)
else:
    safe_print("[SKIP] table_name already exists")

# 字段添加
existing_columns = {c['name'] for c in inspector.get_columns('table_name')}
if 'new_column' not in existing_columns:
    op.add_column('table_name', sa.Column('new_column', ...))
else:
    safe_print("[SKIP] new_column already exists")

# 索引创建
existing_indexes = {idx['name'] for idx in inspector.get_indexes('table_name')}
if 'idx_name' not in existing_indexes:
    op.create_index('idx_name', 'table_name', ['column_name'])
else:
    safe_print("[SKIP] Index already exists")
```

## 迁移开发流程

### 方式1：使用 autogenerate（推荐）

**适用场景**：表结构变更（新增表、字段、索引）

**步骤**：

1. **修改 schema.py**：
   ```python
   # modules/core/db/schema.py
   class NewTable(Base):
       __tablename__ = 'new_table'
       id = Column(Integer, primary_key=True)
       name = Column(String(100), nullable=False)
   ```

2. **生成迁移**：
   ```bash
   alembic revision --autogenerate -m "add_new_table"
   ```

3. **手动检查生成的迁移文件**：
   - 检查生成的代码是否正确
   - **必须添加幂等性检查**（autogenerate 不会自动添加）
   - 检查是否有不需要的变更

4. **测试迁移**：
   ```bash
   # 测试升级
   alembic upgrade heads
   # 测试回滚
   alembic downgrade -1
   # 再次测试升级（验证幂等性）
   alembic upgrade heads
   ```

### 方式2：使用模板（手动编写）

**适用场景**：复杂迁移、数据迁移、autogenerate 无法处理的场景

**步骤**：

1. **复制模板**：
   ```bash
   cp migrations/templates/idempotent_migration.py.template \
      migrations/versions/20260112_120000_add_feature.py
   ```

2. **编辑迁移文件**：
   - 填写 `revision`、`down_revision`、`message`
   - 实现 `upgrade()` 和 `downgrade()` 函数
   - 添加幂等性检查

3. **测试迁移**（同上）

## Schema 快照迁移

### 什么是 Schema 快照迁移？

Schema 快照迁移是一个包含完整数据库结构的单一迁移文件，可作为新环境的起点，不依赖旧迁移历史。

**当前快照迁移**：`migrations/versions/20260112_v5_0_0_schema_snapshot.py`

### 快照迁移后的迁移开发

**重要**：快照迁移后的**第一个**增量迁移的 `down_revision` 必须指向快照迁移：

```python
# 第一个增量迁移
revision = '20260113_0001'
down_revision = 'v5_0_0_schema_snapshot'  # 指向快照迁移
```

**后续迁移**：按正常链式指向前一个迁移：

```python
# 第二个增量迁移
revision = '20260114_0001'
down_revision = '20260113_0001'  # 指向前一个迁移
```

### 生成快照迁移

如果需要更新快照迁移（例如添加了新表），运行：

```bash
python scripts/generate_schema_snapshot.py
```

这会重新生成 `migrations/versions/20260112_v5_0_0_schema_snapshot.py`。

## Alembic autogenerate 使用指南

### 何时使用 autogenerate？

✅ **适用场景**：
- 新增表
- 添加字段
- 添加索引
- 修改字段类型（简单类型）
- 添加/删除唯一约束

❌ **不适用场景**：
- 表重命名（autogenerate 会删除旧表并创建新表）
- 字段重命名（autogenerate 会删除旧字段并添加新字段）
- 数据迁移（需要手动编写 SQL）
- 复杂约束变更（需要手动编写）

### autogenerate 的局限性

1. **表重命名**：autogenerate 无法检测表重命名，会删除旧表并创建新表（导致数据丢失）
2. **字段重命名**：autogenerate 无法检测字段重命名，会删除旧字段并添加新字段（导致数据丢失）
3. **数据迁移**：autogenerate 只处理结构变更，不处理数据迁移
4. **复杂约束**：某些复杂约束变更需要手动编写

### 使用 autogenerate 的最佳实践

1. **生成后必须检查**：autogenerate 生成的代码可能不完美，必须手动检查
2. **添加幂等性检查**：autogenerate 不会自动添加存在性检查，必须手动添加
3. **测试迁移**：生成后必须测试升级和回滚
4. **验证数据**：确保迁移不会导致数据丢失

## 迁移模板使用

### 模板位置

`migrations/templates/idempotent_migration.py.template`

### 模板内容

模板包含：
- `safe_print()` 函数（处理 Windows GBK 编码）
- 表创建示例（带存在性检查）
- 字段添加示例（带存在性检查）
- 索引创建示例（带存在性检查）
- `downgrade()` 幂等示例

### 使用模板

1. 复制模板到 `migrations/versions/` 目录
2. 重命名为合适的文件名（格式：`YYYYMMDD_HHMMSS_description.py`）
3. 填写 `revision`、`down_revision`、`message`
4. 实现 `upgrade()` 和 `downgrade()` 函数
5. 使用模板中的示例代码作为参考

## 常见错误和解决方案

### 错误1：DuplicateTable

**原因**：迁移重复执行，表已存在

**解决方案**：添加存在性检查
```python
if 'table_name' not in existing_tables:
    op.create_table(...)
```

### 错误2：DuplicateColumn

**原因**：迁移重复执行，字段已存在

**解决方案**：添加存在性检查
```python
existing_columns = {c['name'] for c in inspector.get_columns('table_name')}
if 'new_column' not in existing_columns:
    op.add_column(...)
```

### 错误3：FeatureNotSupported（分区表）

**原因**：分区表迁移使用了 `INCLUDING INDEXES`，导致主键约束错误

**解决方案**：
- 不使用 `INCLUDING ALL` 或 `INCLUDING INDEXES`
- 手动创建包含分区键的复合主键

### 错误4：Multiple head revisions

**原因**：迁移历史有多个分支

**解决方案**：
- 使用 `alembic upgrade heads`（复数）而不是 `head`（单数）
- 创建合并迁移（merge migration）合并所有分支

### 错误5：迁移失败但表已部分创建

**原因**：迁移执行过程中失败，部分表已创建

**解决方案**：
- 部署脚本会自动检测并补充缺失的表
- 手动修复：删除部分创建的表，重新执行迁移

## 迁移检查清单

在提交迁移文件前，确保：

- [ ] 所有 `op.create_table()` 都有存在性检查
- [ ] 所有 `op.add_column()` 都有存在性检查
- [ ] 所有 `op.create_index()` 都有存在性检查
- [ ] 使用 `safe_print()` 替代 `print()`
- [ ] `downgrade()` 函数也是幂等的
- [ ] 迁移可以重复执行不报错
- [ ] 没有使用 `INCLUDING ALL` 或 `INCLUDING INDEXES`
- [ ] `revision` 和 `down_revision` 正确设置
- [ ] 测试了升级和回滚
- [ ] 验证了幂等性（重复执行）

## 部署时的智能迁移

部署脚本（`scripts/deploy_remote_production.sh`）包含智能迁移逻辑：

1. **新数据库**：使用 Schema 快照迁移
2. **已有数据库**：尝试增量迁移
3. **迁移失败**：自动检测缺失表并补充

详见部署脚本中的 `smart_database_migrate()` 函数。

## 迁移文件归档策略

### 归档目的

为了简化迁移历史，旧迁移文件已归档到 `migrations/versions_archived/` 目录。新的迁移起点是 Schema 快照迁移（`20260112_v5_0_0_schema_snapshot.py`）。

### 归档内容

- **归档时间**：2026-01-12
- **归档文件数**：55 个旧迁移文件
- **保留文件**：`20260112_v5_0_0_schema_snapshot.py`（作为新起点）

### 归档索引

归档文件的详细信息记录在 `migrations/versions_archived/INDEX.md` 中，包括：
- 每个迁移文件的 `revision` 和 `down_revision`
- 归档时间
- 文件列表

### 使用归档文件

如需查看历史迁移或回滚到旧版本，可以：
1. 查看 `migrations/versions_archived/INDEX.md` 了解迁移历史
2. 从归档目录恢复特定迁移文件（如果需要）

### 归档脚本

使用 `scripts/archive_old_migrations.py` 脚本可以安全地归档迁移文件。

## 相关文档

- [数据库设计规范](DATABASE.md)
- [错误处理和日志规范](ERROR_HANDLING_AND_LOGGING.md)
- [部署指南](../../guides/CI_CD_DEPLOYMENT_GUIDE.md)
- [数据迁移指南](../../guides/DATA_MIGRATION_GUIDE.md)
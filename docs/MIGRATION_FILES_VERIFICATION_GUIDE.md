# 迁移文件验证脚本使用指南

**日期**: 2026-01-11  
**脚本**: `scripts/verify_migration_files.py`  
**用途**: 在提交代码之前检查迁移文件的常见问题

---

## 一、功能说明

这个脚本会在提交代码之前自动检查迁移文件中的常见问题，避免部署时才发现错误。

### 检查项

1. **Python语法错误**
   - 检查迁移文件的Python语法是否正确

2. **BOOLEAN默认值错误**
   - 检查是否有 `server_default=sa.text('1')` 或 `sa.text('0')` 的错误用法
   - 应该使用 `server_default='true'` 或 `server_default='false'`

3. **外键引用错误**
   - 检查是否有 `dim_product.product_surrogate_id` 的错误引用
   - 应该使用 `dim_product_master.product_id`
   - 检查外键引用的表是否在 `schema.py` 中定义

---

## 二、使用方法

### 2.1 基本使用

```bash
# 运行验证脚本
python scripts/verify_migration_files.py
```

### 2.2 输出示例

**成功情况**:
```
================================================================================
迁移文件验证脚本
================================================================================

[1] 读取schema.py中的表定义...
  找到 105 张表定义

[2] 检查 55 个迁移文件...

  [OK] 20250925_0001_init_unified_star_schema.py
  [OK] 20251023_0005_add_erp_core_tables.py
  ...

================================================================================
验证结果汇总
================================================================================
总计: 55 个文件
通过: 55 个
失败: 0 个

[OK] 所有迁移文件验证通过
```

**失败情况**:
```
  [FAIL] 20251023_0005_add_erp_core_tables.py
    第140行: 外键引用错误: dim_product.product_surrogate_id 应该是 dim_product_master.product_id
      代码: sa.ForeignKeyConstraint(['product_id'], ['dim_product.product_surrogate_id'], ),
    第166行: BOOLEAN默认值错误: 使用sa.text('0')，应该是'false'
      代码: sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.text('0')),

================================================================================
验证结果汇总
================================================================================
总计: 55 个文件
通过: 54 个
失败: 1 个

[WARNING] 发现错误，请修复后再提交
```

### 2.3 退出代码

- **0**: 所有迁移文件验证通过
- **1**: 发现错误，需要修复

---

## 三、集成到工作流

### 3.1 本地开发

**建议**: 在提交代码之前运行验证脚本

```bash
# 1. 运行验证脚本
python scripts/verify_migration_files.py

# 2. 如果验证通过，继续提交代码
git add migrations/versions/*.py
git commit -m "fix: 修复迁移文件中的问题"

# 3. 如果验证失败，修复错误后再提交
```

### 3.2 Git Hooks（可选）

可以在 `.git/hooks/pre-commit` 中添加验证脚本，在每次提交前自动运行：

```bash
#!/bin/bash
# .git/hooks/pre-commit

python scripts/verify_migration_files.py
if [ $? -ne 0 ]; then
    echo "迁移文件验证失败，请修复后再提交"
    exit 1
fi
```

### 3.3 CI/CD集成（建议）

在CI/CD流程中添加验证步骤，确保所有合并到主分支的代码都通过验证。

**GitHub Actions 示例**:
```yaml
- name: Verify Migration Files
  run: |
    python scripts/verify_migration_files.py
```

---

## 四、常见问题

### 4.1 BOOLEAN默认值错误

**错误**:
```python
sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
```

**正确**:
```python
sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
```

**原因**: PostgreSQL的BOOLEAN类型默认值必须是 `true` 或 `false`（布尔值），不能使用整数 `1` 或 `0`。

### 4.2 外键引用错误

**错误**:
```python
sa.ForeignKeyConstraint(['product_id'], ['dim_product.product_surrogate_id'], ),
```

**正确**:
```python
sa.ForeignKeyConstraint(['product_id'], ['dim_product_master.product_id'], ),
```

**原因**: 
- `dim_product` 表不存在（错误的表名）
- `dim_product_master` 表存在，是主产品表
- 字段名是 `product_id`，不是 `product_surrogate_id`

### 4.3 表名不存在

**错误**: 外键引用的表在 `schema.py` 中未找到

**解决方法**:
1. 检查表名是否正确
2. 确认表是否在 `schema.py` 中定义
3. 确认表的 `__tablename__` 属性是否正确

---

## 五、历史问题回顾

### 5.1 BOOLEAN默认值错误（2026-01-11修复）

**问题**: 部署时出现 `column "is_active" is of type boolean but default expression is of type integer` 错误

**修复文件**:
- `migrations/versions/20250925_0001_init_unified_star_schema.py`
- `migrations/versions/20251016_0003_add_data_quarantine.py`

**修复数量**: 4处错误

### 5.2 外键引用错误（2026-01-11修复）

**问题**: 部署时出现 `relation "dim_product" does not exist` 错误

**修复文件**:
- `migrations/versions/20251023_0005_add_erp_core_tables.py`

**修复数量**: 3处错误

---

## 六、最佳实践

### 6.1 开发流程

1. **编写迁移文件前**: 检查 `schema.py` 中的表定义
2. **编写迁移文件后**: 运行验证脚本检查问题
3. **提交代码前**: 再次运行验证脚本确保没有问题
4. **合并代码前**: CI/CD会自动运行验证脚本

### 6.2 代码审查

在审查迁移文件时，检查以下内容：
- ✅ BOOLEAN字段的默认值是否使用 `'true'` 或 `'false'`
- ✅ 外键引用的表名是否正确
- ✅ 外键引用的字段名是否正确
- ✅ 外键引用的表是否在 `schema.py` 中定义

### 6.3 测试建议

1. **本地测试**: 在本地Docker环境中测试迁移
2. **语法检查**: 运行验证脚本检查语法错误
3. **功能测试**: 在测试环境中验证迁移功能

---

## 七、相关文档

- [BOOLEAN默认值修复报告](docs/BOOLEAN_DEFAULT_FIX_REPORT.md)
- [外键引用错误修复报告](docs/FOREIGN_KEY_FIX_REPORT.md)
- [数据库迁移最佳实践](docs/DATABASE_MIGRATION_BEST_PRACTICES.md)

---

**最后更新**: 2026-01-11  
**脚本版本**: v1.0.0

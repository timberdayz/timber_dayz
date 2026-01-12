# 数据库迁移优化报告

**完成时间**: 2026-01-12  
**执行**: AI Agent (Cursor)  
**版本**: v4.22.17+

---

## 🎯 改进目标

解决云端部署时数据库迁移失败的问题，特别是外键约束定义错误，并建立完整的迁移验证机制。

---

## 🔴 问题根因分析

### 核心问题

在 Schema Snapshot 迁移脚本 (`migrations/versions/20260112_v5_0_0_schema_snapshot.py`) 中，**复合外键被错误地拆分为多个单独的外键约束**。

### 错误示例

**错误定义（迁移脚本中）：**

```python
# bridge_product_keys 表
sa.ForeignKeyConstraint(['platform_code'], ['dim_products.platform_code'], ),
sa.ForeignKeyConstraint(['shop_id'], ['dim_products.shop_id'], ),
sa.ForeignKeyConstraint(['platform_sku'], ['dim_products.platform_sku'], ),
```

**正确定义（schema.py 中）：**

```python
# 应该是一个复合外键
sa.ForeignKeyConstraint(
    ['platform_code', 'shop_id', 'platform_sku'],
    ['dim_products.platform_code', 'dim_products.shop_id', 'dim_products.platform_sku'],
    ondelete='CASCADE'
),
```

### 为什么会失败？

- `dim_products` 表的主键是**复合主键** `(platform_code, shop_id, platform_sku)`
- 复合主键 = 三个列**组合起来**唯一
- **单个列**（如 `shop_id`）不是唯一的
- PostgreSQL 要求外键必须引用**有唯一约束**的列
- 单独引用 `shop_id` 或 `platform_sku` 会失败

### 错误信息

```
psycopg2.errors.InvalidForeignKey: there is no unique constraint matching given keys for referenced table "dim_products"
```

---

## ✅ 已完成的修复

### 1. 修复迁移脚本中的外键定义错误

#### 修复的表

1. **bridge_product_keys**

   - **修复前**: 3 个单独的外键约束
   - **修复后**: 1 个复合外键约束 + 1 个单列外键约束

2. **fact_product_metrics**
   - **修复前**: 3 个单独的外键约束引用 `dim_products`
   - **修复后**: 1 个复合外键约束引用 `dim_products` + 1 个单列外键约束

#### 修改位置

- `migrations/versions/20260112_v5_0_0_schema_snapshot.py`
  - 第 677-682 行：`bridge_product_keys` 表定义
  - 第 1300-1305 行：`fact_product_metrics` 表定义

---

## 🛠️ 创建的验证工具

### 1. 迁移脚本一致性验证工具

**文件**: `scripts/verify_migration_consistency.py`

**功能**:

- 比对迁移脚本与 `schema.py` 中的表定义
- 验证外键约束是否正确（特别是复合外键）
- 检测复合外键是否被错误拆分
- 验证索引定义是否一致

**使用方法**:

```bash
# 验证最新的 schema snapshot 迁移
python scripts/verify_migration_consistency.py

# 验证指定的迁移文件
python scripts/verify_migration_consistency.py --migration-file migrations/versions/XXXX_schema_snapshot.py
```

**输出示例**:

```
[INFO] 分析迁移文件: migrations/versions/20260112_v5_0_0_schema_snapshot.py
[INFO] 分析 schema 文件: modules/core/db/schema.py

================================================================================
迁移脚本一致性检查报告
================================================================================

[OK] 迁移脚本与 schema.py 一致！
================================================================================
```

### 2. 本地迁移验证脚本

**文件**: `scripts/validate_migrations_local.py`

**功能**:

- 启动临时 PostgreSQL 容器
- 执行所有迁移
- 验证迁移是否成功
- 验证表数量是否正常
- 验证关键表是否存在
- 自动清理临时容器（可选）

**使用方法**:

```bash
# 正常验证（自动清理）
python scripts/validate_migrations_local.py

# 保留容器用于调试
python scripts/validate_migrations_local.py --skip-cleanup
```

**输出示例**:

```
[INFO] 启动临时 PostgreSQL 容器...
[OK] PostgreSQL 容器已启动
[INFO] 等待 PostgreSQL 就绪...
[OK] PostgreSQL 已就绪
[INFO] 执行数据库迁移...
[OK] 迁移执行成功
[INFO] 创建了 64 张表
[OK] 表数量正常（64 张）
[INFO] 验证关键表是否存在...
  [OK] 表 dim_products 存在
  [OK] 表 bridge_product_keys 存在
  [OK] 表 fact_product_metrics 存在
  [OK] 表 dim_product_master 存在

[OK] 本地迁移验证通过！
```

---

## 🔄 CI/CD 集成

### GitHub Actions Workflow 更新

**文件**: `.github/workflows/deploy-production.yml`

**新增步骤**:

1. **PostgreSQL 服务**

   - 在 `validate` job 中添加临时 PostgreSQL 服务
   - 用于迁移测试

2. **迁移脚本一致性验证**

   ```yaml
   - name: Verify Migration Consistency (Release Gate)
     run: |
       python scripts/verify_migration_consistency.py
   ```

3. **数据库迁移测试**
   ```yaml
   - name: Validate Database Migrations (Release Gate)
     env:
       DATABASE_URL: postgresql://migration_test_user:migration_test_pass@localhost:5432/migration_test_db
     run: |
       # 等待 PostgreSQL 就绪
       # 执行迁移
       alembic upgrade heads
       # 验证表数量
       # 验证关键表是否存在
   ```

**验证流程**:

1. ✅ 迁移脚本一致性检查（比对 schema.py）
2. ✅ 实际迁移测试（在临时数据库中执行）
3. ✅ 表结构验证（表数量、关键表存在性）

---

## 📋 开发工作流改进

### 开发前检查清单

在提交代码前，开发者应该：

1. **运行迁移脚本一致性验证**:

   ```bash
   python scripts/verify_migration_consistency.py
   ```

2. **运行本地迁移测试**（如果修改了迁移脚本）:

   ```bash
   python scripts/validate_migrations_local.py
   ```

3. **运行其他验证脚本**:
   ```bash
   python scripts/verify_architecture_ssot.py
   python scripts/verify_contract_first.py
   ```

### CI/CD 自动验证

当 push tag 触发部署时，GitHub Actions 会自动：

1. ✅ 验证迁移脚本一致性
2. ✅ 在临时数据库中执行迁移
3. ✅ 验证表结构完整性
4. ✅ 如果任何检查失败，阻止部署

---

## 🔍 验证工具使用指南

### 何时使用迁移一致性验证工具

- ✅ **创建新的迁移脚本后**（特别是使用 `alembic revision --autogenerate`）
- ✅ **修改 schema.py 后**（需要检查迁移脚本是否需要更新）
- ✅ **Pull Request 前**（确保迁移脚本正确）
- ✅ **本地调试迁移问题时**

### 何时使用本地迁移验证脚本

- ✅ **修改迁移脚本后**（确保迁移能成功执行）
- ✅ **新环境部署前**（确保迁移脚本能在新环境中工作）
- ✅ **调试迁移错误时**（使用 `--skip-cleanup` 保留容器）

---

## 📊 改进效果对比

### 改进前

| 问题                         | 状态 |
| ---------------------------- | ---- |
| 迁移脚本错误在生产环境才发现 | ❌   |
| 没有迁移脚本验证工具         | ❌   |
| 没有本地迁移测试             | ❌   |
| CI 中不测试迁移              | ❌   |
| 迁移失败导致部署阻塞         | ❌   |

### 改进后

| 问题                       | 状态 |
| -------------------------- | ---- |
| 迁移脚本错误在 CI 阶段发现 | ✅   |
| 迁移脚本一致性验证工具     | ✅   |
| 本地迁移验证脚本           | ✅   |
| CI 中自动测试迁移          | ✅   |
| 迁移失败在部署前被阻止     | ✅   |

---

## 🎓 经验教训

### 1. 迁移脚本生成后必须人工审核

**问题**: `alembic revision --autogenerate` 生成的迁移脚本可能不完美

**解决方案**:

- ✅ 使用 `verify_migration_consistency.py` 自动比对
- ✅ 人工审核复合外键定义
- ✅ 在 CI 中强制验证

### 2. 复合外键必须完整定义

**问题**: 复合主键的表，外键必须引用完整的复合键

**正确做法**:

```python
# ✅ 正确：复合外键
sa.ForeignKeyConstraint(
    ['platform_code', 'shop_id', 'platform_sku'],
    ['dim_products.platform_code', 'dim_products.shop_id', 'dim_products.platform_sku'],
    ondelete='CASCADE'
)

# ❌ 错误：拆分的外键
sa.ForeignKeyConstraint(['platform_code'], ['dim_products.platform_code'], ),
sa.ForeignKeyConstraint(['shop_id'], ['dim_products.shop_id'], ),
sa.ForeignKeyConstraint(['platform_sku'], ['dim_products.platform_sku'], ),
```

### 3. 本地验证很重要

**问题**: 生产环境发现问题太晚

**解决方案**:

- ✅ 本地迁移验证脚本（`validate_migrations_local.py`）
- ✅ CI 中自动验证（GitHub Actions）
- ✅ 开发者工具（提前发现问题）

---

## 📝 后续建议

### 短期（已完成）

- [x] 修复迁移脚本中的外键定义错误
- [x] 创建迁移脚本一致性验证工具
- [x] 创建本地迁移验证脚本
- [x] 在 CI 中添加迁移测试

### 中期（可选）

- [ ] 添加迁移脚本生成模板（确保生成的脚本符合规范）
- [ ] 添加迁移回滚测试（验证 downgrade 函数）
- [ ] 添加迁移性能测试（大型数据库迁移耗时）

### 长期（可选）

- [ ] 迁移脚本自动修复工具（自动修复常见错误）
- [ ] 迁移脚本代码审查清单（PR 检查清单）
- [ ] 迁移脚本最佳实践文档（开发指南）

---

## ✅ 验证清单

部署前验证：

- [ ] 运行 `python scripts/verify_migration_consistency.py` 通过
- [ ] 运行 `python scripts/validate_migrations_local.py` 通过（如果修改了迁移）
- [ ] CI 中的迁移测试通过
- [ ] 迁移脚本中的外键约束正确（特别是复合外键）

---

## 📚 相关文档

- [数据库设计规范](docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md)
- [数据库迁移规范](docs/DEVELOPMENT_RULES/DATABASE_MIGRATION.md)
- [开发规范索引](docs/DEVELOPMENT_RULES/README.md)

---

**最后更新**: 2026-01-12  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

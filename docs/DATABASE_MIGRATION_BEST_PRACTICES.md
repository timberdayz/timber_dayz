# 数据库迁移最佳实践指南

**日期**: 2026-01-11  
**目标**: 确保未来数据库表更新、字段增加、新表添加时，迁移不会出现问题

---

## 一、核心原则

### 1.1 Contract-First 开发方法 ⭐⭐⭐

**原则**: 先定义类型/接口，后实现业务逻辑

**数据库迁移流程**:
```
第1步：定义数据模型 → schema.py + Alembic迁移
第2步：定义API契约 → backend/schemas/中的Pydantic模型
第3步：定义路由签名 → @router + response_model
第4步：定义前端API → frontend/src/api/*.js
第5步：实现业务逻辑 → 填充路由函数
第6步：编写测试 → 验证契约
```

**关键点**:
- ✅ **所有表定义必须在 `modules/core/db/schema.py` 中**（SSOT - Single Source of Truth）
- ✅ **修改表结构时，先修改 schema.py，再生成迁移文件**
- ✅ **禁止在迁移文件中直接定义表结构**（应该从 schema.py 生成）

---

## 二、迁移文件生成流程

### 2.1 添加新表

**步骤**:

1. **在 schema.py 中定义表**:
```python
# modules/core/db/schema.py
class NewTable(Base):
    __tablename__ = "new_table"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index('ix_new_table_name', 'name'),
    )
```

2. **生成迁移文件**:
```bash
# 使用 Alembic autogenerate（推荐）
python -m alembic revision --autogenerate -m "add_new_table"

# 或者手动创建迁移文件（如果 autogenerate 失败）
python -m alembic revision -m "add_new_table"
```

3. **检查生成的迁移文件**:
```python
# migrations/versions/20260111_xxxx_add_new_table.py
def upgrade():
    op.create_table(
        'new_table',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_new_table_name', 'new_table', ['name'])

def downgrade():
    op.drop_index('ix_new_table_name', table_name='new_table')
    op.drop_table('new_table')
```

4. **使用 IF NOT EXISTS 模式（可选，但推荐）**:
```python
def upgrade():
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    if 'new_table' not in existing_tables:
        op.create_table(
            'new_table',
            # ... 表定义 ...
        )
    else:
        print("[SKIP] new_table 表已存在")
```

---

### 2.2 添加新字段

**步骤**:

1. **在 schema.py 中添加字段**:
```python
# modules/core/db/schema.py
class ExistingTable(Base):
    __tablename__ = "existing_table"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    # 新增字段
    description = Column(Text, nullable=True)  # 新字段
    status = Column(String(32), nullable=False, server_default='active')  # 新字段
```

2. **生成迁移文件**:
```bash
python -m alembic revision --autogenerate -m "add_fields_to_existing_table"
```

3. **检查生成的迁移文件**:
```python
def upgrade():
    # 添加新字段（使用 IF NOT EXISTS 模式）
    with op.batch_alter_table('existing_table', schema=None) as batch_op:
        # 检查字段是否存在
        inspector = inspect(op.get_bind())
        columns = [col['name'] for col in inspector.get_columns('existing_table')]
        
        if 'description' not in columns:
            batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        
        if 'status' not in columns:
            batch_op.add_column(sa.Column('status', sa.String(length=32), nullable=False, server_default='active'))

def downgrade():
    with op.batch_alter_table('existing_table', schema=None) as batch_op:
        batch_op.drop_column('status')
        batch_op.drop_column('description')
```

**关键点**:
- ✅ **使用 `batch_alter_table` 进行字段修改**（PostgreSQL 推荐）
- ✅ **检查字段是否存在**（避免重复添加）
- ✅ **设置默认值**（如果字段是 NOT NULL）

---

### 2.3 修改字段类型

**步骤**:

1. **在 schema.py 中修改字段类型**:
```python
# 修改前
amount = Column(Float, nullable=False)

# 修改后
amount = Column(Numeric(15, 2), nullable=False)  # 改为精确数值类型
```

2. **生成迁移文件**:
```bash
python -m alembic revision --autogenerate -m "change_amount_type_to_numeric"
```

3. **检查生成的迁移文件**（可能需要手动调整）:
```python
def upgrade():
    # PostgreSQL 类型转换
    op.execute("""
        ALTER TABLE orders 
        ALTER COLUMN amount TYPE NUMERIC(15, 2) 
        USING amount::NUMERIC(15, 2)
    """)

def downgrade():
    op.execute("""
        ALTER TABLE orders 
        ALTER COLUMN amount TYPE DOUBLE PRECISION 
        USING amount::DOUBLE PRECISION
    """)
```

**关键点**:
- ⚠️ **类型转换可能丢失数据**（需要测试）
- ⚠️ **可能需要使用 `USING` 子句**（PostgreSQL）
- ✅ **在生产环境执行前，先在测试环境验证**

---

## 三、避免迁移冲突的策略

### 3.1 使用 IF NOT EXISTS 模式

**为什么重要**:
- ✅ 避免重复创建表/字段
- ✅ 支持多次执行迁移（幂等性）
- ✅ 降低迁移失败风险

**实现方式**:

#### 创建表时:
```python
def upgrade():
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    if 'new_table' not in existing_tables:
        op.create_table('new_table', ...)
    else:
        print("[SKIP] new_table 表已存在")
```

#### 添加字段时:
```python
def upgrade():
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    columns = [col['name'] for col in inspector.get_columns('existing_table')]
    
    if 'new_field' not in columns:
        with op.batch_alter_table('existing_table') as batch_op:
            batch_op.add_column(sa.Column('new_field', sa.String(100), nullable=True))
    else:
        print("[SKIP] new_field 字段已存在")
```

---

### 3.2 迁移文件命名规范

**规范**: `YYYYMMDD_HHMMSS_description.py`

**示例**:
- `20260111_143000_add_user_registration_fields.py`
- `20260111_150000_add_product_images_table.py`
- `20260111_160000_change_amount_to_numeric.py`

**好处**:
- ✅ 按时间排序
- ✅ 描述清晰
- ✅ 避免冲突

---

### 3.3 迁移链管理

**原则**: 每个迁移文件必须正确设置 `down_revision`

**检查迁移链**:
```bash
# 查看迁移历史
python -m alembic history

# 查看当前迁移版本
python -m alembic current

# 检查迁移链是否完整
python -m alembic check
```

**处理多头迁移**:
```python
# 如果出现多个 head，需要创建合并迁移
# migrations/versions/20260111_merge_all_heads.py
revision = '20260111_merge_all_heads'
down_revision = (
    '20260110_complete_schema_base',
    '20251105_204200',
    '20251105_add_image_url',
)
```

---

## 四、迁移验证机制

### 4.1 部署前验证

**使用 `verify_schema_completeness()` 函数**:

```python
# backend/models/database.py
def verify_schema_completeness():
    """
    验证数据库表结构完整性（生产环境必须）
    
    检查：
    1. schema.py 中定义的所有表是否都存在
    2. Alembic 迁移状态是否与代码一致
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables
    
    # 检查 Alembic 版本
    # ...
    
    return {
        "all_tables_exist": len(missing_tables) == 0,
        "missing_tables": list(missing_tables),
        "migration_status": migration_status,
        # ...
    }
```

**在部署脚本中使用**:
```bash
# scripts/deploy_remote_production.sh
# Phase 2: 运行 Alembic 迁移
"${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads

# Phase 2.5: 验证表结构完整性
"${compose_cmd_base[@]}" run --rm --no-deps backend python -c "
from backend.models.database import verify_schema_completeness
result = verify_schema_completeness()
if not result['all_tables_exist']:
    print(f'[ERROR] 缺失表: {result[\"missing_tables\"]}')
    exit(1)
print('[OK] 表结构验证通过')
"
```

---

### 4.2 本地测试

**测试流程**:

1. **在本地环境执行迁移**:
```bash
# 创建测试数据库
docker exec xihong_erp_postgres psql -U erp_user -d postgres -c "CREATE DATABASE test_db;"

# 执行迁移
DATABASE_URL="postgresql://erp_user:password@localhost:5432/test_db" \
python -m alembic upgrade head
```

2. **验证表结构**:
```bash
# 检查所有表是否存在
python -c "
from backend.models.database import verify_schema_completeness
result = verify_schema_completeness()
print(f'缺失表: {result[\"missing_tables\"]}')
"
```

3. **测试回滚**:
```bash
# 回滚到上一个版本
python -m alembic downgrade -1

# 再次升级
python -m alembic upgrade head
```

---

### 4.3 生产环境验证

**部署脚本中的验证**:

```bash
# scripts/deploy_remote_production.sh
# Phase 2: 运行 Alembic 迁移（必须成功）
echo "[INFO] Phase 2: Running Alembic migrations..."
"${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads
MIGRATION_EXIT_CODE=$?

if [ ${MIGRATION_EXIT_CODE} -ne 0 ]; then
  echo "[FAIL] Alembic migrations failed (exit code: ${MIGRATION_EXIT_CODE})"
  echo "[INFO] Deployment blocked due to migration failure"
  exit 1
fi

# Phase 2.5: 验证表结构完整性
echo "[INFO] Phase 2.5: Verifying schema completeness..."
"${compose_cmd_base[@]}" run --rm --no-deps backend python -c "
from backend.models.database import verify_schema_completeness
result = verify_schema_completeness()
if not result['all_tables_exist']:
    print(f'[ERROR] Missing tables: {result[\"missing_tables\"]}')
    exit(1)
if result['migration_status'] != 'up_to_date':
    print(f'[ERROR] Migration status: {result[\"migration_status\"]}')
    exit(1)
print('[OK] Schema verification passed')
"
VERIFY_EXIT_CODE=$?

if [ ${VERIFY_EXIT_CODE} -ne 0 ]; then
  echo "[FAIL] Schema verification failed"
  exit 1
fi
```

---

## 五、常见问题和解决方案

### 5.1 问题1：迁移文件冲突

**症状**: 多个开发者同时创建迁移文件，导致 `down_revision` 冲突

**解决方案**:
1. **使用 Git 分支管理**（每个功能分支独立迁移）
2. **定期合并迁移**（创建合并迁移文件）
3. **使用时间戳命名**（避免冲突）

---

### 5.2 问题2：字段已存在错误

**症状**: `column "xxx" already exists`

**解决方案**:
```python
# 使用 IF NOT EXISTS 模式
def upgrade():
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    columns = [col['name'] for col in inspector.get_columns('table_name')]
    
    if 'new_field' not in columns:
        op.add_column('table_name', sa.Column('new_field', sa.String(100)))
```

---

### 5.3 问题3：表已存在错误

**症状**: `table "xxx" already exists`

**解决方案**:
```python
# 使用 IF NOT EXISTS 模式
def upgrade():
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    
    if 'new_table' not in existing_tables:
        op.create_table('new_table', ...)
```

---

### 5.4 问题4：迁移失败后如何恢复

**步骤**:

1. **检查迁移状态**:
```bash
python -m alembic current
```

2. **查看迁移历史**:
```bash
python -m alembic history
```

3. **回滚到上一个版本**:
```bash
python -m alembic downgrade -1
```

4. **修复迁移文件**:
   - 检查迁移文件中的错误
   - 修复后重新执行

5. **重新执行迁移**:
```bash
python -m alembic upgrade head
```

---

## 六、最佳实践总结

### 6.1 开发流程

1. ✅ **先修改 schema.py**（定义表结构）
2. ✅ **生成迁移文件**（使用 autogenerate）
3. ✅ **检查迁移文件**（确保正确）
4. ✅ **使用 IF NOT EXISTS 模式**（避免冲突）
5. ✅ **本地测试**（验证迁移）
6. ✅ **提交代码**（包含迁移文件）
7. ✅ **部署前验证**（使用 verify_schema_completeness）

### 6.2 迁移文件规范

1. ✅ **使用 IF NOT EXISTS 模式**（幂等性）
2. ✅ **正确设置 down_revision**（迁移链）
3. ✅ **包含完整的 upgrade 和 downgrade**（可回滚）
4. ✅ **添加必要的注释**（说明变更原因）
5. ✅ **测试迁移和回滚**（确保正确）

### 6.3 部署流程

1. ✅ **部署前备份数据库**（重要！）
2. ✅ **执行迁移**（alembic upgrade heads）
3. ✅ **验证表结构**（verify_schema_completeness）
4. ✅ **验证迁移状态**（alembic current）
5. ✅ **启动应用**（确保正常运行）

---

## 七、自动化工具

### 7.1 迁移验证脚本

**脚本**: `scripts/verify_migration_safety.py`

**功能**:
- 检查迁移文件是否正确
- 检查迁移链是否完整
- 检查表结构是否匹配
- 检查是否有冲突

### 7.2 CI/CD 集成

**GitHub Actions 工作流**:
```yaml
- name: Verify Migration Safety
  run: |
    python scripts/verify_migration_safety.py
    
- name: Run Migrations (Test)
  run: |
    docker-compose run --rm backend alembic upgrade head
    
- name: Verify Schema Completeness
  run: |
    docker-compose run --rm backend python -c "
    from backend.models.database import verify_schema_completeness
    result = verify_schema_completeness()
    assert result['all_tables_exist'], f'Missing tables: {result[\"missing_tables\"]}'
    "
```

---

## 八、总结

### 8.1 核心原则

1. **Contract-First**: 先定义 schema.py，再生成迁移
2. **IF NOT EXISTS**: 使用幂等性模式，避免冲突
3. **验证机制**: 部署前验证表结构完整性
4. **测试流程**: 本地测试 → 测试环境 → 生产环境

### 8.2 关键检查点

- ✅ schema.py 是唯一的数据模型定义源（SSOT）
- ✅ 所有迁移文件使用 IF NOT EXISTS 模式
- ✅ 部署前验证表结构完整性
- ✅ 迁移链正确（down_revision 正确）
- ✅ 测试迁移和回滚

---

## 九、相关文档

- [数据库设计规范](DEVELOPMENT_RULES/DATABASE_DESIGN.md) - 表设计详细规范
- [迁移需求总结](MIGRATION_REQUIREMENTS_SUMMARY.md) - 迁移需求说明
- [迁移文件创建计划](MIGRATION_FILE_CREATION_PLAN.md) - 迁移文件创建指南
- [CI/CD 部署指南](CI_CD_DEPLOYMENT_GUIDE.md) - 部署流程

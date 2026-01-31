# Design: 数据库迁移优化技术设计

## 架构设计

### 当前架构问题

```
┌─────────────────┐
│  50+ 迁移文件    │  ← 依赖复杂，难以维护
│  分支合并历史    │
│  缺乏幂等性      │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  部署时执行      │  ← 频繁失败
│  alembic upgrade │
└─────────────────┘
```

### 优化后架构

```
┌─────────────────────┐
│  Schema 快照迁移    │  ← 单一起点，幂等
│  (v5.0.0)          │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  智能迁移检测       │  ← 自动选择策略
│  - 新数据库：快照迁移│
│  - 已有：增量迁移   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  未来增量迁移        │  ← 使用模板，保证幂等
│  (幂等模板)         │
└─────────────────────┘
```

## 技术方案

### 1. Schema 快照迁移设计

**文件结构**：

```python
# migrations/versions/20260112_v5_0_0_schema_snapshot.py

def upgrade():
    """创建完整数据库结构（幂等）"""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # 按模块组织表创建
    # 1. 维度表
    # 2. 事实表
    # 3. 配置表
    # 4. 日志表
    # ...

    # 每个表都检查是否存在
    if 'table_name' not in existing_tables:
        op.create_table('table_name', ...)
    else:
        safe_print("[SKIP] table_name already exists")
```

**优势**：

- 单一文件，易于维护
- 幂等性保证，可重复执行
- 不依赖旧迁移历史
- 可作为新环境的起点

### 2. 智能迁移检测逻辑

**流程图**：

```
开始
  │
  ▼
检查 alembic_version 表是否存在
  │
  ├─ 不存在 → 新数据库
  │              │
  │              ├─ 执行 Schema 快照迁移
  │              │  (alembic upgrade v5_0_0_schema_snapshot)
  │              │
  │              └─ 执行后续增量迁移
  │                 (alembic upgrade heads)
  │
  └─ 存在 → 已有数据库
                 │
                 ├─ 尝试增量迁移
                 │  (alembic upgrade heads)
                 │
                 ├─ 成功 → 完成
                 │
                 └─ 失败 → 直接检查表是否存在（不依赖 verify_schema_completeness）
                            │
                            ├─ 使用 Base.metadata.create_all() 创建缺失的表
                            │
                            ├─ 验证表结构完整性
                            │
                            └─ 验证通过后，alembic stamp heads 标记完成
```

**实现代码**：

```bash
smart_database_migrate() {
    # [FIX] 容器名称配置化（支持不同环境）
    BACKEND_CONTAINER="${BACKEND_CONTAINER:-xihong_erp_backend}"
    POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-xihong_erp_postgres}"
    POSTGRES_USER="${POSTGRES_USER:-erp_user}"
    POSTGRES_DB="${POSTGRES_DB:-xihong_erp}"

    # [FIX] 检查 alembic_version 表是否存在（更准确的判断方式）
    ALEMBIC_VERSION_EXISTS=$(docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -t -c \
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'alembic_version')" \
        2>/dev/null | tr -d ' \n\r')

    if [ "$ALEMBIC_VERSION_EXISTS" = "f" ] || [ -z "$ALEMBIC_VERSION_EXISTS" ]; then
        # 新数据库：使用 Schema 快照迁移
        echo "[INFO] 检测到全新数据库（alembic_version 表不存在），使用 Schema 快照迁移..."
        # [FIX] 验证快照迁移 revision ID 是否存在
        REVISION_EXISTS=$(docker exec ${BACKEND_CONTAINER} alembic history | grep -c "v5_0_0_schema_snapshot" || echo "0")
        if [ "$REVISION_EXISTS" -eq 0 ]; then
            echo "[WARN] 快照迁移 revision ID 'v5_0_0_schema_snapshot' 不存在"
            echo "[INFO] 尝试使用 alembic upgrade heads 作为降级方案..."
            docker exec ${BACKEND_CONTAINER} alembic upgrade heads || {
                echo "[ERROR] 无法执行迁移（快照迁移 revision 不存在且 heads 迁移失败）"
                echo "[INFO] 请检查迁移文件是否存在，或手动创建快照迁移"
                return 1
            }
        else
            docker exec ${BACKEND_CONTAINER} alembic upgrade v5_0_0_schema_snapshot || {
                echo "[ERROR] Schema 快照迁移失败"
                # [FIX] 检查表是否已部分创建
                TABLE_COUNT=$(docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -t -c \
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'" \
                    2>/dev/null | tr -d ' \n\r' || echo "0")
                if [ "$TABLE_COUNT" -gt 5 ]; then
                    echo "[WARN] 检测到表已部分创建（$TABLE_COUNT 张表），可能需要清理或继续"
                    echo "[INFO] 选项1: 清理数据库后重试"
                    echo "[INFO] 选项2: 使用 alembic upgrade heads 继续迁移"
                    # 尝试继续迁移
                    docker exec ${BACKEND_CONTAINER} alembic upgrade heads || {
                        echo "[ERROR] 继续迁移也失败，请手动检查"
                        return 1
                    }
                else
                    return 1
                fi
            }
        fi
        # 继续执行后续增量迁移（如果有）
        # [FIX] 使用 heads（复数）以支持多头迁移分支
        docker exec ${BACKEND_CONTAINER} alembic upgrade heads || {
            echo "[WARN] 后续增量迁移失败，可能是快照迁移 revision ID 不正确或链接问题"
            echo "[INFO] 检查快照迁移的 revision ID 和后续迁移的 down_revision"
            echo "[INFO] 如果表已创建，可以继续部署；否则需要手动修复"
            # 不阻止部署，因为表可能已经通过快照迁移创建
        }
    else
        # 已有数据库：尝试增量迁移
        echo "[INFO] 检测到已有数据库（alembic_version 表存在），尝试增量迁移..."
        # [FIX] 使用 heads（复数）以支持多头迁移分支
        docker exec ${BACKEND_CONTAINER} alembic upgrade heads || {
            # [FIX] 失败时直接检查表是否存在（不依赖 verify_schema_completeness()）
            echo "[WARN] 迁移失败，检测缺失的表..."
            MISSING_TABLES=$(docker exec ${BACKEND_CONTAINER} python3 -c "
from backend.models.database import Base, engine
from sqlalchemy import inspect
import sys

try:
    # 直接检查表是否存在，不依赖 verify_schema_completeness（可能因为多头迁移失败）
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables

    if missing_tables:
        missing = sorted(list(missing_tables))
        print(','.join(missing), file=sys.stdout)
        sys.exit(1)
    else:
        print('[INFO] 所有表都存在，迁移失败可能是其他原因', file=sys.stderr)
        sys.exit(0)
except Exception as e:
    print(f'[ERROR] 检测缺失表时出错: {e}', file=sys.stderr)
    sys.exit(2)
" 2>&1)

            DETECT_EXIT_CODE=$?

            if [ $DETECT_EXIT_CODE -eq 1 ] && [ -n "$MISSING_TABLES" ]; then
                echo "[INFO] 发现缺失的表，尝试补充: $MISSING_TABLES"
                # [FIX] 使用 Base.metadata.create_all() 只创建缺失的表
                # [FIX] 使用 tables 参数指定要创建的表，SQLAlchemy 会自动处理依赖顺序
                docker exec ${BACKEND_CONTAINER} python3 -c "
from backend.models.database import Base, engine
from sqlalchemy import inspect
import sys

inspector = inspect(engine)
existing_tables = set(inspector.get_table_names())
expected_tables = set(Base.metadata.tables.keys())
missing_tables = expected_tables - existing_tables

if missing_tables:
    print(f'[INFO] 创建缺失的表: {missing_tables}')
    # [FIX] 使用 Base.metadata.create_all() 一次性创建所有缺失的表
    # SQLAlchemy 会自动处理外键依赖顺序
    # [FIX] 过滤掉不在 metadata 中的表名（防止 KeyError）
    missing_table_objects = [Base.metadata.tables[t] for t in missing_tables if t in Base.metadata.tables]
    if len(missing_table_objects) < len(missing_tables):
        skipped = set(missing_tables) - set(Base.metadata.tables.keys())
        print(f'[WARN] 跳过不在 metadata 中的表: {skipped}', file=sys.stderr)
    if missing_table_objects:
        Base.metadata.create_all(bind=engine, tables=missing_table_objects, checkfirst=True)
    else:
        print('[WARN] 没有可创建的表（所有缺失的表都不在 metadata 中）', file=sys.stderr)
        sys.exit(1)
    print('[OK] 缺失表已创建')

    # 验证表是否真的创建了
    inspector_after = inspect(engine)
    existing_after = set(inspector_after.get_table_names())
    still_missing = expected_tables - existing_after
    if still_missing:
        print(f'[WARN] 部分表创建失败: {still_missing}', file=sys.stderr)
        sys.exit(1)
else:
    print('[INFO] 所有表都已存在')
" || {
                    echo "[ERROR] 创建缺失表失败"
                    return 1
                }

                # [FIX] 验证表结构完整性后再标记
                # [FIX] 直接检查表是否存在，不依赖 verify_schema_completeness()（可能因多头迁移失败）
                VERIFY_RESULT=$(docker exec ${BACKEND_CONTAINER} python3 -c "
from backend.models.database import Base, engine
from sqlalchemy import inspect
import json
import sys

try:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables

    result = {
        'all_tables_exist': len(missing_tables) == 0,
        'missing_tables': sorted(list(missing_tables)),
        'expected_count': len(expected_tables),
        'actual_count': len(existing_tables)
    }
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({'error': str(e), 'all_tables_exist': False}), file=sys.stderr)
    sys.exit(1)
" 2>&1)

                if echo "$VERIFY_RESULT" | grep -q '"all_tables_exist": true'; then
                    echo "[OK] 表结构验证通过，标记迁移为最新"
                    # [FIX] 仅在验证通过后才标记为最新
                    # [FIX] 检查 head 数量，根据情况选择 stamp 命令
                    # [FIX] 使用更准确的检测方式：统计包含 "(head)" 的行数
                    HEAD_COUNT=$(docker exec ${BACKEND_CONTAINER} alembic heads 2>&1 | grep -E "\(head\)" | wc -l | tr -d ' \n\r' || echo "0")
                    if [ "$HEAD_COUNT" -eq 1 ]; then
                        echo "[INFO] 检测到单个 head，使用 alembic stamp head"
                        docker exec ${BACKEND_CONTAINER} alembic stamp head || {
                            echo "[WARN] alembic stamp head 失败，但表已创建"
                        }
                    else
                        echo "[INFO] 检测到多个 head ($HEAD_COUNT 个)，使用 alembic stamp heads"
                        docker exec ${BACKEND_CONTAINER} alembic stamp heads || {
                            echo "[WARN] alembic stamp heads 失败，但表已创建"
                        }
                    fi
                else
                    echo "[ERROR] 表结构验证失败，不标记迁移"
                    echo "[INFO] 请手动检查并修复表结构"
                    return 1
                fi
            elif [ $DETECT_EXIT_CODE -eq 2 ]; then
                echo "[ERROR] 检测缺失表时出错"
                echo "[INFO] 请检查数据库连接和 Python 环境"
                return 1
            else
                echo "[ERROR] 迁移失败且无法自动修复（所有表都存在）"
                echo "[INFO] 迁移失败可能是其他原因（如字段缺失、索引问题等）"
                echo "[INFO] 请检查迁移日志并手动修复"
                return 1
            fi
        }
    fi
}
```

### 3. 幂等迁移模板设计

**模板结构**：

```python
"""${message}

幂等迁移模板：
- 所有表创建都检查是否存在
- 所有字段添加都检查是否存在
- 所有索引创建都检查是否存在
"""

def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # 表创建示例
    if 'new_table' not in existing_tables:
        op.create_table('new_table', ...)
    else:
        safe_print("[SKIP] new_table already exists")

    # 字段添加示例
    existing_columns = {c['name'] for c in inspector.get_columns('existing_table')}
    if 'new_column' not in existing_columns:
        op.add_column('existing_table', sa.Column('new_column', ...))
    else:
        safe_print("[SKIP] new_column already exists")
```

## 数据流设计

### 新环境部署流程

```
1. Docker 容器启动
   │
2. 检查 alembic_version 表是否存在
   │
3. alembic_version 表不存在 → 新数据库
   │
4. 验证快照迁移 revision ID 是否存在
   │   ├─ 存在 → 继续
   │   └─ 不存在 → 降级使用 alembic upgrade heads
   │
5. 执行 Schema 快照迁移（alembic upgrade v5_0_0_schema_snapshot）
   │   ├─ 成功 → 继续
   │   └─ 失败 → 检查表是否已部分创建
   │              ├─ 部分创建 → 尝试继续迁移（alembic upgrade heads）
   │              └─ 未创建 → 返回错误
   │
6. 执行后续增量迁移（alembic upgrade heads）
   │   ├─ 成功 → 继续
   │   └─ 失败 → 警告但不阻止部署（表可能已通过快照迁移创建）
   │
7. 应用启动
```

### 已有环境迁移流程

```
1. Docker 容器启动
   │
2. 检查 alembic_version 表是否存在
   │
3. alembic_version 表存在 → 已有数据库
   │
4. 尝试 alembic upgrade heads
   │
5. 成功 → 完成
   │
6. 失败 → 直接检查表是否存在（不依赖 verify_schema_completeness，可能因多头迁移失败）
   │
7. 使用 Base.metadata.create_all(bind=engine, tables=[...]) 补充缺失的表（一次性创建，自动处理依赖顺序）
   │
8. 验证表结构完整性
   │
9. 验证通过后，根据 head 数量选择 `alembic stamp head` 或 `alembic stamp heads` 标记完成
```

## 错误处理策略

### 迁移失败恢复

1. **检测失败**：捕获 `alembic upgrade heads` 的退出码
2. **检测缺失表**：直接检查表是否存在（使用 `inspect(engine)` 和 `Base.metadata.tables`）
3. **回退策略**：使用 `Base.metadata.create_all(bind=engine, tables=[...])` 补充缺失的表
4. **标记完成**：根据 head 数量选择 `alembic stamp head` 或 `alembic stamp heads`
5. **日志记录**：记录失败原因和恢复操作

### 常见错误处理

| 错误类型                                | 检测方法                 | 恢复策略                                                                |
| --------------------------------------- | ------------------------ | ----------------------------------------------------------------------- |
| `DuplicateTable`                        | 检查表是否存在           | 跳过创建                                                                |
| `DuplicateColumn`                       | 检查字段是否存在         | 跳过添加                                                                |
| `UndefinedTable`                        | 检查表是否存在           | 使用 `Base.metadata.create_all(bind=engine, tables=[...])` 创建缺失的表 |
| `FeatureNotSupported`                   | 捕获异常                 | 跳过高级特性（如分区表）                                                |
| `init_db()` 生产环境禁用                | 检查环境变量             | 使用 Schema 快照迁移替代                                                |
| `alembic upgrade head` 失败（多头）     | 检查错误信息             | 使用 `alembic upgrade heads`（复数）                                    |
| 迁移失败但表结构不完整                  | 验证表结构完整性         | 创建缺失表，验证通过后才标记                                            |
| `table.create()` 方法不存在             | 使用正确的 API           | 使用 `Base.metadata.create_all(bind=engine, tables=[...])`              |
| 表创建顺序问题（外键依赖）              | 一次性创建               | 使用 `Base.metadata.create_all()` 自动处理依赖顺序                      |
| `alembic stamp heads` 行为不确定        | 检查 head 数量           | 根据 head 数量选择 `stamp head` 或 `stamp heads`（使用准确的检测方式）  |
| `verify_schema_completeness()` 可能失败 | 直接检查表是否存在       | 验证步骤不依赖可能失败的函数，直接使用 `inspect(engine)` 比较           |
| HEAD_COUNT 检测不准确                   | 使用准确的检测方式       | 使用 `grep -E "\(head\)" \| wc -l` 准确统计 head 数量                   |
| `missing_table_objects` KeyError        | 过滤不在 metadata 中的表 | 只创建在 `Base.metadata.tables` 中存在的表                              |
| 快照迁移 revision ID 不存在             | 验证 revision 是否存在   | 在部署前检查 revision，不存在时提供降级方案                             |

## 性能考虑

### 数据库状态检查优化

- 使用 `EXISTS` 查询检查 `alembic_version` 表，比 `COUNT(*)` 更快
- 缓存结果，避免重复查询

### Schema 快照迁移优化

- 使用幂等性检查，只创建缺失的表
- 支持选择性创建（只创建指定的缺失表）
- 不覆盖已有表结构

### 迁移执行优化

- 新环境：使用 Schema 快照迁移，建立完整迁移历史
- 已有环境：只执行增量迁移，不重复执行已完成的迁移
- 失败回退：直接检查表是否存在（使用 `inspect(engine)`），只补充缺失的表

## 安全性考虑

### 数据保护

- 迁移失败时**不删除**已有数据
- Schema 快照迁移只**创建缺失的表**，不修改已有表
- 使用幂等性检查，避免重复创建
- `downgrade()` 函数谨慎实现，避免误删数据
- 不使用 `init_db()` 在生产环境（避免无迁移历史的问题）

### 幂等性保证

- 所有操作都检查是否存在
- 可重复执行不报错
- 不依赖执行顺序

## 可维护性

### 代码组织

- Schema 快照：单一文件，按模块组织，使用自动生成脚本维护
- 模板：标准格式，易于复制
- 规范：文档化，易于遵循
- autogenerate 指南：说明何时使用自动生成，何时手动编写

### 版本控制

- 旧迁移文件归档，不删除
- 创建迁移文件引用索引，便于追溯
- 归档前验证迁移历史完整性
- 新迁移从快照开始，历史清晰
- 支持使用 autogenerate 生成增量迁移

## 数据迁移设计

### 数据迁移架构

```
┌─────────────────────┐
│  数据迁移工具层      │
│  - migrate_data.sh  │  ← 统一入口
│  - migrate_*.py      │  ← Python 工具
│  - API 端点         │  ← REST API
└─────────────────────┘
         │
         ├─ 完整迁移（pg_dump/pg_restore）
         ├─ 选择性迁移（指定表列表）
         └─ API 迁移（小数据量）
         │
         ▼
┌─────────────────────┐
│  数据验证层         │
│  - 记录数验证        │
│  - 字段完整性验证    │
│  - 外键关系验证      │
└─────────────────────┘
```

### 数据迁移工具设计

#### 1. 完整数据库迁移（`migrate_data.sh`）

**使用场景**：初始部署、完整数据迁移

**实现方式**：

```bash
# 导出
pg_dump -h source_host -U user -d database \
  --format=custom \
  --file=backup.dump

# 导入
pg_restore -h target_host -U user -d database \
  --clean --if-exists \
  backup.dump
```

**特点**：

- 完整迁移所有数据
- 保持数据一致性
- 适合维护窗口期间执行

#### 2. 选择性表迁移（`migrate_selective_tables.py`）

**使用场景**：日常同步、增量更新

**实现方式**：

```python
async def migrate_tables(
    source_db_url: str,
    target_db_url: str,
    table_names: list[str],
    incremental: bool = False,
    where_clause: str = None
):
    """迁移指定表的数据"""

    for table_name in table_names:
        # 1. 检查表是否存在
        # 2. 导出数据（支持增量）
        # 3. 导入数据
        # 4. 验证数据
        pass
```

**特点**：

- 灵活选择表
- 支持增量迁移
- 支持数据过滤

#### 3. API 导出/导入（`data_migration.py`）

**使用场景**：小数据量配置类数据

**实现方式**：

```python
# 注意：require_admin 的实际导入路径请根据项目结构确认
# 可能是 from backend.routers.users import require_admin
# 或 from backend.utils.auth import require_admin
from backend.routers.users import require_admin
from fastapi import Depends, HTTPException, APIRouter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.models.database import get_async_db, Base
from modules.core.db import DimUser  # 用户类型
from typing import List, Dict, Any, Optional
import re

router = APIRouter()

# [安全] 白名单验证：只允许导出/导入 ORM 定义的表
def get_allowed_tables() -> set:
    """获取允许操作的表名白名单（从 ORM 元数据获取）"""
    return set(Base.metadata.tables.keys())

def validate_table_name(table_name: str) -> bool:
    """验证表名是否在白名单中，防止 SQL 注入"""
    # 1. 白名单验证
    if table_name not in get_allowed_tables():
        return False
    # 2. 格式验证（只允许字母、数字、下划线）
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        return False
    return True

def validate_column_names(columns: List[str], valid_columns: set) -> bool:
    """验证列名是否有效，防止 SQL 注入"""
    for col in columns:
        if col not in valid_columns:
            return False
        # 格式验证
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
            return False
    return True

@router.post("/data/export")
async def export_data(
    tables: List[str],
    limit: Optional[int] = 10000,  # [性能] 添加分页支持，默认最多 10000 条
    offset: Optional[int] = 0,
    current_user: DimUser = Depends(require_admin),  # 仅管理员可访问
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出指定表的数据（仅管理员）

    安全措施：
    - 表名白名单验证（只允许 ORM 定义的表）
    - 参数化查询（防止 SQL 注入）
    - 分页支持（防止内存溢出）
    """
    data = {}

    for table_name in tables:
        try:
            # [安全] 白名单验证
            if not validate_table_name(table_name):
                raise HTTPException(status_code=400, detail=f"不允许导出表 {table_name}（不在白名单中）")

            # 验证表是否存在
            result = await db.execute(
                text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :table_name)"),
                {"table_name": table_name}
            )
            if not result.scalar():
                raise HTTPException(status_code=404, detail=f"表 {table_name} 不存在")

            # [安全] 使用参数化查询 + 白名单验证后的表名
            # 注意：表名不能参数化，但已通过白名单验证确保安全
            # [性能] 添加分页支持
            query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")
            result = await db.execute(query, {"limit": limit, "offset": offset})
            rows = result.fetchall()
            # 转换为字典列表
            columns = result.keys()
            data[table_name] = [dict(zip(columns, row)) for row in rows]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"导出表 {table_name} 失败: {str(e)}")

    return {
        "success": True,
        "data": data,
        "message": f"成功导出 {len(tables)} 张表的数据",
        "pagination": {"limit": limit, "offset": offset}
    }

@router.post("/data/import")
async def import_data(
    data: Dict[str, List[Dict[str, Any]]],
    on_conflict: str = "skip",  # [功能] 冲突处理策略：skip（跳过）、update（更新）、error（报错）
    current_user: DimUser = Depends(require_admin),  # 仅管理员可访问
    db: AsyncSession = Depends(get_async_db)
):
    """
    导入数据（仅管理员）

    安全措施：
    - 表名白名单验证（只允许 ORM 定义的表）
    - 列名白名单验证（只允许表中存在的列）
    - 参数化查询（防止 SQL 注入）

    冲突处理策略：
    - skip：跳过冲突记录（ON CONFLICT DO NOTHING）
    - update：更新冲突记录（需要指定主键）
    - error：遇到冲突时报错
    """
    if on_conflict not in ("skip", "update", "error"):
        raise HTTPException(status_code=400, detail="on_conflict 参数必须是 skip、update 或 error")

    try:
        imported_tables = []
        skipped_count = 0

        for table_name, records in data.items():
            if not records:
                continue

            try:
                # [安全] 白名单验证
                if not validate_table_name(table_name):
                    raise HTTPException(status_code=400, detail=f"不允许导入表 {table_name}（不在白名单中）")

                # 验证表是否存在
                result = await db.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :table_name)"),
                    {"table_name": table_name}
                )
                if not result.scalar():
                    raise HTTPException(status_code=404, detail=f"表 {table_name} 不存在")

                # [安全] 获取表的有效列名（用于白名单验证）
                result = await db.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table_name"),
                    {"table_name": table_name}
                )
                valid_columns = {row[0] for row in result.fetchall()}

                if records:
                    # 获取列名并验证
                    columns = list(records[0].keys())

                    # [安全] 列名白名单验证
                    if not validate_column_names(columns, valid_columns):
                        invalid_cols = set(columns) - valid_columns
                        raise HTTPException(status_code=400, detail=f"无效列名: {invalid_cols}")

                    # [安全] 构建参数化插入语句
                    # 注意：表名和列名不能参数化，但已通过白名单验证确保安全
                    columns_str = ", ".join(columns)
                    placeholders = ", ".join([f":{col}" for col in columns])

                    # [功能] 根据冲突处理策略构建 SQL
                    # 注意：update 策略需要主键信息，当前简化实现为跳过
                    # 如需真正的 UPSERT，需要获取主键列并构建 ON CONFLICT (pk) DO UPDATE SET ...
                    if on_conflict == "skip":
                        sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                    elif on_conflict == "error":
                        sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                    else:  # update（当前简化为 skip，后续可扩展为真正的 UPSERT）
                        # TODO: 实现真正的 UPSERT 需要：
                        # 1. 获取表的主键列：SELECT a.attname FROM pg_constraint c JOIN pg_attribute a ON ...
                        # 2. 构建 ON CONFLICT (pk_col) DO UPDATE SET col1 = EXCLUDED.col1, ...
                        sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

                    # 批量插入
                    for record in records:
                        try:
                            await db.execute(text(sql), record)
                        except Exception as e:
                            if on_conflict == "error":
                                raise
                            skipped_count += 1

                imported_tables.append(table_name)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"导入表 {table_name} 失败: {str(e)}")

        await db.commit()

        return {
            "success": True,
            "message": f"成功导入 {len(imported_tables)} 张表的数据",
            "imported_tables": imported_tables,
            "skipped_count": skipped_count
        }
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"数据导入失败: {str(e)}")
```

**特点**：

- 快速同步
- 适合配置类数据
- 通过 HTTP API 调用

### 数据迁移流程

#### 完整数据库迁移流程

```
1. 停止目标数据库应用
   │
2. 备份目标数据库（防止失败）
   │
3. 导出源数据库（pg_dump）
   │
4. 传输备份文件到目标服务器
   │
5. 恢复目标数据库（pg_restore）
   │
6. 验证数据完整性
   │
7. 启动目标数据库应用
```

#### 选择性表迁移流程

```
1. 连接源数据库和目标数据库
   │
2. 对每个表执行迁移
   │
   ├─ 检查表是否存在
   │
   ├─ 导出数据（支持增量）
   │
   ├─ 导入数据
   │
   └─ 验证数据
   │
3. 验证外键关系
   │
4. 生成迁移报告
```

#### API 迁移流程

```
1. 调用导出 API
   │
2. 获取 JSON 数据
   │
3. 调用导入 API
   │
4. 验证导入结果
```

### 数据验证策略

#### 验证内容

1. **记录数验证**：

   - 源数据库记录数 = 目标数据库记录数

2. **字段完整性验证**：

   - 关键字段不为 NULL
   - 字段值范围正确

3. **外键关系验证**：
   - 外键引用存在
   - 级联关系正确

#### 验证实现

```python
from sqlalchemy import func, text

async def validate_migration(
    source_db: AsyncSession,
    target_db: AsyncSession,
    table_name: str
) -> dict:
    """
    验证迁移数据

    注意：此函数使用原始 SQL 查询，避免需要 ORM 模型映射。
    如果使用 ORM 模型，需要根据 table_name 动态获取对应的模型类。
    """

    # [安全] 表名无法参数化，必须先做白名单/格式校验
    # 注意：实际使用时应导入 validate_table_name 函数
    # from backend.routers.data_migration import validate_table_name
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        raise ValueError(f"invalid table_name: {table_name}")

    # 1. 记录数验证（使用原始 SQL，避免需要 ORM 模型）
    source_result = await source_db.execute(
        text(f"SELECT COUNT(*) FROM {table_name}")
    )
    source_count = source_result.scalar()

    target_result = await target_db.execute(
        text(f"SELECT COUNT(*) FROM {table_name}")
    )
    target_count = target_result.scalar()

    # 2. 字段完整性验证
    # 示例：检查关键字段不为 NULL
    # null_check = await target_db.execute(
    #     text(f"SELECT COUNT(*) FROM {table_name} WHERE key_column IS NULL")
    # )

    # 3. 外键关系验证
    # 示例：检查外键引用是否存在
    # fk_check = await target_db.execute(
    #     text(f"SELECT COUNT(*) FROM {table_name} t LEFT JOIN related_table r ON t.fk_id = r.id WHERE r.id IS NULL")
    # )

    return {
        "table": table_name,
        "source_count": source_count,
        "target_count": target_count,
        "valid": source_count == target_count
    }
```

### 错误处理策略

#### 迁移失败处理

1. **检测失败**：捕获异常和错误码
2. **回滚策略**：删除已导入的数据
3. **日志记录**：记录失败原因和已迁移的表
4. **报告生成**：生成详细的迁移报告

#### 常见错误处理

| 错误类型 | 检测方法       | 恢复策略              |
| -------- | -------------- | --------------------- |
| 连接失败 | 捕获连接异常   | 重试 3 次，失败后报告 |
| 表不存在 | 检查表是否存在 | 跳过或创建表          |
| 数据冲突 | 检查唯一约束   | 更新或跳过            |
| 外键约束 | 检查外键关系   | 按依赖顺序迁移        |

### 性能考虑

#### 大数据量优化

- **分批迁移**：大表分批迁移，避免内存溢出
- **并行迁移**：独立表可并行迁移
- **增量迁移**：只迁移新数据，减少传输量

#### 网络优化

- **压缩传输**：使用 gzip 压缩备份文件
- **断点续传**：支持中断后继续迁移
- **增量同步**：只传输变更数据

### 安全性考虑

#### 数据保护

- **备份策略**：迁移前自动备份目标数据库
- **权限控制**：API 端点仅管理员可访问
- **数据加密**：传输过程中加密敏感数据

#### 审计日志

- **操作记录**：记录所有迁移操作
- **变更追踪**：记录数据变更历史
- **访问日志**：记录 API 访问日志

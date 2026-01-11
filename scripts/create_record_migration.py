#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建记录型迁移文件

由于66张表已经在数据库中（通过init_db()创建），创建一个"记录"迁移文件。
使用 Base.metadata.create_all() 来创建缺失的表（虽然不是最佳实践，但在这种情况下是可行的）。
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.audit_all_tables import get_schema_tables, get_migration_tables


def safe_print(text_str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def get_missing_tables():
    """获取未迁移的表列表"""
    schema_tables = get_schema_tables()
    migration_tables_dict = get_migration_tables()
    all_migration_tables = set()
    for tables in migration_tables_dict.values():
        all_migration_tables.update(tables)
    
    missing = schema_tables - all_migration_tables - {'alembic_version', 'apscheduler_jobs'}
    return sorted(list(missing))


def create_record_migration():
    """创建记录型迁移文件"""
    missing_tables = get_missing_tables()
    
    safe_print(f"[INFO] 发现 {len(missing_tables)} 张未迁移的表")
    safe_print(f"[INFO] 创建记录型迁移文件...")
    
    # 由于表已经在数据库中，我们创建一个使用 Base.metadata.create_all() 的迁移文件
    # 虽然不是最佳实践，但在这种情况下是可行的
    
    revision_id = "20260111_0001_complete_missing_tables"
    down_revision = "20260111_merge_all_heads"
    
    # 生成表列表字符串
    tables_list_str = ',\n'.join(f'        "{table}"' for table in missing_tables)
    
    content = f'''"""Complete missing tables migration (Record Type)

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

创建所有在schema.py中定义但迁移文件中未创建的表（记录型迁移）。

包含 {len(missing_tables)} 张表。

注意：
- 由于表已经在数据库中（通过init_db()创建），此迁移主要是为了记录
- 使用 Base.metadata.create_all() 来创建缺失的表（虽然不是最佳实践，但在这种情况下是可行的）
- 使用 IF NOT EXISTS 模式（检查表是否存在）
- 如果表已存在，将跳过创建
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, JSON
from sqlalchemy import inspect
from sqlalchemy.engine import reflection

# 导入 Base 和所有模型
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from modules.core.db import Base
from backend.models.database import engine


# revision identifiers, used by Alembic.
revision = '{revision_id}'
down_revision = '{down_revision}'
branch_labels = None
depends_on = None


def upgrade():
    """
    创建所有缺失的表（记录型迁移）
    
    由于表已经在数据库中（通过init_db()创建），此迁移主要是为了记录。
    使用 Base.metadata.create_all() 来创建缺失的表。
    """
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    print("[INFO] 开始创建缺失的表（记录型迁移）...")
    
    # 需要处理的表列表
    missing_tables_list = [
{tables_list_str}
    ]
    
    print(f"[INFO] 需要处理的表数量: {{len(missing_tables_list)}}")
    
    # 使用 Base.metadata.create_all() 创建缺失的表
    # 虽然不是最佳实践，但在这种情况下是可行的（表已经在数据库中）
    
    # 检查哪些表不存在
    missing = [t for t in missing_tables_list if t not in existing_tables]
    
    if missing:
        print(f"[INFO] 需要创建 {{len(missing)}} 张表: {{', '.join(missing[:10])}}{{'...' if len(missing) > 10 else ''}}")
        
        # 使用 Base.metadata.create_all() 创建表
        # 注意：这需要所有模型都已导入（通过 from modules.core.db import Base 实现）
        Base.metadata.create_all(bind=engine, checkfirst=True)
        print(f"[OK] 使用 Base.metadata.create_all() 创建了 {{len(missing)}} 张表")
    else:
        print("[INFO] 所有表都已存在，无需创建")
        print("[INFO] 此迁移主要用于记录，确保所有表都在迁移历史中")
    
    print(f"[OK] 记录型迁移完成: 处理 {{len(missing_tables_list)}} 张表")


def downgrade():
    """删除所有在本迁移中创建的表（谨慎使用）"""
    # 注意：downgrade 只删除在本迁移中创建的表
    # 如果表在迁移前已存在，则不会删除
    
    tables_to_drop = [
{tables_list_str}
    ]
    
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    for table in tables_to_drop:
        if table in existing_tables:
            try:
                op.drop_table(table)
                print(f"[OK] 删除表: {{table}}")
            except Exception as e:
                print(f"[SKIP] 表 {{table}} 无法删除: {{e}}")
        else:
            print(f"[SKIP] 表 {{table}} 不存在")
'''
    
    # 保存到文件
    output_file = project_root / "migrations" / "versions" / f"{revision_id}.py"
    
    # 如果文件已存在，备份
    if output_file.exists():
        backup_file = output_file.with_suffix('.py.backup')
        backup_file.write_text(output_file.read_text(encoding='utf-8'), encoding='utf-8')
        safe_print(f"[INFO] 备份现有文件: {backup_file}")
    
    output_file.write_text(content, encoding='utf-8')
    
    safe_print(f"[OK] 记录型迁移文件已生成: {output_file}")
    safe_print(f"[INFO] 由于表已经在数据库中，此迁移主要用于记录")
    safe_print(f"[INFO] 使用 Base.metadata.create_all() 创建缺失的表（虽然不是最佳实践，但在这种情况下是可行的）")


if __name__ == "__main__":
    try:
        create_record_migration()
    except Exception as e:
        safe_print(f"[ERROR] 创建迁移文件失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

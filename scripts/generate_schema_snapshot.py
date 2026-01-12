#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Schema Snapshot Migration Generator

从 modules/core/db/schema.py 自动生成完整的 Schema 快照迁移文件。

用法:
    python scripts/generate_schema_snapshot.py

输出:
    migrations/versions/20260112_v5_0_0_schema_snapshot.py
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from modules.core.db import Base
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import Column, String, Integer, Float, Boolean, Date, DateTime, JSON, Text, BigInteger, Numeric
    from sqlalchemy.dialects.postgresql import JSONB
    import sqlalchemy as sa
except ImportError as e:
    print(f"[ERROR] Failed to import required modules: {e}")
    print("[INFO] Please ensure you are running from the project root directory")
    sys.exit(1)


def get_safe_print_function() -> str:
    """生成 safe_print() 函数代码"""
    return '''def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)
'''


def column_to_sa_column(column: Column, is_single_pk: bool = False) -> str:
    """将 SQLAlchemy Column 转换为 Alembic sa.Column 代码"""
    col_type = column.type
    
    # 处理特殊类型
    if isinstance(col_type, String):
        length = col_type.length
        if length:
            type_str = f"sa.String(length={length})"
        else:
            type_str = "sa.String()"
    elif isinstance(col_type, Numeric):
        precision = col_type.precision
        scale = col_type.scale
        if precision and scale:
            type_str = f"sa.Numeric(precision={precision}, scale={scale})"
        elif precision:
            type_str = f"sa.Numeric(precision={precision})"
        else:
            type_str = "sa.Numeric()"
    elif isinstance(col_type, JSONB):
        type_str = "sa.dialects.postgresql.JSONB"
    elif isinstance(col_type, JSON):
        type_str = "sa.JSON"
    elif isinstance(col_type, BigInteger):
        type_str = "sa.BigInteger()"
    elif isinstance(col_type, Integer):
        type_str = "sa.Integer()"
    elif isinstance(col_type, Float):
        type_str = "sa.Float()"
    elif isinstance(col_type, Boolean):
        type_str = "sa.Boolean()"
    elif isinstance(col_type, Date):
        type_str = "sa.Date()"
    elif isinstance(col_type, DateTime):
        type_str = "sa.DateTime()"
    elif isinstance(col_type, Text):
        type_str = "sa.Text()"
    else:
        # 降级处理
        type_name = str(col_type.__class__.__name__)
        type_str = f"sa.{type_name}()"
    
    # 构建列参数
    params = []
    if column.nullable is False:
        params.append("nullable=False")
    # [FIX] autoincrement 只在单列主键且是整数类型时设置
    if column.primary_key and is_single_pk and column.autoincrement:
        if isinstance(col_type, (Integer, BigInteger)):
            params.append("autoincrement=True")
    if column.server_default is not None:
        if hasattr(column.server_default, 'arg'):
            default_arg = column.server_default.arg
            if isinstance(default_arg, str):
                # 转义单引号
                default_arg = default_arg.replace("'", "\\'")
                params.append(f"server_default=sa.text('{default_arg}')")
            else:
                params.append(f"server_default={default_arg}")
    
    # 过滤空参数
    params = [p for p in params if p]
    
    if params:
        return f"sa.Column('{column.name}', {type_str}, {', '.join(params)})"
    else:
        return f"sa.Column('{column.name}', {type_str})"


def generate_table_creation_code(table_name: str, table: Any) -> str:
    """生成表创建代码"""
    lines = []
    lines.append(f"    if '{table_name}' not in existing_tables:")
    lines.append(f"        op.create_table(")
    lines.append(f"            '{table_name}',")
    
    # 检查是否是单列主键
    pk_cols = [col.name for col in table.primary_key.columns]
    is_single_pk = len(pk_cols) == 1
    
    # 添加列
    for column in table.columns:
        col_code = column_to_sa_column(column, is_single_pk=is_single_pk and column.primary_key)
        lines.append(f"            {col_code},")
    
    # 添加主键约束（复合主键）
    if pk_cols and not is_single_pk:
        pk_cols_str = ', '.join([f"'{c}'" for c in pk_cols])
        lines.append(f"            sa.PrimaryKeyConstraint({pk_cols_str}),")
    
    # 添加唯一约束
    for constraint in table.constraints:
        if isinstance(constraint, sa.UniqueConstraint):
            cols = [col.name for col in constraint.columns]
            cols_str = ', '.join([f"'{c}'" for c in cols])
            if constraint.name:
                lines.append(f"            sa.UniqueConstraint({cols_str}, name='{constraint.name}'),")
            else:
                lines.append(f"            sa.UniqueConstraint({cols_str}),")
    
    # 添加外键约束（去重）
    fk_constraints = {}
    for fk in table.foreign_keys:
        ref_table = fk.column.table.name
        ref_col = fk.column.name
        # 使用 (local_col, ref_table, ref_col) 作为唯一键
        fk_key = (fk.parent.name, ref_table, ref_col)
        if fk_key not in fk_constraints:
            fk_constraints[fk_key] = f"sa.ForeignKeyConstraint(['{fk.parent.name}'], ['{ref_table}.{ref_col}'], )"
    
    for fk_constraint in fk_constraints.values():
        lines.append(f"            {fk_constraint},")
    
    # 移除最后一个逗号
    if lines[-1].endswith(','):
        lines[-1] = lines[-1][:-1]
    
    lines.append(f"        )")
    
    # 添加索引
    for index in table.indexes:
        if index.name:
            cols = [col.name for col in index.columns]
            lines.append(f"        op.create_index('{index.name}', '{table_name}', {cols})")
    
    lines.append(f"        safe_print(\"[OK] {table_name} table created\")")
    lines.append(f"    else:")
    lines.append(f"        safe_print(\"[SKIP] {table_name} table already exists\")")
    
    return "\n".join(lines)


def generate_migration_file() -> str:
    """生成完整的迁移文件内容"""
    # 获取所有表
    tables = Base.metadata.tables
    
    # 按表名排序（确保依赖顺序）
    sorted_tables = sorted(tables.items())
    
    # 生成文件内容
    lines = []
    
    # 文件头
    lines.append('"""Schema Snapshot Migration (v5.0.0)')
    lines.append('')
    lines.append('Revision ID: v5_0_0_schema_snapshot')
    lines.append('Revises: None')
    lines.append(f'Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')
    lines.append('完整的数据库结构快照迁移。')
    lines.append('包含所有在 schema.py 中定义的表。')
    lines.append('')
    lines.append('注意：')
    lines.append('- 此迁移是幂等的，可以重复执行')
    lines.append('- 如果表已存在，将跳过创建')
    lines.append('- 可作为新环境的起点，不依赖旧迁移历史')
    lines.append('"""')
    lines.append('')
    lines.append('from alembic import op')
    lines.append('import sqlalchemy as sa')
    lines.append('from sqlalchemy import inspect')
    lines.append('from sqlalchemy.dialects.postgresql import JSONB')
    lines.append('')
    lines.append('')
    lines.append('# revision identifiers, used by Alembic.')
    lines.append("revision = 'v5_0_0_schema_snapshot'")
    lines.append('down_revision = None')
    lines.append('branch_labels = None')
    lines.append('depends_on = None')
    lines.append('')
    lines.append('')
    lines.append(get_safe_print_function())
    lines.append('')
    lines.append('')
    lines.append('def upgrade():')
    lines.append('    """创建完整数据库结构（幂等）"""')
    lines.append('    conn = op.get_bind()')
    lines.append('    inspector = inspect(conn)')
    lines.append('    existing_tables = set(inspector.get_table_names())')
    lines.append('')
    
    # 生成每个表的创建代码
    for idx, (table_name, table) in enumerate(sorted_tables, 1):
        lines.append(f"    # ==================== {idx}. {table_name} ====================")
        lines.append(f"    safe_print(\"[{idx}/{len(sorted_tables)}] Creating {table_name} table...\")")
        lines.append('')
        lines.append(generate_table_creation_code(table_name, table))
        lines.append('')
    
    # downgrade 函数
    lines.append('')
    lines.append('')
    lines.append('def downgrade():')
    lines.append('    """回滚：删除所有表（谨慎使用）"""')
    lines.append('    # 注意：downgrade 会删除所有表，生产环境请谨慎使用')
    lines.append('    conn = op.get_bind()')
    lines.append('    inspector = inspect(conn)')
    lines.append('    existing_tables = set(inspector.get_table_names())')
    lines.append('')
    
    # 按相反顺序删除表（处理外键依赖）
    for idx, (table_name, table) in enumerate(reversed(sorted_tables), 1):
        lines.append(f"    if '{table_name}' in existing_tables:")
        lines.append(f"        op.drop_table('{table_name}')")
        lines.append(f"        safe_print(\"[OK] {table_name} table dropped\")")
        lines.append('')
    
    return '\n'.join(lines)


def main():
    """主函数"""
    print("[INFO] Generating schema snapshot migration...")
    
    # 生成迁移文件内容
    migration_content = generate_migration_file()
    
    # 输出文件路径
    output_file = project_root / "migrations" / "versions" / "20260112_v5_0_0_schema_snapshot.py"
    
    # 确保目录存在
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 写入文件
    output_file.write_text(migration_content, encoding='utf-8')
    
    print(f"[OK] Schema snapshot migration generated: {output_file}")
    print(f"[INFO] Total tables: {len(Base.metadata.tables)}")
    
    # 验证生成的文件
    try:
        compile(migration_content, str(output_file), 'exec')
        print("[OK] Generated file syntax is valid")
    except SyntaxError as e:
        print(f"[ERROR] Generated file has syntax errors: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

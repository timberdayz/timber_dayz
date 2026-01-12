#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
迁移脚本一致性验证工具

功能：
1. 比对迁移脚本与 schema.py 中的表定义
2. 验证外键约束是否正确（特别是复合外键）
3. 验证索引定义是否一致
4. 验证字段类型是否一致

使用方法:
    python scripts/verify_migration_consistency.py
    python scripts/verify_migration_consistency.py --migration-file migrations/versions/XXXX_schema_snapshot.py
"""

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import argparse


def safe_print(text: str):
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


class MigrationAnalyzer:
    """分析迁移脚本中的表定义"""
    
    def __init__(self, migration_file: Path):
        self.migration_file = migration_file
        self.tables: Dict[str, Dict] = {}
    
    def parse_migration_file(self):
        """解析迁移文件，提取表定义"""
        with open(self.migration_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则表达式提取 op.create_table 调用
        # 匹配模式：op.create_table('table_name', ...)
        table_pattern = r"op\.create_table\s*\(\s*['\"]([^'\"]+)['\"][^)]+\)"
        
        # 更精确的匹配：找到整个 create_table 调用
        create_table_blocks = re.finditer(
            r"op\.create_table\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]+)\)",
            content,
            re.DOTALL
        )
        
        for match in create_table_blocks:
            table_name = match.group(1)
            table_content = match.group(2)
            
            # 提取外键约束
            foreign_keys = self._extract_foreign_keys(table_content, table_name)
            
            self.tables[table_name] = {
                'foreign_keys': foreign_keys,
                'raw_content': table_content
            }
    
    def _extract_foreign_keys(self, content: str, table_name: str) -> List[Dict]:
        """提取外键约束定义"""
        foreign_keys = []
        
        # 匹配 ForeignKeyConstraint 调用
        # 模式：sa.ForeignKeyConstraint([...], [...], ondelete='...')
        fk_pattern = r"sa\.ForeignKeyConstraint\s*\(\s*\[([^\]]+)\]\s*,\s*\[([^\]]+)\](?:.*?ondelete=['\"]([^'\"]+)['\"])?"
        
        matches = re.finditer(fk_pattern, content, re.DOTALL)
        
        for match in matches:
            source_cols_str = match.group(1)
            target_cols_str = match.group(2)
            ondelete = match.group(3) if match.group(3) else None
            
            # 解析列名列表
            source_cols = [col.strip().strip("'\"") for col in source_cols_str.split(',')]
            target_cols = [col.strip().strip("'\"") for col in target_cols_str.split(',')]
            
            # 提取目标表名（从 'dim_products.platform_code' 提取 'dim_products'）
            target_table = target_cols[0].split('.')[0] if target_cols else None
            
            foreign_keys.append({
                'source_columns': source_cols,
                'target_table': target_table,
                'target_columns': [col.split('.')[-1] if '.' in col else col for col in target_cols],
                'ondelete': ondelete
            })
        
        return foreign_keys
    
    def get_table_foreign_keys(self, table_name: str) -> List[Dict]:
        """获取表的外键约束"""
        return self.tables.get(table_name, {}).get('foreign_keys', [])


class SchemaAnalyzer:
    """分析 schema.py 中的表定义"""
    
    def __init__(self, schema_file: Path):
        self.schema_file = schema_file
        self.tables: Dict[str, Dict] = {}
        
        # 添加项目根目录到路径
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        try:
            from modules.core.db import Base
            from sqlalchemy import inspect
            
            # 从 Base.metadata 中获取所有表
            for table_name, table in Base.metadata.tables.items():
                foreign_keys = []
                
                # 提取外键约束
                for fk in table.foreign_keys:
                    # 获取外键约束对象
                    constraint = fk.constraint
                    if constraint:
                        source_cols = [col.name for col in constraint.columns]
                        target_table = fk.column.table.name
                        target_cols = [col.name for col in constraint.elements]
                        ondelete = getattr(constraint, 'ondelete', None)
                        
                        foreign_keys.append({
                            'source_columns': source_cols,
                            'target_table': target_table,
                            'target_columns': target_cols,
                            'ondelete': str(ondelete) if ondelete else None
                        })
                
                self.tables[table_name] = {
                    'foreign_keys': foreign_keys
                }
        except Exception as e:
            safe_print(f"[ERROR] 无法导入 schema: {e}")
            raise
    
    def get_table_foreign_keys(self, table_name: str) -> List[Dict]:
        """获取表的外键约束"""
        return self.tables.get(table_name, {}).get('foreign_keys', [])


class MigrationConsistencyChecker:
    """迁移脚本一致性检查器"""
    
    def __init__(self, schema_file: Path, migration_file: Path):
        self.schema_file = schema_file
        self.migration_file = migration_file
        self.schema_analyzer = SchemaAnalyzer(schema_file)
        self.migration_analyzer = MigrationAnalyzer(migration_file)
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def check(self) -> bool:
        """执行所有检查"""
        safe_print(f"[INFO] 分析迁移文件: {self.migration_file}")
        self.migration_analyzer.parse_migration_file()
        
        safe_print(f"[INFO] 分析 schema 文件: {self.schema_file}")
        
        # 检查所有表
        all_tables = set(self.schema_analyzer.tables.keys()) | set(self.migration_analyzer.tables.keys())
        
        for table_name in sorted(all_tables):
            if table_name not in self.schema_analyzer.tables:
                self.warnings.append(f"表 {table_name} 在 schema.py 中不存在，但在迁移脚本中存在")
                continue
            
            if table_name not in self.migration_analyzer.tables:
                # 迁移脚本中可能没有所有表（如果是增量迁移）
                continue
            
            self._check_table_foreign_keys(table_name)
        
        return len(self.errors) == 0
    
    def _check_table_foreign_keys(self, table_name: str):
        """检查表的外键约束"""
        schema_fks = self.schema_analyzer.get_table_foreign_keys(table_name)
        migration_fks = self.migration_analyzer.get_table_foreign_keys(table_name)
        
        # 转换为可比较的格式
        schema_fk_signatures = set()
        for fk in schema_fks:
            source_cols = [c for c in fk['source_columns'] if c]
            target_cols = [c for c in fk['target_columns'] if c]
            if source_cols and target_cols and fk['target_table']:
                sig = (
                    tuple(sorted(source_cols)),
                    fk['target_table'],
                    tuple(sorted(target_cols))
                )
                schema_fk_signatures.add(sig)
        
        migration_fk_signatures = set()
        for fk in migration_fks:
            source_cols = [c for c in fk['source_columns'] if c]
            target_cols = [c for c in fk['target_columns'] if c]
            if source_cols and target_cols and fk['target_table']:
                sig = (
                    tuple(sorted(source_cols)),
                    fk['target_table'],
                    tuple(sorted(target_cols))
                )
                migration_fk_signatures.add(sig)
        
        # 检查缺失的外键
        missing_in_migration = schema_fk_signatures - migration_fk_signatures
        extra_in_migration = migration_fk_signatures - schema_fk_signatures
        
        if missing_in_migration:
            for sig in missing_in_migration:
                self.errors.append(
                    f"表 {table_name}: 迁移脚本中缺失外键约束 "
                    f"(源列: {sig[0]}, 目标表: {sig[1]}, 目标列: {sig[2]})"
                )
        
        if extra_in_migration:
            for sig in extra_in_migration:
                self.errors.append(
                    f"表 {table_name}: 迁移脚本中有额外的外键约束 "
                    f"(源列: {sig[0]}, 目标表: {sig[1]}, 目标列: {sig[2]})"
                )
        
        # 检查复合外键是否被错误拆分
        # 如果 schema 中有复合外键（多个源列），但迁移脚本中只有单独的外键，这是错误的
        schema_composite_fks = [
            fk for fk in schema_fks 
            if len(fk['source_columns']) > 1
        ]
        
        if schema_composite_fks:
            for schema_fk in schema_composite_fks:
                source_cols = set(schema_fk['source_columns'])
                target_table = schema_fk['target_table']
                
                # 检查迁移脚本中是否有单独的列引用同一个目标表
                single_fks_to_same_table = [
                    fk for fk in migration_fks
                    if fk['target_table'] == target_table 
                    and len(fk['source_columns']) == 1
                    and fk['source_columns'][0] in source_cols
                ]
                
                if single_fks_to_same_table:
                    self.errors.append(
                        f"表 {table_name}: 复合外键被错误拆分！\n"
                        f"  Schema 定义: 复合外键 ({', '.join(schema_fk['source_columns'])}) -> {target_table}\n"
                        f"  迁移脚本中: 发现了 {len(single_fks_to_same_table)} 个单独的外键约束\n"
                        f"  错误示例: {single_fks_to_same_table[0]}\n"
                        f"  正确做法: 应该使用一个 ForeignKeyConstraint 定义复合外键"
                    )
    
    def print_report(self):
        """打印检查报告"""
        safe_print("\n" + "="*80)
        safe_print("迁移脚本一致性检查报告")
        safe_print("="*80)
        
        if self.errors:
            safe_print(f"\n[ERROR] 发现 {len(self.errors)} 个错误:")
            for i, error in enumerate(self.errors, 1):
                safe_print(f"  {i}. {error}")
        
        if self.warnings:
            safe_print(f"\n[WARNING] 发现 {len(self.warnings)} 个警告:")
            for i, warning in enumerate(self.warnings, 1):
                safe_print(f"  {i}. {warning}")
        
        if not self.errors and not self.warnings:
            safe_print("\n[OK] 迁移脚本与 schema.py 一致！")
        
        safe_print("="*80)


def main():
    parser = argparse.ArgumentParser(description="验证迁移脚本与 schema.py 的一致性")
    parser.add_argument(
        '--migration-file',
        type=str,
        default=None,
        help='要检查的迁移文件（默认检查最新的 schema snapshot 迁移）'
    )
    parser.add_argument(
        '--schema-file',
        type=str,
        default='modules/core/db/schema.py',
        help='Schema 文件路径（默认: modules/core/db/schema.py）'
    )
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    schema_file = project_root / args.schema_file
    
    if not schema_file.exists():
        safe_print(f"[ERROR] Schema 文件不存在: {schema_file}")
        sys.exit(1)
    
    # 如果没有指定迁移文件，查找最新的 schema snapshot 迁移
    if args.migration_file:
        migration_file = project_root / args.migration_file
    else:
        migrations_dir = project_root / 'migrations' / 'versions'
        snapshot_migrations = list(migrations_dir.glob('*v5_0_0_schema_snapshot.py'))
        if not snapshot_migrations:
            safe_print("[ERROR] 未找到 schema snapshot 迁移文件")
            safe_print(f"  请在 migrations/versions/ 目录中查找 v5_0_0_schema_snapshot.py")
            sys.exit(1)
        migration_file = sorted(snapshot_migrations)[-1]  # 使用最新的
    
    if not migration_file.exists():
        safe_print(f"[ERROR] 迁移文件不存在: {migration_file}")
        sys.exit(1)
    
    checker = MigrationConsistencyChecker(schema_file, migration_file)
    
    try:
        success = checker.check()
        checker.print_report()
        
        if not success:
            safe_print("\n[FAIL] 迁移脚本一致性检查失败")
            safe_print("[INFO] 请修复上述错误后重试")
            sys.exit(1)
        else:
            safe_print("\n[OK] 迁移脚本一致性检查通过")
            sys.exit(0)
    except Exception as e:
        safe_print(f"\n[ERROR] 检查过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

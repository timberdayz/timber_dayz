#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查旧表脚本（Check Old Tables）

v4.17.0新增：
- 检查public schema中所有旧的fact_raw_data_*表
- 这些表应该被删除，因为现在使用b_class schema中的按平台分表

使用方法：
- python scripts/check_old_tables.py  # 只检查，不删除
- python scripts/check_old_tables.py --delete  # 实际删除（谨慎使用）
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from backend.models.database import SessionLocal

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_old_tables(delete: bool = False):
    """检查并可选删除旧表"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        
        # 查询public schema中所有表
        public_tables = inspector.get_table_names(schema='public')
        
        # 筛选出所有旧的fact_raw_data_*表（这些表应该被删除）
        old_tables = [
            t for t in public_tables 
            if t.startswith('fact_raw_data_')
        ]
        
        safe_print("="*60)
        safe_print("检查旧表（public schema中的fact_raw_data_*表）")
        safe_print("="*60)
        safe_print(f"\n发现 {len(old_tables)} 个旧表：\n")
        
        if not old_tables:
            safe_print("[OK] 没有发现旧表，数据库已清理")
            return
        
        # 显示每个表的信息
        for table_name in sorted(old_tables):
            try:
                # 查询表行数
                count = db.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar() or 0
                
                # 查询表大小
                size_query = text(f"""
                    SELECT pg_size_pretty(pg_total_relation_size('"{table_name}"'))
                """)
                size = db.execute(size_query).scalar() or "未知"
                
                safe_print(f"  - {table_name}: {count} 行, 大小: {size}")
            except Exception as e:
                safe_print(f"  - {table_name}: 查询失败 ({e})")
        
        safe_print(f"\n总计: {len(old_tables)} 个旧表需要清理")
        
        if delete:
            safe_print("\n" + "="*60)
            safe_print("开始删除旧表...")
            safe_print("="*60)
            
            deleted_count = 0
            failed_count = 0
            
            for table_name in old_tables:
                try:
                    # 删除表（CASCADE会自动删除依赖的索引、约束等）
                    db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
                    db.commit()
                    safe_print(f"  [OK] 删除表: {table_name}")
                    deleted_count += 1
                except Exception as e:
                    db.rollback()
                    safe_print(f"  [FAIL] 删除表失败: {table_name}, 错误: {e}")
                    failed_count += 1
            
            safe_print(f"\n删除完成: 成功 {deleted_count} 个, 失败 {failed_count} 个")
        else:
            safe_print("\n[提示] 这只是检查，未实际删除")
            safe_print("[提示] 要删除这些表，请使用: python scripts/check_old_tables.py --delete")
            safe_print("[警告] 删除前请确认这是开发环境，生产环境需要先备份数据！")
        
        # 对比b_class schema中的新表
        safe_print("\n" + "="*60)
        safe_print("对比b_class schema中的新表")
        safe_print("="*60)
        
        try:
            b_class_tables = inspector.get_table_names(schema='b_class')
            fact_tables = [t for t in b_class_tables if t.startswith('fact_')]
            safe_print(f"\nb_class schema中有 {len(fact_tables)} 个fact_开头的表")
            
            if fact_tables:
                safe_print("前10个表:")
                for table_name in sorted(fact_tables)[:10]:
                    try:
                        count = db.execute(
                            text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
                        ).scalar() or 0
                        safe_print(f"  - {table_name}: {count} 行")
                    except Exception as e:
                        safe_print(f"  - {table_name}: 查询失败")
        except Exception as e:
            safe_print(f"[WARNING] 查询b_class schema失败: {e}")
        
    except Exception as e:
        safe_print(f"[ERROR] 检查过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="检查旧表脚本")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="实际删除旧表（默认只检查，不删除）"
    )
    
    args = parser.parse_args()
    
    check_old_tables(delete=args.delete)


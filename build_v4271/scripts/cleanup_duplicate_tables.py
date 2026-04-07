#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
清理重复表脚本

用途：删除重复的表（保留正确 schema 中的表）

使用方法：
    python scripts/cleanup_duplicate_tables.py

作者: AI Agent
日期: 2026-01-30
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(project_root / ".env")


def safe_print(msg: str):
    """安全打印（避免 Windows 终端 Unicode 错误）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8"))


def main():
    safe_print("=" * 60)
    safe_print("清理重复表")
    safe_print("=" * 60)
    
    database_url = os.getenv("DATABASE_URL", "postgresql://erp_user:erp_password@localhost:15432/xihong_erp")
    
    try:
        import psycopg2
    except ImportError:
        safe_print("[FAIL] 缺少 psycopg2 库")
        return 1
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        cursor = conn.cursor()
        safe_print("[OK] 数据库连接成功")
    except Exception as e:
        safe_print(f"[FAIL] 数据库连接失败: {e}")
        return 1
    
    # 需要清理的重复表（删除的表，保留的表）
    cleanup_targets = [
        # (要删除的, 要保留的, 表名)
        ("core", "a_class", "target_breakdown"),
    ]
    
    for delete_schema, keep_schema, table_name in cleanup_targets:
        safe_print("")
        safe_print(f"--- 处理 {table_name} ---")
        
        # 检查要保留的表是否存在
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            )
        """, (keep_schema, table_name))
        keep_exists = cursor.fetchone()[0]
        
        if not keep_exists:
            safe_print(f"[WARN] {keep_schema}.{table_name} 不存在，跳过清理")
            continue
        
        # 检查要删除的表是否存在
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            )
        """, (delete_schema, table_name))
        delete_exists = cursor.fetchone()[0]
        
        if not delete_exists:
            safe_print(f"[INFO] {delete_schema}.{table_name} 不存在，无需清理")
            continue
        
        # 检查要删除的表中是否有数据
        cursor.execute(f'SELECT COUNT(*) FROM {delete_schema}."{table_name}"')
        count = cursor.fetchone()[0]
        
        if count > 0:
            safe_print(f"[WARN] {delete_schema}.{table_name} 有 {count} 条记录")
            safe_print(f"[WARN] 如果确定要删除，请手动执行: DROP TABLE {delete_schema}.{table_name}")
            continue
        
        # 删除空表
        try:
            cursor.execute(f'DROP TABLE IF EXISTS {delete_schema}."{table_name}" CASCADE')
            conn.commit()
            safe_print(f"[OK] 已删除 {delete_schema}.{table_name}")
        except Exception as e:
            conn.rollback()
            safe_print(f"[FAIL] 删除失败: {e}")
    
    cursor.close()
    conn.close()
    
    safe_print("")
    safe_print("=" * 60)
    safe_print("清理完成")
    safe_print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

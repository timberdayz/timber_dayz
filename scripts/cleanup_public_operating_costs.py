#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 public schema 下的 operating_costs 表

v4.21.0: 费用管理已迁移到 a_class.operating_costs 表(中文字段名)
此脚本用于删除 public schema 下的旧表，避免误用

执行前请确认:
1. 已迁移所有数据到 a_class.operating_costs
2. 已停止使用旧的 /api/config/operating-costs API
3. 已切换到新的 /api/expenses API
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / '.env')

from sqlalchemy import text, inspect
from backend.models.database import engine
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(msg: str):
    """安全打印(Windows编码兼容)"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'ignore').decode('ascii'))


def check_table_exists(conn, schema: str, table_name: str) -> bool:
    """检查表是否存在"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = :schema 
              AND table_name = :table_name
        )
    """), {"schema": schema, "table_name": table_name})
    return result.scalar()


def get_table_row_count(conn, schema: str, table_name: str) -> int:
    """获取表的行数"""
    try:
        if schema == "public":
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        else:
            result = conn.execute(text(f'SELECT COUNT(*) FROM {schema}."{table_name}"'))
        return result.scalar() or 0
    except Exception as e:
        logger.warning(f"无法获取表行数: {e}")
        return -1


def main():
    """主函数"""
    safe_print("=" * 60)
    safe_print("清理 public schema 下的 operating_costs 表")
    safe_print("=" * 60)
    
    with engine.connect() as conn:
        # 1. 检查 public.operating_costs 是否存在
        safe_print("\n[1/3] 检查 public.operating_costs 表...")
        public_exists = check_table_exists(conn, "public", "operating_costs")
        
        if not public_exists:
            safe_print("[OK] public.operating_costs 表不存在，无需清理")
            return
        
        safe_print("[WARNING] public.operating_costs 表存在")
        
        # 2. 检查数据量
        safe_print("\n[2/3] 检查数据量...")
        row_count = get_table_row_count(conn, "public", "operating_costs")
        if row_count > 0:
            safe_print(f"[WARNING] public.operating_costs 表中有 {row_count} 条数据")
            safe_print("[INFO] 请确认这些数据已迁移到 a_class.operating_costs")
            response = input("\n是否继续删除 public.operating_costs 表? (yes/no): ")
            if response.lower() != "yes":
                safe_print("[CANCELLED] 用户取消操作")
                return
        else:
            safe_print("[OK] public.operating_costs 表为空")
        
        # 3. 检查 a_class.operating_costs 是否存在
        safe_print("\n[3/3] 检查 a_class.operating_costs 表...")
        a_class_exists = check_table_exists(conn, "a_class", "operating_costs")
        
        if not a_class_exists:
            safe_print("[ERROR] a_class.operating_costs 表不存在!")
            safe_print("[ERROR] 请先确保 a_class.operating_costs 表已创建")
            return
        
        safe_print("[OK] a_class.operating_costs 表存在")
        
        # 4. 删除 public.operating_costs 表
        safe_print("\n[执行] 删除 public.operating_costs 表...")
        try:
            conn.execute(text('DROP TABLE IF EXISTS public.operating_costs CASCADE'))
            conn.commit()
            safe_print("[OK] public.operating_costs 表已删除")
        except Exception as e:
            conn.rollback()
            safe_print(f"[ERROR] 删除失败: {e}")
            logger.error(f"删除 public.operating_costs 失败: {e}", exc_info=True)
            return
    
    safe_print("\n" + "=" * 60)
    safe_print("[完成] 清理完成")
    safe_print("=" * 60)


if __name__ == "__main__":
    main()

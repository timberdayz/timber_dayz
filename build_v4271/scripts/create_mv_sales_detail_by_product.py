#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建mv_sales_detail_by_product物化视图脚本

用途：
- 创建以product_id为原子级的销售明细物化视图
- 类似华为ISRP系统的销售明细表结构

使用方法：
    python scripts/create_mv_sales_detail_by_product.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.models.database import get_db
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows兼容的安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def create_mv_sales_detail_by_product(db: Session) -> bool:
    """
    创建mv_sales_detail_by_product物化视图
    
    Args:
        db: 数据库会话
    
    Returns:
        是否创建成功
    """
    try:
        safe_print("=" * 70)
        safe_print("创建mv_sales_detail_by_product物化视图")
        safe_print("=" * 70)
        
        # 读取SQL文件
        sql_file = project_root / "sql" / "materialized_views" / "create_mv_sales_detail_by_product.sql"
        
        if not sql_file.exists():
            safe_print(f"[ERROR] SQL文件不存在: {sql_file}")
            return False
        
        safe_print(f"\n[1] 读取SQL文件: {sql_file}")
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割SQL语句（按分号分割，但保留函数定义）
        # 简单处理：按行分割，但合并函数定义
        statements = []
        current_statement = []
        in_function = False
        
        for line in sql_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            
            current_statement.append(line)
            
            # 检测函数开始
            if 'CREATE OR REPLACE FUNCTION' in line.upper():
                in_function = True
            
            # 检测函数结束
            if in_function and line.endswith('$$;'):
                statements.append('\n'.join(current_statement))
                current_statement = []
                in_function = False
            elif not in_function and line.endswith(';'):
                statements.append('\n'.join(current_statement))
                current_statement = []
        
        # 执行SQL语句
        safe_print(f"\n[2] 执行SQL语句（共{len(statements)}条）...")
        
        for i, statement in enumerate(statements, 1):
            try:
                safe_print(f"\n  执行第 {i}/{len(statements)} 条语句...")
                db.execute(text(statement))
                db.commit()
                safe_print(f"  [OK] 执行成功")
            except Exception as e:
                db.rollback()
                # 如果是"已存在"错误，可以忽略
                if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                    safe_print(f"  [WARN] 已存在，跳过: {str(e)[:100]}")
                else:
                    safe_print(f"  [ERROR] 执行失败: {e}")
                    logger.error(f"执行SQL失败: {statement[:200]}...", exc_info=True)
                    return False
        
        # 验证视图是否创建成功
        safe_print("\n[3] 验证视图是否创建成功...")
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM pg_matviews 
            WHERE matviewname = 'mv_sales_detail_by_product'
        """)).scalar()
        
        if result > 0:
            # 获取行数
            row_count = db.execute(text("SELECT COUNT(*) FROM mv_sales_detail_by_product")).scalar()
            safe_print(f"  [OK] 视图创建成功，当前行数: {row_count}")
            return True
        else:
            safe_print("  [ERROR] 视图创建失败，未找到视图")
            return False
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 创建物化视图失败: {e}")
        logger.error("创建mv_sales_detail_by_product失败", exc_info=True)
        return False


def main():
    """主函数"""
    db = next(get_db())
    try:
        success = create_mv_sales_detail_by_product(db)
        if success:
            safe_print("\n" + "=" * 70)
            safe_print("[OK] 物化视图创建完成")
            safe_print("=" * 70)
            return 0
        else:
            safe_print("\n" + "=" * 70)
            safe_print("[ERROR] 物化视图创建失败")
            safe_print("=" * 70)
            return 1
    except Exception as e:
        safe_print(f"\n[ERROR] 执行失败: {e}")
        logger.error("执行失败", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())


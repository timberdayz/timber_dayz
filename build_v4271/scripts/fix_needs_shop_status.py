#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复needs_shop状态脚本

功能：
- 将订单和库存数据域中状态为needs_shop的文件更新为pending
- 因为这些数据域不需要文件级shop_id（全量导出，shop_id从数据行提取或不需要）

注意：
- 本脚本连接Docker PostgreSQL数据库
- 默认dry-run模式，只显示将要更新的文件
- 使用--execute参数才会实际执行更新
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.models.database import engine, SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def fix_needs_shop_status(dry_run: bool = True):
    """修复needs_shop状态"""
    db = SessionLocal()
    
    try:
        # 查询需要修复的文件
        query = text("""
            SELECT id, file_name, platform_code, data_domain, granularity, status, shop_id
            FROM catalog_files
            WHERE status = 'needs_shop'
            AND data_domain IN ('orders', 'inventory')
            ORDER BY first_seen_at DESC
        """)
        
        result = db.execute(query)
        files_to_fix = result.fetchall()
        
        if not files_to_fix:
            print("\n[信息] 没有需要修复的文件")
            return
        
        print(f"\n[发现] 找到 {len(files_to_fix)} 个需要修复的文件")
        print("-" * 80)
        print(f"{'ID':<8} {'文件名':<50} {'平台':<10} {'数据域':<10} {'状态':<12}")
        print("-" * 80)
        
        for row in files_to_fix[:20]:  # 只显示前20个
            print(f"{row[0]:<8} {row[1][:48]:<50} {row[2] or 'N/A':<10} {row[3] or 'N/A':<10} {row[5]:<12}")
        
        if len(files_to_fix) > 20:
            print(f"... 还有 {len(files_to_fix) - 20} 个文件")
        
        if dry_run:
            print("\n[DRY-RUN] 预览模式，不会实际更新")
            print(f"如果执行，将更新 {len(files_to_fix)} 个文件的状态：needs_shop -> pending")
        else:
            # 执行更新
            update_query = text("""
                UPDATE catalog_files
                SET status = 'pending'
                WHERE status = 'needs_shop'
                AND data_domain IN ('orders', 'inventory')
            """)
            
            result = db.execute(update_query)
            db.commit()
            
            updated_count = result.rowcount
            print(f"\n[成功] 已更新 {updated_count} 个文件的状态：needs_shop -> pending")
            
    except Exception as e:
        db.rollback()
        logger.error(f"修复needs_shop状态失败: {e}", exc_info=True)
        print(f"\n[错误] 修复失败: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="修复needs_shop状态脚本")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行更新（默认是dry-run模式）"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("修复needs_shop状态脚本")
    print("=" * 80)
    print(f"模式: {'执行模式' if args.execute else '预览模式 (dry-run)'}")
    print(f"目标: 订单和库存数据域中状态为needs_shop的文件")
    
    fix_needs_shop_status(dry_run=not args.execute)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复services数据域的sub_domain

功能：
- 将所有平台的services数据域中sub_domain为空的文件更新为'agent'
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
from backend.models.database import SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def fix_services_sub_domain(dry_run: bool = True):
    """修复services数据域的sub_domain"""
    db = SessionLocal()
    
    try:
        # 查询需要修复的文件
        query = text("""
            SELECT id, file_name, platform_code, data_domain, granularity, sub_domain, status
            FROM catalog_files
            WHERE data_domain = 'services'
            AND (sub_domain IS NULL OR sub_domain = '')
            ORDER BY platform_code, first_seen_at DESC
        """)
        
        result = db.execute(query)
        files_to_fix = result.fetchall()
        
        if not files_to_fix:
            print("\n[信息] 没有需要修复的文件")
            return
        
        print(f"\n[发现] 找到 {len(files_to_fix)} 个需要修复的文件")
        print("-" * 100)
        print(f"{'ID':<8} {'文件名':<50} {'平台':<10} {'数据域':<10} {'粒度':<10} {'当前sub_domain':<15} {'状态':<12}")
        print("-" * 100)
        
        # 按平台分组统计
        platform_counts = {}
        for row in files_to_fix:
            platform = row[2] or 'unknown'
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        print("\n按平台统计：")
        for platform, count in sorted(platform_counts.items()):
            print(f"  {platform}: {count} 个文件")
        
        print("\n前20个文件详情：")
        for row in files_to_fix[:20]:
            print(f"{row[0]:<8} {row[1][:48]:<50} {row[2] or 'N/A':<10} {row[3] or 'N/A':<10} {row[4] or 'N/A':<10} {row[5] or '(空)':<15} {row[6] or 'N/A':<12}")
        
        if len(files_to_fix) > 20:
            print(f"... 还有 {len(files_to_fix) - 20} 个文件")
        
        if dry_run:
            print("\n[DRY-RUN] 预览模式，不会实际更新")
            print(f"如果执行，将更新 {len(files_to_fix)} 个文件的sub_domain: (空) -> 'agent'")
        else:
            # 执行更新
            update_query = text("""
                UPDATE catalog_files
                SET sub_domain = 'agent'
                WHERE data_domain = 'services'
                AND (sub_domain IS NULL OR sub_domain = '')
            """)
            
            result = db.execute(update_query)
            db.commit()
            
            updated_count = result.rowcount
            print(f"\n[成功] 已更新 {updated_count} 个文件的sub_domain: (空) -> 'agent'")
            
            # 显示按平台统计
            print("\n按平台统计更新后的文件数量：")
            stats_query = text("""
                SELECT platform_code, COUNT(*) as count
                FROM catalog_files
                WHERE data_domain = 'services'
                AND sub_domain = 'agent'
                GROUP BY platform_code
                ORDER BY platform_code
            """)
            stats_result = db.execute(stats_query)
            for row in stats_result:
                print(f"  {row[0] or 'unknown'}: {row[1]} 个文件")
            
    except Exception as e:
        db.rollback()
        logger.error(f"修复services sub_domain失败: {e}", exc_info=True)
        print(f"\n[错误] 修复失败: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="修复services数据域的sub_domain")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行更新（默认是dry-run模式）"
    )
    
    args = parser.parse_args()
    
    print("=" * 100)
    print("修复services数据域的sub_domain")
    print("=" * 100)
    print(f"模式: {'执行模式' if args.execute else '预览模式 (dry-run)'}")
    print(f"目标: 所有平台的services数据域中sub_domain为空的文件")
    print(f"操作: 将sub_domain设置为'agent'（人工服务）")
    
    fix_services_sub_domain(dry_run=not args.execute)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


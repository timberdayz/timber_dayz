#!/usr/bin/env python3
"""验证catalog_files表内容"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # 统计总数
        result = conn.execute(text("SELECT COUNT(*) FROM catalog_files"))
        total = result.fetchone()[0]
        print(f"\n总文件数: {total}")
        
        # 按source_platform分组
        result = conn.execute(text("""
            SELECT source_platform, COUNT(*) as count
            FROM catalog_files
            GROUP BY source_platform
            ORDER BY count DESC
        """))
        print("\n按数据来源平台分组:")
        for row in result:
            print(f"  {row[0]}: {row[1]}个文件")
        
        # 按data_domain分组
        result = conn.execute(text("""
            SELECT data_domain, COUNT(*) as count
            FROM catalog_files
            GROUP BY data_domain
            ORDER BY count DESC
        """))
        print("\n按数据域分组:")
        for row in result:
            print(f"  {row[0]}: {row[1]}个文件")
        
        # 按sub_domain分组（非空）
        result = conn.execute(text("""
            SELECT sub_domain, COUNT(*) as count
            FROM catalog_files
            WHERE sub_domain IS NOT NULL AND sub_domain != ''
            GROUP BY sub_domain
            ORDER BY count DESC
        """))
        print("\n子数据域分布:")
        for row in result:
            print(f"  {row[0]}: {row[1]}个文件")
        
        # 质量评分统计
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                AVG(quality_score) as avg_score,
                MIN(quality_score) as min_score,
                MAX(quality_score) as max_score
            FROM catalog_files
            WHERE quality_score IS NOT NULL
        """))
        row = result.fetchone()
        print(f"\n质量评分统计:")
        print(f"  有评分的文件: {row[0]}个")
        print(f"  平均分: {row[1]:.2f}" if row[1] else "  平均分: N/A")
        print(f"  最低分: {row[2]:.2f}" if row[2] else "  最低分: N/A")
        print(f"  最高分: {row[3]:.2f}" if row[3] else "  最高分: N/A")
        
        # 示例记录
        result = conn.execute(text("""
            SELECT file_name, source_platform, data_domain, sub_domain, quality_score
            FROM catalog_files
            LIMIT 10
        """))
        print("\n示例记录（前10个）:")
        for row in result:
            sub = f", sub={row[3]}" if row[3] else ""
            score = f", 质量={row[4]:.1f}" if row[4] else ""
            print(f"  {row[0][:50]} | {row[1]}/{row[2]}{sub}{score}")


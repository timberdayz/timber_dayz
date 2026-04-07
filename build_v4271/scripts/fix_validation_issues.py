#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复数据库设计规范验证发现的问题

⭐ v4.12.0新增：根据验证报告修复警告级别问题

修复策略：
1. 物化视图唯一索引（优先级高）
2. 关键业务表的字段NULL问题（优先级中）
3. Staging表允许NULL（合理，不修复）
"""

import sys
import json
from pathlib import Path
from sqlalchemy import text

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from modules.core.logger import get_logger

logger = get_logger(__name__)


def fix_materialized_view_indexes(db):
    """修复物化视图唯一索引问题"""
    print("\n[1] 修复物化视图唯一索引...")
    
    # 检查哪些主视图缺少唯一索引
    main_views = {
        'mv_product_management': ['platform_code', 'shop_id', 'platform_sku', 'metric_date'],
        'mv_order_summary': ['platform_code', 'shop_id', 'order_id'],
        'mv_traffic_summary': ['platform_code', 'shop_id', 'traffic_date', 'granularity'],
        'mv_inventory_summary': ['platform_code', 'shop_id', 'platform_sku', 'snapshot_date'],
        'mv_financial_overview': ['platform_code', 'shop_id', 'period_start', 'period_type'],
    }
    
    fixed_count = 0
    
    for view_name, unique_columns in main_views.items():
        try:
            # 检查视图是否存在
            result = db.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM pg_matviews 
                    WHERE schemaname = 'public' AND matviewname = :view_name
                )
            """), {"view_name": view_name})
            
            if not result.scalar():
                print(f"   [SKIP] {view_name} 不存在，跳过")
                continue
            
            # 检查是否已有唯一索引
            result = db.execute(text(f"""
                SELECT COUNT(*) FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = :view_name 
                AND indexdef LIKE '%UNIQUE%'
            """), {"view_name": view_name})
            
            if result.scalar() > 0:
                print(f"   [OK] {view_name} 已有唯一索引")
                continue
            
            # 创建唯一索引
            index_name = f"idx_{view_name}_unique"
            columns_str = ', '.join(unique_columns)
            
            print(f"   [FIX] 为 {view_name} 创建唯一索引...")
            db.execute(text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
                ON {view_name} ({columns_str})
            """))
            db.commit()
            
            print(f"   [OK] {view_name} 唯一索引创建成功")
            fixed_count += 1
            
        except Exception as e:
            logger.error(f"修复 {view_name} 唯一索引失败: {e}")
            db.rollback()
            print(f"   [ERROR] {view_name} 唯一索引创建失败: {e}")
    
    print(f"\n[完成] 修复了 {fixed_count} 个物化视图的唯一索引")
    return fixed_count


def analyze_nullable_issues():
    """分析字段NULL问题，确定哪些需要修复"""
    print("\n[2] 分析字段NULL问题...")
    
    # 读取验证报告
    report_file = Path("temp/outputs/database_design_validation_report_20251120_181038.json")
    if not report_file.exists():
        print("   [ERROR] 验证报告不存在，请先运行验证工具")
        return
    
    with open(report_file, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # 筛选nullable警告
    nullable_warnings = [
        issue for issue in report['issues']
        if issue['severity'] == 'warning' and issue['category'] == 'nullable'
    ]
    
    print(f"   发现 {len(nullable_warnings)} 个字段NULL警告")
    
    # 分类：哪些表需要修复，哪些表允许NULL是合理的
    staging_tables = {'staging_orders', 'staging_product_metrics', 'staging_inventory'}
    fact_tables = {'fact_orders', 'fact_order_items', 'fact_product_metrics'}
    
    need_fix = []
    reasonable_null = []
    
    for issue in nullable_warnings:
        table_name = issue['table_name']
        field_name = issue['field_name']
        
        # Staging表允许NULL是合理的（数据可能不完整）
        if table_name in staging_tables:
            reasonable_null.append(issue)
            continue
        
        # 关键业务标识字段应该NOT NULL
        if field_name in ['platform_code', 'shop_id', 'order_id', 'platform_sku']:
            if table_name not in staging_tables:
                need_fix.append(issue)
            else:
                reasonable_null.append(issue)
        
        # 金额字段应该NOT NULL
        elif any(keyword in field_name.lower() for keyword in ['price', 'amount', 'quantity', 'cost']):
            if table_name in fact_tables:
                need_fix.append(issue)
            else:
                reasonable_null.append(issue)
        else:
            reasonable_null.append(issue)
    
    print(f"\n   需要修复: {len(need_fix)} 个")
    print(f"   合理NULL: {len(reasonable_null)} 个")
    
    # 显示需要修复的问题
    if need_fix:
        print("\n   需要修复的问题:")
        for issue in need_fix[:10]:  # 只显示前10个
            print(f"     - {issue['table_name']}.{issue['field_name']}: {issue['issue']}")
        if len(need_fix) > 10:
            print(f"     ... 还有 {len(need_fix) - 10} 个问题")
    
    return need_fix


def main():
    """主函数"""
    print("=" * 70)
    print("修复数据库设计规范验证发现的问题")
    print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 1. 修复物化视图唯一索引
        fixed_mv_count = fix_materialized_view_indexes(db)
        
        # 2. 分析字段NULL问题
        need_fix = analyze_nullable_issues()
        
        print("\n" + "=" * 70)
        print("修复总结")
        print("=" * 70)
        print(f"[OK] 修复物化视图唯一索引: {fixed_mv_count} 个")
        print(f"[INFO] 需要修复的字段NULL问题: {len(need_fix) if need_fix else 0} 个")
        print("\n提示: 字段NULL问题需要创建Alembic迁移脚本，请根据分析结果手动创建迁移")
        
    except Exception as e:
        logger.error(f"修复过程出错: {e}", exc_info=True)
        print(f"\n[ERROR] 修复失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()


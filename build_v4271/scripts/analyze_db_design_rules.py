#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库设计规则审查脚本

分析shop_id主键约束与数据源不匹配的问题，以及事实表和物化视图与源数据不匹配的问题。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, func
from sqlalchemy.orm import sessionmaker
from modules.core.db import CatalogFile, FactOrder, FactProductMetric, StagingOrders, StagingProductMetrics
from modules.core.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)

def safe_print(text_str):
    """安全打印（处理Windows编码问题）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))

def analyze_shop_id_issues(db):
    """分析shop_id主键约束与数据源不匹配的问题"""
    safe_print("\n" + "="*80)
    safe_print("1. shop_id主键约束与数据源不匹配问题分析")
    safe_print("="*80)
    
    # 1.1 统计catalog_files表中shop_id的情况
    safe_print("\n1.1 catalog_files表中shop_id统计：")
    
    total_files = db.query(func.count(CatalogFile.id)).scalar()
    files_with_shop_id = db.query(func.count(CatalogFile.id)).filter(
        CatalogFile.shop_id.isnot(None),
        CatalogFile.shop_id != ''
    ).scalar()
    files_without_shop_id = total_files - files_with_shop_id
    files_needs_shop = db.query(func.count(CatalogFile.id)).filter(
        CatalogFile.status == 'needs_shop'
    ).scalar()
    
    safe_print(f"  总文件数: {total_files}")
    safe_print(f"  有shop_id的文件数: {files_with_shop_id} ({files_with_shop_id/total_files*100:.1f}%)" if total_files > 0 else "  有shop_id的文件数: 0")
    safe_print(f"  没有shop_id的文件数: {files_without_shop_id} ({files_without_shop_id/total_files*100:.1f}%)" if total_files > 0 else "  没有shop_id的文件数: 0")
    safe_print(f"  需要手动指派shop_id的文件数 (status='needs_shop'): {files_needs_shop}")
    
    # 1.2 按数据域统计shop_id缺失情况
    safe_print("\n1.2 按数据域统计shop_id缺失情况：")
    
    domain_stats = db.execute(text("""
        SELECT 
            COALESCE(data_domain, 'unknown') as domain,
            COUNT(*) as total,
            COUNT(CASE WHEN shop_id IS NOT NULL AND shop_id != '' THEN 1 END) as with_shop_id,
            COUNT(CASE WHEN shop_id IS NULL OR shop_id = '' THEN 1 END) as without_shop_id,
            COUNT(CASE WHEN status = 'needs_shop' THEN 1 END) as needs_shop
        FROM catalog_files
        GROUP BY data_domain
        ORDER BY total DESC
    """)).fetchall()
    
    for domain, total, with_shop, without_shop, needs_shop in domain_stats:
        safe_print(f"  {domain}:")
        safe_print(f"    总文件数: {total}")
        safe_print(f"    有shop_id: {with_shop} ({with_shop/total*100:.1f}%)" if total > 0 else "    有shop_id: 0")
        safe_print(f"    无shop_id: {without_shop} ({without_shop/total*100:.1f}%)" if total > 0 else "    无shop_id: 0")
        safe_print(f"    需要指派: {needs_shop}")
    
    # 1.3 分析FactOrder表中shop_id的情况
    safe_print("\n1.3 FactOrder表中shop_id统计：")
    
    fact_order_total = db.query(func.count(FactOrder.order_id)).scalar()
    fact_order_with_shop_id = db.execute(text("""
        SELECT COUNT(*) 
        FROM fact_orders 
        WHERE shop_id IS NOT NULL AND shop_id != ''
    """)).scalar()
    fact_order_without_shop_id = fact_order_total - fact_order_with_shop_id
    
    safe_print(f"  总订单数: {fact_order_total}")
    safe_print(f"  有shop_id的订单数: {fact_order_with_shop_id} ({fact_order_with_shop_id/fact_order_total*100:.1f}%)" if fact_order_total > 0 else "  有shop_id的订单数: 0")
    safe_print(f"  没有shop_id的订单数: {fact_order_without_shop_id} ({fact_order_without_shop_id/fact_order_total*100:.1f}%)" if fact_order_total > 0 else "  没有shop_id的订单数: 0")
    
    # 注意：FactOrder的主键是(platform_code, shop_id, order_id)，shop_id是主键的一部分，理论上不应该有NULL
    # 但实际上可能有空字符串的情况
    
    # 1.4 分析StagingOrders表中shop_id的情况
    safe_print("\n1.4 StagingOrders表中shop_id统计：")
    
    staging_total = db.query(func.count(StagingOrders.id)).scalar()
    staging_with_shop_id = db.query(func.count(StagingOrders.id)).filter(
        StagingOrders.shop_id.isnot(None),
        StagingOrders.shop_id != ''
    ).scalar()
    staging_without_shop_id = staging_total - staging_with_shop_id
    
    safe_print(f"  总staging记录数: {staging_total}")
    safe_print(f"  有shop_id的记录数: {staging_with_shop_id} ({staging_with_shop_id/staging_total*100:.1f}%)" if staging_total > 0 else "  有shop_id的记录数: 0")
    safe_print(f"  没有shop_id的记录数: {staging_without_shop_id} ({staging_without_shop_id/staging_total*100:.1f}%)" if staging_total > 0 else "  没有shop_id的记录数: 0")
    
    return {
        'catalog_files': {
            'total': total_files,
            'with_shop_id': files_with_shop_id,
            'without_shop_id': files_without_shop_id,
            'needs_shop': files_needs_shop
        },
        'fact_orders': {
            'total': fact_order_total,
            'with_shop_id': fact_order_with_shop_id,
            'without_shop_id': fact_order_without_shop_id
        },
        'staging_orders': {
            'total': staging_total,
            'with_shop_id': staging_with_shop_id,
            'without_shop_id': staging_without_shop_id
        },
        'by_domain': [
            {
                'domain': domain,
                'total': total,
                'with_shop_id': with_shop,
                'without_shop_id': without_shop,
                'needs_shop': needs_shop
            }
            for domain, total, with_shop, without_shop, needs_shop in domain_stats
        ]
    }

def analyze_fact_table_structure(db):
    """分析事实表结构与源数据不匹配的问题"""
    safe_print("\n" + "="*80)
    safe_print("2. 事实表结构与源数据不匹配问题分析")
    safe_print("="*80)
    
    # 2.1 分析FactOrder表结构
    safe_print("\n2.1 FactOrder表结构分析：")
    safe_print("  主键: (platform_code, shop_id, order_id)")
    safe_print("  问题: shop_id是主键的一部分，不能为NULL，但源数据可能没有shop_id")
    
    # 2.2 分析FactProductMetric表结构
    safe_print("\n2.2 FactProductMetric表结构分析：")
    safe_print("  主键: id (自增)")
    safe_print("  唯一索引: (platform_code, shop_id, platform_sku, metric_date)")
    safe_print("  注意: v4.10.0更新后，platform_code和shop_id允许NULL（支持inventory域）")
    
    # 2.3 检查是否有数据因为shop_id缺失而无法入库
    safe_print("\n2.3 检查数据丢失情况：")
    
    # 统计staging中有但fact中没有的数据（可能因为shop_id缺失）
    staging_without_fact = db.execute(text("""
        SELECT COUNT(DISTINCT so.order_id)
        FROM staging_orders so
        LEFT JOIN fact_orders fo ON (
            so.platform_code = fo.platform_code 
            AND so.shop_id = fo.shop_id 
            AND so.order_id = fo.order_id
        )
        WHERE fo.order_id IS NULL
        AND so.shop_id IS NOT NULL 
        AND so.shop_id != ''
    """)).scalar()
    
    safe_print(f"  Staging中有但Fact中没有的订单数（shop_id不为空）: {staging_without_fact}")
    
    # 统计staging中shop_id为空的记录数
    staging_null_shop_id = db.query(func.count(StagingOrders.id)).filter(
        (StagingOrders.shop_id.is_(None)) | (StagingOrders.shop_id == '')
    ).scalar()
    
    safe_print(f"  Staging中shop_id为空的记录数: {staging_null_shop_id}")
    
    return {
        'staging_without_fact': staging_without_fact,
        'staging_null_shop_id': staging_null_shop_id
    }

def analyze_materialized_view_structure(db):
    """分析物化视图结构与字段映射输出不匹配的问题"""
    safe_print("\n" + "="*80)
    safe_print("3. 物化视图结构与字段映射输出不匹配问题分析")
    safe_print("="*80)
    
    # 检查物化视图是否存在
    mv_list = db.execute(text("""
        SELECT schemaname, matviewname 
        FROM pg_matviews 
        WHERE schemaname = 'public'
        ORDER BY matviewname
    """)).fetchall()
    
    safe_print(f"\n3.1 现有物化视图列表（共{len(mv_list)}个）：")
    for schema, name in mv_list:
        safe_print(f"  - {name}")
    
    # 分析主要物化视图的结构
    if mv_list:
        safe_print("\n3.2 主要物化视图结构分析：")
        safe_print("  注意: 需要检查物化视图的字段是否与字段映射输出匹配")
        safe_print("  建议: 对比字段映射辞典和物化视图字段，识别不匹配的字段")
    
    return {
        'materialized_views': [name for _, name in mv_list]
    }

def generate_recommendations(shop_id_stats, fact_stats, mv_stats):
    """生成数据库设计规则优化建议"""
    safe_print("\n" + "="*80)
    safe_print("4. 数据库设计规则优化建议")
    safe_print("="*80)
    
    recommendations = []
    
    # 4.1 shop_id主键约束问题
    safe_print("\n4.1 shop_id主键约束问题：")
    
    catalog_files = shop_id_stats['catalog_files']
    if catalog_files['without_shop_id'] > 0:
        missing_rate = catalog_files['without_shop_id'] / catalog_files['total'] * 100 if catalog_files['total'] > 0 else 0
        safe_print(f"  问题: {catalog_files['without_shop_id']}个文件（{missing_rate:.1f}%）没有shop_id")
        
        if missing_rate > 10:
            recommendations.append({
                'issue': 'shop_id主键约束与数据源不匹配',
                'severity': 'high',
                'description': f'{missing_rate:.1f}%的文件没有shop_id，但FactOrder要求shop_id作为主键的一部分',
                'recommendation': '考虑允许shop_id为NULL（对于平台级数据），或使用account_id替代shop_id'
            })
            safe_print(f"  建议: 考虑允许shop_id为NULL（对于平台级数据），或使用account_id替代shop_id")
        else:
            recommendations.append({
                'issue': 'shop_id主键约束与数据源不匹配',
                'severity': 'medium',
                'description': f'{missing_rate:.1f}%的文件没有shop_id',
                'recommendation': '继续使用shop_id解析机制，但需要改进解析准确率'
            })
            safe_print(f"  建议: 继续使用shop_id解析机制，但需要改进解析准确率")
    
    # 4.2 事实表结构问题
    safe_print("\n4.2 事实表结构问题：")
    
    if fact_stats['staging_null_shop_id'] > 0:
        recommendations.append({
            'issue': 'Staging中有shop_id为空的记录',
            'severity': 'high',
            'description': f'{fact_stats["staging_null_shop_id"]}条staging记录shop_id为空，无法入库到FactOrder',
            'recommendation': '增强shop_id获取逻辑，确保所有数据都有shop_id'
        })
        safe_print(f"  问题: {fact_stats['staging_null_shop_id']}条staging记录shop_id为空，无法入库到FactOrder")
        safe_print(f"  建议: 增强shop_id获取逻辑，确保所有数据都有shop_id")
    
    # 4.3 物化视图问题
    safe_print("\n4.3 物化视图问题：")
    safe_print("  建议: 需要人工审查物化视图字段与字段映射输出的匹配情况")
    
    return recommendations

def main():
    """主函数"""
    try:
        from backend.models.database import get_db
        db = next(get_db())
        
        safe_print("="*80)
        safe_print("数据库设计规则审查报告")
        safe_print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        safe_print("="*80)
        
        # 1. 分析shop_id问题
        shop_id_stats = analyze_shop_id_issues(db)
        
        # 2. 分析事实表结构问题
        fact_stats = analyze_fact_table_structure(db)
        
        # 3. 分析物化视图问题
        mv_stats = analyze_materialized_view_structure(db)
        
        # 4. 生成优化建议
        recommendations = generate_recommendations(shop_id_stats, fact_stats, mv_stats)
        
        # 5. 总结
        safe_print("\n" + "="*80)
        safe_print("5. 总结")
        safe_print("="*80)
        safe_print(f"  发现的问题数: {len(recommendations)}")
        safe_print(f"  高优先级问题: {len([r for r in recommendations if r['severity'] == 'high'])}")
        safe_print(f"  中优先级问题: {len([r for r in recommendations if r['severity'] == 'medium'])}")
        
        safe_print("\n详细建议已生成，请查看上面的分析结果。")
        
        db.close()
        
    except Exception as e:
        logger.error(f"分析失败: {e}", exc_info=True)
        safe_print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()


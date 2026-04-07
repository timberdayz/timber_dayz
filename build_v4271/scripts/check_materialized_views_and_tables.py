#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查物化视图和数据库表的完整性和使用情况

用于回答：
1. 物化视图是否符合要求，有没有多余和无用的
2. 数据库表是否有冗余
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import engine, SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_materialized_views(db):
    """检查物化视图"""
    logger.info("=" * 70)
    logger.info("检查物化视图")
    logger.info("=" * 70)
    
    # 查询所有物化视图
    result = db.execute(text("""
        SELECT 
            matviewname,
            pg_size_pretty(pg_total_relation_size('public.' || matviewname)) as size,
            (SELECT COUNT(*) FROM pg_indexes WHERE tablename = matviewname) as index_count
        FROM pg_matviews 
        WHERE schemaname = 'public'
        ORDER BY matviewname
    """))
    
    views = []
    for row in result:
        views.append({
            'name': row[0],
            'size': row[1],
            'index_count': row[2]
        })
    
    logger.info(f"\n找到 {len(views)} 个物化视图：")
    logger.info("-" * 70)
    
    # 预期的物化视图列表（根据代码和文档）
    expected_views = {
        # 产品域（5个）
        'mv_product_management': '产品管理核心视图',
        'mv_product_sales_trend': '产品销售趋势',
        'mv_product_topn_day': 'TopN日排行',
        'mv_shop_product_summary': '店铺产品汇总',
        'mv_top_products': '顶级产品',
        
        # 销售域（5个）
        'mv_daily_sales': '日销售',
        'mv_weekly_sales': '周销售',
        'mv_monthly_sales': '月销售',
        'mv_order_sales_summary': '订单销售汇总',
        'mv_sales_day_shop_sku': '日度销售SKU汇总',
        
        # 财务域（3个）
        'mv_financial_overview': '财务总览',
        'mv_pnl_shop_month': '店铺P&L',
        'mv_profit_analysis': '利润分析',
        'mv_vendor_performance': '供应商绩效',
        
        # 库存域（3个）
        'mv_inventory_summary': '库存汇总',
        'mv_inventory_by_sku': 'SKU级库存',
        'mv_inventory_age_day': '库存账龄',
        
        # 流量域（1个）
        'mv_shop_traffic_day': '店铺流量',
        
        # C类数据域（2个）- v4.11.2新增
        'mv_shop_daily_performance': '店铺日度表现',
        'mv_shop_health_summary': '店铺健康度汇总',
    }
    
    found_views = set()
    missing_views = []
    extra_views = []
    
    for view in views:
        view_name = view['name']
        found_views.add(view_name)
        
        if view_name in expected_views:
            logger.info(f"  [OK] {view_name:35} - {expected_views[view_name]:20} ({view['size']}, {view['index_count']}索引)")
        else:
            logger.warning(f"  [EXTRA] {view_name:35} - 未在预期列表中 ({view['size']}, {view['index_count']}索引)")
            extra_views.append(view_name)
    
    for view_name, description in expected_views.items():
        if view_name not in found_views:
            logger.warning(f"  [MISSING] {view_name:35} - {description:20} (预期存在但未找到)")
            missing_views.append(view_name)
    
    logger.info("-" * 70)
    logger.info(f"总计: {len(views)} 个视图")
    logger.info(f"预期: {len(expected_views)} 个视图")
    logger.info(f"缺失: {len(missing_views)} 个视图")
    logger.info(f"多余: {len(extra_views)} 个视图")
    
    return {
        'total': len(views),
        'expected': len(expected_views),
        'missing': missing_views,
        'extra': extra_views,
        'views': views
    }


def check_tables(db):
    """检查数据库表"""
    logger.info("\n" + "=" * 70)
    logger.info("检查数据库表（统计）")
    logger.info("=" * 70)
    
    # 查询所有表
    result = db.execute(text("""
        SELECT 
            tablename,
            pg_size_pretty(pg_total_relation_size('public.' || tablename)) as size,
            (SELECT COUNT(*) FROM pg_indexes WHERE tablename = tablename) as index_count
        FROM pg_tables 
        WHERE schemaname = 'public'
        AND tablename NOT LIKE 'pg_%'
        AND tablename NOT LIKE 'sql_%'
        ORDER BY tablename
    """))
    
    tables = []
    for row in result:
        tables.append({
            'name': row[0],
            'size': row[1],
            'index_count': row[2]
        })
    
    logger.info(f"\n找到 {len(tables)} 张表")
    logger.info("-" * 70)
    
    # 按类型分类
    dim_tables = [t for t in tables if t['name'].startswith('dim_')]
    fact_tables = [t for t in tables if t['name'].startswith('fact_')]
    catalog_tables = [t for t in tables if 'catalog' in t['name'] or 'file' in t['name']]
    mapping_tables = [t for t in tables if 'mapping' in t['name'] or 'dictionary' in t['name'] or 'template' in t['name']]
    sales_tables = [t for t in tables if 'sales' in t['name'] or 'campaign' in t['name'] or 'target' in t['name']]
    shop_tables = [t for t in tables if 'shop' in t['name'] and 'dim_' not in t['name']]
    performance_tables = [t for t in tables if 'performance' in t['name'] or 'clearance' in t['name']]
    other_tables = [t for t in tables if not any([
        t['name'].startswith('dim_'),
        t['name'].startswith('fact_'),
        'catalog' in t['name'],
        'mapping' in t['name'],
        'sales' in t['name'],
        'shop' in t['name'],
        'performance' in t['name']
    ])]
    
    logger.info(f"\n维度表 (dim_*): {len(dim_tables)} 张")
    for t in dim_tables[:5]:
        logger.info(f"  - {t['name']}")
    if len(dim_tables) > 5:
        logger.info(f"  ... 还有 {len(dim_tables) - 5} 张")
    
    logger.info(f"\n事实表 (fact_*): {len(fact_tables)} 张")
    for t in fact_tables:
        logger.info(f"  - {t['name']}")
    
    logger.info(f"\n目录/文件表: {len(catalog_tables)} 张")
    for t in catalog_tables:
        logger.info(f"  - {t['name']}")
    
    logger.info(f"\n字段映射表: {len(mapping_tables)} 张")
    for t in mapping_tables:
        logger.info(f"  - {t['name']}")
    
    logger.info(f"\n销售/战役/目标表: {len(sales_tables)} 张")
    for t in sales_tables:
        logger.info(f"  - {t['name']}")
    
    logger.info(f"\n店铺相关表: {len(shop_tables)} 张")
    for t in shop_tables:
        logger.info(f"  - {t['name']}")
    
    logger.info(f"\n绩效/排名表: {len(performance_tables)} 张")
    for t in performance_tables:
        logger.info(f"  - {t['name']}")
    
    logger.info(f"\n其他表: {len(other_tables)} 张")
    for t in other_tables[:10]:
        logger.info(f"  - {t['name']}")
    if len(other_tables) > 10:
        logger.info(f"  ... 还有 {len(other_tables) - 10} 张")
    
    return {
        'total': len(tables),
        'dim': len(dim_tables),
        'fact': len(fact_tables),
        'catalog': len(catalog_tables),
        'mapping': len(mapping_tables),
        'sales': len(sales_tables),
        'shop': len(shop_tables),
        'performance': len(performance_tables),
        'other': len(other_tables)
    }


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("物化视图和数据库表检查")
    logger.info("=" * 70)
    
    db = SessionLocal()
    try:
        # 检查物化视图
        mv_result = check_materialized_views(db)
        
        # 检查数据库表
        table_result = check_tables(db)
        
        # 总结
        logger.info("\n" + "=" * 70)
        logger.info("检查总结")
        logger.info("=" * 70)
        logger.info(f"物化视图: {mv_result['total']} 个（预期 {mv_result['expected']} 个）")
        if mv_result['missing']:
            logger.warning(f"  缺失: {', '.join(mv_result['missing'])}")
        if mv_result['extra']:
            logger.warning(f"  多余: {', '.join(mv_result['extra'])}")
        
        logger.info(f"\n数据库表: {table_result['total']} 张")
        logger.info(f"  维度表: {table_result['dim']} 张")
        logger.info(f"  事实表: {table_result['fact']} 张")
        logger.info(f"  其他表: {table_result['total'] - table_result['dim'] - table_result['fact']} 张")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()


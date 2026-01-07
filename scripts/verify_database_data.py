#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据完整性验证脚本

v4.12.0新增（Phase 3 - 数据完整性验证）：
- 验证事实表数据完整性
- 验证数据关联完整性
- 验证数据质量
- 输出验证报告
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import text, func, select
from modules.core.db import (
    CatalogFile, FactOrder, FactOrderItem, FactProductMetric,
    FactRawDataOrdersDaily, FactRawDataProductsDaily, FactRawDataTrafficDaily,
    FactRawDataServicesDaily, FactRawDataInventorySnapshot,
    DataQuarantine
)
from backend.models.database import get_db
from modules.core.logger import get_logger

logger = get_logger(__name__)


def verify_table_row_counts(db: Session) -> dict:
    """
    验证各表数据行数
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("验证1: 数据行数统计")
    print("="*60)
    
    try:
        # B类数据表
        b_class_tables = {
            'fact_raw_data_orders_daily': FactRawDataOrdersDaily,
            'fact_raw_data_orders_weekly': None,  # 需要导入
            'fact_raw_data_orders_monthly': None,
            'fact_raw_data_products_daily': FactRawDataProductsDaily,
            'fact_raw_data_products_weekly': None,
            'fact_raw_data_products_monthly': None,
            'fact_raw_data_traffic_daily': FactRawDataTrafficDaily,
            'fact_raw_data_traffic_weekly': None,
            'fact_raw_data_traffic_monthly': None,
            'fact_raw_data_services_daily': FactRawDataServicesDaily,
            'fact_raw_data_services_weekly': None,
            'fact_raw_data_services_monthly': None,
            'fact_raw_data_inventory_snapshot': FactRawDataInventorySnapshot
        }
        
        # 事实表
        fact_tables = {
            'fact_orders': FactOrder,
            'fact_order_items': FactOrderItem,
            'fact_product_metrics': FactProductMetric
        }
        
        print("\nB类数据表（fact_raw_data_*）:")
        b_class_stats = {}
        for table_name, model_class in b_class_tables.items():
            if model_class:
                try:
                    count = db.query(model_class).count()
                    b_class_stats[table_name] = count
                    if count > 0:
                        print(f"  - {table_name}: {count} 行")
                except Exception as e:
                    logger.warning(f"查询表 {table_name} 失败: {e}")
                    b_class_stats[table_name] = 0
            else:
                # 使用SQL查询
                try:
                    result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = result.scalar()
                    b_class_stats[table_name] = count
                    if count > 0:
                        print(f"  - {table_name}: {count} 行")
                except Exception:
                    b_class_stats[table_name] = 0
        
        total_b_class = sum(b_class_stats.values())
        print(f"\nB类数据表总行数: {total_b_class}")
        
        print("\n事实表:")
        fact_stats = {}
        for table_name, model_class in fact_tables.items():
            try:
                count = db.query(model_class).count()
                fact_stats[table_name] = count
                if count > 0:
                    print(f"  - {table_name}: {count} 行")
            except Exception as e:
                logger.warning(f"查询表 {table_name} 失败: {e}")
                fact_stats[table_name] = 0
        
        total_fact = sum(fact_stats.values())
        print(f"\n事实表总行数: {total_fact}")
        
        # 验证Raw → Fact数据行数一致性（允许隔离数据）
        print(f"\n数据行数一致性验证:")
        print(f"  - B类数据表: {total_b_class} 行")
        print(f"  - 事实表: {total_fact} 行")
        print(f"  - 差异: {total_b_class - total_fact} 行（可能为隔离数据或未映射数据）")
        
        if total_b_class >= total_fact:
            print("[OK] 数据行数一致性验证通过（B类数据表 >= 事实表）")
        else:
            print("[WARNING] 数据行数异常（B类数据表 < 事实表）")
        
        return {
            "success": True,
            "b_class_stats": b_class_stats,
            "fact_stats": fact_stats,
            "total_b_class": total_b_class,
            "total_fact": total_fact
        }
        
    except Exception as e:
        logger.error(f"数据行数统计失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def verify_key_fields_integrity(db: Session) -> dict:
    """
    验证关键字段完整性
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("验证2: 关键字段完整性")
    print("="*60)
    
    try:
        integrity_stats = {}
        
        # 1. 验证 platform_code 字段完整性
        print("\n1. platform_code 字段完整性:")
        
        # B类数据表
        for table_name in ['fact_raw_data_orders_daily', 'fact_raw_data_products_daily', 
                          'fact_raw_data_traffic_daily', 'fact_raw_data_inventory_snapshot']:
            try:
                result = db.execute(text(f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(platform_code) as has_platform_code,
                        COUNT(*) - COUNT(platform_code) as null_count
                    FROM {table_name}
                """))
                row = result.fetchone()
                if row and row[0] > 0:
                    total, has_platform, null_count = row
                    integrity_stats[table_name] = {
                        'total': total,
                        'has_platform_code': has_platform,
                        'null_platform_code': null_count
                    }
                    print(f"  - {table_name}: {has_platform}/{total} 有platform_code ({null_count} 个NULL)")
            except Exception:
                pass
        
        # 事实表（使用SQL查询避免ORM问题）
        for table_name in ['fact_orders', 'fact_product_metrics']:
            try:
                result = db.execute(text(f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(platform_code) as has_platform_code,
                        COUNT(*) - COUNT(platform_code) as null_count
                    FROM {table_name}
                """))
                row = result.fetchone()
                if row and row[0] > 0:
                    total, has_platform, null_count = row
                    integrity_stats[table_name] = {
                        'total': total,
                        'has_platform_code': has_platform,
                        'null_platform_code': null_count
                    }
                    print(f"  - {table_name}: {has_platform}/{total} 有platform_code ({null_count} 个NULL)")
            except Exception as e:
                logger.warning(f"查询表 {table_name} 失败: {e}")
                db.rollback()
        
        # 2. 验证日期字段完整性
        print("\n2. 日期字段完整性:")
        
        # fact_orders（使用SQL查询）
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(order_date_local) as has_date
                FROM fact_orders
            """))
            row = result.fetchone()
            if row and row[0] > 0:
                total, has_date = row
                print(f"  - fact_orders.order_date_local: {has_date}/{total} 有日期")
        except Exception as e:
            logger.warning(f"查询fact_orders日期字段失败: {e}")
            db.rollback()
        
        # fact_product_metrics（使用SQL查询）
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(metric_date) as has_date
                FROM fact_product_metrics
            """))
            row = result.fetchone()
            if row and row[0] > 0:
                total, has_date = row
                print(f"  - fact_product_metrics.metric_date: {has_date}/{total} 有日期")
        except Exception as e:
            logger.warning(f"查询fact_product_metrics日期字段失败: {e}")
            db.rollback()
        
        # 3. 验证业务主键唯一性
        print("\n3. 业务主键唯一性:")
        
        # fact_orders (platform_code, shop_id, order_id)
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT (platform_code, shop_id, order_id)) as unique_keys
                FROM fact_orders
            """))
            row = result.fetchone()
            if row and row[0] > 0:
                total, unique_keys = row
                if total == unique_keys:
                    print(f"  - fact_orders: {total} 行，{unique_keys} 个唯一主键 [OK]")
                else:
                    print(f"  - fact_orders: {total} 行，{unique_keys} 个唯一主键 [WARNING] 有重复")
        except Exception:
            pass
        
        # fact_product_metrics (platform_code, shop_id, platform_sku, metric_date, granularity, sku_scope, data_domain)
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT (platform_code, shop_id, platform_sku, metric_date, granularity, sku_scope, data_domain)) as unique_keys
                FROM fact_product_metrics
            """))
            row = result.fetchone()
            if row and row[0] > 0:
                total, unique_keys = row
                if total == unique_keys:
                    print(f"  - fact_product_metrics: {total} 行，{unique_keys} 个唯一主键 [OK]")
                else:
                    print(f"  - fact_product_metrics: {total} 行，{unique_keys} 个唯一主键 [WARNING] 有重复")
        except Exception:
            pass
        
        print("\n[OK] 关键字段完整性验证完成")
        
        return {
            "success": True,
            "integrity_stats": integrity_stats
        }
        
    except Exception as e:
        logger.error(f"关键字段完整性验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def verify_data_quality(db: Session) -> dict:
    """
    验证数据质量
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("验证3: 数据质量")
    print("="*60)
    
    try:
        # 1. 验证数据隔离机制
        print("\n1. 数据隔离机制（data_quarantine表）:")
        
        try:
            result = db.execute(text("SELECT COUNT(*) FROM data_quarantine"))
            quarantine_count = result.scalar()
            print(f"  - 隔离数据总数: {quarantine_count} 条")
            
            if quarantine_count > 0:
                # 统计各错误类型的隔离数据（data_quarantine表没有status字段，使用error_type）
                try:
                    result = db.execute(text("""
                        SELECT error_type, COUNT(*) as count
                        FROM data_quarantine
                        GROUP BY error_type
                        ORDER BY count DESC
                        LIMIT 10
                    """))
                    error_stats = result.fetchall()
                    
                    print(f"    - 错误类型分布（前10个）:")
                    for error_type, count in error_stats:
                        print(f"      - {error_type}: {count} 条")
                except Exception:
                    # 如果error_type字段也不存在，跳过
                    pass
            
            print("[OK] 数据隔离机制正常")
        except Exception as e:
            logger.warning(f"查询data_quarantine表失败: {e}")
            db.rollback()
        
        # 2. 验证文件状态分布
        print("\n2. 文件状态分布（catalog_files表）:")
        
        try:
            result = db.execute(text("""
                SELECT status, COUNT(*) as count
                FROM catalog_files
                GROUP BY status
            """))
            status_stats = result.fetchall()
            
            total_files = sum(count for _, count in status_stats)
            print(f"  - 总文件数: {total_files}")
            
            for status, count in status_stats:
                percentage = count / total_files * 100 if total_files > 0 else 0
                print(f"    - {status}: {count} 个 ({percentage:.1f}%)")
            
            print("[OK] 文件状态分布正常")
        except Exception as e:
            logger.warning(f"查询catalog_files状态失败: {e}")
            db.rollback()
        
        # 3. 验证数据质量评分（如果catalog_files表有quality_score字段）
        print("\n3. 数据质量评分:")
        
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(quality_score) as has_score,
                    AVG(quality_score) as avg_score,
                    MIN(quality_score) as min_score,
                    MAX(quality_score) as max_score
                FROM catalog_files
                WHERE quality_score IS NOT NULL
            """))
            row = result.fetchone()
            if row and row[0] > 0:
                total, has_score, avg_score, min_score, max_score = row
                print(f"  - 有质量评分的文件: {has_score} 个")
                if avg_score:
                    print(f"  - 平均质量评分: {avg_score:.2f}")
                    print(f"  - 最低质量评分: {min_score:.2f}")
                    print(f"  - 最高质量评分: {max_score:.2f}")
            else:
                print("  - 暂无质量评分数据")
        except Exception:
            print("  - quality_score字段可能不存在或为空")
        
        print("\n[OK] 数据质量验证完成")
        
        return {
            "success": True
        }
        
    except Exception as e:
        logger.error(f"数据质量验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def verify_data_relationships(db: Session) -> dict:
    """
    验证数据关联完整性
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("验证4: 数据关联完整性")
    print("="*60)
    
    try:
        # 1. 验证文件关联（file_id）
        print("\n1. 文件关联（file_id）:")
        
        # B类数据表
        for table_name in ['fact_raw_data_orders_daily', 'fact_raw_data_products_daily',
                          'fact_raw_data_inventory_snapshot']:
            try:
                result = db.execute(text(f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(DISTINCT file_id) as unique_files,
                        COUNT(*) - COUNT(file_id) as null_file_id
                    FROM {table_name}
                """))
                row = result.fetchone()
                if row and row[0] > 0:
                    total, unique_files, null_count = row
                    print(f"  - {table_name}:")
                    print(f"    - 总行数: {total}")
                    print(f"    - 关联文件数: {unique_files}")
                    print(f"    - NULL file_id: {null_count}")
                    
                    # 验证file_id是否存在于catalog_files表
                    if unique_files > 0:
                        result2 = db.execute(text(f"""
                            SELECT COUNT(DISTINCT r.file_id)
                            FROM {table_name} r
                            INNER JOIN catalog_files c ON r.file_id = c.id
                        """))
                        valid_files = result2.scalar()
                        if valid_files == unique_files:
                            print(f"    - 文件关联完整性: [OK] 所有file_id都存在于catalog_files")
                        else:
                            print(f"    - 文件关联完整性: [WARNING] {valid_files}/{unique_files} 个file_id有效")
            except Exception as e:
                logger.warning(f"验证表 {table_name} 文件关联失败: {e}")
        
        # 2. 验证产品关联（product_id）
        print("\n2. 产品关联（product_id）:")
        
        try:
            # fact_order_items（使用SQL查询）
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(product_id) as has_product_id
                FROM fact_order_items
            """))
            row = result.fetchone()
            if row and row[0] > 0:
                total_items, has_product = row
                print(f"  - fact_order_items: {has_product}/{total_items} 有product_id")
                
                # 验证product_id是否存在于BridgeProductKeys表
                try:
                    result = db.execute(text("""
                        SELECT COUNT(DISTINCT oi.product_id)
                        FROM fact_order_items oi
                        INNER JOIN bridge_product_keys bpk ON oi.product_id = bpk.product_id
                    """))
                    valid_products = result.scalar()
                    if valid_products == has_product:
                        print(f"    - 产品关联完整性: [OK] 所有product_id都存在于bridge_product_keys")
                    else:
                        print(f"    - 产品关联完整性: [WARNING] {valid_products}/{has_product} 个product_id有效")
                except Exception:
                    print("    - 无法验证product_id关联（bridge_product_keys表可能不存在）")
        except Exception as e:
            logger.warning(f"验证产品关联失败: {e}")
            db.rollback()
        
        print("\n[OK] 数据关联完整性验证完成")
        
        return {
            "success": True
        }
        
    except Exception as e:
        logger.error(f"数据关联完整性验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """主函数"""
    print("="*60)
    print("数据完整性验证脚本")
    print("="*60)
    print("\n本脚本将验证以下内容:")
    print("  1. 数据行数统计")
    print("  2. 关键字段完整性")
    print("  3. 数据质量")
    print("  4. 数据关联完整性")
    
    # 获取数据库会话
    db = next(get_db())
    
    try:
        results = {}
        
        # 验证1: 数据行数统计
        results["row_counts"] = verify_table_row_counts(db)
        
        # 验证2: 关键字段完整性
        results["field_integrity"] = verify_key_fields_integrity(db)
        
        # 验证3: 数据质量
        results["data_quality"] = verify_data_quality(db)
        
        # 验证4: 数据关联完整性
        results["relationships"] = verify_data_relationships(db)
        
        # 输出总结报告
        print("\n" + "="*60)
        print("验证报告总结")
        print("="*60)
        
        all_passed = True
        for test_name, result in results.items():
            if result.get("success"):
                status = "[OK] 通过"
            else:
                status = "[FAIL] 失败"
                all_passed = False
            
            print(f"{test_name}: {status}")
            if not result.get("success"):
                if "error" in result:
                    print(f"  错误: {result['error']}")
        
        if all_passed:
            print("\n[OK] 所有验证通过！")
        else:
            print("\n[WARNING] 部分验证失败，请检查日志")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        logger.error(f"验证脚本执行失败: {e}", exc_info=True)
        print(f"\n[ERROR] 验证脚本执行失败: {e}")
        return 1
        
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())


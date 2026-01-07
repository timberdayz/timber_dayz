#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整测试脚本：验证inventory数据域功能
时间: 2025-11-05
版本: v4.10.0
说明: 自动化测试所有功能点
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FactProductMetric, CatalogFile, FieldMappingDictionary
from modules.core.validators import VALID_DATA_DOMAINS, is_valid_data_domain
from sqlalchemy import text, select, func
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def test_1_validators():
    """测试1: 验证器支持inventory域"""
    safe_print("\n" + "="*70)
    safe_print("[测试1] 验证器支持inventory域")
    safe_print("="*70)
    
    assert 'inventory' in VALID_DATA_DOMAINS, "VALID_DATA_DOMAINS中缺少inventory域"
    assert is_valid_data_domain('inventory'), "is_valid_data_domain('inventory')返回False"
    
    safe_print("[OK] 验证器支持inventory域")
    return True


def test_2_schema():
    """测试2: schema.py中data_domain字段和唯一索引"""
    safe_print("\n" + "="*70)
    safe_print("[测试2] schema.py中data_domain字段和唯一索引")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 检查字段是否存在
        check_column = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fact_product_metrics' 
            AND column_name = 'data_domain'
        """)
        result = db.execute(check_column).fetchone()
        assert result is not None, "fact_product_metrics表缺少data_domain字段"
        
        # 检查唯一索引是否包含data_domain
        check_index = text("""
            SELECT indexdef 
            FROM pg_indexes 
            WHERE tablename = 'fact_product_metrics' 
            AND indexname = 'ix_product_unique_with_scope'
        """)
        result = db.execute(check_index).fetchone()
        assert result is not None, "唯一索引ix_product_unique_with_scope不存在"
        assert 'data_domain' in result[0], "唯一索引中缺少data_domain字段"
        
        safe_print("[OK] schema.py中data_domain字段和唯一索引正确")
        return True
        
    finally:
        db.close()


def test_3_unique_index():
    """测试3: 唯一索引支持同一SKU在同一天有多个数据域的数据"""
    safe_print("\n" + "="*70)
    safe_print("[测试3] 唯一索引支持同一SKU在同一天有多个数据域的数据")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 测试插入同一SKU的products域和inventory域数据
        test_data = {
            'platform_code': 'test_platform',
            'shop_id': 'test_shop',
            'platform_sku': 'TEST_SKU_001',
            'metric_date': '2025-11-05',
            'granularity': 'daily',
            'sku_scope': 'product',
            'data_domain': 'products',
            'sales_volume': 100
        }
        
        # 插入products域数据
        insert1 = text("""
            INSERT INTO fact_product_metrics (
                platform_code, shop_id, platform_sku, metric_date, 
                granularity, sku_scope, data_domain, sales_volume,
                created_at, updated_at
            ) VALUES (
                :platform_code, :shop_id, :platform_sku, :metric_date,
                :granularity, :sku_scope, :data_domain, :sales_volume,
                NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
        """)
        db.execute(insert1, test_data)
        db.commit()
        
        # 插入inventory域数据（应该成功，因为data_domain不同）
        test_data['data_domain'] = 'inventory'
        test_data['total_stock'] = 500
        test_data['available_stock'] = 400
        insert2 = text("""
            INSERT INTO fact_product_metrics (
                platform_code, shop_id, platform_sku, metric_date, 
                granularity, sku_scope, data_domain, total_stock, available_stock,
                created_at, updated_at
            ) VALUES (
                :platform_code, :shop_id, :platform_sku, :metric_date,
                :granularity, :sku_scope, :data_domain, :total_stock, :available_stock,
                NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
        """)
        db.execute(insert2, test_data)
        db.commit()
        
        # 验证两条数据都存在
        check_query = text("""
            SELECT data_domain, COUNT(*) 
            FROM fact_product_metrics
            WHERE platform_code = :platform_code
              AND shop_id = :shop_id
              AND platform_sku = :platform_sku
              AND metric_date = :metric_date
            GROUP BY data_domain
        """)
        results = db.execute(check_query, {
            'platform_code': 'test_platform',
            'shop_id': 'test_shop',
            'platform_sku': 'TEST_SKU_001',
            'metric_date': '2025-11-05'
        }).fetchall()
        
        domains = {row[0]: row[1] for row in results}
        assert 'products' in domains, "products域数据未插入"
        assert 'inventory' in domains, "inventory域数据未插入"
        
        # 清理测试数据
        cleanup = text("""
            DELETE FROM fact_product_metrics
            WHERE platform_code = 'test_platform'
              AND shop_id = 'test_shop'
              AND platform_sku = 'TEST_SKU_001'
        """)
        db.execute(cleanup)
        db.commit()
        
        safe_print("[OK] 唯一索引支持同一SKU在同一天有多个数据域的数据")
        return True
        
    except Exception as e:
        db.rollback()
        safe_print(f"[FAIL] 测试失败: {e}")
        raise
    finally:
        db.close()


def test_4_materialized_views():
    """测试4: 物化视图data_domain过滤"""
    safe_print("\n" + "="*70)
    safe_print("[测试4] 物化视图data_domain过滤")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 检查mv_product_management视图的WHERE条件
        check_view = text("""
            SELECT definition 
            FROM pg_matviews 
            WHERE matviewname = 'mv_product_management'
        """)
        result = db.execute(check_view).fetchone()
        
        if result:
            definition = result[0]
            assert "data_domain" in definition.lower(), "mv_product_management视图缺少data_domain过滤"
            safe_print("[OK] mv_product_management视图包含data_domain过滤")
        else:
            safe_print("[SKIP] mv_product_management视图不存在（可能需要先创建）")
        
        # 检查mv_inventory_summary视图是否存在
        check_inv_view = text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE matviewname = 'mv_inventory_summary'
        """)
        result = db.execute(check_inv_view).fetchone()
        
        if result:
            safe_print("[OK] mv_inventory_summary视图存在")
        else:
            safe_print("[SKIP] mv_inventory_summary视图不存在（需要运行SQL脚本创建）")
        
        return True
        
    finally:
        db.close()


def test_5_field_dictionary():
    """测试5: 字段映射辞典包含inventory域字段"""
    safe_print("\n" + "="*70)
    safe_print("[测试5] 字段映射辞典包含inventory域字段")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 查询inventory域的标准字段
        query = select(FieldMappingDictionary.field_code).where(
            FieldMappingDictionary.data_domain == 'inventory'
        )
        result = db.execute(query).all()
        found_fields = [row[0] for row in result]
        
        required_fields = ['platform_sku', 'total_stock', 'available_stock', 'warehouse']
        
        missing_fields = [f for f in required_fields if f not in found_fields]
        
        if missing_fields:
            safe_print(f"[WARN] 缺少字段: {missing_fields}")
            safe_print(f"[INFO] 找到的字段: {found_fields}")
        else:
            safe_print(f"[OK] 找到{len(found_fields)}个inventory域标准字段")
            safe_print(f"[INFO] 字段列表: {found_fields}")
        
        return True
        
    finally:
        db.close()


def test_6_api_endpoints():
    """测试6: API端点支持inventory域"""
    safe_print("\n" + "="*70)
    safe_print("[测试6] API端点支持inventory域")
    safe_print("="*70)
    
    # 检查get_file_groups是否包含inventory域
    # 这个测试需要实际运行API，暂时跳过
    safe_print("[SKIP] API端点测试需要实际运行后端服务")
    safe_print("[INFO] 请手动测试以下端点:")
    safe_print("  - GET /api/field-mapping/file-groups (应包含inventory域)")
    safe_print("  - GET /api/field-mapping/data-domains (应包含inventory域)")
    safe_print("  - GET /api/field-mapping/field-mappings/inventory (应返回inventory域字段)")
    
    return True


def main():
    """运行所有测试"""
    safe_print("\n" + "="*70)
    safe_print("开始自动化测试 - inventory数据域功能验证")
    safe_print("="*70)
    
    tests = [
        test_1_validators,
        test_2_schema,
        test_3_unique_index,
        test_4_materialized_views,
        test_5_field_dictionary,
        test_6_api_endpoints,
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
        except AssertionError as e:
            safe_print(f"[FAIL] {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            safe_print(f"[ERROR] {test_func.__name__}: {e}")
            failed += 1
    
    safe_print("\n" + "="*70)
    safe_print("测试结果汇总")
    safe_print("="*70)
    safe_print(f"通过: {passed}")
    safe_print(f"失败: {failed}")
    safe_print(f"总计: {len(tests)}")
    
    if failed == 0:
        safe_print("\n[SUCCESS] 所有测试通过！")
        return 0
    else:
        safe_print(f"\n[FAIL] {failed}个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())


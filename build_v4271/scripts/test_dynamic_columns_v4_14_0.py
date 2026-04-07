#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：动态列管理和核心字段去重功能（v4.14.0）

测试内容：
1. 动态列管理服务（ensure_columns_exist, get_existing_columns）
2. 核心字段去重逻辑（calculate_data_hash with deduplication_fields）
3. data_hash 计算（基于核心字段）
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from backend.services.dynamic_column_manager import get_dynamic_column_manager
from backend.services.deduplication_service import DeduplicationService
from backend.services.deduplication_fields_config import get_deduplication_fields
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def test_dynamic_column_manager():
    """测试动态列管理服务"""
    safe_print("=" * 70)
    safe_print("测试1: 动态列管理服务")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        manager = get_dynamic_column_manager(db)
        table_name = "fact_raw_data_orders_daily"
        
        # 测试1.1: 查询现有列
        safe_print("\n1.1 查询现有列...")
        existing_columns = manager.get_existing_columns(table_name)
        safe_print(f"  现有列数: {len(existing_columns)}")
        safe_print(f"  系统字段: {', '.join(sorted(existing_columns)[:10])}...")
        
        # 测试1.2: 列名规范化
        safe_print("\n1.2 测试列名规范化...")
        test_names = [
            "订单ID",
            "order-id",
            "product.sku",
            "销售额（BRL）",
            "123invalid",
            "very_long_column_name_that_exceeds_postgresql_maximum_length_limit"
        ]
        for name in test_names:
            normalized = manager.normalize_column_name(name)
            safe_print(f"  '{name}' -> '{normalized}'")
        
        # 测试1.3: 确保列存在（使用测试列名）
        safe_print("\n1.3 测试动态添加列...")
        test_header_columns = ["测试列1", "测试列2", "order_id"]
        try:
            added_columns = manager.ensure_columns_exist(
                table_name=table_name,
                header_columns=test_header_columns
            )
            safe_print(f"  成功添加列: {len(added_columns)}个")
            if added_columns:
                safe_print(f"  添加的列: {', '.join(added_columns)}")
        except Exception as e:
            safe_print(f"  [ERROR] 添加列失败: {e}")
        
        safe_print("\n[OK] 动态列管理服务测试完成")
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试失败", exc_info=True)
    finally:
        db.close()


def test_deduplication_fields_config():
    """测试核心字段配置"""
    safe_print("\n" + "=" * 70)
    safe_print("测试2: 核心字段配置")
    safe_print("=" * 70)
    
    # 测试2.1: 默认核心字段配置
    safe_print("\n2.1 测试默认核心字段配置...")
    test_domains = ['orders', 'products', 'inventory', 'traffic', 'services']
    for domain in test_domains:
        fields = get_deduplication_fields(domain)
        safe_print(f"  {domain}: {fields}")
    
    # 测试2.2: 模板配置优先级
    safe_print("\n2.2 测试模板配置优先级...")
    template_fields = ['custom_field1', 'custom_field2']
    fields = get_deduplication_fields('orders', template_fields=template_fields)
    safe_print(f"  模板配置: {template_fields}")
    safe_print(f"  最终使用: {fields}")
    assert fields == template_fields, "应该使用模板配置"
    
    # 测试2.3: 默认配置回退
    safe_print("\n2.3 测试默认配置回退...")
    fields = get_deduplication_fields('orders', template_fields=None)
    safe_print(f"  无模板配置: {fields}")
    assert len(fields) > 0, "应该使用默认配置"
    
    safe_print("\n[OK] 核心字段配置测试完成")


def test_data_hash_calculation():
    """测试data_hash计算"""
    safe_print("\n" + "=" * 70)
    safe_print("测试3: data_hash计算（核心字段去重）")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        dedup_service = DeduplicationService(db)
        
        # 测试3.1: 使用所有字段计算hash
        safe_print("\n3.1 测试使用所有字段计算hash...")
        row1 = {
            'order_id': '12345',
            'order_date': '2025-01-01',
            'amount': 100.0,
            'status': 'completed'
        }
        row2 = {
            'order_id': '12345',
            'order_date': '2025-01-01',
            'amount': 100.0,
            'status': 'completed',
            'new_field': 'new_value'  # 新增字段
        }
        
        hash1_all = dedup_service.calculate_data_hash(row1)
        hash2_all = dedup_service.calculate_data_hash(row2)
        safe_print(f"  row1 hash (所有字段): {hash1_all[:16]}...")
        safe_print(f"  row2 hash (所有字段): {hash2_all[:16]}...")
        safe_print(f"  是否相同: {hash1_all == hash2_all}")
        assert hash1_all != hash2_all, "新增字段应该导致hash不同"
        
        # 测试3.2: 使用核心字段计算hash
        safe_print("\n3.2 测试使用核心字段计算hash...")
        deduplication_fields = ['order_id', 'order_date']
        hash1_core = dedup_service.calculate_data_hash(row1, deduplication_fields=deduplication_fields)
        hash2_core = dedup_service.calculate_data_hash(row2, deduplication_fields=deduplication_fields)
        safe_print(f"  核心字段: {deduplication_fields}")
        safe_print(f"  row1 hash (核心字段): {hash1_core[:16]}...")
        safe_print(f"  row2 hash (核心字段): {hash2_core[:16]}...")
        safe_print(f"  是否相同: {hash1_core == hash2_core}")
        assert hash1_core == hash2_core, "核心字段相同，hash应该相同"
        
        # 测试3.3: 批量计算hash
        safe_print("\n3.3 测试批量计算hash...")
        rows = [row1, row2]
        hashes = dedup_service.batch_calculate_data_hash(
            rows,
            deduplication_fields=deduplication_fields
        )
        safe_print(f"  批量计算: {len(hashes)}个hash")
        safe_print(f"  hash1: {hashes[0][:16]}...")
        safe_print(f"  hash2: {hashes[1][:16]}...")
        safe_print(f"  是否相同: {hashes[0] == hashes[1]}")
        assert hashes[0] == hashes[1], "核心字段相同，hash应该相同"
        
        safe_print("\n[OK] data_hash计算测试完成")
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试失败", exc_info=True)
    finally:
        db.close()


def test_table_header_change_scenario():
    """测试表头变化场景"""
    safe_print("\n" + "=" * 70)
    safe_print("测试4: 表头变化场景（核心字段去重）")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        dedup_service = DeduplicationService(db)
        deduplication_fields = ['order_id', 'order_date', 'platform_code', 'shop_id']
        
        # 模拟上午10点采集的数据
        safe_print("\n4.1 模拟上午10点采集的数据...")
        morning_row = {
            'order_id': '12345',
            'order_date': '2025-01-01',
            'platform_code': 'shopee',
            'shop_id': 'shop001',
            'amount': 100.0,
            'status': 'completed'
        }
        morning_hash = dedup_service.calculate_data_hash(
            morning_row,
            deduplication_fields=deduplication_fields
        )
        safe_print(f"  数据: order_id=12345, order_date=2025-01-01, amount=100.0")
        safe_print(f"  hash: {morning_hash[:16]}...")
        
        # 模拟下午6点采集的数据（表头新增字段）
        safe_print("\n4.2 模拟下午6点采集的数据（表头新增字段）...")
        evening_row = {
            'order_id': '12345',
            'order_date': '2025-01-01',
            'platform_code': 'shopee',
            'shop_id': 'shop001',
            'amount': 100.0,
            'status': 'completed',
            'new_field': 'new_value',  # 新增字段
            'another_field': 'another_value'  # 新增字段
        }
        evening_hash = dedup_service.calculate_data_hash(
            evening_row,
            deduplication_fields=deduplication_fields
        )
        safe_print(f"  数据: order_id=12345, order_date=2025-01-01, amount=100.0, new_field=new_value")
        safe_print(f"  hash: {evening_hash[:16]}...")
        
        # 验证核心字段相同的数据，hash相同
        safe_print("\n4.3 验证核心字段去重...")
        safe_print(f"  核心字段: {deduplication_fields}")
        safe_print(f"  上午hash: {morning_hash[:16]}...")
        safe_print(f"  下午hash: {evening_hash[:16]}...")
        safe_print(f"  是否相同: {morning_hash == evening_hash}")
        
        if morning_hash == evening_hash:
            safe_print("  [OK] 核心字段相同，hash相同，去重成功！")
        else:
            safe_print("  [ERROR] 核心字段相同但hash不同，去重失败！")
            assert False, "核心字段相同的数据，hash应该相同"
        
        safe_print("\n[OK] 表头变化场景测试完成")
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试失败", exc_info=True)
    finally:
        db.close()


def main():
    """运行所有测试"""
    safe_print("=" * 70)
    safe_print("v4.14.0 动态列管理和核心字段去重功能测试")
    safe_print("=" * 70)
    
    try:
        # 测试1: 动态列管理服务
        test_dynamic_column_manager()
        
        # 测试2: 核心字段配置
        test_deduplication_fields_config()
        
        # 测试3: data_hash计算
        test_data_hash_calculation()
        
        # 测试4: 表头变化场景
        test_table_header_change_scenario()
        
        safe_print("\n" + "=" * 70)
        safe_print("[OK] 所有测试完成！")
        safe_print("=" * 70)
        
    except Exception as e:
        safe_print(f"\n[ERROR] 测试失败: {e}")
        logger.error("测试失败", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


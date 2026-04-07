#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据入库功能（修复后）
验证fact_order_items表结构修复后，数据入库是否正常
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text, inspect
from modules.core.db import FactOrderItem, FactOrder
from modules.core.logger import get_logger

logger = get_logger(__name__)

def test_table_structure():
    """测试表结构是否正确"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        columns = inspector.get_columns('fact_order_items')
        column_names = [c['name'] for c in columns]
        
        required_fields = ['platform_code', 'shop_id', 'order_id', 'platform_sku']
        missing_fields = [f for f in required_fields if f not in column_names]
        
        if missing_fields:
            print(f"[ERROR] 表缺少必需字段: {missing_fields}")
            return False
        else:
            print("[OK] 表结构正确，包含所有必需字段")
            return True
    finally:
        db.close()

def test_insert_order_item():
    """测试插入订单明细"""
    db = SessionLocal()
    try:
        # 准备测试数据
        test_data = {
            "platform_code": "shopee",
            "shop_id": "test_shop",
            "order_id": "test_order_123",
            "platform_sku": "test_sku_456",
            "product_title": "测试商品",
            "quantity": 1,
            "currency": "CNY",
            "unit_price": 10.0,
            "unit_price_rmb": 10.0,
            "line_amount": 10.0,
            "line_amount_rmb": 10.0,
            "attributes": None
        }
        
        # 尝试插入
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from datetime import datetime
        
        stmt = pg_insert(FactOrderItem).values(**test_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["platform_code", "shop_id", "order_id", "platform_sku"],
            set_={
                "product_title": stmt.excluded["product_title"],
                "quantity": stmt.excluded["quantity"],
                "updated_at": datetime.now()
            }
        )
        
        db.execute(stmt)
        db.commit()
        
        print("[OK] 订单明细插入成功")
        
        # 清理测试数据
        db.execute(text("""
            DELETE FROM fact_order_items 
            WHERE platform_code = 'shopee' 
            AND shop_id = 'test_shop' 
            AND order_id = 'test_order_123'
        """))
        db.commit()
        print("[OK] 测试数据已清理")
        
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] 插入订单明细失败: {e}", exc_info=True)
        print(f"[ERROR] 插入失败: {e}")
        return False
    finally:
        db.close()

if __name__ == '__main__':
    print("=" * 60)
    print("数据入库功能测试（修复后）")
    print("=" * 60)
    
    # 测试1: 检查表结构
    print("\n[测试1] 检查表结构...")
    if not test_table_structure():
        print("[ERROR] 表结构检查失败，无法继续测试")
        sys.exit(1)
    
    # 测试2: 测试插入订单明细
    print("\n[测试2] 测试插入订单明细...")
    if test_insert_order_item():
        print("\n[OK] 所有测试通过！")
    else:
        print("\n[ERROR] 测试失败")
        sys.exit(1)


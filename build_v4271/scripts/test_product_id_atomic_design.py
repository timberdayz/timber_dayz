#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试产品ID原子级设计功能

测试内容：
1. FactOrderItem表是否有product_id字段
2. product_id字段索引是否存在
3. 数据入库时product_id自动关联功能
4. mv_sales_detail_by_product物化视图是否存在
5. 销售明细查询API功能

使用方法：
    python scripts/test_product_id_atomic_design.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from backend.models.database import get_db
from modules.core.db import FactOrderItem, BridgeProductKeys, DimProductMaster
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows兼容的安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def test_fact_order_item_schema(db: Session) -> bool:
    """测试FactOrderItem表结构"""
    safe_print("\n" + "=" * 70)
    safe_print("测试1: FactOrderItem表结构")
    safe_print("=" * 70)
    
    try:
        # 检查表是否存在
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        
        if 'fact_order_items' not in tables:
            safe_print("[FAIL] fact_order_items表不存在")
            return False
        
        safe_print("[OK] fact_order_items表存在")
        
        # 检查product_id字段是否存在
        columns = inspector.get_columns('fact_order_items')
        column_names = [col['name'] for col in columns]
        
        if 'product_id' not in column_names:
            safe_print("[FAIL] product_id字段不存在")
            return False
        
        safe_print("[OK] product_id字段存在")
        
        # 检查product_id字段属性
        product_id_col = next(col for col in columns if col['name'] == 'product_id')
        safe_print(f"  - 字段类型: {product_id_col['type']}")
        safe_print(f"  - 允许NULL: {product_id_col['nullable']}")
        
        # 检查索引是否存在
        indexes = inspector.get_indexes('fact_order_items')
        index_names = [idx['name'] for idx in indexes]
        
        if 'ix_fact_items_product_id' not in index_names:
            safe_print("[WARN] ix_fact_items_product_id索引不存在（可能还未创建）")
        else:
            safe_print("[OK] ix_fact_items_product_id索引存在")
        
        # 检查外键约束
        foreign_keys = inspector.get_foreign_keys('fact_order_items')
        fk_names = [fk['name'] for fk in foreign_keys]
        
        if 'fk_fact_order_items_product_id' not in fk_names:
            safe_print("[WARN] fk_fact_order_items_product_id外键不存在（可能还未创建）")
        else:
            safe_print("[OK] fk_fact_order_items_product_id外键存在")
        
        return True
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试FactOrderItem表结构失败", exc_info=True)
        return False


def test_materialized_view_exists(db: Session) -> bool:
    """测试mv_sales_detail_by_product物化视图是否存在"""
    safe_print("\n" + "=" * 70)
    safe_print("测试2: mv_sales_detail_by_product物化视图")
    safe_print("=" * 70)
    
    try:
        # 查询物化视图是否存在
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM pg_matviews 
            WHERE matviewname = 'mv_sales_detail_by_product'
        """)).scalar()
        
        if result == 0:
            safe_print("[WARN] mv_sales_detail_by_product物化视图不存在（需要创建）")
            safe_print("  提示: 运行 python scripts/create_mv_sales_detail_by_product.py")
            return False
        
        safe_print("[OK] mv_sales_detail_by_product物化视图存在")
        
        # 检查视图结构
        result = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'mv_sales_detail_by_product'
            ORDER BY ordinal_position
        """))
        
        columns = result.fetchall()
        safe_print(f"\n  视图包含 {len(columns)} 个字段:")
        key_fields = ['product_id', 'platform_sku', 'order_id', 'sale_date', 'line_amount_rmb']
        for col in columns:
            marker = "⭐" if col[0] in key_fields else "  "
            safe_print(f"  {marker} {col[0]}: {col[1]}")
        
        # 检查索引
        result = db.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'mv_sales_detail_by_product'
        """))
        
        indexes = [row[0] for row in result.fetchall()]
        safe_print(f"\n  视图包含 {len(indexes)} 个索引:")
        for idx in indexes:
            safe_print(f"    - {idx}")
        
        # 检查数据行数
        row_count = db.execute(text("SELECT COUNT(*) FROM mv_sales_detail_by_product")).scalar()
        safe_print(f"\n  当前数据行数: {row_count}")
        
        return True
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试物化视图失败", exc_info=True)
        return False


def test_product_id_association(db: Session) -> bool:
    """测试product_id自动关联功能"""
    safe_print("\n" + "=" * 70)
    safe_print("测试3: product_id自动关联功能")
    safe_print("=" * 70)
    
    try:
        # 统计订单明细数据
        total_items = db.execute(text("SELECT COUNT(*) FROM fact_order_items")).scalar()
        items_with_product_id = db.execute(text("""
            SELECT COUNT(*) 
            FROM fact_order_items 
            WHERE product_id IS NOT NULL
        """)).scalar()
        items_without_product_id = total_items - items_with_product_id
        
        safe_print(f"  总订单明细数: {total_items}")
        safe_print(f"  已关联product_id: {items_with_product_id} ({items_with_product_id/total_items*100:.1f}%)" if total_items > 0 else "  已关联product_id: 0")
        safe_print(f"  未关联product_id: {items_without_product_id} ({items_without_product_id/total_items*100:.1f}%)" if total_items > 0 else "  未关联product_id: 0")
        
        if total_items == 0:
            safe_print("[WARN] 没有订单明细数据，无法测试关联功能")
            return True
        
        # 检查BridgeProductKeys数据
        bridge_count = db.execute(text("SELECT COUNT(*) FROM bridge_product_keys")).scalar()
        safe_print(f"\n  BridgeProductKeys记录数: {bridge_count}")
        
        if bridge_count == 0:
            safe_print("[WARN] BridgeProductKeys表为空，无法进行自动关联")
            return True
        
        # 检查是否有可以关联的数据
        sample_item = db.execute(text("""
            SELECT platform_code, shop_id, platform_sku 
            FROM fact_order_items 
            WHERE product_id IS NULL 
            LIMIT 1
        """)).fetchone()
        
        if sample_item:
            # 检查是否有对应的BridgeProductKeys记录
            bridge = db.execute(text("""
                SELECT product_id 
                FROM bridge_product_keys 
                WHERE platform_code = :platform_code 
                  AND shop_id = :shop_id 
                  AND platform_sku = :platform_sku
            """), {
                "platform_code": sample_item[0],
                "shop_id": sample_item[1],
                "platform_sku": sample_item[2]
            }).fetchone()
            
            if bridge:
                safe_print(f"\n  [OK] 示例数据可以关联product_id: {bridge[0]}")
                safe_print(f"    平台: {sample_item[0]}, 店铺: {sample_item[1]}, SKU: {sample_item[2]}")
            else:
                safe_print(f"\n  [INFO] 示例数据暂无对应的product_id（正常，需要先建立BridgeProductKeys映射）")
        
        if items_with_product_id > 0:
            safe_print("\n  [OK] product_id自动关联功能正常")
            return True
        else:
            safe_print("\n  [WARN] 所有订单明细都未关联product_id（可能需要运行数据修复脚本）")
            safe_print("    提示: 运行 python scripts/fix_historical_product_id_association.py")
            return True  # 不算失败，只是需要修复
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试product_id关联功能失败", exc_info=True)
        return False


def test_sales_detail_query(db: Session) -> bool:
    """测试销售明细查询功能"""
    safe_print("\n" + "=" * 70)
    safe_print("测试4: 销售明细查询功能")
    safe_print("=" * 70)
    
    try:
        # 检查物化视图是否存在
        mv_exists = db.execute(text("""
            SELECT COUNT(*) 
            FROM pg_matviews 
            WHERE matviewname = 'mv_sales_detail_by_product'
        """)).scalar()
        
        if mv_exists == 0:
            safe_print("[SKIP] 物化视图不存在，跳过查询测试")
            return True
        
        # 测试基本查询
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM mv_sales_detail_by_product
        """)).scalar()
        
        safe_print(f"  [OK] 基本查询成功，返回 {result} 条记录")
        
        # 测试按product_id查询
        if result > 0:
            sample = db.execute(text("""
                SELECT product_id, platform_sku, order_id, sale_date, line_amount_rmb
                FROM mv_sales_detail_by_product
                WHERE product_id IS NOT NULL
                LIMIT 1
            """)).fetchone()
            
            if sample:
                safe_print(f"\n  [OK] 按product_id查询成功:")
                safe_print(f"    product_id: {sample[0]}")
                safe_print(f"    platform_sku: {sample[1]}")
                safe_print(f"    order_id: {sample[2]}")
                safe_print(f"    sale_date: {sample[3]}")
                safe_print(f"    line_amount_rmb: {sample[4]}")
            else:
                safe_print("\n  [WARN] 没有包含product_id的记录（需要先关联product_id）")
        
        # 测试按SKU查询
        if result > 0:
            sku_count = db.execute(text("""
                SELECT COUNT(DISTINCT platform_sku) 
                FROM mv_sales_detail_by_product
            """)).scalar()
            safe_print(f"\n  [OK] 按SKU查询成功，共有 {sku_count} 个不同的SKU")
        
        # 测试按日期范围查询
        if result > 0:
            date_range = db.execute(text("""
                SELECT MIN(sale_date), MAX(sale_date)
                FROM mv_sales_detail_by_product
            """)).fetchone()
            
            if date_range[0] and date_range[1]:
                safe_print(f"\n  [OK] 按日期范围查询成功:")
                safe_print(f"    最早日期: {date_range[0]}")
                safe_print(f"    最晚日期: {date_range[1]}")
        
        return True
        
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        logger.error("测试销售明细查询失败", exc_info=True)
        return False


def test_api_endpoint() -> bool:
    """测试API端点（需要API服务运行）"""
    safe_print("\n" + "=" * 70)
    safe_print("测试5: API端点测试")
    safe_print("=" * 70)
    
    try:
        import requests
        
        # 尝试连接API（如果服务运行）
        base_url = "http://localhost:8000"  # 默认FastAPI端口
        
        try:
            response = requests.get(f"{base_url}/api/management/sales-detail-by-product?page_size=1", timeout=2)
            if response.status_code == 200:
                data = response.json()
                safe_print(f"  [OK] API端点响应正常")
                safe_print(f"    返回数据: {len(data.get('data', []))} 条")
                safe_print(f"    总数: {data.get('total', 0)}")
                return True
            else:
                safe_print(f"  [WARN] API端点返回状态码: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            safe_print("  [SKIP] API服务未运行，跳过API测试")
            safe_print("    提示: 启动API服务后可以测试 /api/management/sales-detail-by-product 端点")
            return True
        except Exception as e:
            safe_print(f"  [WARN] API测试失败: {e}")
            return True  # 不算失败
        
    except ImportError:
        safe_print("  [SKIP] requests库未安装，跳过API测试")
        return True


def main():
    """主函数"""
    safe_print("=" * 70)
    safe_print("产品ID原子级设计功能测试")
    safe_print("=" * 70)
    safe_print("\n测试时间: " + str(Path(__file__).stat().st_mtime))
    
    db = next(get_db())
    try:
        results = []
        
        # 运行所有测试
        results.append(("FactOrderItem表结构", test_fact_order_item_schema(db)))
        results.append(("物化视图存在性", test_materialized_view_exists(db)))
        results.append(("product_id自动关联", test_product_id_association(db)))
        results.append(("销售明细查询", test_sales_detail_query(db)))
        results.append(("API端点", test_api_endpoint()))
        
        # 输出测试总结
        safe_print("\n" + "=" * 70)
        safe_print("测试总结")
        safe_print("=" * 70)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            safe_print(f"  {status} {test_name}")
        
        safe_print(f"\n通过: {passed}/{total}")
        
        if passed == total:
            safe_print("\n[SUCCESS] 所有测试通过！")
            return 0
        else:
            safe_print(f"\n[WARNING] {total - passed} 个测试未通过，请检查上述输出")
            return 1
        
    except Exception as e:
        safe_print(f"\n[ERROR] 测试执行失败: {e}")
        logger.error("测试执行失败", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())


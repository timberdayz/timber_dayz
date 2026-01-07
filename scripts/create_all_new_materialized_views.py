#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量创建所有新的物化视图（v4.12.0主视图架构）

创建以下物化视图：
1. mv_order_summary - orders域主视图
2. mv_traffic_summary - traffic域主视图
3. mv_sales_detail_by_product - 产品ID级别销售明细
4. mv_inventory_by_sku - inventory域主视图（如果不存在）

使用方法：
    python scripts/create_all_new_materialized_views.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def check_view_exists(db, view_name):
    """检查物化视图是否存在"""
    result = db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_matviews 
            WHERE schemaname = 'public' AND matviewname = :view_name
        )
    """), {"view_name": view_name})
    return result.scalar()


def create_mv_order_summary(db):
    """创建mv_order_summary物化视图"""
    safe_print("\n" + "=" * 70)
    safe_print("1. 创建 mv_order_summary（orders域主视图）")
    safe_print("=" * 70)
    
    if check_view_exists(db, "mv_order_summary"):
        safe_print("[INFO] mv_order_summary 已存在，跳过创建")
        return True
    
    try:
        from scripts.create_mv_order_summary import create_mv_order_summary as create_func
        return create_func()
    except Exception as e:
        safe_print(f"[ERROR] 创建失败: {e}")
        logger.error("创建mv_order_summary失败", exc_info=True)
        return False


def create_mv_traffic_summary(db):
    """创建mv_traffic_summary物化视图"""
    safe_print("\n" + "=" * 70)
    safe_print("2. 创建 mv_traffic_summary（traffic域主视图）")
    safe_print("=" * 70)
    
    if check_view_exists(db, "mv_traffic_summary"):
        safe_print("[INFO] mv_traffic_summary 已存在，跳过创建")
        return True
    
    try:
        from scripts.create_mv_traffic_summary import create_mv_traffic_summary as create_func
        return create_func()
    except Exception as e:
        safe_print(f"[ERROR] 创建失败: {e}")
        logger.error("创建mv_traffic_summary失败", exc_info=True)
        return False


def create_mv_sales_detail_by_product(db):
    """创建mv_sales_detail_by_product物化视图"""
    safe_print("\n" + "=" * 70)
    safe_print("3. 创建 mv_sales_detail_by_product（产品ID级别销售明细）")
    safe_print("=" * 70)
    
    if check_view_exists(db, "mv_sales_detail_by_product"):
        safe_print("[INFO] mv_sales_detail_by_product 已存在，跳过创建")
        return True
    
    try:
        from scripts.create_mv_sales_detail_by_product import create_mv_sales_detail_by_product as create_func
        return create_func(db)
    except Exception as e:
        safe_print(f"[ERROR] 创建失败: {e}")
        logger.error("创建mv_sales_detail_by_product失败", exc_info=True)
        return False


def create_mv_inventory_by_sku(db):
    """创建mv_inventory_by_sku物化视图"""
    safe_print("\n" + "=" * 70)
    safe_print("4. 创建 mv_inventory_by_sku（inventory域主视图）")
    safe_print("=" * 70)
    
    if check_view_exists(db, "mv_inventory_by_sku"):
        safe_print("[INFO] mv_inventory_by_sku 已存在，跳过创建")
        return True
    
    try:
        from scripts.create_mv_inventory_by_sku_main_view import create_mv_inventory_by_sku as create_func
        return create_func()
    except Exception as e:
        safe_print(f"[ERROR] 创建失败: {e}")
        logger.error("创建mv_inventory_by_sku失败", exc_info=True)
        return False


def main():
    """主函数"""
    safe_print("=" * 70)
    safe_print("批量创建所有新的物化视图（v4.12.0主视图架构）")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        results = []
        
        # 1. 创建mv_order_summary
        results.append(("mv_order_summary", create_mv_order_summary(db)))
        
        # 2. 创建mv_traffic_summary
        results.append(("mv_traffic_summary", create_mv_traffic_summary(db)))
        
        # 3. 创建mv_sales_detail_by_product
        results.append(("mv_sales_detail_by_product", create_mv_sales_detail_by_product(db)))
        
        # 4. 创建mv_inventory_by_sku
        results.append(("mv_inventory_by_sku", create_mv_inventory_by_sku(db)))
        
        # 总结
        safe_print("\n" + "=" * 70)
        safe_print("创建结果总结")
        safe_print("=" * 70)
        
        success_count = sum(1 for _, success in results if success)
        total_count = len(results)
        
        for view_name, success in results:
            status = "[OK]" if success else "[FAILED]"
            safe_print(f"{status} {view_name}")
        
        safe_print(f"\n总计: {success_count}/{total_count} 个物化视图创建成功")
        
        if success_count == total_count:
            safe_print("\n[SUCCESS] 所有物化视图创建完成！")
            safe_print("现在可以在前端数据浏览器中看到这些新的物化视图了。")
            return 0
        else:
            safe_print("\n[WARNING] 部分物化视图创建失败，请检查错误信息")
            return 1
            
    except Exception as e:
        safe_print(f"\n[ERROR] 执行失败: {e}")
        logger.error("批量创建物化视图失败", exc_info=True)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())


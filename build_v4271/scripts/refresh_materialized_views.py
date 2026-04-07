"""
物化视图刷新脚本（v4.6.0+）
确保视图定义变更后自动刷新

使用方法:
    python scripts/refresh_materialized_views.py [view_name]
    
如果不指定view_name，将刷新所有视图
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from backend.services.materialized_view_service import MaterializedViewService
from modules.core.logger import get_logger

logger = get_logger(__name__)


def refresh_view(view_name: str = None):
    """
    刷新指定的物化视图或所有视图
    
    Args:
        view_name: 视图名称，如果为None则刷新所有视图
    """
    db = SessionLocal()
    try:
        if view_name:
            logger.info(f"[刷新视图] 开始刷新视图: {view_name}")
            # 刷新单个视图
            if view_name == MaterializedViewService.VIEW_INVENTORY_BY_SKU:
                MaterializedViewService.refresh_inventory_by_sku_view(db)
            elif view_name == MaterializedViewService.VIEW_INVENTORY_SUMMARY:
                MaterializedViewService.refresh_inventory_summary_view(db)
            elif view_name == MaterializedViewService.VIEW_PRODUCT_MANAGEMENT:
                MaterializedViewService.refresh_product_management_view(db)
            elif view_name == MaterializedViewService.VIEW_SALES_TREND:
                MaterializedViewService.refresh_sales_trend_view(db)
            elif view_name == MaterializedViewService.VIEW_TOP_PRODUCTS:
                MaterializedViewService.refresh_top_products_view(db)
            elif view_name == MaterializedViewService.VIEW_SHOP_SUMMARY:
                MaterializedViewService.refresh_shop_summary_view(db)
            else:
                logger.warning(f"[刷新视图] 未知视图名称: {view_name}")
                logger.info(f"[刷新视图] 可用视图: {MaterializedViewService.VIEW_INVENTORY_BY_SKU}, "
                           f"{MaterializedViewService.VIEW_INVENTORY_SUMMARY}, "
                           f"{MaterializedViewService.VIEW_PRODUCT_MANAGEMENT}")
                return False
            logger.info(f"[刷新视图] 视图 {view_name} 刷新完成")
        else:
            logger.info("[刷新视图] 开始刷新所有视图")
            result = MaterializedViewService.refresh_all_views(db, triggered_by="script")
            logger.info(f"[刷新视图] 所有视图刷新完成: {result}")
        return True
    except Exception as e:
        logger.error(f"[刷新视图] 刷新失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


def main():
    """主函数"""
    view_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    if view_name:
        logger.info(f"[刷新视图] 刷新指定视图: {view_name}")
    else:
        logger.info("[刷新视图] 刷新所有视图")
    
    success = refresh_view(view_name)
    
    if success:
        logger.info("[刷新视图] 刷新成功")
        sys.exit(0)
    else:
        logger.error("[刷新视图] 刷新失败")
        sys.exit(1)


if __name__ == "__main__":
    main()

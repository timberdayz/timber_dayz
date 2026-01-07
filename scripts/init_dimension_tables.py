"""
初始化维度表 - 从catalog_files自动提取
执行：python scripts/init_dimension_tables.py

v4.9.1新增：
- 自动从catalog_files提取平台和店铺
- 初始化dim_platforms和dim_shops
- 为物化视图准备维度数据
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.db import DimPlatform, DimShop
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def init_dimension_tables():
    """初始化维度表"""
    db = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("[Step 1/4] Extracting platforms from catalog_files...")
        
        # 1. 从catalog_files提取平台
        result = db.execute(text("""
            SELECT DISTINCT platform_code
            FROM catalog_files
            WHERE platform_code IS NOT NULL
            ORDER BY platform_code
        """))
        
        platform_name_map = {
            'miaoshou': '妙手ERP',
            'shopee': 'Shopee',
            'amazon': 'Amazon',
            'tiktok': 'TikTok',
            'lazada': 'Lazada'
        }
        
        platform_count = 0
        for row in result:
            platform_code = row[0]
            
            # 检查是否已存在
            existing = db.query(DimPlatform).filter(
                DimPlatform.platform_code == platform_code
            ).first()
            
            if not existing:
                platform = DimPlatform(
                    platform_code=platform_code,
                    name=platform_name_map.get(platform_code, platform_code.title()),
                    is_active=True
                )
                db.add(platform)
                platform_count += 1
                logger.info(f"  [+] Added platform: {platform_code} ({platform.name})")
            else:
                logger.info(f"  [Skip] Platform exists: {platform_code}")
        
        db.commit()
        logger.info(f"[OK] Step 1 Complete: {platform_count} new platforms inserted")
        
        # 2. 从catalog_files提取店铺
        logger.info("\n[Step 2/4] Extracting shops from catalog_files...")
        
        result = db.execute(text("""
            SELECT DISTINCT platform_code, shop_id
            FROM catalog_files
            WHERE platform_code IS NOT NULL AND shop_id IS NOT NULL
            ORDER BY platform_code, shop_id
        """))
        
        shop_count = 0
        for row in result:
            platform_code, shop_id = row[0], row[1]
            
            # 检查是否已存在
            existing = db.query(DimShop).filter(
                DimShop.platform_code == platform_code,
                DimShop.shop_id == shop_id
            ).first()
            
            if not existing:
                shop = DimShop(
                    platform_code=platform_code,
                    shop_id=shop_id,
                    shop_slug=shop_id
                )
                db.add(shop)
                shop_count += 1
                logger.info(f"  [+] Added shop: {platform_code}/{shop_id}")
            else:
                logger.info(f"  [Skip] Shop exists: {platform_code}/{shop_id}")
        
        db.commit()
        logger.info(f"[OK] Step 2 Complete: {shop_count} new shops inserted")
        
        # 3. 验证
        logger.info("\n[Step 3/4] Verifying dimension tables...")
        
        platform_total = db.execute(text("SELECT COUNT(*) FROM dim_platforms")).scalar()
        shop_total = db.execute(text("SELECT COUNT(*) FROM dim_shops")).scalar()
        
        logger.info(f"  dim_platforms: {platform_total} rows")
        logger.info(f"  dim_shops: {shop_total} rows")
        
        if platform_total == 0:
            logger.warning("[WARN] dim_platforms is still empty!")
            logger.warning("Please check if catalog_files has platform_code data")
        
        if shop_total == 0:
            logger.warning("[WARN] dim_shops is still empty!")
            logger.warning("Please check if catalog_files has shop_id data")
        
        # 4. 刷新物化视图
        logger.info("\n[Step 4/4] Refreshing materialized views...")
        
        if platform_total > 0 and shop_total > 0:
            try:
                # 刷新产品管理视图
                db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_product_management"))
                db.commit()
                
                mv_count = db.execute(text("SELECT COUNT(*) FROM mv_product_management")).scalar()
                logger.info(f"[OK] mv_product_management refreshed: {mv_count} rows")
                
            except Exception as e:
                logger.warning(f"[WARN] MV refresh failed (may need data): {e}")
        else:
            logger.warning("[SKIP] Not refreshing MVs (dimension tables still empty)")
        
        logger.info("\n" + "=" * 60)
        logger.info("[SUCCESS] Dimension table initialization complete!")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Collect product data (Data Collection → Products)")
        logger.info("2. Map fields and ingest (Field Mapping → Ingest)")
        logger.info("3. Wait for MV auto-refresh (15 min) or manual refresh")
        
        return {
            "success": True,
            "platforms_added": platform_count,
            "shops_added": shop_count,
            "platforms_total": platform_total,
            "shops_total": shop_total
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"[ERROR] Initialization failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_dimension_tables()


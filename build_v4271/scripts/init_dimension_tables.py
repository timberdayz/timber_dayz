"""
初始化维度表 - v4.19.0 方案A优化
执行：python scripts/init_dimension_tables.py

v4.19.0 更新（方案A）：
- 平台：从 catalog_files 提取（保留，平台信息相对稳定）
- 店铺：从 platform_accounts 同步（✅ 方案A：废弃从 catalog_files 提取）
- 确保 dim_shops 数据来源单一，避免混乱
- 同步所有账号（enabled状态仅影响数据采集，不影响维度表同步）
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import Optional
from backend.models.database import SessionLocal
from modules.core.db import DimPlatform, DimShop, PlatformAccount
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def sync_platform_account_to_dim_shop_sync(db, platform_account: PlatformAccount) -> Optional[DimShop]:
    """
    同步 platform_accounts 到 dim_shops（同步版本）
    
    用于 init_dimension_tables.py 脚本，使用同步 Session。
    
    Args:
        db: 同步数据库会话
        platform_account: 平台账号对象
        
    Returns:
        创建的或更新的 DimShop 对象，如果 shop_id 为空则返回 None
    """
    # 确定 shop_id（优先使用 shop_id，其次 account_id）
    shop_id = platform_account.shop_id or platform_account.account_id
    if not shop_id:
        logger.warning(f"[ShopSync] 账号 {platform_account.account_id} 没有 shop_id，跳过同步")
        return None
    
    # 规范化 platform_code 为小写（数据库标准格式）
    platform_code_raw = platform_account.platform
    platform_code = platform_code_raw.lower() if platform_code_raw else None
    
    if not platform_code:
        logger.warning(f"[ShopSync] 账号 {platform_account.account_id} 没有 platform，跳过同步")
        return None
    
    # 1. 确保平台存在（先按 platform_code 查找）
    platform = db.query(DimPlatform).filter(
        DimPlatform.platform_code == platform_code
    ).first()
    
    if not platform:
        # 如果 platform_code 不存在，检查 name 是否已存在（处理大小写不一致的情况）
        platform_name_map = {
            'miaoshou': '妙手ERP',
            'shopee': 'Shopee',
            'amazon': 'Amazon',
            'tiktok': 'TikTok',
            'lazada': 'Lazada'
        }
        expected_name = platform_name_map.get(platform_code, platform_code.title())
        
        # 检查是否有相同 name 但不同 platform_code 的记录
        existing_by_name = db.query(DimPlatform).filter(
            DimPlatform.name == expected_name
        ).first()
        
        if existing_by_name:
            # 如果 name 已存在，使用已存在的平台记录
            platform = existing_by_name
            logger.info(f"[ShopSync] 找到已存在的平台记录（通过name）: {platform.platform_code} ({platform.name})")
        else:
            # 创建新平台记录
            platform = DimPlatform(
                platform_code=platform_code,
                name=expected_name,
                is_active=True
            )
            db.add(platform)
            db.flush()
            logger.info(f"[ShopSync] 自动创建平台记录: {platform_code} ({platform.name})")
    
    # 2. 检查店铺是否存在
    shop = db.query(DimShop).filter(
        DimShop.platform_code == platform_code,
        DimShop.shop_id == shop_id
    ).first()
    
    if shop:
        # 更新现有店铺信息
        shop.shop_name = platform_account.store_name or shop.shop_name
        shop.shop_slug = platform_account.shop_id or shop.shop_slug or shop_id
        shop.region = platform_account.shop_region or shop.region
        shop.currency = platform_account.currency or shop.currency
        shop.updated_at = datetime.now(timezone.utc)
        logger.info(f"[ShopSync] 更新店铺记录: {platform_code}/{shop_id} ({shop.shop_name})")
    else:
        # 创建新店铺记录
        shop = DimShop(
            platform_code=platform_code,
            shop_id=shop_id,
            shop_slug=platform_account.shop_id or shop_id,
            shop_name=platform_account.store_name or platform_account.account_alias or shop_id,
            region=platform_account.shop_region,
            currency=platform_account.currency or 'CNY',
            timezone=None  # 暂时不设置时区
        )
        db.add(shop)
        logger.info(f"[ShopSync] 自动创建店铺记录: {platform_code}/{shop_id} ({shop.shop_name})")
    
    db.flush()
    return shop

def init_dimension_tables():
    """初始化维度表（v4.19.0 方案A）"""
    db = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("[v4.19.0 方案A] 初始化维度表")
        logger.info("=" * 60)
        
        # Step 1: 从 catalog_files 提取平台（保留，平台信息相对稳定）
        logger.info("\n[Step 1/4] Extracting platforms from catalog_files...")
        
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
        
        # Step 2: ✅ 方案A - 从 platform_accounts 同步店铺（废弃从 catalog_files 提取）
        logger.info("\n[Step 2/4] Syncing shops from platform_accounts (Plan A)...")
        logger.info("  [Info] 数据来源：platform_accounts（用户手动配置，最高级配置管理）")
        logger.info("  [Info] 同步所有账号（enabled状态仅影响数据采集，不影响维度表同步）")
        
        # 从 platform_accounts 读取所有账号（不区分enabled状态）
        # enabled状态仅表示是否进行数据采集，不影响dim_shops维度表的完整性
        accounts = db.query(PlatformAccount).all()
        
        shop_count = 0
        skipped_count = 0
        
        for account in accounts:
            # 确定 shop_id（优先使用 shop_id，其次 account_id）
            shop_id = account.shop_id or account.account_id
            if not shop_id:
                skipped_count += 1
                logger.debug(f"  [Skip] 账号 {account.account_id} 没有 shop_id，跳过")
                continue
            
            # 使用同步版本的同步函数
            shop = sync_platform_account_to_dim_shop_sync(db, account)
            if shop:
                shop_count += 1
            else:
                skipped_count += 1
        
        db.commit()
        logger.info(f"[OK] Step 2 Complete: {shop_count} shops synced, {skipped_count} skipped")
        
        # Step 3: 验证
        logger.info("\n[Step 3/4] Verifying dimension tables...")
        
        platform_total = db.execute(text("SELECT COUNT(*) FROM dim_platforms")).scalar()
        shop_total = db.execute(text("SELECT COUNT(*) FROM dim_shops")).scalar()
        account_total = db.execute(text("SELECT COUNT(*) FROM core.platform_accounts")).scalar()
        account_enabled = db.execute(text("SELECT COUNT(*) FROM core.platform_accounts WHERE enabled = true")).scalar()
        
        logger.info(f"  dim_platforms: {platform_total} rows")
        logger.info(f"  dim_shops: {shop_total} rows")
        logger.info(f"  platform_accounts (total): {account_total} rows")
        logger.info(f"  platform_accounts (enabled): {account_enabled} rows")
        
        if platform_total == 0:
            logger.warning("[WARN] dim_platforms is still empty!")
            logger.warning("Please check if catalog_files has platform_code data")
        
        if shop_total == 0:
            logger.warning("[WARN] dim_shops is still empty!")
            logger.warning("Please ensure platform_accounts has accounts with shop_id set")
            logger.warning("You can add accounts via: Account Management page")
        
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
        logger.info("\n方案A优化说明：")
        logger.info("  [OK] dim_shops 数据来源：platform_accounts（用户手动配置）")
        logger.info("  [OK] 废弃从 catalog_files 提取店铺的逻辑")
        logger.info("  [OK] 数据来源单一，避免混乱")
        logger.info("  [OK] 同步所有账号（enabled仅影响数据采集）")
        logger.info("\nNext steps:")
        logger.info("1. Add accounts via Account Management page (if needed)")
        logger.info("2. Collect product data (Data Collection → Products)")
        logger.info("3. Map fields and ingest (Field Mapping → Ingest)")
        logger.info("4. Wait for MV auto-refresh (15 min) or manual refresh")
        
        return {
            "success": True,
            "platforms_added": platform_count,
            "shops_added": shop_count,
            "shops_skipped": skipped_count,
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

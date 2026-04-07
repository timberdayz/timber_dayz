#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
店铺同步服务 (v4.19.0)

功能:
- 自动同步 platform_accounts 到 dim_shops
- 确保数据仓库维度表的完整性
- 支持创建和更新操作
"""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from modules.core.db import PlatformAccount, DimShop, DimPlatform
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def sync_platform_account_to_dim_shop(
    db: AsyncSession,
    platform_account: PlatformAccount
) -> Optional[DimShop]:
    """
    同步 platform_accounts 到 dim_shops
    
    如果店铺不存在,自动创建;如果存在,更新店铺信息。
    确保数据仓库维度表的完整性,支持外键约束。
    
    Args:
        db: 数据库会话
        platform_account: 平台账号对象
        
    Returns:
        创建的或更新的 DimShop 对象,如果 shop_id 为空则返回 None
        
    Raises:
        Exception: 数据库操作失败时抛出异常
    """
    # 确定 shop_id(优先使用 shop_id,其次 account_id)
    shop_id = platform_account.shop_id or platform_account.account_id
    if not shop_id:
        logger.warning(f"[ShopSync] 账号 {platform_account.account_id} 没有 shop_id,跳过同步")
        return None
    
    platform_code = platform_account.platform
    
    # 1. 确保平台存在
    platform = (await db.execute(
        select(DimPlatform).where(DimPlatform.platform_code == platform_code)
    )).scalar_one_or_none()
    
    if not platform:
        # 创建平台记录
        platform_name_map = {
            'miaoshou': '妙手ERP',
            'shopee': 'Shopee',
            'amazon': 'Amazon',
            'tiktok': 'TikTok',
            'lazada': 'Lazada'
        }
        platform = DimPlatform(
            platform_code=platform_code,
            name=platform_name_map.get(platform_code, platform_code.title()),
            is_active=True
        )
        db.add(platform)
        await db.flush()
        logger.info(f"[ShopSync] 自动创建平台记录: {platform_code} ({platform.name})")
    
    # 2. 检查店铺是否存在
    shop = (await db.execute(
        select(DimShop).where(
            DimShop.platform_code == platform_code,
            DimShop.shop_id == shop_id
        )
    )).scalar_one_or_none()
    
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
    
    await db.flush()
    return shop

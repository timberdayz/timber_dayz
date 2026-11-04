#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
店铺同步服务 (v4.19.0)

功能:
- 自动同步 platform_accounts 到 dim_shops（旧模型，已被 shop_accounts 取代）
- 同步 shop_accounts 到 dim_shops（**当前权威来源**）
- 确保数据仓库维度表的完整性
- 支持创建和更新操作
"""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from modules.core.db import PlatformAccount, DimShop, DimPlatform, ShopAccount
from modules.core.logger import get_logger

logger = get_logger(__name__)


def _is_missing_relation_error(exc: BaseException) -> bool:
    """这个异常是不是「表/视图不存在」。

    只放过这一类：其它数据库错误必须照常抛出（不能把真故障吞成告警）。
    """
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "no such table" in message
        or "does not exist" in message
        or "undefined table" in message
    )


#: 平台维度缺失时自动补的显示名（与旧同步同一套映射）。
_PLATFORM_NAME_MAP = {
    "miaoshou": "妙手ERP",
    "shopee": "Shopee",
    "amazon": "Amazon",
    "tiktok": "TikTok",
    "lazada": "Lazada",
}


def resolve_dim_shop_id(shop_account: ShopAccount) -> str:
    """派生 ``dim_shops.shop_id``（店铺粒度的展示键）。

    **必须与语义层逐字一致** —— 语义层的身份解析用的是：

        resolved_shop_id = COALESCE(
            NULLIF(TRIM(COALESCE(platform_shop_id,'')),''),
            NULLIF(TRIM(COALESCE(shop_account_id,'')),''),
            id::text
        )

    派生不一致 ⇒ 看板显示名的 JOIN 永远落空 ⇒ 维度表等于没有。
    （对应 SQL：``current_migrations/versions/20261107_align_dim_shops_with_shop_accounts.py``）
    """
    return (
        str(shop_account.platform_shop_id or "").strip()
        or str(shop_account.shop_account_id or "").strip()
        or str(shop_account.id)
    )


async def sync_shop_account_to_dim_shop(
    db: AsyncSession,
    shop_account: ShopAccount,
) -> Optional[DimShop]:
    """把一个店铺账号同步到 ``core.dim_shops``（展示维度表）。

    维度表的**权威来源是店铺账号**（``core.shop_accounts``）：看板的显示名
    JOIN 读它，绩效/提成/告警等业务表也以它为外键目标。

    幂等：按主键 upsert，重复调用不会产生重复行。

    **展示维度表缺失不阻断业务**：某些环境（例如只建了业务表的测试库）里
    ``core.dim_platforms`` / ``core.dim_shops`` 并不存在 —— 此时只告警不抛错，
    账号本身该存还是要存。

    Returns:
        同步后的维度行；平台维度不存在或表缺失时返回 None。
    """
    platform_code = str(shop_account.platform or "").strip().lower()
    if not platform_code:
        return None

    try:
        platform = (
            await db.execute(
                select(DimPlatform).where(DimPlatform.platform_code == platform_code)
            )
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        if not _is_missing_relation_error(exc):
            raise
        logger.warning("[ShopSync] 展示维度表不可用，跳过 dim_shops 同步: %s", exc)
        return None

    if platform is None:
        # 平台维度缺失就补一条 —— 与旧同步（``sync_platform_account_to_dim_shop``）
        # 行为一致：不补的话维度表永远建不出第一行。
        platform = DimPlatform(
            platform_code=platform_code,
            name=_PLATFORM_NAME_MAP.get(platform_code, platform_code.title()),
            is_active=True,
        )
        db.add(platform)
        await db.flush()
        logger.info(
            "[ShopSync] 自动创建平台维度: {platform} ({name})".format(
                platform=platform_code, name=platform.name
            )
        )

    shop_id = resolve_dim_shop_id(shop_account)
    if not shop_id:
        return None

    try:
        shop = (
            await db.execute(
                select(DimShop).where(
                    DimShop.platform_code == platform_code,
                    DimShop.shop_id == shop_id,
                )
            )
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        if not _is_missing_relation_error(exc):
            raise
        logger.warning("[ShopSync] 展示维度表不可用，跳过 dim_shops 同步: %s", exc)
        return None

    store_name = str(shop_account.store_name or "").strip() or None
    region = str(shop_account.shop_region or "").strip() or None
    slug = str(shop_account.shop_account_id or "").strip() or None
    is_active = bool(shop_account.enabled) if shop_account.enabled is not None else True

    if shop is None:
        shop = DimShop(
            platform_code=platform_code,
            shop_id=shop_id,
            shop_slug=slug,
            shop_name=store_name,
            region=region,
            currency="CNY",
            is_active=is_active,
        )
        db.add(shop)
        await db.flush()
        logger.info(
            "[ShopSync] 新建 dim_shops 行: {platform}/{shop_id} ({name})".format(
                platform=platform_code, shop_id=shop_id, name=store_name
            )
        )
        return shop

    shop.shop_slug = slug
    shop.shop_name = store_name
    shop.region = region
    shop.is_active = is_active
    shop.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return shop


async def sync_platform_account_to_dim_shop(
    db: AsyncSession, platform_account: PlatformAccount
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
        logger.warning(
            f"[ShopSync] 账号 {platform_account.account_id} 没有 shop_id,跳过同步"
        )
        return None

    platform_code = platform_account.platform

    # 1. 确保平台存在
    platform = (
        await db.execute(
            select(DimPlatform).where(DimPlatform.platform_code == platform_code)
        )
    ).scalar_one_or_none()

    if not platform:
        # 创建平台记录
        platform_name_map = {
            "miaoshou": "妙手ERP",
            "shopee": "Shopee",
            "amazon": "Amazon",
            "tiktok": "TikTok",
            "lazada": "Lazada",
        }
        platform = DimPlatform(
            platform_code=platform_code,
            name=platform_name_map.get(platform_code, platform_code.title()),
            is_active=True,
        )
        db.add(platform)
        await db.flush()
        logger.info(f"[ShopSync] 自动创建平台记录: {platform_code} ({platform.name})")

    # 2. 检查店铺是否存在
    shop = (
        await db.execute(
            select(DimShop).where(
                DimShop.platform_code == platform_code, DimShop.shop_id == shop_id
            )
        )
    ).scalar_one_or_none()

    if shop:
        # 更新现有店铺信息
        shop.shop_name = platform_account.store_name or shop.shop_name
        shop.shop_slug = platform_account.shop_id or shop.shop_slug or shop_id
        shop.region = platform_account.shop_region or shop.region
        shop.currency = platform_account.currency or shop.currency
        shop.updated_at = datetime.now(timezone.utc)
        logger.info(
            f"[ShopSync] 更新店铺记录: {platform_code}/{shop_id} ({shop.shop_name})"
        )
    else:
        # 创建新店铺记录
        shop = DimShop(
            platform_code=platform_code,
            shop_id=shop_id,
            shop_slug=platform_account.shop_id or shop_id,
            shop_name=platform_account.store_name
            or platform_account.account_alias
            or shop_id,
            region=platform_account.shop_region,
            currency=platform_account.currency or "CNY",
            timezone=None,  # 暂时不设置时区
        )
        db.add(shop)
        logger.info(
            f"[ShopSync] 自动创建店铺记录: {platform_code}/{shop_id} ({shop.shop_name})"
        )

    await db.flush()
    return shop

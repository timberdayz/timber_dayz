from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import PlatformShopDiscovery, ShopAccount


class PlatformShopDiscoveryService:
    async def confirm_discovery(
        self,
        db: AsyncSession,
        discovery_id: int,
        shop_account_id: str,
    ) -> PlatformShopDiscovery:
        discovery = (
            await db.execute(
                select(PlatformShopDiscovery).where(PlatformShopDiscovery.id == discovery_id)
            )
        ).scalar_one_or_none()
        if discovery is None:
            raise ValueError("platform shop discovery not found")

        shop_account = (
            await db.execute(
                select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
            )
        ).scalar_one_or_none()
        if shop_account is None:
            raise ValueError("shop account not found")

        shop_account.platform_shop_id = discovery.detected_platform_shop_id
        shop_account.platform_shop_id_status = "manual_confirmed"
        discovery.status = "manual_confirmed"

        await db.commit()
        await db.refresh(discovery)
        return discovery


_platform_shop_discovery_service: PlatformShopDiscoveryService | None = None


def get_platform_shop_discovery_service() -> PlatformShopDiscoveryService:
    global _platform_shop_discovery_service
    if _platform_shop_discovery_service is None:
        _platform_shop_discovery_service = PlatformShopDiscoveryService()
    return _platform_shop_discovery_service

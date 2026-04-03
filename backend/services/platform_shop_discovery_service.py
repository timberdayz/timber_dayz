from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.platform_shop_discovery import (
    PlatformShopDiscoveryCreateShopAccountRequest,
)
from modules.core.db import PlatformShopDiscovery, ShopAccount


class PlatformShopDiscoveryService:
    async def record_runtime_discovery(
        self,
        db: AsyncSession,
        *,
        platform: str,
        main_account_id: str,
        shop_account_id: str,
        detected_store_name: str | None,
        detected_platform_shop_id: str | None,
        detected_region: str | None,
        raw_payload: dict | None = None,
    ) -> PlatformShopDiscovery | None:
        if not detected_platform_shop_id:
            return None

        discovery = PlatformShopDiscovery(
            platform=platform,
            main_account_id=main_account_id,
            detected_store_name=detected_store_name,
            detected_platform_shop_id=detected_platform_shop_id,
            detected_region=detected_region,
            candidate_shop_account_ids=[shop_account_id],
            status="detected_single_bound",
            raw_payload=raw_payload or {},
        )
        db.add(discovery)

        shop_account = (
            await db.execute(
                select(ShopAccount).where(ShopAccount.shop_account_id == shop_account_id)
            )
        ).scalar_one_or_none()
        if shop_account is not None:
            shop_account.platform_shop_id = detected_platform_shop_id
            shop_account.platform_shop_id_status = "auto_bound"

        await db.commit()
        await db.refresh(discovery)
        return discovery

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

    async def create_shop_account_from_discovery(
        self,
        db: AsyncSession,
        discovery_id: int,
        payload: PlatformShopDiscoveryCreateShopAccountRequest,
    ) -> PlatformShopDiscovery:
        discovery = (
            await db.execute(
                select(PlatformShopDiscovery).where(PlatformShopDiscovery.id == discovery_id)
            )
        ).scalar_one_or_none()
        if discovery is None:
            raise ValueError("platform shop discovery not found")

        existing_shop = (
            await db.execute(
                select(ShopAccount).where(ShopAccount.shop_account_id == payload.shop_account_id)
            )
        ).scalar_one_or_none()
        if existing_shop is not None:
            raise ValueError("shop account already exists")

        shop_account = ShopAccount(
            platform=discovery.platform,
            shop_account_id=payload.shop_account_id,
            main_account_id=discovery.main_account_id,
            store_name=payload.store_name,
            platform_shop_id=discovery.detected_platform_shop_id,
            platform_shop_id_status="manual_confirmed"
            if discovery.detected_platform_shop_id
            else "missing",
            shop_region=payload.shop_region or discovery.detected_region,
            shop_type=payload.shop_type,
            enabled=True,
            notes=payload.notes,
            created_by="system",
            updated_by="system",
        )
        db.add(shop_account)

        discovery.candidate_shop_account_ids = [payload.shop_account_id]
        discovery.status = "created_shop_account"
        discovery.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(discovery)
        return discovery


_platform_shop_discovery_service: PlatformShopDiscoveryService | None = None


def get_platform_shop_discovery_service() -> PlatformShopDiscoveryService:
    global _platform_shop_discovery_service
    if _platform_shop_discovery_service is None:
        _platform_shop_discovery_service = PlatformShopDiscoveryService()
    return _platform_shop_discovery_service

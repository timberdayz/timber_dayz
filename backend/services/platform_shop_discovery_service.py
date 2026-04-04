from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.platform_shop_discovery import (
    PlatformShopDiscoveryCreateShopAccountRequest,
)
from backend.schemas.shop_discovery import (
    ShopDiscoveryEvidencePayload,
    ShopDiscoveryFieldSource,
    ShopDiscoveryMatchPayload,
    ShopDiscoveryPayload,
    ShopDiscoveryRunResponse,
)
from modules.core.db import PlatformShopDiscovery, ShopAccount, ShopAccountAlias


class PlatformShopDiscoveryService:
    @staticmethod
    def _normalize_alias(value: str | None) -> str:
        return " ".join(str(value or "").strip().lower().split())

    async def _candidate_shop_account_ids(
        self,
        db: AsyncSession,
        *,
        platform: str,
        detected_store_name: str | None,
        detected_platform_shop_id: str | None,
        detected_region: str | None,
    ) -> list[str]:
        candidates: list[str] = []

        if detected_platform_shop_id:
            result = await db.execute(
                select(ShopAccount.shop_account_id).where(
                    func.lower(ShopAccount.platform) == platform.lower(),
                    ShopAccount.platform_shop_id == detected_platform_shop_id,
                    ShopAccount.enabled == True,
                )
            )
            candidates.extend(result.scalars().all())

        if detected_store_name:
            normalized_alias = self._normalize_alias(detected_store_name)
            alias_result = await db.execute(
                select(ShopAccount.shop_account_id)
                .join(ShopAccountAlias, ShopAccountAlias.shop_account_id == ShopAccount.id)
                .where(
                    func.lower(ShopAccountAlias.platform) == platform.lower(),
                    ShopAccountAlias.alias_normalized == normalized_alias,
                    ShopAccountAlias.is_active == True,
                    ShopAccount.enabled == True,
                )
            )
            candidates.extend(alias_result.scalars().all())

            shop_stmt = select(ShopAccount.shop_account_id).where(
                func.lower(ShopAccount.platform) == platform.lower(),
                ShopAccount.store_name == detected_store_name,
                ShopAccount.enabled == True,
            )
            if detected_region:
                shop_stmt = shop_stmt.where(ShopAccount.shop_region == detected_region)
            shop_result = await db.execute(shop_stmt)
            candidates.extend(shop_result.scalars().all())

        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

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

    async def record_manual_discovery(
        self,
        db: AsyncSession,
        *,
        platform: str,
        main_account_id: str,
        detected_store_name: str | None,
        detected_platform_shop_id: str | None,
        detected_region: str | None,
        raw_payload: dict | None,
        confidence: float,
        source: dict[str, str | None],
        screenshot_path: str | None,
    ) -> ShopDiscoveryRunResponse:
        candidates = await self._candidate_shop_account_ids(
            db,
            platform=platform,
            detected_store_name=detected_store_name,
            detected_platform_shop_id=detected_platform_shop_id,
            detected_region=detected_region,
        )

        if len(candidates) == 1:
            status = "auto_bound"
        elif len(candidates) > 1:
            status = "pending_confirm"
        elif detected_store_name or detected_platform_shop_id:
            status = "no_match"
        else:
            status = "failed"

        persisted_status = {
            "auto_bound": "auto_bound",
            "pending_confirm": "pending_confirm",
            "no_match": "detected",
            "failed": "failed",
        }.get(status, "detected")

        discovery_record = PlatformShopDiscovery(
            platform=platform,
            main_account_id=main_account_id,
            detected_store_name=detected_store_name,
            detected_platform_shop_id=detected_platform_shop_id,
            detected_region=detected_region,
            candidate_shop_account_ids=candidates,
            status=persisted_status,
            raw_payload={
                **(raw_payload or {}),
                "source": source,
                "confidence": confidence,
                "screenshot_path": screenshot_path,
            },
        )
        db.add(discovery_record)

        if status == "auto_bound":
            shop_account = (
                await db.execute(
                    select(ShopAccount).where(ShopAccount.shop_account_id == candidates[0])
                )
            ).scalar_one_or_none()
            if shop_account is not None and detected_platform_shop_id:
                shop_account.platform_shop_id = detected_platform_shop_id
                shop_account.platform_shop_id_status = "auto_bound"
                discovery_record.status = "auto_bound"

        await db.commit()
        await db.refresh(discovery_record)

        return ShopDiscoveryRunResponse(
            success=status != "failed",
            platform=platform,
            main_account_id=main_account_id,
            mode="current_only",
            discovery=ShopDiscoveryPayload(
                detected_store_name=detected_store_name,
                detected_platform_shop_id=detected_platform_shop_id,
                detected_region=detected_region,
                current_url=(raw_payload or {}).get("current_url"),
                source=ShopDiscoveryFieldSource(**source),
                confidence=confidence,
            ),
            match=ShopDiscoveryMatchPayload(
                status=status,
                shop_account_id=candidates[0] if len(candidates) == 1 else None,
                candidate_count=len(candidates),
            ),
            evidence=ShopDiscoveryEvidencePayload(screenshot_path=screenshot_path),
        )

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

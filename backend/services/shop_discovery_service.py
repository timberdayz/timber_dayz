from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from backend.schemas.shop_discovery import (
    ShopDiscoveryEvidencePayload,
    ShopDiscoveryFieldSource,
    ShopDiscoveryMatchPayload,
    ShopDiscoveryPayload,
    ShopDiscoveryRunResponse,
)
from backend.services.platform_shop_discovery_service import (
    get_platform_shop_discovery_service,
)
from modules.core.db import MainAccount


class ShopDiscoveryService:
    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize_region(value: Any) -> str | None:
        text = str(value or "").strip().upper()
        return text or None

    def extract_current_shop_context(
        self,
        *,
        platform: str,
        current_url: str,
        dom_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dom_snapshot = dom_snapshot or {}
        parsed = urlparse(str(current_url or ""))
        query = parse_qs(parsed.query)

        platform_shop_id = None
        platform_shop_id_source = None
        for key in ("cnsc_shop_id", "shop_id"):
            values = query.get(key) or []
            if values and self._normalize_text(values[0]):
                platform_shop_id = self._normalize_text(values[0])
                platform_shop_id_source = "url"
                break

        region = None
        region_source = None
        for key in ("shop_region", "region"):
            values = query.get(key) or []
            if values and self._normalize_region(values[0]):
                region = self._normalize_region(values[0])
                region_source = "url"
                break

        store_name = self._normalize_text(dom_snapshot.get("store_name"))
        store_name_source = "dom" if store_name else None

        if region is None:
            region = self._normalize_region(dom_snapshot.get("region"))
            region_source = "dom" if region else None

        if platform_shop_id and (store_name or region):
            confidence = 0.95
        elif store_name and region:
            confidence = 0.8
        elif store_name:
            confidence = 0.6
        else:
            confidence = 0.0

        return {
            "platform": str(platform or "").strip().lower(),
            "detected_store_name": store_name,
            "detected_platform_shop_id": platform_shop_id,
            "detected_region": region,
            "current_url": self._normalize_text(current_url),
            "source": {
                "platform_shop_id": platform_shop_id_source,
                "store_name": store_name_source,
                "region": region_source,
            },
            "confidence": confidence,
        }

    async def _capture_runtime_snapshot(
        self,
        db,  # noqa: ANN001
        *,
        platform: str,
        main_account_id: str,
        request,  # noqa: ANN001
    ) -> dict[str, Any]:
        result = await db.execute(
            select(MainAccount).where(MainAccount.main_account_id == main_account_id)
        )
        main_account = result.scalar_one_or_none()
        if main_account is None:
            raise ValueError("main account not found")

        return {
            "current_url": main_account.login_url or "",
            "dom_snapshot": {
                "store_name": None,
                "region": request.expected_region,
            },
            "screenshot_path": None,
        }

    async def run_current_discovery(
        self,
        db,  # noqa: ANN001
        *,
        platform: str,
        main_account_id: str,
        request,  # noqa: ANN001
    ) -> ShopDiscoveryRunResponse:
        snapshot = await self._capture_runtime_snapshot(
            db,
            platform=platform,
            main_account_id=main_account_id,
            request=request,
        )
        discovery = self.extract_current_shop_context(
            platform=platform,
            current_url=snapshot.get("current_url", ""),
            dom_snapshot=snapshot.get("dom_snapshot") or {},
        )

        service = get_platform_shop_discovery_service()
        return await service.record_manual_discovery(
            db,
            platform=str(platform or "").lower(),
            main_account_id=main_account_id,
            detected_store_name=discovery["detected_store_name"],
            detected_platform_shop_id=discovery["detected_platform_shop_id"],
            detected_region=discovery["detected_region"],
            raw_payload={"current_url": discovery["current_url"]},
            confidence=discovery["confidence"],
            source=discovery["source"],
            screenshot_path=snapshot.get("screenshot_path"),
        )


_shop_discovery_service: ShopDiscoveryService | None = None


def get_shop_discovery_service() -> ShopDiscoveryService:
    global _shop_discovery_service
    if _shop_discovery_service is None:
        _shop_discovery_service = ShopDiscoveryService()
    return _shop_discovery_service

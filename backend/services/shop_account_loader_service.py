#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.encryption_service import get_encryption_service
from modules.core.db import MainAccount, ShopAccount, ShopAccountCapability
from modules.core.logger import get_logger

logger = get_logger(__name__)


class ShopAccountLoaderService:
    def __init__(self) -> None:
        self.encryption_service = get_encryption_service()

    def _decrypt_password(self, encrypted: str) -> str:
        return self.encryption_service.decrypt_password(encrypted)

    def _normalize_login_url(self, login_url: Optional[str]) -> str:
        raw = str(login_url or "").strip()
        if not raw:
            return ""
        try:
            parsed = urlparse(raw)
            if parsed.netloc:
                return f"{parsed.scheme or 'https'}://{parsed.netloc}"
        except Exception:
            pass
        return raw

    def _build_payload(
        self,
        main_account: MainAccount,
        shop_account: ShopAccount,
        capabilities: dict[str, bool],
    ) -> Dict[str, Any]:
        plaintext_password = self._decrypt_password(main_account.password_encrypted)
        normalized_login_url = self._normalize_login_url(main_account.login_url)
        compat_account = {
            "account_id": shop_account.shop_account_id,
            "main_account_id": main_account.main_account_id,
            "platform": (shop_account.platform or main_account.platform or "").lower(),
            "store_name": shop_account.store_name,
            "shop_id": shop_account.platform_shop_id or "",
            "shop_region": shop_account.shop_region or "",
            "shop_type": shop_account.shop_type or "",
            "username": main_account.username,
            "password": plaintext_password,
            "login_url": normalized_login_url,
            "enabled": shop_account.enabled,
            "capabilities": capabilities,
        }
        return {
            "main_account": {
                "id": main_account.id,
                "platform": main_account.platform,
                "main_account_id": main_account.main_account_id,
                "username": main_account.username,
                "password": plaintext_password,
                "login_url": normalized_login_url,
                "enabled": main_account.enabled,
                "notes": main_account.notes or "",
            },
            "shop_context": {
                "id": shop_account.id,
                "platform": shop_account.platform,
                "shop_account_id": shop_account.shop_account_id,
                "main_account_id": shop_account.main_account_id,
                "store_name": shop_account.store_name,
                "platform_shop_id": shop_account.platform_shop_id,
                "platform_shop_id_status": shop_account.platform_shop_id_status,
                "shop_region": shop_account.shop_region or "",
                "shop_type": shop_account.shop_type or "",
                "enabled": shop_account.enabled,
                "notes": shop_account.notes or "",
            },
            "capabilities": capabilities,
            "compat_account": compat_account,
        }

    async def load_shop_account_async(
        self, shop_account_id: str, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        shop_result = await db.execute(
            select(ShopAccount).where(
                ShopAccount.shop_account_id == shop_account_id,
                ShopAccount.enabled == True,
            )
        )
        shop_account = shop_result.scalar_one_or_none()
        if shop_account is None:
            logger.warning("Shop account %s not found or disabled", shop_account_id)
            return None

        main_result = await db.execute(
            select(MainAccount).where(
                MainAccount.main_account_id == shop_account.main_account_id,
                MainAccount.platform == shop_account.platform,
                MainAccount.enabled == True,
            )
        )
        main_account = main_result.scalar_one_or_none()
        if main_account is None:
            logger.warning(
                "Main account %s not found or disabled for shop account %s",
                shop_account.main_account_id,
                shop_account_id,
            )
            return None

        capability_result = await db.execute(
            select(ShopAccountCapability).where(
                ShopAccountCapability.shop_account_id == shop_account.id
            )
        )
        capabilities = {
            row.data_domain: bool(row.enabled)
            for row in capability_result.scalars().all()
        }

        return self._build_payload(main_account, shop_account, capabilities)


_shop_account_loader_service: Optional[ShopAccountLoaderService] = None


def get_shop_account_loader_service() -> ShopAccountLoaderService:
    global _shop_account_loader_service
    if _shop_account_loader_service is None:
        _shop_account_loader_service = ShopAccountLoaderService()
    return _shop_account_loader_service

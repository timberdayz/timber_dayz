#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.services.encryption_service import get_encryption_service
from modules.core.db import MainAccount, ShopAccount, ShopAccountCapability
from modules.core.logger import get_logger

logger = get_logger(__name__)


class AccountLoaderService:
    """Compatibility loader backed by canonical main/shop account tables."""

    def __init__(self):
        self.encryption_service = get_encryption_service()

    def _decrypt_password(self, encrypted: str) -> Optional[str]:
        try:
            return self.encryption_service.decrypt_password(encrypted)
        except Exception as e:
            logger.error(f"解密密码失败: {e}")
            return None

    @staticmethod
    def _extract_legacy_shop_extra(shop: ShopAccount) -> Dict:
        data = shop.extra_config or {}
        return {
            "proxy_required": bool(data.get("legacy_proxy_required", False)),
            "currency": data.get("legacy_currency", "CNY"),
            "region": data.get("legacy_region", "CN"),
            "email": data.get("legacy_email", ""),
            "phone": data.get("legacy_phone", ""),
            "login_flags": data.get("login_flags", {}),
        }

    def _build_account_dict(
        self,
        main_account: MainAccount,
        shop_account: ShopAccount,
        capabilities: Dict[str, bool],
    ) -> Optional[Dict]:
        password = self._decrypt_password(main_account.password_encrypted)
        if password is None:
            return None

        legacy = self._extract_legacy_shop_extra(shop_account)
        return {
            "account_id": shop_account.shop_account_id,
            "main_account_id": main_account.main_account_id,
            "platform": (shop_account.platform or main_account.platform or "unknown").lower(),
            "store_name": shop_account.store_name,
            "username": main_account.username,
            "password": password,
            "login_url": main_account.login_url or "",
            "email": legacy["email"],
            "phone": legacy["phone"],
            "region": legacy["region"],
            "currency": legacy["currency"],
            "shop_type": shop_account.shop_type or "",
            "shop_region": shop_account.shop_region or "",
            "shop_id": shop_account.platform_shop_id or "",
            "parent_account": main_account.main_account_id,
            "enabled": shop_account.enabled,
            "proxy_required": legacy["proxy_required"],
            "notes": shop_account.notes or "",
            "capabilities": capabilities,
            "another_name": "",
            "account_alias": "",
            "E-mail": legacy["email"],
            "Email account": legacy["email"],
            "Email password": "",
            "Email address": "",
            "login_flags": legacy["login_flags"],
        }

    async def _load_capabilities_async(
        self, shop_account_id: int, db: AsyncSession
    ) -> Dict[str, bool]:
        result = await db.execute(
            select(ShopAccountCapability).where(
                ShopAccountCapability.shop_account_id == shop_account_id
            )
        )
        return {row.data_domain: bool(row.enabled) for row in result.scalars().all()}

    def _load_capabilities_sync(
        self, shop_account_id: int, db: Session
    ) -> Dict[str, bool]:
        rows = (
            db.query(ShopAccountCapability)
            .filter(ShopAccountCapability.shop_account_id == shop_account_id)
            .all()
        )
        return {row.data_domain: bool(row.enabled) for row in rows}

    async def load_account_async(self, account_id: str, db: AsyncSession) -> Optional[Dict]:
        result = await db.execute(
            select(ShopAccount).where(
                ShopAccount.shop_account_id == account_id,
                ShopAccount.enabled == True,
            )
        )
        shop_account = result.scalar_one_or_none()
        if not shop_account:
            logger.warning(f"账号 {account_id} 未找到或未启用")
            return None

        result = await db.execute(
            select(MainAccount).where(
                MainAccount.main_account_id == shop_account.main_account_id,
                MainAccount.platform == shop_account.platform,
                MainAccount.enabled == True,
            )
        )
        main_account = result.scalar_one_or_none()
        if not main_account:
            logger.warning(f"主账号 {shop_account.main_account_id} 未找到或未启用")
            return None

        capabilities = await self._load_capabilities_async(shop_account.id, db)
        account_dict = self._build_account_dict(main_account, shop_account, capabilities)
        if account_dict:
            logger.debug(f"从主/店铺账号表加载账号: {account_id} ({shop_account.store_name})")
        return account_dict

    async def load_all_accounts_async(
        self, db: AsyncSession, platform: Optional[str] = None
    ) -> List[Dict]:
        stmt = (
            select(ShopAccount)
            .where(ShopAccount.enabled == True)
            .order_by(ShopAccount.platform, ShopAccount.store_name)
        )
        if platform:
            stmt = stmt.where(ShopAccount.platform.ilike(platform))

        rows = (await db.execute(stmt)).scalars().all()
        out: List[Dict] = []
        for shop_account in rows:
            result = await db.execute(
                select(MainAccount).where(
                    MainAccount.main_account_id == shop_account.main_account_id,
                    MainAccount.platform == shop_account.platform,
                    MainAccount.enabled == True,
                )
            )
            main_account = result.scalar_one_or_none()
            if not main_account:
                continue
            capabilities = await self._load_capabilities_async(shop_account.id, db)
            account_dict = self._build_account_dict(main_account, shop_account, capabilities)
            if account_dict:
                out.append(account_dict)
        logger.info(f"从主/店铺账号表加载了 {len(out)} 个活跃账号" + (f" (平台: {platform})" if platform else ""))
        return out

    def load_account(self, account_id: str, db: Union[Session, AsyncSession]) -> Optional[Dict]:
        if isinstance(db, AsyncSession):
            raise ValueError("异步 Session 请使用 load_account_async() 方法")

        shop_account = (
            db.query(ShopAccount)
            .filter(
                ShopAccount.shop_account_id == account_id,
                ShopAccount.enabled == True,
            )
            .first()
        )
        if not shop_account:
            logger.warning(f"账号 {account_id} 未找到或未启用")
            return None

        main_account = (
            db.query(MainAccount)
            .filter(
                MainAccount.main_account_id == shop_account.main_account_id,
                MainAccount.platform == shop_account.platform,
                MainAccount.enabled == True,
            )
            .first()
        )
        if not main_account:
            logger.warning(f"主账号 {shop_account.main_account_id} 未找到或未启用")
            return None

        capabilities = self._load_capabilities_sync(shop_account.id, db)
        account_dict = self._build_account_dict(main_account, shop_account, capabilities)
        if account_dict:
            logger.debug(f"从主/店铺账号表加载账号: {account_id} ({shop_account.store_name})")
        return account_dict

    def load_all_accounts(self, db: Session, platform: Optional[str] = None) -> List[Dict]:
        query = db.query(ShopAccount).filter(ShopAccount.enabled == True)
        if platform:
            query = query.filter(ShopAccount.platform.ilike(platform))

        shop_accounts = query.order_by(ShopAccount.platform, ShopAccount.store_name).all()
        result: List[Dict] = []
        for shop_account in shop_accounts:
            account_dict = self.load_account(shop_account.shop_account_id, db)
            if account_dict:
                result.append(account_dict)

        logger.info(
            f"从主/店铺账号表加载了 {len(result)} 个活跃账号"
            + (f"(平台: {platform})" if platform else "")
        )
        return result

    def get_accounts_by_capability(
        self,
        db: Session,
        platform: str,
        data_domain: str,
    ) -> List[Dict]:
        accounts = self.load_all_accounts(db, platform=platform)
        filtered = [
            acc for acc in accounts
            if acc.get("capabilities", {}).get(data_domain, False)
        ]
        logger.info(f"平台 {platform} 支持 {data_domain} 的账号数: {len(filtered)}/{len(accounts)}")
        return filtered


_account_loader_service = None


def get_account_loader_service() -> AccountLoaderService:
    global _account_loader_service
    if _account_loader_service is None:
        _account_loader_service = AccountLoaderService()
    return _account_loader_service

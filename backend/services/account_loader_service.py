#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.services.account_proxy_config import extract_proxy_config
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
        """组装运行时账号 dict。

        代理相关键来自**主账号级** ``core.main_accounts.extra_config["proxy"]``
        （店铺级 ``core.shop_accounts.extra_config["proxy"]`` 仅作回退），
        解析规则见 ``backend/services/account_proxy_config.py``
        （AccountLoaderService 与 ShopAccountLoaderService 共用的单一定义源）。

        其中 ``proxy_region`` 是**自由地区标识**（例如 ``"sg"``），与遗留
        ``AccountConfig.proxy_region`` 用的"地区池 key"词汇表
        （``config/proxy_config.py`` 的 ``"china"`` / ``"singapore"``）**不是同一套**。
        """
        password = self._decrypt_password(main_account.password_encrypted)
        if password is None:
            return None

        legacy = self._extract_legacy_shop_extra(shop_account)
        # 代理来源：**主账号级优先**，店铺级作为回退。
        #
        # 为什么主账号级优先
        # ----------------
        # 业务上是「一个登录身份 = 一个设备 = 一个出口」。IP 隔离的目的就是让平台
        # 无法把这些账号关联成「同一个出口的账号矩阵」⇒ 出口必须绑在**登录身份**上。
        # 主账号级 extra_config['proxy'] 是权威位；店铺级仅作回退（历史数据仍在店铺侧）。
        #
        # 巡店与采集**必须用同一个来源** —— 登录时 IP 与采集时 IP 不一致，
        # 平台立刻判定「环境突变」，比没有隔离更糟。
        proxy = extract_proxy_config(getattr(main_account, "extra_config", None))
        if not proxy.get("proxy_enabled"):
            proxy = extract_proxy_config(getattr(shop_account, "extra_config", None))
        return {
            "account_id": shop_account.shop_account_id,
            "main_account_id": main_account.main_account_id,
            "platform": (
                shop_account.platform or main_account.platform or "unknown"
            ).lower(),
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
            # proxy_required：账号需要代理（历史 legacy_proxy_required 标记 或 extra_config.proxy.enabled）。
            # 注意：遗留链路 modules/utils/proxy_config_manager.py 也读这个键去选"地区池"代理，
            # 账号自有 proxy_server 必须在注入浏览器时优先于地区池，否则一账号会出两个 IP。
            # 新链路（backend/services/account_proxy_config.resolve_account_proxy）不读这个键，
            # 只认账号自有的 proxy_server。
            "proxy_required": bool(legacy["proxy_required"] or proxy["proxy_enabled"]),
            "proxy_enabled": proxy["proxy_enabled"],
            "proxy_server": proxy["proxy_server"],
            "proxy_region": proxy["proxy_region"],
            "proxy_username": proxy["proxy_username"],
            "proxy_password": proxy["proxy_password"],
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

    async def load_account_async(
        self, account_id: str, db: AsyncSession
    ) -> Optional[Dict]:
        result = await db.execute(
            select(ShopAccount).where(
                ShopAccount.shop_account_id == account_id,
                ShopAccount.enabled.is_(True),
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
                MainAccount.enabled.is_(True),
            )
        )
        main_account = result.scalar_one_or_none()
        if not main_account:
            logger.warning(f"主账号 {shop_account.main_account_id} 未找到或未启用")
            return None

        capabilities = await self._load_capabilities_async(shop_account.id, db)
        account_dict = self._build_account_dict(
            main_account, shop_account, capabilities
        )
        if account_dict:
            logger.debug(
                f"从主/店铺账号表加载账号: {account_id} ({shop_account.store_name})"
            )
        return account_dict

    async def load_all_accounts_async(
        self, db: AsyncSession, platform: Optional[str] = None
    ) -> List[Dict]:
        stmt = (
            select(ShopAccount)
            .where(ShopAccount.enabled.is_(True))
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
                    MainAccount.enabled.is_(True),
                )
            )
            main_account = result.scalar_one_or_none()
            if not main_account:
                continue
            capabilities = await self._load_capabilities_async(shop_account.id, db)
            account_dict = self._build_account_dict(
                main_account, shop_account, capabilities
            )
            if account_dict:
                out.append(account_dict)
        logger.info(
            f"从主/店铺账号表加载了 {len(out)} 个活跃账号"
            + (f" (平台: {platform})" if platform else "")
        )
        return out


_account_loader_service = None


def get_account_loader_service() -> AccountLoaderService:
    global _account_loader_service
    if _account_loader_service is None:
        _account_loader_service = AccountLoaderService()
    return _account_loader_service

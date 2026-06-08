from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.account_loader_service import get_account_loader_service
from backend.services.shop_account_loader_service import get_shop_account_loader_service
from modules.core.db import MainAccount, ShopAccount


@dataclass
class CollectionAccountRuntimeError(Exception):
    code: str
    user_message: str
    log_message: str
    http_status: int = 500

    def __str__(self) -> str:
        return self.user_message


async def probe_account_runtime_state(
    account_id: str,
    db: AsyncSession,
) -> tuple[ShopAccount | None, MainAccount | None]:
    shop = (
        await db.execute(
            select(ShopAccount).where(ShopAccount.shop_account_id == account_id)
        )
    ).scalar_one_or_none()
    if shop is None:
        return None, None

    main = (
        await db.execute(
            select(MainAccount).where(
                MainAccount.main_account_id == shop.main_account_id,
                MainAccount.platform == shop.platform,
            )
        )
    ).scalar_one_or_none()
    return shop, main


def classify_account_runtime_error(
    *,
    shop_exists: bool,
    shop_enabled: bool | None,
    main_exists: bool,
    main_enabled: bool | None,
) -> CollectionAccountRuntimeError:
    if not shop_exists:
        return CollectionAccountRuntimeError(
            code="shop_account_missing",
            user_message="店铺账号不存在，请先在账号管理中维护",
            log_message="shop account missing",
            http_status=404,
        )
    if shop_enabled is False:
        return CollectionAccountRuntimeError(
            code="shop_account_disabled",
            user_message="店铺账号已禁用，请先在账号管理中启用",
            log_message="shop account disabled",
            http_status=404,
        )
    if not main_exists:
        return CollectionAccountRuntimeError(
            code="main_account_missing",
            user_message="主账号不存在，请先在账号管理中维护",
            log_message="main account missing",
            http_status=404,
        )
    if main_enabled is False:
        return CollectionAccountRuntimeError(
            code="main_account_disabled",
            user_message="主账号已禁用，请先在账号管理中启用",
            log_message="main account disabled",
            http_status=404,
        )
    return CollectionAccountRuntimeError(
        code="account_config_invalid",
        user_message="账号配置不完整，无法执行采集",
        log_message="account runtime state invalid",
        http_status=500,
    )


def map_account_loader_exception(exc: Exception) -> CollectionAccountRuntimeError:
    message = str(exc)
    lowered = message.lower()
    if "account_encryption_key" in lowered:
        return CollectionAccountRuntimeError(
            code="encryption_key_missing",
            user_message="采集运行环境缺少账号加密密钥，无法解密账号密码",
            log_message=message,
            http_status=500,
        )
    if "密码解密失败" in message or "invalidtoken" in lowered or "无效的密钥" in message:
        return CollectionAccountRuntimeError(
            code="password_decryption_failed",
            user_message="账号密码解密失败，请检查加密密钥或重新保存账号密码",
            log_message=message,
            http_status=500,
        )
    return CollectionAccountRuntimeError(
        code="account_runtime_unavailable",
        user_message=f"账号运行时加载失败: {message}",
        log_message=message,
        http_status=500,
    )


async def load_collection_account_runtime(
    account_id: str,
    *,
    db: AsyncSession,
) -> dict[str, Any]:
    shop, main = await probe_account_runtime_state(account_id, db)

    if not os.getenv("ACCOUNT_ENCRYPTION_KEY", "").strip():
        raise map_account_loader_exception(
            RuntimeError("collector missing ACCOUNT_ENCRYPTION_KEY for account password decryption")
        )

    loader_errors: list[Exception] = []

    try:
        shop_payload = await get_shop_account_loader_service().load_shop_account_async(
            account_id,
            db,
        )
        if shop_payload:
            return {
                **shop_payload["compat_account"],
                "main_account_id": shop_payload["main_account"]["main_account_id"],
                "shop_account_id": shop_payload["shop_context"]["shop_account_id"],
            }
    except Exception as exc:
        loader_errors.append(exc)

    try:
        account_payload = await get_account_loader_service().load_account_async(
            account_id,
            db,
        )
        if account_payload:
            return account_payload
    except Exception as exc:
        loader_errors.append(exc)

    if loader_errors:
        raise map_account_loader_exception(loader_errors[-1])

    raise classify_account_runtime_error(
        shop_exists=shop is not None,
        shop_enabled=getattr(shop, "enabled", None),
        main_exists=main is not None,
        main_enabled=getattr(main, "enabled", None),
    )

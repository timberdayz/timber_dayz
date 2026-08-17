from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimShop, ShopAccount, ShopAccountAlias


class OperationPerformanceShopScopeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def load_candidates(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        accounts = (
            (
                await self.db.execute(
                    select(ShopAccount).where(ShopAccount.enabled.is_(True))
                )
            )
            .scalars()
            .all()
        )
        dim_shop_keys = {
            (str(platform).strip().lower(), str(shop_id).strip())
            for platform, shop_id in (
                await self.db.execute(select(DimShop.platform_code, DimShop.shop_id))
            ).all()
        }
        aliases_by_account: dict[int, list[str]] = {}
        aliases = (
            (
                await self.db.execute(
                    select(ShopAccountAlias).where(ShopAccountAlias.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        for alias in aliases:
            aliases_by_account.setdefault(alias.shop_account_id, []).append(alias.alias_value)
        return self.build_candidates(
            accounts=accounts,
            dim_shop_keys=dim_shop_keys,
            aliases_by_account=aliases_by_account,
        )
    @staticmethod
    def _role_value(value: Any) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

    @classmethod
    def build_candidates(
        cls,
        *,
        accounts: list[Any],
        dim_shop_keys: set[tuple[str, str]],
        aliases_by_account: dict[int, list[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        candidates: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for account in accounts:
            if not bool(getattr(account, "enabled", False)):
                continue
            if cls._role_value(getattr(account, "business_role", None)) != "operating_store":
                continue
            account_id = int(getattr(account, "id"))
            platform_code = str(getattr(account, "platform", "") or "").strip().lower()
            platform_shop_id = str(
                getattr(account, "platform_shop_id", "") or ""
            ).strip() or None
            shop_account_id = str(
                getattr(account, "shop_account_id", "") or ""
            ).strip() or None
            aliases = list(aliases_by_account.get(account_id, []))
            shop_id = next(
                (
                    candidate
                    for candidate in (platform_shop_id, shop_account_id)
                    if candidate and (platform_code, candidate) in dim_shop_keys
                ),
                None,
            )
            standard_name = str(getattr(account, "store_name", "") or "").strip()
            if shop_id is None:
                unresolved.append(
                    {
                        "source_shop_account_id": account_id,
                        "platform_code": platform_code,
                        "standard_name": standard_name or shop_account_id or platform_shop_id,
                        "aliases": aliases,
                        "raw_platform_shop_id": platform_shop_id,
                        "raw_shop_account_id": shop_account_id,
                    }
                )
                continue
            candidates.append(
                {
                    "source_shop_account_id": account_id,
                    "platform_code": platform_code,
                    "shop_id": shop_id,
                    "standard_name": standard_name or shop_id,
                    "aliases": aliases,
                }
            )
        candidates.sort(key=lambda item: (item["platform_code"], item["standard_name"], item["shop_id"]))
        unresolved.sort(key=lambda item: (item["platform_code"], item["standard_name"] or ""))
        return candidates, unresolved

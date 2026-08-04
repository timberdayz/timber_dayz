from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import SystemConfig


class LaborCostPolicyService:
    """Resolves the month from which system-projected labor cost is authoritative."""

    CONFIG_KEY = "labor_cost_auto_effective_month"
    V1 = "A_ONLY_V1"
    V2 = "A_PRE_COMMISSION_LABOR_V2"

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _validate_month(year_month: str) -> str:
        value = str(year_month or "").strip()
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError as exc:
            raise ValueError("effective month must use YYYY-MM") from exc
        return value

    async def get_effective_month(self) -> Optional[str]:
        record = (
            await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == self.CONFIG_KEY)
            )
        ).scalar_one_or_none()
        if record is None or not str(record.config_value or "").strip():
            return None
        return self._validate_month(record.config_value)

    async def get_profit_basis_version(self, year_month: str) -> str:
        requested_month = self._validate_month(year_month)
        effective_month = await self.get_effective_month()
        if effective_month is not None and requested_month >= effective_month:
            return self.V2
        return self.V1

    async def is_manual_labor_cost_allowed(self, year_month: str) -> bool:
        return await self.get_profit_basis_version(year_month) == self.V1

    async def set_effective_month(
        self,
        year_month: str,
        *,
        updated_by_user_id: Optional[int] = None,
    ) -> str:
        normalized_month = self._validate_month(year_month)
        record = (
            await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == self.CONFIG_KEY)
            )
        ).scalar_one_or_none()
        if record is None:
            self.db.add(
                SystemConfig(
                    config_key=self.CONFIG_KEY,
                    config_value=normalized_month,
                    description="First month using projected labor cost",
                    updated_by=updated_by_user_id,
                )
            )
        else:
            record.config_value = normalized_month
            record.updated_at = datetime.now(timezone.utc)
            record.updated_by = updated_by_user_id
        await self.db.commit()
        return normalized_month

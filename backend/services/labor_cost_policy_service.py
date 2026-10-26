from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import SystemConfig
from modules.core.logger import get_logger


class LaborCostPolicyService:
    """Resolves the system-wide, fixed V2 labor cost policy."""

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
        """读取人工成本策略的生效月份；未配置或读不到时返回 None。

        ⚠️ **缺表必须降级而不是抛错**：看板概览等读路径会调用本方法，
        而 `system_config` 属于可选配置表——部分初始化的库里可能还没有它。
        读不到就按「未配置策略」处理（调用方退回手工成本口径），
        不能让整个看板接口 500。
        """
        try:
            record = (
                await self.db.execute(
                    select(SystemConfig).where(
                        SystemConfig.config_key == self.CONFIG_KEY
                    )
                )
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            get_logger(__name__).warning(
                "[LaborCostPolicy] failed to read %s, treating as unset: %s",
                self.CONFIG_KEY,
                exc,
            )
            await self.db.rollback()
            return None
        if record is None or not str(record.config_value or "").strip():
            return None
        return self._validate_month(record.config_value)

    async def get_profit_basis_version(self, year_month: str) -> str:
        self._validate_month(year_month)
        return self.V2

    async def is_manual_labor_cost_allowed(self, year_month: str) -> bool:
        await self.get_profit_basis_version(year_month)
        return False

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

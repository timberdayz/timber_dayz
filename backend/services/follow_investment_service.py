from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.profit_basis_service import ProfitBasisService
from modules.core.db import FollowInvestment, FollowInvestmentDetail, FollowInvestmentSettlement


class FollowInvestmentService:
    def __init__(self, db: AsyncSession | None):
        self.db = db

    @staticmethod
    def _to_month_start(year_month: str) -> date:
        return datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()

    def calculate_occupied_days(
        self,
        year_month: str,
        contribution_date: date,
        withdraw_date: date | None,
    ) -> int:
        month_start = self._to_month_start(year_month)
        month_end = date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])
        effective_start = max(month_start, contribution_date)
        effective_end = min(month_end, withdraw_date or month_end)
        if effective_end < effective_start:
            return 0
        return (effective_end - effective_start).days + 1

    def build_settlement_details(
        self,
        year_month: str,
        distributable_amount: float,
        investments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []
        total_weighted_capital = 0.0

        for row in investments:
            amount = float(row.get("contribution_amount") or 0.0)
            occupied_days = self.calculate_occupied_days(
                year_month=year_month,
                contribution_date=row["contribution_date"],
                withdraw_date=row.get("withdraw_date"),
            )
            weighted_capital = amount * occupied_days
            details.append(
                {
                    "investor_user_id": int(row["investor_user_id"]),
                    "contribution_amount_snapshot": amount,
                    "occupied_days": occupied_days,
                    "weighted_capital": weighted_capital,
                }
            )
            total_weighted_capital += weighted_capital

        for detail in details:
            share_ratio = (detail["weighted_capital"] / total_weighted_capital) if total_weighted_capital > 0 else 0.0
            detail["share_ratio"] = share_ratio
            detail["estimated_income"] = round(distributable_amount * share_ratio, 2)

        return details

    async def _load_active_investments(
        self,
        platform_code: str,
        shop_id: str,
    ) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        result = await self.db.execute(
            select(FollowInvestment).where(
                FollowInvestment.status == "active",
                FollowInvestment.platform_code == platform_code.lower(),
                FollowInvestment.shop_id == shop_id,
            )
        )
        rows = result.scalars().all()
        return [
            {
                "investor_user_id": row.investor_user_id,
                "contribution_amount": row.contribution_amount,
                "contribution_date": row.contribution_date,
                "withdraw_date": row.withdraw_date,
            }
            for row in rows
        ]

    async def calculate_settlement(
        self,
        year_month: str,
        platform_code: str,
        shop_id: str,
        distribution_ratio: float,
    ) -> dict[str, Any]:
        basis_service = ProfitBasisService(self.db)
        basis = await basis_service.build_profit_basis(
            year_month=year_month,
            platform_code=platform_code,
            shop_id=shop_id,
        )
        distributable_amount = basis_service.calculate_distributable_amount(
            profit_basis_amount=basis["profit_basis_amount"],
            distribution_ratio=distribution_ratio,
        )
        investments = await self._load_active_investments(platform_code, shop_id)
        details = self.build_settlement_details(
            year_month=year_month,
            distributable_amount=distributable_amount,
            investments=investments,
        )
        settlement = {
            "period_month": year_month,
            "platform_code": platform_code.lower(),
            "shop_id": shop_id,
            "profit_basis_amount": basis["profit_basis_amount"],
            "distribution_ratio": distribution_ratio,
            "distributable_amount": distributable_amount,
        }
        return {"settlement": settlement, "details": details}

    async def get_my_income(
        self,
        user_id: int,
        period_month: str | None = None,
    ) -> dict[str, Any]:
        if self.db is None:
            return {
                "summary": {
                    "estimated_income": 0.0,
                    "approved_income": 0.0,
                    "paid_income": 0.0,
                    "current_contribution_amount": 0.0,
                },
                "items": [],
            }

        stmt = (
            select(FollowInvestmentDetail, FollowInvestmentSettlement)
            .join(
                FollowInvestmentSettlement,
                FollowInvestmentDetail.settlement_id == FollowInvestmentSettlement.id,
            )
            .where(FollowInvestmentDetail.investor_user_id == user_id)
        )
        if period_month:
            stmt = stmt.where(FollowInvestmentSettlement.period_month == period_month)

        rows = (await self.db.execute(stmt)).all()
        items: list[dict[str, Any]] = []
        summary = {
            "estimated_income": 0.0,
            "approved_income": 0.0,
            "paid_income": 0.0,
            "current_contribution_amount": 0.0,
        }

        for detail, settlement in rows:
            items.append(
                {
                    "period_month": settlement.period_month,
                    "platform_code": settlement.platform_code,
                    "shop_id": settlement.shop_id,
                    "profit_basis_amount": settlement.profit_basis_amount,
                    "share_ratio": detail.share_ratio,
                    "estimated_income": detail.estimated_income,
                    "approved_income": detail.approved_income,
                    "paid_income": detail.paid_income,
                    "status": settlement.status,
                }
            )
            summary["estimated_income"] += float(detail.estimated_income or 0.0)
            summary["approved_income"] += float(detail.approved_income or 0.0)
            summary["paid_income"] += float(detail.paid_income or 0.0)
            summary["current_contribution_amount"] += float(detail.contribution_amount_snapshot or 0.0)

        return {"summary": summary, "items": items}

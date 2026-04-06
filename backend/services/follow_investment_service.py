from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.profit_basis_service import ProfitBasisService
from modules.core.db import ApprovalLog, FollowInvestment, FollowInvestmentDetail, FollowInvestmentSettlement, ShopProfitBasis


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
                "id": row.id,
                "investor_user_id": row.investor_user_id,
                "contribution_amount": row.contribution_amount,
                "contribution_date": row.contribution_date,
                "withdraw_date": row.withdraw_date,
                "status": row.status,
                "capital_type": row.capital_type,
                "remark": row.remark,
            }
            for row in rows
        ]

    async def list_investments(
        self,
        platform_code: str | None = None,
        shop_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        stmt = select(FollowInvestment)
        if platform_code:
            stmt = stmt.where(FollowInvestment.platform_code == platform_code.lower())
        if shop_id:
            stmt = stmt.where(FollowInvestment.shop_id == shop_id)
        if status:
            stmt = stmt.where(FollowInvestment.status == status)
        rows = (await self.db.execute(stmt.order_by(FollowInvestment.id.desc()))).scalars().all()
        return [
            {
                "id": row.id,
                "investor_user_id": row.investor_user_id,
                "platform_code": row.platform_code,
                "shop_id": row.shop_id,
                "contribution_amount": row.contribution_amount,
                "contribution_date": row.contribution_date.isoformat(),
                "withdraw_date": row.withdraw_date.isoformat() if row.withdraw_date else None,
                "capital_type": row.capital_type,
                "status": row.status,
                "remark": row.remark,
            }
            for row in rows
        ]

    async def create_investment(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.db is None:
            return payload
        record = FollowInvestment(
            investor_user_id=payload["investor_user_id"],
            platform_code=(payload["platform_code"] or "").lower(),
            shop_id=payload["shop_id"],
            contribution_amount=payload["contribution_amount"],
            contribution_date=date.fromisoformat(payload["contribution_date"]),
            withdraw_date=date.fromisoformat(payload["withdraw_date"]) if payload.get("withdraw_date") else None,
            capital_type=payload.get("capital_type") or "working_capital",
            status=payload.get("status") or "active",
            remark=payload.get("remark"),
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(record)
        return {
            "id": record.id,
            "investor_user_id": record.investor_user_id,
            "platform_code": record.platform_code,
            "shop_id": record.shop_id,
            "contribution_amount": record.contribution_amount,
            "contribution_date": record.contribution_date.isoformat(),
            "withdraw_date": record.withdraw_date.isoformat() if record.withdraw_date else None,
            "capital_type": record.capital_type,
            "status": record.status,
            "remark": record.remark,
        }

    async def update_investment(self, investment_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.db is None:
            raise ValueError("database unavailable")
        row = (await self.db.execute(select(FollowInvestment).where(FollowInvestment.id == investment_id))).scalar_one_or_none()
        if not row:
            raise ValueError("investment not found")
        if "contribution_amount" in payload and payload["contribution_amount"] is not None:
            row.contribution_amount = payload["contribution_amount"]
        if "contribution_date" in payload and payload["contribution_date"]:
            row.contribution_date = date.fromisoformat(payload["contribution_date"])
        if "withdraw_date" in payload:
            row.withdraw_date = date.fromisoformat(payload["withdraw_date"]) if payload["withdraw_date"] else None
        if "status" in payload and payload["status"]:
            row.status = payload["status"]
        if "capital_type" in payload and payload["capital_type"]:
            row.capital_type = payload["capital_type"]
        if "remark" in payload:
            row.remark = payload["remark"]
        await self.db.commit()
        await self.db.refresh(row)
        return {
            "id": row.id,
            "investor_user_id": row.investor_user_id,
            "platform_code": row.platform_code,
            "shop_id": row.shop_id,
            "contribution_amount": row.contribution_amount,
            "contribution_date": row.contribution_date.isoformat(),
            "withdraw_date": row.withdraw_date.isoformat() if row.withdraw_date else None,
            "capital_type": row.capital_type,
            "status": row.status,
            "remark": row.remark,
        }

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
        if self.db is not None:
            basis_row = (
                await self.db.execute(
                    select(ShopProfitBasis).where(
                        ShopProfitBasis.period_month == year_month,
                        ShopProfitBasis.platform_code == platform_code.lower(),
                        ShopProfitBasis.shop_id == shop_id,
                        ShopProfitBasis.basis_version == basis["basis_version"],
                    )
                )
            ).scalar_one_or_none()
            if basis_row is None:
                basis_row = ShopProfitBasis(
                    period_month=year_month,
                    platform_code=platform_code.lower(),
                    shop_id=shop_id,
                    orders_profit_amount=basis["orders_profit_amount"],
                    a_class_cost_amount=basis["a_class_cost_amount"],
                    b_class_cost_amount=basis["b_class_cost_amount"],
                    profit_basis_amount=basis["profit_basis_amount"],
                    basis_version=basis["basis_version"],
                )
                self.db.add(basis_row)
                await self.db.flush()
            else:
                basis_row.orders_profit_amount = basis["orders_profit_amount"]
                basis_row.a_class_cost_amount = basis["a_class_cost_amount"]
                basis_row.b_class_cost_amount = basis["b_class_cost_amount"]
                basis_row.profit_basis_amount = basis["profit_basis_amount"]

            existing = (
                await self.db.execute(
                    select(FollowInvestmentSettlement).where(
                        FollowInvestmentSettlement.period_month == year_month,
                        FollowInvestmentSettlement.platform_code == platform_code.lower(),
                        FollowInvestmentSettlement.shop_id == shop_id,
                    )
                )
            ).scalar_one_or_none()
            if existing and existing.status == "approved":
                raise ValueError("settlement already approved; reopen before recalculation")

            if existing is None:
                existing = FollowInvestmentSettlement(
                    profit_basis_id=basis_row.id,
                    period_month=year_month,
                    platform_code=platform_code.lower(),
                    shop_id=shop_id,
                )
                self.db.add(existing)
                await self.db.flush()

            existing.profit_basis_id = basis_row.id
            existing.profit_basis_amount = basis["profit_basis_amount"]
            existing.distribution_ratio = distribution_ratio
            existing.distributable_amount = distributable_amount
            existing.status = "calculated"

            await self.db.execute(
                delete(FollowInvestmentDetail).where(FollowInvestmentDetail.settlement_id == existing.id)
            )
            await self.db.flush()

            for detail in details:
                self.db.add(
                    FollowInvestmentDetail(
                        settlement_id=existing.id,
                        investor_user_id=detail["investor_user_id"],
                        contribution_amount_snapshot=detail["contribution_amount_snapshot"],
                        occupied_days=detail["occupied_days"],
                        weighted_capital=detail["weighted_capital"],
                        share_ratio=detail["share_ratio"],
                        estimated_income=detail["estimated_income"],
                        approved_income=0.0,
                        paid_income=0.0,
                    )
                )
            await self.db.commit()
            settlement["id"] = existing.id
            settlement["status"] = existing.status
        return {"settlement": settlement, "details": details}

    async def approve_settlement(self, settlement_id: int, approver: str) -> dict[str, Any]:
        if self.db is None:
            raise ValueError("database unavailable")
        settlement = (
            await self.db.execute(
                select(FollowInvestmentSettlement).where(FollowInvestmentSettlement.id == settlement_id)
            )
        ).scalar_one_or_none()
        if not settlement:
            raise ValueError("settlement not found")
        settlement.status = "approved"
        settlement.approved_by = approver
        settlement.approved_at = datetime.now(timezone.utc)
        details = (
            await self.db.execute(
                select(FollowInvestmentDetail).where(FollowInvestmentDetail.settlement_id == settlement_id)
            )
        ).scalars().all()
        for detail in details:
            detail.approved_income = detail.estimated_income
        self.db.add(
            ApprovalLog(
                entity_type="follow_investment_settlement",
                entity_id=str(settlement_id),
                approver=approver,
                status="approved",
                comment="approved via finance follow investment workflow",
            )
        )
        await self.db.commit()
        return {
            "id": settlement.id,
            "status": settlement.status,
            "approved_by": settlement.approved_by,
        }

    async def reopen_settlement(self, settlement_id: int) -> dict[str, Any]:
        if self.db is None:
            raise ValueError("database unavailable")
        settlement = (
            await self.db.execute(
                select(FollowInvestmentSettlement).where(FollowInvestmentSettlement.id == settlement_id)
            )
        ).scalar_one_or_none()
        if not settlement:
            raise ValueError("settlement not found")
        settlement.status = "draft"
        settlement.approved_by = None
        settlement.approved_at = None
        details = (
            await self.db.execute(
                select(FollowInvestmentDetail).where(FollowInvestmentDetail.settlement_id == settlement_id)
            )
        ).scalars().all()
        for detail in details:
            detail.approved_income = 0.0
        await self.db.commit()
        return {
            "id": settlement.id,
            "status": settlement.status,
        }

    async def list_settlements(
        self,
        period_month: str | None = None,
        platform_code: str | None = None,
        shop_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        stmt = select(FollowInvestmentSettlement)
        if period_month:
            stmt = stmt.where(FollowInvestmentSettlement.period_month == period_month)
        if platform_code:
            stmt = stmt.where(FollowInvestmentSettlement.platform_code == platform_code.lower())
        if shop_id:
            stmt = stmt.where(FollowInvestmentSettlement.shop_id == shop_id)
        if status:
            stmt = stmt.where(FollowInvestmentSettlement.status == status)
        rows = (await self.db.execute(stmt.order_by(FollowInvestmentSettlement.id.desc()))).scalars().all()
        return [
            {
                "id": row.id,
                "period_month": row.period_month,
                "platform_code": row.platform_code,
                "shop_id": row.shop_id,
                "profit_basis_amount": row.profit_basis_amount,
                "distribution_ratio": row.distribution_ratio,
                "distributable_amount": row.distributable_amount,
                "status": row.status,
                "approved_by": row.approved_by,
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            }
            for row in rows
        ]

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

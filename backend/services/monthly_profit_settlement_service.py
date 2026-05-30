from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeeCommission,
    EmployeePerformance,
    FollowInvestmentDetail,
    FollowInvestmentSettlement,
    MonthlyProfitAdjustment,
    MonthlyProfitEmployeeCommissionSnapshot,
    MonthlyProfitEmployeePerformanceSnapshot,
    MonthlyProfitFollowDetail,
    MonthlyProfitPayrollSnapshot,
    MonthlyProfitPersonnelDetail,
    MonthlyProfitShopBasisSnapshot,
    MonthlyProfitSettlement,
    PayrollRecord,
    ShopProfitBasis,
)


class MonthlyProfitSettlementNotFoundError(LookupError):
    pass


class MonthlyProfitSettlementConflictError(ValueError):
    pass


class MonthlyProfitSettlementValidationError(ValueError):
    pass


class MonthlyProfitSettlementService:
    APPROVAL_DIFFERENCE_AMOUNT_THRESHOLD = 3000.0
    APPROVAL_DIFFERENCE_RATIO_THRESHOLD = 0.01

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_float(value: Any) -> float:
        if value is None:
            return 0.0
        return float(value)

    @staticmethod
    def _get_value(record: Any, key: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(key, default)
        return getattr(record, key, default)

    def build_summary(
        self,
        *,
        period_month: str,
        net_profit_amount: float,
        personnel_actual_amount: float,
        follow_actual_amount: float,
        adjustment_amount: float,
        personnel_target_ratio: float,
        follow_target_ratio: float,
        company_target_ratio: float,
        status: str = "draft",
        settlement_id: int | None = None,
        approved_by: str | None = None,
        remark: str | None = None,
    ) -> dict[str, Any]:
        total_ratio = personnel_target_ratio + follow_target_ratio + company_target_ratio
        if abs(total_ratio - 1.0) > 1e-9:
            raise MonthlyProfitSettlementValidationError("target ratios must sum to 1")

        personnel_target_amount = net_profit_amount * personnel_target_ratio
        follow_target_amount = net_profit_amount * follow_target_ratio
        company_target_amount = net_profit_amount * company_target_ratio

        company_actual_amount = (
            net_profit_amount - personnel_actual_amount - follow_actual_amount - adjustment_amount
        )

        personnel_actual_ratio = (personnel_actual_amount / net_profit_amount) if net_profit_amount else 0.0
        follow_actual_ratio = (follow_actual_amount / net_profit_amount) if net_profit_amount else 0.0
        company_actual_ratio = (company_actual_amount / net_profit_amount) if net_profit_amount else 0.0
        difference_amount = company_target_amount - company_actual_amount
        difference_ratio = (difference_amount / net_profit_amount) if net_profit_amount else 0.0

        return {
            "id": settlement_id,
            "period_month": period_month,
            "net_profit_amount": round(net_profit_amount, 4),
            "personnel_target_ratio": personnel_target_ratio,
            "follow_target_ratio": follow_target_ratio,
            "company_target_ratio": company_target_ratio,
            "personnel_target_amount": round(personnel_target_amount, 4),
            "follow_target_amount": round(follow_target_amount, 4),
            "company_target_amount": round(company_target_amount, 4),
            "personnel_actual_amount": round(personnel_actual_amount, 4),
            "follow_actual_amount": round(follow_actual_amount, 4),
            "company_actual_amount": round(company_actual_amount, 4),
            "personnel_actual_ratio": round(personnel_actual_ratio, 8),
            "follow_actual_ratio": round(follow_actual_ratio, 8),
            "company_actual_ratio": round(company_actual_ratio, 8),
            "adjustment_amount": round(adjustment_amount, 4),
            "difference_amount": round(difference_amount, 4),
            "difference_ratio": round(difference_ratio, 8),
            "status": status,
            "approved_by": approved_by,
            "remark": remark,
        }

    async def _load_net_profit_amount(self, period_month: str) -> float:
        rows = (
            await self.db.execute(
                select(ShopProfitBasis).where(ShopProfitBasis.period_month == period_month)
            )
        ).scalars().all()
        return sum(self._to_float(row.profit_basis_amount) for row in rows)

    async def _load_personnel_payload(self, period_month: str) -> dict[str, Any]:
        payroll_rows = (
            await self.db.execute(
                select(PayrollRecord).where(
                    PayrollRecord.year_month == period_month,
                    PayrollRecord.status.in_(("confirmed", "paid")),
                )
            )
        ).scalars().all()

        details: list[dict[str, Any]] = []
        total = 0.0

        for row in payroll_rows:
            amount = self._to_float(getattr(row, "total_cost", 0))
            total += amount
            details.append(
                {
                    "detail_type": "payroll_total_cost",
                    "amount": amount,
                    "employee_code": getattr(row, "employee_code", None),
                    "source_module": "payroll_records",
                    "source_record_id": str(getattr(row, "id", "") or ""),
                    "remark": None,
                }
            )

        return {"actual_amount": total, "details": details}

    async def _load_follow_payload(self, period_month: str) -> dict[str, Any]:
        rows = (
            await self.db.execute(
                select(FollowInvestmentDetail)
                .join(
                    FollowInvestmentSettlement,
                    FollowInvestmentDetail.settlement_id == FollowInvestmentSettlement.id,
                )
                .where(
                    FollowInvestmentSettlement.period_month == period_month,
                    FollowInvestmentSettlement.status == "approved",
                )
            )
        ).scalars().all()

        details: list[dict[str, Any]] = []
        total = 0.0
        for row in rows:
            approved_income = getattr(row, "approved_income", None)
            estimated_income = getattr(row, "estimated_income", 0)
            amount = self._to_float(approved_income if approved_income is not None else estimated_income)
            total += amount
            details.append(
                {
                    "investor_user_id": getattr(row, "investor_user_id", None),
                    "source_settlement_id": getattr(row, "settlement_id", None) or getattr(row, "source_settlement_id", None),
                    "amount": amount,
                    "status": "approved",
                    "remark": None,
                }
            )
        return {"actual_amount": total, "details": details}

    async def _load_settlement_record(self, period_month: str) -> MonthlyProfitSettlement | None:
        return (
            await self.db.execute(
                select(MonthlyProfitSettlement).where(MonthlyProfitSettlement.period_month == period_month)
            )
        ).scalar_one_or_none()

    async def _load_personnel_details(self, settlement_id: int) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(MonthlyProfitPersonnelDetail).where(MonthlyProfitPersonnelDetail.settlement_id == settlement_id)
            )
        ).scalars().all()
        return [
            {
                "detail_type": row.detail_type,
                "amount": self._to_float(row.amount),
                "employee_code": row.employee_code,
                "platform_code": row.platform_code,
                "shop_id": row.shop_id,
                "source_module": row.source_module,
                "source_record_id": row.source_record_id,
                "remark": row.remark,
            }
            for row in rows
        ]

    async def _load_follow_details(self, settlement_id: int) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(MonthlyProfitFollowDetail).where(MonthlyProfitFollowDetail.settlement_id == settlement_id)
            )
        ).scalars().all()
        return [
            {
                "investor_user_id": row.investor_user_id,
                "source_settlement_id": row.source_settlement_id,
                "amount": self._to_float(row.amount),
                "status": row.status,
                "remark": row.remark,
            }
            for row in rows
        ]

    async def _load_adjustments(self, settlement_id: int) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(MonthlyProfitAdjustment).where(MonthlyProfitAdjustment.settlement_id == settlement_id)
            )
        ).scalars().all()
        return [
            {
                "adjustment_type": row.adjustment_type,
                "amount": self._to_float(row.amount),
                "reason": row.reason,
                "created_by": row.created_by,
            }
            for row in rows
        ]

    async def _load_active_snapshot_version(self, settlement_id: int) -> int | None:
        row = (
            await self.db.execute(
                select(MonthlyProfitPayrollSnapshot.snapshot_version).where(
                    MonthlyProfitPayrollSnapshot.settlement_id == settlement_id,
                    MonthlyProfitPayrollSnapshot.snapshot_status == "active",
                )
            )
        ).first()
        if row is None:
            return None
        if hasattr(row, "__getitem__") and len(row) > 0:
            return int(row[0])
        return int(self._get_value(row, "snapshot_version", 0) or 0)

    async def _load_snapshot_personnel_details(
        self,
        settlement_id: int,
        snapshot_version: int,
    ) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(MonthlyProfitPayrollSnapshot).where(
                    MonthlyProfitPayrollSnapshot.settlement_id == settlement_id,
                    MonthlyProfitPayrollSnapshot.snapshot_version == snapshot_version,
                    MonthlyProfitPayrollSnapshot.snapshot_status == "active",
                )
            )
        ).scalars().all()
        return [
            {
                "detail_type": "payroll_total_cost",
                "amount": self._to_float(getattr(row, "total_cost", 0.0)),
                "employee_code": getattr(row, "employee_code", None),
                "platform_code": None,
                "shop_id": None,
                "source_module": "payroll_snapshot",
                "source_record_id": str(getattr(row, "payroll_record_id", "") or ""),
                "remark": getattr(row, "remark", None),
            }
            for row in rows
        ]

    async def load_snapshot_settlement_view(self, record: Any) -> dict[str, Any]:
        settlement_id = int(self._get_value(record, "id"))
        snapshot_version = await self._load_active_snapshot_version(settlement_id)
        personnel_details = (
            await self._load_snapshot_personnel_details(settlement_id, snapshot_version)
            if snapshot_version is not None
            else []
        )
        follow_details = await self._load_follow_details(settlement_id)
        adjustments = await self._load_adjustments(settlement_id)
        personnel_actual_amount = sum(self._to_float(detail.get("amount")) for detail in personnel_details)
        follow_actual_amount = sum(self._to_float(detail.get("amount")) for detail in follow_details)
        adjustment_amount = sum(self._to_float(detail.get("amount")) for detail in adjustments)
        personnel_target_ratio = self._to_float(self._get_value(record, "personnel_target_ratio"))
        follow_target_ratio = self._to_float(self._get_value(record, "follow_target_ratio"))
        company_target_ratio = self._to_float(self._get_value(record, "company_target_ratio"))
        if personnel_target_ratio == 0 and follow_target_ratio == 0 and company_target_ratio == 0:
            company_target_ratio = 1.0
        summary = self.build_summary(
            period_month=self._get_value(record, "period_month"),
            net_profit_amount=self._to_float(self._get_value(record, "net_profit_amount")),
            personnel_actual_amount=personnel_actual_amount,
            follow_actual_amount=follow_actual_amount,
            adjustment_amount=adjustment_amount,
            personnel_target_ratio=personnel_target_ratio,
            follow_target_ratio=follow_target_ratio,
            company_target_ratio=company_target_ratio,
            status=self._get_value(record, "status", "approved"),
            settlement_id=settlement_id,
            approved_by=self._get_value(record, "approved_by"),
            remark=self._get_value(record, "remark"),
        )
        return {
            "summary": summary,
            "personnel_details": personnel_details,
            "follow_details": follow_details,
            "adjustments": adjustments,
        }

    async def get_next_snapshot_version(self, settlement_id: int) -> int:
        snapshot_rows = (
            await self.db.execute(
                select(MonthlyProfitPayrollSnapshot.snapshot_version).where(
                    MonthlyProfitPayrollSnapshot.settlement_id == settlement_id
                )
            )
        ).all()
        max_version = 0
        for row in snapshot_rows:
            version = self._get_value(row, "snapshot_version", None)
            if version is None and hasattr(row, "__getitem__") and len(row) > 0:
                version = row[0]
            max_version = max(max_version, int(version or 0))
        return max_version + 1

    async def mark_active_snapshots_superseded(self, settlement_id: int) -> None:
        snapshot_models = (
            MonthlyProfitShopBasisSnapshot,
            MonthlyProfitEmployeeCommissionSnapshot,
            MonthlyProfitEmployeePerformanceSnapshot,
            MonthlyProfitPayrollSnapshot,
        )
        for model in snapshot_models:
            rows = (
                await self.db.execute(
                    select(model).where(
                        model.settlement_id == settlement_id,
                        model.snapshot_status == "active",
                    )
                )
            ).scalars().all()
            for row in rows:
                row.snapshot_status = "superseded"

    async def build_settlement_snapshots(
        self,
        *,
        settlement_id: int,
        period_month: str,
        snapshot_version: int,
        created_by: str,
    ) -> None:
        shop_basis_rows = (
            await self.db.execute(
                select(ShopProfitBasis).where(ShopProfitBasis.period_month == period_month)
            )
        ).scalars().all()
        for row in shop_basis_rows:
            self.db.add(
                MonthlyProfitShopBasisSnapshot(
                    settlement_id=settlement_id,
                    period_month=period_month,
                    snapshot_version=snapshot_version,
                    snapshot_status="active",
                    platform_code=getattr(row, "platform_code", None),
                    shop_id=getattr(row, "shop_id", None),
                    shop_name=None,
                    basis_version=getattr(row, "basis_version", None),
                    orders_profit_amount=self._to_float(getattr(row, "orders_profit_amount", 0.0)),
                    a_class_cost_amount=self._to_float(getattr(row, "a_class_cost_amount", 0.0)),
                    profit_basis_amount=self._to_float(getattr(row, "profit_basis_amount", 0.0)),
                    created_by=created_by,
                )
            )

        commission_rows = (
            await self.db.execute(
                select(EmployeeCommission).where(EmployeeCommission.year_month == period_month)
            )
        ).scalars().all()
        for row in commission_rows:
            self.db.add(
                MonthlyProfitEmployeeCommissionSnapshot(
                    settlement_id=settlement_id,
                    period_month=period_month,
                    snapshot_version=snapshot_version,
                    snapshot_status="active",
                    employee_code=getattr(row, "employee_code", None),
                    employee_name=None,
                    platform_code="",
                    shop_id="",
                    shop_name=None,
                    sales_amount=self._to_float(getattr(row, "sales_amount", 0.0)),
                    commission_rate=self._to_float(getattr(row, "commission_rate", 0.0)),
                    commission_amount=self._to_float(getattr(row, "commission_amount", 0.0)),
                    created_by=created_by,
                )
            )

        performance_rows = (
            await self.db.execute(
                select(EmployeePerformance).where(EmployeePerformance.year_month == period_month)
            )
        ).scalars().all()
        for row in performance_rows:
            self.db.add(
                MonthlyProfitEmployeePerformanceSnapshot(
                    settlement_id=settlement_id,
                    period_month=period_month,
                    snapshot_version=snapshot_version,
                    snapshot_status="active",
                    employee_code=getattr(row, "employee_code", None),
                    employee_name=None,
                    actual_sales=self._to_float(getattr(row, "actual_sales", 0.0)),
                    achievement_rate=self._to_float(getattr(row, "achievement_rate", 0.0)),
                    performance_score=self._to_float(getattr(row, "performance_score", 0.0)),
                    attendance_adjustment_score=0.0,
                    manual_adjustment_score=0.0,
                    created_by=created_by,
                )
            )

        payroll_rows = (
            await self.db.execute(
                select(PayrollRecord).where(PayrollRecord.year_month == period_month)
            )
        ).scalars().all()
        for row in payroll_rows:
            self.db.add(
                MonthlyProfitPayrollSnapshot(
                    settlement_id=settlement_id,
                    period_month=period_month,
                    snapshot_version=snapshot_version,
                    snapshot_status="active",
                    payroll_record_id=getattr(row, "id", None),
                    employee_code=getattr(row, "employee_code", None),
                    employee_name=None,
                    base_salary=getattr(row, "base_salary", 0.0),
                    position_salary=getattr(row, "position_salary", 0.0),
                    performance_salary=getattr(row, "performance_salary", 0.0),
                    overtime_pay=getattr(row, "overtime_pay", 0.0),
                    commission=getattr(row, "commission", 0.0),
                    allowances=getattr(row, "allowances", 0.0),
                    bonus=getattr(row, "bonus", 0.0),
                    gross_salary=getattr(row, "gross_salary", 0.0),
                    social_insurance_personal=getattr(row, "social_insurance_personal", 0.0),
                    housing_fund_personal=getattr(row, "housing_fund_personal", 0.0),
                    income_tax=getattr(row, "income_tax", 0.0),
                    other_deductions=getattr(row, "other_deductions", 0.0),
                    total_deductions=getattr(row, "total_deductions", 0.0),
                    net_salary=getattr(row, "net_salary", 0.0),
                    social_insurance_company=getattr(row, "social_insurance_company", 0.0),
                    housing_fund_company=getattr(row, "housing_fund_company", 0.0),
                    total_cost=getattr(row, "total_cost", 0.0),
                    payroll_status=getattr(row, "status", None),
                    pay_date=getattr(row, "pay_date", None),
                    remark=getattr(row, "remark", None),
                    created_by=created_by,
                )
            )

    async def _upsert_settlement(self, period_month: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = await self._load_settlement_record(period_month)
        if record is None:
            record = MonthlyProfitSettlement(period_month=period_month)
            self.db.add(record)
            await self.db.flush()

        if getattr(record, "status", "draft") == "approved":
            raise MonthlyProfitSettlementConflictError("settlement already approved; reopen before rebuild")

        for field in [
            "net_profit_amount",
            "personnel_target_ratio",
            "follow_target_ratio",
            "company_target_ratio",
            "personnel_target_amount",
            "follow_target_amount",
            "company_target_amount",
            "personnel_actual_amount",
            "follow_actual_amount",
            "company_actual_amount",
            "adjustment_amount",
            "difference_amount",
            "difference_ratio",
            "status",
            "remark",
        ]:
            setattr(record, field, payload[field])

        record.locked_at = datetime.now(timezone.utc) if payload["status"] == "approved" else None
        record.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        payload["id"] = record.id
        return payload

    async def rebuild_month(
        self,
        *,
        period_month: str,
        personnel_target_ratio: float,
        follow_target_ratio: float,
        company_target_ratio: float,
        adjustment_amount: float = 0.0,
        adjustment_reason: str | None = None,
    ) -> dict[str, Any]:
        net_profit_amount = await self._load_net_profit_amount(period_month)
        personnel_payload = await self._load_personnel_payload(period_month)
        follow_payload = await self._load_follow_payload(period_month)

        summary = self.build_summary(
            period_month=period_month,
            net_profit_amount=net_profit_amount,
            personnel_actual_amount=self._to_float(personnel_payload.get("actual_amount")),
            follow_actual_amount=self._to_float(follow_payload.get("actual_amount")),
            adjustment_amount=adjustment_amount,
            personnel_target_ratio=personnel_target_ratio,
            follow_target_ratio=follow_target_ratio,
            company_target_ratio=company_target_ratio,
        )
        summary = await self._upsert_settlement(period_month, summary)
        settlement_id = int(summary["id"])

        await self.db.execute(
            delete(MonthlyProfitPersonnelDetail).where(MonthlyProfitPersonnelDetail.settlement_id == settlement_id)
        )
        await self.db.execute(
            delete(MonthlyProfitFollowDetail).where(MonthlyProfitFollowDetail.settlement_id == settlement_id)
        )
        await self.db.execute(
            delete(MonthlyProfitAdjustment).where(MonthlyProfitAdjustment.settlement_id == settlement_id)
        )
        await self.db.flush()

        for detail in personnel_payload.get("details", []):
            self.db.add(
                MonthlyProfitPersonnelDetail(
                    settlement_id=settlement_id,
                    detail_type=detail.get("detail_type") or "personnel_cost",
                    employee_code=detail.get("employee_code"),
                    platform_code=detail.get("platform_code"),
                    shop_id=detail.get("shop_id"),
                    source_module=detail.get("source_module"),
                    source_record_id=detail.get("source_record_id"),
                    amount=self._to_float(detail.get("amount")),
                    remark=detail.get("remark"),
                )
            )

        for detail in follow_payload.get("details", []):
            self.db.add(
                MonthlyProfitFollowDetail(
                    settlement_id=settlement_id,
                    investor_user_id=detail.get("investor_user_id"),
                    source_settlement_id=detail.get("source_settlement_id"),
                    amount=self._to_float(detail.get("amount")),
                    status=detail.get("status") or "approved",
                    remark=detail.get("remark"),
                )
            )

        if adjustment_amount:
            self.db.add(
                MonthlyProfitAdjustment(
                    settlement_id=settlement_id,
                    adjustment_type="manual_adjustment",
                    amount=self._to_float(adjustment_amount),
                    reason=adjustment_reason or "monthly settlement adjustment",
                    created_by="system",
                )
            )

        await self.db.commit()
        return {
            "summary": summary,
            "personnel_details": personnel_payload.get("details", []),
            "follow_details": follow_payload.get("details", []),
            "adjustments": (
                [
                    {
                        "adjustment_type": "manual_adjustment",
                        "amount": self._to_float(adjustment_amount),
                        "reason": adjustment_reason or "monthly settlement adjustment",
                        "created_by": "system",
                    }
                ]
                if adjustment_amount
                else []
            ),
        }

    async def get_month(self, period_month: str) -> dict[str, Any]:
        record = await self._load_settlement_record(period_month)
        if record is None:
            return {
                "summary": self.build_summary(
                    period_month=period_month,
                    net_profit_amount=0.0,
                    personnel_actual_amount=0.0,
                    follow_actual_amount=0.0,
                    adjustment_amount=0.0,
                    personnel_target_ratio=0.0,
                    follow_target_ratio=0.0,
                    company_target_ratio=1.0,
                ),
                "personnel_details": [],
                "follow_details": [],
                "adjustments": [],
            }

        if self._get_value(record, "status", "draft") == "approved":
            return await self.load_snapshot_settlement_view(record)

        settlement_id = int(self._get_value(record, "id"))
        personnel_target_ratio = self._to_float(self._get_value(record, "personnel_target_ratio"))
        follow_target_ratio = self._to_float(self._get_value(record, "follow_target_ratio"))
        company_target_ratio = self._to_float(self._get_value(record, "company_target_ratio"))
        if personnel_target_ratio == 0 and follow_target_ratio == 0 and company_target_ratio == 0:
            company_target_ratio = 1.0
        summary = self.build_summary(
            period_month=self._get_value(record, "period_month"),
            net_profit_amount=self._to_float(self._get_value(record, "net_profit_amount")),
            personnel_actual_amount=self._to_float(self._get_value(record, "personnel_actual_amount")),
            follow_actual_amount=self._to_float(self._get_value(record, "follow_actual_amount")),
            adjustment_amount=self._to_float(self._get_value(record, "adjustment_amount")),
            personnel_target_ratio=personnel_target_ratio,
            follow_target_ratio=follow_target_ratio,
            company_target_ratio=company_target_ratio,
            status=self._get_value(record, "status", "draft"),
            settlement_id=settlement_id,
            approved_by=self._get_value(record, "approved_by"),
            remark=self._get_value(record, "remark"),
        )
        return {
            "summary": summary,
            "personnel_details": await self._load_personnel_details(settlement_id),
            "follow_details": await self._load_follow_details(settlement_id),
            "adjustments": await self._load_adjustments(settlement_id),
        }

    async def update_targets(self, settlement_id: int, body: dict[str, Any]) -> dict[str, Any]:
        record = (
            await self.db.execute(
                select(MonthlyProfitSettlement).where(MonthlyProfitSettlement.id == settlement_id)
            )
        ).scalar_one_or_none()
        if record is None:
            raise MonthlyProfitSettlementNotFoundError("settlement not found")
        if record.status == "approved":
            raise MonthlyProfitSettlementConflictError("approved settlement cannot be edited; reopen first")

        summary = self.build_summary(
            period_month=record.period_month,
            net_profit_amount=self._to_float(record.net_profit_amount),
            personnel_actual_amount=self._to_float(record.personnel_actual_amount),
            follow_actual_amount=self._to_float(record.follow_actual_amount),
            adjustment_amount=self._to_float(body.get("adjustment_amount", 0.0)),
            personnel_target_ratio=self._to_float(body["personnel_target_ratio"]),
            follow_target_ratio=self._to_float(body["follow_target_ratio"]),
            company_target_ratio=self._to_float(body["company_target_ratio"]),
            status=record.status,
            settlement_id=settlement_id,
            approved_by=record.approved_by,
            remark=record.remark,
        )

        await self.db.execute(
            delete(MonthlyProfitAdjustment).where(MonthlyProfitAdjustment.settlement_id == settlement_id)
        )
        if summary["adjustment_amount"]:
            self.db.add(
                MonthlyProfitAdjustment(
                    settlement_id=settlement_id,
                    adjustment_type="manual_adjustment",
                    amount=summary["adjustment_amount"],
                    reason=body.get("adjustment_reason") or "monthly settlement adjustment",
                    created_by="system",
                )
            )

        for field, value in summary.items():
            if field == "id":
                continue
            setattr(record, field, value)
        await self.db.commit()
        return {
            "summary": summary,
            "personnel_details": await self._load_personnel_details(settlement_id),
            "follow_details": await self._load_follow_details(settlement_id),
            "adjustments": await self._load_adjustments(settlement_id),
        }

    async def approve(self, settlement_id: int, approver: str) -> dict[str, Any]:
        record = (
            await self.db.execute(
                select(MonthlyProfitSettlement).where(MonthlyProfitSettlement.id == settlement_id)
            )
        ).scalar_one_or_none()
        if record is None:
            raise MonthlyProfitSettlementNotFoundError("settlement not found")
        if record.status == "approved":
            raise MonthlyProfitSettlementConflictError("settlement already approved")
        if (
            abs(self._to_float(getattr(record, "difference_amount", 0.0))) > self.APPROVAL_DIFFERENCE_AMOUNT_THRESHOLD
            or abs(self._to_float(getattr(record, "difference_ratio", 0.0))) > self.APPROVAL_DIFFERENCE_RATIO_THRESHOLD
        ):
            raise MonthlyProfitSettlementConflictError("difference threshold exceeded")
        snapshot_version = await self.get_next_snapshot_version(settlement_id)
        await self.build_settlement_snapshots(
            settlement_id=settlement_id,
            period_month=str(getattr(record, "period_month", "")),
            snapshot_version=snapshot_version,
            created_by=approver,
        )
        record.status = "approved"
        record.approved_by = approver
        record.approved_at = datetime.now(timezone.utc)
        record.locked_at = datetime.now(timezone.utc)
        snapshot_payload = await self.load_snapshot_settlement_view(record)
        snapshot_summary = snapshot_payload["summary"]
        for field in [
            "net_profit_amount",
            "personnel_target_ratio",
            "follow_target_ratio",
            "company_target_ratio",
            "personnel_target_amount",
            "follow_target_amount",
            "company_target_amount",
            "personnel_actual_amount",
            "follow_actual_amount",
            "company_actual_amount",
            "adjustment_amount",
            "difference_amount",
            "difference_ratio",
            "remark",
        ]:
            setattr(record, field, snapshot_summary[field])
        await self.db.commit()
        return {"id": settlement_id, "status": "approved", "approved_by": approver}

    async def reopen(self, settlement_id: int) -> dict[str, Any]:
        record = (
            await self.db.execute(
                select(MonthlyProfitSettlement).where(MonthlyProfitSettlement.id == settlement_id)
            )
        ).scalar_one_or_none()
        if record is None:
            raise MonthlyProfitSettlementNotFoundError("settlement not found")
        if record.status != "approved":
            raise MonthlyProfitSettlementConflictError("only approved settlement can be reopened")
        await self.mark_active_snapshots_superseded(settlement_id)
        record.status = "draft"
        record.locked_at = None
        record.approved_by = None
        record.approved_at = None
        await self.db.commit()
        return {"id": settlement_id, "status": "draft"}

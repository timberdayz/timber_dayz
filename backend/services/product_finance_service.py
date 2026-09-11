from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    DimErpSku,
    LogisticsBill,
    LogisticsBillLine,
    LogisticsBillLineAllocation,
    LogisticsBillPurchaseOrder,
    ProductCostAssumptionProfile,
    SkuProfitEstimate,
)

from .product_profit_service import (
    BillTotalMismatchError,
    build_baseline_profit,
    build_logistics_sku_line,
    validate_bill_total,
)
from .product_logistics_service import allocate_bill_line


class ProductFinanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_bill_or_raise(self, bill_id: int) -> LogisticsBill:
        bill = await self.db.get(LogisticsBill, bill_id)
        if bill is None:
            raise ValueError("logistics bill not found")
        return bill

    async def replace_bill_lines(self, bill: LogisticsBill, lines: list[dict]) -> list[LogisticsBillLine]:
        if bill.status != "draft":
            raise ValueError("only draft logistics bills can be edited")
        sku_ids = {sku_id for line in lines for sku_id in (line.get("sku_ids") or [line.get("sku_id")]) if sku_id is not None}
        legacy_ids = [line.get("sku_id") for line in lines if line.get("sku_ids") is None]
        if len(legacy_ids) != len(set(legacy_ids)):
            raise ValueError("a logistics bill can contain each SKU only once")
        sku_rows = (
            await self.db.execute(select(DimErpSku).where(DimErpSku.sku_id.in_(sku_ids)))
        ).scalars().all()
        skus = {sku.sku_id: sku for sku in sku_rows}
        if len(skus) != len(sku_ids):
            raise ValueError("one or more SKUs do not exist")

        await self.db.execute(delete(LogisticsBillLine).where(LogisticsBillLine.bill_id == bill.bill_id))
        rows: list[LogisticsBillLine] = []
        for index, line in enumerate(lines, start=1):
            line_sku_ids = line.get("sku_ids") or [line["sku_id"]]
            sku = skus[line_sku_ids[0]]
            volume = None
            if all(value is not None for value in (sku.package_length_cm, sku.package_width_cm, sku.package_height_cm)):
                volume = Decimal(str(sku.package_length_cm * sku.package_width_cm * sku.package_height_cm)) / Decimal("1000000")
            shipped_qty = line.get("shipped_qty") or 0
            if line.get("billing_basis") == "fixed" and not shipped_qty:
                shipped_qty = 1
            calculated = build_logistics_sku_line(
                shipped_qty=shipped_qty,
                unit_weight_kg=sku.weight_kg,
                unit_volume_cbm=volume,
                actual_total_weight_kg=line.get("actual_total_weight_kg"),
                actual_total_volume_cbm=line.get("actual_total_volume_cbm"),
                headhaul_cost=line.get("headhaul_cost"),
                handling_cost=line.get("handling_cost"),
                last_mile_cost=line.get("last_mile_cost"),
            )
            row = LogisticsBillLine(
                bill_id=bill.bill_id,
                line_no=index,
                sku_id=sku.sku_id,
                po_id=line.get("po_id"),
                billing_basis=line.get("billing_basis", "volume"),
                billing_unit=line.get("billing_unit"),
                billing_unit_rate=line.get("billing_unit_rate"),
                is_sensitive=bool(line.get("is_sensitive", False)),
                sensitive_surcharge=line.get("sensitive_surcharge", 0),
                shipped_qty=calculated["shipped_qty"],
                calculated_total_weight_kg=calculated["calculated_total_weight_kg"],
                calculated_total_volume_cbm=calculated["calculated_total_volume_cbm"],
                actual_total_weight_kg=calculated["actual_total_weight_kg"],
                actual_total_volume_cbm=calculated["actual_total_volume_cbm"],
                headhaul_cost=calculated["headhaul_cost"],
                handling_cost=calculated["handling_cost"],
                last_mile_cost=calculated["last_mile_cost"],
                unit_headhaul_cost=calculated["unit_headhaul_cost"],
                unit_handling_cost=calculated["unit_handling_cost"],
                unit_last_mile_cost=calculated["unit_last_mile_cost"],
                line_total_amount=line.get("line_total_amount", calculated["line_total_amount"]),
                notes=line.get("notes"),
            )
            self.db.add(row)
            rows.append(row)
        await self.db.flush()
        # Preserve multi-SKU lineage in the allocation table. The first SKU remains
        # in the legacy direct column for backwards compatibility.
        for row, line in zip(rows, lines):
            line_sku_ids = line.get("sku_ids") or [line["sku_id"]]
            if len(line_sku_ids) <= 1:
                continue
            amount = Decimal(str(row.line_total_amount or 0))
            basis = line.get("billing_basis", "volume")
            allocation_items = []
            for sku_id in line_sku_ids:
                item_sku = skus[sku_id]
                unit_volume = Decimal("0")
                if all(value is not None for value in (item_sku.package_length_cm, item_sku.package_width_cm, item_sku.package_height_cm)):
                    unit_volume = Decimal(str(item_sku.package_length_cm * item_sku.package_width_cm * item_sku.package_height_cm)) / Decimal("1000000")
                allocation_items.append({"sku_id": sku_id, "quantity": Decimal(str(line.get("shipped_qty") or 1)) / Decimal(len(line_sku_ids)), "volume_cbm": unit_volume * (Decimal(str(line.get("shipped_qty") or 1)) / Decimal(len(line_sku_ids))), "weight_kg": Decimal(str(item_sku.weight_kg or 0)) * (Decimal(str(line.get("shipped_qty") or 1)) / Decimal(len(line_sku_ids)))})
            allocations = allocate_bill_line(line_amount=amount, basis=(basis if basis in {"volume", "weight", "quantity"} else "quantity"), items=allocation_items)
            for allocation in allocations:
                sku_id = allocation["sku_id"]
                self.db.add(LogisticsBillLineAllocation(
                    bill_line_id=row.line_id,
                    sku_id=sku_id,
                    allocated_quantity=next(item["quantity"] for item in allocation_items if item["sku_id"] == sku_id),
                    allocation_ratio=allocation["allocation_ratio"],
                    allocated_amount=allocation["allocated_amount"],
                    allocation_basis=basis,
                    mapping_status="confirmed",
                ))
        return rows

    async def replace_bill_purchase_orders(self, bill: LogisticsBill, po_ids: list[str]) -> list[LogisticsBillPurchaseOrder]:
        if bill.status != "draft":
            raise ValueError("only draft logistics bills can be edited")
        await self.db.execute(delete(LogisticsBillPurchaseOrder).where(LogisticsBillPurchaseOrder.bill_id == bill.bill_id))
        rows = [LogisticsBillPurchaseOrder(bill_id=bill.bill_id, po_id=po_id) for po_id in dict.fromkeys(po_ids)]
        self.db.add_all(rows)
        await self.db.flush()
        return rows

    async def confirm_bill(self, bill: LogisticsBill, user_id: int | None) -> LogisticsBill:
        if bill.status != "draft":
            raise ValueError("only draft logistics bills can be confirmed")
        lines = (
            await self.db.execute(
                select(LogisticsBillLine).where(LogisticsBillLine.bill_id == bill.bill_id)
            )
        ).scalars().all()
        if not lines:
            raise ValueError("a logistics bill needs at least one SKU line")
        validate_bill_total(bill.total_amount, [line.line_total_amount for line in lines])
        bill.status = "confirmed"
        bill.confirmed_at = datetime.now(timezone.utc)
        bill.confirmed_by = user_id
        return bill

    async def void_bill(self, bill: LogisticsBill, user_id: int | None, reason: str) -> LogisticsBill:
        if bill.status != "confirmed":
            raise ValueError("only confirmed logistics bills can be voided")
        if bill.status == "voided":
            raise ValueError("logistics bill is already voided")
        bill.status = "voided"
        bill.voided_at = datetime.now(timezone.utc)
        bill.voided_by = user_id
        bill.void_reason = reason
        return bill

    async def find_active_assumption(self, destination: str | None, transport_type: str | None, as_of: date) -> ProductCostAssumptionProfile | None:
        base_filters = [
            ProductCostAssumptionProfile.active.is_(True),
            ProductCostAssumptionProfile.effective_from <= as_of,
            (ProductCostAssumptionProfile.effective_to.is_(None)) | (ProductCostAssumptionProfile.effective_to >= as_of),
        ]
        scopes = []
        if destination and transport_type:
            scopes.extend([
                (ProductCostAssumptionProfile.destination == destination, ProductCostAssumptionProfile.transport_type == transport_type),
                (ProductCostAssumptionProfile.destination == destination, ProductCostAssumptionProfile.transport_type.is_(None)),
                (ProductCostAssumptionProfile.destination.is_(None), ProductCostAssumptionProfile.transport_type == transport_type),
            ])
        elif destination:
            scopes.append((ProductCostAssumptionProfile.destination == destination,))
        elif transport_type:
            scopes.append((ProductCostAssumptionProfile.transport_type == transport_type,))
        scopes.append((ProductCostAssumptionProfile.destination.is_(None), ProductCostAssumptionProfile.transport_type.is_(None)))
        for scope in scopes:
            statement = select(ProductCostAssumptionProfile).where(*base_filters, *scope).order_by(ProductCostAssumptionProfile.effective_from.desc())
            row = (await self.db.execute(statement)).scalars().first()
            if row is not None:
                return row
        return None

    async def find_confirmed_logistics_cost(self, sku_id: int, destination: str | None, transport_type: str | None) -> Decimal | None:
        statement = (
            select(LogisticsBillLine)
            .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
            .where(LogisticsBillLine.sku_id == sku_id, LogisticsBill.status == "confirmed")
        )
        if destination:
            statement = statement.where(LogisticsBill.destination == destination)
        if transport_type:
            statement = statement.where(LogisticsBill.transport_type == transport_type)
        line = (await self.db.execute(statement.order_by(LogisticsBill.confirmed_at.desc()))).scalars().first()
        if line is None or not line.shipped_qty:
            return None
        return Decimal(str(line.line_total_amount)) / Decimal(str(line.shipped_qty))

    async def preview_profit(self, data: dict) -> dict:
        sku = await self.db.get(DimErpSku, data["sku_id"])
        if sku is None:
            raise ValueError("SKU not found")
        assumption = await self.find_active_assumption(data.get("destination"), data.get("transport_type"), date.today())
        confirmed_logistics = await self.find_confirmed_logistics_cost(sku.sku_id, data.get("destination"), data.get("transport_type"))
        assumption_logistics = assumption.freight_unit_rate if assumption is not None else None
        result = build_baseline_profit(
            selling_price=data["selling_price"],
            coupon_amount=data.get("coupon_amount"),
            default_purchase_cost=sku.default_purchase_cost,
            confirmed_logistics_cost=confirmed_logistics,
            assumption_logistics_cost=assumption_logistics,
            storage_cost=assumption.storage_unit_rate if assumption is not None else None,
            platform_fee_rate=assumption.platform_fee_rate if assumption is not None else None,
            return_rate=assumption.return_rate if assumption is not None else None,
            damage_rate=assumption.damage_rate if assumption is not None else None,
        )
        result.update({
            "sku_id": sku.sku_id,
            "assumption_profile_id": assumption.profile_id if assumption else None,
            "assumption_version": f"profile-{assumption.profile_id}" if assumption else "manual-fallback",
            "cost_completeness": "complete" if all(value is not None for value in (
                sku.default_purchase_cost,
                result.get("logistics_cost"),
                result.get("storage_cost"),
                result.get("platform_fee"),
                result.get("expected_return_loss"),
                result.get("expected_damage_loss"),
            )) else "partial",
            "confidence_level": assumption.confidence_level if assumption else "low",
        })
        return result

    async def save_profit_estimate(self, data: dict) -> SkuProfitEstimate:
        preview = await self.preview_profit(data)
        row = SkuProfitEstimate(
            sku_id=preview["sku_id"],
            assumption_version=data["assumption_version"],
            scenario="base",
            selling_price=data["selling_price"],
            coupon_amount=data.get("coupon_amount", 0),
            purchase_cost=preview["purchase_cost"],
            purchase_cost_source=preview["purchase_cost_source"],
            logistics_cost=preview["logistics_cost"],
            logistics_cost_source=preview["logistics_cost_source"],
            storage_cost=preview["storage_cost"],
            storage_cost_source=preview["storage_cost_source"],
            platform_fee=preview["platform_fee"],
            expected_return_loss=preview["expected_return_loss"],
            expected_damage_loss=preview["expected_damage_loss"],
            estimated_contribution_profit=preview["estimated_contribution_profit"],
            estimated_margin_rate=preview["estimated_margin_rate"],
            assumption_profile_id=preview["assumption_profile_id"],
            cost_completeness=preview["cost_completeness"],
            confidence_level=preview["confidence_level"],
        )
        self.db.add(row)
        await self.db.flush()
        return row

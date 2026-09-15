from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    BridgeSpuSku,
    BridgeErpSkuKey,
    DimErpSku,
    DimPlatform,
    DimWarehouse,
    DimSpu,
    LogisticsBill,
    LogisticsBillLine,
    LogisticsBillLineAllocation,
    LogisticsBillPurchaseOrder,
    POHeader,
    POLine,
    ProductCostAssumptionProfile,
    LogisticsProviderRule,
    WarehouseStorageRule,
    SkuOperatingProfile,
    SkuProfitEstimate,
)

from .product_profit_service import (
    BillTotalMismatchError,
    build_baseline_profit,
    build_platform_profit_preview,
    build_logistics_sku_line,
    validate_bill_total,
    build_reference_storage_cost,
    reference_storage_days,
)
from .product_logistics_service import allocate_bill_line


def _unit_volume_cbm(sku: DimErpSku) -> Decimal:
    dimensions = (sku.package_length_cm, sku.package_width_cm, sku.package_height_cm)
    if any(value is None for value in dimensions):
        return Decimal("0")
    return Decimal(str(dimensions[0] * dimensions[1] * dimensions[2])) / Decimal("1000000")


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
        allowed_po_ids = set(
            (
                await self.db.execute(
                    select(LogisticsBillPurchaseOrder.po_id).where(
                        LogisticsBillPurchaseOrder.bill_id == bill.bill_id
                    )
                )
            ).scalars()
        )
        referenced_po_ids = {
            po_id
            for line in lines
            for po_id in [
                line.get("po_id"),
                *(item.get("po_id") for item in line.get("allocations", [])),
            ]
            if po_id
        }
        if referenced_po_ids - allowed_po_ids:
            raise ValueError("all logistics line purchase orders must be linked to the batch")
        sku_ids = {
            sku_id
            for line in lines
            for sku_id in (
                [item["sku_id"] for item in line.get("allocations", [])]
                or line.get("sku_ids")
                or [line.get("sku_id")]
            )
            if sku_id is not None
        }
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
        allocation_specs_by_line: list[list[dict]] = []
        for index, line in enumerate(lines, start=1):
            line_sku_ids = line.get("sku_ids") or [line["sku_id"]]
            allocation_specs = line.get("allocations") or []
            if not allocation_specs:
                legacy_quantity = Decimal(str(line.get("shipped_qty") or 0))
                if line.get("billing_basis") == "fixed" and not legacy_quantity:
                    legacy_quantity = Decimal("1")
                allocation_specs = [
                    {
                        "sku_id": sku_id,
                        "po_id": line.get("po_id"),
                        "shipped_qty": legacy_quantity / Decimal(len(line_sku_ids)),
                    }
                    for sku_id in line_sku_ids
                ]
            shipped_qty = sum((Decimal(str(item["shipped_qty"])) for item in allocation_specs), Decimal("0"))
            calculated_weight = sum(
                (Decimal(str(skus[item["sku_id"]].weight_kg or 0)) * Decimal(str(item["shipped_qty"])) for item in allocation_specs),
                Decimal("0"),
            )
            calculated_volume = sum(
                (_unit_volume_cbm(skus[item["sku_id"]]) * Decimal(str(item["shipped_qty"])) for item in allocation_specs),
                Decimal("0"),
            )
            basis = line.get("billing_basis", "volume")
            chargeable_quantity = {
                "volume": Decimal(str(line.get("actual_total_volume_cbm"))) if line.get("actual_total_volume_cbm") is not None else calculated_volume,
                "weight": Decimal(str(line.get("actual_total_weight_kg"))) if line.get("actual_total_weight_kg") is not None else calculated_weight,
                "quantity": shipped_qty,
            }.get(basis, Decimal("1"))
            headhaul_cost = Decimal(str(line.get("headhaul_cost") or 0))
            if line.get("billing_unit_rate") is not None and not headhaul_cost and basis != "fixed":
                headhaul_cost = (chargeable_quantity * Decimal(str(line["billing_unit_rate"]))).quantize(Decimal("0.01"))
            handling_cost = Decimal(str(line.get("handling_cost") or 0))
            last_mile_cost = Decimal(str(line.get("last_mile_cost") or 0))
            sensitive_surcharge = Decimal(str(line.get("sensitive_surcharge") or 0))
            component_total = headhaul_cost + handling_cost + last_mile_cost + sensitive_surcharge
            supplied_total = line.get("line_total_amount")
            if supplied_total is None or (Decimal(str(supplied_total)) == 0 and component_total):
                line_total = component_total
            elif basis == "fixed" and component_total == 0:
                headhaul_cost = Decimal(str(supplied_total))
                line_total = headhaul_cost
            elif Decimal(str(supplied_total)) != component_total:
                raise ValueError("line total does not match billed components")
            else:
                line_total = Decimal(str(supplied_total))
            warehouse_code = line.get("warehouse_code")
            if not warehouse_code or await self.db.get(DimWarehouse, warehouse_code) is None:
                raise ValueError("warehouse is required and must exist")
            sku = skus[line_sku_ids[0]]
            calculated = build_logistics_sku_line(
                shipped_qty=shipped_qty,
                unit_weight_kg=calculated_weight / shipped_qty if shipped_qty else 0,
                unit_volume_cbm=calculated_volume / shipped_qty if shipped_qty else 0,
                actual_total_weight_kg=line.get("actual_total_weight_kg"),
                actual_total_volume_cbm=line.get("actual_total_volume_cbm"),
                headhaul_cost=headhaul_cost,
                handling_cost=handling_cost,
                last_mile_cost=last_mile_cost,
            )
            row = LogisticsBillLine(
                bill_id=bill.bill_id,
                line_no=index,
                sku_id=sku.sku_id,
                po_id=line.get("po_id"),
                warehouse_code=warehouse_code,
                billing_basis=basis,
                billing_unit=line.get("billing_unit"),
                billing_unit_rate=line.get("billing_unit_rate"),
                is_sensitive=bool(line.get("is_sensitive", False)),
                sensitive_surcharge=sensitive_surcharge,
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
                line_total_amount=line_total,
                notes=line.get("notes"),
            )
            self.db.add(row)
            rows.append(row)
            allocation_specs_by_line.append(allocation_specs)
        await self.db.flush()
        # Preserve multi-SKU lineage in the allocation table. The first SKU remains
        # in the legacy direct column for backwards compatibility.
        for row, line, allocation_specs in zip(rows, lines, allocation_specs_by_line):
            amount = Decimal(str(row.line_total_amount or 0))
            basis = line.get("billing_basis", "volume")
            allocation_items = []
            for spec in allocation_specs:
                item_sku = skus[spec["sku_id"]]
                quantity = Decimal(str(spec["shipped_qty"]))
                allocation_items.append({"sku_id": item_sku.sku_id, "po_id": spec.get("po_id"), "quantity": quantity, "volume_cbm": _unit_volume_cbm(item_sku) * quantity, "weight_kg": Decimal(str(item_sku.weight_kg or 0)) * quantity})
            allocations = allocate_bill_line(line_amount=amount, basis=(basis if basis in {"volume", "weight", "quantity"} else "quantity"), items=allocation_items)
            for allocation in allocations:
                sku_id = allocation["sku_id"]
                self.db.add(LogisticsBillLineAllocation(
                    bill_line_id=row.line_id,
                    sku_id=sku_id,
                    po_id=next(item["po_id"] for item in allocation_items if item["sku_id"] == sku_id),
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
        unique_po_ids = list(dict.fromkeys(po_ids))
        existing_po_ids = set((await self.db.execute(select(POHeader.po_id).where(POHeader.po_id.in_(unique_po_ids)))).scalars())
        if existing_po_ids != set(unique_po_ids):
            raise ValueError("one or more purchase orders do not exist")
        await self.db.execute(delete(LogisticsBillPurchaseOrder).where(LogisticsBillPurchaseOrder.bill_id == bill.bill_id))
        rows = [LogisticsBillPurchaseOrder(bill_id=bill.bill_id, po_id=po_id) for po_id in unique_po_ids]
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

    async def find_confirmed_logistics_cost(self, sku_id: int, warehouse_code: str | None, transport_type: str | None) -> Decimal | None:
        allocated = (
            select(
                func.sum(LogisticsBillLineAllocation.allocated_amount),
                func.sum(LogisticsBillLineAllocation.allocated_quantity),
            )
            .join(LogisticsBillLine, LogisticsBillLine.line_id == LogisticsBillLineAllocation.bill_line_id)
            .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
            .where(LogisticsBillLineAllocation.sku_id == sku_id, LogisticsBill.status == "confirmed")
        )
        if transport_type:
            allocated = allocated.where(LogisticsBill.transport_type == transport_type)
        if warehouse_code:
            allocated = allocated.where(LogisticsBillLine.warehouse_code == warehouse_code)
        allocated_amount, allocated_quantity = (await self.db.execute(allocated)).one()
        if allocated_quantity:
            return Decimal(str(allocated_amount)) / Decimal(str(allocated_quantity))
        statement = (
            select(func.sum(LogisticsBillLine.line_total_amount), func.sum(LogisticsBillLine.shipped_qty))
            .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
            .where(LogisticsBillLine.sku_id == sku_id, LogisticsBill.status == "confirmed")
        )
        if transport_type:
            statement = statement.where(LogisticsBill.transport_type == transport_type)
        if warehouse_code:
            statement = statement.where(LogisticsBillLine.warehouse_code == warehouse_code)
        total_amount, total_quantity = (await self.db.execute(statement)).one()
        if total_quantity is None or not total_quantity:
            return None
        return Decimal(str(total_amount or 0)) / Decimal(str(total_quantity))

    async def find_reference_logistics_cost(self, sku: DimErpSku, warehouse_code: str, transport_type: str) -> tuple[Decimal | None, LogisticsProviderRule | None]:
        statement = select(LogisticsProviderRule).where(
            or_(
                LogisticsProviderRule.warehouse_code == warehouse_code,
                LogisticsProviderRule.warehouse_code.is_(None),
            ),
            or_(
                LogisticsProviderRule.transport_type == transport_type,
                LogisticsProviderRule.transport_type.is_(None),
            ),
            LogisticsProviderRule.status == "active",
            LogisticsProviderRule.is_sensitive.is_(False),
            LogisticsProviderRule.currency == "CNY",
            LogisticsProviderRule.effective_from <= date.today(),
            (LogisticsProviderRule.effective_to.is_(None)) | (LogisticsProviderRule.effective_to >= date.today()),
        )
        rules = (await self.db.execute(statement)).scalars().all()
        if not rules:
            return None, None
        rule = self._select_reference_logistics_rule(rules, warehouse_code, transport_type)
        if rule is None:
            return None, None
        return self._reference_logistics_from_rule(sku, rule), rule

    @staticmethod
    def _select_reference_logistics_rule(
        rules: list[LogisticsProviderRule], warehouse_code: str, transport_type: str
    ) -> LogisticsProviderRule | None:
        """Select one unambiguous current rule; never choose a tariff arbitrarily."""
        if not rules:
            return None
        def specificity(rule: LogisticsProviderRule) -> int:
            return int(rule.warehouse_code == warehouse_code) + int(
                rule.transport_type == transport_type
            )

        highest_specificity = max(specificity(rule) for rule in rules)
        best_rules = [
            rule
            for rule in rules
            if specificity(rule) == highest_specificity
        ]
        if len(best_rules) != 1:
            return None
        return best_rules[0]

    @staticmethod
    def _reference_logistics_from_rule(
        sku: DimErpSku, rule: LogisticsProviderRule
    ) -> Decimal | None:
        if rule.freight_unit_rate is None:
            return None
        if rule.billing_basis == "volume":
            if any(value is None for value in (sku.package_length_cm, sku.package_width_cm, sku.package_height_cm)):
                return None
            measure = _unit_volume_cbm(sku)
        elif rule.billing_basis == "weight":
            if sku.weight_kg is None:
                return None
            measure = Decimal(str(sku.weight_kg))
        elif rule.billing_basis in {"quantity", "fixed"}:
            measure = Decimal("1")
        else:
            return None
        return (measure * Decimal(str(rule.freight_unit_rate))).quantize(Decimal("0.01"))

    async def find_reference_storage_cost(self, sku: DimErpSku, warehouse_code: str) -> tuple[Decimal | None, WarehouseStorageRule | None]:
        statement = select(WarehouseStorageRule).where(
            WarehouseStorageRule.warehouse_code == warehouse_code,
            WarehouseStorageRule.status == "active",
            WarehouseStorageRule.effective_from <= date.today(),
            (WarehouseStorageRule.effective_to.is_(None)) | (WarehouseStorageRule.effective_to >= date.today()),
        ).order_by(WarehouseStorageRule.effective_from.desc(), WarehouseStorageRule.rule_id.desc())
        rule = (await self.db.execute(statement)).scalars().first()
        if rule is None:
            return None, None
        volume = None if any(value is None for value in (sku.package_length_cm, sku.package_width_cm, sku.package_height_cm)) else _unit_volume_cbm(sku)
        return build_reference_storage_cost(unit_volume_cbm=volume, unit_rate_cny_per_cbm_month=rule.unit_rate_cny, turnover_class=sku.turnover_class), rule

    async def find_latest_purchase_cost(self, sku: DimErpSku) -> Decimal | None:
        purchase_cost = case(
            (POLine.currency == "CNY", POLine.unit_price),
            (
                and_(
                    POLine.currency != "CNY",
                    POLine.base_amt.is_not(None),
                    POLine.base_amt > 0,
                    POLine.qty_ordered > 0,
                ),
                POLine.base_amt / POLine.qty_ordered,
            ),
            else_=None,
        )
        valid_purchase_cost = or_(
            and_(POLine.currency == "CNY", POLine.unit_price.is_not(None)),
            and_(
                POLine.currency != "CNY",
                POLine.base_amt.is_not(None),
                POLine.base_amt > 0,
                POLine.qty_ordered > 0,
            ),
        )
        row = (
            await self.db.execute(
                select(purchase_cost)
                .join(POHeader, POHeader.po_id == POLine.po_id)
                .where(
                    POLine.platform_sku.in_(
                        select(BridgeErpSkuKey.source_key).where(
                            BridgeErpSkuKey.sku_id == sku.sku_id,
                            BridgeErpSkuKey.active.is_(True),
                            BridgeErpSkuKey.effective_to.is_(None),
                        )
                    )
                    | (POLine.platform_sku == sku.sku_key),
                    valid_purchase_cost,
                )
                .order_by(POHeader.po_date.desc(), POLine.po_line_id.desc())
            )
        ).scalars().first()
        return Decimal(str(row)) if row is not None else None

    async def prefetch_platform_sku_profit_inputs(
        self,
        skus: list[DimErpSku],
        warehouse_code: str,
        transport_type: str,
    ) -> dict[int, dict[str, object]]:
        """Load cost inputs for a page in bounded queries rather than per-SKU awaits."""
        if not skus:
            return {}
        sku_ids = [sku.sku_id for sku in skus]
        sku_by_id = {sku.sku_id: sku for sku in skus}
        source_rows = (
            await self.db.execute(
                select(BridgeErpSkuKey.sku_id, BridgeErpSkuKey.source_key).where(
                    BridgeErpSkuKey.sku_id.in_(sku_ids),
                    BridgeErpSkuKey.active.is_(True),
                    BridgeErpSkuKey.effective_to.is_(None),
                )
            )
        ).all()
        sku_by_source_key = {sku.sku_key: sku.sku_id for sku in skus}
        sku_by_source_key.update({source_key: sku_id for sku_id, source_key in source_rows})
        purchase_costs: dict[int, Decimal] = {}
        if sku_by_source_key:
            purchase_cost = case(
                (POLine.currency == "CNY", POLine.unit_price),
                (
                    and_(
                        POLine.currency != "CNY",
                        POLine.base_amt.is_not(None),
                        POLine.base_amt > 0,
                        POLine.qty_ordered > 0,
                    ),
                    POLine.base_amt / POLine.qty_ordered,
                ),
                else_=None,
            )
            valid_purchase_cost = or_(
                and_(POLine.currency == "CNY", POLine.unit_price.is_not(None)),
                and_(
                    POLine.currency != "CNY",
                    POLine.base_amt.is_not(None),
                    POLine.base_amt > 0,
                    POLine.qty_ordered > 0,
                ),
            )
            purchase_rows = (
                await self.db.execute(
                    select(POLine.platform_sku, purchase_cost)
                    .join(POHeader, POHeader.po_id == POLine.po_id)
                    .where(
                        POLine.platform_sku.in_(sku_by_source_key),
                        valid_purchase_cost,
                    )
                    .order_by(POHeader.po_date.desc(), POLine.po_line_id.desc())
                )
            ).all()
            for source_key, unit_price in purchase_rows:
                mapped_sku_id = sku_by_source_key.get(source_key)
                if mapped_sku_id is not None and mapped_sku_id not in purchase_costs:
                    purchase_costs[mapped_sku_id] = Decimal(str(unit_price))

        actual_logistics: dict[int, Decimal] = {}
        allocated_rows = (
            await self.db.execute(
                select(
                    LogisticsBillLineAllocation.sku_id,
                    func.sum(LogisticsBillLineAllocation.allocated_amount),
                    func.sum(LogisticsBillLineAllocation.allocated_quantity),
                )
                .join(LogisticsBillLine, LogisticsBillLine.line_id == LogisticsBillLineAllocation.bill_line_id)
                .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
                .where(
                    LogisticsBillLineAllocation.sku_id.in_(sku_ids),
                    LogisticsBill.status == "confirmed",
                    LogisticsBill.transport_type == transport_type,
                    LogisticsBillLine.warehouse_code == warehouse_code,
                )
                .group_by(LogisticsBillLineAllocation.sku_id)
            )
        ).all()
        for item_sku_id, amount, quantity in allocated_rows:
            if quantity:
                actual_logistics[item_sku_id] = Decimal(str(amount)) / Decimal(str(quantity))
        missing_actual_ids = [sku_id for sku_id in sku_ids if sku_id not in actual_logistics]
        if missing_actual_ids:
            legacy_rows = (
                await self.db.execute(
                    select(
                        LogisticsBillLine.sku_id,
                        func.sum(LogisticsBillLine.line_total_amount),
                        func.sum(LogisticsBillLine.shipped_qty),
                    )
                    .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
                    .where(
                        LogisticsBillLine.sku_id.in_(missing_actual_ids),
                        LogisticsBill.status == "confirmed",
                        LogisticsBill.transport_type == transport_type,
                        LogisticsBillLine.warehouse_code == warehouse_code,
                    )
                    .group_by(LogisticsBillLine.sku_id)
                )
            ).all()
            for item_sku_id, amount, quantity in legacy_rows:
                if quantity:
                    actual_logistics[item_sku_id] = Decimal(str(amount or 0)) / Decimal(str(quantity))

        current_rules = (
            await self.db.execute(
                select(LogisticsProviderRule).where(
                    or_(
                        LogisticsProviderRule.warehouse_code == warehouse_code,
                        LogisticsProviderRule.warehouse_code.is_(None),
                    ),
                    or_(
                        LogisticsProviderRule.transport_type == transport_type,
                        LogisticsProviderRule.transport_type.is_(None),
                    ),
                    LogisticsProviderRule.status == "active",
                    LogisticsProviderRule.is_sensitive.is_(False),
                    LogisticsProviderRule.currency == "CNY",
                    LogisticsProviderRule.effective_from <= date.today(),
                    (LogisticsProviderRule.effective_to.is_(None))
                    | (LogisticsProviderRule.effective_to >= date.today()),
                )
            )
        ).scalars().all()
        logistics_rule = self._select_reference_logistics_rule(
            current_rules, warehouse_code, transport_type
        )
        storage_rule = (
            await self.db.execute(
                select(WarehouseStorageRule)
                .where(
                    WarehouseStorageRule.warehouse_code == warehouse_code,
                    WarehouseStorageRule.status == "active",
                    WarehouseStorageRule.effective_from <= date.today(),
                    (WarehouseStorageRule.effective_to.is_(None))
                    | (WarehouseStorageRule.effective_to >= date.today()),
                )
                .order_by(
                    WarehouseStorageRule.effective_from.desc(),
                    WarehouseStorageRule.rule_id.desc(),
                )
            )
        ).scalars().first()

        inputs: dict[int, dict[str, object]] = {}
        for item_sku_id, sku in sku_by_id.items():
            reference_logistics = (
                self._reference_logistics_from_rule(sku, logistics_rule)
                if logistics_rule is not None
                else None
            )
            volume = (
                None
                if any(
                    value is None
                    for value in (
                        sku.package_length_cm,
                        sku.package_width_cm,
                        sku.package_height_cm,
                    )
                )
                else _unit_volume_cbm(sku)
            )
            reference_storage = (
                build_reference_storage_cost(
                    unit_volume_cbm=volume,
                    unit_rate_cny_per_cbm_month=storage_rule.unit_rate_cny,
                    turnover_class=sku.turnover_class,
                )
                if storage_rule is not None
                else None
            )
            inputs[item_sku_id] = {
                "purchase_cost": purchase_costs.get(item_sku_id),
                "actual_logistics_cost": actual_logistics.get(item_sku_id),
                "reference_logistics_cost": reference_logistics,
                "reference_logistics_rule": logistics_rule,
                "reference_storage_cost": reference_storage,
                "reference_storage_rule": storage_rule,
            }
        return inputs

    async def preview_profit(self, data: dict) -> dict:
        sku = await self.db.get(DimErpSku, data["sku_id"])
        if sku is None:
            raise ValueError("SKU not found")
        purchase_cost = await self.find_latest_purchase_cost(sku)
        confirmed_logistics = await self.find_confirmed_logistics_cost(sku.sku_id, data.get("warehouse_code"), data.get("transport_type"))
        # Platform master data is the only active source for platform fees.
        platform = await self.db.get(DimPlatform, data.get("platform_code")) if data.get("platform_code") else None
        platform_fee_rate = platform.default_fee_rate if platform is not None else None
        binding = (
            await self.db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku.sku_id,
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        ).scalars().first()
        spu = await self.db.get(DimSpu, binding.spu) if binding is not None else None
        result = build_baseline_profit(
            selling_price=data["selling_price"],
            coupon_amount=data.get("coupon_amount"),
            default_purchase_cost=purchase_cost if purchase_cost is not None else sku.default_purchase_cost,
            confirmed_logistics_cost=confirmed_logistics,
            assumption_logistics_cost=(
                data.get("expected_logistics_cost")
                if data.get("expected_logistics_cost") is not None
                else sku.expected_logistics_cost
            ),
            storage_cost=(
                data.get("expected_storage_cost")
                if data.get("expected_storage_cost") is not None
                else sku.expected_storage_cost
            ),
            platform_fee_rate=(data.get("platform_fee_rate") if data.get("platform_fee_rate") is not None else platform_fee_rate),
            return_rate=spu.return_loss_rate if spu is not None else None,
            damage_rate=spu.logistics_damage_rate if spu is not None else None,
        )
        result.update({
            "sku_id": sku.sku_id,
            "assumption_profile_id": None,
            "assumption_version": ";".join(filter(None, (
                f"sku-master-{sku.updated_at.date().isoformat()}" if sku.updated_at else "sku-master",
                f"platform-{platform.platform_code}-{platform.fee_rate_effective_from.isoformat()}" if platform is not None and platform.fee_rate_effective_from else f"platform-{platform.platform_code}" if platform is not None else "platform-missing",
                f"warehouse-{data.get('warehouse_code')}" if data.get("warehouse_code") else None,
            ))),
            "spu_rate_version": f"spu-{spu.spu}-{spu.updated_at.date().isoformat()}" if spu is not None and spu.updated_at else None,
            "cost_completeness": "complete" if all(value is not None for value in (
                result.get("purchase_cost"),
                result.get("logistics_cost"),
                result.get("storage_cost"),
                platform_fee_rate,
                spu.logistics_damage_rate if spu is not None else None,
                spu.return_loss_rate if spu is not None else None,
            )) else "partial",
            "confidence_level": sku.purchase_cost_confidence or "low",
        })
        if purchase_cost is not None:
            result["purchase_cost_source"] = "purchase_order"
        if confirmed_logistics is None:
            result["logistics_cost_source"] = (
                "sku_operating_expected_logistics" if data.get("expected_logistics_cost") is not None else "sku_expected_logistics" if sku.expected_logistics_cost is not None else "missing"
            )
        result["storage_cost_source"] = (
            "sku_operating_expected_storage" if data.get("expected_storage_cost") is not None else "sku_expected_storage" if sku.expected_storage_cost is not None else "missing"
        )
        return result

    async def get_operating_profile(self, profile_id: int) -> SkuOperatingProfile:
        profile = await self.db.get(SkuOperatingProfile, profile_id)
        if profile is None:
            raise ValueError("SKU operating profile not found")
        return profile

    async def preview_operating_profit(self, profile_id: int, data: dict) -> dict:
        profile = await self.get_operating_profile(profile_id)
        sku_data = {
            "sku_id": profile.sku_id,
            "selling_price": data.get("selling_price") if data.get("selling_price") is not None else profile.selling_price,
            "coupon_amount": data.get("coupon_amount") if data.get("coupon_amount") is not None else profile.default_coupon_amount,
            "platform_code": profile.platform_code,
            "transport_type": data.get("transport_type") or profile.transport_type,
            "warehouse_code": profile.warehouse_code,
            "expected_logistics_cost": profile.expected_logistics_cost,
            "expected_storage_cost": profile.expected_storage_cost,
            "platform_fee_rate": None,
        }
        if sku_data["selling_price"] is None:
            raise ValueError("selling_price is required for operating profile")
        result = await self.preview_profit(sku_data)
        result.update({
            "profile_id": profile.profile_id,
            "platform_code": profile.platform_code,
            "warehouse_code": profile.warehouse_code,
        })
        return result

    async def preview_platform_sku_profit(self, data: dict) -> dict:
        sku = await self.db.get(DimErpSku, data["sku_id"])
        if sku is None:
            raise ValueError("SKU not found")
        platform = await self.db.get(DimPlatform, data["platform_code"])
        if platform is None or not platform.is_active or platform.platform_role != "sales":
            raise ValueError("active sales platform not found")
        if await self.db.get(DimWarehouse, data["warehouse_code"]) is None:
            raise ValueError("warehouse not found")
        purchase_cost = await self.find_latest_purchase_cost(sku)
        transport_type = data.get("transport_type")
        if transport_type not in {"sea", "air", "rail"}:
            raise ValueError("transport_type must be selected")
        actual_logistics = await self.find_confirmed_logistics_cost(sku.sku_id, data["warehouse_code"], transport_type)
        reference_logistics, logistics_rule = await self.find_reference_logistics_cost(sku, data["warehouse_code"], transport_type)
        reference_storage, storage_rule = await self.find_reference_storage_cost(sku, data["warehouse_code"])
        binding = (
            await self.db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku.sku_id,
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        ).scalars().first()
        spu = await self.db.get(DimSpu, binding.spu) if binding else None
        expected_selling_price = data.get("expected_selling_price")
        if expected_selling_price is None:
            expected_selling_price = sku.reference_selling_price
        if expected_selling_price is None:
            raise ValueError("expected_selling_price or reference_selling_price is required")
        result = build_platform_profit_preview(
            expected_selling_price=expected_selling_price,
            competitor_price=data.get("competitor_price"),
            seller_coupon_amount=data.get("seller_coupon_amount"),
            purchase_cost=purchase_cost if purchase_cost is not None else sku.default_purchase_cost,
            expected_logistics_cost=reference_logistics,
            expected_storage_cost=reference_storage,
            actual_logistics_cost=actual_logistics,
            actual_storage_cost=None,
            platform_fee_rate=platform.default_fee_rate,
            expected_ad_rate=data.get("expected_ad_rate"),
            return_rate=spu.return_loss_rate if spu else None,
            damage_rate=spu.logistics_damage_rate if spu else None,
        )
        result.update({
            "sku_id": sku.sku_id,
            "spu": spu.spu if spu else None,
            "platform_code": data["platform_code"],
            "warehouse_code": data["warehouse_code"],
            "platform_fee_rate": platform.default_fee_rate,
            "actual_storage_cost": None,
            "transport_type": transport_type,
            "reference_logistics_cost": reference_logistics,
            "reference_logistics_rule_id": logistics_rule.rule_id if logistics_rule else None,
            "reference_storage_cost": reference_storage,
            "reference_storage_rule_id": storage_rule.rule_id if storage_rule else None,
            "reference_storage_rule_version": storage_rule.version if storage_rule else None,
            "reference_storage_days": reference_storage_days(sku.turnover_class),
            "currency": "CNY",
            "actual_logistics_cost": actual_logistics,
            "cost_completeness": "complete" if result["expected"].get("profit") is not None else "incomplete",
        })
        return result

    async def save_operating_profit(self, profile_id: int, data: dict) -> SkuProfitEstimate:
        profile = await self.get_operating_profile(profile_id)
        preview = await self.preview_operating_profit(profile_id, data)
        if data.get("selling_price") is not None:
            profile.selling_price = data["selling_price"]
        if data.get("coupon_amount") is not None:
            profile.default_coupon_amount = data["coupon_amount"]
        if data.get("transport_type") is not None:
            profile.transport_type = data["transport_type"]
        row = SkuProfitEstimate(
            sku_id=profile.sku_id,
            operating_profile_id=profile.profile_id,
            platform_code=profile.platform_code,
            warehouse_code=profile.warehouse_code,
            assumption_version=data.get("assumption_version") or preview["assumption_version"],
            scenario="base",
            selling_price=preview["net_revenue"] + Decimal(str(data.get("coupon_amount") or profile.default_coupon_amount or 0)),
            coupon_amount=data.get("coupon_amount") if data.get("coupon_amount") is not None else profile.default_coupon_amount or 0,
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

    async def save_profit_estimate(self, data: dict) -> SkuProfitEstimate:
        preview = await self.preview_profit(data)
        row = SkuProfitEstimate(
            sku_id=preview["sku_id"],
            assumption_version=data.get("assumption_version") or preview["assumption_version"],
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

from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.inventory_overview import (
    InventoryOverviewAlertResponse,
    InventoryOverviewPlatformBreakdownResponse,
    InventoryOverviewProductItemResponse,
    InventoryOverviewProductListResponse,
    InventoryOverviewSummaryResponse,
)
from backend.services.inventory.reconciliation_service import InventoryReconciliationService
from modules.core.db import FactProductMetric


def _coalesce_stock(row: FactProductMetric) -> int:
    if row.available_stock is not None:
        return int(row.available_stock or 0)
    if row.total_stock is not None:
        return int(row.total_stock or 0)
    return int(row.stock or 0)


class InventoryOverviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.reconciliation_service = InventoryReconciliationService(db)

    async def _load_latest_products(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> list[FactProductMetric]:
        stmt = select(FactProductMetric).where(
            or_(
                FactProductMetric.data_domain == "inventory",
                FactProductMetric.data_domain == "products",
                FactProductMetric.data_domain.is_(None),
            )
        )
        if platform:
            stmt = stmt.where(FactProductMetric.platform_code == platform)
        if shop_id:
            stmt = stmt.where(FactProductMetric.shop_id == shop_id)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    FactProductMetric.platform_sku.ilike(pattern),
                    FactProductMetric.product_name.ilike(pattern),
                )
            )
        stmt = stmt.order_by(
            FactProductMetric.metric_date.desc(),
            FactProductMetric.updated_at.desc(),
        )

        rows = (await self.db.execute(stmt)).scalars().all()
        latest_by_key: dict[tuple[str, str, str], FactProductMetric] = {}
        for row in rows:
            key = (row.platform_code, row.shop_id, row.platform_sku)
            if key not in latest_by_key:
                latest_by_key[key] = row
        return list(latest_by_key.values())

    def _to_product_item(
        self,
        row: FactProductMetric,
    ) -> InventoryOverviewProductItemResponse:
        stock = _coalesce_stock(row)
        image_url = row.image_url
        return InventoryOverviewProductItemResponse(
            platform_code=row.platform_code,
            shop_id=row.shop_id,
            platform_sku=row.platform_sku,
            product_name=row.product_name,
            warehouse=row.warehouse,
            stock=stock,
            total_stock=int(row.total_stock or 0),
            available_stock=int(row.available_stock or 0),
            reserved_stock=int(row.reserved_stock or 0),
            in_transit_stock=int(row.in_transit_stock or 0),
            category=row.category,
            brand=row.brand,
            price=float(row.price or 0.0),
            currency=row.currency or "CNY",
            sales_volume=int(row.sales_volume or 0),
            sales_amount=float(row.sales_amount or 0.0),
            page_views=int(row.page_views or 0),
            image_url=image_url,
            thumbnail_url=image_url,
            image_count=1 if image_url else 0,
            all_images=[image_url] if image_url else [],
            metric_date=row.metric_date,
            updated_at=row.updated_at,
        )

    async def get_summary(
        self,
        platform: Optional[str] = None,
    ) -> InventoryOverviewSummaryResponse:
        products = await self._load_latest_products(platform=platform)
        breakdown_map: dict[str, dict[str, int]] = {}

        total_stock = 0
        total_value = 0.0
        low_stock_count = 0
        out_of_stock_count = 0

        for row in products:
            stock = _coalesce_stock(row)
            total_stock += stock
            total_value += stock * float(row.price or 0.0)
            if stock < 10:
                low_stock_count += 1
            if stock == 0:
                out_of_stock_count += 1

            platform_key = row.platform_code or "unknown"
            if platform_key not in breakdown_map:
                breakdown_map[platform_key] = {"product_count": 0, "total_stock": 0}
            breakdown_map[platform_key]["product_count"] += 1
            breakdown_map[platform_key]["total_stock"] += stock

        breakdown = [
            InventoryOverviewPlatformBreakdownResponse(
                platform=platform_key,
                product_count=data["product_count"],
                total_stock=data["total_stock"],
            )
            for platform_key, data in sorted(breakdown_map.items())
        ]

        risk_summary_row = (
            await self.db.execute(
                text(
                    """
                    SELECT
                        COALESCE(high_risk_sku_count, 0) AS high_risk_sku_count,
                        COALESCE(medium_risk_sku_count, 0) AS medium_risk_sku_count,
                        COALESCE(low_risk_sku_count, 0) AS low_risk_sku_count
                    FROM api.inventory_backlog_summary_module
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()

        return InventoryOverviewSummaryResponse(
            total_products=len(products),
            total_stock=total_stock,
            total_value=total_value,
            low_stock_count=low_stock_count,
            out_of_stock_count=out_of_stock_count,
            high_risk_sku_count=int(risk_summary_row["high_risk_sku_count"]) if risk_summary_row else 0,
            medium_risk_sku_count=int(risk_summary_row["medium_risk_sku_count"]) if risk_summary_row else 0,
            low_risk_sku_count=int(risk_summary_row["low_risk_sku_count"]) if risk_summary_row else 0,
            platform_breakdown=breakdown,
        )

    async def get_products(
        self,
        page: int = 1,
        page_size: int = 20,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        keyword: Optional[str] = None,
        low_stock: Optional[bool] = None,
    ) -> InventoryOverviewProductListResponse:
        products = await self._load_latest_products(
            platform=platform,
            shop_id=shop_id,
            keyword=keyword,
        )
        items = [self._to_product_item(row) for row in products]
        if low_stock:
            items = [item for item in items if item.stock < 10]

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]
        total_pages = (total + page_size - 1) // page_size if page_size else 0

        return InventoryOverviewProductListResponse(
            data=page_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_previous=page > 1,
            has_next=page < total_pages,
        )

    async def get_product_detail(
        self,
        sku: str,
        platform: str,
        shop_id: str,
    ) -> InventoryOverviewProductItemResponse:
        stmt = (
            select(FactProductMetric)
            .where(
                FactProductMetric.platform_sku == sku,
                FactProductMetric.platform_code == platform,
                FactProductMetric.shop_id == shop_id,
            )
            .order_by(FactProductMetric.metric_date.desc(), FactProductMetric.updated_at.desc())
        )
        product = (await self.db.execute(stmt)).scalars().first()
        if product is None:
            raise ValueError(f"Product snapshot not found: {platform}/{shop_id}/{sku}")
        return self._to_product_item(product)

    async def get_alerts(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        low_stock_threshold: int = 10,
    ) -> list[InventoryOverviewAlertResponse]:
        products = await self._load_latest_products(platform=platform, shop_id=shop_id)
        alerts: list[InventoryOverviewAlertResponse] = []
        for row in products:
            stock = _coalesce_stock(row)
            if stock > low_stock_threshold:
                continue
            alerts.append(
                InventoryOverviewAlertResponse(
                    platform_code=row.platform_code,
                    shop_id=row.shop_id,
                    platform_sku=row.platform_sku,
                    product_name=row.product_name,
                    stock=stock,
                    alert_type="out_of_stock" if stock == 0 else "low_stock",
                )
            )
        return alerts

    async def get_reconciliation_snapshot(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_sku: Optional[str] = None,
    ):
        return await self.reconciliation_service.list_reconciliation(
            platform=platform,
            shop_id=shop_id,
            platform_sku=platform_sku,
        )

from __future__ import annotations

from typing import Optional

from types import SimpleNamespace

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
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
    available_stock = getattr(row, "available_stock", None)
    total_stock = getattr(row, "total_stock", None)
    stock = getattr(row, "stock", None)
    if available_stock is not None:
        return int(available_stock or 0)
    if total_stock is not None:
        return int(total_stock or 0)
    return int(stock or 0)


class InventoryOverviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.reconciliation_service = InventoryReconciliationService(db)

    def _base_product_filters(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ):
        filters = [
            FactProductMetric.data_domain == "inventory"
        ]
        if platform:
            filters.append(FactProductMetric.platform_code == platform)
        if shop_id:
            filters.append(FactProductMetric.shop_id == shop_id)
        if keyword:
            pattern = f"%{keyword}%"
            filters.append(
                or_(
                    FactProductMetric.platform_sku.ilike(pattern),
                    FactProductMetric.product_name.ilike(pattern),
                )
            )
        return filters

    def _latest_products_subquery(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ):
        ranked = (
            select(
                FactProductMetric,
                func.row_number()
                .over(
                    partition_by=(
                        FactProductMetric.platform_code,
                        FactProductMetric.shop_id,
                        FactProductMetric.platform_sku,
                    ),
                    order_by=(
                        FactProductMetric.metric_date.desc(),
                        FactProductMetric.updated_at.desc(),
                    ),
                )
                .label("rn"),
            )
            .where(*self._base_product_filters(platform=platform, shop_id=shop_id, keyword=keyword))
            .subquery()
        )
        return select(ranked).where(ranked.c.rn == 1).subquery()

    async def _load_latest_products(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> list[FactProductMetric]:
        latest_products = self._latest_products_subquery(
            platform=platform,
            shop_id=shop_id,
            keyword=keyword,
        )
        stmt = select(latest_products).order_by(
            latest_products.c.metric_date.desc(),
            latest_products.c.updated_at.desc(),
            latest_products.c.platform_code.asc(),
            latest_products.c.shop_id.asc(),
            latest_products.c.platform_sku.asc(),
        )
        rows = (await self.db.execute(stmt)).mappings().all()
        return [SimpleNamespace(**row) for row in rows]

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
        latest_products = self._latest_products_subquery(platform=platform)
        stock_expr = func.coalesce(
            latest_products.c.available_stock,
            latest_products.c.total_stock,
            latest_products.c.stock,
            0,
        )
        summary_row = (
            await self.db.execute(
                select(
                    func.count().label("total_products"),
                    func.coalesce(func.sum(stock_expr), 0).label("total_stock"),
                    func.coalesce(
                        func.sum(stock_expr * func.coalesce(latest_products.c.price, 0.0)),
                        0.0,
                    ).label("total_value"),
                    func.coalesce(
                        func.sum(case((stock_expr < 10, 1), else_=0)),
                        0,
                    ).label("low_stock_count"),
                    func.coalesce(
                        func.sum(case((stock_expr == 0, 1), else_=0)),
                        0,
                    ).label("out_of_stock_count"),
                )
            )
        ).mappings().one()

        breakdown_rows = (
            await self.db.execute(
                select(
                    func.coalesce(latest_products.c.platform_code, "unknown").label("platform"),
                    func.count().label("product_count"),
                    func.coalesce(func.sum(stock_expr), 0).label("total_stock"),
                )
                .group_by(latest_products.c.platform_code)
                .order_by(latest_products.c.platform_code.asc())
            )
        ).mappings().all()
        breakdown = [
            InventoryOverviewPlatformBreakdownResponse(
                platform=row["platform"],
                product_count=int(row["product_count"] or 0),
                total_stock=int(row["total_stock"] or 0),
            )
            for row in breakdown_rows
        ]

        try:
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
        except SQLAlchemyError:
            risk_summary_row = None

        return InventoryOverviewSummaryResponse(
            total_products=int(summary_row["total_products"] or 0),
            total_stock=int(summary_row["total_stock"] or 0),
            total_value=float(summary_row["total_value"] or 0.0),
            low_stock_count=int(summary_row["low_stock_count"] or 0),
            out_of_stock_count=int(summary_row["out_of_stock_count"] or 0),
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
        latest_products = self._latest_products_subquery(
            platform=platform,
            shop_id=shop_id,
            keyword=keyword,
        )
        stock_expr = func.coalesce(
            latest_products.c.available_stock,
            latest_products.c.total_stock,
            latest_products.c.stock,
            0,
        )
        filters = [stock_expr < 10] if low_stock else []
        total = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(latest_products).where(*filters)
                )
            ).scalar()
            or 0
        )
        start = (page - 1) * page_size
        end = start + page_size
        rows = (
            await self.db.execute(
                select(latest_products)
                .where(*filters)
                .order_by(
                    latest_products.c.metric_date.desc(),
                    latest_products.c.updated_at.desc(),
                    latest_products.c.platform_code.asc(),
                    latest_products.c.shop_id.asc(),
                    latest_products.c.platform_sku.asc(),
                )
                .offset(start)
                .limit(page_size)
            )
        ).mappings().all()
        page_items = [self._to_product_item(SimpleNamespace(**row)) for row in rows]
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

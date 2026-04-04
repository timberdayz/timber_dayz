from pathlib import Path
from urllib.parse import urlparse, urlunparse
import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.services.data_pipeline.refresh_runner import execute_sql_text

def _read_sql(path_str: str) -> str:
    sql_path = Path(path_str)
    assert sql_path.exists(), f"missing sql asset: {path_str}"
    return sql_path.read_text(encoding="utf-8")


def _normalized(sql_text: str) -> str:
    return "".join(sql_text.lower().split())


def _extract_final_select_columns(sql_text: str, view_name: str) -> list[str]:
    pattern = re.compile(
        rf"CREATE OR REPLACE VIEW {re.escape(view_name)} AS\s+(?:WITH[\s\S]*?\)\s*)?SELECT\s+([\s\S]*?)\s+FROM\b",
        re.IGNORECASE,
    )
    match = pattern.search(sql_text)
    assert match, f"unable to locate final select list in {view_name}"
    select_block = match.group(1)
    columns = []
    for line in select_block.splitlines():
        cleaned = line.strip().rstrip(",")
        if cleaned:
            columns.append(cleaned)
    return columns


def test_b_cost_shop_month_sql_asset_has_required_upstream_fields_and_formulas():
    sql_text = _read_sql("sql/mart/b_cost_shop_month.sql")
    normalized = _normalized(sql_text)

    assert "CREATE OR REPLACE VIEW mart.b_cost_shop_month AS" in sql_text
    assert "semantic.fact_orders_atomic" in sql_text

    required_fields = (
        "period_month",
        "platform_code",
        "shop_id",
        "shop_key",
        "gmv",
        "purchase_amount",
        "warehouse_operation_fee",
        "shipping_fee",
        "promotion_fee",
        "platform_commission",
        "platform_deduction_fee",
        "platform_voucher",
        "platform_service_fee",
        "platform_total_cost_itemized",
        "total_cost_b",
        "gross_margin_ref",
        "net_margin_ref",
        "currency_code",
    )
    for field_name in required_fields:
        assert field_name in sql_text

    assert "platform_code||'|'||shop_id" in normalized
    assert (
        "coalesce(purchase_amount,0)"
        "+coalesce(warehouse_operation_fee,0)"
        "+coalesce(platform_total_cost_itemized,0)"
        in normalized
    )
    assert "(gmv-purchase_amount)/nullif(gmv,0)" in normalized
    assert "(gmv-total_cost_b)/nullif(gmv,0)" in normalized


def test_b_cost_analysis_overview_module_sql_asset():
    sql_text = _read_sql("sql/api_modules/b_cost_analysis_overview_module.sql")
    assert "CREATE OR REPLACE VIEW api.b_cost_analysis_overview_module AS" in sql_text
    assert "mart.b_cost_shop_month" in sql_text
    expected_projection = [
        "period_month",
        "platform_code",
        "currency_code",
        "gmv",
        "purchase_amount",
        "warehouse_operation_fee",
        "shipping_fee",
        "promotion_fee",
        "platform_commission",
        "platform_deduction_fee",
        "platform_voucher",
        "platform_service_fee",
        "platform_total_cost_itemized",
        "total_cost_b",
        "(gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref",
        "(gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref",
    ]
    assert _extract_final_select_columns(sql_text, "api.b_cost_analysis_overview_module") == expected_projection


def test_b_cost_analysis_shop_month_module_sql_asset():
    sql_text = _read_sql("sql/api_modules/b_cost_analysis_shop_month_module.sql")
    assert "CREATE OR REPLACE VIEW api.b_cost_analysis_shop_month_module AS" in sql_text
    assert "mart.b_cost_shop_month" in sql_text
    expected_projection = [
        "period_month",
        "platform_code",
        "shop_id",
        "shop_key",
        "currency_code",
        "gmv",
        "purchase_amount",
        "warehouse_operation_fee",
        "shipping_fee",
        "promotion_fee",
        "platform_commission",
        "platform_deduction_fee",
        "platform_voucher",
        "platform_service_fee",
        "platform_total_cost_itemized",
        "total_cost_b",
        "gross_margin_ref",
        "net_margin_ref",
    ]
    assert _extract_final_select_columns(sql_text, "api.b_cost_analysis_shop_month_module") == expected_projection


def test_b_cost_analysis_order_detail_module_sql_asset():
    sql_text = _read_sql("sql/api_modules/b_cost_analysis_order_detail_module.sql")
    normalized = _normalized(sql_text)

    assert "CREATE OR REPLACE VIEW api.b_cost_analysis_order_detail_module AS" in sql_text
    assert "semantic.fact_orders_atomic" in sql_text
    assert "platform_code||'|'||shop_id" in normalized
    assert (
        "coalesce(purchase_amount,0)"
        "+coalesce(warehouse_operation_fee,0)"
        "+coalesce(platform_total_cost_itemized,0)"
        in normalized
    )
    assert "(gmv-total_cost_b)/nullif(gmv,0)" in normalized
    expected_projection = [
        "period_month",
        "platform_code",
        "shop_id",
        "shop_key",
        "currency_code",
        "order_id",
        "order_status",
        "COALESCE(order_time, order_date::timestamp) AS order_time",
        "order_date",
        "order_original_amount",
        "product_id",
        "platform_sku",
        "sku_id",
        "product_sku",
        "product_name",
        "gmv",
        "purchase_amount",
        "warehouse_operation_fee",
        "shipping_fee",
        "promotion_fee",
        "platform_commission",
        "platform_deduction_fee",
        "platform_voucher",
        "platform_service_fee",
        "platform_total_cost_itemized",
        "platform_total_cost_derived",
        "total_cost_b",
        "(gmv - purchase_amount) / NULLIF(gmv, 0) AS gross_margin_ref",
        "(gmv - total_cost_b) / NULLIF(gmv, 0) AS net_margin_ref",
    ]
    assert _extract_final_select_columns(sql_text, "api.b_cost_analysis_order_detail_module") == expected_projection


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_b_cost_views_are_queryable_with_currency_and_detail_columns():
    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE semantic.fact_orders_atomic (
                        metric_date DATE,
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        currency_code VARCHAR(8),
                        order_id VARCHAR(128),
                        order_status VARCHAR(64),
                        order_time TIMESTAMP,
                        order_date DATE,
                        order_original_amount NUMERIC(18,2),
                        paid_amount NUMERIC(18,2),
                        purchase_amount NUMERIC(18,2),
                        warehouse_operation_fee NUMERIC(18,2),
                        shipping_fee NUMERIC(18,2),
                        promotion_fee NUMERIC(18,2),
                        platform_commission NUMERIC(18,2),
                        platform_deduction_fee NUMERIC(18,2),
                        platform_voucher NUMERIC(18,2),
                        platform_service_fee NUMERIC(18,2),
                        platform_total_cost_itemized NUMERIC(18,2),
                        platform_total_cost_derived NUMERIC(18,2),
                        product_id VARCHAR(128),
                        platform_sku VARCHAR(128),
                        sku_id VARCHAR(128),
                        product_sku VARCHAR(128),
                        product_name VARCHAR(512)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_orders_atomic (
                        metric_date, platform_code, shop_id, currency_code,
                        order_id, order_status, order_time, order_date,
                        order_original_amount, paid_amount, purchase_amount, warehouse_operation_fee,
                        shipping_fee, promotion_fee, platform_commission, platform_deduction_fee,
                        platform_voucher, platform_service_fee, platform_total_cost_itemized, platform_total_cost_derived,
                        product_id, platform_sku, sku_id, product_sku, product_name
                    ) VALUES
                    (
                        DATE '2026-04-01', 'tiktok', 'shop-1', 'USD',
                        'ORD-USD-1', 'paid', TIMESTAMP '2026-04-01 09:10:00', DATE '2026-04-01',
                        150.00, 120.00, 70.00, 5.00,
                        4.00, 3.00, 2.00, 1.00,
                        1.00, 1.00, 12.00, 21.00,
                        'P-USD', 'PSKU-USD', 'SKU-ID-USD', 'PROD-SKU-USD', 'Product USD'
                    ),
                    (
                        DATE '2026-04-02', 'tiktok', 'shop-1', 'HKD',
                        'ORD-HKD-1', 'paid', NULL, DATE '2026-04-02',
                        230.00, 200.00, 100.00, 8.00,
                        7.00, 6.00, 5.00, 4.00,
                        3.00, 2.00, 27.00, 35.00,
                        'P-HKD', 'PSKU-HKD', 'SKU-ID-HKD', 'PROD-SKU-HKD', 'Product HKD'
                    )
                    """
                )
            )
            await execute_sql_text(session, _read_sql("sql/mart/b_cost_shop_month.sql"))
            await execute_sql_text(session, _read_sql("sql/api_modules/b_cost_analysis_order_detail_module.sql"))
            await session.commit()

            mart_rows = (
                await session.execute(
                    text(
                        """
                        SELECT currency_code, total_cost_b
                        FROM mart.b_cost_shop_month
                        WHERE platform_code = 'tiktok' AND shop_id = 'shop-1'
                        ORDER BY currency_code
                        """
                    )
                )
            ).mappings().all()
            assert len(mart_rows) == 2
            assert mart_rows[0]["currency_code"] == "HKD"
            assert mart_rows[1]["currency_code"] == "USD"
            assert mart_rows[0]["total_cost_b"] is not None
            assert mart_rows[1]["total_cost_b"] is not None

            detail_columns = (
                await session.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'api'
                          AND table_name = 'b_cost_analysis_order_detail_module'
                        ORDER BY ordinal_position
                        """
                    )
                )
            ).scalars().all()
            for column_name in (
                "currency_code",
                "order_original_amount",
                "product_id",
                "platform_sku",
                "sku_id",
                "product_sku",
                "product_name",
                "platform_total_cost_derived",
                "gross_margin_ref",
                "total_cost_b",
            ):
                assert column_name in detail_columns

            detail_row = (
                await session.execute(
                    text(
                        """
                        SELECT
                            currency_code,
                            order_original_amount,
                            product_id,
                            product_name,
                            platform_total_cost_derived,
                            total_cost_b
                        FROM api.b_cost_analysis_order_detail_module
                        WHERE order_id = 'ORD-USD-1'
                        """
                    )
                )
            ).mappings().one()
            assert detail_row["currency_code"] == "USD"
            assert float(detail_row["order_original_amount"]) == 150.0
            assert detail_row["product_id"] == "P-USD"
            assert detail_row["product_name"] == "Product USD"
            assert float(detail_row["platform_total_cost_derived"]) == 21.0
            assert detail_row["total_cost_b"] is not None

        await engine.dispose()

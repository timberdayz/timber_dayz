from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import FieldMappingTemplate


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def template_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_updates_only_published_shopee_orders_daily_and_monthly(template_session_factory):
    from backend.services.template_semantic_binding_backfill import (
        backfill_published_shopee_orders_template_bindings,
    )

    now = datetime.now(timezone.utc)
    async with template_session_factory() as session:
        published_monthly = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="monthly",
            template_name="shopee_orders__monthly_v5",
            version=5,
            status="published",
            header_columns=[
                "订单编号",
                "销售数量",
                "买家支付(RMB)",
                "利润(RMB)",
                "预估回款金额",
                "结算时间",
            ],
            header_bindings=[
                {"raw_name": "订单编号", "semantic_key": "order_id", "hash_participates": True},
                {"raw_name": "销售数量", "semantic_key": None, "hash_participates": False},
            ],
            created_at=now,
            updated_at=now,
        )
        archived_monthly = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="monthly",
            template_name="archived",
            version=4,
            status="archived",
            header_columns=["销售数量"],
            header_bindings=[{"raw_name": "销售数量", "semantic_key": None}],
            created_at=now,
            updated_at=now,
        )
        published_weekly = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="weekly",
            template_name="weekly",
            version=1,
            status="published",
            header_columns=["销售数量"],
            header_bindings=[{"raw_name": "销售数量", "semantic_key": None}],
            created_at=now,
            updated_at=now,
        )
        session.add_all([published_monthly, archived_monthly, published_weekly])
        await session.commit()

        result = await backfill_published_shopee_orders_template_bindings(session)
        await session.refresh(published_monthly)
        await session.refresh(archived_monthly)
        await session.refresh(published_weekly)

    assert result == {"templates_checked": 1, "templates_updated": 1, "bindings_updated": 5}
    bindings = {item["raw_name"]: item for item in published_monthly.header_bindings}
    assert bindings["销售数量"]["semantic_key"] == "sales_volume"
    assert bindings["销售数量"]["hash_participates"] is False
    assert bindings["买家支付(RMB)"]["semantic_key"] == "paid_amount"
    assert bindings["利润(RMB)"]["semantic_key"] == "profit"
    assert bindings["预估回款金额"]["semantic_key"] == "estimated_settlement_amount"
    assert bindings["结算时间"]["semantic_key"] == "settlement_time"
    assert archived_monthly.header_bindings == [{"raw_name": "销售数量", "semantic_key": None}]
    assert published_weekly.header_bindings == [{"raw_name": "销售数量", "semantic_key": None}]

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, FieldMappingTemplate


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def template_status_session_factory(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


def test_tiktok_orders_monthly_alias_registry_does_not_whitelist_business_field_renames():
    from backend.services.template_alias_registry import get_header_alias_mapping

    mapping = get_header_alias_mapping("tiktok", "orders", "monthly")

    assert mapping == {}


@pytest.mark.asyncio
async def test_detect_header_changes_reports_update_required_for_tiktok_business_field_rename(
    template_status_session_factory,
):
    from backend.services.template_matcher import TemplateMatcher

    now = datetime.now(timezone.utc)
    async with template_status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            template_name="tiktok_orders__monthly_v2",
            version=2,
            status="published",
            header_row=1,
            header_columns=[
                "订单编号",
                "TikTok Shop平台佣金",
                "TikTok Shop平台佣金(RMB)",
                "马来西亚税费SST",
                "马来西亚税费SST(RMB)",
            ],
            created_at=now,
            updated_at=now,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

        matcher = TemplateMatcher(session)
        result = await matcher.detect_header_changes(
            template.id,
            [
                "订单编号",
                "TikTok 平台佣金",
                "TikTok 平台佣金(RMB)",
                "SST",
                "SST(RMB)",
            ],
        )

    assert result["is_exact_match"] is False
    assert result["is_semantic_match"] is False
    assert "TikTok 平台佣金" in result["added_fields"]
    assert "TikTok Shop平台佣金" in result["removed_fields"]


@pytest.mark.parametrize(
    "current_columns",
    [
        ["订单编号", "利润(RMB)", "买家支付(USD)"],
        ["订单编号", "RMB利润", "USD买家支付"],
        ["订单编号", "利润USD", "买家RMB支付"],
    ],
)
@pytest.mark.asyncio
async def test_template_status_service_treats_currency_code_differences_as_ready(
    template_status_session_factory, tmp_path, current_columns
):
    from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService

    file_path = tmp_path / "tiktok_orders_monthly.xlsx"
    file_path.write_text("demo", encoding="utf-8")
    now = datetime.now(timezone.utc)

    async with template_status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            template_name="tiktok_orders__monthly_v2",
            version=2,
            status="published",
            header_row=1,
            header_columns=["订单编号", "利润", "买家支付"],
            created_at=now,
            updated_at=now,
        )
        catalog_file = CatalogFile(
            file_path=str(file_path),
            file_name=file_path.name,
            source="data/raw",
            platform_code="tiktok",
            source_platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            status="pending",
            first_seen_at=now,
        )
        session.add_all([template, catalog_file])
        await session.commit()
        await session.refresh(template)
        await session.refresh(catalog_file)

        service = DataSyncTemplateStatusService(session)
        status = await service.evaluate_catalog_file(
            catalog_file,
            template=template,
            current_columns=current_columns,
        )

    assert status["template_status"] == "ready"
    assert status["template_update_required"] is False
    assert status["semantic_match"] is True


@pytest.mark.asyncio
async def test_template_status_service_returns_update_required_for_true_structure_drift(
    template_status_session_factory, tmp_path
):
    from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService

    file_path = tmp_path / "tiktok_orders_monthly.xlsx"
    file_path.write_text("demo", encoding="utf-8")
    now = datetime.now(timezone.utc)

    async with template_status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            template_name="tiktok_orders__monthly_v2",
            version=2,
            status="published",
            header_row=1,
            header_columns=["订单编号", "TikTok Shop平台佣金", "马来西亚税费SST"],
            created_at=now,
            updated_at=now,
        )
        catalog_file = CatalogFile(
            file_path=str(file_path),
            file_name=file_path.name,
            source="data/raw",
            platform_code="tiktok",
            source_platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            status="pending",
            first_seen_at=now,
        )
        session.add_all([template, catalog_file])
        await session.commit()
        await session.refresh(template)
        await session.refresh(catalog_file)

        service = DataSyncTemplateStatusService(session)
        status = await service.evaluate_catalog_file(
            catalog_file,
            template=template,
            current_columns=["订单编号", "TikTok 平台佣金", "全新业务字段"],
        )

    assert status["template_status"] == "update_required"
    assert status["template_update_required"] is True
    assert status["semantic_match"] is False


@pytest.mark.asyncio
async def test_template_status_service_requires_update_for_tiktok_business_field_rename(
    template_status_session_factory, tmp_path
):
    from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService

    file_path = tmp_path / "tiktok_orders_monthly.xlsx"
    file_path.write_text("demo", encoding="utf-8")
    now = datetime.now(timezone.utc)

    async with template_status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            template_name="tiktok_orders__monthly_v2",
            version=2,
            status="published",
            header_row=1,
            header_columns=["订单编号", "TikTok Shop平台佣金", "马来西亚税费SST"],
            created_at=now,
            updated_at=now,
        )
        catalog_file = CatalogFile(
            file_path=str(file_path),
            file_name=file_path.name,
            source="data/raw",
            platform_code="tiktok",
            source_platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            status="pending",
            first_seen_at=now,
        )
        session.add_all([template, catalog_file])
        await session.commit()
        await session.refresh(template)
        await session.refresh(catalog_file)

        service = DataSyncTemplateStatusService(session)
        status = await service.evaluate_catalog_file(
            catalog_file,
            template=template,
            current_columns=["订单编号", "TikTok 平台佣金", "SST"],
        )

    assert status["template_status"] == "update_required"
    assert status["template_update_required"] is True
    assert status["semantic_match"] is False


@pytest.mark.asyncio
async def test_template_status_service_returns_missing_without_template(
    template_status_session_factory, tmp_path
):
    from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService

    file_path = tmp_path / "inventory.xlsx"
    file_path.write_text("demo", encoding="utf-8")
    now = datetime.now(timezone.utc)

    async with template_status_session_factory() as session:
        catalog_file = CatalogFile(
            file_path=str(file_path),
            file_name=file_path.name,
            source="data/raw",
            platform_code="miaoshou",
            source_platform="miaoshou",
            data_domain="inventory",
            granularity="monthly",
            status="pending",
            first_seen_at=now,
        )
        session.add(catalog_file)
        await session.commit()
        await session.refresh(catalog_file)

        service = DataSyncTemplateStatusService(session)
        status = await service.evaluate_catalog_file(catalog_file, template=None, current_columns=["SKU"])

    assert status["template_status"] == "missing"
    assert status["has_template"] is False


@pytest.mark.asyncio
async def test_shopee_products_monthly_semantic_aliases_allow_auto_sync(
    template_status_session_factory, tmp_path
):
    from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService

    file_path = tmp_path / "shopee_products_monthly.xlsx"
    file_path.write_text("demo", encoding="utf-8")
    now = datetime.now(timezone.utc)

    async with template_status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="products",
            granularity="monthly",
            sub_domain=None,
            template_name="shopee_products__monthly_v7",
            version=7,
            status="published",
            header_row=0,
            header_columns=[
                "商品编号",
                "销售额（已下订单） (MXN)",
                "销售额（已付款订单） (MXN)",
                "订单转化率（已付款订单）",
                "已付款订单",
                "件数（已付款订单）",
                "买家数（已付款订单）",
                "转化率（已付款订单）",
                "每笔订单销售额（已付款订单） (MXN)",
                "订单复购率（已付款订单）",
                "订单复购的平均天数（已付款订单）",
            ],
            created_at=now,
            updated_at=now,
        )
        catalog_file = CatalogFile(
            file_path=str(file_path),
            file_name=file_path.name,
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="products",
            granularity="monthly",
            status="pending",
            first_seen_at=now,
        )
        session.add_all([template, catalog_file])
        await session.commit()
        await session.refresh(template)
        await session.refresh(catalog_file)

        service = DataSyncTemplateStatusService(session)
        status = await service.evaluate_catalog_file(
            catalog_file,
            template=template,
            current_columns=[
                "商品编号",
                "销售额（已下订单） (PHP)",
                "销售额（已确定订单） (PHP)",
                "订单转化率（已确认订单）",
                "已确定订单",
                "件数（已确定订单）",
                "买家数（已确定订单）",
                "转化率（已确定订单）",
                "每笔订单销售额（已确认订单） (PHP)",
                "订单复购率（已确认订单）",
                "订单复购的平均天数（已确认订单）",
            ],
        )

    assert status["template_status"] in {"ready", "alias_only"}
    assert status["template_update_required"] is False
    assert status["should_auto_sync"] is True
    assert status["semantic_match"] is True

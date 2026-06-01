from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import (
    CatalogFile,
    FieldMappingTemplate,
    FieldMappingTemplateFamily,
    FieldMappingTemplateVariant,
    FieldMappingTemplateVersion,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def template_selection_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.execute(text("ATTACH DATABASE ':memory:' AS public"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)
        await conn.run_sync(FieldMappingTemplateFamily.__table__.create)
        await conn.run_sync(FieldMappingTemplateVersion.__table__.create)
        await conn.run_sync(FieldMappingTemplateVariant.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_load_field_parse_rules_for_file_selects_matching_template_by_date_format(
    template_selection_session,
    monkeypatch,
):
    from backend.routers import field_mapping_ingest as module

    async with template_selection_session() as session:
        dash_template = FieldMappingTemplate(
            id=1001,
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            header_row=3,
            template_name="shopee_analytics_monthly_dash",
            version=10,
            status="published",
            header_columns=["日期", "页面浏览数", "访客数"],
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "date_format": "dd-mm-yyyy",
                    "strict": True,
                }
            ],
        )
        slash_template = FieldMappingTemplate(
            id=1002,
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            header_row=3,
            template_name="shopee_analytics_monthly_slash",
            version=11,
            status="published",
            header_columns=["日期", "页面浏览数", "访客数"],
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "date_format": "dd/mm/yyyy",
                    "strict": True,
                }
            ],
        )
        file_record = CatalogFile(
            id=999,
            file_path="data/raw/2026/shopee_analytics_monthly_demo.xlsx",
            file_name="shopee_analytics_monthly_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([dash_template, slash_template, file_record])
        await session.commit()

        monkeypatch.setattr(module, "_safe_resolve_path", lambda _path: "demo.xlsx")

        def _fake_read_excel(_path, header=0, nrows=None, **_kwargs):
            import pandas as pd

            assert header == 3
            return pd.DataFrame(
                [
                    {"日期": "01/03/2026", "页面浏览数": 100, "访客数": 20},
                    {"日期": "02/03/2026", "页面浏览数": 120, "访客数": 30},
                ]
            )

        from backend.services.excel_parser import ExcelParser

        monkeypatch.setattr(ExcelParser, "read_excel", _fake_read_excel)

        rules = await module._load_field_parse_rules_for_file(
            db=session,
            file_record=file_record,
            domain="analytics",
            granularity="monthly",
        )

        assert rules == slash_template.field_parse_rules


@pytest.mark.asyncio
async def test_load_field_parse_rules_for_file_prefers_resolver_selected_variant(
    template_selection_session,
    monkeypatch,
):
    from backend.routers import field_mapping_ingest as module

    async with template_selection_session() as session:
        file_record = CatalogFile(
            id=1999,
            file_path="data/raw/2026/shopee_analytics_monthly_demo.xlsx",
            file_name="shopee_analytics_monthly_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(file_record)
        await session.commit()

        monkeypatch.setattr(module, "_safe_resolve_path", lambda _path: "demo.xlsx")

        def _fake_read_excel(_path, header=0, nrows=None, **_kwargs):
            import pandas as pd

            return pd.DataFrame([{"日期": "01/03/2026", "浏览量": 100, "访客数": 20}])

        from backend.services.excel_parser import ExcelParser

        monkeypatch.setattr(ExcelParser, "read_excel", _fake_read_excel)

        class _ResolverStub:
            async def resolve(self, **_kwargs):
                return {
                    "variant": {
                        "field_parse_rules": [
                            {
                                "target_field": "metric_date",
                                "source_column": "日期",
                                "value_kind": "single_date",
                                "date_format": "dd/mm/yyyy",
                                "strict": True,
                            }
                        ]
                    }
                }

        monkeypatch.setattr(
            module,
            "get_template_resolver",
            lambda _db: _ResolverStub(),
        )

        rules = await module._load_field_parse_rules_for_file(
            db=session,
            file_record=file_record,
            domain="analytics",
            granularity="monthly",
        )

        assert rules == [
            {
                "target_field": "metric_date",
                "source_column": "日期",
                "value_kind": "single_date",
                "date_format": "dd/mm/yyyy",
                "strict": True,
            }
        ]

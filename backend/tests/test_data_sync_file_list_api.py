from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, FieldMappingTemplate


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def file_list_client():
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    class _MockUser:
        id = 1
        username = "test_admin"
        is_active = True
        is_superuser = True
        role_id = 1

    async def override_current_user():
        return _MockUser()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_files_does_not_mark_services_file_as_template_covered_when_only_other_sub_domain_template_exists(
    file_list_client,
):
    client, session_factory = file_list_client

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="services",
                granularity="daily",
                sub_domain="agent",
                template_name="tiktok_services_agent_daily_v1",
                version=1,
                status="published",
                header_row=2,
                header_columns=["日期", "客服"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CatalogFile(
                file_path="data/raw/2026/tiktok_services_ai_assistant_daily_20260413_185520.xlsx",
                file_name="tiktok_services_ai_assistant_daily_20260413_185520.xlsx",
                source="data/raw",
                platform_code="tiktok",
                source_platform="tiktok",
                data_domain="services",
                granularity="daily",
                sub_domain="ai_assistant",
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "tiktok", "domain": "services", "granularity": "daily"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] == 1
    file_row = payload["data"]["files"][0]
    assert file_row["sub_domain"] == "ai_assistant"
    assert file_row["has_template"] is False
    assert file_row["template_name"] is None


@pytest.mark.asyncio
async def test_list_files_marks_template_as_update_required_when_headers_changed(
    file_list_client,
    monkeypatch,
    tmp_path,
):
    client, session_factory = file_list_client

    excel_path = tmp_path / "tiktok_products_monthly_sample.xlsx"
    excel_path.write_text("placeholder", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="products",
                granularity="monthly",
                sub_domain=None,
                template_name="tiktok_products__monthly_v2",
                version=2,
                status="published",
                header_row=2,
                header_columns=["日期", "商品交易总额", "退款金额"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CatalogFile(
                file_path=str(excel_path),
                file_name=excel_path.name,
                source="data/raw",
                platform_code="tiktok",
                source_platform="tiktok",
                data_domain="products",
                granularity="monthly",
                sub_domain=None,
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    class _FakeDf:
        class _Cols(list):
            def tolist(self):
                return list(self)

        @property
        def columns(self):
            return self._Cols(["日期", "订单", "去重客户数"])

    async def _fake_detect_header_changes(*args, **kwargs):
        return {
            "detected": True,
            "added_fields": ["订单", "去重客户数", "总收入（含平台商品补贴）明细"],
            "removed_fields": ["商品交易总额", "退款金额"],
            "match_rate": 61.5,
            "is_exact_match": False,
            "template_columns": ["日期", "商品交易总额", "退款金额"],
            "current_columns": ["日期", "订单", "去重客户数"],
        }

    class _FakeExecutorManager:
        async def run_cpu_intensive(self, *args, **kwargs):
            return _FakeDf()

    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(
        "backend.services.template_matcher.TemplateMatcher.detect_header_changes",
        _fake_detect_header_changes,
    )

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "tiktok", "domain": "products", "granularity": "monthly"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    file_row = payload["data"]["files"][0]
    assert file_row["has_template"] is True
    assert file_row["template_status"] == "update_required"
    assert file_row["template_update_required"] is True
    assert "匹配率: 61.5%" in file_row["update_reason"]


@pytest.mark.asyncio
async def test_list_files_marks_file_as_parse_failed_when_template_status_evaluation_cannot_read_file(
    file_list_client,
    monkeypatch,
    tmp_path,
):
    client, session_factory = file_list_client

    excel_path = tmp_path / "miaoshou_inventory_snapshot_20260413_232430.xls"
    excel_path.write_text("placeholder", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="miaoshou",
                data_domain="inventory",
                granularity="snapshot",
                sub_domain=None,
                template_name="miaoshou_inventory__snapshot_v1",
                version=1,
                status="published",
                header_row=0,
                header_columns=["SKU", "库存"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CatalogFile(
                file_path=str(excel_path),
                file_name=excel_path.name,
                source="data/raw",
                platform_code="miaoshou",
                source_platform="miaoshou",
                data_domain="inventory",
                granularity="snapshot",
                sub_domain=None,
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    class _BrokenExecutorManager:
        async def run_cpu_intensive(self, *args, **kwargs):
            raise ValueError("无法读取大型.xls文件(10.96MB),文件可能损坏。建议:用Excel重新导出为标准.xlsx格式。")

    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _BrokenExecutorManager(),
    )

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "miaoshou", "domain": "inventory", "granularity": "snapshot"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    file_row = payload["data"]["files"][0]
    assert file_row["has_template"] is True
    assert file_row["template_status"] == "parse_failed"
    assert file_row["template_update_required"] is False
    assert "无法读取大型.xls文件" in file_row["update_reason"]


@pytest.mark.asyncio
async def test_list_files_marks_missing_file_as_file_missing_when_catalog_path_does_not_exist(
    file_list_client,
    tmp_path,
):
    client, session_factory = file_list_client

    missing_path = tmp_path / "missing_inventory_snapshot.xls"

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="miaoshou",
                data_domain="inventory",
                granularity="snapshot",
                sub_domain=None,
                template_name="miaoshou_inventory__snapshot_v1",
                version=1,
                status="published",
                header_row=0,
                header_columns=["SKU", "库存"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CatalogFile(
                file_path=str(missing_path),
                file_name=missing_path.name,
                source="data/raw",
                platform_code="miaoshou",
                source_platform="miaoshou",
                data_domain="inventory",
                granularity="snapshot",
                sub_domain=None,
                status="failed",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "miaoshou", "domain": "inventory", "granularity": "snapshot", "status": "failed"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    file_row = payload["data"]["files"][0]
    assert file_row["has_template"] is True
    assert file_row["template_status"] == "file_missing"
    assert file_row["template_update_required"] is False
    assert "文件不存在" in file_row["update_reason"]


@pytest.mark.asyncio
async def test_list_files_excludes_semantic_anomaly_pending_file(file_list_client):
    client, session_factory = file_list_client

    async with session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path="data/raw/2026/tiktok_products_monthly_20260517_221824.xlsx",
                    file_name="tiktok_products_monthly_20260517_221824.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    status="pending",
                    first_seen_at=datetime.now(timezone.utc),
                ),
                CatalogFile(
                    file_path="data/raw/2026/tiktok_products_tiktok_monthly_20260407_123005.xlsx",
                    file_name="tiktok_products_tiktok_monthly_20260407_123005.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    sub_domain="tiktok",
                    status="pending",
                    first_seen_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "tiktok", "domain": "products", "granularity": "monthly", "status": "pending"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] == 1
    assert [row["file_name"] for row in payload["data"]["files"]] == [
        "tiktok_products_monthly_20260517_221824.xlsx"
    ]

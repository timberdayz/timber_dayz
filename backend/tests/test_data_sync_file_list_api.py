from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
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
async def test_list_files_without_status_returns_recent_ingested_asset_fields(
    file_list_client,
    tmp_path,
):
    client, session_factory = file_list_client

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / "shopee_orders_monthly_20260608_035100.xls"
    raw_file.write_text("demo", encoding="utf-8")
    meta_file = raw_file.with_suffix(".meta.json")
    meta_file.write_text('{"collection_info": {"collection_platform": "miaoshou"}}', encoding="utf-8")

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path=str(raw_file),
                file_name=raw_file.name,
                source="data/raw",
                platform_code="shopee",
                source_platform="miaoshou",
                data_domain="orders",
                granularity="monthly",
                status="ingested",
                first_seen_at=now,
                meta_file_path=str(meta_file),
            )
        )
        await session.commit()

    response = await client.get("/api/data-sync/files")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] == 1
    file_row = payload["data"]["files"][0]
    assert file_row["file_name"] == raw_file.name
    assert file_row["status"] == "ingested"
    assert file_row["platform"] == "shopee"
    assert file_row["business_platform"] == "shopee"
    assert file_row["collection_platform"] == "miaoshou"
    assert file_row["meta_file_path"] == str(meta_file)
    assert file_row["meta_exists"] is True
    assert file_row["catalog_registered"] is True


@pytest.mark.asyncio
async def test_list_files_filters_by_collection_task_id_from_meta_original_path(
    file_list_client,
    tmp_path,
):
    client, session_factory = file_list_client

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    matched_file = raw_dir / "matched.xlsx"
    matched_file.write_text("demo", encoding="utf-8")
    matched_meta = matched_file.with_suffix(".meta.json")
    matched_meta.write_text(
        '{"collection_info": {"original_path": "temp/downloads/task-abc-123/miaoshou/orders/export.xls"}}',
        encoding="utf-8",
    )
    other_file = raw_dir / "other.xlsx"
    other_file.write_text("demo", encoding="utf-8")
    other_meta = other_file.with_suffix(".meta.json")
    other_meta.write_text(
        '{"collection_info": {"original_path": "temp/downloads/task-other/miaoshou/orders/export.xls"}}',
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path=str(matched_file),
                    file_name=matched_file.name,
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="miaoshou",
                    data_domain="orders",
                    granularity="monthly",
                    status="ingested",
                    first_seen_at=now,
                    meta_file_path=str(matched_meta),
                ),
                CatalogFile(
                    file_path=str(other_file),
                    file_name=other_file.name,
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="miaoshou",
                    data_domain="orders",
                    granularity="monthly",
                    status="ingested",
                    first_seen_at=now,
                    meta_file_path=str(other_meta),
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/data-sync/files", params={"collection_task_id": "task-abc-123"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total"] == 1
    assert payload["data"]["files"][0]["file_name"] == matched_file.name


@pytest.mark.asyncio
async def test_get_file_detail_returns_raw_meta_and_catalog_sections(
    file_list_client,
    tmp_path,
):
    client, session_factory = file_list_client

    raw_file = tmp_path / "data" / "raw" / "2026" / "detail.xlsx"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text("demo", encoding="utf-8")
    meta_file = raw_file.with_suffix(".meta.json")
    meta_file.write_text(
        '{"collection_info": {"collection_platform": "miaoshou", "original_path": "temp/downloads/task-detail-1/export.xls"}}',
        encoding="utf-8",
    )

    async with session_factory() as session:
        record = CatalogFile(
            file_path=str(raw_file),
            file_name=raw_file.name,
            source="data/raw",
            platform_code="shopee",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="monthly",
            status="ingested",
            first_seen_at=datetime.now(timezone.utc),
            meta_file_path=str(meta_file),
        )
        session.add(record)
        await session.commit()
        file_id = record.id

    response = await client.get(f"/api/data-sync/files/{file_id}")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["raw_file"]["path"] == str(raw_file)
    assert payload["raw_file"]["exists"] is True
    assert payload["meta_file"]["path"] == str(meta_file)
    assert payload["meta_file"]["exists"] is True
    assert payload["meta_file"]["original_path"].endswith("task-detail-1/export.xls")
    assert payload["meta_file"]["collection_task_ids"] == ["task-detail-1"]
    assert payload["catalog_record"]["id"] == file_id
    assert payload["catalog_record"]["source_platform"] == "miaoshou"
    assert payload["catalog_record"]["platform_code"] == "shopee"


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
async def test_list_files_returns_semantic_contract_summary_for_required_field_gap(
    file_list_client,
    monkeypatch,
    tmp_path,
):
    client, session_factory = file_list_client

    excel_path = tmp_path / "shopee_orders_weekly_sample.xlsx"
    excel_path.write_text("placeholder", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="shopee",
                data_domain="orders",
                granularity="weekly",
                sub_domain=None,
                template_name="shopee_orders__weekly_v1",
                version=1,
                status="published",
                header_row=0,
                header_columns=["order_no", "shop_name", "order_created_at", "sold_qty", "buyer_paid", "profit_amount"],
                header_bindings=[
                    {"raw_name": "order_no", "semantic_key": "order_id"},
                    {"raw_name": "shop_name", "semantic_key": "shop_id"},
                    {"raw_name": "order_created_at", "semantic_key": "order_date"},
                    {"raw_name": "sold_qty", "semantic_key": "sales_volume"},
                    {"raw_name": "buyer_paid", "semantic_key": "paid_amount"},
                    {"raw_name": "profit_amount", "semantic_key": "profit"},
                ],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CatalogFile(
                file_path=str(excel_path),
                file_name=excel_path.name,
                source="data/raw",
                platform_code="shopee",
                source_platform="shopee",
                data_domain="orders",
                granularity="weekly",
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
            return self._Cols(["order_no", "shop_name", "order_created_at", "sold_qty", "profit_amount"])

    async def _fake_detect_header_changes(*args, **kwargs):
        return {
            "detected": True,
            "added_fields": [],
            "removed_fields": ["buyer_paid"],
            "match_rate": 83.3,
            "is_exact_match": False,
            "is_semantic_match": False,
            "template_columns": ["order_no", "shop_name", "order_created_at", "sold_qty", "buyer_paid", "profit_amount"],
            "current_columns": ["order_no", "shop_name", "order_created_at", "sold_qty", "profit_amount"],
            "blocking_changes": ["paid_amount"],
            "non_blocking_changes": [],
            "semantic_contract_status": "breaking_drift",
            "missing_required_keys": ["paid_amount"],
            "missing_optional_keys": [],
            "impact_descriptions": ["业务概览订单销售额/转化率无法计算"],
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
        params={"platform": "shopee", "domain": "orders", "granularity": "weekly"},
    )

    assert response.status_code == 200
    file_row = response.json()["data"]["files"][0]
    assert file_row["template_status"] == "update_required"
    assert file_row["governance_status"] == "breaking_drift"
    assert file_row["semantic_contract_status"] == "breaking_drift"
    assert file_row["missing_required_keys"] == ["paid_amount"]
    assert file_row["missing_optional_keys"] == []
    assert file_row["impact_descriptions"] == ["业务概览订单销售额/转化率无法计算"]
    assert file_row["template_update_required"] is True


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


@pytest.mark.asyncio
async def test_list_files_keeps_inventory_granularity_anomaly_visible_for_repair(file_list_client):
    client, session_factory = file_list_client

    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path="data/raw/2026/miaoshou_inventory_monthly_20260407_121357.xls",
                file_name="miaoshou_inventory_monthly_20260407_121357.xls",
                source="data/raw",
                platform_code="miaoshou",
                source_platform="miaoshou",
                data_domain="inventory",
                granularity="monthly",
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "miaoshou", "domain": "inventory", "status": "pending"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] == 1
    file_row = payload["data"]["files"][0]
    assert file_row["file_name"] == "miaoshou_inventory_monthly_20260407_121357.xls"
    assert file_row["template_status"] == "semantic_invalid"
    assert file_row["governance_status"] == "semantic_invalid"
    assert file_row["semantic_anomaly_type"] == "inventory_granularity_invalid"


@pytest.mark.asyncio
async def test_list_files_includes_inventory_granularity_anomaly_with_repair_context(file_list_client):
    client, session_factory = file_list_client

    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path="data/raw/2026/miaoshou_inventory_monthly_20260407_121357.xls",
                file_name="miaoshou_inventory_monthly_20260407_121357.xls",
                source="data/raw",
                platform_code="miaoshou",
                source_platform="miaoshou",
                data_domain="inventory",
                granularity="monthly",
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "miaoshou", "domain": "inventory", "status": "pending"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] == 1

    file_row = payload["data"]["files"][0]
    assert file_row["file_name"] == "miaoshou_inventory_monthly_20260407_121357.xls"
    assert file_row["template_status"] == "semantic_invalid"
    assert file_row["governance_status"] == "semantic_invalid"
    assert file_row["semantic_anomaly_type"] == "inventory_granularity_invalid"
    assert file_row["semantic_repair_action"] == "repair_inventory_snapshot"


@pytest.mark.asyncio
async def test_list_files_returns_hidden_and_raw_unregistered_hints(file_list_client, tmp_path, monkeypatch):
    client, session_factory = file_list_client

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / "shopee_orders_monthly_20260608_010000.xlsx"
    raw_file.write_text("demo", encoding="utf-8")

    from backend.domains.data_platform.routers import data_sync as router_module

    monkeypatch.setattr(router_module, "get_data_raw_dir", lambda: tmp_path / "data" / "raw", raising=False)

    async with session_factory() as session:
        session.add(
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
            )
        )
        await session.commit()

    response = await client.get("/api/data-sync/files", params={"status": "pending"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["files"] == []
    assert payload["data"]["hidden_semantic_invalid_count"] == 1
    assert payload["data"]["raw_unregistered_hint"]["candidate_count"] == 1
    assert payload["data"]["raw_unregistered_hint"]["official_unregistered_count"] == 1
    assert payload["data"]["raw_unregistered_hint"]["repaired_cache_count"] == 0


@pytest.mark.asyncio
async def test_list_files_diagnostics_classifies_repaired_and_legacy_raw_files(
    file_list_client,
    tmp_path,
    monkeypatch,
):
    client, _session_factory = file_list_client

    official_dir = tmp_path / "data" / "raw" / "2026"
    official_dir.mkdir(parents=True, exist_ok=True)
    official_file = official_dir / "shopee_orders_monthly_20260608_010000.xlsx"
    official_file.write_text("demo", encoding="utf-8")
    official_file.with_suffix(".meta.json").write_text("{}", encoding="utf-8")

    repaired_dir = tmp_path / "data" / "raw" / "repaired" / "2025"
    repaired_dir.mkdir(parents=True, exist_ok=True)
    repaired_file = repaired_dir / "shopee_orders_monthly_20250925_105724.xlsx"
    repaired_file.write_text("demo", encoding="utf-8")

    legacy_dir = tmp_path / "data" / "raw" / "2025"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / "tiktok_analytics_daily_20250923_205930.xlsx"
    legacy_file.write_text("demo", encoding="utf-8")

    from backend.domains.data_platform.routers import data_sync as router_module

    monkeypatch.setattr(router_module, "get_data_raw_dir", lambda: tmp_path / "data" / "raw", raising=False)

    response = await client.get("/api/data-sync/files")

    assert response.status_code == 200
    payload = response.json()
    raw_hint = payload["data"]["raw_unregistered_hint"]
    assert raw_hint["official_unregistered_count"] == 1
    assert raw_hint["candidate_count"] == 1
    assert raw_hint["repaired_cache_count"] == 1
    assert raw_hint["legacy_without_meta_count"] == 1
    assert str(repaired_file) not in raw_hint["sample_files"]
    assert str(legacy_file) not in raw_hint["sample_files"]


@pytest.mark.asyncio
async def test_refresh_data_sync_files_scans_data_raw(file_list_client, tmp_path, monkeypatch):
    client, _session_factory = file_list_client

    from backend.domains.data_platform.routers import data_sync as router_module

    calls = []

    def fake_scan_and_register(base_dir):
        calls.append(base_dir)
        return SimpleNamespace(seen=3, registered=2, skipped=1, new_file_ids=[10, 11])

    monkeypatch.setattr(router_module, "get_data_raw_dir", lambda: tmp_path / "data" / "raw", raising=False)
    monkeypatch.setattr(router_module, "scan_and_register", fake_scan_and_register, raising=False)

    response = await client.post("/api/data-sync/files/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == {
        "seen": 3,
        "registered": 2,
        "skipped": 1,
        "new_file_ids": [10, 11],
    }
    assert calls == [tmp_path / "data" / "raw"]


@pytest.mark.asyncio
async def test_data_sync_file_diagnostics_reports_unregistered_raw_candidates(
    file_list_client,
    tmp_path,
    monkeypatch,
):
    client, session_factory = file_list_client

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / "shopee_orders_monthly_20260608_010000.xlsx"
    raw_file.write_text("demo", encoding="utf-8")

    from backend.domains.data_platform.routers import data_sync as router_module

    monkeypatch.setattr(router_module, "get_data_raw_dir", lambda: tmp_path / "data" / "raw", raising=False)

    async with session_factory() as session:
        session.add(
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
            )
        )
        await session.commit()

    response = await client.get("/api/data-sync/files/diagnostics", params={"hours": 24})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["raw_file_count"] == 1
    assert payload["data"]["catalog_file_count"] == 1
    assert payload["data"]["unregistered_raw_candidates"] == 1
    assert payload["data"]["semantic_invalid_count"] == 1
    assert payload["data"]["recommendations"]


@pytest.mark.asyncio
async def test_repair_inventory_snapshot_semantics_endpoint_updates_catalog_record(file_list_client, tmp_path):
    client, session_factory = file_list_client

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    wrong_file = raw_dir / "miaoshou_inventory_monthly_20260407_121357.xls"
    wrong_file.write_text("demo", encoding="utf-8")
    meta_path = wrong_file.with_suffix(".meta.json")
    meta_path.write_text(
        '{"business_metadata": {"granularity": "monthly"}}',
        encoding="utf-8",
    )

    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path=str(wrong_file),
                file_name=wrong_file.name,
                source="data/raw",
                platform_code="miaoshou",
                source_platform="miaoshou",
                data_domain="inventory",
                granularity="monthly",
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.post("/api/data-sync/repair-inventory-snapshot-semantics", json=[])

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["repaired_count"] == 1

    async with session_factory() as session:
        result = await session.execute(select(CatalogFile))
        repaired = result.scalar_one()
        assert repaired.granularity == "snapshot"
        assert repaired.file_name == "miaoshou_inventory_snapshot_20260407_121357.xls"

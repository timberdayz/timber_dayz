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
async def grading_session_factory():
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


@pytest.mark.asyncio
async def test_template_status_service_allows_optional_field_drop_for_shopee_orders_monthly(
    grading_session_factory, tmp_path
):
    from backend.services.data_sync_template_status_service import DataSyncTemplateStatusService

    now = datetime.now(timezone.utc)
    file_path = tmp_path / "shopee_orders_monthly_20260617_104634.xls"
    file_path.write_text("demo", encoding="utf-8")

    async with grading_session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            template_name="shopee_orders__monthly_v6",
            version=6,
            status="published",
            header_row=1,
            header_columns=[
                "订单编号",
                "订单状态",
                "售后状态",
                "产品ID",
                "平台SKU",
                "SKU ID",
                "平台产品标题",
                "规格",
                "商品名称",
                "商品SKU",
                "商品类型",
                "出库仓库",
                "出库数量",
                "采购单号",
                "采购平台",
                "采购时间",
                "采购账号",
                "销售数量",
                "店铺",
                "下单时间",
                "付款时间",
                "发货时间",
                "利润(RMB)",
                "利润",
                "成本利润率",
                "销售利润率",
                "预估回款金额(RMB)",
                "预估回款金额",
                "已结算金额(RMB)",
                "已结算金额",
                "结算时间",
                "买家支付(RMB)",
                "买家支付",
                "订单原始金额(RMB)",
                "订单原始金额",
                "产品原价(RMB)",
                "产品原价",
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
            current_columns=[
                "订单编号",
                "订单状态",
                "售后状态",
                "产品ID",
                "平台SKU",
                "SKU ID",
                "平台产品标题",
                "规格",
                "商品名称",
                "商品SKU",
                "商品类型",
                "出库仓库",
                "出库数量",
                "采购单号",
                "采购平台",
                "采购时间",
                "采购账号",
                "销售数量",
                "店铺",
                "下单时间",
                "付款时间",
                "发货时间",
                "利润(RMB)",
                "利润",
                "成本利润率",
                "销售利润率",
                "已结算金额(RMB)",
                "已结算金额",
                "结算时间",
                "买家支付(RMB)",
                "买家支付",
                "订单原始金额(RMB)",
                "订单原始金额",
                "产品原价(RMB)",
                "产品原价",
            ],
        )

    assert status["template_status"] == "alias_only"
    assert status["template_update_required"] is False
    assert status["should_auto_sync"] is True
    assert status["header_changes"]["blocking_changes"] == []
    assert status["header_changes"]["non_blocking_changes"]


@pytest.mark.asyncio
async def test_template_matcher_uses_semantic_contract_for_orders_weekly_optional_drop(
    grading_session_factory,
):
    from backend.services.template_matcher import TemplateMatcher

    now = datetime.now(timezone.utc)
    async with grading_session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="weekly",
            sub_domain=None,
            template_name="shopee_orders__weekly_v1",
            version=1,
            status="published",
            header_row=0,
            header_columns=["订单编号", "店铺", "下单时间", "销售数量", "买家支付", "利润", "预估回款金额"],
            header_bindings=[
                {"raw_name": "订单编号", "semantic_key": "order_id"},
                {"raw_name": "店铺", "semantic_key": "shop_id"},
                {"raw_name": "下单时间", "semantic_key": "order_date"},
                {"raw_name": "销售数量", "semantic_key": "sales_volume"},
                {"raw_name": "买家支付", "semantic_key": "paid_amount"},
                {"raw_name": "利润", "semantic_key": "profit"},
                {"raw_name": "预估回款金额", "semantic_key": "estimated_settlement_amount"},
            ],
            created_at=now,
            updated_at=now,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

        matcher = TemplateMatcher(session)
        header_changes = await matcher.detect_header_changes(
            template.id,
            ["订单编号", "店铺", "下单时间", "销售数量", "买家支付", "利润"],
        )

    assert header_changes["detected"] is True
    assert header_changes["semantic_contract_status"] == "non_breaking_drift"
    assert header_changes["blocking_changes"] == []
    assert header_changes["missing_required_keys"] == []
    assert header_changes["missing_optional_keys"] == ["estimated_settlement_amount"]


def test_auto_ingest_marks_template_update_required_when_readiness_blocks(
    monkeypatch,
):
    from backend.tasks import scheduled_tasks as scheduled_module
    original_asyncio_run = __import__("asyncio").run

    records = {}
    file_record = type(
        "CatalogFile",
        (),
        {"id": 2849, "status": "processing", "file_metadata": {}, "error_message": None},
    )()

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [2849]

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _FakeAsyncSession:
        async def get(self, model, key):
            return file_record

        async def commit(self):
            records["async_commit"] = True

        async def rollback(self):
            return None

        async def close(self):
            return None

    class _FakeTaskCenterSyncService:
        def __init__(self, db):
            self.db = db

        def create_task(self, **fields):
            records["created"] = fields
            return type("Task", (), {"task_id": fields["task_id"]})()

        def get_task(self, task_id):
            return type("Task", (), {"task_id": task_id})()

        def update_task(self, task, **updates):
            records["updated"] = updates
            return task

        def add_link(self, *args, **kwargs):
            return None

    class _FakeDataSyncService:
        def __init__(self, db):
            self.db = db

        async def get_file_sync_readiness(self, file_id, use_template_header_row=True):
            return {
                "ready": False,
                "file_id": file_id,
                "file_name": "shopee_orders_monthly_20260617_104634.xls",
                "template_status": "update_required",
                "should_auto_sync": False,
                "update_reason": "新增0个字段, 删除1个字段 (匹配率: 98.5%)",
            }

        async def sync_single_file(self, *args, **kwargs):
            raise AssertionError("sync_single_file should not run for update_required")

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(scheduled_module, "reset_async_engine_pool_for_new_loop", lambda: None, raising=False)
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _FakeAsyncSession())
    monkeypatch.setattr("backend.services.data_sync_service.DataSyncService", _FakeDataSyncService)
    monkeypatch.setattr("backend.services.task_center_sync_service.TaskCenterSyncService", _FakeTaskCenterSyncService)
    monkeypatch.setattr(scheduled_module.asyncio, "run", lambda coro: original_asyncio_run(coro))

    result = scheduled_module.auto_ingest_pending_files(max_files=1)

    assert result["status"] == "success"
    assert result["summary"]["skipped_template_update"] == 1
    assert records["updated"]["status"] == "partial_success"
    assert records["updated"]["details_json"]["task_details"]["skipped_template_update"] == 1
    assert file_record.status == "template_update_required"
    assert file_record.error_message == "新增0个字段, 删除1个字段 (匹配率: 98.5%)"
    assert file_record.file_metadata["auto_ingest"]["last_status"] == "template_update_required"

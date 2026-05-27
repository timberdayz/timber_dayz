from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services.data_sync_service import DataSyncService


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, file_record):
        self.file_record = file_record
        self.commit_calls = 0
        self.rollback_calls = 0

    async def execute(self, _query):
        return _FakeResult(self.file_record)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


class _TemplateStub:
    id = 1
    template_name = "demo_template"
    header_row = 0
    header_columns = ["订单编号", "金额"]


class _TemplateMatcherStub:
    async def find_best_template(self, **_kwargs):
        return _TemplateStub()

    async def detect_header_changes(self, **_kwargs):
        return {
            "detected": False,
            "match_rate": 100.0,
            "added_fields": [],
            "removed_fields": [],
            "template_columns": ["订单编号", "金额"],
            "current_columns": ["订单编号", "金额"],
        }


class _TemplateStatusServiceStub:
    async def evaluate_catalog_file(self, *args, **kwargs):
        return {
            "template_status": "ready",
            "has_template": True,
            "template_name": "demo_template",
            "template_header_row": 0,
            "template_update_required": False,
            "update_reason": None,
            "error_code": None,
            "should_auto_sync": True,
            "exact_match": True,
            "semantic_match": True,
            "header_changes": {
                "detected": False,
                "match_rate": 100.0,
                "added_fields": [],
                "removed_fields": [],
            },
        }


class _ExecutorManagerStub:
    async def run_cpu_intensive(self, func, *args, **kwargs):
        return func(*args, **kwargs)


async def _failed_ingest_stub(**_kwargs):
    return {
        "success": False,
        "message": "数据同步失败:raw_storage,boom",
        "status": "failed",
    }


async def _success_ingest_stub(**_kwargs):
    return {
        "success": True,
        "message": "入库成功",
        "status": "success",
        "imported": 1,
        "quarantined": 0,
        "import_stats": {"inserted": 1, "updated": 0, "skipped": 0},
    }


@pytest.mark.asyncio
async def test_failed_sync_updates_catalog_file_status_and_error_message(monkeypatch, tmp_path):
    file_path = tmp_path / "orders.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2391,
        file_path=str(file_path),
        file_name="orders.xlsx",
        status="pending",
        error_message=None,
        file_metadata=None,
        data_domain="orders",
        platform_code="shopee",
        source_platform="shopee",
        shop_id="shop-1",
        granularity="daily",
        sub_domain=None,
        last_processed_at=None,
    )
    fake_db = _FakeDb(file_record)
    service = DataSyncService(fake_db)

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(service, "template_matcher", _TemplateMatcherStub())
    monkeypatch.setattr(service, "template_status_service", _TemplateStatusServiceStub())
    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.data_sync_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"订单编号": "A001", "金额": "10"}]),
    )
    monkeypatch.setattr(
        service.ingestion_service,
        "ingest_data",
        _failed_ingest_stub,
    )

    result = await service.sync_single_file(
        file_id=2391,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2391_contract",
        use_template_header_row=True,
    )

    assert result["success"] is False
    assert file_record.status == "failed"
    assert file_record.error_message == "数据同步失败:raw_storage,boom"


@pytest.mark.asyncio
async def test_successful_sync_clears_stale_error_and_updates_last_processed_at(monkeypatch, tmp_path):
    file_path = tmp_path / "orders.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2392,
        file_path=str(file_path),
        file_name="orders.xlsx",
        status="pending",
        error_message="old failure",
        file_metadata=None,
        data_domain="orders",
        platform_code="shopee",
        source_platform="shopee",
        shop_id="shop-1",
        granularity="daily",
        sub_domain=None,
        last_processed_at=None,
    )
    fake_db = _FakeDb(file_record)
    service = DataSyncService(fake_db)

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(service, "template_matcher", _TemplateMatcherStub())
    monkeypatch.setattr(service, "template_status_service", _TemplateStatusServiceStub())
    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.data_sync_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"订单编号": "A001", "金额": "10"}]),
    )
    monkeypatch.setattr(
        service.ingestion_service,
        "ingest_data",
        _success_ingest_stub,
    )

    result = await service.sync_single_file(
        file_id=2392,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2392_contract",
        use_template_header_row=True,
    )

    assert result["success"] is True
    assert file_record.status == "ingested"
    assert file_record.error_message is None
    assert file_record.last_processed_at is not None

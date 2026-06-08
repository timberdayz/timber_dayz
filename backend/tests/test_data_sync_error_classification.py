from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services.data_ingestion_service import DataIngestionService


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, file_record):
        self.file_record = file_record

    async def execute(self, _query):
        return _FakeResult(self.file_record)

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeExecutorManager:
    async def run_cpu_intensive(self, func, *args, **kwargs):
        return func(*args, **kwargs)


class _FakeRawImporter:
    async def async_batch_insert_raw_data(self, **_kwargs):
        raise RuntimeError("boom from importer")


class _FakeDeduplicationService:
    def __init__(self, _db):
        pass

    def batch_calculate_data_hash(self, rows, deduplication_fields=None, header_bindings=None, **_kwargs):
        return [f"hash-{index}" for index, _ in enumerate(rows)]


def test_format_sync_stage_error_uses_stage_label_instead_of_blame_shift():
    from backend.services.data_ingestion_service import _format_sync_stage_error

    message = _format_sync_stage_error(
        stage="raw_storage",
        detail="Field normalization collision",
    )

    assert "RawDataImporter异常" not in message
    assert message == "数据同步失败:raw_storage,Field normalization collision"


@pytest.mark.asyncio
async def test_ingest_data_reports_raw_storage_stage_for_importer_failures(
    monkeypatch,
    tmp_path,
):
    file_path = tmp_path / "orders.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=1,
        file_path=str(file_path),
        file_name="orders.xlsx",
        status="pending",
        error_message=None,
        data_domain="orders",
        platform_code="shopee",
        shop_id="shop-1",
        granularity="daily",
        sub_domain=None,
    )
    fake_db = _FakeDb(file_record)
    service = DataIngestionService(fake_db)

    monkeypatch.setattr(
        "backend.services.data_ingestion_service.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"订单号": "A001"}]),
    )
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.normalize_table",
        lambda df, **_kwargs: (df, {"strategy": "none", "filled_rows": 0, "filled_columns": []}),
    )
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.get_raw_data_importer",
        lambda _db: _FakeRawImporter(),
    )
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.DeduplicationService",
        _FakeDeduplicationService,
    )

    result = await service.ingest_data(
        file_id=1,
        platform="shopee",
        domain="orders",
        mappings=None,
        header_row=0,
    )

    assert result["success"] is False
    assert result["message"].startswith("数据同步失败:raw_storage,")
    assert "boom from importer" in result["message"]

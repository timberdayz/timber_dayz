import pytest
from pathlib import Path


def test_analytics_raw_contract_preserves_coexisting_source_columns():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    row = {
        "订单数": 10,
        "SKU 订单数": 14,
        "GMV": 100.0,
    }

    normalized = normalize_row_fields_for_domain(
        domain="analytics",
        row=row,
    )

    assert "订单数" in normalized
    assert "SKU 订单数" in normalized
    assert normalized["订单数"] == 10
    assert normalized["SKU 订单数"] == 14
    assert normalized["GMV"] == 100.0


def test_orders_raw_contract_preserves_distinct_currency_source_fields():
    from backend.services.data_ingestion_service import normalize_row_fields_for_domain

    normalized = normalize_row_fields_for_domain(
        domain="orders",
        row={
            "VAT(RMB)": 1.2,
            "SST(RMB)": 2.3,
        },
    )

    assert "VAT(RMB)" in normalized
    assert "SST(RMB)" in normalized
    assert normalized["VAT(RMB)"] == 1.2
    assert normalized["SST(RMB)"] == 2.3


@pytest.mark.asyncio
async def test_template_recognized_columns_are_passed_through_to_raw_importer(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import pandas as pd

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

    class _FakeDeduplicationService:
        def __init__(self, _db):
            pass

        def batch_calculate_data_hash(self, rows, deduplication_fields=None, header_bindings=None, **_kwargs):
            return [f"hash-{index}" for index, _ in enumerate(rows)]

    captured = {}

    class _FakeRawImporter:
        def _extract_period_dates_by_rules(self, row, field_parse_rules):
            from backend.services.raw_data_importer import RawDataImporter

            importer = RawDataImporter.__new__(RawDataImporter)
            importer.file_date_from = file_record.date_from
            importer.file_date_to = file_record.date_to
            return importer._extract_period_dates_by_rules(row, field_parse_rules)

        async def async_batch_insert_raw_data(self, **kwargs):
            captured.update(kwargs)
            return {"inserted": 1, "updated": 0, "skipped": 0}

    file_path = tmp_path / "analytics.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2391,
        file_path=str(file_path),
        file_name="analytics.xlsx",
        status="pending",
        error_message=None,
        data_domain="analytics",
        platform_code="tiktok",
        shop_id="shop-1",
        granularity="monthly",
        sub_domain=None,
        last_processed_at=None,
    )

    service = DataIngestionService(_FakeDb(file_record))

    monkeypatch.setattr(
        "backend.services.data_ingestion_service.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame(
            [{"日期": "2026-03-01", "订单数": 10, "SKU 订单数": 14}]
        ),
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
        file_id=2391,
        platform="tiktok",
        domain="analytics",
        mappings=None,
        header_columns=["日期", "订单数", "SKU 订单数"],
        header_row=8,
        template_id=328,
    )

    assert result["success"] is True
    assert captured["rows"][0]["订单数"] == 10
    assert captured["rows"][0]["SKU 订单数"] == 14
    assert captured["header_columns"] == ["日期", "订单数", "SKU 订单数"]
    assert captured["original_header_columns"] == ["日期", "订单数", "SKU 订单数"]
    assert captured["template_id"] == 328


@pytest.mark.asyncio
async def test_ingest_data_passes_file_date_range_to_raw_importer(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import pandas as pd

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

    class _FakeDeduplicationService:
        def __init__(self, _db):
            pass

        def batch_calculate_data_hash(self, rows, deduplication_fields=None, header_bindings=None, **_kwargs):
            return [f"hash-{index}" for index, _ in enumerate(rows)]

    captured = {}

    class _FakeRawImporter:
        async def async_batch_insert_raw_data(self, **kwargs):
            captured["file_date_from"] = getattr(self, "file_date_from", None)
            captured["file_date_to"] = getattr(self, "file_date_to", None)
            captured.update(kwargs)
            return {"inserted": 1, "updated": 0, "skipped": 0}

    file_path = tmp_path / "analytics.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2398,
        file_path=str(file_path),
        file_name="analytics.xlsx",
        status="pending",
        error_message=None,
        data_domain="analytics",
        platform_code="tiktok",
        shop_id="shop-1",
        granularity="daily",
        sub_domain=None,
        date_from=pd.Timestamp("2026-05-16").date(),
        date_to=pd.Timestamp("2026-05-16").date(),
        last_processed_at=None,
    )

    service = DataIngestionService(_FakeDb(file_record))

    monkeypatch.setattr(
        "backend.services.data_ingestion_service.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"日期": "2026-05-16", "订单数": 10}]),
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
        file_id=2398,
        platform="tiktok",
        domain="analytics",
        mappings=None,
        header_columns=["日期", "订单数"],
        header_row=8,
        template_id=328,
    )

    assert result["success"] is True
    assert captured["file_date_from"] == pd.Timestamp("2026-05-16").date()
    assert captured["file_date_to"] == pd.Timestamp("2026-05-16").date()


def test_data_ingestion_hash_uses_template_field_parse_rules():
    text = Path("backend/services/data_ingestion_service.py").read_text(encoding="utf-8")
    sync_text = Path("backend/services/data_sync_service.py").read_text(encoding="utf-8")

    assert "field_parse_rules: Optional[List[Dict[str, Any]]] = None" in text
    assert "raw_importer.field_parse_rules = field_parse_rules" in text
    assert "hash_identity_values = _build_hash_identity_values(" in text
    assert "identity_values=hash_identity_values" in text
    assert "resolved_field_parse_rules" in sync_text


@pytest.mark.asyncio
async def test_ingest_data_passes_date_context_to_async_raw_importer(monkeypatch, tmp_path):
    from datetime import date
    from types import SimpleNamespace

    import pandas as pd

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

    class _FakeDeduplicationService:
        def __init__(self, _db):
            pass

        def batch_calculate_data_hash(self, rows, **_kwargs):
            return [f"hash-{index}" for index, _ in enumerate(rows)]

    captured = {}

    class _FakeRawImporter:
        def _extract_period_dates_by_rules(self, row, field_parse_rules):
            from backend.services.raw_data_importer import RawDataImporter

            importer = RawDataImporter.__new__(RawDataImporter)
            importer.file_date_from = file_record.date_from
            importer.file_date_to = file_record.date_to
            return importer._extract_period_dates_by_rules(row, field_parse_rules)

        async def async_batch_insert_raw_data(self, **kwargs):
            captured.update(kwargs)
            return {"inserted": 1, "updated": 0, "skipped": 0}

    file_path = tmp_path / "shopee_products_monthly_20260608_143141.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2545,
        file_path=str(file_path),
        file_name=file_path.name,
        status="pending",
        error_message=None,
        data_domain="products",
        platform_code="shopee",
        shop_id="1540271744",
        granularity="monthly",
        sub_domain=None,
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 30),
        last_processed_at=None,
    )

    service = DataIngestionService(_FakeDb(file_record))
    parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        }
    ]
    header_bindings = [{"source_header": "商品编号", "semantic_key": "product_id"}]

    monkeypatch.setattr(
        "backend.services.data_ingestion_service.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"商品编号": "sku-1", "商品": "item"}]),
    )
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.normalize_table",
        lambda df, **_kwargs: (
            df,
            {"strategy": "none", "filled_rows": 0, "filled_columns": []},
        ),
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
        file_id=2545,
        platform="shopee",
        domain="products",
        mappings=None,
        header_columns=["商品编号", "商品"],
        header_row=0,
        template_id=296,
        field_parse_rules=parse_rules,
        header_bindings=header_bindings,
    )

    assert result["success"] is True
    assert captured["file_date_from"] == date(2026, 4, 1)
    assert captured["file_date_to"] == date(2026, 4, 30)
    assert captured["field_parse_rules"] == parse_rules
    assert captured["header_bindings"] == header_bindings

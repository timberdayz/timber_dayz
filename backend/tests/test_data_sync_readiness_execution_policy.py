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
    template_name = "orders_weekly_variant"
    header_row = 0
    header_columns = ["order_id", "estimated_settlement"]
    deduplication_fields = ["order_id"]
    header_bindings = [{"raw_name": "order_number", "semantic_key": "order_id"}]
    field_parse_rules = []
    sub_domain = None


class _HeaderDriftTemplateMatcherStub:
    async def find_best_template(self, **_kwargs):
        return _TemplateStub()

    async def detect_header_changes(self, **_kwargs):
        return {
            "detected": True,
            "match_rate": 85.5,
            "added_fields": ["order_number", "extra_service_fee"],
            "removed_fields": ["order_id", "estimated_settlement"],
            "template_columns": ["order_id", "estimated_settlement"],
            "current_columns": ["order_number", "extra_service_fee"],
        }


class _NonBreakingDriftStatusServiceStub:
    async def evaluate_catalog_file(self, *args, **kwargs):
        return {
            "template_status": "ready",
            "governance_status": "non_breaking_drift",
            "semantic_contract_status": "non_breaking_drift",
            "has_template": True,
            "template_name": "orders_weekly_variant",
            "template_header_row": 0,
            "template_update_required": False,
            "update_reason": None,
            "error_code": None,
            "should_auto_sync": True,
            "exact_match": False,
            "semantic_match": True,
            "missing_required_keys": [],
            "blocking_changes": [],
            "header_changes": {
                "detected": True,
                "match_rate": 85.5,
                "added_fields": ["order_number", "extra_service_fee"],
                "removed_fields": ["order_id", "estimated_settlement"],
            },
        }


class _ExecutorManagerStub:
    async def run_cpu_intensive(self, func, *args, **kwargs):
        return func(*args, **kwargs)


@pytest.mark.asyncio
async def test_sync_single_file_allows_header_drift_when_readiness_auto_syncs(
    monkeypatch,
    tmp_path,
):
    file_path = tmp_path / "orders.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2395,
        file_path=str(file_path),
        file_name="shopee_orders_weekly_20260626_182428.xls",
        status="pending",
        error_message=None,
        file_metadata=None,
        data_domain="orders",
        platform_code="shopee",
        source_platform="shopee",
        shop_id="shop-1",
        granularity="weekly",
        sub_domain=None,
        last_processed_at=None,
    )
    service = DataSyncService(_FakeDb(file_record))
    captured = {}

    async def _capture_ingest(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "message": "ingested",
            "status": "success",
            "imported": 1,
            "quarantined": 0,
            "import_stats": {"inserted": 1, "updated": 0, "skipped": 0},
        }

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(service, "template_matcher", _HeaderDriftTemplateMatcherStub())
    monkeypatch.setattr(service, "template_status_service", _NonBreakingDriftStatusServiceStub())
    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.data_sync_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame(
            [{"order_number": "A001", "extra_service_fee": "0"}]
        ),
    )
    monkeypatch.setattr(service.ingestion_service, "ingest_data", _capture_ingest)

    result = await service.sync_single_file(
        file_id=2395,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2395_contract",
        use_template_header_row=True,
    )

    assert result["success"] is True
    assert result["sync_mode"] == "semantic_drift_allowed"
    assert result.get("error_code") != "HEADER_CHANGED"
    assert captured["file_id"] == 2395

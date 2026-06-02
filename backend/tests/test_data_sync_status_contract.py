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


class _TemplateResolverStub:
    def __init__(self, template_id):
        self.template_id = template_id

    async def resolve(self, **_kwargs):
        return {
            "matched": True,
            "governance_status": "ready",
            "family": None,
            "active_version": None,
            "variant": {
                "source_legacy_template_id": self.template_id,
            },
            "shadow_compare": {"is_consistent": True},
        }


class _TwoPhaseTemplateResolverStub:
    def __init__(self, template_id, semantic_bindings, deduplication_fields):
        self.template_id = template_id
        self.semantic_bindings = semantic_bindings
        self.deduplication_fields = deduplication_fields
        self.calls = []

    async def resolve(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "matched": False,
                "governance_status": "missing_variant",
                "family": None,
                "active_version": None,
                "variant": None,
                "semantic_bindings": [],
                "shadow_compare": {"is_consistent": False},
            }
        return {
            "matched": True,
            "governance_status": "ready",
            "family": {"id": 15},
            "active_version": {"id": 8, "deduplication_fields": self.deduplication_fields},
            "variant": {
                "id": 3,
                "source_legacy_template_id": self.template_id,
            },
            "semantic_bindings": self.semantic_bindings,
            "shadow_compare": {"is_consistent": True},
        }


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


@pytest.mark.asyncio
async def test_sync_single_file_prefers_resolver_selected_legacy_template(monkeypatch, tmp_path):
    file_path = tmp_path / "orders.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2393,
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

    chosen_template = SimpleNamespace(
        id=888,
        template_name="resolver_selected_template",
        header_row=0,
        header_columns=["订单编号", "金额"],
        deduplication_fields=["订单编号"],
        sub_domain=None,
    )

    async def _fake_db_get(model, value):
        assert value == 888
        return chosen_template

    captured = {}

    async def _capture_ingest(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "message": "入库成功",
            "status": "success",
            "imported": 1,
            "quarantined": 0,
            "import_stats": {"inserted": 1, "updated": 0, "skipped": 0},
        }

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(service, "template_matcher", _TemplateMatcherStub())
    monkeypatch.setattr(service, "template_status_service", _TemplateStatusServiceStub())
    monkeypatch.setattr(service, "template_resolver", _TemplateResolverStub(888))
    monkeypatch.setattr(service.db, "get", _fake_db_get, raising=False)
    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.data_sync_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"订单编号": "A001", "金额": "10"}]),
    )
    monkeypatch.setattr(service.ingestion_service, "ingest_data", _capture_ingest)

    result = await service.sync_single_file(
        file_id=2393,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2393_contract",
        use_template_header_row=True,
    )

    assert result["success"] is True
    assert captured["template_id"] == 888


@pytest.mark.asyncio
async def test_sync_single_file_re_resolves_after_preview_and_uses_semantic_payload(
    monkeypatch,
    tmp_path,
):
    file_path = tmp_path / "orders.xlsx"
    file_path.write_bytes(b"test")

    file_record = SimpleNamespace(
        id=2394,
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

    matcher_template = SimpleNamespace(
        id=777,
        template_name="matcher_template",
        header_row=0,
        header_columns=["订单号", "金额"],
        header_bindings=[{"raw_name": "订单号", "semantic_key": "order_id"}],
        deduplication_fields=["订单号"],
        sub_domain=None,
    )
    resolver_template = SimpleNamespace(
        id=889,
        template_name="resolver_template",
        header_row=0,
        header_columns=["订单编号", "金额"],
        header_bindings=[{"raw_name": "订单编号", "semantic_key": "order_id"}],
        deduplication_fields=["order_id"],
        sub_domain=None,
    )
    resolver_bindings = [
        {
            "raw_name": "订单编号",
            "display_name": "订单编号",
            "semantic_key": "order_id",
            "required": True,
            "hash_participates": True,
        }
    ]
    resolver = _TwoPhaseTemplateResolverStub(
        889,
        resolver_bindings,
        ["order_id"],
    )

    async def _fake_db_get(model, value):
        assert value == 889
        return resolver_template

    captured = {}

    async def _capture_ingest(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "message": "入库成功",
            "status": "success",
            "imported": 1,
            "quarantined": 0,
            "import_stats": {"inserted": 0, "updated": 1, "skipped": 0},
        }

    matcher = _TemplateMatcherStub()

    async def _matcher_find_best_template(**_kwargs):
        return matcher_template

    matcher.find_best_template = _matcher_find_best_template

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(service, "template_matcher", matcher)
    monkeypatch.setattr(service, "template_status_service", _TemplateStatusServiceStub())
    monkeypatch.setattr(service, "template_resolver", resolver)
    monkeypatch.setattr(service.db, "get", _fake_db_get, raising=False)
    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.data_sync_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"订单编号": "A001", "金额": "10"}]),
    )
    monkeypatch.setattr(service.ingestion_service, "ingest_data", _capture_ingest)

    result = await service.sync_single_file(
        file_id=2394,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2394_contract",
        use_template_header_row=True,
    )

    assert result["success"] is True
    assert captured["template_id"] == 889
    assert captured["deduplication_fields"] == ["order_id"]
    assert captured["header_bindings"] == resolver_bindings
    assert len(resolver.calls) == 2
    assert resolver.calls[1]["header_columns"] == ["订单编号", "金额"]
    assert resolver.calls[1]["sample_rows"] == [{"订单编号": "A001", "金额": "10"}]

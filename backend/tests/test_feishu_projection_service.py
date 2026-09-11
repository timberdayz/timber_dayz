import asyncio
from datetime import datetime, timezone
from pathlib import Path

from backend.services.feishu_projection_service import (
    FeishuProjectionService,
    _sku_table_fields,
    _spu_table_fields,
    projection_payload_hash,
)
from modules.core.db import FeishuProjectionLog, FeishuProjectionTask


def test_projection_payload_hash_is_stable_for_same_payload_content():
    assert projection_payload_hash({"sku_id": 1, "name": "SKU-A"}) == projection_payload_hash({"name": "SKU-A", "sku_id": 1})


def test_projection_table_field_definitions_use_storage_keys():
    assert _spu_table_fields()[0] == {"name": "SPU", "type": "text"}
    assert _sku_table_fields()[0] == {"name": "ERP SKU", "type": "text"}
    assert all(field["type"] != "formula" for field in _spu_table_fields() + _sku_table_fields())


def test_sku_projection_contract_carries_expected_and_actual_costs_and_spu_loss_rates():
    source = Path("backend/services/feishu_projection_service.py").read_text(encoding="utf-8")

    assert '"预计物流成本 RMB"' in source
    assert '"预计仓储成本 RMB"' in source
    assert '"实际物流成本 RMB"' in source
    assert '"物流货损率"' in source
    assert '"退货损失率"' in source


def test_projection_attempt_marks_task_and_appends_delivery_log():
    class FakeSession:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

    db = FakeSession()
    task = FeishuProjectionTask(
        id=7,
        entity_type="sku",
        business_key="42",
        payload_hash="payload-hash",
        payload_json={"sku_id": 42},
        attempt_count=0,
    )

    asyncio.run(FeishuProjectionService(db).record_attempt(task, "completed"))

    assert task.status == "completed"
    assert task.attempt_count == 1
    assert task.completed_at is not None
    assert len(db.added) == 1
    assert isinstance(db.added[0], FeishuProjectionLog)
    assert db.added[0].task_id == 7
    assert db.added[0].payload_hash == "payload-hash"


def test_failed_projection_attempt_schedules_automatic_retry():
    class FakeSession:
        def add(self, _row):
            pass

    task = FeishuProjectionTask(
        id=8,
        entity_type="sku",
        business_key="42",
        payload_hash="payload-hash",
        payload_json={"sku_id": 42},
        attempt_count=0,
    )

    asyncio.run(FeishuProjectionService(FakeSession()).record_attempt(task, "failed", "network"))

    assert task.status == "failed"
    assert task.next_retry_at is not None
    assert task.next_retry_at > datetime.now(timezone.utc)

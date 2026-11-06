"""入库身份门禁 (P2-1) 的守护测试。

为什么要有这些用例
------------------
``shop_account_id`` 是唯一正确的店铺锚点(改名不变、跨平台一致、采集器写不坏);
入库门禁保证「缺稳定身份戳的数据不落库」。

这些用例守三件事:

1. **门禁判定本身** —— 缺戳拒收 / 行内身份冲突拒收 / 非店铺数据放行;
2. **门禁真的挡在入库之前** —— 拒收时一行数据都不许写进 b_class;
3. **拒收后的文件落到终态且不会被反复捞起** —— 否则会形成无限重试闭环
   (仓库里已经踩过一次这个坑: 8 个文件 2 天内产生 72 次无效同步任务)。
"""

from types import SimpleNamespace

import pytest


# ── 门禁判定(纯函数) ─────────────────────────────────────────────────


def _file_record(**overrides):
    base = {
        "id": 1,
        "file_path": "data/raw/analytics.xlsx",
        "file_name": "analytics.xlsx",
        "status": "pending",
        "error_message": None,
        "data_domain": "analytics",
        "platform_code": "shopee",
        "shop_id": "1540271744",
        "shop_account_id": None,
        "platform_shop_id": "1540271744",
        "store_name": "DAJU Mall",
        "granularity": "monthly",
        "sub_domain": None,
        "last_processed_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_gate_rejects_shop_file_without_shop_account_id():
    """店铺数据缺稳定身份戳 ⇒ 拒收(这正是 2026-06-09 那批 2195 行的成因)。"""
    from backend.services.shop_identity_gate_service import (
        SHOP_IDENTITY_GATE_SKIP_REASON_MISSING,
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(),
        domain="analytics",
        rows=[{"订单数": 1}],
    )

    assert decision.allowed is False
    assert decision.skip_reason == SHOP_IDENTITY_GATE_SKIP_REASON_MISSING
    assert "shop_account_id" in decision.message


def test_gate_rejects_shop_file_when_only_other_identity_signals_exist():
    """只有店名/平台编号、没有账号 ID —— 仍然是「知道是哪家店但认不出稳定身份」。"""
    from backend.services.shop_identity_gate_service import (
        SHOP_IDENTITY_GATE_SKIP_REASON_MISSING,
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(data_domain="services", shop_id=None),
        domain="services",
        rows=[{"x": 1}],
    )

    assert decision.allowed is False
    assert decision.skip_reason == SHOP_IDENTITY_GATE_SKIP_REASON_MISSING


def test_gate_allows_file_that_carries_shop_account_id():
    from backend.services.shop_identity_gate_service import (
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(shop_account_id="shopee_sg_daju"),
        domain="analytics",
        rows=[{"订单数": 1}],
    )

    assert decision.allowed is True
    assert decision.skip_reason is None


def test_gate_allows_non_shop_scoped_file():
    """既不在门禁域、又没有任何店铺身份信号的文件 ⇒ 不是店铺数据，放行。"""
    from backend.services.shop_identity_gate_service import (
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(
            data_domain="services",
            shop_id=None,
            platform_shop_id=None,
            store_name=None,
        ),
        domain="services",
        rows=[{"x": 1}],
    )

    assert decision.allowed is True


def test_gate_treats_none_placeholder_as_no_identity_signal():
    """'none' 是采集器写的占位符, 不能当成「知道是哪家店」。"""
    from backend.services.shop_identity_gate_service import (
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(
            data_domain="services",
            shop_id="none",
            platform_shop_id=None,
            store_name=None,
        ),
        domain="services",
        rows=[{"x": 1}],
    )

    assert decision.allowed is True


def test_gate_rejects_rows_carrying_a_different_shop_account_id():
    """行内自带身份戳且与文件级不一致 ⇒ 同一个文件混了两个账号, 拒收。"""
    from backend.services.shop_identity_gate_service import (
        SHOP_IDENTITY_GATE_SKIP_REASON_CONFLICT,
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(shop_account_id="shopee_sg_daju"),
        domain="analytics",
        rows=[
            {"shop_account_id": "shopee_sg_daju"},
            {"shop_account_id": "shopee_my_other"},
        ],
    )

    assert decision.allowed is False
    assert decision.skip_reason == SHOP_IDENTITY_GATE_SKIP_REASON_CONFLICT
    assert decision.conflicting_shop_account_id == "shopee_my_other"


def test_gate_allows_rows_carrying_the_same_shop_account_id():
    from backend.services.shop_identity_gate_service import (
        evaluate_shop_identity_gate,
    )

    decision = evaluate_shop_identity_gate(
        file_record=_file_record(shop_account_id="shopee_sg_daju"),
        domain="analytics",
        rows=[{"shop_account_id": "shopee_sg_daju"}],
    )

    assert decision.allowed is True


# ── 门禁真的挡在入库之前 ──────────────────────────────────────────────


def _build_ingest_service(monkeypatch, tmp_path, file_record, captured):
    """搭一个最小可用的 ingest_data 测试环境(与既有契约测试同构)。"""
    import pandas as pd

    from backend.services.data_ingestion_service import DataIngestionService

    class _FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _FakeDb:
        def __init__(self, record):
            self.file_record = record

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

        def batch_calculate_data_hash(
            self, rows, deduplication_fields=None, header_bindings=None, **_kwargs
        ):
            return [f"hash-{index}" for index, _ in enumerate(rows)]

    class _FakeRawImporter:
        async def async_batch_insert_raw_data(self, **kwargs):
            captured.update(kwargs)
            return {"inserted": 1, "updated": 0, "skipped": 0}

    class _FakeEventListener:
        """挡住 DATA_INGESTED 事件 —— 它会去连 Redis/Celery，单个用例能卡 2 分钟。"""

        async def handle_data_ingested_async(self, _event):
            return None

    monkeypatch.setattr(
        "backend.services.event_listeners.event_listener",
        _FakeEventListener(),
    )

    file_path = tmp_path / "analytics.xlsx"
    file_path.write_bytes(b"test")
    file_record.file_path = str(file_path)

    service = DataIngestionService(_FakeDb(file_record))

    monkeypatch.setattr(
        "backend.services.data_ingestion_service.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(
        "backend.services.data_ingestion_service.ExcelParser.read_excel",
        lambda *_args, **_kwargs: pd.DataFrame([{"日期": "2026-03-01", "订单数": 10}]),
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
    return service


@pytest.mark.asyncio
async def test_ingest_data_refuses_file_without_shop_account_id(monkeypatch, tmp_path):
    """缺稳定身份戳 ⇒ 拒收, 而且**一行都不许写进 b_class**。"""
    from backend.services.shop_identity_gate_service import (
        SHOP_IDENTITY_GATE_SKIP_REASON_MISSING,
    )

    captured = {}
    file_record = _file_record()
    service = _build_ingest_service(monkeypatch, tmp_path, file_record, captured)

    result = await service.ingest_data(
        file_id=1,
        platform="shopee",
        domain="analytics",
        mappings=None,
        header_columns=["日期", "订单数"],
        header_row=0,
        template_id=328,
    )

    assert result["success"] is False
    assert result["identity_blocked"] is True
    assert result["skip_reason"] == SHOP_IDENTITY_GATE_SKIP_REASON_MISSING
    assert captured == {}, "门禁拒收时不允许写入任何数据"


@pytest.mark.asyncio
async def test_ingest_data_stamps_rows_with_shop_account_id(monkeypatch, tmp_path):
    """有稳定身份戳 ⇒ 正常入库, 且每一行都盖上戳。"""
    captured = {}
    file_record = _file_record(shop_account_id="shopee_sg_daju")
    service = _build_ingest_service(monkeypatch, tmp_path, file_record, captured)

    result = await service.ingest_data(
        file_id=1,
        platform="shopee",
        domain="analytics",
        mappings=None,
        header_columns=["日期", "订单数"],
        header_row=0,
        template_id=328,
        extract_images=False,
    )

    assert result["success"] is True
    assert result.get("identity_blocked") is None
    assert captured["rows"][0]["shop_account_id"] == "shopee_sg_daju"


# ── 终态归属: 落 needs_shop, 且不会被自动入库反复捞起 ──────────────────


def test_identity_blocked_state_lands_on_needs_shop():
    from backend.services.data_sync_file_state_service import (
        apply_identity_blocked_state,
        resolve_identity_blocked_catalog_status,
    )

    catalog_file = SimpleNamespace(
        status="pending",
        error_message=None,
        file_metadata={"auto_ingest": {"attempts": 1}},
        auto_ingest_skip_reason=None,
    )

    target = apply_identity_blocked_state(
        catalog_file,
        reason="缺稳定身份编号(shop_account_id)",
        skip_reason="missing_shop_account_id",
    )

    assert target == resolve_identity_blocked_catalog_status()
    assert target == "needs_shop"
    assert catalog_file.status == "needs_shop"
    assert catalog_file.error_message == "缺稳定身份编号(shop_account_id)"
    assert catalog_file.auto_ingest_skip_reason == "missing_shop_account_id"
    assert catalog_file.file_metadata["auto_ingest"]["current_task_id"] is None


def test_needs_shop_is_a_legal_catalog_status():
    """needs_shop 必须在 SSOT 的合法状态集合里(数据库有 CHECK 约束)。"""
    from modules.core.catalog_status import (
        CATALOG_FILE_STATUS_NEEDS_SHOP,
        CATALOG_FILE_STATUS_SET,
        is_valid_catalog_file_status,
    )

    assert CATALOG_FILE_STATUS_NEEDS_SHOP in CATALOG_FILE_STATUS_SET
    assert is_valid_catalog_file_status("needs_shop") is True


def test_needs_shop_is_not_picked_up_by_auto_ingest():
    """needs_shop 不能在「待自动入库」的活跃集合里, 否则会无限重试。"""
    from modules.core.catalog_status import (
        CATALOG_FILE_STATUS_ACTIVE,
        CATALOG_FILE_STATUS_NEEDS_SHOP,
        CATALOG_FILE_STATUS_PENDING,
    )

    assert CATALOG_FILE_STATUS_NEEDS_SHOP not in CATALOG_FILE_STATUS_ACTIVE
    # 自动入库只捞 pending; needs_shop 停在原地等人处理
    assert CATALOG_FILE_STATUS_PENDING in CATALOG_FILE_STATUS_ACTIVE


def test_data_sync_service_routes_identity_blocked_to_needs_shop():
    """门禁拒收必须落到 needs_shop 终态, 而不是 failed(否则会被当成可重试故障)。"""
    from pathlib import Path

    sync_text = Path("backend/services/data_sync_service.py").read_text(encoding="utf-8")

    assert "elif result.get(\"identity_blocked\"):" in sync_text
    assert "apply_identity_blocked_state(" in sync_text


def test_catalog_scanner_only_releases_needs_shop_when_account_id_present():
    """身份没补齐就不能放回 pending —— 否则会在扫描↔入库之间空转。"""
    from pathlib import Path

    scanner_text = Path("modules/services/catalog_scanner.py").read_text(
        encoding="utf-8"
    )

    assert "if existing.shop_account_id:" in scanner_text

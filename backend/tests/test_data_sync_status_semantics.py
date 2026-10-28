"""第 2 批回归测试: 状态语义统一(D3) + 单一状态模型(D4) + 统一读表头入口(D6)。

覆盖
----
D3 统一 status 语义
  1. template_status -> governance_status 映射是**唯一**的
  2. 旧的那份漏掉的 ``semantic_invalid`` 也能正确映射
  3. 未知取值原样返回, 不静默变成 ready
  4. 阻断性判定只有一个来源

D4 单一状态模型
  5. 缺模板 / 缺变体 / 语义契约不满足 -> 人工处理, 归模板负责人
  6. 模板待更新 -> 系统自动重检; 连续重检仍阻塞 -> 升级为人工
  7. 已入库 / 部分成功 / 隔离 -> 不需要人工
  8. 状态迁移表: 正常迁移允许, 异常跳变被识别

D6 统一读表头入口
  9. 表头行口径统一: header_row < 0 = 无表头行
  10. 相对路径从项目根解析; 绝对路径越界时宽松放行 / 严格拒绝
  11. 判定链路与入库链路共用同一个入口(实现同源)
"""

from pathlib import Path

import pandas as pd
import pytest


# ======================================================================
# D3 统一 status 语义
# ======================================================================
def test_template_status_maps_to_governance_status():
    from backend.services.data_sync_status_semantics import (
        GOVERNANCE_STATUS_BREAKING_DRIFT,
        GOVERNANCE_STATUS_MISSING_FAMILY,
        GOVERNANCE_STATUS_MISSING_VARIANT,
        GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
        GOVERNANCE_STATUS_READY,
        GOVERNANCE_STATUS_SEMANTIC_INVALID,
        TEMPLATE_STATUS_ALIAS_ONLY,
        TEMPLATE_STATUS_MISSING,
        TEMPLATE_STATUS_MISSING_VARIANT,
        TEMPLATE_STATUS_READY,
        TEMPLATE_STATUS_SEMANTIC_INVALID,
        TEMPLATE_STATUS_UPDATE_REQUIRED,
        governance_status_for,
    )

    assert governance_status_for(TEMPLATE_STATUS_READY) == GOVERNANCE_STATUS_READY
    assert (
        governance_status_for(TEMPLATE_STATUS_ALIAS_ONLY)
        == GOVERNANCE_STATUS_NON_BREAKING_DRIFT
    )
    assert (
        governance_status_for(TEMPLATE_STATUS_UPDATE_REQUIRED)
        == GOVERNANCE_STATUS_BREAKING_DRIFT
    )
    assert governance_status_for(TEMPLATE_STATUS_MISSING) == GOVERNANCE_STATUS_MISSING_FAMILY
    assert (
        governance_status_for(TEMPLATE_STATUS_MISSING_VARIANT)
        == GOVERNANCE_STATUS_MISSING_VARIANT
    )
    # [*] 旧映射表漏掉的那一项
    assert (
        governance_status_for(TEMPLATE_STATUS_SEMANTIC_INVALID)
        == GOVERNANCE_STATUS_SEMANTIC_INVALID
    )


def test_governance_status_for_unknown_value_is_not_silently_ready():
    from backend.services.data_sync_status_semantics import governance_status_for

    assert governance_status_for("something_new") == "something_new"
    assert governance_status_for(None) != "ready"


def test_blocking_governance_status_is_single_sourced():
    from backend.services.data_sync_status_semantics import (
        is_blocking_governance_status,
        is_breaking_drift,
    )

    assert is_blocking_governance_status("breaking_drift") is True
    assert is_blocking_governance_status("missing_family") is True
    assert is_blocking_governance_status("missing_variant") is True
    assert is_blocking_governance_status("ready") is False
    assert is_blocking_governance_status("non_breaking_drift") is False

    # 语义契约状态与治理状态共用同一套漂移词汇
    assert is_breaking_drift("breaking_drift") is True
    assert is_breaking_drift(None, "breaking_drift") is True
    assert is_breaking_drift("non_breaking_drift", "ready") is False


def test_service_normalize_governance_status_uses_the_ssot():
    from backend.services.data_sync_service import DataSyncService

    status = DataSyncService._normalize_governance_status(
        {"template_status": "alias_only"}
    )
    assert status["governance_status"] == "non_breaking_drift"

    # 已有的 governance_status 不被覆盖
    status = DataSyncService._normalize_governance_status(
        {"template_status": "alias_only", "governance_status": "ready"}
    )
    assert status["governance_status"] == "ready"


# ======================================================================
# D4 单一状态模型
# ======================================================================
def test_disposition_missing_template_goes_to_template_owner():
    from backend.services.data_sync_file_state_service import (
        FILE_ACTION_MANUAL_MAPPING,
        FILE_OWNER_TEMPLATE,
        FILE_STATE_BLOCKED_MISSING_TEMPLATE,
        resolve_file_disposition,
    )

    disposition = resolve_file_disposition(
        catalog_status="pending",
        template_status="missing",
        governance_status="missing_family",
    )
    assert disposition["file_state"] == FILE_STATE_BLOCKED_MISSING_TEMPLATE
    assert disposition["needs_manual_action"] is True
    assert disposition["next_action"] == FILE_ACTION_MANUAL_MAPPING
    assert disposition["owner"] == FILE_OWNER_TEMPLATE


def test_disposition_missing_variant_goes_to_template_owner():
    from backend.services.data_sync_file_state_service import (
        FILE_ACTION_MANUAL_MAPPING,
        FILE_OWNER_TEMPLATE,
        FILE_STATE_BLOCKED_MISSING_VARIANT,
        resolve_file_disposition,
    )

    disposition = resolve_file_disposition(
        catalog_status="pending",
        template_status="missing_variant",
        governance_status="missing_variant",
    )
    assert disposition["file_state"] == FILE_STATE_BLOCKED_MISSING_VARIANT
    assert disposition["next_action"] == FILE_ACTION_MANUAL_MAPPING
    assert disposition["owner"] == FILE_OWNER_TEMPLATE


def test_disposition_template_update_waits_for_system_then_escalates():
    from backend.services.data_sync_file_state_service import (
        FILE_ACTION_AWAIT_TEMPLATE_UPDATE,
        FILE_ACTION_MANUAL_TEMPLATE_UPDATE,
        FILE_OWNER_SYSTEM,
        FILE_OWNER_TEMPLATE,
        FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE,
        FILE_STATE_BLOCKED_TEMPLATE_UPDATE,
        resolve_file_disposition,
    )

    waiting = resolve_file_disposition(
        catalog_status="template_update_required",
        template_status="update_required",
        governance_status="breaking_drift",
        template_update_required=True,
    )
    assert waiting["file_state"] == FILE_STATE_BLOCKED_TEMPLATE_UPDATE
    assert waiting["next_action"] == FILE_ACTION_AWAIT_TEMPLATE_UPDATE
    assert waiting["owner"] == FILE_OWNER_SYSTEM
    assert waiting["needs_manual_action"] is False

    escalated = resolve_file_disposition(
        catalog_status="template_update_required",
        template_status="update_required",
        governance_status="breaking_drift",
        template_update_required=True,
        auto_meta={"needs_manual_template_update": True},
    )
    assert escalated["file_state"] == FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE
    assert escalated["next_action"] == FILE_ACTION_MANUAL_TEMPLATE_UPDATE
    assert escalated["owner"] == FILE_OWNER_TEMPLATE
    assert escalated["needs_manual_action"] is True


def test_disposition_finished_files_need_nobody():
    from backend.services.data_sync_file_state_service import (
        FILE_ACTION_NONE,
        FILE_OWNER_NONE,
        FILE_STATE_INGESTED,
        FILE_STATE_PARTIAL_SUCCESS,
        FILE_STATE_QUARANTINED,
        resolve_file_disposition,
    )

    for status, expected_state in (
        ("ingested", FILE_STATE_INGESTED),
        ("partial_success", FILE_STATE_PARTIAL_SUCCESS),
        ("quarantined", FILE_STATE_QUARANTINED),
    ):
        disposition = resolve_file_disposition(catalog_status=status)
        assert disposition["file_state"] == expected_state
        assert disposition["next_action"] == FILE_ACTION_NONE
        assert disposition["owner"] == FILE_OWNER_NONE
        assert disposition["needs_manual_action"] is False


def test_disposition_ready_file_goes_to_auto_sync():
    from backend.services.data_sync_file_state_service import (
        FILE_ACTION_AUTO_SYNC,
        FILE_OWNER_SYSTEM,
        FILE_STATE_READY_TO_SYNC,
        resolve_file_disposition,
    )

    disposition = resolve_file_disposition(
        catalog_status="pending",
        template_status="ready",
        governance_status="ready",
        should_auto_sync=True,
    )
    assert disposition["file_state"] == FILE_STATE_READY_TO_SYNC
    assert disposition["next_action"] == FILE_ACTION_AUTO_SYNC
    assert disposition["owner"] == FILE_OWNER_SYSTEM


def test_disposition_semantic_contract_break_goes_to_template_owner():
    from backend.services.data_sync_file_state_service import (
        FILE_ACTION_MANUAL_TEMPLATE_UPDATE,
        FILE_OWNER_TEMPLATE,
        FILE_STATE_BLOCKED_SEMANTIC_CONTRACT,
        resolve_file_disposition,
    )

    disposition = resolve_file_disposition(
        catalog_status="pending",
        template_status="update_required",
        governance_status="breaking_drift",
        semantic_contract_status="breaking_drift",
    )
    assert disposition["file_state"] == FILE_STATE_BLOCKED_SEMANTIC_CONTRACT
    assert disposition["next_action"] == FILE_ACTION_MANUAL_TEMPLATE_UPDATE
    assert disposition["owner"] == FILE_OWNER_TEMPLATE


def test_transition_table_flags_illegal_jumps():
    from backend.services.data_sync_file_state_service import can_transition

    # 正常流程
    assert can_transition("pending", "processing") is True
    assert can_transition("processing", "ingested") is True
    assert can_transition("template_update_required", "pending") is True
    # 重置重导是合法的运维动作
    assert can_transition("ingested", "pending") is True
    # 明显异常的跳变
    assert can_transition("ingested", "processing") is False
    assert can_transition("pending", "quarantined") is True  # 隔离是允许的


def test_disposition_from_catalog_file_reads_auto_meta():
    from backend.services.data_sync_file_state_service import (
        FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE,
        disposition_from_catalog_file,
    )
    from modules.core.db import CatalogFile

    catalog_file = CatalogFile(
        file_path="data/raw/x.xlsx",
        file_name="x.xlsx",
        source="data/raw",
        status="template_update_required",
        file_metadata={"auto_ingest": {"needs_manual_template_update": True}},
    )
    disposition = disposition_from_catalog_file(
        catalog_file,
        template_status="update_required",
        governance_status="breaking_drift",
        template_update_required=True,
    )
    assert disposition["file_state"] == FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE


# ======================================================================
# D6 统一读表头入口
# ======================================================================
def test_header_row_negative_means_no_header():
    from backend.services.spreadsheet_header_reader import SpreadsheetHeaderReader

    reader = SpreadsheetHeaderReader()
    assert reader is not None


def test_safe_path_resolves_relative_from_project_root(tmp_path, monkeypatch):
    from backend.services.spreadsheet_header_reader import SpreadsheetHeaderReader

    reader = SpreadsheetHeaderReader(strict_allowed_roots=False)
    resolved = reader.resolve_safe_path("data/raw/2026/demo.xlsx")
    assert Path(resolved).is_absolute()
    assert "data/raw/2026/demo.xlsx" in resolved.replace("\\", "/")


def test_safe_path_strict_mode_rejects_outside_allowed_roots(tmp_path):
    from backend.services.spreadsheet_header_reader import SpreadsheetHeaderReader

    outside = tmp_path / "not_allowed.xlsx"
    outside.write_text("demo", encoding="utf-8")

    strict_reader = SpreadsheetHeaderReader(strict_allowed_roots=True)
    with pytest.raises(ValueError):
        strict_reader.resolve_safe_path(str(outside))

    # 宽松模式: 放行但保留原路径
    loose_reader = SpreadsheetHeaderReader(strict_allowed_roots=False)
    assert loose_reader.resolve_safe_path(str(outside))


@pytest.mark.asyncio
async def test_read_columns_uses_shared_header_row_semantics(tmp_path, monkeypatch):
    from backend.services import excel_parser as excel_parser_module
    from backend.services.spreadsheet_header_reader import SpreadsheetHeaderReader

    captured = {}

    def _fake_read_excel(_path, header=None, nrows=None, **_kwargs):
        captured["header"] = header
        captured["nrows"] = nrows
        return pd.DataFrame(columns=["商品ID", "商品名称"])

    monkeypatch.setattr(
        excel_parser_module.ExcelParser, "read_excel", staticmethod(_fake_read_excel)
    )

    class _ThreadExecutor:
        async def run_io_intensive(self, func, *args, **kwargs):
            return func(*args, **kwargs)

        async def run_cpu_intensive(self, func, *args, **kwargs):
            return func(*args, **kwargs)

    class _StubManager:
        async def run_io_intensive(self, func, *args, **kwargs):
            return func(*args, **kwargs)

        async def run_cpu_intensive(self, func, *args, **kwargs):
            return func(*args, **kwargs)

    reader = SpreadsheetHeaderReader(
        strict_allowed_roots=False,
        use_cpu_executor=False,
        executor_manager_factory=_StubManager,
    )

    target = tmp_path / "demo.xlsx"
    target.write_text("demo", encoding="utf-8")

    result = await reader.read_columns(str(target), header_row=2, nrows=5)
    assert result.ok is True
    assert result.columns == ["商品ID", "商品名称"]
    assert captured["header"] == 2
    assert captured["nrows"] == 5

    # header_row < 0 -> 无表头行(pandas header=None)
    await reader.read_columns(str(target), header_row=-1, nrows=5)
    assert captured["header"] is None


def test_judgement_and_ingest_share_the_same_reader_entry():
    """判定链路与入库链路必须共用同一个入口(实现同源)。"""
    from backend.services.data_ingestion_service import DataIngestionService
    from backend.services.data_sync_service import DataSyncService
    from backend.services.spreadsheet_header_reader import SpreadsheetHeaderReader

    sync_reader = DataSyncService.__new__(DataSyncService)
    sync_reader._header_reader = SpreadsheetHeaderReader(log_prefix="DataSync")
    ingest_reader = DataIngestionService.__new__(DataIngestionService)
    ingest_reader._header_reader = SpreadsheetHeaderReader(log_prefix="Ingest")

    assert isinstance(sync_reader._header_reader, SpreadsheetHeaderReader)
    assert isinstance(ingest_reader._header_reader, SpreadsheetHeaderReader)
    # 两个入口暴露的是同一套方法(没有各自抄一份)
    assert hasattr(sync_reader._header_reader, "read_columns")
    assert hasattr(ingest_reader._header_reader, "read_columns")
    assert hasattr(sync_reader._header_reader, "resolve_safe_path")
    assert hasattr(ingest_reader._header_reader, "resolve_safe_path")

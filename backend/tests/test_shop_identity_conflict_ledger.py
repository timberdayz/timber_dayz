"""同步侧「矛盾行台账」的守护测试（批次 4.3）。

背景
----
批次 3.7 的「双基准守卫」把**本地/云端登记信息不一致**的行降级成可观测事件,
事件落在 ``ops.pipeline_run_log`` 的 ``context->'events'``(整批 jsonb 样本)。

批次 4.3 补上**行级台账** ``ops.shop_identity_conflict_rows``:
被跳过 / 被降级的行**逐行**登记(带原因码、标注「已知历史遗留 / 待人工处理」),
并给出手工重发入口。

本测试盯住七件事
----------------
1. 矛盾行被记进台账, 且**带正确的标注与原因码**;
2. 台账写入失败时**同步照跑**(不抛、不改写入结果);
3. 台账**去重**: 同一矛盾行再来一次 ⇒ 仍是同一行, 累计次数 +1, 不是两行;
4. 批次 3.7 的事件台账**不再重复写**;
5. **推进算法没变**: 矛盾行之后的自洽行仍然照常落库(不许卡死);
6. 重发脚本 ``--dry-run`` 不改动任何东西、``--execute`` 只处理「待人工处理」的行、
   默认不动「已知历史遗留」;
7. 迁移链的 revision 指向与 ORM 模型与迁移一致。

⚠️ 断言消息一律提到**变量**里再 ``assert`` —— 本地 Python 3.13 与 CI 的
3.11 对 ``assert 条件, (消息)`` 的括号换行判定不同, 提成变量两端才都绿。
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest

from backend.services import cloud_sync_identity_guard_service as guard_service
from backend.services import shop_identity_conflict_ledger_service as ledger_service
from backend.services.cloud_b_class_sync_service import (
    SQLAlchemyCloudWriter,
    build_sync_payload,
    split_rows_by_dual_baseline,
)
from backend.services.cloud_sync_identity_guard_service import (
    GUARD_PIPELINE_NAME,
    REASON_CLOUD_AMBIGUOUS,
    REASON_CLOUD_DIFFERENT_ACCOUNT,
    REASON_CLOUD_UNRESOLVED,
    CloudSyncIdentityGuardEventRecorder,
)
from backend.services.shop_identity_conflict_ledger_service import (
    CONFLICT_NOTIFY_ENABLED_ENV,
    REASON_LOCAL_REGISTRY_AMBIGUOUS,
    REASON_LOCAL_TOKEN_MISMATCH,
    STATUS_KNOWN_LEGACY,
    STATUS_PENDING_MANUAL,
    ConflictRowRecord,
    ShopIdentityConflictLedgerRecorder,
    build_dedup_key,
    build_row_locator,
    classify_conflict_status,
    conflict_notify_enabled,
    pick_identity_value,
    select_conflict_rows,
)
from backend.services.shop_identity_reconciliation_service import build_identity_index
from scripts import replay_shop_identity_conflict_rows as replay_script


# ---------------------------------------------------------------------------
# 台账样例: 本地与云端**故意不一致**(复刻 2026-11 事故的错位形态)
# ---------------------------------------------------------------------------

LOCAL_ACCOUNTS = [
    {
        "id": 1,
        "shop_account_id": "shopee_sg_hx_home_local",
        "platform": "shopee",
        "platform_shop_id": "1391124228",
        "store_name": "hx_home.sg",
        "shop_region": "SG",
        "enabled": True,
        "business_role": "operating_store",
    },
    {
        "id": 2,
        "shop_account_id": "shopee_ph_xhkj11_local",
        "platform": "shopee",
        "platform_shop_id": "1419169771",
        "store_name": "xhkj11.ph",
        "shop_region": "PH",
        "enabled": True,
        "business_role": "operating_store",
    },
]

CLOUD_ACCOUNTS = [
    {
        "id": 1,
        "shop_account_id": "shopee_sg_hx_home_local",
        "platform": "shopee",
        "platform_shop_id": "1419169771",  # ← 错位
        "store_name": "hx_home.sg",
        "shop_region": "SG",
        "enabled": True,
        "business_role": "operating_store",
    },
    {
        "id": 2,
        "shop_account_id": "shopee_ph_xhkj11_local",
        "platform": "shopee",
        "platform_shop_id": "1391124228",  # ← 错位
        "store_name": "xhkj11.ph",
        "shop_region": "PH",
        "enabled": True,
        "business_role": "operating_store",
    },
]

LOCAL_INDEX = build_identity_index(LOCAL_ACCOUNTS, [])
CLOUD_INDEX = build_identity_index(CLOUD_ACCOUNTS, [])

#: 对齐生效日 —— 「历史遗留 / 待人工处理」的分界。
ALIGNMENT_DATE = "2026-11-01"


def _cloud_registry():
    from backend.services.cloud_sync_identity_guard_service import (
        LOAD_STATUS_LOADED,
        CloudIdentityRegistry,
    )

    return CloudIdentityRegistry(
        status=LOAD_STATUS_LOADED,
        target="postgresql://127.0.0.1:15433/xihong_erp",
        index=CLOUD_INDEX,
        account_count=2,
        alias_count=0,
    )


def _row(raw_data: dict[str, Any], **extra) -> dict[str, Any]:
    row = {
        "id": 1,
        "ingest_timestamp": "2026-06-22T00:00:00+00:00",
        "platform_code": "shopee",
        "shop_id": "1391124228",
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "data_hash": "hash-1",
        "raw_data": raw_data,
    }
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# ① 台账口径(纯函数)
# ---------------------------------------------------------------------------


def test_reason_codes_have_a_single_definition():
    """★ 批次 3.7 的原因码与台账的原因码**必须是同一份**(不写第二套)。"""
    message = "批次 3.7 的原因码必须直接来自台账模块"
    assert REASON_CLOUD_UNRESOLVED == ledger_service.REASON_CLOUD_UNRESOLVED, message
    assert REASON_CLOUD_AMBIGUOUS == ledger_service.REASON_CLOUD_AMBIGUOUS, message
    assert (
        REASON_CLOUD_DIFFERENT_ACCOUNT == ledger_service.REASON_CLOUD_DIFFERENT_ACCOUNT
    ), message
    assert set(ledger_service.ALL_REASON_CODES) >= {
        REASON_LOCAL_REGISTRY_AMBIGUOUS,
        REASON_LOCAL_TOKEN_MISMATCH,
        REASON_CLOUD_UNRESOLVED,
        REASON_CLOUD_AMBIGUOUS,
        REASON_CLOUD_DIFFERENT_ACCOUNT,
    }, message


def test_dedup_key_is_stable_for_the_same_four_fields():
    """★ 去重键 = 「(源表, 业务日期, 行内定位, 原因码)」, 且稳定可复算。"""
    first = build_dedup_key(
        source_table_name="fact_shopee_products_daily",
        business_date="2026-06-22",
        row_locator="12|hash-1",
        reason_code=REASON_LOCAL_REGISTRY_AMBIGUOUS,
    )
    second = build_dedup_key(
        source_table_name="fact_shopee_products_daily",
        business_date="2026-06-22",
        row_locator="12|hash-1",
        reason_code=REASON_LOCAL_REGISTRY_AMBIGUOUS,
    )
    other_reason = build_dedup_key(
        source_table_name="fact_shopee_products_daily",
        business_date="2026-06-22",
        row_locator="12|hash-1",
        reason_code=REASON_CLOUD_UNRESOLVED,
    )

    message = "同一组四要素必须算出同一个去重键"
    assert first == second, message
    assert first != other_reason, "原因码不同 ⇒ 必须算成不同的行"


def test_row_locator_is_built_from_the_source_row_identity():
    """行内定位 = 源行主键 + 冲突键摘要(跨轮次稳定)。"""
    locator = build_row_locator(source_row_id=12, data_hash="hash-1")
    message = "行内定位必须由源行主键与摘要拼成"
    assert locator == "12|hash-1", message


def test_conflict_status_is_known_legacy_before_the_alignment_date():
    """★ 业务日期早于对齐生效日 ⇒ 「已知历史遗留」(历史不修)。"""
    from datetime import date

    status = classify_conflict_status(
        business_date="2026-06-22",
        alignment_effective_date=date(2026, 11, 1),
    )
    message = "对齐生效日之前的行必须归「已知历史遗留」"
    assert status == STATUS_KNOWN_LEGACY, message


def test_conflict_status_is_pending_manual_after_the_alignment_date():
    """★ 业务日期不早于对齐生效日 ⇒ 「待人工处理」。"""
    from datetime import date

    status = classify_conflict_status(
        business_date="2026-11-05",
        alignment_effective_date=date(2026, 11, 1),
    )
    message = "对齐生效日之后的行必须归「待人工处理」"
    assert status == STATUS_PENDING_MANUAL, message


def test_conflict_status_is_known_legacy_when_alignment_date_is_missing():
    """★ 未配置对齐生效日 ⇒ 一律「已知历史遗留」(与批次 3.2 同口径)。"""
    status = classify_conflict_status(
        business_date="2026-11-05",
        alignment_effective_date=None,
    )
    message = "没有基准就分不出历史与新增 ⇒ 一律按历史遗留"
    assert status == STATUS_KNOWN_LEGACY, message


def test_identity_value_follows_the_ssot_priority():
    """★ 「行内那列的值」按**账号章优先**取(与唯一台账声明同向)。"""
    tokens = {
        "platform_shop_id": "1391124228",
        "shop_account_id": "shopee_sg_hx_home_local",
        "shop_id": "1391124228",
    }
    message = "认人优先级只能有一处定义 ⇒ 账号章优先"
    assert pick_identity_value(tokens) == "shopee_sg_hx_home_local", message


def test_conflict_notify_is_disabled_by_default(monkeypatch):
    """★ 通知出口**默认关**(上线后行为与现在完全一致)。"""
    monkeypatch.delenv(CONFLICT_NOTIFY_ENABLED_ENV, raising=False)
    message = "通知出口默认必须是关的"
    assert conflict_notify_enabled() is False, message

    monkeypatch.setenv(CONFLICT_NOTIFY_ENABLED_ENV, "1")
    assert conflict_notify_enabled() is True, "显式打开后必须为真"

    monkeypatch.setenv(CONFLICT_NOTIFY_ENABLED_ENV, "0")
    assert conflict_notify_enabled() is False, "显式关掉后必须为假"


# ---------------------------------------------------------------------------
# ② 矛盾行被记进台账(带正确的标注与原因码)
# ---------------------------------------------------------------------------


def test_conflict_row_is_recorded_with_reason_code_and_status(monkeypatch):
    """★ 本地真矛盾的行被记进台账, 带原因码与「历史遗留 / 待人工」标注。"""
    monkeypatch.setenv("SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE", ALIGNMENT_DATE)
    engine = _FakeLedgerEngine()
    recorder = ShopIdentityConflictLedgerRecorder(engine)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=None,
        conflict_ledger_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228", "shop_id": "1419169771"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "真矛盾的行必须被记进台账"
    assert len(engine.rows) == 1, message
    row = list(engine.rows.values())[0]
    assert row["reason_code"] == REASON_LOCAL_REGISTRY_AMBIGUOUS, message
    assert row["status"] == STATUS_KNOWN_LEGACY, message
    assert row["occurrence_count"] == 1, message


def test_new_rows_after_the_alignment_date_are_pending_manual(monkeypatch):
    """★ 对齐生效日之后的矛盾行 ⇒ 「待人工处理」(可以手工重发)。"""
    monkeypatch.setenv("SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE", ALIGNMENT_DATE)
    engine = _FakeLedgerEngine()
    recorder = ShopIdentityConflictLedgerRecorder(engine)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=None,
        conflict_ledger_recorder=recorder,
    )
    rows = [
        _row(
            {"platform_shop_id": "1391124228", "shop_id": "1419169771"},
            metric_date="2026-11-05",
        )
    ]

    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "对齐生效日之后的行必须标成待人工处理"
    assert len(engine.rows) == 1, message
    row = list(engine.rows.values())[0]
    assert row["status"] == STATUS_PENDING_MANUAL, message
    assert row["business_date"] == "2026-11-05", message


def test_degraded_row_is_recorded_with_the_cloud_reason_code(monkeypatch):
    """★ 被双基准降级的行也进台账, 带**云端**那一侧的原因码。"""
    monkeypatch.setenv("SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE", ALIGNMENT_DATE)
    engine = _FakeLedgerEngine()
    recorder = ShopIdentityConflictLedgerRecorder(engine)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        conflict_ledger_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "被降级的行必须进台账并带云端原因码"
    assert len(engine.rows) == 1, message
    row = list(engine.rows.values())[0]
    assert row["reason_code"] == REASON_CLOUD_DIFFERENT_ACCOUNT, message
    assert json.loads(row["cloud_accounts"]) == ["shopee_ph_xhkj11_local"], message
    assert row["resolved_account_id"] == "shopee_sg_hx_home_local", message


# ---------------------------------------------------------------------------
# ③ 只记不阻塞
# ---------------------------------------------------------------------------


def test_ledger_write_failure_does_not_block_the_sync():
    """★ 台账写失败**绝不阻塞同步**(数据照写)。"""
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=None,
        conflict_ledger_recorder=_BrokenLedgerRecorder(),
    )
    rows = [_row({"shop_account_id": "shopee_sg_hx_home_local"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "台账写失败不该把同步搞挂"
    assert result["success"] is True, message
    assert result["written_rows"] == 1, message


def test_ledger_recorder_exception_is_swallowed():
    """★ 台账记录器**抛异常**也被吞掉(同步照跑)。"""
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=None,
        conflict_ledger_recorder=_ExplodingLedgerRecorder(),
    )
    rows = [_row({"shop_account_id": "shopee_sg_hx_home_local"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "台账记录器抛异常不该把同步搞挂"
    assert result["success"] is True, message
    assert result["written_rows"] == 1, message


def test_ledger_table_missing_does_not_block_the_sync():
    """★ 台账表不存在(迁移还没跑)⇒ 同步照跑。"""
    engine = _FakeLedgerEngine(error=RuntimeError("relation does not exist"))
    recorder = ShopIdentityConflictLedgerRecorder(engine)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=None,
        conflict_ledger_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228", "shop_id": "1419169771"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "台账表不存在不该把同步搞挂"
    assert result["success"] is True, message
    assert result["identity_conflict_rows"] == 1, message


# ---------------------------------------------------------------------------
# ④ 台账去重
# ---------------------------------------------------------------------------


def test_the_same_conflict_row_is_deduped_in_the_ledger():
    """★ 同一矛盾行再来一次 ⇒ 台账里**仍是同一行**, 累计次数 +1。"""
    engine = _FakeLedgerEngine()
    recorder = ShopIdentityConflictLedgerRecorder(engine)
    record = ConflictRowRecord(
        reason_code=REASON_LOCAL_REGISTRY_AMBIGUOUS,
        row_locator=build_row_locator(source_row_id=1, data_hash="hash-1"),
        source_row_id="1",
        platform_code="shopee",
        business_date="2026-06-22",
        identity_value="shopee_sg_hx_home_local",
        identity_tokens={"shop_account_id": "shopee_sg_hx_home_local"},
        resolved_accounts=["shopee_sg_hx_home_local", "shopee_ph_xhkj11_local"],
    )

    first = recorder.record_conflicts(
        source_table_name="fact_shopee_analytics_monthly",
        data_domain="analytics",
        records=[record],
    )
    second = recorder.record_conflicts(
        source_table_name="fact_shopee_analytics_monthly",
        data_domain="analytics",
        records=[record],
    )

    message = "同一矛盾行必须被去重(不能插两行)"
    assert len(engine.rows) == 1, message
    assert first["new_rows"] == 1, "第一次见到 ⇒ 算新行"
    assert second["new_rows"] == 0, "第二次见到 ⇒ 不算新行"
    assert second["seen_rows"] == 1, "第二次见到 ⇒ 算已见过"
    row = list(engine.rows.values())[0]
    assert row["occurrence_count"] == 2, "累计次数必须 +1"


def test_the_upsert_uses_the_database_unique_constraint():
    """★ 幂等由**数据库唯一约束**兜底(SQL 里必须能看出来)。"""
    source = Path(ledger_service.__file__).read_text(encoding="utf-8")

    message = "去重必须落在 ON CONFLICT 上, 不能靠应用层先查后写"
    assert "ON CONFLICT (dedup_key) DO UPDATE" in source, message
    counter_bump = (
        "occurrence_count = ops.shop_identity_conflict_rows.occurrence_count + 1"
    )
    assert counter_bump in source, message


def test_the_upsert_binds_every_parameter_it_references():
    """★ SQL 里引用的绑定参数**一个都不能少**(少一个真库直接抛异常)。

    ⚠️ 这条是**真库验出来的**: 曾经少绑了 ``resolution_status``,
    替身不校验时用例照样绿, 真库上却整条 upsert 失败。
    """
    engine = _FakeLedgerEngine()
    recorder = ShopIdentityConflictLedgerRecorder(engine)
    record = ConflictRowRecord(
        reason_code=REASON_LOCAL_REGISTRY_AMBIGUOUS,
        row_locator=build_row_locator(source_row_id=1, data_hash="hash-1"),
        source_row_id="1",
        platform_code="shopee",
        business_date="2026-06-22",
    )

    summary = recorder.record_conflicts(
        source_table_name="fact_shopee_analytics_monthly",
        data_domain="analytics",
        records=[record],
    )

    message = "绑定参数没给全 ⇒ upsert 会在真库上失败"
    assert summary["status"] == "recorded", message
    assert len(engine.rows) == 1, message


# ---------------------------------------------------------------------------
# ⑤ 批次 3.7 的事件不再重复写
# ---------------------------------------------------------------------------


def test_guard_event_is_not_written_twice_for_the_same_batch():
    """★ 同一批被降级两次 ⇒ ``ops.pipeline_run_log`` **只记一条**事件。"""
    recorder = _FakeGuardRecorder()
    ledger = _FakeLedgerRecorder(new_rows_sequence=[1, 0])
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        guard_event_recorder=recorder,
        conflict_ledger_recorder=ledger,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")
    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "同一批的降级事件不该被重复记一条"
    assert len(recorder.mismatch_calls) == 1, message


def test_guard_event_is_still_written_when_the_ledger_is_not_configured():
    """★ 没配台账 ⇒ 事件照记(宁可多记一条, 也不丢可观测性)。"""
    recorder = _FakeGuardRecorder()
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        guard_event_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "没配台账时事件必须照记"
    assert len(recorder.mismatch_calls) == 1, message


def test_guard_event_is_still_written_when_the_ledger_write_fails():
    """★ 台账写失败 ⇒ 事件照记(不因为台账坏了就丢可观测性)。"""
    recorder = _FakeGuardRecorder()
    writer = SQLAlchemyCloudWriter(
        engine=_FakeWriterEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        guard_event_recorder=recorder,
        conflict_ledger_recorder=_BrokenLedgerRecorder(),
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "台账坏了不该让事件也一起消失"
    assert len(recorder.mismatch_calls) == 1, message


# ---------------------------------------------------------------------------
# ⑥ 推进算法没变(不许卡死)
# ---------------------------------------------------------------------------


def test_rows_after_a_conflicting_row_are_still_written():
    """★ 矛盾行**之后**的自洽行仍然照常落库(不许卡死)。"""
    engine = _FakeWriterEngine()
    writer = SQLAlchemyCloudWriter(
        engine=engine,
        identity_index=LOCAL_INDEX,
        cloud_registry=None,
    )
    rows = [
        _row(
            {"platform_shop_id": "1391124228", "shop_id": "1419169771"},
            id=1,
            data_hash="hash-conflict",
        ),
        _row({"shop_account_id": "shopee_sg_hx_home_local"}, id=2, data_hash="hash-ok"),
    ]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "矛盾行之后的自洽行必须照常落库"
    assert result["written_rows"] == 1, message
    assert result["identity_conflict_rows"] == 1, message
    assert result["last_written_index"] == 1, "检查点仍推进到最后一个落库行"


def test_the_checkpoint_advance_algorithm_is_unchanged():
    """★ 检查点推进算法**没有被改成**「停在第一个矛盾行」。"""
    rows = [
        _row(
            {"platform_shop_id": "1391124228", "shop_id": "1419169771"},
            id=1,
            data_hash="hash-conflict",
        ),
        _row({"shop_account_id": "shopee_sg_hx_home_local"}, id=2, data_hash="hash-ok"),
    ]

    split = split_rows_by_dual_baseline(rows, LOCAL_INDEX, None)

    message = "推进算法必须仍然是「最后一个落库行」"
    assert split.last_written_index == 1, message
    assert split.conflict_rows == 1, message
    assert len(split.consistent) == 1, message


def test_a_batch_where_everything_conflicts_keeps_the_old_behaviour():
    """★ 整批都矛盾 ⇒ 检查点仍停在当前水位(既有语义不变)。"""
    rows = [
        _row(
            {"platform_shop_id": "1391124228", "shop_id": "1419169771"},
            id=1,
            data_hash="hash-conflict",
        )
    ]

    split = split_rows_by_dual_baseline(rows, LOCAL_INDEX, None)

    message = "整批矛盾 ⇒ 检查点不推进(既有语义)"
    assert split.last_written_index == -1, message
    assert split.conflict_rows == 1, message


# ---------------------------------------------------------------------------
# ⑦ 手工重发入口
# ---------------------------------------------------------------------------


def _fake_ledger_rows(status: str = STATUS_PENDING_MANUAL) -> list[dict[str, Any]]:
    return [
        {
            "id": 11,
            "dedup_key": "fact_shopee_analytics_monthly|2026-11-05|1|hash-1|"
            + REASON_LOCAL_REGISTRY_AMBIGUOUS,
            "source_table_name": "fact_shopee_analytics_monthly",
            "platform_code": "shopee",
            "data_domain": "analytics",
            "business_date": "2026-11-05",
            "row_locator": "1|hash-1",
            "source_row_id": "1",
            "identity_value": "shopee_sg_hx_home_local",
            "identity_tokens": {},
            "resolved_account_id": "",
            "resolved_accounts": ["shopee_sg_hx_home_local"],
            "cloud_accounts": [],
            "reason_code": REASON_LOCAL_REGISTRY_AMBIGUOUS,
            "status": status,
            "occurrence_count": 1,
            "first_seen_at": None,
            "last_seen_at": None,
            "resolution_status": "open",
            "resolved_by": None,
            "resolved_at": None,
            "resolution_note": None,
        }
    ]


def test_replay_dry_run_changes_nothing(monkeypatch, capsys):
    """★ ``--dry-run`` **不改动任何东西**。"""
    engine = _FakeLedgerEngine()
    calls: list[dict[str, Any]] = []

    def _fake_select(_engine, **kwargs):
        calls.append(kwargs)
        return _fake_ledger_rows()

    monkeypatch.setattr(replay_script, "create_engine", lambda _url: engine)
    monkeypatch.setattr(replay_script, "select_conflict_rows", _fake_select)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p@127.0.0.1:15433/db")

    exit_code = replay_script.main(["--dry-run"])

    output = capsys.readouterr().out
    message = "dry-run 必须成功返回且不写任何东西"
    assert exit_code == 0, message
    assert engine.written_statements == [], "dry-run 不许执行任何写语句"
    assert "DRY-RUN" in output, output


def test_replay_defaults_to_pending_manual_only(monkeypatch):
    """★ 默认只挑「待人工处理」的行。"""
    engine = _FakeLedgerEngine()
    calls: list[dict[str, Any]] = []

    def _fake_select(_engine, **kwargs):
        calls.append(kwargs)
        return _fake_ledger_rows()

    monkeypatch.setattr(replay_script, "create_engine", lambda _url: engine)
    monkeypatch.setattr(replay_script, "select_conflict_rows", _fake_select)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p@127.0.0.1:15433/db")

    replay_script.main(["--dry-run"])

    message = "默认必须只处理「待人工处理」的行"
    assert calls, "应当读过一次台账"
    assert calls[0]["statuses"] == [STATUS_PENDING_MANUAL], message


def test_replay_refuses_known_legacy_without_the_explicit_flag(monkeypatch, capsys):
    """★ 默认**不动**「已知历史遗留」的行(历史不修)。"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p@127.0.0.1:15433/db")

    exit_code = replay_script.main(["--execute", "--status", STATUS_KNOWN_LEGACY])

    output = capsys.readouterr().out
    message = "「已知历史遗留」必须默认拒绝"
    assert exit_code == 2, message
    assert "include-known-legacy" in output, output


def test_replay_execute_only_processes_pending_manual(monkeypatch):
    """★ ``--execute`` 也只处理「待人工处理」的行。"""
    engine = _FakeLedgerEngine()
    engine.source_rows = {
        "1": {
            "id": 1,
            "platform_code": "shopee",
            "shop_id": "1391124228",
            "data_domain": "analytics",
            "granularity": "monthly",
            "metric_date": "2026-11-05",
            "data_hash": "hash-1",
            "raw_data": {"shop_account_id": "shopee_sg_hx_home_local"},
        }
    }
    calls: list[dict[str, Any]] = []
    written_tables: list[str] = []

    def _fake_select(_engine, **kwargs):
        calls.append(kwargs)
        return _fake_ledger_rows()

    class _FakeWriter:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __call__(self, table_name, rows, data_domain):
            written_tables.append(table_name)
            return {"success": True, "written_rows": len(rows)}

    monkeypatch.setattr(replay_script, "create_engine", lambda _url: engine)
    monkeypatch.setattr(replay_script, "select_conflict_rows", _fake_select)
    monkeypatch.setattr(replay_script, "SQLAlchemyCloudWriter", _FakeWriter)
    monkeypatch.setattr(
        "backend.services.cloud_b_class_auto_sync_factory._load_identity_index",
        lambda _engine: LOCAL_INDEX,
    )
    monkeypatch.setattr(
        "backend.services.cloud_sync_identity_guard_service.load_cloud_identity_registry",
        lambda: _cloud_registry(),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p@127.0.0.1:15433/db")

    exit_code = replay_script.main(["--execute"])

    message = "执行路径必须成功"
    assert exit_code == 0, message
    assert calls[0]["statuses"] == [STATUS_PENDING_MANUAL], "只处理待人工处理"
    assert written_tables == ["fact_shopee_analytics_monthly"], written_tables


def test_replay_script_has_no_connection_string_literal():
    """★ 源码里**不得出现连接串字面量**。"""
    source = Path(replay_script.__file__).read_text(encoding="utf-8")

    message = "源码里出现了连接串字面量"
    assert "postgresql://" not in source, message
    assert "postgresql+psycopg" not in source, message
    assert "make_url" in source, "解析连接串要用 make_url"


# ---------------------------------------------------------------------------
# ⑧ 迁移链与 ORM 一致
# ---------------------------------------------------------------------------


def test_the_ledger_migration_points_at_the_current_chain_head():
    """★ 新迁移的 ``down_revision`` 必须指向当前链头。"""
    source = Path(
        Path(__file__).resolve().parents[2]
        / "current_migrations"
        / "versions"
        / "20261224_shop_identity_conflict_rows.py"
    ).read_text(encoding="utf-8")

    message = "迁移链的 revision 指向不对"
    assert (
        'revision = "current_schema_20261224_shop_identity_conflict_rows"' in source
    ), message
    assert (
        'down_revision = "current_schema_20261223_collection_source_identifiers"'
        in source
    ), message


def test_the_orm_model_and_the_migration_agree_on_the_columns():
    """★ ORM 模型与迁移的列名**必须一致**(否则代码一用就 500)。"""
    from modules.core.db import ShopIdentityConflictRow

    orm_columns = {column.name for column in ShopIdentityConflictRow.__table__.columns}

    source = Path(
        Path(__file__).resolve().parents[2]
        / "current_migrations"
        / "versions"
        / "20261224_shop_identity_conflict_rows.py"
    ).read_text(encoding="utf-8")

    message = "迁移里必须出现 ORM 声明的每一列"
    for column in sorted(orm_columns):
        if column == "id":
            continue
        assert '"%s"' % column in source, message

    message = "ORM 模型必须落在 ops 域"
    assert ShopIdentityConflictRow.__table__.schema == "ops", message
    assert (
        ShopIdentityConflictRow.__tablename__ == "shop_identity_conflict_rows"
    ), message


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


#: SQL 里出现的绑定参数名(``:name`` / ``%(name)s``)。
_BIND_PARAM_PATTERN = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def _assert_bind_params_present(sql: str, params: dict[str, Any]) -> None:
    """★ 绑定参数一个都不能少 —— 真库上少一个就直接抛异常。"""
    required = {
        name for name in _BIND_PARAM_PATTERN.findall(sql) if name not in ("keys",)
    }
    missing = sorted(required - set(params or {}))
    message = "SQL 里的绑定参数没给全: %s" % missing
    assert not missing, message


class _FakeLedgerConn:
    """模拟台账表: 按 ``dedup_key`` 唯一, 冲突时累计次数 +1。

    ⚠️ **会校验绑定参数** —— 真库上少一个绑定参数会直接抛
    ``InvalidRequestError: A value is required for bind parameter '...'``。
    替身不做这个校验的话, 「少绑一个参数」这种错会被漏过去 ⇒ 这里补上。
    """

    def __init__(self, engine) -> None:
        self.engine = engine

    def execute(self, statement, params=None):
        sql = str(statement)
        if self.engine.error is not None:
            raise self.engine.error
        if self.engine.execute_hook is not None:
            return self.engine.execute_hook(sql, params)
        if "SELECT dedup_key" in sql:
            keys = list((params or {}).get("keys") or [])
            return _FakeResult([(key,) for key in keys if key in self.engine.rows])
        if "INSERT INTO ops.shop_identity_conflict_rows" in sql:
            items = params if isinstance(params, list) else [params]
            for item in items:
                _assert_bind_params_present(sql, item)
                key = item["dedup_key"]
                if key in self.engine.rows:
                    row = self.engine.rows[key]
                    row["occurrence_count"] = int(row["occurrence_count"]) + 1
                    row["last_seen_at"] = item["now"]
                    row["status"] = item["status"]
                else:
                    new_row = dict(item)
                    new_row["occurrence_count"] = 1
                    self.engine.rows[key] = new_row
            self.engine.written_statements.append(sql)
            return _FakeResult([])
        if "FROM b_class." in sql:
            # 源行读取 —— 按主键返回预置的行。
            wanted = {
                value
                for key, value in (params or {}).items()
                if key.startswith("row_id_")
            }
            return _FakeResult(
                [
                    dict(row)
                    for row in self.engine.source_rows.values()
                    if str(row.get("id")) in wanted
                ]
            )
        return _FakeResult([])


class _FakeLedgerEngine:
    """台账引擎替身(带「表不存在」的模拟开关)。"""

    def __init__(self, *, error=None) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.source_rows: dict[str, dict[str, Any]] = {}
        self.error = error
        self.execute_hook = None
        self.written_statements: list[str] = []

    def connect(self):
        return self

    def begin(self):
        return self

    def __enter__(self):
        return _FakeLedgerConn(self)

    def __exit__(self, *exc_info):
        return False

    def dispose(self):
        return None


class _FakeWriterConn:
    def __init__(self, engine) -> None:
        self.engine = engine

    def execute(self, statement, params=None):
        self.engine.executed.append((str(statement), params))
        return _FakeResult([])


class _FakeWriterEngine:
    """云端写入引擎替身(只记录执行过的语句)。"""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    def begin(self):
        return self

    def __enter__(self):
        return _FakeWriterConn(self)

    def __exit__(self, *exc_info):
        return False

    def dispose(self):
        return None


class _BrokenLedgerRecorder:
    """台账记录器: 直接抛异常。"""

    def record_conflicts(self, **_kwargs):
        raise RuntimeError("ledger unavailable")


class _ExplodingLedgerRecorder:
    """台账记录器: 返回失败摘要(模拟表不存在)。"""

    def record_conflicts(self, **_kwargs):
        return {"status": "failed", "error": "relation does not exist", "new_rows": 0}


class _FakeLedgerRecorder:
    """按预设序列返回 ``new_rows`` 的台账记录器。"""

    def __init__(self, new_rows_sequence) -> None:
        self.new_rows_sequence = list(new_rows_sequence)
        self.calls: list[dict[str, Any]] = []

    def record_conflicts(self, **kwargs):
        self.calls.append(kwargs)
        new_rows = self.new_rows_sequence.pop(0) if self.new_rows_sequence else 0
        return {
            "status": "recorded",
            "new_rows": new_rows,
            "seen_rows": 0,
            "total_rows": len(kwargs.get("records") or []),
        }


class _FakeGuardRecorder:
    """记录守卫事件调用的替身。"""

    def __init__(self) -> None:
        self.mismatch_calls: list[dict[str, Any]] = []
        self.unavailable_calls: list[dict[str, Any]] = []

    def record_mismatch(self, **kwargs):
        self.mismatch_calls.append(kwargs)
        return {"status": "recorded"}

    def record_unavailable(self, **kwargs):
        self.unavailable_calls.append(kwargs)
        return {"status": "recorded"}


def test_the_guard_event_recorder_still_targets_pipeline_run_log():
    """★ 事件仍落在 ``ops.pipeline_run_log``(批次 3.7 的查询口径不变)。"""
    from backend.services.cloud_sync_identity_guard_service import (
        CloudSyncIdentityGuardEventRecorder as Recorder,
    )

    source = Path(guard_service.__file__).read_text(encoding="utf-8")
    message = "事件落点必须仍是 ops.pipeline_run_log"
    assert "ops.pipeline_run_log" in source, message
    assert Recorder.PIPELINE_NAME == GUARD_PIPELINE_NAME, message


def test_select_conflict_rows_is_read_only():
    """★ 读台账的函数**不得**含写语句。"""
    source = Path(ledger_service.__file__).read_text(encoding="utf-8")
    marker = "def select_conflict_rows("
    body = source[source.index(marker) :]
    message = "读台账的函数只许读"
    assert "UPDATE" not in body.upper(), message
    assert "DELETE" not in body.upper(), message


def test_select_conflict_rows_supports_the_filters(monkeypatch):
    """★ 读台账支持按源表 / 状态 / 日期范围筛选。"""
    engine = _FakeLedgerEngine()
    captured: dict[str, Any] = {}

    def _fake_execute(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return _FakeResult([])

    engine.execute_hook = _fake_execute

    rows = select_conflict_rows(
        engine,
        source_table_name="fact_shopee_products_daily",
        statuses=[STATUS_PENDING_MANUAL],
        date_from="2026-11-01",
        date_to="2026-11-30",
        reason_codes=[REASON_LOCAL_REGISTRY_AMBIGUOUS],
        limit=10,
    )

    message = "读台账必须带上限并返回空列表"
    assert rows == [], message
    assert "source_table_name" in captured["sql"], captured["sql"]
    assert "business_date" in captured["sql"], captured["sql"]
    assert captured["params"]["source_table_name"] == "fact_shopee_products_daily"
    assert captured["params"]["row_limit"] == 10


def test_asyncio_is_available_for_the_notify_helper():
    """★ 通知出口是异步的(挂在同步链路的异步层)。"""
    message = "通知出口必须是异步的"
    assert asyncio.iscoroutinefunction(ledger_service.notify_new_conflict_rows), message


# ---------------------------------------------------------------------------
# ⑧ 源行主键必须一路带到底（v7.20.1 热修）
# ---------------------------------------------------------------------------
#
# ⚠️ 这一节的坑是**真库实测**出来的, 假引擎测不出来：
#   - 同步的**生产路径**是「源行 → build_sync_payload → 写入器」,
#     而 build_sync_payload 原来只留 canonical 列 ⇒ **主键被丢掉**
#     ⇒ 守卫/台账拿到的行没有 id ⇒ source_row_id 恒为空
#     ⇒ 手工重发入口定位不到源行;
#   - 重发脚本读源行时只 SELECT canonical 列 ⇒ 真库不返回 id
#     ⇒ mapping.get("id") 恒为 None ⇒ 映射键全变成 "None"
#     ⇒ 每一行都被误判成「源行已不存在」。
#
# ⇒ 假引擎**不校验 SELECT 列**、也不校验负载的键集 ⇒ 这两条必须用
#    「忠实形状」的替身来盯。


class _FaithfulRow:
    """忠实模拟 SQLAlchemy 的 Row：**只有被 SELECT 的列**。"""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping

    def __getitem__(self, key: str) -> Any:
        return self._mapping[key]


class _FaithfulResult:
    def __init__(self, rows: list[_FaithfulRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[_FaithfulRow]:
        return list(self._rows)


class _FaithfulConn:
    """按 SQL 里**实际 SELECT 的列**造行 —— 与真库行为一致。"""

    def __init__(self, engine: "_FaithfulEngine") -> None:
        self._engine = engine

    def __enter__(self) -> "_FaithfulConn":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def execute(self, statement: Any, params: Any = None) -> _FaithfulResult:
        sql = str(statement)
        self._engine.sql = sql
        select_part = sql.split("FROM", 1)[0].replace("SELECT", "", 1)
        columns = [
            part.strip().strip('"') for part in select_part.split(",") if part.strip()
        ]
        self._engine.selected_columns = columns
        rows = []
        for row_id in list((params or {}).values()):
            mapping = {column: f"{column}-of-{row_id}" for column in columns}
            # 主键列的值就是行主键本身(与真库一致)。
            if "id" in mapping:
                mapping["id"] = row_id
            rows.append(_FaithfulRow(mapping))
        return _FaithfulResult(rows)


class _FaithfulEngine:
    """只记录 SQL 与被 SELECT 的列(不替你补列)。"""

    def __init__(self) -> None:
        self.sql = ""
        self.selected_columns: list[str] = []

    def connect(self) -> _FaithfulConn:
        return _FaithfulConn(self)

    def dispose(self) -> None:
        return None


def test_the_replay_loader_selects_the_primary_key():
    """★ 重发脚本读源行时**必须把主键一起 SELECT 出来**。"""
    engine = _FaithfulEngine()

    source_rows = replay_script._load_source_rows(
        engine,
        source_table_name="fact_shopee_analytics_monthly",
        source_row_ids=["1", "2"],
    )

    message = "SELECT 里必须带上主键, 否则真库不会返回它"
    assert "id" in engine.selected_columns, message

    message = "映射键必须是源行主键, 不能全是 None"
    assert set(source_rows.keys()) == {"1", "2"}, message


def test_the_sync_payload_keeps_the_source_row_primary_key():
    """★ 同步负载**必须带上源行主键** —— 守卫与台账靠它定位「这一行」。"""
    payload = build_sync_payload(
        {
            "id": 101,
            "platform_code": "shopee",
            "data_domain": "analytics",
            "data_hash": "hash-101",
        }
    )

    message = "负载必须带源行主键"
    assert payload.get("id") == 101, message


def test_the_production_path_records_the_source_row_id():
    """★ 生产路径(源行 → 负载 → 闸门)必须把 ``source_row_id`` 记下来。

    这正是「台账写进去的行却定位不到源行」的根因所在。
    """
    rows = [
        _row(
            {"platform_shop_id": "1391124228", "shop_id": "1419169771"},
            id=77,
            data_hash="hash-77",
        )
    ]
    payload_rows = [build_sync_payload(row) for row in rows]

    split = split_rows_by_dual_baseline(payload_rows, LOCAL_INDEX, None)

    message = "必须产出矛盾行事件"
    assert split.conflict_events, message

    message = "矛盾行事件必须带源行主键, 否则重发入口定位不到行"
    assert split.conflict_events[0].get("source_row_id") == "77", message

    message = "行内定位必须由源行主键 + 摘要拼成"
    assert split.conflict_events[0].get("row_locator") == "77|hash-77", message


def test_the_replay_payload_keeps_the_same_dedup_key_as_the_original():
    """★ 重发时算出的去重键必须与原始那一行**一致**（否则台账会多出一行）。"""
    original = build_dedup_key(
        source_table_name="fact_shopee_analytics_monthly",
        business_date="2026-11-05",
        row_locator=build_row_locator(source_row_id="77", data_hash="hash-77"),
        reason_code=REASON_LOCAL_REGISTRY_AMBIGUOUS,
    )

    row = _row(
        {"platform_shop_id": "1391124228", "shop_id": "1419169771"},
        id=77,
        data_hash="hash-77",
    )
    payload = build_sync_payload(row)
    replayed = build_dedup_key(
        source_table_name="fact_shopee_analytics_monthly",
        business_date="2026-11-05",
        row_locator=build_row_locator(
            source_row_id=payload.get("id"),
            data_hash=payload.get("data_hash"),
        ),
        reason_code=REASON_LOCAL_REGISTRY_AMBIGUOUS,
    )

    message = "重发算出的去重键必须与原始那一行相同"
    assert replayed == original, message

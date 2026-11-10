"""同步侧「双基准守卫」的守护测试(批次 3.7)。

背景
----
同步侧推送前的身份判定只看**本地**那份登记信息(``core.shop_accounts`` /
``core.shop_account_aliases``)。但**云端也有一份登记信息** —— 两边不同步时
(采集机本地台账与云端台账不一致), 本地判「自洽」的行推到云端后, 云端会用
**云端**的登记去解释 ⇒ 可能指向别的店 ⇒ **归属塌陷**(语义层落 ``unknown``)。

⇒ 本守卫在推送前**再比一次**: 两边解释不一致 ⇒ 该行降级为**可观测事件**
(记下来 / 可查 / 可计数), **不再当自洽行直接放行**, 但**不阻塞同步**。

本测试盯住五件事
----------------
1. **两边不一致 ⇒ 该行被降级**, 不再当自洽行放行;
2. **云端连不上 ⇒ 退回本地单基准** + 记「双基准不可用」事件, **同步不挂**;
3. **两边一致 ⇒ 行为与改造前完全相同**;
4. **降级事件可被查询/计数**, 且**不阻塞**同步;
5. **连接的建立与关闭不泄漏**。

⚠️ 断言消息一律提到**变量**里再 ``assert`` —— 本地 Python 3.13 与 CI 的
3.11 对 ``assert 条件, (消息)`` 的括号换行判定不同, 提成变量两端才都绿。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from backend.services import cloud_sync_identity_guard_service as guard_service
from backend.services.cloud_b_class_sync_service import (
    CloudBClassSyncService,
    SQLAlchemyCloudWriter,
    split_rows_by_dual_baseline,
    split_rows_by_identity_consistency,
)
from backend.services.cloud_sync_identity_guard_service import (
    DUAL_BASELINE_CONSISTENT,
    DUAL_BASELINE_MISMATCH,
    DUAL_BASELINE_NOT_APPLIED,
    DUAL_BASELINE_UNAVAILABLE,
    GUARD_ENABLED_ENV,
    GUARD_PIPELINE_NAME,
    LOAD_STATUS_DISABLED,
    LOAD_STATUS_LOADED,
    REASON_CLOUD_AMBIGUOUS,
    REASON_CLOUD_DIFFERENT_ACCOUNT,
    REASON_CLOUD_UNRESOLVED,
    CloudIdentityRegistry,
    CloudSyncIdentityGuardEventRecorder,
    classify_registry_agreement,
    load_cloud_identity_registry,
)
from backend.services.shop_identity_reconciliation_service import build_identity_index


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

#: 云端台账: 两个店的**平台编号整体错位了一位**(本地是对的)。
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


def _cloud_registry(index=CLOUD_INDEX) -> CloudIdentityRegistry:
    return CloudIdentityRegistry(
        status=LOAD_STATUS_LOADED,
        target="postgresql://127.0.0.1:15433/xihong_erp",
        index=index,
        account_count=2,
        alias_count=0,
    )


def _unavailable_registry(
    reason="cloud_registry_unreadable:boom",
) -> CloudIdentityRegistry:
    return CloudIdentityRegistry(
        status="unavailable",
        reason=reason,
        target="postgresql://127.0.0.1:15433/xihong_erp",
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
# ① 两边不一致 ⇒ 该行降级, 不再当自洽行放行
# ---------------------------------------------------------------------------


def test_registry_mismatch_degrades_the_row():
    """★ 本地认出的账号, 云端指向**另一个账号** ⇒ 该行被降级。"""
    rows = [_row({"platform_shop_id": "1391124228"})]

    split = split_rows_by_dual_baseline(rows, LOCAL_INDEX, _cloud_registry())

    message = "两边登记信息不一致的行不该再当自洽行放行"
    assert split.consistent == [], message
    assert split.degraded_rows == 1, message
    assert split.dual_baseline_status == DUAL_BASELINE_MISMATCH
    assert split.degraded[0]["reason"] == REASON_CLOUD_DIFFERENT_ACCOUNT
    assert split.degraded[0]["local_accounts"] == ["shopee_sg_hx_home_local"]
    assert split.degraded[0]["cloud_accounts"] == ["shopee_ph_xhkj11_local"]


def test_registry_mismatch_does_not_write_the_row_to_cloud():
    """★ 降级行**不写云端**(写上去云端会用云端登记解释 ⇒ 归属塌陷)。"""
    engine = _FakeEngine()
    writer = SQLAlchemyCloudWriter(
        engine=engine,
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "降级行不该被写进云端"
    assert result["written_rows"] == 0, message
    assert result["identity_registry_mismatch_rows"] == 1, message
    assert engine.conn.executed == [], message
    assert result["dual_baseline_status"] == DUAL_BASELINE_MISMATCH


def test_cloud_cannot_resolve_the_account_is_also_a_mismatch():
    """★ 本地认出的账号, 云端**认不出** ⇒ 同样是不一致。"""
    cloud_only_other = build_identity_index(
        [
            {
                "id": 9,
                "shop_account_id": "shopee_ph_other_local",
                "platform": "shopee",
                "platform_shop_id": "9999999999",
                "store_name": "other.ph",
                "shop_region": "PH",
                "enabled": True,
                "business_role": "operating_store",
            }
        ],
        [],
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    split = split_rows_by_dual_baseline(
        rows, LOCAL_INDEX, _cloud_registry(cloud_only_other)
    )

    message = "云端认不出本地认出的账号 ⇒ 不一致"
    assert split.degraded_rows == 1, message
    assert split.degraded[0]["reason"] == REASON_CLOUD_UNRESOLVED, message


def test_cloud_ambiguous_account_is_a_mismatch():
    """★ 云端自己都认不唯一 ⇒ 推上去也是歧义 ⇒ 不一致。"""
    ambiguous_accounts = [
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
            "platform_shop_id": "1391124228",  # ← 与上面同编号 ⇒ 歧义
            "store_name": "xhkj11.ph",
            "shop_region": "PH",
            "enabled": True,
            "business_role": "operating_store",
        },
    ]
    rows = [_row({"platform_shop_id": "1391124228"})]

    split = split_rows_by_dual_baseline(
        rows, LOCAL_INDEX, _cloud_registry(build_identity_index(ambiguous_accounts, []))
    )

    message = "云端歧义 ⇒ 不一致"
    assert split.degraded_rows == 1, message
    assert split.degraded[0]["reason"] == REASON_CLOUD_AMBIGUOUS, message


def test_only_the_mismatched_row_is_degraded():
    """一批里只有对不上的那几行被降级, 其余照常放行。"""
    rows = [
        _row({"platform_shop_id": "1391124228"}, data_hash="hash-a"),
        _row({"shop_account_id": "shopee_sg_hx_home_local"}, data_hash="hash-b"),
    ]

    split = split_rows_by_dual_baseline(rows, LOCAL_INDEX, _cloud_registry())

    message = "只有对不上的那行该被降级"
    assert split.degraded_rows == 1, message
    assert len(split.consistent) == 1, message
    assert split.written_indexes == (1,), message


def test_unresolved_rows_are_not_compared_across_environments():
    """★ 本地没唯一认出来的行**不做跨端比较** —— 行为保持不变。"""
    rows = [_row({"shop_account_id": "shopee_sg_eternalbloom_local"})]

    split = split_rows_by_dual_baseline(rows, LOCAL_INDEX, _cloud_registry())

    message = "未归属行没有可比对的基准, 不该被降级"
    assert split.degraded_rows == 0, message
    assert len(split.consistent) == 1, message
    assert split.unresolved_rows == 1, message


# ---------------------------------------------------------------------------
# ② 两边一致 ⇒ 行为与改造前完全相同
# ---------------------------------------------------------------------------


def test_identical_registries_keep_the_previous_behavior():
    """★ 两边一致 ⇒ 自洽行照常放行, 与改造前**完全相同**。"""
    rows = [_row({"platform_shop_id": "1391124228"})]

    before = split_rows_by_identity_consistency(rows, LOCAL_INDEX)
    after = split_rows_by_dual_baseline(rows, LOCAL_INDEX, _cloud_registry(LOCAL_INDEX))

    message = "两边一致时行为必须与改造前完全相同"
    assert len(after.consistent) == len(before.consistent) == 1, message
    assert after.written_indexes == before.written_indexes, message
    assert after.degraded == [], message
    assert after.dual_baseline_status == DUAL_BASELINE_CONSISTENT


def test_identical_registries_write_every_row():
    """两边一致 ⇒ 写进云端的行数与改造前一致。"""
    engine = _FakeEngine()
    writer = SQLAlchemyCloudWriter(
        engine=engine,
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(LOCAL_INDEX),
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "两边一致时不该少写行"
    assert result["written_rows"] == 1, message
    assert result["identity_registry_mismatch_rows"] == 0, message
    assert len(engine.conn.executed) == 1, message


# ---------------------------------------------------------------------------
# ③ 云端连不上 ⇒ 退回本地单基准 + 记「双基准不可用」事件, 同步不挂
# ---------------------------------------------------------------------------


def test_missing_local_registry_also_disables_the_dual_baseline():
    """★ 本地台账拿不到 ⇒ 双基准不可用(退回本地降级判据, 不比较)。"""
    rows = [_row({"platform_shop_id": "1391124228"})]

    split = split_rows_by_dual_baseline(rows, None, _cloud_registry())

    message = "本地台账拿不到时不该做跨端比较"
    assert split.dual_baseline_status == DUAL_BASELINE_UNAVAILABLE, message
    assert split.degraded == [], message
    assert len(split.consistent) == 1, message


def test_unreachable_cloud_falls_back_to_local_single_baseline():
    """★ 云端不可用 ⇒ 行为与改造前**完全相同**(本地单基准)。"""
    rows = [_row({"platform_shop_id": "1391124228"})]

    before = split_rows_by_identity_consistency(rows, LOCAL_INDEX)
    after = split_rows_by_dual_baseline(rows, LOCAL_INDEX, _unavailable_registry())

    message = "云端不可用时不该改变任何行为"
    assert len(after.consistent) == len(before.consistent) == 1, message
    assert after.degraded == [], message
    assert after.dual_baseline_status == DUAL_BASELINE_UNAVAILABLE


def test_unreachable_cloud_records_unavailable_event_and_keeps_syncing():
    """★ 云端不可用 ⇒ 记一条「双基准不可用」事件, **同步流程不挂**。"""
    engine = _FakeEngine()
    recorder = _FakeRecorder()
    writer = SQLAlchemyCloudWriter(
        engine=engine,
        identity_index=LOCAL_INDEX,
        cloud_registry=_unavailable_registry(),
        guard_event_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "云端连不上不该把同步搞挂"
    assert result["success"] is True, message
    assert result["written_rows"] == 1, message
    assert len(engine.conn.executed) == 1, message
    assert recorder.unavailable_calls, "应当记一条双基准不可用事件"
    assert recorder.mismatch_calls == [], "不可用时不该记成不一致"


def test_unavailable_event_is_recorded_only_once_per_run():
    """「双基准不可用」每轮只记一次(否则每批次刷一条)。"""
    recorder = _FakeRecorder()
    writer = SQLAlchemyCloudWriter(
        engine=_FakeEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_unavailable_registry(),
        guard_event_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")
    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "双基准不可用事件不该每批次刷一条"
    assert len(recorder.unavailable_calls) == 1, message


def test_missing_cloud_url_is_treated_as_unavailable(monkeypatch):
    """没配 ``CLOUD_DATABASE_URL`` ⇒ 双基准不可用(不是异常)。"""
    monkeypatch.delenv("CLOUD_DATABASE_URL", raising=False)

    registry = load_cloud_identity_registry()

    message = "没配连接串不该抛异常"
    assert registry.available is False, message
    assert registry.reason == "missing_cloud_database_url", message


def test_guard_can_be_disabled_by_env(monkeypatch):
    """★ 止血开关: 关掉后行为与本批次上线前**完全一致**。"""
    monkeypatch.setenv(GUARD_ENABLED_ENV, "0")
    monkeypatch.setenv("CLOUD_DATABASE_URL", "postgresql://u:p@127.0.0.1:15433/db")

    registry = load_cloud_identity_registry()

    message = "关掉开关后不该去连云端"
    assert registry.status == LOAD_STATUS_DISABLED, message
    assert registry.available is False, message


def test_disabled_guard_keeps_previous_behavior():
    """守卫被关掉 ⇒ 自洽行照常放行, 且**不记**任何事件。"""
    recorder = _FakeRecorder()
    disabled = CloudIdentityRegistry(status=LOAD_STATUS_DISABLED)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=disabled,
        guard_event_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "守卫关掉后不该有任何降级或事件"
    assert result["written_rows"] == 1, message
    assert result["identity_registry_mismatch_rows"] == 0, message
    assert result["dual_baseline_status"] == DUAL_BASELINE_NOT_APPLIED, message
    assert recorder.mismatch_calls == [], message
    assert recorder.unavailable_calls == [], message


# ---------------------------------------------------------------------------
# ④ 降级事件可被查询/计数, 且不阻塞同步
# ---------------------------------------------------------------------------


def test_guard_event_is_written_to_pipeline_run_log():
    """★ 降级事件写进 ``ops.pipeline_run_log``(不新建表)。"""
    engine = _FakeEngine()
    recorder = CloudSyncIdentityGuardEventRecorder(engine)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        guard_event_recorder=recorder,
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "应当写一条守卫事件进 ops.pipeline_run_log"
    assert len(engine.conn.executed) == 1, message
    statement, params = engine.conn.executed[0]
    assert "ops.pipeline_run_log" in statement
    assert params["pipeline_name"] == GUARD_PIPELINE_NAME
    assert params["status"] == "partial_failed"
    context = json.loads(params["context"])
    assert context["dual_baseline_status"] == DUAL_BASELINE_MISMATCH
    assert context["degraded_rows"] == 1
    assert context["events"][0]["reason"] == REASON_CLOUD_DIFFERENT_ACCOUNT


def test_guard_event_context_carries_countable_numbers():
    """★ 台账里带**可计数**的字段(不需要额外表)。"""
    engine = _FakeEngine()
    recorder = CloudSyncIdentityGuardEventRecorder(engine)
    events = [
        {
            "reason": REASON_CLOUD_DIFFERENT_ACCOUNT,
            "local_accounts": ["a"],
            "cloud_accounts": ["b"],
            "platform_code": "shopee",
            "row_index": 0,
        }
    ]

    recorder.record_mismatch(
        source_table_name="fact_shopee_products_daily",
        data_domain="products",
        events=events,
    )

    _statement, params = engine.conn.executed[0]
    context = json.loads(params["context"])
    message = "台账里必须带可计数的降级行数"
    assert context["degraded_rows"] == 1, message
    assert context["source_table_name"] == "fact_shopee_products_daily", message
    assert context["event_count"] == 1, message


def test_event_recording_failure_does_not_block_the_sync():
    """★ 记事件失败**绝不阻塞同步**(数据照写)。

    ⚠️ 这条用例以前是**空转**的: 行内的身份 token 用的是 ``shop_account_id``
    (本地与云端的账号编码本来就一样) ⇒ 两边解释一致 ⇒ 压根不进
    ``record_mismatch`` 分支 ⇒ 事件记录器**从未被调用**
    ⇒ 「记事件失败不阻塞同步」这条契约其实一直没有测试保护。
    ⇒ 现在行内必须带**平台编号**(两端认成不同的店)⇒ 真的降级、真的去记事件,
    并断言记录器**确实被调用过**。
    """
    broken_engine = _BrokenEngine()
    recorder = CloudSyncIdentityGuardEventRecorder(broken_engine)
    writer = SQLAlchemyCloudWriter(
        engine=_FakeEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        guard_event_recorder=recorder,
    )
    rows = [
        # ⚠️ 平台编号在两端认成不同的店 ⇒ 降级 ⇒ 真的去记事件。
        _row({"platform_shop_id": "1391124228"}),
        # 账号编码两端一致 ⇒ 自洽 ⇒ 照常落云端。
        _row({"shop_account_id": "shopee_sg_hx_home_local"}),
    ]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "记事件失败不该把同步搞挂"
    assert result["success"] is True, message
    message = "自洽的那一行必须照常落库"
    assert result["written_rows"] == 1, message
    message = "必须真的走到「记事件」这一步(否则这条用例就是空转)"
    assert broken_engine.begin_calls > 0, message
    message = "降级行数必须被如实上报"
    assert result["identity_registry_mismatch_rows"] == 1, message


def test_a_raising_event_recorder_does_not_block_the_sync():
    """★ 事件记录器**自己**炸了(不只是它内部的写库失败)也绝不阻塞同步。

    ⚠️ 这是**另一层**的兜底: 记录器内部的写库失败由记录器自己吞掉;
    记录器**整个**抛出来时, 由 ``_report_guard_events`` 的兜底吞掉。
    两层都要在, 同步才不会被可观测性拖挂。
    """

    class _RaisingRecorder:
        def record_mismatch(self, **_kwargs):
            raise RuntimeError("recorder exploded")

        def record_unavailable(self, **_kwargs):
            raise RuntimeError("recorder exploded")

    writer = SQLAlchemyCloudWriter(
        engine=_FakeEngine(),
        identity_index=LOCAL_INDEX,
        cloud_registry=_cloud_registry(),
        guard_event_recorder=_RaisingRecorder(),
    )
    rows = [_row({"platform_shop_id": "1391124228"})]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    message = "记录器自己炸了也不该把同步搞挂"
    assert result["success"] is True, message
    message = "降级行数必须仍然被如实上报"
    assert result["identity_registry_mismatch_rows"] == 1, message


def test_sync_table_reports_registry_mismatch_rows():
    """★ 表级结果里要带降级行数(可观测)。"""
    checkpoints = _FakeCheckpointService()
    service = _build_service(
        [_source_row(index) for index in range(3)],
        checkpoints,
        rejected_indexes={1},
        registry_mismatch_rows=1,
    )

    result = asyncio.run(service.sync_table("fact_shopee_analytics_monthly"))

    message = "表级结果里应当带降级行数"
    assert result["identity_registry_mismatch_rows"] == 1, message
    assert result["status"] == "partial_success", message


def test_sync_table_completed_when_registries_agree():
    """两边一致 ⇒ 状态仍是 ``completed``(与改造前相同)。"""
    checkpoints = _FakeCheckpointService()
    service = _build_service(
        [_source_row(index) for index in range(2)],
        checkpoints,
        rejected_indexes=set(),
        registry_mismatch_rows=0,
    )

    result = asyncio.run(service.sync_table("fact_shopee_analytics_monthly"))

    message = "两边一致时不该出现降级计数"
    assert result["status"] == "completed", message
    assert result["identity_registry_mismatch_rows"] == 0, message


# ---------------------------------------------------------------------------
# ⑤ 连接的建立与关闭不泄漏
# ---------------------------------------------------------------------------


def test_cloud_registry_connection_is_disposed_on_success(monkeypatch):
    """★ 读到数据后引擎**必须**被 dispose。"""
    engine = _FakeRegistryEngine(rows=_registry_records())
    monkeypatch.setattr(guard_service, "create_engine", lambda url: engine)

    registry = load_cloud_identity_registry("postgresql://u:p@127.0.0.1:15433/db")

    message = "引擎必须被 dispose, 否则连接会泄漏"
    assert registry.available is True, message
    assert engine.disposed == 1, message


def test_cloud_registry_connection_is_disposed_on_failure(monkeypatch):
    """★ 读失败时引擎**也必须**被 dispose(异常路径不漏连接)。"""
    engine = _FakeRegistryEngine(error=RuntimeError("connection refused"))
    monkeypatch.setattr(guard_service, "create_engine", lambda url: engine)

    registry = load_cloud_identity_registry("postgresql://u:p@127.0.0.1:15433/db")

    message = "异常路径也必须 dispose"
    assert registry.available is False, message
    assert engine.disposed == 1, message
    assert registry.reason


def test_guard_module_has_no_connection_string_literal():
    """★ 源码里**不得出现任何连接串字面量**(连接串只从环境变量读)。"""
    source = Path(guard_service.__file__).read_text(encoding="utf-8")

    message = "源码里出现了连接串字面量"
    assert "postgresql://" not in source, message
    assert "postgresql+psycopg" not in source, message


def test_guard_module_uses_make_url_not_urlparse():
    """★ 解析连接串用 ``make_url``(自动解码百分号编码口令)。"""
    source = Path(guard_service.__file__).read_text(encoding="utf-8")

    message = "不能用 urlparse 解析连接串(不解码百分号编码口令)"
    assert "urlparse(" not in source, message
    assert "import urlparse" not in source, message
    assert "make_url" in source, message


def test_redacted_error_message_never_contains_the_password():
    """★ 异常消息里的口令必须被抹掉(日志/台账都会被运维看到)。"""
    raw_url = "postgresql://erp_user:p%40ssword@127.0.0.1:15433/db"

    redacted = guard_service._redact(
        "could not connect: password p%40ssword rejected", raw_url
    )

    message = "口令(编码形式)必须被抹掉"
    assert "p%40ssword" not in redacted, message
    assert "***" in redacted, message


def test_redaction_handles_a_password_with_a_bare_at_sign():
    """★ 口令里带**未编码的 ``@``** ⇒ 必须整个抹掉, 不能只剩尾巴。

    ``make_url`` 只取到第一个 ``@`` 之前的那一段 ⇒ 口令 ``p@ss`` 会被当成
    ``p`` 抹掉, 剩下 ``***@ss`` —— 尾巴 ``ss`` 露在外面。
    """
    raw_url = "postgresql://erp_user:p@ss@127.0.0.1:15433/db"

    redacted = guard_service._redact("boom p@ss", raw_url)

    message = "带裸 @ 的口令必须被整个抹掉"
    assert "p@ss" not in redacted, message
    assert "ss" not in redacted, message
    assert "***" in redacted, message


def test_the_cloud_registry_index_build_failure_does_not_escape(monkeypatch):
    """★ 云端建索引炸了 ⇒ **绝不能**把整个同步任务打挂。

    守卫的契约是「云端这一侧读不了 / 建不了索引就退回本地单基准」。
    拆行与建索引原本在 try 之外 ⇒ 异常会一路冒到 worker ⇒ 整批数据不落云端。
    """
    engine = _FakeRegistryEngine(rows=_registry_records())
    monkeypatch.setattr(guard_service, "create_engine", lambda url: engine)

    def _boom(*_args, **_kwargs):
        raise ValueError("bad registry row")

    monkeypatch.setattr(guard_service, "build_identity_index", _boom)

    registry = guard_service.load_cloud_identity_registry(
        "postgresql://u:p@127.0.0.1:15433/db"
    )

    message = "建索引失败必须降级成「不可用」, 而不是抛异常"
    assert registry.available is False, message
    assert registry.status == "unavailable", message
    message = "降级原因必须写清楚"
    assert registry.reason, message
    message = "连接仍必须被 dispose"
    assert engine.disposed == 1, message


# ---------------------------------------------------------------------------
# 判定口径(纯函数)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("local_accounts", "cloud_accounts", "expected"),
    [
        (["a"], ["a"], None),
        (["a"], [], REASON_CLOUD_UNRESOLVED),
        (["a"], ["b"], REASON_CLOUD_DIFFERENT_ACCOUNT),
        (["a"], ["b", "c"], REASON_CLOUD_AMBIGUOUS),
    ],
)
def test_classify_registry_agreement(local_accounts, cloud_accounts, expected):
    """判定口径: 一致 ⇒ None; 三种不一致各有各的原因码。"""
    assert classify_registry_agreement(local_accounts, cloud_accounts) == expected


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))


class _FakeEngine:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc_info):
        return False

    def dispose(self):
        return None


class _BrokenEngine:
    """写入必炸的引擎(用来验证「记事件失败不阻塞同步」)。"""

    def __init__(self) -> None:
        #: 被调用了几次 —— 用它证明「事件记录器确实被调用过」(防空转)。
        self.begin_calls = 0

    def begin(self):
        self.begin_calls += 1
        raise RuntimeError("local database unavailable")


class _FakeRecorder:
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


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeRegistryEngine:
    """模拟云端引擎: 记录 dispose 是否被调用。"""

    def __init__(self, *, rows=None, error=None) -> None:
        self.rows = rows or []
        self.error = error
        self.disposed = 0

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, statement, params=None):
        if self.error is not None:
            raise self.error
        return _FakeResult(self.rows)

    def dispose(self):
        self.disposed += 1


def _registry_records():
    """模拟 ``core.shop_accounts`` LEFT JOIN ``core.shop_account_aliases`` 的扁平行。"""
    return [
        {
            "account_pk": 1,
            "shop_account_id": "shopee_sg_hx_home_local",
            "platform": "shopee",
            "platform_shop_id": "1391124228",
            "store_name": "hx_home.sg",
            "shop_region": "SG",
            "enabled": True,
            "business_role": "operating_store",
            "alias_pk": None,
            "alias_owner_pk": None,
            "alias_value": None,
            "alias_normalized": None,
            "is_active": None,
        }
    ]


class _FakeCheckpointService:
    def __init__(self) -> None:
        self.advanced: list[dict[str, Any]] = []
        self.failures: list[tuple] = []

    def create_or_get_checkpoint(self, table_name, table_schema="b_class"):
        return None

    def advance_checkpoint(
        self, table_name, ingest_timestamp, source_id, status, table_schema="b_class"
    ):
        self.advanced.append({"source_id": source_id, "status": status})

    def mark_failure(self, table_name, message, table_schema="b_class"):
        self.failures.append((table_name, message))


class _FakeMirrorManager:
    def ensure_cloud_mirror_table(self, table_name, data_domain):
        return None


class _StubWriter:
    def __init__(self, rejected_indexes, registry_mismatch_rows=0) -> None:
        self.rejected_indexes = set(rejected_indexes)
        self.registry_mismatch_rows = registry_mismatch_rows

    def __call__(self, table_name, rows, data_domain):
        written_indexes = [
            index for index in range(len(rows)) if index not in self.rejected_indexes
        ]
        return {
            "success": True,
            "written_rows": len(written_indexes),
            "identity_conflict_rows": len(self.rejected_indexes),
            "identity_unresolved_rows": 0,
            "identity_registry_mismatch_rows": self.registry_mismatch_rows,
            "last_written_index": written_indexes[-1] if written_indexes else -1,
        }


def _source_row(index: int) -> dict:
    return {
        "id": index + 1,
        "ingest_timestamp": "2026-06-22T00:00:00+00:00",
        "platform_code": "shopee",
        "shop_id": "1391124228",
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "data_hash": "hash-%d" % index,
        "raw_data": {"shop_account_id": "shopee_sg_hx_home_local"},
    }


def _build_service(rows, checkpoint_service, rejected_indexes, registry_mismatch_rows):
    return CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=_FakeMirrorManager(),
        source_batch_reader=lambda **kwargs: list(rows),
        remote_writer=_StubWriter(rejected_indexes, registry_mismatch_rows),
        receive_log_recorder=None,
    )

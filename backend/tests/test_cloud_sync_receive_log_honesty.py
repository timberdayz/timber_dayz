"""D 项守护: 账本诚实 + 检查点只按真正落库的行推进 + 作业状态 ``partial_success``。

事故背景
--------
2026-11-07 的采集同步丢数事故里, 有三件事同时发生在**云端接收账本**上:

1. **账本虚报** —— ``ops.cloud_sync_receive_log.written_rows`` 记的是
   「送进 writer 的行数」, 不是「真正写进云端的行数」。
   生产最后一条记录是 ``written_rows=72, status=completed``,
   而那 72 行**一行都没落库**。
2. **检查点照常推进** —— 检查点无条件推进到 ``rows[-1]``,
   于是那些**根本没写进去**的行被一并跳过 ⇒ 永久丢数。
3. **作业报成功** —— 明明有行被丢弃, 状态却是 ``completed``,
   没有任何地方能看出「这一批丢了几行」。

本文件把这三件事逐一钉死:

* 账本记**实际落库行数**, 并额外记「被拒行数」与「未归属行数」;
* 账本状态在有行被拒时是 ``partial_success``, 不是 ``completed``;
* 检查点**只**推进到最后一行**真正落库**的数据;
* 一行都没落库时, 检查点**不推进**, 作业落 ``partial_success``。
"""

from __future__ import annotations

from typing import Any

from backend.services.cloud_b_class_sync_service import (
    CloudBClassSyncService,
    SQLAlchemyCloudWriter,
    split_rows_by_identity_consistency,
)
from backend.services.shop_identity_reconciliation_service import build_identity_index


# ---------------------------------------------------------------------------
# 主数据样例
# ---------------------------------------------------------------------------

ACCOUNTS = [
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

INDEX = build_identity_index(ACCOUNTS, [])


def _row(shop_id: str, *, raw_shop_id: str | None = None, **extra: Any) -> dict:
    raw_data: dict[str, Any] = {"shop_account_id": "shopee_sg_hx_home_local"}
    if raw_shop_id is not None:
        raw_data["shop_id"] = raw_shop_id
    row = {
        "platform_code": "shopee",
        "shop_id": shop_id,
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "raw_data": raw_data,
        "data_hash": "hash-1",
    }
    row.update(extra)
    return row


def _conflicting_row() -> dict:
    """行内两个身份键指向**不同**账号 ⇒ 真矛盾。"""
    return {
        "platform_code": "shopee",
        "shop_id": "1419169771",
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "data_hash": "hash-2",
        "raw_data": {
            "platform_shop_id": "1391124228",  # → shopee_sg_hx_home_local
            "shop_account_id": "shopee_ph_xhkj11_local",  # → 另一个账号
        },
    }


# ---------------------------------------------------------------------------
# ① 账本诚实
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self) -> None:
        self.executed: list[Any] = []

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


class _CapturingRecorder:
    """捕获账本写入参数(不连数据库)。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record_success_on_connection(self, conn, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": kwargs.get("status", "completed"),
            "receive_id": kwargs.get("receive_id", "receive-test"),
            "written_rows": kwargs.get("written_rows", 0),
        }


def _write_with_log(rows: list[dict]) -> tuple[dict, dict]:
    engine = _FakeEngine()
    recorder = _CapturingRecorder()
    writer = SQLAlchemyCloudWriter(engine=engine, identity_index=INDEX)

    result = writer.write_rows_with_receive_log(
        table_name="fact_shopee_analytics_monthly",
        rows=rows,
        data_domain="analytics",
        receive_log_recorder=recorder,
        receive_log_context={
            "source_table_name": "fact_shopee_analytics_monthly",
            "receive_id": "receive-test",
            "written_rows": len(rows),  # ← 上游给的"送进去的行数"
            "rows": rows,
        },
    )
    return result, recorder.calls[0]


def test_receive_log_records_actual_written_rows_not_submitted_rows():
    """★ 账本必须记**真正落库**的行数。

    事故里账本记 72 行 / 实际落库 0 行 —— 因为它记的是"送进去"的行数。
    """
    rows = [_row("1391124228", raw_shop_id="1391124228"), _conflicting_row()]

    result, logged = _write_with_log(rows)

    assert result["written_rows"] == 1
    assert logged["written_rows"] == 1, "账本记的是送进去的行数(2), 不是落库行数(1)"
    assert logged["written_rows"] != len(rows)


def test_receive_log_records_conflict_and_unresolved_counts():
    """★ 被拒行数与未归属行数都要进账本。"""
    rows = [_row("1391124228", raw_shop_id="1391124228"), _conflicting_row()]

    _result, logged = _write_with_log(rows)

    assert logged["identity_conflict_rows"] == 1
    assert "identity_unresolved_rows" in logged


def test_receive_log_status_is_partial_success_when_rows_rejected():
    """★ 有行被拒时, 账本状态是 ``partial_success`` 而不是 ``completed``。"""
    rows = [_row("1391124228", raw_shop_id="1391124228"), _conflicting_row()]

    _result, logged = _write_with_log(rows)

    assert logged["status"] == "partial_success"


def test_receive_log_status_is_completed_when_nothing_rejected():
    """没有行被拒 ⇒ 状态仍是 ``completed``。"""
    rows = [_row("1391124228", raw_shop_id="1391124228")]

    _result, logged = _write_with_log(rows)

    assert logged["status"] == "completed"
    assert logged["written_rows"] == 1


def test_unresolved_rows_are_counted_but_still_written():
    """★ 未归属(认不到主数据账号)的行**照常落库**, 只是被计数。

    把"未归属"当成"矛盾"丢掉, 就是 2026-11-07 事故的形态。
    """
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1292370001",
            "data_domain": "analytics",
            "granularity": "monthly",
            "sub_domain": None,
            "metric_date": "2026-06-22",
            "data_hash": "hash-3",
            "raw_data": {
                "shop_account_id": "shopee_sg_eternalbloom_local",  # 已停用, 不在索引
                "shop_id": "1292370001",
            },
        }
    ]

    split = split_rows_by_identity_consistency(rows, INDEX)

    assert split.written_rows == 1, "未归属的行不该被丢掉"
    assert split.conflict_rows == 0
    assert split.unresolved_rows == 1, "未归属的行要被计数"


# ---------------------------------------------------------------------------
# ② 检查点只按真正落库的行推进
# ---------------------------------------------------------------------------


class _FakeCheckpointService:
    def __init__(self) -> None:
        self.advanced: list[dict[str, Any]] = []
        self.failures: list[tuple] = []

    def create_or_get_checkpoint(self, table_name, table_schema="b_class"):
        return None

    def advance_checkpoint(
        self, table_name, ingest_timestamp, source_id, status, table_schema="b_class"
    ):
        self.advanced.append(
            {
                "table_name": table_name,
                "ingest_timestamp": ingest_timestamp,
                "source_id": source_id,
                "status": status,
            }
        )

    def mark_failure(self, table_name, message, table_schema="b_class"):
        self.failures.append((table_name, message))


class _FakeMirrorManager:
    def ensure_cloud_mirror_table(self, table_name, data_domain):
        return None


class _StubWriter:
    """按给定下标把行分成「落库」与「被拒」, 并如实回报计数。"""

    def __init__(self, rejected_indexes: set[int]) -> None:
        self.rejected_indexes = set(rejected_indexes)

    def __call__(self, table_name, rows, data_domain):
        written_indexes = [
            index for index in range(len(rows)) if index not in self.rejected_indexes
        ]
        return {
            "success": True,
            "written_rows": len(written_indexes),
            "identity_conflict_rows": len(self.rejected_indexes),
            "identity_unresolved_rows": 0,
            "last_written_index": written_indexes[-1] if written_indexes else -1,
        }


def _source_row(index: int) -> dict:
    return {
        "id": index + 1,
        "ingest_timestamp": f"2026-06-2{index}T00:00:00+00:00",
        "platform_code": "shopee",
        "shop_id": "1391124228",
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "data_hash": f"hash-{index}",
        "raw_data": {"shop_account_id": "shopee_sg_hx_home_local"},
    }


def _build_service(rows, rejected_indexes, checkpoint_service):
    return CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=_FakeMirrorManager(),
        source_batch_reader=lambda **kwargs: list(rows),
        remote_writer=_StubWriter(rejected_indexes),
        receive_log_recorder=None,
    )


def test_checkpoint_advances_only_to_the_last_written_row():
    """★ 检查点只能推进到最后一行**真正落库**的数据。

    推进到 ``rows[-1]`` 就等于把被拒的行一并跳过 —— 那是丢数的机制本身。
    """
    rows = [_source_row(index) for index in range(3)]
    checkpoints = _FakeCheckpointService()
    service = _build_service(rows, {2}, checkpoints)

    import asyncio

    result = asyncio.run(service.sync_table("fact_shopee_analytics_monthly"))

    assert checkpoints.advanced, "检查点应当推进到第 2 行(index=1)"
    advanced = checkpoints.advanced[-1]
    assert advanced["source_id"] == 2, "推进到了被拒行的 source_id(3) ⇒ 会跳过丢数行"
    assert advanced["ingest_timestamp"] == rows[1]["ingest_timestamp"]
    assert result["status"] == "partial_success"


def test_checkpoint_does_not_advance_when_no_row_was_written():
    """★ 本批一行都没落库 ⇒ 检查点**不推进**, 停在当前水位。"""
    rows = [_source_row(index) for index in range(2)]
    checkpoints = _FakeCheckpointService()
    service = _build_service(rows, {0, 1}, checkpoints)

    import asyncio

    result = asyncio.run(service.sync_table("fact_shopee_analytics_monthly"))

    assert checkpoints.advanced == [], "一行都没落库却推进了检查点 ⇒ 会静默跳过"
    assert result["status"] == "partial_success"
    assert result["identity_conflict_rows"] == 2


def test_sync_table_completed_when_nothing_rejected():
    """没有行被拒 ⇒ 状态仍是 ``completed``。"""
    rows = [_source_row(index) for index in range(2)]
    checkpoints = _FakeCheckpointService()
    service = _build_service(rows, set(), checkpoints)

    import asyncio

    result = asyncio.run(service.sync_table("fact_shopee_analytics_monthly"))

    assert result["status"] == "completed"
    assert result["identity_conflict_rows"] == 0
    assert len(checkpoints.advanced) == 1


def test_sync_all_tables_distinguishes_partial_from_failed():
    """汇总时要把「部分成功」与「真失败」分开统计。"""
    import asyncio

    class _Handler:
        @staticmethod
        async def handler(table_name, batch_size=1000):
            if table_name.endswith("_a"):
                return {"status": "completed", "written_rows": 10}
            if table_name.endswith("_b"):
                return {"status": "partial_success", "written_rows": 8}
            return {"status": "failed", "written_rows": 0, "error": "boom"}

    checkpoints = _FakeCheckpointService()
    service = CloudBClassSyncService(
        checkpoint_service=checkpoints,
        mirror_manager=_FakeMirrorManager(),
        source_batch_reader=lambda **kwargs: [],
        remote_writer=_StubWriter(set()),
        table_inspector=lambda: ["fact_a", "fact_b", "fact_c"],
        sync_table_handler=_Handler.handler,
        receive_log_recorder=None,
    )

    summary = asyncio.run(service.sync_all_tables())

    assert summary["status"] == "partial_success"
    assert summary["succeeded_tables"] == 1
    assert summary["partial_tables"] == 1
    assert summary["failed_tables"] == 1

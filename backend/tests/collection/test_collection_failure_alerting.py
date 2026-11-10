"""采集失败**主动告警**（批次 3.4 / 任务单 P2-5）的守护测试。

覆盖九件事：

1. **失败终态判定口径不变**：只有「0 个域成功且有失败」才是 ``failed``；
   ``partial_success`` 不算失败终态；
2. **同轮聚类**：同一轮 7 个店挂在同一个错误上 ⇒ 只发 **1 条**通知；
3. **跨轮去重**：同一问题连续多轮只通知一次；
4. **恢复后再失败** ⇒ 重新通知（去重不是「一辈子只发一次」）；
5. **``partial_success`` 不发失败告警**，但**单独记一档**（台账里看得见）；
6. **「等待验证码回填」单独归类**，不与步骤失败混聚；
7. **脱敏**：连接串/口令不进通知正文；店铺标识中段遮蔽；
8. **通知失败不影响采集主流程**：通道全挂时不抛异常、状态照常落库，
   且**不记入已通知集合** ⇒ 下一轮重试；
9. **快速采集（不属于配置轮次）的单任务失败**也会告警。
"""

import json

import pytest

from backend.services.collection_failure_alert_service import (
    CATEGORY_STEP_FAILURE,
    CATEGORY_VERIFICATION_WAIT,
    COLLECTION_FAILURE_ALERT_TYPE_PREFIX,
    PIPELINE_NAME,
    alert_collection_run_failures,
    alert_collection_task_failure,
    classify_failure_category,
    cluster_failures,
    error_fingerprint,
    mask_shop_label,
    normalize_error_text,
)
from backend.services.data_pipeline.source_freshness_notify import mask_sensitive_text

STEP_ERROR = "TimeoutError: date option was not clicked"


class _FakeResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字返回预置结果，并记录执行过的语句。

    它还会**记住上一轮写进运行日志的 context** ⇒ 下一轮读「已通知过的指纹」时
    能拿到上一轮的结果 —— 这正是跨轮去重依赖的那份状态。
    """

    def __init__(self, *, task_rows=()):
        self._task_rows = list(task_rows)
        self._previous_context = None
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.inserted_context = None

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        params = args[0] if args else kwargs
        self.statements.append((sql, params))
        stripped = sql.lstrip().upper()

        if "core.collection_tasks" in sql:
            return _FakeResult(self._task_rows)
        if stripped.startswith("SELECT") and "ops.pipeline_run_log" in sql:
            rows = []
            if self._previous_context is not None:
                rows.append((self._previous_context,))
            return _FakeResult(rows)
        if stripped.startswith("INSERT") and "ops.pipeline_run_log" in sql:
            context = params.get("context") if isinstance(params, dict) else None
            if context:
                self.inserted_context = json.loads(context)
                self._previous_context = self.inserted_context
        return _FakeResult([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _row(
    task_id,
    account_id,
    *,
    status="failed",
    failed_domains=None,
    error_message=None,
    platform="shopee",
):
    """一行 ``core.collection_tasks`` 的采集视角字段。"""
    return (
        task_id,
        platform,
        account_id,
        status,
        failed_domains,
        error_message,
    )


def _install_channels(monkeypatch, calls, *, in_app_ok=True, webhook_ok=True):
    """把两条现成通知通道换成记录用的假实现。"""

    async def _fake_in_app(db, notification_type, title, content, **kwargs):
        calls.append(
            {
                "channel": "in_app",
                "title": title,
                "content": content,
                "extra_data": kwargs.get("extra_data"),
            }
        )
        return [object()] if in_app_ok else []

    async def _fake_webhook(alert_type, message, *args, **kwargs):
        calls.append({"channel": "webhook", "alert_type": alert_type})
        return webhook_ok

    monkeypatch.setattr(
        "backend.domains.platform.routers.notifications.create_notifications_for_admins",
        _fake_in_app,
    )
    monkeypatch.setattr(
        "backend.services.alert_service.send_resource_alert", _fake_webhook
    )


# ── 1. 失败终态判定口径不变 ────────────────────────────────────────────


def test_failed_terminal_status_only_when_no_domain_succeeded():
    """只有「0 个域成功且有失败」才是 ``failed``；部分成功不是失败终态。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)

    status, _message = CollectionExecutorV2._resolve_final_collection_status(
        executor,
        completed_count=0,
        failed_count=3,
        total_domains_count=3,
        processed_file_count=0,
    )
    assert status == "failed"

    status, _message = CollectionExecutorV2._resolve_final_collection_status(
        executor,
        completed_count=2,
        failed_count=1,
        total_domains_count=3,
        processed_file_count=1,
    )
    assert status == "partial_success"

    status, _message = CollectionExecutorV2._resolve_final_collection_status(
        executor,
        completed_count=3,
        failed_count=0,
        total_domains_count=3,
        processed_file_count=2,
    )
    assert status == "completed"


# ── 2. 同轮聚类：7 个店同一错误 ⇒ 1 条通知 ─────────────────────────────


@pytest.mark.asyncio
async def test_seven_shops_with_same_error_produce_one_notification(monkeypatch):
    """同一轮 7 个店挂在同一个错误上 ⇒ 聚成 1 条通知（不是 7 条）。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            f"task-{index}",
            f"shop-sg-{index}",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
        for index in range(1, 8)
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_run_failures(session, config_run_id=42)

    assert len(outcome.notified) == 1
    assert len(calls) == 2  # 站内信 + webhook 各一次
    assert calls[0]["channel"] == "in_app"
    assert calls[1]["channel"] == "webhook"

    in_app = calls[0]
    assert "7 个店铺" in in_app["title"]
    assert in_app["extra_data"]["shop_count"] == 7
    assert in_app["extra_data"]["task_count"] == 7
    assert in_app["extra_data"]["domains"] == ["orders"]


@pytest.mark.asyncio
async def test_different_errors_in_same_round_are_clustered_separately(monkeypatch):
    """两个不同的错误 ⇒ 两条通知（聚类按错误指纹，不是按轮次一刀切）。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        ),
        _row(
            "task-2",
            "shop-sg-2",
            failed_domains=[
                {"domain": "products", "error": "TimeoutError: export failed"}
            ],
        ),
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_run_failures(session, config_run_id=42)

    assert len(outcome.notified) == 2
    assert len(calls) == 4


# ── 3./4. 跨轮去重 + 恢复后重新通知 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_same_problem_is_notified_only_once_across_rounds(monkeypatch):
    """同一问题连续多轮 ⇒ 只在第一轮通知。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    first = await alert_collection_run_failures(session, config_run_id=42)
    assert len(first.notified) == 1
    assert len(calls) == 2

    calls.clear()
    second = await alert_collection_run_failures(session, config_run_id=43)

    assert second.notified == []
    assert len(second.suppressed) == 1
    assert calls == []


@pytest.mark.asyncio
async def test_recovered_problem_is_notified_again_when_it_breaks_again(monkeypatch):
    """恢复后再失败 ⇒ 重新通知（去重不是「一辈子只发一次」）。"""
    calls = []
    _install_channels(monkeypatch, calls)

    failed_rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=failed_rows)

    await alert_collection_run_failures(session, config_run_id=42)
    assert len(calls) == 2

    # 第二轮：恢复（没有失败任务）⇒ 状态被清空
    calls.clear()
    session._task_rows = []
    recovered = await alert_collection_run_failures(session, config_run_id=43)
    assert recovered.notified == []
    assert calls == []
    assert session.inserted_context["notified_collection_failures"] == []

    # 第三轮：再次失败 ⇒ 重新通知
    calls.clear()
    session._task_rows = failed_rows
    again = await alert_collection_run_failures(session, config_run_id=44)
    assert len(again.notified) == 1
    assert len(calls) == 2


# ── 5. partial_success 不算失败告警（只单独记一档） ────────────────────


@pytest.mark.asyncio
async def test_partial_success_is_not_alerted_but_is_recorded_separately(monkeypatch):
    """``partial_success`` 不发失败告警，但在运行日志里**单独记一档**。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            status="partial_success",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_run_failures(session, config_run_id=42)

    assert outcome.notified == []
    assert calls == []
    assert len(outcome.partial_success_clusters) == 1
    assert session.inserted_context["partial_success_clusters"]
    assert session.inserted_context["notified_collection_failures"] == []


# ── 6. 「等待验证码回填」单独归类 ───────────────────────────────────────


def test_verification_wait_is_classified_apart_from_step_failure():
    """等待验证码回填 ⇒ 单独一档，绝不与步骤失败混在一起。"""
    assert classify_failure_category("验证码等待超时") == CATEGORY_VERIFICATION_WAIT
    assert classify_failure_category("等待人工处理超时") == CATEGORY_VERIFICATION_WAIT
    assert classify_failure_category("TimeoutError: date option was not clicked") == (
        CATEGORY_STEP_FAILURE
    )


@pytest.mark.asyncio
async def test_verification_wait_is_not_merged_into_step_failure_cluster(monkeypatch):
    """验证码等待与步骤失败**不聚成一簇**，也不触发失败告警。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": "验证码等待超时"}],
        ),
        _row(
            "task-2",
            "shop-sg-2",
            failed_domains=[{"domain": "products", "error": STEP_ERROR}],
        ),
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_run_failures(session, config_run_id=42)

    assert len(outcome.verification_waits) == 1
    assert len(outcome.notified) == 1
    # 只有步骤失败那一簇发了通知
    assert len(calls) == 2
    assert calls[0]["extra_data"]["domains"] == ["products"]
    assert session.inserted_context["verification_waits"]


# ── 7. 脱敏 ────────────────────────────────────────────────────────────


def test_masking_is_shared_with_batch_3_3_implementation():
    """脱敏口径只有一处：复用批次 3.3 已落地的实现，不许抄第二份。"""
    from backend.services.collection_failure_alert_service import (
        mask_sensitive_text as module_mask,
    )
    from backend.services.data_pipeline.source_freshness_notify import (
        mask_sensitive_text as canonical_mask,
    )

    assert module_mask is canonical_mask


def test_sensitive_text_is_masked():
    """连接串口令 / token 一律替换掉。"""
    assert "secretpass" not in mask_sensitive_text(
        "postgresql://erp_user:secretpass@localhost:15432/xihong_erp"
    )
    assert "abc123" not in mask_sensitive_text("login failed password=abc123")
    assert "tok-xyz" not in mask_sensitive_text("header token=tok-xyz")


def test_shop_label_is_masked_in_the_middle():
    """店铺标识中段遮蔽（整段抹掉就没法定位问题）。"""
    assert mask_shop_label("shop-sg-1") == "sh***-1"
    assert mask_shop_label("ab") == "***"
    assert mask_shop_label("") == "unknown"


@pytest.mark.asyncio
async def test_notification_content_carries_no_credentials(monkeypatch):
    """通知正文里没有连接串口令，也没有店铺明文。"""
    calls = []
    _install_channels(monkeypatch, calls)

    secret_error = "postgresql://erp_user:secretpass@localhost:15432/xihong_erp"
    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": secret_error}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    await alert_collection_run_failures(session, config_run_id=42)

    content = calls[0]["content"]
    assert "secretpass" not in content
    assert "shop-sg-1" not in content
    assert "sh***-1" in content


def test_error_fingerprint_ignores_volatile_parts():
    """数字/时间戳/URL 变化不应把同一个问题分成两条指纹。"""
    left = error_fingerprint("TimeoutError: page 12 not ready at 2026-11-11 08:00:00")
    right = error_fingerprint("TimeoutError: page 99 not ready at 2026-11-12 09:30:00")
    assert left == right

    other = error_fingerprint("TimeoutError: export failed")
    assert other != left


def test_normalize_error_text_replaces_volatile_parts():
    normalized = normalize_error_text(
        "failed after 30 seconds on /tmp/data/orders.xlsx"
    )
    assert "30" not in normalized
    assert "/tmp/data/orders.xlsx" not in normalized


def test_cluster_failures_groups_by_fingerprint():
    from backend.services.collection_failure_alert_service import CollectionFailure

    failures = [
        CollectionFailure(
            task_id="task-1",
            platform="shopee",
            account_id="shop-sg-1",
            domain="orders",
            error=STEP_ERROR,
            fingerprint=error_fingerprint(STEP_ERROR),
            category=CATEGORY_STEP_FAILURE,
        ),
        CollectionFailure(
            task_id="task-2",
            platform="shopee",
            account_id="shop-sg-2",
            domain="orders",
            error=STEP_ERROR,
            fingerprint=error_fingerprint(STEP_ERROR),
            category=CATEGORY_STEP_FAILURE,
        ),
    ]

    clusters = cluster_failures(failures)
    assert len(clusters) == 1
    assert len(clusters[0].failures) == 2
    assert clusters[0].shop_labels == ["sh***-1", "sh***-2"]


# ── 8. 通知失败不影响采集主流程 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_channel_failure_does_not_break_collection_and_retries_next_round(
    monkeypatch,
):
    """两条通道都失败 ⇒ 不抛异常、状态照常落库、**不记入已通知** ⇒ 下轮重试。"""
    calls = []
    _install_channels(monkeypatch, calls, in_app_ok=False, webhook_ok=False)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_run_failures(session, config_run_id=42)

    assert outcome.notified == []
    assert len(calls) == 2  # 两条通道都试过了
    # 采集主流程不受影响：运行日志照常写下来了
    assert session.inserted_context is not None
    assert session.inserted_context["notified_collection_failures"] == []

    # 下一轮：还没被记进「已通知」⇒ 重新试一次
    calls.clear()
    _install_channels(monkeypatch, calls)
    retry = await alert_collection_run_failures(session, config_run_id=43)
    assert len(retry.notified) == 1
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_dispatch_exception_is_swallowed(monkeypatch):
    """通道直接抛异常 ⇒ 告警不冒泡（采集主流程不能被通知拖垮）。"""
    calls = []

    async def _boom_in_app(*args, **kwargs):
        calls.append("in_app")
        raise RuntimeError("db down")

    async def _boom_webhook(*args, **kwargs):
        calls.append("webhook")
        raise RuntimeError("webhook down")

    monkeypatch.setattr(
        "backend.domains.platform.routers.notifications.create_notifications_for_admins",
        _boom_in_app,
    )
    monkeypatch.setattr(
        "backend.services.alert_service.send_resource_alert", _boom_webhook
    )

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_run_failures(session, config_run_id=42)

    assert outcome.notified == []
    assert calls == ["in_app", "webhook"]
    # 站内信写库失败 ⇒ 必须回滚，否则后面的写库跟着炸
    assert session.rollbacks >= 1


# ── 9. 快速采集（不属于配置轮次）的单任务失败 ──────────────────────────


@pytest.mark.asyncio
async def test_standalone_task_failure_is_alerted(monkeypatch):
    """不属于配置轮次的任务（快速采集）失败 ⇒ 也会告警。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    outcome = await alert_collection_task_failure(session, task_id="task-1")

    assert len(outcome.notified) == 1
    assert len(calls) == 2
    assert calls[0]["extra_data"]["round_key"] == "task:task-1"


@pytest.mark.asyncio
async def test_alert_type_is_isolated_per_fingerprint(monkeypatch):
    """webhook 的 alert_type **按错误指纹隔离** ⇒ 冷却不会误伤别的错误。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        ),
        _row(
            "task-2",
            "shop-sg-2",
            failed_domains=[
                {"domain": "products", "error": "TimeoutError: export failed"}
            ],
        ),
    ]
    session = _FakeSession(task_rows=rows)

    await alert_collection_run_failures(session, config_run_id=42)

    alert_types = [item["alert_type"] for item in calls if item["channel"] == "webhook"]
    assert len(alert_types) == 2
    assert len(set(alert_types)) == 2
    for alert_type in alert_types:
        assert alert_type.startswith(COLLECTION_FAILURE_ALERT_TYPE_PREFIX)


@pytest.mark.asyncio
async def test_state_is_written_to_existing_run_log_table(monkeypatch):
    """去重状态落在**既有的** ``ops.pipeline_run_log``（不加表不加迁移）。"""
    calls = []
    _install_channels(monkeypatch, calls)

    rows = [
        _row(
            "task-1",
            "shop-sg-1",
            failed_domains=[{"domain": "orders", "error": STEP_ERROR}],
        )
    ]
    session = _FakeSession(task_rows=rows)

    await alert_collection_run_failures(session, config_run_id=42)

    inserts = [
        (sql, params)
        for sql, params in session.statements
        if sql.lstrip().upper().startswith("INSERT")
    ]
    assert len(inserts) == 1
    sql, params = inserts[0]
    assert "ops.pipeline_run_log" in sql
    assert params["pipeline_name"] == PIPELINE_NAME
    assert params["status"] == "failed"
    assert params["run_id"].startswith(PIPELINE_NAME)
    assert session.inserted_context["round_key"] == "config_run:42"

"""数据新鲜度**分档** + 通知出口（批次 3.3）的守护测试。

覆盖六件事：
1. 「已停采的链」单独成档（``out_of_scope``），**不再**把整体红灯拉起来；
2. 「从未被采的链」仍然是 ``empty`` ⇒ ``skipped``（**既有行为不许被改**）；
3. 采集范围**从数据库读**（``core.collection_configs`` /
   ``core.collection_config_shop_scopes``）；
4. 数据库读不到时走**兜底**，且**结果里能看出用了兜底**；
5. 阈值口径**未被改动**（粒度默认 + 链级例外 + 环境变量覆盖各一例）；
6. 通知**去重**：连续两轮同一问题只发一次。
"""

import json
from datetime import date, datetime, timezone

import pytest

from backend.services.data_pipeline.source_freshness_notify import (
    SOURCE_FRESHNESS_ALERT_TYPE,
    build_alert_payload,
    mask_sensitive_text,
)
from backend.services.data_pipeline.source_freshness_scope import (
    SCOPE_SOURCE_DATABASE,
    SCOPE_SOURCE_FALLBACK,
    SCOPE_STATUS_OUT_OF_SCOPE,
    SCOPE_STATUS_UNKNOWN,
    CollectionScope,
)
from backend.services.data_pipeline.source_freshness_service import (
    GRANULARITY_MAX_AGE_DAYS,
    SOURCE_FRESHNESS_PIPELINE_NAME,
    SOURCE_FRESHNESS_STATUS_EMPTY,
    SOURCE_FRESHNESS_STATUS_FRESH,
    SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE,
    SOURCE_FRESHNESS_STATUS_STALE,
    classify_source_freshness,
    collect_source_freshness,
    max_age_days_for,
    record_source_freshness_run,
    resolve_scope_status,
    run_source_freshness_check,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

# 一条 shopee 生效配置：只采 products / analytics（services 已停采）。
SHOPEE_CONFIG_ROWS = [
    (10, "shopee", ["products", "analytics"], ["products", "analytics"], True),
]


class _FakeResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字返回预置结果，并记录执行过的语句。

    它还会**记住上一轮写进运行日志的 context** ⇒ 下一轮读「已通知过的链」时
    能拿到上一轮的结果 —— 这正是通知去重依赖的那份状态。
    """

    def __init__(
        self,
        *,
        discovered=(),
        ready=(),
        aggregate=(),
        scope_rows=(),
        scope_error=None,
    ):
        self._discovered = [(name,) for name in discovered]
        self._ready = [(name,) for name in ready]
        self._aggregate = list(aggregate)
        self._scope_rows = list(scope_rows)
        self._scope_error = scope_error
        self._previous_run_context = None
        self.statements = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        params = args[0] if args else kwargs
        self.statements.append((sql, params))
        stripped = sql.lstrip().upper()

        if "core.collection_configs" in sql:
            if self._scope_error is not None:
                raise self._scope_error
            return _FakeResult(self._scope_rows)
        if stripped.startswith("SELECT") and "ops.pipeline_run_log" in sql:
            rows = []
            if self._previous_run_context is not None:
                rows.append((self._previous_run_context,))
            return _FakeResult(rows)
        if "pg_class" in sql:
            return _FakeResult(self._discovered)
        if "information_schema.columns" in sql:
            return _FakeResult(self._ready)
        if stripped.startswith("INSERT") and "ops.pipeline_run_log" in sql:
            context = params.get("context") if isinstance(params, dict) else None
            if context:
                self._previous_run_context = json.loads(context)
        return _FakeResult(self._aggregate)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _scope(
    domains_by_platform=None, *, source=SCOPE_SOURCE_DATABASE, platform_known=True
):
    return CollectionScope(
        domains_by_platform={
            platform: frozenset(domains)
            for platform, domains in (domains_by_platform or {}).items()
        },
        source=source,
        detail="test scope",
        config_count=len(domains_by_platform or {}),
        shop_scope_count=0,
        platform_known=platform_known,
    )


# ── 1. 分档：已停采的链不再拉高红灯 ────────────────────────────────────


@pytest.mark.asyncio
async def test_stopped_collection_chain_is_tiered_out_of_scope():
    """曾采过、现已不在当前采集范围的链 ⇒ 单独一档，不进 partial_failed。"""
    session = _FakeSession(
        discovered=["fact_shopee_services_monthly"],
        ready=["fact_shopee_services_monthly"],
        aggregate=[
            (
                "fact_shopee_services_monthly",
                251,
                date(2026, 7, 1),
                datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc),
            )
        ],
        scope_rows=SHOPEE_CONFIG_ROWS,
    )

    report = await collect_source_freshness(session, now=NOW)

    row = report.rows[0]
    assert row.scope_status == SCOPE_STATUS_OUT_OF_SCOPE
    assert row.status == SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE
    # 「落后多少天」照样算出来（台账里看得见），但不算断流。
    assert row.business_age_days == 133
    # 关键：整体红灯不再被这条链拉起来。
    assert report.is_success is True
    assert report.stale_rows == []
    assert len(report.out_of_scope_rows) == 1
    assert report.to_error_message() is None

    await record_source_freshness_run(session, report)
    inserted = [
        params
        for sql, params in session.statements
        if sql.lstrip().upper().startswith("INSERT")
    ]
    run_params = next(
        p for p in inserted if p.get("pipeline_name") == SOURCE_FRESHNESS_PIPELINE_NAME
    )
    assert run_params["status"] == "success"

    step_params = next(
        p for p in inserted if p.get("step_name") == "check_source_freshness"
    )
    assert step_params["status"] == "skipped"
    assert "out_of_scope" in (step_params["error_message"] or "")


@pytest.mark.asyncio
async def test_in_scope_chain_still_turns_red_when_stale():
    """还在采集范围里的链 ⇒ 断流照旧报警（分档不能把真断流藏起来）。"""
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            (
                "fact_shopee_products_monthly",
                25809,
                date(2026, 7, 1),
                datetime(2026, 10, 13, 9, 15, tzinfo=timezone.utc),
            )
        ],
        scope_rows=SHOPEE_CONFIG_ROWS,
    )

    report = await collect_source_freshness(session, now=NOW)

    row = report.rows[0]
    assert row.scope_status == "in_scope"
    assert row.status == SOURCE_FRESHNESS_STATUS_STALE
    assert report.is_success is False
    assert "stale_source_chains" in (report.to_error_message() or "")


# ── 2. 既有行为：从没被采过的链仍是 skipped ────────────────────────────


@pytest.mark.asyncio
async def test_never_collected_chain_is_still_empty_and_skipped():
    """「从未被采」的表判 empty ⇒ skipped，**不进 partial_failed**（行为不许变）。"""
    session = _FakeSession(
        discovered=["fact_shopee_inventory_snapshot", "fact_shopee_products_monthly"],
        ready=["fact_shopee_inventory_snapshot", "fact_shopee_products_monthly"],
        aggregate=[
            ("fact_shopee_inventory_snapshot", 0, None, None),
            (
                "fact_shopee_products_monthly",
                25809,
                date(2026, 11, 1),
                datetime(2026, 11, 8, 4, 15, tzinfo=timezone.utc),
            ),
        ],
        scope_rows=SHOPEE_CONFIG_ROWS,
    )

    report = await collect_source_freshness(session, now=NOW)

    by_table = {row.table_name: row for row in report.rows}
    never_collected = by_table["fact_shopee_inventory_snapshot"]
    assert never_collected.status == SOURCE_FRESHNESS_STATUS_EMPTY
    assert never_collected.business_age_days is None
    # inventory 不在 shopee 的生效范围里 —— 但**空表优先**：仍然是 empty，不是 out_of_scope。
    assert never_collected.scope_status == SCOPE_STATUS_OUT_OF_SCOPE
    assert never_collected.status != SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE
    assert report.is_success is True

    await record_source_freshness_run(session, report)
    inserted = [
        params
        for sql, params in session.statements
        if sql.lstrip().upper().startswith("INSERT")
    ]
    step_params = [
        p for p in inserted if p.get("step_name") == "check_source_freshness"
    ]
    empty_step = next(
        p for p in step_params if p["target_name"] == "fact_shopee_inventory_snapshot"
    )
    assert empty_step["status"] == "skipped"
    assert "empty_source_table" in (empty_step["error_message"] or "")


def test_classify_keeps_empty_and_fresh_semantics_without_scope():
    """不传 scope_status 时，判定口径与改造前完全一致。"""
    assert classify_source_freshness(
        row_count=0,
        max_metric_date=None,
        now_date=date(2026, 11, 11),
        max_age_days=60,
    ) == ("empty", None)
    assert classify_source_freshness(
        row_count=10,
        max_metric_date=date(2026, 10, 1),
        now_date=date(2026, 11, 11),
        max_age_days=60,
    ) == ("fresh", 41)
    assert classify_source_freshness(
        row_count=10,
        max_metric_date=date(2026, 9, 1),
        now_date=date(2026, 11, 11),
        max_age_days=60,
    ) == ("stale", 71)


# ── 3./4. 采集范围：来自数据库；读不到才兜底 ───────────────────────────


@pytest.mark.asyncio
async def test_collection_scope_is_read_from_database():
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            (
                "fact_shopee_products_monthly",
                25809,
                date(2026, 11, 1),
                datetime(2026, 11, 8, 4, 15, tzinfo=timezone.utc),
            )
        ],
        scope_rows=SHOPEE_CONFIG_ROWS,
    )

    report = await collect_source_freshness(session, now=NOW)

    assert report.scope_source == SCOPE_SOURCE_DATABASE
    assert report.to_summary()["scope_source"] == SCOPE_SOURCE_DATABASE
    scope_sql = " ".join(
        sql for sql, _ in session.statements if "core.collection_configs" in sql
    )
    assert "core.collection_configs" in scope_sql
    assert "core.collection_config_shop_scopes" in scope_sql
    assert "is_active IS TRUE" in scope_sql


@pytest.mark.asyncio
async def test_collection_scope_falls_back_when_database_read_fails():
    """数据库读不到 ⇒ 走兜底，且**结果里能看出用了兜底**。"""
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            (
                "fact_shopee_products_monthly",
                25809,
                date(2026, 11, 1),
                datetime(2026, 11, 8, 4, 15, tzinfo=timezone.utc),
            )
        ],
        scope_error=RuntimeError("boom"),
    )

    report = await collect_source_freshness(session, now=NOW)

    assert report.scope_source == SCOPE_SOURCE_FALLBACK
    summary = report.to_summary()
    assert summary["scope_source"] == SCOPE_SOURCE_FALLBACK
    scope_detail = summary["scope_detail"] or ""
    assert "fallback" in scope_detail or "failed" in scope_detail
    # 兜底不能把巡检整体挂掉。
    assert report.rows and report.rows[0].status == SOURCE_FRESHNESS_STATUS_FRESH


@pytest.mark.asyncio
async def test_scope_without_any_active_config_cannot_tier_as_out_of_scope():
    """读到了表但没有任何生效配置 ⇒ 判不了，不许把告警整体静音。"""
    session = _FakeSession(
        discovered=["fact_shopee_services_monthly"],
        ready=["fact_shopee_services_monthly"],
        aggregate=[
            (
                "fact_shopee_services_monthly",
                251,
                date(2026, 7, 1),
                datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc),
            )
        ],
        scope_rows=[],
    )

    report = await collect_source_freshness(session, now=NOW)

    row = report.rows[0]
    assert row.scope_status == SCOPE_STATUS_UNKNOWN
    assert row.status == SOURCE_FRESHNESS_STATUS_STALE
    assert report.is_success is False


def test_resolve_scope_status_uses_order_source_provider_contract():
    """shopee/tiktok 的订单由 miaoshou 采集器提供 ⇒ 不能误判成「已停采」。"""
    from backend.services.data_pipeline.source_freshness_service import (
        SourceTableIdentity,
    )

    scope = _scope({"miaoshou": frozenset({"orders", "inventory"})})
    identity = SourceTableIdentity(
        table_name="fact_shopee_orders_monthly",
        platform="shopee",
        domain="orders",
        granularity="monthly",
    )
    assert resolve_scope_status(scope, identity) == "in_scope"


# ── 5. 阈值口径未被改动 ────────────────────────────────────────────────


def test_threshold_granularity_defaults_unchanged():
    assert GRANULARITY_MAX_AGE_DAYS["daily"] == 365
    assert GRANULARITY_MAX_AGE_DAYS["weekly"] == 365
    assert GRANULARITY_MAX_AGE_DAYS["monthly"] == 60
    assert GRANULARITY_MAX_AGE_DAYS["snapshot"] == 10
    assert max_age_days_for("daily") == 365
    assert max_age_days_for("weekly") == 365
    assert max_age_days_for("monthly") == 60
    assert max_age_days_for("snapshot") == 10


def test_threshold_chain_level_exception_unchanged():
    # 商品日粒度直接喂商品经营看板 ⇒ 单独收紧到 30 天。
    assert max_age_days_for("daily", "shopee/products[daily]") == 30
    assert max_age_days_for("daily", "tiktok/products[daily]") == 30
    assert max_age_days_for("daily", "shopee/orders[daily]") == 365


def test_threshold_env_override_unchanged(monkeypatch):
    monkeypatch.setenv("SOURCE_FRESHNESS_MAX_AGE_MONTHLY", "15")
    assert max_age_days_for("monthly") == 15

    monkeypatch.setenv(
        "SOURCE_FRESHNESS_MAX_AGE_CHAINS",
        json.dumps({"shopee/orders[daily]": 7}),
    )
    assert max_age_days_for("daily", "shopee/orders[daily]") == 7


@pytest.mark.asyncio
async def test_out_of_scope_chain_keeps_the_same_threshold_value():
    """分档只改「结论落在哪一档」，阈值数值一个都不动。"""
    session = _FakeSession(
        discovered=["fact_shopee_products_daily"],
        ready=["fact_shopee_products_daily"],
        aggregate=[
            (
                "fact_shopee_products_daily",
                1,
                date(2026, 6, 6),
                datetime(2026, 6, 9, 8, 45, tzinfo=timezone.utc),
            )
        ],
        # shopee 只采 products/analytics —— 这里让 products 不在范围内，链变 out_of_scope。
        scope_rows=[(10, "shopee", ["analytics"], ["analytics"], True)],
    )

    report = await collect_source_freshness(session, now=NOW)

    row = report.rows[0]
    assert row.status == SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE
    # 阈值仍是链级例外的 30 天（不是 365）。
    assert row.max_age_days == 30


# ── 6. 通知出口 + 去重 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notification_is_dispatched_only_once_for_the_same_problem(monkeypatch):
    """连续两轮同一问题 ⇒ 只发一次通知（第二轮读上一轮的已通知集合）。"""
    calls = []

    async def _fake_in_app(db, notification_type, title, content, **kwargs):
        calls.append({"channel": "in_app", "title": title, "content": content})
        return [object()]

    async def _fake_webhook(alert_type, message, *args, **kwargs):
        calls.append({"channel": "webhook", "alert_type": alert_type})
        return None

    monkeypatch.setattr(
        "backend.domains.platform.routers.notifications.create_notifications_for_admins",
        _fake_in_app,
    )
    monkeypatch.setattr(
        "backend.services.alert_service.send_resource_alert", _fake_webhook
    )

    def _session():
        return _FakeSession(
            discovered=["fact_shopee_products_monthly"],
            ready=["fact_shopee_products_monthly"],
            aggregate=[
                (
                    "fact_shopee_products_monthly",
                    25809,
                    date(2026, 7, 1),
                    datetime(2026, 10, 13, 9, 15, tzinfo=timezone.utc),
                )
            ],
            scope_rows=SHOPEE_CONFIG_ROWS,
        )

    session = _session()
    first = await run_source_freshness_check(session, trigger_source="scheduler")
    assert first.notified_stale_chains == ["shopee/products[monthly]"]
    assert len(calls) == 2  # 站内信 + webhook 各一次
    assert calls[0]["channel"] == "in_app"
    assert calls[1]["alert_type"] == SOURCE_FRESHNESS_ALERT_TYPE

    calls.clear()
    second = await run_source_freshness_check(session, trigger_source="scheduler")
    assert second.notified_stale_chains == ["shopee/products[monthly]"]
    assert calls == []  # 同一问题第二轮不再通知


@pytest.mark.asyncio
async def test_out_of_scope_chain_is_not_notified(monkeypatch):
    """已停采的链不通知（它不是「本轮新出现的问题」）。"""
    calls = []

    async def _fake_in_app(db, notification_type, title, content, **kwargs):
        calls.append(title)
        return [object()]

    async def _fake_webhook(alert_type, message, *args, **kwargs):
        calls.append(alert_type)
        return None

    monkeypatch.setattr(
        "backend.domains.platform.routers.notifications.create_notifications_for_admins",
        _fake_in_app,
    )
    monkeypatch.setattr(
        "backend.services.alert_service.send_resource_alert", _fake_webhook
    )

    session = _FakeSession(
        discovered=["fact_shopee_services_monthly"],
        ready=["fact_shopee_services_monthly"],
        aggregate=[
            (
                "fact_shopee_services_monthly",
                251,
                date(2026, 7, 1),
                datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc),
            )
        ],
        scope_rows=SHOPEE_CONFIG_ROWS,
    )

    report = await run_source_freshness_check(session, trigger_source="scheduler")
    assert report.rows[0].status == SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE
    assert calls == []
    assert report.notified_stale_chains == []


@pytest.mark.asyncio
async def test_recovered_chain_is_notified_again_when_it_breaks_again(monkeypatch):
    """链恢复后再次断流 ⇒ 重新通知（去重不是「一辈子只发一次」）。"""
    calls = []

    async def _fake_in_app(db, notification_type, title, content, **kwargs):
        calls.append(title)
        return [object()]

    async def _fake_webhook(alert_type, message, *args, **kwargs):
        return None

    monkeypatch.setattr(
        "backend.domains.platform.routers.notifications.create_notifications_for_admins",
        _fake_in_app,
    )
    monkeypatch.setattr(
        "backend.services.alert_service.send_resource_alert", _fake_webhook
    )

    session = _FakeSession(
        discovered=["fact_shopee_products_monthly"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            (
                "fact_shopee_products_monthly",
                25809,
                date(2026, 7, 1),
                datetime(2026, 10, 13, 9, 15, tzinfo=timezone.utc),
            )
        ],
        scope_rows=SHOPEE_CONFIG_ROWS,
    )

    await run_source_freshness_check(session, trigger_source="scheduler")
    assert len(calls) == 1

    # 第二轮：链恢复了（变新鲜）⇒ 不该再通知，已通知集合清空。
    session._aggregate = [
        (
            "fact_shopee_products_monthly",
            25809,
            date(2026, 11, 10),
            datetime(2026, 11, 11, 4, 15, tzinfo=timezone.utc),
        )
    ]
    calls.clear()
    await run_source_freshness_check(session, trigger_source="scheduler")
    assert calls == []

    # 第三轮：又断了 ⇒ 重新通知。
    session._aggregate = [
        (
            "fact_shopee_products_monthly",
            25809,
            date(2026, 7, 1),
            datetime(2026, 10, 13, 9, 15, tzinfo=timezone.utc),
        )
    ]
    calls.clear()
    await run_source_freshness_check(session, trigger_source="scheduler")
    assert len(calls) == 1


def test_notification_payload_is_masked():
    """通知内容脱敏：连接串口令 / token 一律不进通知。"""
    masked = mask_sensitive_text(
        "连接串 postgresql://erp_user:sup3rsecret@localhost:15432/xihong_erp "
        "password=hunter2 token=abcdef"
    )
    assert "sup3rsecret" not in masked
    assert "hunter2" not in masked
    assert "abcdef" not in masked
    assert "***" in masked


def test_alert_payload_contains_only_safe_fields():
    """载荷里只有链名/表名/天数/上限/run_id —— 没有原始数据。"""
    report = type(
        "_Report",
        (),
        {
            "run_id": "source_freshness_test",
            "pipeline_name": "source_freshness_check",
            "stale_rows": [],
        },
    )()
    payload = build_alert_payload(report, [])
    assert payload["run_id"] == "source_freshness_test"
    assert payload["chains"] == []
    assert "raw_data" not in json.dumps(payload)

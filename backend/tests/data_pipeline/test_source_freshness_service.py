"""源数据新鲜度巡检的单元测试。

覆盖三件事：
1. 表名 → 平台/业务域/粒度的解析（决定每条链用哪套滞后阈值）
2. 新鲜/断流/空表的判定口径
3. 巡检结论落库时写进 ops 监控表的内容
"""

import asyncio
import json
import os
from datetime import date, datetime, timezone

from backend.services.data_pipeline.source_freshness_service import (
    GRANULARITY_MAX_AGE_DAYS,
    SOURCE_FRESHNESS_PIPELINE_NAME,
    classify_source_freshness,
    collect_source_freshness,
    max_age_days_for,
    parse_source_table_name,
    record_source_freshness_run,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """按 SQL 关键字返回预置结果，并记录执行过的语句。"""

    def __init__(self, discovered=(), ready=(), aggregate=()):
        self._discovered = [(name,) for name in discovered]
        self._ready = [(name,) for name in ready]
        self._aggregate = list(aggregate)
        self.statements = []
        self.committed = False

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        self.statements.append((sql, args[0] if args else kwargs))
        if "pg_class" in sql:
            return _FakeResult(self._discovered)
        if "information_schema.columns" in sql:
            return _FakeResult(self._ready)
        return _FakeResult(self._aggregate)

    async def commit(self):
        self.committed = True


def test_parse_source_table_name_extracts_platform_domain_and_granularity():
    identity = parse_source_table_name("fact_shopee_products_monthly")
    assert identity.platform == "shopee"
    assert identity.domain == "products"
    assert identity.granularity == "monthly"
    assert identity.subdomain is None


def test_parse_source_table_name_keeps_subdomain():
    identity = parse_source_table_name("fact_shopee_services_ai_assistant_daily")
    assert identity.platform == "shopee"
    assert identity.domain == "services"
    assert identity.subdomain == "ai_assistant"
    assert identity.granularity == "daily"


def test_parse_source_table_name_handles_platform_scoped_subdomain():
    identity = parse_source_table_name("fact_miaoshou_orders_shopee_monthly")
    assert identity.platform == "miaoshou"
    assert identity.domain == "orders"
    assert identity.subdomain == "shopee"
    assert identity.granularity == "monthly"


def test_parse_source_table_name_ignores_non_fact_table():
    identity = parse_source_table_name("dim_shops")
    assert identity.platform is None
    assert identity.domain is None
    assert identity.granularity is None


def test_max_age_days_for_uses_granularity_defaults():
    assert max_age_days_for("daily") == GRANULARITY_MAX_AGE_DAYS["daily"]
    assert max_age_days_for("weekly") == GRANULARITY_MAX_AGE_DAYS["weekly"]
    assert max_age_days_for("monthly") == GRANULARITY_MAX_AGE_DAYS["monthly"]
    assert max_age_days_for("snapshot") == GRANULARITY_MAX_AGE_DAYS["snapshot"]


def test_max_age_days_for_allows_env_override(monkeypatch):
    monkeypatch.setenv("SOURCE_FRESHNESS_MAX_AGE_MONTHLY", "15")
    try:
        assert max_age_days_for("monthly") == 15
    finally:
        os.environ.pop("SOURCE_FRESHNESS_MAX_AGE_MONTHLY", None)


def test_max_age_days_for_prefers_chain_level_override():
    # 商品日粒度直接喂 product_day_kpi，必须比普通日链更严。
    assert max_age_days_for("daily", "shopee/products[daily]") == 30
    # 普通日/周链是按需采集，给宽限，避免噪音淹没真断流。
    assert max_age_days_for("daily", "shopee/orders[daily]") == 365


def test_max_age_days_for_allows_env_chain_override(monkeypatch):
    monkeypatch.setenv(
        "SOURCE_FRESHNESS_MAX_AGE_CHAINS",
        json.dumps({"shopee/orders[daily]": 7}),
    )
    try:
        assert max_age_days_for("daily", "shopee/orders[daily]") == 7
    finally:
        os.environ.pop("SOURCE_FRESHNESS_MAX_AGE_CHAINS", None)


def test_classify_marks_empty_table():
    status, age = classify_source_freshness(
        row_count=0,
        max_metric_date=None,
        now_date=date(2026, 11, 5),
        max_age_days=60,
    )
    assert status == "empty"
    assert age is None


def test_classify_marks_recent_data_as_fresh():
    status, age = classify_source_freshness(
        row_count=10,
        max_metric_date=date(2026, 10, 1),
        now_date=date(2026, 11, 5),
        max_age_days=60,
    )
    assert status == "fresh"
    assert age == 35


def test_classify_marks_old_data_as_stale():
    status, age = classify_source_freshness(
        row_count=10,
        max_metric_date=date(2026, 9, 1),
        now_date=date(2026, 11, 5),
        max_age_days=60,
    )
    assert status == "stale"
    assert age == 65


def test_collect_source_freshness_reports_stale_chain():
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly", "fact_shopee_orders_monthly"],
        ready=["fact_shopee_products_monthly", "fact_shopee_orders_monthly"],
        aggregate=[
            (
                "fact_shopee_orders_monthly",
                4384,
                date(2026, 10, 1),
                datetime(2026, 11, 3, 14, 15, tzinfo=timezone.utc),
            ),
            (
                "fact_shopee_products_monthly",
                31173,
                date(2026, 9, 1),
                datetime(2026, 10, 19, 4, 45, tzinfo=timezone.utc),
            ),
        ],
    )
    report = asyncio.run(
        collect_source_freshness(
            session,
            now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
    )

    by_table = {row.table_name: row for row in report.rows}
    assert by_table["fact_shopee_orders_monthly"].status == "fresh"
    assert by_table["fact_shopee_products_monthly"].status == "stale"
    assert by_table["fact_shopee_products_monthly"].business_age_days == 65
    assert report.is_success is False
    assert "shopee/products[monthly]" in (report.to_error_message() or "")


def test_collect_source_freshness_keeps_on_demand_chains_out_of_alarm():
    """按需采集的日链不进告警集；商品日链必须进（它直接喂商品看板）。"""
    session = _FakeSession(
        discovered=[
            "fact_shopee_orders_daily",
            "fact_shopee_products_daily",
        ],
        ready=["fact_shopee_orders_daily", "fact_shopee_products_daily"],
        aggregate=[
            ("fact_shopee_orders_daily", 336, date(2026, 6, 18), None),
            ("fact_shopee_products_daily", 316, date(2026, 8, 23), None),
        ],
    )
    report = asyncio.run(
        collect_source_freshness(
            session,
            now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
    )
    by_table = {row.table_name: row for row in report.rows}
    assert by_table["fact_shopee_orders_daily"].status == "fresh"
    assert by_table["fact_shopee_products_daily"].status == "stale"
    assert by_table["fact_shopee_products_daily"].max_age_days == 30


def test_record_source_freshness_run_writes_valid_json_payloads():
    """context / details 必须能被 PostgreSQL 的 jsonb 解析（单引号 repr 是不行的）。"""
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            (
                "fact_shopee_products_monthly",
                31173,
                date(2026, 9, 1),
                datetime(2026, 10, 19, 4, 45, tzinfo=timezone.utc),
            ),
        ],
    )
    report = asyncio.run(
        collect_source_freshness(
            session,
            now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
    )
    asyncio.run(record_source_freshness_run(session, report))

    inserted = [
        params
        for sql, params in session.statements
        if sql.lstrip().upper().startswith("INSERT")
    ]
    payloads = [
        params[key]
        for params in inserted
        for key in ("context", "details")
        if params.get(key)
    ]
    assert payloads
    for payload in payloads:
        json.loads(payload)  # 解析失败说明写进 jsonb 会被数据库拒


def test_collect_source_freshness_skips_tables_without_metric_columns():
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly", "fact_shopee_broken"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            ("fact_shopee_products_monthly", 10, date(2026, 10, 1), None),
        ],
    )
    report = asyncio.run(
        collect_source_freshness(
            session,
            now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
    )
    assert [row.table_name for row in report.rows] == ["fact_shopee_products_monthly"]


def test_record_source_freshness_run_writes_pipeline_and_step_logs():
    session = _FakeSession(
        discovered=["fact_shopee_products_monthly"],
        ready=["fact_shopee_products_monthly"],
        aggregate=[
            (
                "fact_shopee_products_monthly",
                31173,
                date(2026, 9, 1),
                datetime(2026, 10, 19, 4, 45, tzinfo=timezone.utc),
            ),
        ],
    )
    report = asyncio.run(
        collect_source_freshness(
            session,
            now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
    )
    asyncio.run(record_source_freshness_run(session, report))

    inserted = [
        params
        for sql, params in session.statements
        if sql.lstrip().upper().startswith("INSERT")
    ]
    run_params = next(
        p for p in inserted if p.get("pipeline_name") == SOURCE_FRESHNESS_PIPELINE_NAME
    )
    assert run_params["status"] == "partial_failed"
    assert "stale_source_chains" in (run_params["error_message"] or "")

    step_params = next(
        p for p in inserted if p.get("step_name") == "check_source_freshness"
    )
    assert step_params["target_name"] == "fact_shopee_products_monthly"
    assert step_params["status"] == "failed"
    assert session.committed is True

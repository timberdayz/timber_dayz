"""语义层就绪状态位 + 订单域来源治理（语义层 SSOT 改造 · 阶段 6）的单元测试。

覆盖三件事：
1. 状态判定口径：``fresh`` / ``updating`` / ``stale`` / ``unknown``；
2. 采集侧来源治理：shopee 采集配置不含 orders 域 => 提示
   「shopee 订单需由 miaoshou 采集器提供」；
3. 看板路由把状态位挂进 ``meta.semantic_readiness``（**新增**字段，
   既有 ``meta.data_status`` 语义不变）。
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.collection_contracts import (
    build_missing_order_source_note,
    build_order_source_note,
    get_order_source_provider,
)
from backend.services.data_pipeline.order_source_governance import (
    audit_collection_config_order_sources,
    collect_collection_order_source_audit,
)
from backend.services.data_pipeline.semantic_readiness_service import (
    ORDER_SOURCE_TABLES_BY_GRANULARITY,
    SEMANTIC_READINESS_FRESH,
    SEMANTIC_READINESS_STALE,
    SEMANTIC_READINESS_UNKNOWN,
    SEMANTIC_READINESS_UPDATING,
    classify_semantic_readiness,
    collect_semantic_readiness,
)

NOW = datetime(2026, 11, 8, 12, 40, tzinfo=timezone.utc)


class _FakeResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字返回预置结果的假 session。"""

    def __init__(self, *, existing_tables=(), aggregate=(), semantic_ready=()):
        self._existing_tables = [(name,) for name in existing_tables]
        self._aggregate = list(aggregate)
        self._semantic_ready = list(semantic_ready)
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        params = args[0] if args else kwargs
        self.statements.append((sql, params))
        if "information_schema.tables" in sql:
            return _FakeResult(self._existing_tables)
        if "ops.data_freshness_log" in sql:
            return _FakeResult(self._semantic_ready)
        return _FakeResult(self._aggregate)


# ── 1. 状态判定 ───────────────────────────────────────────────────────


def test_classify_reports_fresh_when_semantic_layer_includes_latest_ingest():
    status, reason = classify_semantic_readiness(
        last_ingest_at=NOW - timedelta(seconds=60),
        last_semantic_ready_at=NOW - timedelta(seconds=30),
        now=NOW,
    )
    assert status == SEMANTIC_READINESS_FRESH
    assert reason == "semantic_layer_includes_latest_ingest"


def test_classify_reports_updating_when_ingest_is_newer_than_semantic_ready():
    status, reason = classify_semantic_readiness(
        last_ingest_at=NOW - timedelta(seconds=70),
        last_semantic_ready_at=NOW - timedelta(minutes=5),
        now=NOW,
    )
    assert status == SEMANTIC_READINESS_UPDATING
    assert reason == "semantic_layer_pending_after_ingest"


def test_classify_reports_stale_when_semantic_layer_pending_too_long():
    status, reason = classify_semantic_readiness(
        last_ingest_at=NOW - timedelta(hours=3),
        last_semantic_ready_at=NOW - timedelta(days=1),
        now=NOW,
    )
    assert status == SEMANTIC_READINESS_STALE
    assert reason == "semantic_layer_pending_too_long"


def test_classify_reports_stale_when_source_data_exceeds_freshness_threshold():
    status, reason = classify_semantic_readiness(
        last_ingest_at=NOW - timedelta(seconds=30),
        last_semantic_ready_at=NOW - timedelta(seconds=10),
        now=NOW,
        source_status="stale",
    )
    assert status == SEMANTIC_READINESS_STALE
    assert reason == "source_data_exceeds_freshness_threshold"


def test_classify_reports_unknown_without_ingest_and_semantic_ready():
    status, reason = classify_semantic_readiness(
        last_ingest_at=None,
        last_semantic_ready_at=None,
        now=NOW,
    )
    assert status == SEMANTIC_READINESS_UNKNOWN
    assert reason == "no_ingest_and_no_semantic_ready"


def test_classify_reports_fresh_when_only_semantic_ready_recorded():
    status, reason = classify_semantic_readiness(
        last_ingest_at=None,
        last_semantic_ready_at=NOW - timedelta(hours=1),
        now=NOW,
    )
    assert status == SEMANTIC_READINESS_FRESH
    assert reason == "semantic_ready_without_pending_ingest"


# ── 2. 采集（SQL 口径）────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_reports_fresh_when_semantic_ready_after_ingest():
    session = _FakeSession(
        existing_tables=ORDER_SOURCE_TABLES_BY_GRANULARITY["monthly"],
        aggregate=[(629, NOW.date(), NOW - timedelta(seconds=70))],
        semantic_ready=[(NOW - timedelta(seconds=40),)],
    )
    result = await collect_semantic_readiness(session, granularity="monthly", now=NOW)
    assert result["status"] == SEMANTIC_READINESS_FRESH
    assert result["last_ingest_at"] == (NOW - timedelta(seconds=70)).isoformat()
    assert result["last_semantic_ready_at"] == (NOW - timedelta(seconds=40)).isoformat()
    assert result["row_count"] == 629
    assert result["pending_seconds"] is None


@pytest.mark.asyncio
async def test_collect_reports_updating_when_semantic_layer_lags_behind_ingest():
    session = _FakeSession(
        existing_tables=ORDER_SOURCE_TABLES_BY_GRANULARITY["monthly"],
        aggregate=[(629, NOW.date(), NOW - timedelta(seconds=70))],
        semantic_ready=[(NOW - timedelta(minutes=5),)],
    )
    result = await collect_semantic_readiness(session, granularity="monthly", now=NOW)
    assert result["status"] == SEMANTIC_READINESS_UPDATING
    assert result["pending_seconds"] == 70
    assert result["semantic_targets"] == ["semantic.fact_orders_monthly_atomic_mv"]


@pytest.mark.asyncio
async def test_collect_reports_stale_when_source_data_is_too_old():
    session = _FakeSession(
        existing_tables=ORDER_SOURCE_TABLES_BY_GRANULARITY["monthly"],
        aggregate=[
            (
                10,
                (NOW - timedelta(days=120)).date(),
                NOW - timedelta(days=120),
            )
        ],
        semantic_ready=[(NOW - timedelta(days=121),)],
    )
    result = await collect_semantic_readiness(session, granularity="monthly", now=NOW)
    assert result["status"] == SEMANTIC_READINESS_STALE
    assert result["reason"] == "source_data_exceeds_freshness_threshold"
    assert result["business_age_days"] == 120


@pytest.mark.asyncio
async def test_collect_skips_missing_source_tables():
    session = _FakeSession(
        existing_tables=["fact_shopee_orders_monthly"],
        aggregate=[(1, NOW.date(), NOW - timedelta(seconds=5))],
        semantic_ready=[(NOW - timedelta(seconds=1),)],
    )
    result = await collect_semantic_readiness(session, granularity="monthly", now=NOW)
    assert result["source_tables"] == ["fact_shopee_orders_monthly"]
    assert result["status"] == SEMANTIC_READINESS_FRESH


@pytest.mark.asyncio
async def test_collect_filters_source_tables_by_platform():
    session = _FakeSession(
        existing_tables=ORDER_SOURCE_TABLES_BY_GRANULARITY["monthly"],
        aggregate=[(1, NOW.date(), NOW - timedelta(seconds=5))],
        semantic_ready=[(NOW - timedelta(seconds=1),)],
    )
    result = await collect_semantic_readiness(
        session, granularity="monthly", platform="shopee", now=NOW
    )
    assert result["source_tables"] == ["fact_shopee_orders_monthly"]
    sql_text = " ".join(statement for statement, _ in session.statements)
    assert "platform_code = :platform_code" in sql_text


# ── 3. 订单域来源治理（6.1）──────────────────────────────────────────


def test_order_source_provider_is_miaoshou_for_shopee_and_tiktok():
    assert get_order_source_provider("shopee") == "miaoshou"
    assert get_order_source_provider("TikTok") == "miaoshou"
    assert get_order_source_provider("miaoshou") is None
    assert build_order_source_note("shopee") == "shopee 订单由 miaoshou 采集器提供"
    assert (
        build_missing_order_source_note("tiktok")
        == "tiktok 订单需由 miaoshou 采集器提供"
    )


def test_audit_warns_when_shopee_config_has_no_orders_domain():
    report = audit_collection_config_order_sources(
        [
            {
                "id": 7,
                "name": "shopee 月采集",
                "platform": "shopee",
                "data_domains": ["products", "analytics"],
                "is_active": True,
            }
        ]
    )
    assert report.checked_config_count == 1
    assert report.warning_count == 1
    warning = report.items[0].warning
    assert warning == "shopee 订单需由 miaoshou 采集器提供"
    assert report.items[0].reason == "orders_domain_provided_by_other_collector"
    assert report.notes["shopee"] == "shopee 订单由 miaoshou 采集器提供"


def test_audit_flags_duplicate_orders_domain():
    report = audit_collection_config_order_sources(
        [
            {
                "id": 8,
                "name": "shopee 全域采集",
                "platform": "shopee",
                "data_domains": ["orders", "products"],
                "is_active": True,
            }
        ]
    )
    assert report.warning_count == 1
    assert report.items[0].reason == "duplicate_orders_domain"
    assert "miaoshou" in report.items[0].warning


def test_audit_ignores_inactive_configs_and_other_platforms():
    report = audit_collection_config_order_sources(
        [
            {
                "id": 9,
                "name": "已停用的 shopee 配置",
                "platform": "shopee",
                "data_domains": ["products"],
                "is_active": False,
            },
            {
                "id": 10,
                "name": "miaoshou 采集",
                "platform": "miaoshou",
                "data_domains": ["orders"],
                "is_active": True,
            },
        ]
    )
    assert report.items == []
    assert report.checked_config_count == 0


def test_audit_handles_json_text_domains_from_raw_sql():
    # asyncpg 默认把 JSON 列当字符串返回 —— 采集配置读出来就是这种形态。
    report = audit_collection_config_order_sources(
        [
            {
                "id": 12,
                "name": "shopee 日采集",
                "platform": "shopee",
                "data_domains": '["products", "analytics"]',
                "is_active": True,
            }
        ]
    )
    assert report.warning_count == 1
    assert report.items[0].warning == "shopee 订单需由 miaoshou 采集器提供"
    assert report.items[0].data_domains == ["products", "analytics"]


def test_audit_handles_json_text_domains_with_orders():
    report = audit_collection_config_order_sources(
        [
            {
                "id": 13,
                "name": "shopee 全域采集",
                "platform": "shopee",
                "data_domains": '["orders"]',
                "is_active": True,
            }
        ]
    )
    assert report.items[0].reason == "duplicate_orders_domain"


@pytest.mark.asyncio
async def test_collect_audit_reads_active_configs_from_db():
    session = _FakeSession()
    session.execute = _make_config_execute(
        [
            (7, "shopee 月采集", "shopee", ["products"], True),
            (11, "miaoshou 采集", "miaoshou", ["orders"], True),
        ]
    )
    report = await collect_collection_order_source_audit(session)
    assert report.checked_config_count == 1
    assert report.items[0].warning == "shopee 订单需由 miaoshou 采集器提供"


def _make_config_execute(rows):
    async def _execute(statement, *args, **kwargs):
        sql = str(statement)
        assert "core.collection_configs" in sql
        return _FakeResult(rows)

    return _execute


@pytest.mark.asyncio
async def test_collection_endpoint_returns_order_source_audit():
    from backend.domains.collection.routers.collection_config import (
        get_collection_config_order_source,
    )

    session = _FakeSession()
    session.execute = _make_config_execute(
        [
            (7, "shopee 月采集", "shopee", ["products"], True),
            (11, "miaoshou 采集", "miaoshou", ["orders"], True),
        ]
    )
    payload = await get_collection_config_order_source(platform=None, db=session)
    assert payload.summary.warning_count == 1
    assert payload.warnings[0].warning == "shopee 订单需由 miaoshou 采集器提供"
    assert payload.summary.source_notes["shopee"] == "shopee 订单由 miaoshou 采集器提供"


def test_collection_order_source_route_is_registered():
    from backend.domains.collection.routers.collection_config import router

    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/config-order-source" in paths


def test_data_pipeline_semantic_readiness_route_is_registered():
    from backend.domains.data_platform.routers.data_pipeline import router

    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/api/data-pipeline/semantic-readiness" in paths


# ── 4. 看板路由把状态位挂进 meta（新增字段）─────────────────────────


@pytest.mark.asyncio
async def test_router_attaches_semantic_readiness_to_meta(monkeypatch):
    from backend.domains.business.routers import dashboard_api_postgresql as router

    class _ServiceStub:
        async def get_business_overview_semantic_readiness(self, **_kwargs):
            return {
                "status": "updating",
                "reason": "semantic_layer_pending_after_ingest",
                "last_ingest_at": "2026-11-08T12:39:00+00:00",
                "last_semantic_ready_at": None,
            }

    monkeypatch.setattr(
        router, "get_postgresql_dashboard_service", lambda: _ServiceStub()
    )

    meta = {"warnings": [], "data_status": "ok"}
    await router._try_attach_business_overview_semantic_readiness(
        meta, platform_code=None, shop_id=None, granularity="monthly"
    )

    assert meta["semantic_readiness"]["status"] == "updating"
    assert "semantic_readiness_updating" in meta["warnings"]
    # 既有字段语义不变：data_status 仍然是「ok」，没有被改成 fresh/updating。
    assert meta["data_status"] == "ok"


@pytest.mark.asyncio
async def test_router_keeps_meta_when_readiness_query_fails(monkeypatch):
    from backend.domains.business.routers import dashboard_api_postgresql as router

    class _BrokenService:
        async def get_business_overview_semantic_readiness(self, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        router, "get_postgresql_dashboard_service", lambda: _BrokenService()
    )

    meta = {"warnings": [], "data_status": "ok"}
    await router._try_attach_business_overview_semantic_readiness(
        meta, platform_code=None, shop_id=None, granularity="monthly"
    )

    assert "semantic_readiness" not in meta
    assert meta["data_status"] == "ok"

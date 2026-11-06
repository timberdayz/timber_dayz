import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from starlette.requests import Request

from backend.routers import dashboard_api_postgresql as dashboard_router
from backend.domains.business.routers.dashboard_api_postgresql import (
    get_business_overview_bootstrap_postgresql,
    get_business_overview_comparison_postgresql,
    get_business_overview_kpi_postgresql,
    get_business_overview_traffic_ranking_postgresql,
)


def _make_request(path: str = "/api/dashboard/test"):
    app = SimpleNamespace(
        state=SimpleNamespace(
            dashboard_assets_report={
                "modules": {
                    "business_overview": {
                        "status": "ready",
                        "ready": True,
                    }
                }
            }
        )
    )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


class _PostgresqlServiceStub:
    def __init__(self, payload):
        self.payload = payload

    async def get_business_overview_kpi(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_comparison(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_operational_metrics(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_traffic_ranking(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_shop_racing(self, *args, **kwargs):
        return self.payload

    async def get_business_overview_identity_health(self, *args, **kwargs):
        return {
            "status": "warning",
            "warning_count": 1,
            "warnings": [
                {
                    "warning_code": "traffic_without_order_match_due_to_identity",
                    "platform_code": "shopee",
                    "shop_id": "1308200832",
                    "shop_account_id": "shopee_sg_xhkj33_local",
                    "order_count": Decimal("1"),
                    "visitor_count": Decimal("200"),
                }
            ],
        }


def _patch_dashboard_service(monkeypatch, service):
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: service,
    )


def test_postgresql_dashboard_router_exposes_expected_contract_paths():
    paths = {route.path for route in dashboard_router.router.routes}
    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/dashboard/business-overview/comparison" in paths
    assert "/api/dashboard/business-overview/bootstrap" in paths


def test_business_overview_kpi_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/kpi")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            {
                "gmv": 100,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5.0,
                "avg_order_value": 10.0,
                "attach_rate": 1.2,
                "labor_efficiency": 50.0,
            }
        ),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=request,
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert "meta" in body
    assert body["meta"]["period_key"] == "2026-03-01"
    assert body["meta"]["granularity"] == "monthly"
    assert body["meta"].get("platform_code") in (None, "")
    data = body["data"]
    assert body["success"] is True
    assert {
        "gmv",
        "order_count",
        "visitor_count",
        "conversion_rate",
        "avg_order_value",
        "attach_rate",
        "labor_efficiency",
    }.issubset(data.keys())


def test_business_overview_comparison_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/comparison")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            {
                "metrics": {
                    "sales_amount": {
                        "today": 100,
                        "yesterday": 90,
                        "average": 95,
                        "change": 11.11,
                    }
                },
                "target": {
                    "sales_amount": 120,
                    "achievement_rate": 83.33,
                },
            }
        ),
    )

    response = asyncio.run(
        get_business_overview_comparison_postgresql(
            request=request,
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert "meta" in body
    assert body["meta"]["period_key"] == "2026-03-01"
    assert body["meta"]["granularity"] == "monthly"
    data = body["data"]
    assert body["success"] is True
    assert "metrics" in data
    assert "target" in data
    assert "sales_amount" in data["metrics"]


def test_business_overview_bootstrap_contract_shape(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/bootstrap")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            {
                "any": "payload",
            }
        ),
    )

    response = asyncio.run(
        get_business_overview_bootstrap_postgresql(
            request=request,
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert "meta" in body
    assert body["meta"]["granularity"] == "monthly"
    assert body["meta"]["period_key"] == "2026-03-01"
    data = body["data"]
    assert body["success"] is True
    assert {
        "kpi",
        "comparison",
        "operational_metrics",
        "traffic_ranking",
        "shop_racing",
    }.issubset(data.keys())


def test_business_overview_traffic_ranking_meta_includes_identity_health(monkeypatch):
    request = _make_request("/api/dashboard/business-overview/traffic-ranking")
    _patch_dashboard_service(
        monkeypatch,
        _PostgresqlServiceStub(
            [
                {
                    "platform_code": "shopee",
                    "shop_id": "1308200832",
                    "visitor_count": 200,
                    "page_views": 400,
                    "uv_conversion_rate": None,
                    "pv_conversion_rate": None,
                }
            ]
        ),
    )

    response = asyncio.run(
        get_business_overview_traffic_ranking_postgresql(
            request=request,
            granularity="monthly",
            dimension="visitor",
            period_key="2026-06-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["meta"]["identity_health"]["status"] == "warning"
    assert body["meta"]["identity_health"]["warning_count"] == 1
    assert (
        body["meta"]["identity_health"]["warnings"][0]["warning_code"]
        == "traffic_without_order_match_due_to_identity"
    )
    assert body["meta"]["identity_health"]["warnings"][0]["visitor_count"] == 200


# ---------------------------------------------------------------------------
# P2-3: unknown 按原因拆开
#
# 为什么
# ----
# 三类原因混在一个 ``warning_count`` 里会让排查方向跑偏 —— 实测 738 行 unknown 里
# 93% 是 unmatched(TikTok 改名没留曾用名别名), 只有 7% 是 ambiguous, 而 conflict
# 又是另一回事(同一个账号出现多个 shop_id)。三者的处置完全不同。
# ---------------------------------------------------------------------------


def _identity_health_service(
    rows,
    discovery_count_rows=None,
    discovery_detail_rows=None,
):
    from backend.services.postgresql_dashboard_service import (
        PostgresqlDashboardService,
    )

    service = PostgresqlDashboardService()

    async def _fake_fetch_rows(query, params):
        # 身份健康度会发两类查询: 语义层告警 + 采集期探测异常。
        # 按查询内容分流, 免得假实现把两类数据混在一起。
        if "platform_shop_discoveries" not in query:
            return list(rows)
        if "AS issue_count" in query:
            return list(discovery_count_rows or [])
        return list(discovery_detail_rows or [])

    service._fetch_rows = _fake_fetch_rows
    return service


def test_identity_health_splits_unknown_by_reason():
    """按 unmatched / ambiguous / conflict 分组, 各自给 UV / PV / 订单数。"""
    rows = [
        {
            "warning_code": "unmatched_shop_label",
            "platform_code": "tiktok",
            "shop_id": "unknown",
            "shop_account_id": None,
            "order_count": None,
            "visitor_count": Decimal("100"),
            "page_views": Decimal("200"),
        },
        {
            "warning_code": "ambiguous_shop_label",
            "platform_code": "shopee",
            "shop_id": "unknown",
            "shop_account_id": None,
            "order_count": None,
            "visitor_count": Decimal("7"),
            "page_views": Decimal("9"),
        },
        {
            "warning_code": "identity_conflict",
            "platform_code": "shopee",
            "shop_id": "1308200832",
            "shop_account_id": "sa-1",
            "order_count": None,
            "visitor_count": None,
            "page_views": None,
        },
        {
            "warning_code": "traffic_without_order_match_due_to_identity",
            "platform_code": "shopee",
            "shop_id": "1308200825",
            "shop_account_id": "sa-2",
            "order_count": Decimal("3"),
            "visitor_count": Decimal("5"),
            "page_views": None,
        },
    ]

    service = _identity_health_service(rows)
    result = asyncio.run(
        service.get_business_overview_identity_health("monthly", "2026-06-01")
    )

    assert result["warning_count"] == 4
    breakdown = result["warning_breakdown"]
    assert breakdown["unmatched"]["warning_count"] == 1
    assert breakdown["unmatched"]["visitor_count"] == 100
    assert breakdown["unmatched"]["page_views"] == 200
    assert breakdown["ambiguous"]["warning_count"] == 1
    assert breakdown["ambiguous"]["visitor_count"] == 7
    assert breakdown["conflict"]["warning_count"] == 2
    assert breakdown["conflict"]["order_count"] == 3
    assert breakdown["conflict"]["visitor_count"] == 5
    assert {warning["warning_reason"] for warning in result["warnings"]} == {
        "unmatched",
        "ambiguous",
        "conflict",
    }


def test_identity_health_counts_all_warnings_even_when_the_list_is_sliced():
    """列表只展示前 50 条, 但计数与拆因统计的是**全部**告警。

    否则「有 300 条告警」会被显示成「50 条」—— 排查时会以为只有这么多。
    """
    rows = [
        {
            "warning_code": "unmatched_shop_label",
            "platform_code": "tiktok",
            "shop_id": "unknown",
            "shop_account_id": None,
            "order_count": None,
            "visitor_count": Decimal("1"),
            "page_views": Decimal("2"),
        }
        for _ in range(120)
    ]

    service = _identity_health_service(rows)
    result = asyncio.run(
        service.get_business_overview_identity_health("monthly", "2026-06-01")
    )

    assert result["warning_count"] == 120
    assert len(result["warnings"]) == 50
    assert result["warning_breakdown"]["unmatched"]["warning_count"] == 120
    assert result["warning_breakdown"]["unmatched"]["visitor_count"] == 120


def test_identity_health_returns_empty_breakdown_for_non_monthly_granularity():
    """非 monthly 粒度没有告警, 但返回体形状必须一致(前端按固定形状读)。"""
    from backend.services.postgresql_dashboard_service import (
        PostgresqlDashboardService,
    )

    service = PostgresqlDashboardService()
    result = asyncio.run(
        service.get_business_overview_identity_health("daily", "2026-06-01")
    )

    assert result["warning_count"] == 0
    assert result["warnings"] == []
    assert set(result["warning_breakdown"]) == {
        "unmatched",
        "ambiguous",
        "conflict",
        "other",
    }
    # 采集期探测异常也必须在同一份返回体里(前端按固定形状读)
    assert result["discovery_issues"] == {
        "issue_count": 0,
        "by_status": {},
        "issues": [],
    }


# ---------------------------------------------------------------------------
# P2-2: 采集期(事前)的身份异常要和语义层(事后)告警一起暴露
# ---------------------------------------------------------------------------


def test_identity_health_exposes_collection_time_discovery_issues():
    """采集期就发现编号对不上 ⇒ 必须出现在身份健康里, 不能只存在于采集日志。

    语义层告警是**事后**信号(数据已经落错); 采集期探测异常是**事前**信号
    (这次采集读到的编号就对不上账号)。只有事后信号 ⇒ 问题会反复出现。
    """
    service = _identity_health_service(
        [],  # 语义层没有告警
        discovery_count_rows=[
            {"status": "conflict_detected", "issue_count": 2},
            {"status": "stale_url", "issue_count": 1},
        ],
        discovery_detail_rows=[
            {
                "id": 7,
                "platform": "shopee",
                "main_account_id": "main_1",
                "detected_store_name": "xhkj1.my",
                "detected_platform_shop_id": "1308200825",
                "candidate_shop_account_ids": ["shopee_sg_xhkj33_local"],
                "status": "conflict_detected",
                "created_at": datetime(2026, 11, 6, tzinfo=timezone.utc),
            }
        ],
    )
    result = asyncio.run(
        service.get_business_overview_identity_health("monthly", "2026-06-01")
    )

    assert result["warning_count"] == 0
    discovery = result["discovery_issues"]
    assert discovery["issue_count"] == 3
    assert discovery["by_status"] == {"conflict_detected": 2, "stale_url": 1}
    assert discovery["issues"][0]["status"] == "conflict_detected"
    assert discovery["issues"][0]["candidate_shop_account_ids"] == [
        "shopee_sg_xhkj33_local"
    ]


def test_identity_health_discovery_issue_statuses_match_the_state_machine():
    """看板用的「问题态」必须与探测状态机的定义**同源**。

    两边各写一份常量, 迟早会漂移 —— 漂移的表现是: 采集期明明报了冲突,
    看板却一声不吭。
    """
    from backend.services.platform_shop_discovery_service import (
        PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES,
    )

    service = _identity_health_service(
        [],
        discovery_count_rows=[
            {"status": status, "issue_count": 1}
            for status in sorted(PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES)
        ],
    )
    result = asyncio.run(
        service.get_business_overview_identity_health("monthly", "2026-06-01")
    )

    assert set(result["discovery_issues"]["by_status"]) == set(
        PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES
    )

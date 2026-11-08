"""语义层覆盖率巡检 **HTTP 端点** 的测试。

覆盖三件事（对应任务验收口径）：
1. 路由已注册：``GET /api/data-pipeline/semantic-coverage`` 在 router 与 app 的
   OpenAPI 里都可见；
2. 正常路径返回**可 JSON 序列化**的结构（域健康度 / 平台解析率 / 0% 字段的真实
   列名候选 / 告警列表）；
3. **DB 不可用时仍然返回 200 + 空报告 + warning**（不抛异常、不 500 把调用方带崩）。

测试用假 session（不连库）：``SemanticCoverageAuditService`` 的调用链是
``to_regclass`` 探测 → 聚合 SQL → （可选）真实列名采集, 假 session 按 SQL 关键字
分流即可覆盖这三条路径。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from backend.domains.data_platform.routers.data_pipeline import (
    get_semantic_coverage,
    router as data_pipeline_router,
)
from backend.services.semantic_coverage_audit_service import (
    ORDERS_STANDARD_FIELDS,
    PRODUCTS_STANDARD_FIELDS,
)


# ── 假 session ────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows: Iterable[Dict[str, Any]]) -> None:
        self._rows = list(rows)

    def mappings(self) -> "_FakeResult":
        return self

    def one(self) -> Dict[str, Any]:
        return self._rows[0]

    def all(self) -> List[Dict[str, Any]]:
        return list(self._rows)


class _FakeNested:
    async def __aenter__(self) -> "_FakeNested":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeSession:
    """按 SQL 关键字返回预置结果的假 session。

    * ``relation_missing=True`` ⇒ ``to_regclass`` 探测返回 NULL（视图不存在）。
    * ``raise_on_probe`` ⇒ 探测阶段直接抛错（模拟 DB 完全不可用）。
    * ``raise_on_query`` ⇒ 聚合查询阶段抛错（模拟视图存在但查询失败）。
    """

    def __init__(
        self,
        *,
        rows: Optional[List[Dict[str, Any]]] = None,
        column_names: Optional[List[Dict[str, Any]]] = None,
        relation_missing: bool = False,
        raise_on_probe: Optional[Exception] = None,
        raise_on_query: Optional[Exception] = None,
    ) -> None:
        self._rows = list(rows or [])
        self._column_names = list(column_names or [])
        self._relation_missing = relation_missing
        self._raise_on_probe = raise_on_probe
        self._raise_on_query = raise_on_query
        self.statements: List[str] = []
        self.rollback_count = 0

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        if "to_regclass" in sql:
            if self._raise_on_probe is not None:
                raise self._raise_on_probe
            return _FakeResult([{"oid": None if self._relation_missing else "16400"}])
        if self._raise_on_query is not None:
            raise self._raise_on_query
        if "jsonb_object_keys" in sql:
            return _FakeResult(self._column_names)
        return _FakeResult(self._rows)

    def begin_nested(self) -> _FakeNested:
        return _FakeNested()

    async def rollback(self) -> None:
        """记录回滚次数。

        PostgreSQL 里一条语句失败会让整个事务 aborted ⇒ 端点必须在失败后回滚,
        否则请求收尾的 commit 会把本次响应打成 500。
        """
        self.rollback_count += 1


# ── 构造聚合结果行 ────────────────────────────────────────────────────


def _row(
    platform_code: str,
    granularity: str,
    *,
    total_rows: int,
    empty_shell_rows: int = 0,
    all_unresolved_rows: int = 0,
    resolved: Optional[Dict[str, int]] = None,
    fields: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """造一行聚合结果（``resolved`` 省略的字段按 0 处理）。"""
    row: Dict[str, Any] = {
        "platform_code": platform_code,
        "granularity": granularity,
        "total_rows": total_rows,
        "empty_shell_rows": empty_shell_rows,
        "all_unresolved_rows": all_unresolved_rows,
    }
    for field in fields if fields is not None else PRODUCTS_STANDARD_FIELDS:
        row[f"resolved_{field.standard_field}"] = int(
            (resolved or {}).get(field.standard_field, 0)
        )
    return row


def _orders_row(
    platform_code: str,
    granularity: str,
    *,
    total_rows: int,
    resolved: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """造一行**订单域**的聚合结果。"""
    return _row(
        platform_code,
        granularity,
        total_rows=total_rows,
        resolved=resolved,
        fields=ORDERS_STANDARD_FIELDS,
    )


def _response_body(response: Any) -> Dict[str, Any]:
    """把 ``success_response`` 的 JSONResponse 解成 dict。"""
    return json.loads(response.body.decode("utf-8"))


# ── 1. 路由已注册 ─────────────────────────────────────────────────────


def test_semantic_coverage_route_is_registered_on_router():
    """router 上必须有这条只读路由。"""
    paths = {getattr(route, "path", "") for route in data_pipeline_router.routes}
    assert "/api/data-pipeline/semantic-coverage" in paths


def test_semantic_coverage_route_is_visible_in_app_openapi():
    """端点要在 app 的 OpenAPI 里可见（前端/运维能自助发现）。"""
    from backend.main import app

    schema = app.openapi()
    assert "/api/data-pipeline/semantic-coverage" in schema["paths"]

    operation = schema["paths"]["/api/data-pipeline/semantic-coverage"]["get"]
    # 只读端点：只暴露 GET。
    assert "post" not in schema["paths"]["/api/data-pipeline/semantic-coverage"]
    assert "domain" in operation.get("parameters", []) or any(
        param.get("name") == "domain" for param in operation.get("parameters", [])
    )


# ── 2. 正常路径返回结构 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoint_returns_serializable_report_for_single_domain():
    """指定域 ⇒ 返回该域的解析率 / 平台诊断 / 列名候选 / 告警，且可 JSON 序列化。"""
    rows = [
        _orders_row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved={
                field.standard_field: 100
                for field in ORDERS_STANDARD_FIELDS
                if field.standard_field != "profit"
            },
        )
    ]
    session = _FakeSession(
        rows=rows,
        column_names=[
            {
                "platform_code": "shopee",
                "granularity": "monthly",
                "column_names": ["销售利润", "profit"],
            }
        ],
    )

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)

    assert response.status_code == 200
    body = _response_body(response)
    assert body["success"] is True

    data = body["data"]
    assert data["domain"] == "orders"
    # 不传 threshold ⇒ 沿用服务层默认 0.5。
    assert data["threshold"] == 0.5
    assert len(data["reports"]) == 1

    report = data["reports"][0]
    assert report["domain"] == "orders"
    assert report["relation"] == "semantic.fact_orders_atomic"
    assert report["entries"], "解析率条目不能为空"
    assert report["groups"][0]["platform_code"] == "shopee"
    assert report["platforms"][0]["platform_code"] == "shopee"
    assert isinstance(report["warnings"], list)
    assert report["summary"]["health"] in {"healthy", "degraded", "unknown"}

    # 整个响应体可以直接 JSON 序列化（tuple/dataclass 已被显式转成 list/dict）。
    json.dumps(body)


@pytest.mark.asyncio
async def test_endpoint_returns_zero_rate_fields_with_column_candidates():
    """解析率 0% 的字段要带上**源表真实列名候选**（运维要的就是「源表里叫啥」）。"""
    rows = [
        _orders_row(
            "tiktok",
            "monthly",
            total_rows=50,
            resolved={
                field.standard_field: 50
                for field in ORDERS_STANDARD_FIELDS
                if field.standard_field != "profit"
            },
        )
    ]
    session = _FakeSession(
        rows=rows,
        column_names=[
            {
                "platform_code": "tiktok",
                "granularity": "monthly",
                # 用**字典里尚未登记**的列名 —— 已登记的列名不算「列名未登记」的候选
                # （那是「登记了但取不到数」，是另一类问题）。
                "column_names": ["利润合计", "利润总额"],
            }
        ],
    )

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)
    body = _response_body(response)
    report = body["data"]["reports"][0]

    zero_rate_entries = [
        entry for entry in report["entries"] if entry["resolution_rate"] <= 0
    ]
    assert zero_rate_entries, "profit 解析率 0% 必须出现在条目里"

    candidates = report["column_candidates"]
    assert candidates, "解析率 0% 必须给出真实列名候选"
    candidate_values = [name for names in candidates.values() for name in names]
    assert candidate_values, "列名候选不能是空列表"

    # 告警里要点名解析率为 0 的字段。
    assert any("profit" in warning for warning in report["warnings"])


@pytest.mark.asyncio
async def test_endpoint_defaults_to_all_domains():
    """不传 domain ⇒ 两个域都出（面板要同时看订单域与商品域）。"""
    session = _FakeSession(rows=[])

    response = await get_semantic_coverage(domain=None, threshold=None, db=session)
    body = _response_body(response)

    data = body["data"]
    assert data["domain"] == "all"
    # 2026-11-08: 流量域也进入巡检范围 ⇒ all 覆盖三个域。
    assert {report["domain"] for report in data["reports"]} == {
        "analytics",
        "orders",
        "products",
    }


@pytest.mark.asyncio
async def test_endpoint_accepts_custom_threshold():
    """阈值可传：调低阈值后告警口径跟着变。"""
    rows = [
        _orders_row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved={
                field.standard_field: 100
                for field in ORDERS_STANDARD_FIELDS
                if field.standard_field != "profit"
            },
        )
    ]
    session = _FakeSession(rows=rows)

    response = await get_semantic_coverage(domain="orders", threshold=0.99, db=session)
    body = _response_body(response)

    assert body["data"]["threshold"] == 0.99
    assert body["data"]["reports"][0]["threshold"] == 0.99


@pytest.mark.asyncio
async def test_endpoint_rejects_unknown_domain():
    """未知域是**调用方参数写错** ⇒ 明确报 400，不静默吞掉。"""
    session = _FakeSession(rows=[])

    with pytest.raises(Exception) as exc_info:
        await get_semantic_coverage(domain="not_a_domain", threshold=None, db=session)

    assert getattr(exc_info.value, "status_code", None) == 400


# ── 3. DB 不可用 ⇒ 200 + 空报告 + warning（不抛异常） ─────────────────


@pytest.mark.asyncio
async def test_endpoint_returns_empty_report_with_warning_when_relation_missing():
    """semantic 视图不存在 ⇒ 200 + 空报告 + 一条 warning。"""
    session = _FakeSession(relation_missing=True)

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)

    assert response.status_code == 200
    body = _response_body(response)
    assert body["success"] is True

    report = body["data"]["reports"][0]
    assert report["entries"] == []
    assert report["groups"] == []
    assert report["warnings"], "视图不可用必须留下 warning"
    assert "semantic.fact_orders_atomic" in report["warnings"][0]
    # 域级概览也要标成 unknown（判不了）。
    assert report["summary"]["health"] == "unknown"


@pytest.mark.asyncio
async def test_endpoint_returns_empty_report_with_warning_when_db_unavailable():
    """DB 完全不可用（探测阶段就失败）⇒ 200 + 空报告 + warning，不抛异常。"""
    session = _FakeSession(
        raise_on_probe=OperationalError("SELECT 1", {}, Exception("db down"))
    )

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)

    assert response.status_code == 200
    body = _response_body(response)
    assert body["success"] is True

    report = body["data"]["reports"][0]
    assert report["entries"] == []
    assert report["warnings"]
    assert "跳过" in report["warnings"][0]


@pytest.mark.asyncio
async def test_endpoint_returns_empty_report_with_warning_when_query_fails():
    """视图存在但查询失败（列改名/权限不足）⇒ 200 + 空报告 + warning。"""
    session = _FakeSession(
        raise_on_query=ProgrammingError("SELECT 1", {}, Exception("boom"))
    )

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)

    assert response.status_code == 200
    body = _response_body(response)
    report = body["data"]["reports"][0]
    assert report["entries"] == []
    assert report["warnings"]


@pytest.mark.asyncio
async def test_endpoint_survives_unexpected_exception_from_audit():
    """巡检整体抛出未预期异常 ⇒ 端点兜住，仍然 200 + 空报告 + warning。

    服务层只吞 ``SQLAlchemyError``；会话失效之类的更外层异常由端点兜底，
    保证运维脚本不会因为一次巡检就 500。
    """
    session = _FakeSession(raise_on_probe=RuntimeError("会话已失效"))

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)

    assert response.status_code == 200
    body = _response_body(response)
    report = body["data"]["reports"][0]
    assert report["entries"] == []
    assert report["warnings"]
    assert "RuntimeError" in report["warnings"][0]


@pytest.mark.asyncio
async def test_endpoint_rolls_back_after_failed_audit():
    """巡检失败后必须回滚 —— 否则请求收尾的 commit 会把响应打成 500。

    PostgreSQL 里一条语句失败会让整个事务 aborted ⇒ 后续任何操作都抛
    ``PendingRollbackError``。不回滚 ⇒ 「巡检失败返回 200」的承诺在真实
    DB 上会失效(端点函数本身返回了 200, 但依赖的收尾 commit 会抛)。
    """
    session = _FakeSession(
        raise_on_probe=OperationalError("SELECT 1", {}, Exception("db down"))
    )

    response = await get_semantic_coverage(domain="orders", threshold=None, db=session)

    assert response.status_code == 200
    assert session.rollback_count >= 1, "巡检失败后必须回滚，避免事务 aborted"


@pytest.mark.asyncio
async def test_endpoint_is_read_only():
    """只读：整条链路只发 SELECT，绝不写库。"""
    session = _FakeSession(rows=[])

    await get_semantic_coverage(domain="all", threshold=None, db=session)

    assert session.statements, "巡检必须发出查询"
    for sql in session.statements:
        upper = sql.upper()
        for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
            assert forbidden not in upper, f"只读端点不得出现 {forbidden}"


# ── 4. HTTP 层端到端（TestClient） ─────────────────────────────────────


def _build_test_app(session: Any) -> Any:
    """挂上 data_pipeline 路由的最小 app（把 DB 依赖换成假 session）。"""
    from fastapi import FastAPI

    from backend.models.database import get_async_db

    app = FastAPI()
    app.include_router(data_pipeline_router)
    app.dependency_overrides[get_async_db] = lambda: session
    return app


def test_http_endpoint_returns_200_with_warning_when_db_unavailable():
    """HTTP 层验证：DB 不可用 ⇒ 200 + 空报告 + warning（不 500）。"""
    from fastapi.testclient import TestClient

    session = _FakeSession(
        raise_on_probe=OperationalError("SELECT 1", {}, Exception("db down"))
    )
    client = TestClient(_build_test_app(session))

    response = client.get("/api/data-pipeline/semantic-coverage?domain=orders")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    report = body["data"]["reports"][0]
    assert report["entries"] == []
    assert report["warnings"]
    assert "跳过" in report["warnings"][0]


def test_http_endpoint_returns_report_payload():
    """HTTP 层验证：正常路径返回可 JSON 序列化的巡检结论。"""
    from fastapi.testclient import TestClient

    rows = [
        _orders_row(
            "shopee",
            "monthly",
            total_rows=100,
            resolved={
                field.standard_field: 100
                for field in ORDERS_STANDARD_FIELDS
                if field.standard_field != "profit"
            },
        )
    ]
    session = _FakeSession(rows=rows)
    client = TestClient(_build_test_app(session))

    response = client.get("/api/data-pipeline/semantic-coverage?domain=orders")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    report = body["data"]["reports"][0]
    assert report["domain"] == "orders"
    assert report["entries"]
    assert report["summary"]["health"] == "degraded"


def test_http_endpoint_rejects_unknown_domain_with_400():
    """HTTP 层验证：未知域 ⇒ 400（调用方参数写错，不该静默吞掉）。"""
    from fastapi.testclient import TestClient

    session = _FakeSession(rows=[])
    client = TestClient(_build_test_app(session))

    response = client.get("/api/data-pipeline/semantic-coverage?domain=nope")

    assert response.status_code == 400


# ── 流量域可巡检(2026-11-08) ────────────────────────────────────────────
#
# 之前 ``?domain=analytics`` 会被白名单挡下来返回 400 ——
# 而流量域是本轮变化最大的域, 巡检不到就等于「改完看不见」。


def test_endpoint_accepts_analytics_domain():
    """``domain=analytics`` 必须返回 200(不是 400)。"""
    from fastapi.testclient import TestClient

    client = TestClient(_build_test_app(_FakeSession(rows=[])))

    response = client.get("/api/data-pipeline/semantic-coverage?domain=analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    report = body["data"]["reports"][0]
    assert report["domain"] == "analytics"
    assert report["relation"] == "semantic.fact_analytics_atomic"


def test_endpoint_all_domain_covers_three_domains():
    """不传 domain ⇒ 三个域都出(订单 / 商品 / 流量)。"""
    from fastapi.testclient import TestClient

    client = TestClient(_build_test_app(_FakeSession(rows=[])))

    response = client.get("/api/data-pipeline/semantic-coverage")

    assert response.status_code == 200
    body = response.json()
    domains = {report["domain"] for report in body["data"]["reports"]}
    assert domains == {"orders", "products", "analytics"}


def test_endpoint_unknown_domain_still_rejected():
    """未登记的域仍然 400(不能因为放开 analytics 就把白名单拆了)。"""
    from fastapi.testclient import TestClient

    client = TestClient(_build_test_app(_FakeSession(rows=[])))

    response = client.get("/api/data-pipeline/semantic-coverage?domain=nope")

    assert response.status_code == 400

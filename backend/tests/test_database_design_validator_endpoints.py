"""数据库设计规范校验 API 的端点契约测试。

背景（2026-10-31 实证）
-----------------------
这组端点从**第一版起**就是全线 500（`git log --follow` 证明 4 个端点
从没通过过）：路由是 `async def` + `Depends(get_async_db)`（拿到 AsyncSession），
却把异步会话直接喂给同步校验器 ——
`inspect(AsyncEngine)` 不支持、`db.execute()` 返回协程、
`validate_field_mapping(db)` 的签名压根不是「拿会话」。

本文件锁两件事：
1. **5 个端点必须 200**（不是 500）—— 「500 全线修复」的回归门禁；
2. `/validate/field-mapping` 的**校验规则**必须真的生效：
   数值型字段的 data_type 被写成 string 要报 error、数据域一个必填字段都没标
   要报 warning、域里没有生效字段要报 error。
"""

from __future__ import annotations

from typing import Any, List

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ENDPOINTS = [
    "/api/database-design/validate",
    "/api/database-design/validate/tables",
    "/api/database-design/validate/materialized-views",
    "/api/database-design/validate/field-mapping",
    "/api/database-design/validate/data-ingestion",
]


@pytest_asyncio.fixture
async def design_client():
    """只挂这一个 router 的客户端。

    这组端点没有鉴权依赖（`register_business_routes` 也没给 router 加全局依赖），
    所以不需要覆盖 `get_current_user`。
    数据库走仓库自己的引擎 —— 测试护栏已经把引擎指向一次性隔离容器，
    绝不会碰到真实业务库。
    """
    from backend.domains.business.routers import database_design_validator

    app = FastAPI()
    app.include_router(database_design_validator.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ----------------------------------------------------------------------
# 端点层：全线 500 的回归门禁
# ----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ENDPOINTS)
async def test_design_validation_endpoints_do_not_return_500(design_client, path):
    """每个端点都必须 200。

    这是本次修复的核心断言：修复前这 5 条全是 500。
    """
    response = await design_client.get(path)

    assert (
        response.status_code == 200
    ), f"{path} 返回 {response.status_code}：{response.text[:500]}"


@pytest.mark.asyncio
async def test_validate_endpoint_returns_design_issues_structure(design_client):
    """`/validate` 必须给出可用的校验结论，而不是空壳 200。"""
    response = await design_client.get("/api/database-design/validate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["is_valid"], bool)
    assert isinstance(data["issues"], list)
    summary = data["summary"]
    for key in ("total_issues", "error_count", "warning_count", "info_count"):
        assert key in summary, f"summary 缺 {key}"
    assert summary["total_issues"] == len(data["issues"])
    for issue in data["issues"]:
        assert issue["severity"] in ("error", "warning", "info")
        assert issue["category"]
        assert issue["issue"]


@pytest.mark.asyncio
async def test_validate_tables_endpoint_only_reports_table_issues(design_client):
    """`/validate/tables` 只给表结构类问题（不含物化视图）。"""
    response = await design_client.get("/api/database-design/validate/tables")

    assert response.status_code == 200
    issues = response.json()["data"]["issues"]
    assert isinstance(issues, list)
    for issue in issues:
        assert issue["category"] in (
            "primary_key",
            "nullable",
            "index",
            "foreign_key",
        )


@pytest.mark.asyncio
async def test_validate_materialized_views_endpoint_only_reports_mv_issues(
    design_client,
):
    """`/validate/materialized-views` 只给物化视图类问题。"""
    response = await design_client.get(
        "/api/database-design/validate/materialized-views"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    for issue in payload["issues"]:
        assert issue["category"] == "materialized_view"


@pytest.mark.asyncio
async def test_validate_data_ingestion_endpoint_returns_issues_structure(design_client):
    """`/validate/data-ingestion` 必须给出结论与问题清单。"""
    response = await design_client.get("/api/database-design/validate/data-ingestion")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["is_valid"], bool)
    assert isinstance(payload["issues"], list)
    assert "total_issues" in payload["summary"]


@pytest.mark.asyncio
async def test_validate_field_mapping_endpoint_returns_dictionary_report(design_client):
    """`/validate/field-mapping` 必须给出**字段映射字典**的体检报告。

    修复前这个端点把 AsyncSession 传给了签名是 `(mapped_rows, data_domain)`
    的 `validate_field_mapping` —— 必错。
    """
    response = await design_client.get("/api/database-design/validate/field-mapping")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["is_valid"], bool)
    assert isinstance(data["issues"], list)

    summary = data["summary"]
    for key in ("total_issues", "error_count", "warning_count", "info_count"):
        assert key in summary
    assert summary["total_issues"] == len(data["issues"])
    assert "total_fields" in summary
    assert "total_domains" in summary
    assert isinstance(summary["domains"], dict)


# ----------------------------------------------------------------------
# 规则层：字典校验规则本身
# ----------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> List[Any]:
        return self._rows


class _FakeAsyncSession:
    """最小 AsyncSession 替身：只回一行结果集。

    列顺序与 `validate_field_mapping_dictionary` 的 SELECT 一致：
    data_domain, field_code, cn_name, en_name, field_group,
    is_required, data_type, active, status, synonyms
    """

    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows
        self.executed = 0

    async def execute(self, statement, *args, **kwargs):
        self.executed += 1
        return _FakeResult(self._rows)


def _row(
    *,
    domain: str = "orders",
    code: str = "order_amount",
    group: str = "measure",
    required: bool = True,
    data_type: str = "numeric",
    active: bool = True,
    status: str = "active",
):
    return (domain, code, code, None, group, required, data_type, active, status, None)


@pytest.mark.asyncio
async def test_dictionary_reports_numeric_field_typed_as_string_as_error():
    """数值型字段的 data_type 写成 string —— 采集能进来，算账会炸，必须报 error。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession([_row(code="order_amount", data_type="string")])
    result = await validate_field_mapping_dictionary(db)

    assert result["success"] is True
    assert result["is_valid"] is False
    errors = [i for i in result["issues"] if i["severity"] == "error"]
    assert len(errors) == 1
    assert errors[0]["category"] == "data_type"
    assert errors[0]["field_name"] == "order_amount"
    assert result["summary"]["error_count"] == 1


@pytest.mark.asyncio
async def test_dictionary_accepts_numeric_field_typed_as_number():
    """data_type 写对了就不该报错（别把正常字段也骂一遍）。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession([_row(code="order_amount", data_type="numeric")])
    result = await validate_field_mapping_dictionary(db)

    assert result["is_valid"] is True
    assert result["summary"]["total_issues"] == 0


@pytest.mark.asyncio
async def test_dictionary_does_not_flag_plain_text_field_as_numeric():
    """名字里没有数值暗示的字段，data_type=string 是正常的。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession([_row(code="order_status", data_type="string")])
    result = await validate_field_mapping_dictionary(db)

    assert [i for i in result["issues"] if i["severity"] == "error"] == []


@pytest.mark.asyncio
async def test_dictionary_reports_domain_without_required_field_as_warning():
    """一个必填字段都没标的数据域 = 采集没有守门，要报 warning。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession([_row(code="order_id", required=False)])
    result = await validate_field_mapping_dictionary(db)

    warnings = [i for i in result["issues"] if i["severity"] == "warning"]
    assert any(i["category"] == "required" for i in warnings)
    assert result["is_valid"] is True  # warning 不算不合法


@pytest.mark.asyncio
async def test_dictionary_reports_domain_without_active_field_as_error():
    """域里一个生效字段都没有 = 采集一定对不上标准字段，报 error。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession([_row(code="order_id", active=False, status="inactive")])
    result = await validate_field_mapping_dictionary(db)

    errors = [i for i in result["issues"] if i["severity"] == "error"]
    assert any(i["category"] == "coverage" for i in errors)
    assert result["is_valid"] is False


@pytest.mark.asyncio
async def test_dictionary_reports_missing_data_type_and_field_group():
    """缺 data_type（warning）与缺 field_group（info）都要被指出来。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession([_row(code="order_note", data_type="", group="")])
    result = await validate_field_mapping_dictionary(db)

    severities = {(i["category"], i["severity"]) for i in result["issues"]}
    assert ("data_type", "warning") in severities
    assert ("field_group", "info") in severities


@pytest.mark.asyncio
async def test_dictionary_summary_counts_fields_and_domains():
    """摘要要能回答「配了多少字段、几个域」。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    db = _FakeAsyncSession(
        [
            _row(domain="orders", code="order_id", required=True),
            _row(domain="orders", code="order_amount", required=False),
            _row(domain="products", code="product_id", required=True),
        ]
    )
    result = await validate_field_mapping_dictionary(db)

    summary = result["summary"]
    assert summary["total_fields"] == 3
    assert summary["total_domains"] == 2
    assert summary["domains"]["orders"]["total_fields"] == 2
    assert summary["domains"]["orders"]["required_fields"] == 1
    assert summary["domains"]["products"]["active_fields"] == 1


@pytest.mark.asyncio
async def test_dictionary_survives_a_broken_database_without_raising():
    """数据库读不出来时不能把端点带崩 —— 返回失败结论即可。"""
    from backend.services.field_mapping_validator import (
        validate_field_mapping_dictionary,
    )

    class _BrokenSession:
        async def execute(self, statement, *args, **kwargs):
            raise RuntimeError("table missing")

    result = await validate_field_mapping_dictionary(_BrokenSession())

    assert result["success"] is False
    assert result["is_valid"] is False
    assert result["issues"] == []

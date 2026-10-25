"""SKU 级滞销排名的服务与端点契约测试。

关键门禁（与 test_business_overview_query_policy_gates.py 同一套思路）：
1. 查询**只打**只读视图 `api.sku_clearance_ranking_module`，
   不碰 b_class./semantic.fact_orders_atomic/raw_data->>；
2. 每个筛选参数**真的进 WHERE 子句**（不是空转）；
3. 排序字段走白名单，用户输入永远不拼进 SQL；
4. 未匹配 ERP 主数据的 SKU 照常返回，定价字段为空；
5. 视图 SQL 不得把定价公式写进去，也不得退回慢的 backlog_base 取数路径。
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.services.inventory.sku_clearance_service import (
    CLEARANCE_VIEW,
    SkuClearanceService,
)

VIEW_SQL_PATH = Path("sql/api_modules/sku_clearance_ranking_module.sql")

POLICY_ROWS = [
    {
        "min_restock_days": 0,
        "tier_label": "日常",
        "discount_rate": Decimal("0.10"),
        "target_margin_rate": Decimal("0.25"),
        "platform_basis": "tiktok",
    },
    {
        "min_restock_days": 60,
        "tier_label": "滞销30天",
        "discount_rate": Decimal("0.15"),
        "target_margin_rate": Decimal("0.22"),
        "platform_basis": "tiktok",
    },
]


def _fake_platform():
    """假平台：带 other_cost_rate / default_creator_commission_rate。

    没有平台成本率时 `compute_sku_pricing` 会记 `missing_platform_cost_rate`
    并拒绝计算成本线（这是设计如此，不是 bug）。
    """
    return type(
        "FakePlatform",
        (),
        {
            "platform_code": "tiktok",
            "other_cost_rate": Decimal("0.06"),
            "default_creator_commission_rate": Decimal("0.0606"),
        },
    )()


def _row(**overrides):
    base = {
        "snapshot_date": date(2026, 9, 14),
        "platform_code": "miaoshou",
        "product_sku": "SKU-A",
        "sku_key": "SKU-A",
        "product_name": "Product A",
        "current_qty": 10,
        "on_hand_qty": 10,
        "inventory_value": 1000.0,
        "warehouse_count": 1,
        # 主判据：距上次进货天数
        "days_since_restock": 0,
        # DOS 参考原料：近 90 天窗口销量
        "checklist_sales_90d": 90,
        "sku_id": 1001,
        "default_purchase_cost": 46.5,
        "reference_selling_price": None,
        "min_selling_price_override": None,
    }
    base.update(overrides)
    return base


def _build_service(
    monkeypatch,
    *,
    rows=None,
    summary=None,
    tier_rows=None,
    pricing_inputs=None,
    policy_rows=None,
    platform=None,
):
    service = SkuClearanceService(db=None)
    captured: list[tuple[str, dict]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, dict(params)))
        # 顺序要紧：档位分组查询里也有 count(*) AS sku_count，必须先判它
        if "AS tier_index" in query:
            return tier_rows or []
        if "count(*) AS sku_count" in query:
            return [summary or {"sku_count": 0, "total_quantity": 0,
                                "total_inventory_value": 0,
                                "missing_reference_price_count": 0}]
        return rows or []

    async def fake_load_pricing_inputs(_rows):
        return pricing_inputs or {}

    async def fake_load_policy_rows():
        return policy_rows if policy_rows is not None else POLICY_ROWS

    async def fake_load_platform(_policy_rows):
        return platform

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_pricing_inputs", fake_load_pricing_inputs)
    monkeypatch.setattr(service, "_load_policy_rows", fake_load_policy_rows)
    monkeypatch.setattr(service, "_load_platform", fake_load_platform)
    return service, captured


@pytest.mark.asyncio
async def test_query_only_touches_the_clearance_view(monkeypatch):
    service, captured = _build_service(monkeypatch, rows=[_row()])

    await service.get_sku_clearance_ranking()

    assert captured, "应该至少发出一条查询"
    for query, _params in captured:
        assert CLEARANCE_VIEW in query
        for forbidden in (
            "FROM b_class.",
            "FROM semantic.fact_orders_atomic",
            "raw_data->>",
            "FROM mart.",
        ):
            assert forbidden not in query


@pytest.mark.asyncio
async def test_min_restock_days_filter_is_applied_not_a_noop(monkeypatch):
    service, captured = _build_service(monkeypatch, rows=[_row()])

    await service.get_sku_clearance_ranking(min_restock_days=120)

    detail_queries = [q for q, _ in captured if "ORDER BY" in q]
    assert detail_queries, "应该有带排序的明细查询"
    assert "days_since_restock >= :min_restock_days" in detail_queries[0]
    params = [p for q, p in captured if "ORDER BY" in q][0]
    assert params["min_restock_days"] == 120


@pytest.mark.asyncio
async def test_max_restock_days_and_other_filters_are_applied(monkeypatch):
    service, captured = _build_service(monkeypatch, rows=[_row()])

    await service.get_sku_clearance_ranking(
        min_restock_days=30,
        max_restock_days=180,
        platform_code="miaoshou",
        keyword="SKU-A",
    )

    detail = [q for q, _ in captured if "ORDER BY" in q][0]
    params = [p for q, p in captured if "ORDER BY" in q][0]
    assert "days_since_restock >= :min_restock_days" in detail
    assert "days_since_restock <= :max_restock_days" in detail
    assert "platform_code = :platform_code" in detail
    assert "product_sku ILIKE :keyword" in detail
    assert params["max_restock_days"] == 180
    assert params["platform_code"] == "miaoshou"
    assert params["keyword"] == "%SKU-A%"


@pytest.mark.asyncio
async def test_unsupported_sort_by_is_rejected_and_never_reaches_sql(monkeypatch):
    service, captured = _build_service(monkeypatch, rows=[_row()])

    with pytest.raises(ValueError):
        await service.get_sku_clearance_ranking(sort_by="product_sku; DROP TABLE x")

    assert captured == [], "非法排序字段必须在发查询之前就被拒"


@pytest.mark.asyncio
async def test_sort_by_whitelist_maps_to_known_columns(monkeypatch):
    service, captured = _build_service(monkeypatch, rows=[_row()])

    await service.get_sku_clearance_ranking(sort_by="days_since_restock", sort_order="asc")

    detail = [q for q, _ in captured if "ORDER BY" in q][0]
    assert "ORDER BY days_since_restock ASC" in detail


@pytest.mark.asyncio
async def test_summary_counts_missing_reference_price(monkeypatch):
    service, _ = _build_service(
        monkeypatch,
        rows=[_row()],
        summary={
            "sku_count": 3,
            "total_quantity": 30,
            "total_inventory_value": 3000.0,
            "missing_reference_price_count": 2,
        },
    )

    result = await service.get_sku_clearance_ranking()

    assert result.total == 3
    assert result.summary.sku_count == 3
    assert result.summary.total_quantity == 30
    assert result.summary.total_inventory_value == 3000.0
    assert result.summary.missing_reference_price_count == 2


@pytest.mark.asyncio
async def test_unmatched_erp_sku_is_kept_with_empty_pricing(monkeypatch):
    """匹配不到主数据的 SKU 必须留在清单里，定价字段为空。"""
    service, _ = _build_service(
        monkeypatch,
        rows=[
            _row(
                product_sku="HJJ-XH-CTD01",
                sku_id=None,
                default_purchase_cost=None,
                reference_selling_price=None,
            )
        ],
        pricing_inputs={},
    )

    result = await service.get_sku_clearance_ranking(min_restock_days=0)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.product_sku == "HJJ-XH-CTD01"
    assert item.pricing_matched_erp is False
    assert item.min_selling_price is None
    assert item.pricing_tier_label is None
    assert item.clearance_recovery_amount is None


@pytest.mark.asyncio
async def test_pricing_uses_pure_function_and_reports_tier(monkeypatch):
    """定价字段由 product_pricing_service 的纯函数补齐，档位按距上次进货天数命中。"""
    service, _ = _build_service(
        monkeypatch,
        rows=[_row(days_since_restock=70)],
        pricing_inputs={
            1001: {
                "creator_commission_rate": None,
                "spu_bound": True,
                "spu_return_loss_rate": Decimal("0.02"),
                "spu_damage_rate": Decimal("0.01"),
            }
        },
        platform=_fake_platform(),
    )

    result = await service.get_sku_clearance_ranking(min_restock_days=0)

    item = result.items[0]
    assert item.pricing_tier_label == "滞销30天"
    assert item.current_discount_rate == pytest.approx(0.15)
    assert item.clearance_max_discount_rate == pytest.approx(0.15)
    assert item.current_target_margin_rate == pytest.approx(0.22)
    assert item.min_selling_price is not None
    # 参考售价缺失 -> 清货回款算不出来（None），不是 0
    assert item.clearance_recovery_amount is None


@pytest.mark.asyncio
async def test_clearance_recovery_amount_uses_current_discount(monkeypatch):
    service, _ = _build_service(
        monkeypatch,
        rows=[_row(days_since_restock=70, reference_selling_price=100.0, current_qty=10)],
        pricing_inputs={
            1001: {
                "creator_commission_rate": None,
                "spu_bound": True,
                "spu_return_loss_rate": Decimal("0.02"),
                "spu_damage_rate": Decimal("0.01"),
            }
        },
        platform=_fake_platform(),
    )

    result = await service.get_sku_clearance_ranking(min_restock_days=0)

    # 100 * (1 - 0.15) * 10 = 850.00
    assert result.items[0].clearance_recovery_amount == pytest.approx(850.0)


@pytest.mark.asyncio
async def test_endpoint_returns_full_payload(monkeypatch):
    """端点 200 + 响应结构完整。"""
    from httpx import ASGITransport, AsyncClient
    from fastapi import FastAPI

    from backend.dependencies.auth import get_current_user
    from backend.domains.business.routers import inventory_domain
    from backend.models.database import get_async_db

    app = FastAPI()
    app.include_router(inventory_domain.router)

    async def override_get_async_db():
        yield None

    async def override_current_user():
        return type("U", (), {"user_id": 1, "id": 1, "roles": []})()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    captured: dict = {}

    async def fake_get_ranking(self, **kwargs):
        captured.update(kwargs)
        from backend.schemas.inventory import (
            SkuClearanceRankingItemResponse,
            SkuClearanceRankingResponse,
            SkuClearanceRankingSummaryResponse,
        )

        return SkuClearanceRankingResponse(
            summary=SkuClearanceRankingSummaryResponse(
                sku_count=1,
                total_quantity=10,
                total_inventory_value=1000.0,
                missing_reference_price_count=1,
            ),
            items=[
                SkuClearanceRankingItemResponse(
                    platform_code="miaoshou",
                    product_sku="SKU-A",
                    current_qty=10,
                    inventory_value=1000.0,
                    days_since_restock=70,
                )
            ],
            total=1,
            limit=kwargs.get("limit", 100),
            offset=kwargs.get("offset", 0),
        )

    monkeypatch.setattr(SkuClearanceService, "get_sku_clearance_ranking", fake_get_ranking)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/inventory/clearance-ranking",
            params={"min_restock_days": 90, "limit": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["summary"]["missing_reference_price_count"] == 1
    assert payload["items"][0]["product_sku"] == "SKU-A"
    assert captured["min_restock_days"] == 90
    assert captured["limit"] == 20


@pytest.mark.asyncio
async def test_endpoint_rejects_unknown_sort_by(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from fastapi import FastAPI

    from backend.dependencies.auth import get_current_user
    from backend.domains.business.routers import inventory_domain
    from backend.models.database import get_async_db

    app = FastAPI()
    app.include_router(inventory_domain.router)

    async def override_get_async_db():
        yield None

    async def override_current_user():
        return type("U", (), {"user_id": 1, "id": 1, "roles": []})()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/inventory/clearance-ranking",
            params={"sort_by": "product_sku"},
        )

    assert response.status_code == 422


# ----------------------------------------------------------------------
# 档位分组（门槛来自档位表）
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_groups_skus_by_policy_tier(monkeypatch):
    """汇总要按**档位表门槛**分组，门槛与档位名都取自 policy_rows。"""
    service, _ = _build_service(
        monkeypatch,
        rows=[_row(days_since_restock=70)],
        summary={
            "sku_count": 2,
            "total_quantity": 20,
            "total_inventory_value": 300.0,
            "missing_reference_price_count": 0,
        },
        tier_rows=[
            {"tier_index": 0, "sku_count": 1, "inventory_value": 100.0},
            {"tier_index": 1, "sku_count": 1, "inventory_value": 200.0},
        ],
    )

    result = await service.get_sku_clearance_ranking(min_restock_days=0)

    tiers = result.summary.restock_tiers
    assert len(tiers) == 2
    assert tiers[0].min_restock_days == 0
    assert tiers[0].tier_label == "日常"
    assert tiers[0].sku_count == 1
    assert tiers[0].inventory_value == pytest.approx(100.0)
    assert tiers[1].min_restock_days == 60
    assert tiers[1].tier_label == "滞销30天"
    assert tiers[1].sku_count == 1
    assert tiers[1].inventory_value == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_tier_thresholds_are_bound_as_parameters_not_inlined(monkeypatch):
    """门槛走参数绑定 —— 档位表里改个门槛，不该需要改代码。"""
    service, captured = _build_service(monkeypatch, rows=[_row()])

    await service.get_sku_clearance_ranking(min_restock_days=0)

    tier_queries = [(q, p) for q, p in captured if "AS tier_index" in q]
    assert tier_queries, "应该有档位分组查询"
    query, params = tier_queries[0]
    assert params["bound_0"] == 0
    assert params["bound_1"] == 60
    assert ":bound_1" in query
    assert "days_since_restock >= 60" not in query


@pytest.mark.asyncio
async def test_tier_label_never_reaches_sql_text(monkeypatch):
    """tier_label 是运营填的自由文本，拼进 SQL 就是注入。"""
    service, captured = _build_service(monkeypatch, rows=[_row()])

    await service.get_sku_clearance_ranking(min_restock_days=0)

    for query, _params in captured:
        assert "日常" not in query
        assert "滞销30天" not in query


# ----------------------------------------------------------------------
# DOS 参考值
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dos_reference_value_uses_the_canonical_implementation(monkeypatch):
    """DOS 必须走 inventory_dos_service：45 ÷ (30 ÷ 90) = 135 天。"""
    service, _ = _build_service(
        monkeypatch,
        rows=[_row(current_qty=45, checklist_sales_90d=30)],
    )

    result = await service.get_sku_clearance_ranking(min_restock_days=0)

    assert result.items[0].checklist_dos_sales90 == pytest.approx(135.0)


@pytest.mark.asyncio
async def test_dos_reference_value_is_none_when_not_computable(monkeypatch):
    """销量取不到 → DOS 是 None（不可算），不是 0、也不是哨兵值。"""
    service, _ = _build_service(
        monkeypatch,
        rows=[_row(current_qty=45, checklist_sales_90d=None)],
    )

    result = await service.get_sku_clearance_ranking(min_restock_days=0)

    assert result.items[0].checklist_dos_sales90 is None


# ----------------------------------------------------------------------
# 端点的排序白名单
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_accepts_new_sort_fields_and_rejects_legacy_ones(monkeypatch):
    """端点的 sort_by 白名单必须与 service 一致（旧值要 422，不能 500）。"""
    from httpx import ASGITransport, AsyncClient
    from fastapi import FastAPI

    from backend.dependencies.auth import get_current_user
    from backend.domains.business.routers import inventory_domain
    from backend.models.database import get_async_db

    app = FastAPI()
    app.include_router(inventory_domain.router)

    async def override_get_async_db():
        yield None

    async def override_current_user():
        return type("U", (), {"user_id": 1, "id": 1, "roles": []})()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        accepted = await client.get(
            "/api/inventory/clearance-ranking",
            params={"sort_by": "days_since_restock"},
        )
        legacy = await client.get(
            "/api/inventory/clearance-ranking",
            params={"sort_by": "age_days"},
        )

    # service 拿不到真实 db 时返回空结果，但**不应该**因为 sort_by 报错
    assert accepted.status_code == 200
    assert legacy.status_code == 422


# ----------------------------------------------------------------------
# 视图 SQL 的静态门禁
# ----------------------------------------------------------------------


def _view_sql() -> str:
    return VIEW_SQL_PATH.read_text(encoding="utf-8", errors="replace")


def _view_sql_body() -> str:
    """去掉 `--` 注释，只留可执行 SQL。

    文件头写了不少「为什么不用 backlog_base」「为什么定价不在视图里」的说明，
    注释里出现这些词是**应该**的，门禁只针对真正执行的语句。
    """
    body = [
        line
        for line in _view_sql().splitlines()
        if not line.strip().startswith("--")
    ]
    return "\n".join(body)


def test_clearance_view_does_not_use_the_slow_backlog_base_path():
    """视图不得退回 mart.inventory_backlog_base 取数。

    这条是**性能门禁**，不是洁癖：`mart.inventory_backlog_base` 的 sales_30d 用
    `metric_date::date` 过滤，谓词下不进 semantic.fact_orders_atomic 的底层扫描，
    实测单这一段就要 8.8 秒（视图明细查询整体 8867ms），交互页面不可接受。

    库存/滞留列改从 mart.inventory_snapshot_change 取：它与 mart.inventory_snapshot_latest
    共用同一个 company_daily CTE 和同一个 ROW_NUMBER 窗口 PARTITION BY，
    rank=1 的 available_stock / on_hand_stock / inventory_value 完全等价，代价只有 48ms。
    """
    sql_text = _view_sql_body()

    assert "mart.inventory_backlog_base" not in sql_text, (
        "视图不能引用 mart.inventory_backlog_base：它的销售 CTE 要 8.8 秒，"
        "会让滞销清单页面变成 11 秒的慢查询"
    )
    assert "mart.inventory_state" in sql_text, (
        "主判据应改从 mart.inventory_state 取（距上次进货天数）"
    )


def test_clearance_view_restricts_sales_to_platforms_with_inventory():
    """销售聚合必须限定在「有库存的平台」。

    `platform_code = ANY(ARRAY(SELECT DISTINCT platform_code FROM mart.inventory_state))`
    是 InitPlan → 常量数组 → 谓词能下推到 fact_orders_atomic 的 UNION ALL 分支，
    实测 21.0s → 12ms。

    不改变任何数字：销售与库存的连接键含 platform_code，没有库存的平台
    其销售行本来也匹配不上。
    """
    sql_text = _view_sql_body()

    assert "ARRAY(SELECT DISTINCT platform_code FROM mart.inventory_state)" in sql_text, (
        "销售 CTE 必须限定在有库存的平台，否则 fact_orders_atomic 全量求值要 21 秒"
    )
    assert "semantic.fact_orders_atomic" in sql_text


def test_clearance_view_keeps_pricing_formulas_out_of_sql():
    """定价公式只在 product_pricing_service 一处，视图里不重写。

    允许出现 `min_selling_price_override`——那是**原料**（人工覆盖价），
    不是算出来的最低售价。
    """
    sql_text = _view_sql_body()

    computed_pricing = re.findall(r"min_selling_price(?!_override)", sql_text)
    assert not computed_pricing, (
        "视图里不能出现算出来的 min_selling_price："
        "定价口径必须只留 product_pricing_service 一处"
    )
    for forbidden in (
        "AS current_discount_rate",
        "AS clearance_max_discount_rate",
        "discount_guard",
        "cost_floor",
        "target_margin_rate",
    ):
        assert forbidden not in sql_text, (
            f"视图里出现 {forbidden}：定价口径必须只留 product_pricing_service 一处"
        )

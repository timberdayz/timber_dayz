"""库龄分档「彻底一致」的守护测试。

背景
----
旧看板分档是 ``<30 / 90~180 / >=180``（**30~90 天整段无档**），
业务定价档位却是 ``0 / 60 / 90 / 120`` ⇒ 同一批货在两套体系里结论相反
（「商品中心说该打折、看板说活跃」）；而且行数 / SKU 数只覆盖 <30 的行，
与「货值是全量」自相矛盾。

守三件事
--------
1. **SQL 视图的档位分组 == Python 唯一实现**（逐档 value / row_count / sku_count）；
2. **SQL 视图用的门槛 == Python 唯一实现的门槛**
   （业务改档位表必须被看见，不许两边各写一份）；
3. **档位互斥且可加**：各档货值加起来 == 总货值，各档 SKU 数加起来 == 总 SKU 数
   ⇒ 「货值是全量、行数只覆盖一部分」这种自相矛盾不得复发。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from backend.services.inventory.inventory_restock_service import (
    RESTOCK_TIER_THRESHOLDS,
    build_restock_tier_buckets,
    normalize_policy_tier_buckets,
)
from backend.services.postgresql_dashboard_service import (
    summarize_inventory_backlog_rows,
)


VIEW_SQL_PATH = (
    Path(__file__).resolve().parents[3]
    / "sql"
    / "api_modules"
    / "inventory_backlog_summary_module.sql"
)

#: 业务定价档位表当前生效的四行（与迁移
#: ``20261020_sku_pricing_guardrails`` / ``20261120_rename_pricing_tier_labels`` 一致）。
POLICY_ROWS = [
    (0, "日常"),
    (60, "库龄≥60天"),
    (90, "库龄≥90天"),
    (120, "库龄≥120天"),
]


async def _apply_view_sql(session) -> None:
    """把视图 SQL 文件逐条执行到测试库。"""
    sql_text = VIEW_SQL_PATH.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql_text.split(";") if part.strip()]
    assert len(statements) >= 2
    for statement in statements:
        result = await session.execute(text(statement))
        if hasattr(result, "close"):
            result.close()


@pytest.fixture
async def tier_env(pg_session):
    """建出最小可用的 mart / api / finance 资产并灌入夹具数据。"""
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS mart"))
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS api"))
    await pg_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mart.inventory_backlog_base (
                platform_code varchar(32),
                product_sku text,
                warehouse_name text,
                available_stock numeric(18, 4),
                inventory_value numeric(18, 4),
                days_since_restock integer
            )
            """
        )
    )
    await pg_session.execute(text("DELETE FROM finance.sku_pricing_policies"))
    for min_days, label in POLICY_ROWS:
        await pg_session.execute(
            text(
                """
                INSERT INTO finance.sku_pricing_policies
                    (min_restock_days, tier_label, discount_rate, target_margin_rate,
                     platform_basis, effective_from, status, source, version)
                VALUES (:min_days, :label, 0.1, 0.2, 'company', CURRENT_DATE,
                        'active', 'test', 'v1')
                """
            ),
            {"min_days": min_days, "label": label},
        )
    await pg_session.execute(text("DELETE FROM mart.inventory_backlog_base"))
    await _apply_view_sql(pg_session)
    await pg_session.flush()
    yield pg_session
    await pg_session.rollback()


async def _insert_rows(session, rows: list[dict[str, Any]]) -> None:
    await session.execute(
        text(
            """
            INSERT INTO mart.inventory_backlog_base
                (platform_code, product_sku, warehouse_name, available_stock,
                 inventory_value, days_since_restock)
            VALUES (:platform_code, :product_sku, :warehouse_name, :available_stock,
                    :inventory_value, :days_since_restock)
            """
        ),
        rows,
    )
    await session.flush()


def _row(sku: str, warehouse: str, days, value: float, stock: float) -> dict[str, Any]:
    return {
        "platform_code": "shopee",
        "product_sku": sku,
        "warehouse_name": warehouse,
        "available_stock": stock,
        "inventory_value": value,
        "days_since_restock": days,
    }


async def _view_buckets(session) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT restock_tiers, total_value, total_row_count, total_sku_count,
                           unknown_restock_row_count
                    FROM api.inventory_backlog_summary_module
                    """
                )
            )
        )
        .mappings()
        .first()
    )
    assert row is not None
    data = dict(row)
    buckets = normalize_policy_tier_buckets(data["restock_tiers"])
    return buckets, data


async def _python_buckets(session) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT platform_code, product_sku, warehouse_name, available_stock,
                           inventory_value, days_since_restock
                    FROM mart.inventory_backlog_base
                    """
                )
            )
        )
        .mappings()
        .all()
    )
    row_dicts = [dict(row) for row in rows]
    summary = summarize_inventory_backlog_rows(row_dicts)
    tier_summary = build_restock_tier_buckets(row_dicts)
    return summary["restock_tiers"], {
        "total_value": tier_summary["total_value"],
        "total_row_count": tier_summary["total_row_count"],
        "total_sku_count": tier_summary["total_sku_count"],
        "unknown_restock_row_count": tier_summary["unknown_row_count"],
    }


@pytest.mark.asyncio
async def test_view_tiers_match_python_unique_implementation(tier_env):
    """SQL 视图的分组必须与 Python 唯一实现**逐档相同**。"""
    await _insert_rows(
        tier_env,
        [
            _row("SKU-A", "仓1", 10, 100.0, 5.0),
            # 同一个 SKU 的第二个仓：库龄更长 ⇒ 整个 SKU 归到更长那一档
            _row("SKU-A", "仓2", 70, 200.0, 3.0),
            _row("SKU-B", "仓1", 95, 50.0, 1.0),
            _row("SKU-C", "仓1", 130, 25.0, 2.0),
        ],
    )

    view_buckets, view_totals = await _view_buckets(tier_env)
    python_buckets, python_totals = await _python_buckets(tier_env)

    assert len(view_buckets) == len(python_buckets) == 4
    for view_bucket, python_bucket in zip(view_buckets, python_buckets):
        assert view_bucket["tier"] == python_bucket["tier"]
        assert view_bucket["label"] == python_bucket["label"]
        assert view_bucket["threshold_days"] == python_bucket["threshold_days"]
        assert view_bucket["value"] == pytest.approx(python_bucket["value"])
        assert view_bucket["row_count"] == python_bucket["row_count"]
        assert view_bucket["sku_count"] == python_bucket["sku_count"]

    assert view_totals["total_value"] == pytest.approx(python_totals["total_value"])
    assert view_totals["total_row_count"] == python_totals["total_row_count"]
    assert view_totals["total_sku_count"] == python_totals["total_sku_count"]
    assert (
        view_totals["unknown_restock_row_count"]
        == python_totals["unknown_restock_row_count"]
    )


@pytest.mark.asyncio
async def test_tier_buckets_are_mutually_exclusive_and_additive(tier_env):
    """档位互斥且可加：货值与 SKU 数加起来正好等于总数。"""
    await _insert_rows(
        tier_env,
        [
            _row("SKU-A", "仓1", 10, 100.0, 5.0),
            _row("SKU-A", "仓2", 70, 200.0, 3.0),
            _row("SKU-B", "仓1", 95, 50.0, 1.0),
            _row("SKU-C", "仓1", 130, 25.0, 2.0),
        ],
    )

    view_buckets, view_totals = await _view_buckets(tier_env)

    assert sum(bucket["value"] for bucket in view_buckets) == pytest.approx(
        view_totals["total_value"]
    )
    assert (
        sum(bucket["sku_count"] for bucket in view_buckets)
        == view_totals["total_sku_count"]
    )
    assert (
        sum(bucket["row_count"] for bucket in view_buckets)
        == view_totals["total_row_count"]
    )
    # 30~90 天**不再无档**：压60-90天这一档必须有货
    light = next(b for b in view_buckets if b["tier"] == "light")
    assert light["sku_count"] == 1
    assert light["value"] == pytest.approx(300.0)
    assert light["row_count"] == 2


@pytest.mark.asyncio
async def test_unknown_restock_rows_are_not_counted_into_any_tier(tier_env):
    """库龄取不到的行**不落任何档**，但要被单独暴露出来。"""
    await _insert_rows(
        tier_env,
        [
            _row("SKU-A", "仓1", 10, 100.0, 5.0),
            # 库龄取不到 + 没有可售库存 ⇒ 算不出库龄 ⇒ 不可算
            _row("SKU-X", "仓1", None, 10.0, 0.0),
        ],
    )

    view_buckets, view_totals = await _view_buckets(tier_env)
    python_buckets, python_totals = await _python_buckets(tier_env)

    assert view_totals["unknown_restock_row_count"] == 1
    assert python_totals["unknown_restock_row_count"] == 1
    for view_bucket, python_bucket in zip(view_buckets, python_buckets):
        assert view_bucket["value"] == pytest.approx(python_bucket["value"])
        assert view_bucket["sku_count"] == python_bucket["sku_count"]
    # 不可算的货值不在任何档里，但仍在总货值里
    assert sum(bucket["value"] for bucket in view_buckets) == pytest.approx(100.0)
    assert view_totals["total_value"] == pytest.approx(110.0)


@pytest.mark.asyncio
async def test_policy_thresholds_match_python_unique_implementation(tier_env):
    """业务定价档位表的门槛必须与 Python 唯一实现**一致**。

    两边各写一份门槛 = 迟早漂移（业务改了档位表，看板还按老口径算）。
    """
    thresholds = (
        (
            await tier_env.execute(
                text(
                    """
                    SELECT min_restock_days
                    FROM finance.sku_pricing_policies
                    WHERE status = 'active' AND effective_to IS NULL
                    ORDER BY min_restock_days
                    """
                )
            )
        )
        .scalars()
        .all()
    )

    assert list(thresholds) == [0] + list(RESTOCK_TIER_THRESHOLDS)

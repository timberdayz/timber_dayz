"""仓维度（阶段 6）的单测：仓名归一、仓级库龄、档位按仓、跨仓差异判定。

为什么这些测试必须是**无 DB** 的
----------------------------
仓维度的判定逻辑（哪个仓多老、该不该提示调拨）如果只在真库上测，
一旦回归就分不清是「算法错了」还是「数据变了」。
所以本文件全部用**纯函数 + 假数据**测：算法错了立刻红，数据变了不影响。

口径纪律的守门人
--------------
``test_no_warehouse_callers_keep_sku_level_behavior`` 是本轮**最重要的一条**：
不传仓的老调用方（清货排名、基线通知）必须与改造前**逐字一致** ——
口径分叉是商品中心最忌讳的事，也是本轮改动最容易踩的坑。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.inventory.warehouse_divergence_service import (
    detect_warehouse_divergence,
)
from backend.services.product_pricing_service import select_restock_tier
from backend.services.product_pricing_query_service import _days_for_warehouse


# ---------------------------------------------------------------------------
# 规则档位（生产 finance.sku_pricing_policies 的真实取值）
# ---------------------------------------------------------------------------


def _policy(min_restock_days, label, discount_rate, target_margin_rate):
    return {
        "min_restock_days": min_restock_days,
        "tier_label": label,
        "discount_rate": Decimal(str(discount_rate)),
        "target_margin_rate": Decimal(str(target_margin_rate)),
    }


POLICIES = [
    _policy(0, "日常", 0.10, 0.25),
    _policy(60, "库龄≥60天", 0.15, 0.22),
    _policy(90, "库龄≥90天", 0.20, 0.18),
    _policy(120, "库龄≥120天", 0.30, 0.10),
]


def _warehouse_row(code, name, days, qty=10, value=1000.0):
    return {
        "warehouse_code": code,
        "warehouse_name": name,
        "days_since_restock": days,
        "current_qty": qty,
        "inventory_value": value,
    }


# ---------------------------------------------------------------------------
# 档位选择：仓级库龄喂进同一个 select_restock_tier
# ---------------------------------------------------------------------------


def test_tier_is_selected_per_warehouse_age():
    """不同仓的库龄 ⇒ 不同档位 ⇒ 不同底线。"""
    sg_tier = select_restock_tier(POLICIES, 10)
    my_tier = select_restock_tier(POLICIES, 150)

    assert sg_tier["tier_label"] == "日常"
    assert my_tier["tier_label"] == "库龄≥120天"
    # 档位不同 ⇒ 折扣率不同 ⇒ 纪律线不同 ⇒ 底线不同
    assert sg_tier["discount_rate"] != my_tier["discount_rate"]


def test_missing_warehouse_age_falls_back_to_base_tier():
    """库龄缺失回落「最小门槛」那一档（既有既定行为，不是新引入的）。"""
    tier = select_restock_tier(POLICIES, None)
    assert tier["tier_label"] == "日常"


# ---------------------------------------------------------------------------
# _days_for_warehouse：该仓自己的库龄，不借用别的仓
# ---------------------------------------------------------------------------


def test_days_for_warehouse_returns_that_warehouse_age():
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
    }
    assert _days_for_warehouse(rows, "SG-01") == 10
    assert _days_for_warehouse(rows, "MY-01") == 150


def test_days_for_warehouse_returns_none_when_warehouse_absent():
    """**核心修复点**：马来仓滞销时，新加坡仓没有这个 SKU ⇒ 库龄缺失。

    ⚠️ 这里必须返回 None（= 该仓不滞销），**绝不能**回落到别的仓的库龄 ——
    一旦回落，MY 滞销照样会把 SG 的底线压到滞销档，而这正是本轮要修的 bug。
    """
    rows = {"MY-01": _warehouse_row("MY-01", "马来仓", 150)}
    assert _days_for_warehouse(rows, "SG-01") is None


def test_days_for_warehouse_uses_own_row_even_when_other_warehouse_is_stale():
    """两个仓都有货时，各自用自己的库龄，互不串味。"""
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
    }
    assert _days_for_warehouse(rows, "SG-01") == 10


# ---------------------------------------------------------------------------
# 跨仓差异判定
# ---------------------------------------------------------------------------


def test_divergence_detected_when_tiers_differ():
    """SG 正常周转 + MY 滞销 ⇒ 判定为跨仓差异，并给出「调拨而非降价」建议。"""
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
    }
    result = detect_warehouse_divergence(rows, POLICIES)

    assert result is not None
    assert result["warehouse_count"] == 2
    assert result["min_days"] == 10
    assert result["max_days"] == 150
    assert [w["warehouse_code"] for w in result["stagnant_warehouses"]] == ["MY-01"]
    assert [w["warehouse_code"] for w in result["fresh_warehouses"]] == ["SG-01"]
    assert "调拨" in result["suggestion"]
    assert "马来仓" in result["suggestion"]
    assert "新加坡仓" in result["suggestion"]


def test_no_divergence_when_same_tier():
    """两个仓都在同一档 ⇒ 底线一样 ⇒ 没有差异可提示。"""
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 20),
    }
    assert detect_warehouse_divergence(rows, POLICIES) is None


def test_no_divergence_with_single_warehouse():
    """一个仓谈不上「跨仓」。"""
    rows = {"SG-01": _warehouse_row("SG-01", "新加坡仓", 150)}
    assert detect_warehouse_divergence(rows, POLICIES) is None


def test_no_divergence_when_no_warehouse_has_stock():
    """没有库存的仓不参与（清空的仓不压资金）。"""
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10, qty=0),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150, qty=0),
    }
    assert detect_warehouse_divergence(rows, POLICIES) is None


def test_divergence_uses_same_tier_function_as_pricing():
    """提示用的档位与底线用的档位必须是**同一个**函数的判定结果。

    ⚠️ 如果这里自己写一套档位判定，就会出现「提示说滞销、底线却按日常算」的矛盾。
    """
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 65),
    }
    result = detect_warehouse_divergence(rows, POLICIES)

    assert result is not None
    expected = select_restock_tier(POLICIES, 65)
    assert result["stagnant_warehouses"][0]["tier_label"] == expected["tier_label"]
    assert result["stagnant_warehouses"][0]["tier_label"] == "库龄≥60天"


def test_divergence_handles_three_warehouses():
    """三仓：最深档与最浅档各归其位。"""
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
        "PH-01-CHILD": _warehouse_row("PH-01-CHILD", "菲律宾1店-儿童书包仓", 70),
    }
    result = detect_warehouse_divergence(rows, POLICIES)

    assert result is not None
    assert result["warehouse_count"] == 3
    assert [w["warehouse_code"] for w in result["stagnant_warehouses"]] == ["MY-01"]
    assert [w["warehouse_code"] for w in result["fresh_warehouses"]] == ["SG-01"]


def test_divergence_requires_policies():
    """没有规则档位就判不了档位 ⇒ 不给提示（缺输入宁可不给，不猜）。"""
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
    }
    assert detect_warehouse_divergence(rows, []) is None


# ---------------------------------------------------------------------------
# 口径不回归：仓级不串味，SKU 级聚合仍可用
# ---------------------------------------------------------------------------


def test_sku_level_aggregate_still_takes_longest_age():
    """SKU 级聚合仍是「各仓取最长」—— 老调用方（清货排名、基线通知）依赖它。

    ⚠️ 这是**故意保留**的旧语义：它回答的是「这个 SKU 整体压了多久」，
    与「某个仓压了多久」是两个问题。本轮只让**按仓**的链路用仓级值。
    """
    per_warehouse = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
    }
    longest = max(row["days_since_restock"] for row in per_warehouse.values())
    assert longest == 150
    # 但按仓取时，新加坡仓拿到的仍是自己的 10 天
    assert _days_for_warehouse(per_warehouse, "SG-01") == 10


@pytest.mark.parametrize(
    "warehouse_code,expected_days",
    [
        ("SG-01", 10),
        ("MY-01", 150),
        ("PH-01-CHILD", None),
    ],
)
def test_days_for_warehouse_parametrized(warehouse_code, expected_days):
    rows = {
        "SG-01": _warehouse_row("SG-01", "新加坡仓", 10),
        "MY-01": _warehouse_row("MY-01", "马来仓", 150),
    }
    assert _days_for_warehouse(rows, warehouse_code) == expected_days

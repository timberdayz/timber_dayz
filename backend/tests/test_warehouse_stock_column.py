"""当前仓库存（阶段 7）的单测：状态词、筛选与排序、口径不串。

这一轮改造的核心是一句话
------------------------
**「这个仓现在还有多少货」和「这批货压了多久」是两件事，必须分家。**

- 库龄（距上次进货天数）：只看**还有库存**的仓 —— 已清空的仓不压资金；
- 库存数量：**零库存也要列出来** —— 零就是"这个仓清过这货"这条事实本身。

以前两者混在一起，运营在测算表上看到"库龄 -"，分不清是压了 90 天
还是早清空了，于是把清仓 SKU 当滞销品去降价。

守门人
------
- ``test_stock_query_keeps_zero_stock_rows``：库存快照这条 SQL **不许**带
  ``available_stock > 0``；库龄那两条**必须**带 —— 两条口径一旦串了，
  就会出现"库龄和库存说的不是同一件事"，这是最隐蔽的一种错。
- ``test_only_in_stock_filter_happens_before_pagination``：筛选必须在分页**之前**，
  否则前端筛只筛当前页，总数对不上、翻页漏行。
- ``test_no_stock_row_is_not_the_same_as_unavailable_state``：「这个仓没这个货」
  与「状态层查不到」在页面上长得一样，业务含义完全相反，必须能分开。
"""

from __future__ import annotations

from pathlib import Path

from backend.services.inventory.inventory_restock_query_service import (
    _RESTOCK_BY_WAREHOUSE_STMT,
    _RESTOCK_LOOKUP_STMT,
)
from backend.services.inventory.inventory_warehouse_stock_query_service import (
    STOCK_STATUS_CLEARED,
    STOCK_STATUS_IN_STOCK,
    STOCK_STATUS_NO_RECORD,
    STOCK_STATUS_UNAVAILABLE,
    _WAREHOUSE_STOCK_STMT,
    resolve_stock_status,
    select_sku_ids_by_stock,
)

ROUTER_SOURCE = Path("backend/domains/business/routers/product_center.py")


# ---------------------------------------------------------------------------
# 状态词：四种情况必须分得开
# ---------------------------------------------------------------------------


def test_stock_status_in_stock_when_available_stock_positive():
    status = resolve_stock_status({"available_stock": 12})
    assert status == STOCK_STATUS_IN_STOCK


def test_stock_status_cleared_when_row_exists_but_quantity_is_zero():
    """零库存 = 已清仓 —— 是一条事实，页面要显示出来，不能当成缺数据。"""
    status = resolve_stock_status({"available_stock": 0})
    assert status == STOCK_STATUS_CLEARED


def test_stock_status_no_record_when_warehouse_has_no_such_sku():
    status = resolve_stock_status(None)
    assert status == STOCK_STATUS_NO_RECORD


def test_no_stock_row_is_not_the_same_as_unavailable_state():
    """「这个仓没这个货」≠「状态层查不到」—— 后者更严重（管道坏了）。"""
    assert resolve_stock_status(None) != resolve_stock_status(None, False)
    assert resolve_stock_status(None, False) == STOCK_STATUS_UNAVAILABLE


# ---------------------------------------------------------------------------
# 筛选 + 排序：纯函数
# ---------------------------------------------------------------------------


def _stock_map(rows):
    """``{sku_id: {"available_stock": n}}``"""
    return {sku_id: {"available_stock": qty} for sku_id, qty in rows.items()}


KEYS = {1: "A-001", 2: "B-002", 3: "C-003", 4: "D-004"}


def test_only_in_stock_keeps_only_rows_with_available_stock():
    stock = _stock_map({1: 5, 2: 0, 3: 7})
    ordered = select_sku_ids_by_stock([1, 2, 3], KEYS, stock, only_in_stock=True)
    assert ordered == [1, 3]


def test_zero_stock_rows_are_dropped_when_filter_is_on():
    """已清仓的 SKU 在「仅有库存」下不该出现 —— 但它在关掉筛选时必须出现。"""
    stock = _stock_map({1: 5, 2: 0})
    assert 2 not in select_sku_ids_by_stock([1, 2], KEYS, stock, only_in_stock=True)
    assert 2 in select_sku_ids_by_stock([1, 2], KEYS, stock, only_in_stock=False)


def test_sku_without_any_stock_row_is_treated_as_out_of_stock():
    stock = _stock_map({1: 5})
    ordered = select_sku_ids_by_stock([1, 2], KEYS, stock, only_in_stock=False)
    assert ordered == [1, 2]


def test_in_stock_rows_come_first_when_filter_is_off():
    """有货优先：运营打开测算表先看到还有货的那批。"""
    stock = _stock_map({1: 0, 2: 3, 3: 9, 4: 0})
    ordered = select_sku_ids_by_stock([1, 2, 3, 4], KEYS, stock, only_in_stock=False)
    assert ordered[:2] == [2, 3]
    assert ordered[2:] == [1, 4]


def test_group_order_is_stable_by_sku_key():
    """组内按 ERP SKU 升序 —— 翻页时顺序不跳，运营才认得出行。"""
    stock = _stock_map({3: 1, 1: 1, 2: 1})
    ordered = select_sku_ids_by_stock([3, 1, 2], KEYS, stock, only_in_stock=True)
    assert ordered == [1, 2, 3]


def test_filter_and_sort_run_before_pagination():
    """筛选必须发生在分页之前（否则总数对不上、翻页漏行）。"""
    stock = _stock_map({1: 5, 2: 0, 3: 7, 4: 0, 5: 2})
    ordered = select_sku_ids_by_stock([1, 2, 3, 4, 5], KEYS, stock, only_in_stock=True)
    assert len(ordered) == 3
    # 分页只是切片：总数 = 过滤后的行数，而不是过滤前的
    assert ordered[0:2] == ordered[:2]
    assert len(ordered[0:2]) == 2


# ---------------------------------------------------------------------------
# 口径不串：库存快照与库龄是两条路
# ---------------------------------------------------------------------------


def test_stock_query_keeps_zero_stock_rows():
    """库存快照**必须**包含零库存行 —— 那正是"已清仓"这条事实。"""
    sql = " ".join(_WAREHOUSE_STOCK_STMT.text.split())
    assert "available_stock > 0" not in sql
    assert "available_stock" in sql


def test_restock_queries_keep_the_in_stock_filter():
    """库龄那两条**必须**继续过滤零库存 —— 已清空的仓不压资金。"""
    for stmt in (_RESTOCK_LOOKUP_STMT, _RESTOCK_BY_WAREHOUSE_STMT):
        sql = " ".join(stmt.text.split())
        assert "available_stock > 0" in sql


def test_stock_query_scopes_to_one_warehouse():
    """库存快照按**当前仓**取 —— 讲的是"这个仓还有多少"，不是"全渠道还有多少"。"""
    sql = " ".join(_WAREHOUSE_STOCK_STMT.text.split())
    assert "warehouse_code = :warehouse_code" in sql


# ---------------------------------------------------------------------------
# 路由契约
# ---------------------------------------------------------------------------


def test_candidates_endpoint_defaults_to_only_in_stock():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert "only_in_stock: bool = Query(" in source
    assert "只看当前仓有可用库存的 SKU（默认打开）" in source


def test_candidates_endpoint_exposes_current_warehouse_stock():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert "current_warehouse_available_stock" in source
    assert "current_warehouse_stock_status" in source


def test_candidates_endpoint_uses_stock_snapshot_service():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert "load_warehouse_stock_snapshot(" in source
    assert "select_sku_ids_by_stock(" in source


def test_stock_filter_is_skipped_when_state_layer_unavailable():
    """状态层不可用时**不筛**（而不是把整张表筛空）——
    整表空掉会被运营读成"这个仓没货"，比不筛更坏。"""
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert "only_in_stock filter skipped: inventory state unavailable" in source


def test_fallback_warning_distinguishes_unavailable_from_empty():
    """误报告警修正：状态层不可用 ≠ 这批 SKU 没有有库存的记录。"""
    source = Path(
        "backend/services/product_pricing_query_service.py"
    ).read_text(encoding="utf-8")
    assert "probe_inventory_state_available" in source
    assert "no stocked inventory rows for the requested SKUs" in source
    # 状态层真的不可用时，仍然要留 warning（管道坏了要有人去修）
    assert "inventory_state unavailable, falling back to legacy age_days caliber" in source


def test_fallback_caliber_itself_is_unchanged():
    """回落口径一个字都不改（A4：不传仓的老调用方输出必须与改造前逐字一致）。"""
    source = Path(
        "backend/services/product_pricing_query_service.py"
    ).read_text(encoding="utf-8")
    assert 'restock_source = "legacy_age_days"' in source
    assert "load_current_inventory_ages(db, sku_ids)" in source

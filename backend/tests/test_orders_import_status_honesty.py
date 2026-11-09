"""契约测试：订单入库必须如实上报「正式账本是否真的落库」。

背景（SSOT）
------------
旧实现在 ``upsert_orders_v2`` 的循环里「打一行 warning 就 ``return``」。这个
``return`` 直接**结束整个函数**，返回值是 ``None``：

* 调用方执行 ``total_imported += imported`` 会抛
  ``TypeError: unsupported operand type(s) for +=: 'int' and 'NoneType'``，
  被上层当成「文件处理失败」；
* 而真正的真相——「一行都没进订单正式账本」——被彻底掩盖。

订单正式账本现在是 ``b_class.fact_{platform}_orders_{granularity}``（旧的
``FactOrder`` 表已在 v4.19.0 删除），那条写入路径至今未实现。本测试锁死两件事：

1. ``upsert_orders`` **绝不返回 None**（不能再让调用方炸 TypeError）；
2. 未落正式账本时，结果里必须带着 ``fact_imported=False`` 和原因说明。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


class _FakeDB:
    """最小可用的 db 替身：只需要 ``bind.url`` 供方言判断。"""

    bind = SimpleNamespace(url="postgresql://user:pass@localhost:5432/xihong_erp")


def _run(coro):
    return asyncio.run(coro)


def _upsert_orders(rows):
    from backend.services.data_importer import upsert_orders

    return _run(upsert_orders(_FakeDB(), rows))


def test_upsert_orders_never_returns_none():
    """回归点：旧实现返回 None，调用方 `+= imported` 直接 TypeError。"""
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "order_id": "order-1",
            "total_amount": 12.5,
        }
    ]

    result = _upsert_orders(rows)

    assert result is not None, "upsert_orders 绝不能返回 None（旧实现会让调用方 TypeError）"
    assert isinstance(result, int)


def test_upsert_orders_reports_fact_import_status():
    """未落正式账本时必须显式标记，并给出原因。"""
    from backend.services.data_importer import ORDERS_FACT_IMPORT_NOTE

    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "order_id": "order-1",
            "total_amount": 12.5,
        }
    ]

    result = _upsert_orders(rows)

    assert result.fact_imported is False, "正式账本未落库时 fact_imported 必须为 False"
    assert result.note, "必须说明为什么没有落库，不能静默"
    assert ORDERS_FACT_IMPORT_NOTE in result.note
    assert int(result) == 0, "没有真正落库时，入库条数必须为 0"


def test_upsert_orders_with_no_rows_has_no_debt():
    """没有可入库的行 ⇒ 没有欠账，fact_imported 为真。"""
    from backend.services.data_importer import upsert_orders

    result = _run(upsert_orders(_FakeDB(), []))

    assert result is not None
    assert int(result) == 0
    assert result.fact_imported is True


def test_upsert_orders_result_supports_arithmetic():
    """结果必须能直接参与累加（调用方就是这么用的）。"""
    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "shop-1",
            "order_id": "order-1",
        }
    ]

    total_imported = 0
    total_imported += _upsert_orders(rows)

    assert total_imported == 0


def test_callers_surface_the_status():
    """调用方必须把状态透出到响应里，否则「显形」就白做了。"""
    targets = [
        "backend/domains/data_platform/routers/field_mapping_files.py",
        "backend/domains/data_platform/routers/field_mapping_ingest.py",
        "backend/tasks/data_processing.py",
    ]
    for rel in targets:
        source = (ROOT / rel).read_text(encoding="utf-8-sig")
        assert "orders_fact_imported" in source, (
            f"{rel} 必须把 orders_fact_imported 透出到响应/结果里"
        )

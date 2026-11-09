"""契约测试：慢查询必须读物化视图，而不是普通视图。

背景
----
``semantic.fact_orders_atomic`` 是**普通视图**：每行都要跑一次店铺别名解析
（LEFT JOIN LATERAL → semantic.shop_identity_resolution_candidates），
9 张 B 类事实表全量扫描 + 逐行 JSON 解析 + 逐行身份解析。

实测（本地，同一段查询，EXPLAIN ANALYZE）：

======================  ========
数据源                    耗时
======================  ========
``semantic.fact_orders_atomic``    23.53 秒
``semantic.fact_orders_atomic_mv``  0.30 秒
======================  ========

两者结果完全一致。生产更严重：物化视图的创建脚本里记录过
``SELECT count(*) FROM semantic.fact_orders_atomic`` 要 **114.6 秒**。

本测试锁死两件事：

1. 「未匹配别名」查询读的是物化视图（不得再退回普通视图）；
2. 别名改动后的刷新目标里**包含**这个物化视图（否则列表永远是旧快照）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTER = (
    ROOT / "backend" / "domains" / "collection" / "routers" / "shop_account_aliases.py"
)


def _read_router() -> str:
    return ROUTER.read_text(encoding="utf-8-sig")


def test_unmatched_alias_query_reads_materialized_view():
    source = _read_router()

    assert (
        "FROM semantic.fact_orders_atomic_mv" in source
    ), "未匹配别名查询必须读物化视图（实测 23.53s → 0.30s，结果一致）"
    assert (
        "FROM semantic.fact_orders_atomic\n" not in source
    ), "不得再直读普通视图 semantic.fact_orders_atomic（那是 20~114 秒的来源）"


def test_alias_change_refreshes_the_snapshot_the_query_reads():
    """别名改了必须刷新本查询读的物化副本，否则用户认领完还看到旧列表。"""
    from backend.domains.collection.routers.shop_account_aliases import (
        _SHOP_IDENTITY_REFRESH_TARGETS,
    )

    assert (
        "semantic.fact_orders_atomic_mv" in _SHOP_IDENTITY_REFRESH_TARGETS
    ), "别名改动后的刷新目标必须包含 fact_orders_atomic_mv"
    assert "semantic.shop_identity_resolution_candidates_v2_mv" in (
        _SHOP_IDENTITY_REFRESH_TARGETS
    )


def test_view_file_documents_the_materialized_view_rule():
    """视图文件本身要写清「消费方读 MV」，避免下一个人重复踩坑。"""
    sql_text = (ROOT / "sql" / "semantic" / "orders_atomic.sql").read_text(
        encoding="utf-8-sig"
    )

    assert (
        "semantic.fact_orders_atomic_mv" in sql_text
    ), "视图文件必须写明消费方应读物化视图"

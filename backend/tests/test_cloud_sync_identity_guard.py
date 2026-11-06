"""同步侧「身份自洽」拦截的守护测试(WP-4)。

背景
----
云同步的 upsert 冲突键是 ``(platform_code, shop_id, data_domain, granularity,
data_hash)``, 而 ``data_hash`` **不含 raw_data** ⇒ 两行只要核心业务字段相同就会
撞到同一个冲突键。

于是本地第二行(列 ``shop_id``=A、raw_data 身份=**B**) 命中冲突键后,
``DO UPDATE`` 把 raw_data 改成 B 的 ⇒ 云端留下一行「列是 A、内容是 B」的**混合行**。
这是同步侧的**放大器**。

本测试盯住两件事
----------------
1. **不自洽的行不写云端** —— 宁可少同步一行, 也不把混合行搬进云端;
2. **``shop_id`` 与 ``raw_data`` 绑定** —— 两者同进同退, 不再一个动一个不动。
"""

from __future__ import annotations

from backend.services.cloud_b_class_sync_service import (
    SQLAlchemyCloudWriter,
    split_rows_by_identity_consistency,
)


def _row(shop_id, raw_shop_id=None, raw_platform_shop_id=None, **extra):
    raw_data = {"shop_account_id": "shopee_sg_xhkj11_local"}
    if raw_shop_id is not None:
        raw_data["shop_id"] = raw_shop_id
    if raw_platform_shop_id is not None:
        raw_data["platform_shop_id"] = raw_platform_shop_id
    row = {
        "platform_code": "shopee",
        "shop_id": shop_id,
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "metric_date": "2026-06-22",
        "raw_data": raw_data,
        "data_hash": "hash-1",
    }
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# 分流
# ---------------------------------------------------------------------------


def test_consistent_row_is_kept():
    """列与 raw_data 同源 ⇒ 照常同步。"""
    rows = [_row("1308200825", raw_shop_id="1308200825")]
    consistent, conflicting = split_rows_by_identity_consistency(rows)
    assert len(consistent) == 1
    assert conflicting == []


def test_column_vs_raw_data_mismatch_is_conflicting():
    """列是 A、raw_data 是 B ⇒ 混合行 ⇒ 不写云端。"""
    rows = [_row("1308200825", raw_shop_id="1419169771")]
    consistent, conflicting = split_rows_by_identity_consistency(rows)
    assert consistent == []
    assert len(conflicting) == 1


def test_platform_shop_id_vs_shop_id_mismatch_is_conflicting():
    """raw_data 内部两个编号互相矛盾 ⇒ 也是混合行。"""
    rows = [_row("1308200825", raw_shop_id="1308200825", raw_platform_shop_id="1419169771")]
    consistent, conflicting = split_rows_by_identity_consistency(rows)
    assert consistent == []
    assert len(conflicting) == 1


def test_empty_values_are_not_treated_as_conflict():
    """空值没有可比基准 ⇒ 不算矛盾(否则会大面积误杀)。"""
    rows = [_row("", raw_shop_id="")]
    consistent, conflicting = split_rows_by_identity_consistency(rows)
    assert len(consistent) == 1
    assert conflicting == []


def test_missing_raw_data_is_not_treated_as_conflict():
    """没有 raw_data 就无从判矛盾 ⇒ 照常同步。"""
    rows = [_row("1308200825")]
    rows[0]["raw_data"] = None
    consistent, conflicting = split_rows_by_identity_consistency(rows)
    assert len(consistent) == 1
    assert conflicting == []


def test_mixed_batch_is_split_correctly():
    """一批里自洽与矛盾的行要分得干净。"""
    rows = [
        _row("1308200825", raw_shop_id="1308200825"),
        _row("1419169771", raw_shop_id="9999999"),
        _row("1308200826", raw_shop_id="1308200826"),
    ]
    consistent, conflicting = split_rows_by_identity_consistency(rows)
    assert len(consistent) == 2
    assert len(conflicting) == 1
    assert conflicting[0]["shop_id"] == "1419169771"


# ---------------------------------------------------------------------------
# upsert 语句: shop_id 与 raw_data 绑定
# ---------------------------------------------------------------------------


def test_shop_id_is_updated_together_with_raw_data():
    """``shop_id`` 必须与 ``raw_data`` 同进同退 —— 不能一个更新一个不动。

    ⚠️ 以前 ``shop_id`` 被排除在更新集之外, 而 ``raw_data`` 会被更新
    ⇒ 两者一拆开就必然产生「列是 A、内容是 B」的混合行。
    """
    writer = SQLAlchemyCloudWriter(engine=None)
    sql = writer._build_upsert_sql("fact_shopee_analytics_monthly", "analytics")

    update_clause = sql.split("DO UPDATE SET", 1)[1]
    assert "shop_id = EXCLUDED.shop_id" in update_clause
    assert "raw_data = EXCLUDED.raw_data" in update_clause
    # 冲突键与作用域列仍然不更新
    assert "platform_code = EXCLUDED.platform_code" not in update_clause
    assert "data_hash = EXCLUDED.data_hash" not in update_clause


def test_conflict_clauses_unchanged():
    """冲突键不许动(动了会重复入库)。"""
    writer = SQLAlchemyCloudWriter(engine=None)
    assert (
        "ON CONFLICT (platform_code, shop_id, data_domain, granularity, data_hash)"
        in writer._build_upsert_sql("fact_shopee_analytics_monthly", "analytics")
    )
    assert (
        "ON CONFLICT (data_domain, sub_domain, granularity, data_hash)"
        in writer._build_upsert_sql("fact_shopee_services_agent_daily", "services")
    )


# ---------------------------------------------------------------------------
# 写入入口
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self):
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))


class _FakeEngine:
    def __init__(self):
        self.conn = _FakeConn()

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc_info):
        return False


def test_writer_skips_conflicting_rows_and_reports_count():
    """冲突行不写云端, 且计数要报出来(可观测)。"""
    engine = _FakeEngine()
    writer = SQLAlchemyCloudWriter(engine=engine)
    rows = [
        _row("1308200825", raw_shop_id="1308200825"),
        _row("1419169771", raw_shop_id="9999999"),
    ]

    result = writer("fact_shopee_analytics_monthly", rows, "analytics")

    assert result["written_rows"] == 1
    assert result["identity_conflict_rows"] == 1
    assert len(engine.conn.executed) == 1
    # 只写进了那一行自洽的
    written_params = engine.conn.executed[0][1]
    assert [p["shop_id"] for p in written_params] == ["1308200825"]

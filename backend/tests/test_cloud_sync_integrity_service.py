"""E 项守护: 云端同步链路的完整性巡检(陈旧 / 收敛率 / 候选池平台)。

事故背景
--------
2026-11-07 的采集同步丢数事故里, 三个信号**同时**存在, 而一个都没人看见:

1. 云端事实表停在 11-06 —— 同步链断了;
2. 行内身份收敛率恒为 0 —— 入库侧枚举 bug 让收敛 100% 静默失效;
3. 候选池缺平台 —— ``miaoshou`` 的采集源账号不在候选池里。

本文件守住这条巡检链: 三项检查必须**各自能独立报警**,
且**不能**因为「没有身份线索的行」而误报。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.services.data_pipeline.cloud_sync_integrity_service import (
    classify_convergence,
    classify_sync_freshness,
    collect_candidate_pool_coverage,
    collect_identity_convergence,
)
from backend.services.shop_identity_reconciliation_service import build_identity_index


NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

ACCOUNTS = [
    {
        "id": 1,
        "shop_account_id": "shopee_sg_hx_home_local",
        "platform": "shopee",
        "platform_shop_id": "1391124228",
        "store_name": "hx_home.sg",
        "shop_region": "SG",
        "enabled": True,
        "business_role": "operating_store",
    },
    {
        "id": 2,
        "shop_account_id": "shopee_ph_xhkj11_local",
        "platform": "shopee",
        "platform_shop_id": "1419169771",
        "store_name": "xhkj11.ph",
        "shop_region": "PH",
        "enabled": True,
        "business_role": "operating_store",
    },
]

INDEX = build_identity_index(ACCOUNTS, [])


# ---------------------------------------------------------------------------
# ① 云端同步新鲜度
# ---------------------------------------------------------------------------


def test_fresh_cloud_chain_is_not_stale():
    status, age = classify_sync_freshness(
        row_count=100,
        max_ingest_timestamp=NOW - timedelta(hours=3),
        now=NOW,
        max_age_days=2,
    )
    assert status == "fresh"
    assert age == 0


def test_stale_cloud_chain_is_detected():
    """★ 云端数据停更 ⇒ 报警(这正是事故形态)。"""
    status, age = classify_sync_freshness(
        row_count=100,
        max_ingest_timestamp=NOW - timedelta(days=9),
        now=NOW,
        max_age_days=2,
    )
    assert status == "stale"
    assert age == 9


def test_empty_cloud_table_is_only_informational():
    """空表只提示, 不算断流(可能本来就没开这条采集)。"""
    status, age = classify_sync_freshness(
        row_count=0,
        max_ingest_timestamp=None,
        now=NOW,
        max_age_days=2,
    )
    assert status == "empty"
    assert age is None


# ---------------------------------------------------------------------------
# ② 身份收敛率
# ---------------------------------------------------------------------------


def test_convergence_rate_counts_only_rows_with_identity():
    """★ 分母只算「行内带了身份线索」的行。

    没有身份线索的行(比如 miaoshou 采集链上的 ``xihong``)无从判定,
    算进去只会稀释指标、淹没真正的告警。
    """
    status, rate = classify_convergence(
        sampled_rows=10,
        rows_with_identity=4,
        converged_rows=4,
        min_rate=0.8,
    )
    assert status == "ok"
    assert rate == 1.0


def test_low_convergence_rate_is_degraded():
    """★ 收敛率掉下来 ⇒ 报警(这正是 A 项 bug 的形态)。"""
    status, rate = classify_convergence(
        sampled_rows=10,
        rows_with_identity=10,
        converged_rows=0,
        min_rate=0.8,
    )
    assert status == "degraded"
    assert rate == 0.0


def test_rows_without_identity_do_not_trigger_alarm():
    """全部行都没有身份线索 ⇒ ``unknown``, 不报警。"""
    status, rate = classify_convergence(
        sampled_rows=10,
        rows_with_identity=0,
        converged_rows=0,
        min_rate=0.8,
    )
    assert status == "unknown"
    assert rate is None


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows


class _FakeAsyncSession:
    """按 SQL 片段返回预设结果的最小 AsyncSession 替身。"""

    def __init__(self, responses: list[tuple[str, list[Any]]]) -> None:
        self._responses = responses
        self.executed: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append(sql)
        for snippet, rows in self._responses:
            if snippet in sql:
                return _FakeResult(rows)
        return _FakeResult([])


def test_collect_identity_convergence_counts_resolvable_rows():
    """★ 端到端: 抽样行的归属情况被正确分类。"""
    rows = [
        # 唯一归属 ⇒ 收敛
        ({"platform_shop_id": "1391124228"}, "shopee"),
        # 认不到账号(停用店) ⇒ 未归属
        ({"shop_account_id": "shopee_sg_gone_local"}, "shopee"),
        # 两个身份键指向不同账号 ⇒ 矛盾
        (
            {
                "platform_shop_id": "1391124228",
                "shop_account_id": "shopee_ph_xhkj11_local",
            },
            "shopee",
        ),
        # 没有身份线索(采集方代号)⇒ 不进分母
        ({"shop_id": "xihong"}, "shopee"),
    ]
    db = _FakeAsyncSession(
        [("SELECT raw_data, platform_code", rows)]
    )

    result = asyncio.run(
        collect_identity_convergence(
            db,
            table_names=["fact_shopee_orders_daily"],
            identity_index=INDEX,
            min_rate=0.8,
        )
    )

    assert len(result) == 1
    row = result[0]
    assert row.sampled_rows == 4
    assert row.rows_with_identity == 3, "没有身份线索的行不该进分母"
    assert row.converged_rows == 1
    assert row.unresolved_rows == 1
    assert row.conflicting_rows == 1
    assert row.status == "degraded"
    assert row.convergence_rate == pytest.approx(1 / 3)


def test_collect_identity_convergence_ok_when_all_rows_resolve():
    """全部行都能唯一归属 ⇒ ``ok``。"""
    rows = [
        ({"platform_shop_id": "1391124228"}, "shopee"),
        ({"platform_shop_id": "1419169771"}, "shopee"),
    ]
    db = _FakeAsyncSession([("SELECT raw_data, platform_code", rows)])

    result = asyncio.run(
        collect_identity_convergence(
            db,
            table_names=["fact_shopee_orders_daily"],
            identity_index=INDEX,
            min_rate=0.8,
        )
    )

    assert result[0].status == "ok"
    assert result[0].convergence_rate == 1.0


# ---------------------------------------------------------------------------
# ③ 候选池平台覆盖
# ---------------------------------------------------------------------------


def test_missing_candidate_platform_is_detected():
    """★ 主数据里有在营经营店的平台, 候选池里却没有 ⇒ 报警。

    这正是 2026-11 实测到的形态: ``miaoshou`` 的采集源账号不在候选池里,
    那条链的身份从一开始就解析不出来。
    """
    db = _FakeAsyncSession(
        [
            ("FROM core.shop_accounts", [("shopee",), ("miaoshou",)]),
            (
                "FROM semantic.shop_identity_resolution_candidates",
                [("shopee", 138)],
            ),
        ]
    )

    rows = asyncio.run(collect_candidate_pool_coverage(db))

    by_platform = {row.platform_code: row for row in rows}
    assert by_platform["shopee"].status == "ok"
    assert by_platform["miaoshou"].status == "missing"
    assert by_platform["miaoshou"].candidate_rows == 0


def test_candidate_platform_present_is_ok():
    db = _FakeAsyncSession(
        [
            ("FROM core.shop_accounts", [("shopee",), ("tiktok",)]),
            (
                "FROM semantic.shop_identity_resolution_candidates",
                [("shopee", 138), ("tiktok", 24)],
            ),
        ]
    )

    rows = asyncio.run(collect_candidate_pool_coverage(db))

    assert all(row.status == "ok" for row in rows)

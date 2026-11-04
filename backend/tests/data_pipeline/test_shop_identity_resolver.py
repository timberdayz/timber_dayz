"""契约测试：三条链路（products / services / inventory）必须接入身份解析。

背景
----
语义层有 5 条链路：orders / analytics / products / services / inventory。
以前**只有 orders 与 analytics 做了身份解析**（每行跑一次 LEFT JOIN LATERAL，
逻辑在两个文件里各抄了一份）；products / services / inventory 完全没解析，
直接把采集文件里的原始 shop_id 透传出去 ⇒

- 同一个店在不同链路里是三种键（平台店铺ID / 业务店铺ID / 原始店名 / 占位键）
- 库存链路的 4,111 行全部挂在占位键 'xihong' 上 ⇒ 库存看板按店拆不开

这些断言是**口径守护**：任何一条链路被改回「不解析」，测试必须红。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# 三条「以前没做身份解析」的链路
UNRESOLVED_CHAINS = (
    "semantic.fact_products_atomic",
    "semantic.fact_inventory_snapshot",
    "semantic.fact_services_atomic",
)


def _read_asset(target: str) -> str:
    path = REPO_ROOT / SQL_TARGET_PATHS[target]
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("target", UNRESOLVED_CHAINS)
def test_chain_calls_shared_identity_resolver(target: str) -> None:
    """每条链路都必须调用共享解析函数，不能再自己透传原始键。"""
    body = _read_asset(target)
    assert (
        "semantic.resolve_shop_identity(" in body
    ), f"{target} 没有接入身份解析 —— 原始键会被直接透传出去"


@pytest.mark.parametrize("target", UNRESOLVED_CHAINS)
def test_chain_keeps_source_key_and_resolves_after_dedup(target: str) -> None:
    """解析必须发生在去重之后，且去重分区仍用原始键（去重口径零变化）。"""
    body = _read_asset(target)
    assert "source_shop_id" in body, f"{target} 没有保留原始店铺标识"
    assert (
        "PARTITION BY platform_code, source_shop_id, data_hash" in body
    ), f"{target} 的去重分区不再用原始键 —— 去重口径被改动了"


@pytest.mark.parametrize("target", UNRESOLVED_CHAINS)
def test_unmatched_rows_keep_source_key(target: str) -> None:
    """候选为 0（这个店没账号）时必须**保留原始键**，不能抹成 unknown。

    抹成 unknown 等于把「看得见的原始标识」变成「看不出所以然」——
    对 tiktok 的商品采集文件（只带「地区(店名)」这种店名）尤其致命。
    """
    body = _read_asset(target)
    assert "WHEN r.candidate_count = 1 THEN r.resolved_shop_id" in body
    assert (
        "WHEN r.candidate_count > 1 THEN 'unknown'" not in body
    ), f"{target} 把有歧义的行抹成了 unknown —— 会让看板查不到店名"
    assert (
        "ELSE d.source_shop_id" in body
    ), f"{target} 在解析失败时没有保留原始键 —— 会造成信息丢失"


@pytest.mark.parametrize("target", UNRESOLVED_CHAINS)
def test_ambiguous_rows_keep_source_key(target: str) -> None:
    """有歧义（候选 > 1）时也必须保留原始键：既不猜、也不抹。

    原始键是采集文件里数据自己写的（平台店铺ID 还有唯一约束）；
    歧义来自同一个源行的**其它身份路径**命中了别的账号。
    抹成 unknown ⇒ 看板再也查不到店名（显示名 JOIN 靠的正是原始键）；
    猜一个 ⇒ 在编数据。两者都不做。
    """
    body = _read_asset(target)
    assert (
        "WHEN r.candidate_count > 1 THEN 'unknown'" not in body
    ), f"{target} 把有歧义的行抹成了 unknown —— 会让看板查不到店名"
    assert "ELSE d.source_shop_id" in body


@pytest.mark.parametrize("target", UNRESOLVED_CHAINS)
def test_new_columns_are_appended_at_the_end(target: str) -> None:
    """新增列必须追加在末尾 —— CREATE OR REPLACE VIEW 不允许改变已有列顺序。"""
    body = _read_asset(target)
    tail = body[body.rindex("SELECT") :]
    assert "resolved_shop_account_id" in tail
    assert "identity_candidate_count" in tail
    # 末尾两个新增列必须排在所有旧列之后
    assert tail.rindex("resolved_shop_account_id") > tail.rindex("currency_code")


def test_resolver_asset_exists_and_is_registered() -> None:
    assert "semantic.shop_identity_resolver" in SQL_TARGET_PATHS
    assert (
        SQL_TARGET_PATHS["semantic.shop_identity_resolver"]
        == "sql/semantic/shop_identity_resolver.sql"
    )
    for target in UNRESOLVED_CHAINS:
        assert "semantic.shop_identity_resolver" in PIPELINE_DEPENDENCIES[target]


def test_resolver_reads_the_materialized_candidate_copy() -> None:
    """解析函数必须读物化副本（否则每行都要重算候选集 ⇒ N+1 回归）。"""
    body = _read_asset("semantic.shop_identity_resolver")
    assert "semantic.shop_identity_resolution_candidates_v2_mv" in body


def test_resolver_asset_never_drops_anything() -> None:
    """资产里不允许出现 DROP / CASCADE —— 误伤下游不可重建的对象。"""
    body = _read_asset("semantic.shop_identity_resolver").upper()
    assert "DROP " not in body
    assert "CASCADE" not in body


def test_resolver_dependency_order_is_correct() -> None:
    """函数读候选集物化副本 ⇒ 建函数前副本必须已存在。"""
    assert PIPELINE_DEPENDENCIES["semantic.shop_identity_resolver"] == [
        "semantic.shop_identity_resolution_candidates_v2_mv"
    ]
    assert PIPELINE_DEPENDENCIES[
        "semantic.shop_identity_resolution_candidates_v2_mv"
    ] == ["semantic.shop_identity_resolution_candidates"]


def test_resolved_chains_still_deduplicate_on_source_key() -> None:
    """去重口径与改造前逐字一致（否则历史行数会变）。"""
    for target in UNRESOLVED_CHAINS:
        body = _read_asset(target)
        assert "PARTITION BY platform_code, source_shop_id, data_hash" in body
        assert "PARTITION BY platform_code, shop_id, data_hash" not in body

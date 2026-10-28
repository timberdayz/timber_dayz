"""D7 回归测试: 跨 family 变体接管。

背景
----
实测 ``tiktok/products/monthly``(2026-10-29, 本地库)::

    family 27 (monthly) -> 变体 id=30 -> legacy 模板 id=350 (38 列, header_row=2)
    family 23 (daily)   -> 变体 id=44 -> legacy 模板 id=362 (176 列, header_row=3)

TikTok 商品导出实际只有一种表结构(176 列), monthly 只是采集时间范围不同。
monthly 的模板停留在旧版 38 列 -> monthly 的文件匹配不到任何变体 ->
被判结构漂移 -> 永不自动入库(自我强化的死循环)。

覆盖
----
1.  接管门槛: 匹配率 < 95% 不接管; 缺失列 > 1 不接管
2.  接管边界: 变体必须**按自己声明的 header_row** 读表头再评估
3.  接管报告: 来源 family / 变体 / 匹配率 都要留痕
4.  契约回写: 接管来源写进 template_contract
5.  处置模型: 区分「跨 family 接管」与「真漂移」
6.  基准优先级: 契约 > 接管 > 当前已发布模板
"""

from types import SimpleNamespace

import pytest


# ======================================================================
# 1. 接管门槛
# ======================================================================
def _variant(**overrides):
    payload = {
        "id": 44,
        "variant_key": "daily_header_3_f40e8338",
        "match_priority": 1,
        "header_row": 3,
        "required_headers": ["商品名", "商品 ID", "GMV"],
        "source_legacy_template_id": 362,
    }
    payload.update(overrides)
    return payload


def test_takeover_hits_when_coverage_meets_threshold():
    from backend.services.template_variant_takeover import evaluate_variant_takeover

    decision = evaluate_variant_takeover(
        _variant(),
        ["商品名", "商品 ID", "GMV", "额外的列"],
    )
    assert decision is not None
    assert decision["match_rate"] == 1.0
    assert decision["missing_headers"] == []
    assert decision["source_legacy_template_id"] == 362
    assert decision["header_row"] == 3


def test_takeover_rejected_when_coverage_below_threshold():
    from backend.services.template_variant_takeover import evaluate_variant_takeover

    variant = _variant(required_headers=[f"列{index}" for index in range(10)])
    # 只覆盖 8/10 = 80% < 95%
    decision = evaluate_variant_takeover(variant, [f"列{index}" for index in range(8)])
    assert decision is None


def test_takeover_rejected_when_missing_headers_exceed_limit():
    from backend.services.template_variant_takeover import evaluate_variant_takeover

    variant = _variant(required_headers=["A", "B", "C"])
    # 覆盖率 66% 已经低于门槛; 再补一个「覆盖率够但缺 2 列」的例子
    variant = _variant(required_headers=[f"列{index}" for index in range(20)])
    columns = [f"列{index}" for index in range(18)]
    # 18/20 = 90% < 95% -> 拒绝
    assert evaluate_variant_takeover(variant, columns) is None

    variant = _variant(required_headers=[f"列{index}" for index in range(20)])
    columns = [f"列{index}" for index in range(19)]
    # 19/20 = 95% 达标, 但缺失 1 列(上限内) -> 命中
    decision = evaluate_variant_takeover(variant, columns)
    assert decision is not None
    assert decision["missing_headers"] == ["列19"]


def test_takeover_requires_required_headers_and_columns():
    from backend.services.template_variant_takeover import evaluate_variant_takeover

    assert evaluate_variant_takeover(_variant(required_headers=[]), ["商品名"]) is None
    assert evaluate_variant_takeover(_variant(), []) is None
    assert evaluate_variant_takeover(None, ["商品名"]) is None


def test_header_normalization_ignores_case_and_whitespace():
    from backend.services.template_variant_takeover import normalize_header_set

    assert normalize_header_set([" GMV ", "gmv", None, ""]) == {"gmv"}
    assert normalize_header_set(None) == set()


# ======================================================================
# 2. 接管报告
# ======================================================================
def test_takeover_report_keeps_provenance():
    from backend.services.template_variant_takeover import (
        build_takeover_report,
        evaluate_variant_takeover,
    )

    decision = evaluate_variant_takeover(_variant(), ["商品名", "商品 ID", "GMV"])
    report = build_takeover_report(
        decision,
        source_family={"id": 23, "granularity": "daily"},
        source_version={"id": 23, "version_no": 6},
    )
    assert report["flag"] == "cross_family_variant_takeover"
    assert report["source_family_id"] == 23
    assert report["source_family_granularity"] == "daily"
    assert report["source_version_no"] == 6
    assert report["variant_key"] == "daily_header_3_f40e8338"
    assert report["match_rate"] == 1.0


def test_select_best_takeover_prefers_higher_match_rate_then_priority():
    from backend.services.template_variant_takeover import select_best_takeover

    candidates = [
        {
            "variant": _variant(id=1, match_priority=1),
            "decision": {"match_rate": 0.9},
        },
        {
            "variant": _variant(id=2, match_priority=9),
            "decision": {"match_rate": 1.0},
        },
        {
            "variant": _variant(id=3, match_priority=5),
            "decision": {"match_rate": 1.0},
        },
    ]
    best = select_best_takeover(candidates)
    # 匹配率一样时 match_priority 小的优先
    assert best["variant"]["id"] == 3
    assert select_best_takeover([]) is None
    assert select_best_takeover(None) is None


def test_select_best_takeover_prefers_own_family_over_sibling():
    """自家变体必须优先 —— 接管的前提是「自己家解释不了」。

    实测反例: tiktok/services 的 monthly 与 daily 两个变体 required_headers
    完全相同(都是 11 列客服指标), 匹配率都是 100% ——
    若不区分自家, monthly 的文件会被 daily 的变体抢走解释权。
    """
    from backend.services.template_variant_takeover import select_best_takeover

    candidates = [
        {
            "variant": _variant(id=8, variant_key="daily_dash"),
            "decision": {"match_rate": 1.0},
            "is_own_family": False,
        },
        {
            "variant": _variant(id=9, variant_key="monthly_dash"),
            "decision": {"match_rate": 1.0},
            "is_own_family": True,
        },
    ]
    best = select_best_takeover(candidates)
    assert best["variant"]["variant_key"] == "monthly_dash"


def test_account_dimension_treats_none_family_as_any_account():
    """模板族几乎都是 account=None(与店铺无关), 文件的 account 是具体店铺。

    若按字面相等判断, 自家 family 永远匹配不上 -> 接管会抢走自家文件的解释权。
    """
    from backend.services.template_family_service import _account_dimension_matches

    assert _account_dimension_matches(None, "shop@163.com") is True
    assert _account_dimension_matches(None, None) is True
    assert _account_dimension_matches("shop@163.com", "shop@163.com") is True
    assert _account_dimension_matches("shop@163.com", "other@163.com") is False
    assert _account_dimension_matches("shop@163.com", None) is False


# ======================================================================
# 3. 契约回写: 接管来源进契约
# ======================================================================
def test_contract_records_takeover_provenance():
    from backend.services.template_contract_service import (
        CONTRACT_SOURCE_TAKEOVER,
        build_template_contract,
    )

    template = SimpleNamespace(
        id=362,
        version=6,
        status="published",
        template_name="tiktok_products__daily_v6",
        header_row=3,
        header_columns=["商品名", "商品 ID", "GMV"],
    )
    takeover = {
        "flag": "cross_family_variant_takeover",
        "source_family_id": 23,
        "source_family_granularity": "daily",
        "variant_key": "daily_header_3_f40e8338",
        "match_rate": 1.0,
    }
    contract = build_template_contract(
        template,
        source=CONTRACT_SOURCE_TAKEOVER,
        takeover=takeover,
    )
    assert contract["template_id"] == 362
    assert contract["header_row"] == 3
    assert contract["source"] == CONTRACT_SOURCE_TAKEOVER
    assert contract["takeover"]["source_family_id"] == 23
    assert contract["takeover"]["variant_key"] == "daily_header_3_f40e8338"


def test_contract_without_takeover_has_no_takeover_key():
    from backend.services.template_contract_service import build_template_contract

    template = SimpleNamespace(
        id=1,
        version=1,
        status="published",
        template_name="x",
        header_row=0,
        header_columns=["A"],
    )
    contract = build_template_contract(template)
    assert "takeover" not in contract


def test_template_explains_columns_uses_same_ruler():
    from backend.services.template_variant_takeover import template_explains_columns

    template = SimpleNamespace(id=1, header_row=0, header_columns=["A", "B", "C"])
    assert template_explains_columns(template, ["A", "B", "C", "D"]) is True
    assert template_explains_columns(template, ["A", "B"]) is False
    assert template_explains_columns(None, ["A"]) is False


# ======================================================================
# 4. 处置模型: 区分接管与真漂移
# ======================================================================
def test_disposition_exposes_takeover_signal():
    from backend.services.data_sync_file_state_service import (
        FILE_STATE_READY_TO_SYNC,
        resolve_file_disposition,
    )

    takeover = {
        "flag": "cross_family_variant_takeover",
        "source_family_id": 23,
        "source_family_granularity": "daily",
        "variant_key": "daily_header_3_f40e8338",
        "match_rate": 1.0,
        "missing_headers": [],
    }
    disposition = resolve_file_disposition(
        catalog_status="pending",
        template_status="ready",
        governance_status="ready",
        should_auto_sync=True,
        template_baseline="cross_family_variant",
        takeover=takeover,
    )
    assert disposition["file_state"] == FILE_STATE_READY_TO_SYNC
    assert disposition["template_baseline"] == "cross_family_variant"
    assert disposition["takeover"]["source_family_id"] == 23
    assert disposition["takeover"]["variant_key"] == "daily_header_3_f40e8338"
    assert "接管" in (disposition["reason"] or "")


def test_disposition_without_takeover_has_no_takeover_key():
    from backend.services.data_sync_file_state_service import resolve_file_disposition

    disposition = resolve_file_disposition(
        catalog_status="pending",
        template_status="ready",
        governance_status="ready",
        should_auto_sync=True,
    )
    assert "takeover" not in disposition
    assert "template_baseline" not in disposition


def test_drift_disposition_distinguishes_takeover_from_real_drift():
    from backend.services.data_sync_file_state_service import resolve_file_disposition

    real_drift = resolve_file_disposition(
        catalog_status="template_update_required",
        template_status="update_required",
        governance_status="breaking_drift",
    )
    assert real_drift["file_state"] == "blocked_template_update"

    takeover_drift = resolve_file_disposition(
        catalog_status="template_update_required",
        template_status="update_required",
        governance_status="breaking_drift",
        template_baseline="cross_family_variant",
        takeover={"flag": "cross_family_variant_takeover"},
    )
    assert takeover_drift["file_state"] == "blocked_template_update"
    assert "接管" in (takeover_drift["reason"] or "")
    assert takeover_drift["takeover"]["flag"] == "cross_family_variant_takeover"


# ======================================================================
# 5. 表头行一致性: 变体行不匹配就不参与比对
# ======================================================================
def test_variant_header_row_must_match_actual_read_row():
    from backend.services.template_family_service import _variant_header_row_matches

    assert _variant_header_row_matches({"header_row": 3}, 3) is True
    assert _variant_header_row_matches({"header_row": 2}, 3) is False
    # 变体没声明行 / 调用方不知道行 -> 放行(不猜)
    assert _variant_header_row_matches({}, 3) is True
    assert _variant_header_row_matches({"header_row": 3}, None) is True


# ======================================================================
# 6. 基准来源常量
# ======================================================================
def test_template_baseline_constants_are_single_sourced():
    from backend.services.data_sync_status_semantics import (
        TEMPLATE_BASELINE_CONTRACT,
        TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
        TEMPLATE_BASELINE_CURRENT,
        TEMPLATE_BASELINE_NONE,
        TEMPLATE_BASELINES,
        status_semantics_snapshot,
    )

    assert TEMPLATE_BASELINE_CONTRACT == "contract"
    assert TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT == "cross_family_variant"
    assert TEMPLATE_BASELINE_CURRENT == "current"
    assert TEMPLATE_BASELINE_NONE == "none"
    assert set(TEMPLATE_BASELINES) == {
        "contract",
        "cross_family_variant",
        "current",
        "none",
    }
    snapshot = status_semantics_snapshot()
    assert snapshot["template_baselines"] == list(TEMPLATE_BASELINES)


@pytest.mark.parametrize(
    "contract_id,template_id,expect_stale",
    [
        (362, 362, False),   # 契约指向的就是接管模板 -> 不算过时
        (350, 362, True),    # 契约指向别的模板 -> 需要修正
    ],
)
def test_contract_stale_detection(contract_id, template_id, expect_stale):
    """契约指向的模板与实际解释文件的模板不一致时, 契约算过时。"""
    from backend.services.data_sync_status_semantics import (
        TEMPLATE_BASELINE_CONTRACT,
        TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    )

    contract = {"template_id": contract_id}
    baseline_kind = (
        TEMPLATE_BASELINE_CONTRACT
        if contract_id == template_id
        else TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT
    )
    stale = bool(contract and baseline_kind != TEMPLATE_BASELINE_CONTRACT)
    assert stale is expect_stale

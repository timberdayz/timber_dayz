from backend.domains.business.routers.performance_management import (
    _apply_ranking_policy,
    _build_performance_alert_payloads,
)


def _base_row(shop_id: str, total_score: float) -> dict:
    return {
        "platform_code": "shopee",
        "shop_id": shop_id,
        "sales_score": 20.0,
        "profit_score": 20.0,
        "key_product_score": 20.0,
        "operation_score": total_score - 60.0,
        "total_score": total_score,
        "rank": None,
        "performance_coefficient": None,
        "score_details": {
            "summary": {"calculation_status": "complete"},
        },
    }


def test_apply_ranking_policy_keeps_short_operating_shop_in_official_pool():
    rows = [
        _base_row("shop-1", 92.0),
        _base_row("shop-2", 88.0),
    ]

    _apply_ranking_policy(
        rows,
        {
            "shopee|shop-1": 20,
            "shopee|shop-2": 10,
        },
    )

    official = next(row for row in rows if row["shop_id"] == "shop-1")
    short_coverage = next(row for row in rows if row["shop_id"] == "shop-2")

    assert official["rank"] == 1
    assert official["performance_coefficient"] == 1.2
    assert official["score_details"]["summary"]["ranking_pool"] == "official"

    assert short_coverage["rank"] == 2
    assert short_coverage["performance_coefficient"] is not None
    assert short_coverage["score_details"]["summary"]["ranking_pool"] == "official"
    assert short_coverage["score_details"]["summary"]["formal_ready"] is True
    assert short_coverage["score_details"]["summary"]["data_coverage_warning"] is True
    assert short_coverage["score_details"]["summary"]["operating_days"] == 10


def test_build_performance_alert_payloads_escalates_after_two_prior_red_months():
    rows = [_base_row("shop-1", 58.0)]
    rows[0]["score_details"]["summary"].update(
        {"ranking_pool": "official", "formal_ready": True}
    )

    alerts = _build_performance_alert_payloads(
        period="2026-03",
        calc_list=rows,
        prior_red_streak_by_shop={"shopee|shop-1": 2},
    )

    payloads = alerts["shopee|shop-1"]
    alert_types = {item["alert_type"] for item in payloads}
    assert "performance_red_card" in alert_types
    assert "performance_elimination_review" in alert_types
    summary = rows[0]["score_details"]["summary"]
    assert summary["performance_alert_level"] == "critical"
    assert "performance_red_card" in summary["performance_alert_types"]
    assert "performance_elimination_review" in summary["performance_alert_types"]

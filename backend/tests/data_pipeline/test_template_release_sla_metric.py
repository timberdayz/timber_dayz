"""模板发布**闭环指标**的守护（2026-11-14，批次 4-2）。

为什么要有这批守护
------------------
「模板发布后 T 分钟内完成重估的比例」这个指标, 如果实现错了会**静默地**
给出一个看起来正常的数字 —— 而这个数字会被用来回答
「我们改模板之后多久能见效」。那比没有数字更危险。

锁住的事
--------
1. **归因**: 重估记录只归属到「同维度 + 同一次发布」;
2. **窗口**: 窗口内算达标, 超窗口算超时;
3. **无数据 ≠ 达标**: 没有重检埋点的发布事件, 一律计入「无数据」,
   **绝不能**被算成「按时完成」;
4. **埋点真的写进去了**: 重检时必须留下「何时重检 + 针对哪次发布」,
   否则指标永远算不出来。

这些用例全是**纯离线**的: 不连数据库, 也不碰业务数据。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.template_release_sla_metric import (  # noqa: E402
    attribute_rechecks,
)

T0 = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc)

DIM_A = ("tiktok", "orders", "monthly", None, None)
DIM_B = ("shopee", "orders", "monthly", None, None)


def _event(
    template_id: int,
    dimension=DIM_A,
    published_at: datetime = T0,
    version: int = 12,
) -> Dict[str, Any]:
    return {
        "template_id": template_id,
        "version": version,
        "status": "published",
        "dimension": dimension,
        "published_at": published_at,
        "template_name": f"tpl_{template_id}",
    }


def _recheck(
    template_id: int,
    minutes_after: float,
    dimension=DIM_A,
    file_id: int = 1,
) -> Dict[str, Any]:
    return {
        "file_id": file_id,
        "rechecked_at": T0 + timedelta(minutes=minutes_after),
        "dimension": dimension,
    }


# ---------------------------------------------------------------------------
# 1. 归因与窗口
# ---------------------------------------------------------------------------
def test_recheck_inside_window_counts_as_on_time():
    """发布后 5 分钟内完成重检 ⇒ 达标。"""
    report = attribute_rechecks(
        [_event(101)],
        {101: _recheck(101, minutes_after=5)},
        window_minutes=15,
    )
    assert report["affected_files"] == 1
    assert report["on_time_files"] == 1
    assert report["late_files"] == 0
    assert report["overall_ratio"] == 1.0


def test_recheck_outside_window_counts_as_late():
    """发布后 40 分钟才重检 ⇒ 超时(不是「没达标」, 是「超时」)。"""
    report = attribute_rechecks(
        [_event(101)],
        {101: _recheck(101, minutes_after=40)},
        window_minutes=15,
    )
    assert report["affected_files"] == 1
    assert report["on_time_files"] == 0
    assert report["late_files"] == 1
    assert report["overall_ratio"] == 0.0
    late_files = report["per_event"][0]["late_files"]
    assert late_files[0]["minutes_after_publish"] == 40.0


def test_events_without_recheck_records_are_not_counted_as_on_time():
    """**无数据 ≠ 达标**。

    这是本指标最容易出错的地方: 把「没重检记录」当成「按时完成」,
    比例就会虚高 100%。
    """
    report = attribute_rechecks(
        [_event(101)],
        {},
        window_minutes=15,
    )
    assert report["publish_events"] == 1
    assert report["events_without_recheck_records"] == 1
    assert report["affected_files"] == 0
    assert report["on_time_files"] == 0
    assert report["overall_ratio"] is None, "没有数据时不该给出比例"
    assert report["per_event"][0]["ratio"] is None


def test_recheck_of_other_dimension_is_not_attributed():
    """别的维度的重检不能算到这次发布头上。"""
    report = attribute_rechecks(
        [_event(101, dimension=DIM_A)],
        {101: _recheck(101, minutes_after=1, dimension=DIM_B)},
        window_minutes=15,
    )
    assert report["affected_files"] == 0
    assert report["events_without_recheck_records"] == 1


def test_multiple_files_are_aggregated_per_event():
    """一次发布下多个文件重检 ⇒ 逐个统计, 比例 = 达标数 / 总数。"""
    rechecks = {
        101: _recheck(101, minutes_after=2, file_id=1),
        102: _recheck(101, minutes_after=3, file_id=2),
        103: _recheck(101, minutes_after=99, file_id=3),
    }
    report = attribute_rechecks(
        [_event(101)],
        rechecks,
        window_minutes=15,
    )
    assert report["affected_files"] == 3
    assert report["on_time_files"] == 2
    assert report["late_files"] == 1
    assert report["overall_ratio"] == 2 / 3


def test_window_boundary_is_inclusive():
    """正好卡在窗口边界上算达标(<= window)。"""
    report = attribute_rechecks(
        [_event(101)],
        {101: _recheck(101, minutes_after=15)},
        window_minutes=15,
    )
    assert report["on_time_files"] == 1


# ---------------------------------------------------------------------------
# 2. 埋点真的写进去了
# ---------------------------------------------------------------------------
def _file_record() -> SimpleNamespace:
    return SimpleNamespace(
        id=3059,
        file_name="tiktok_orders_monthly.xlsx",
        status="template_update_required",
        error_message=None,
        file_metadata={},
    )


def test_recheck_records_timestamp_and_target_template():
    """重检必须留下「何时重检 + 针对哪一次模板发布」。

    没有 ``last_recheck_template_id`` 就无法把重检归属到某次发布,
    闭环比例永远算不出来。
    """
    from backend.services.template_recheck_service import TemplateRecheckService

    record = _file_record()
    TemplateRecheckService.apply_recheck(
        record,
        {
            "should_auto_sync": True,
            "template_status": "ready",
            "governance_status": "ready",
            "template_id": 372,
        },
    )

    auto = record.file_metadata["auto_ingest"]
    assert auto.get("last_recheck_at"), "缺少重检时刻"
    assert auto.get("last_recheck_template_id") == 372, "缺少本次重检对应的发布事件"


def test_blocked_recheck_also_records_the_timestamp():
    """仍被阻塞的重检也要留痕 —— 「查过了但没过」同样是完成了一次重估。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    record = _file_record()
    TemplateRecheckService.apply_recheck(
        record,
        {
            "should_auto_sync": False,
            "template_status": "update_required",
            "governance_status": "breaking_drift",
            "update_reason": "缺少必需字段",
            "template_id": 372,
        },
    )

    auto = record.file_metadata["auto_ingest"]
    assert auto.get("last_recheck_at"), "缺少重检时刻"
    assert auto.get("last_recheck_template_id") == 372
    assert auto.get("last_status") == "template_update_required"


def test_recheck_without_template_id_still_records_the_timestamp():
    """拿不到模板 id 时也要记时刻(时刻是重估的必备事实)。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    record = _file_record()
    TemplateRecheckService.apply_recheck(
        record,
        {
            "should_auto_sync": True,
            "template_status": "ready",
            "governance_status": "ready",
        },
    )

    auto = record.file_metadata["auto_ingest"]
    assert auto.get("last_recheck_at")
    assert "last_recheck_template_id" not in auto


def test_recheck_with_contract_promotion_records_promotion_history():
    """发生**契约晋升**时也要走通(潜伏 bug 的守护)。

    ``apply_recheck`` 是 ``@staticmethod``; 晋升分支里如果误用 ``self.``,
    错误只会在**真的晋升**时才抛出来 —— 平时跑完全看不出来。
    """
    from backend.services.template_recheck_service import TemplateRecheckService

    record = _file_record()
    TemplateRecheckService.apply_recheck(
        record,
        {
            "should_auto_sync": True,
            "template_status": "ready",
            "governance_status": "ready",
            "template_id": 372,
            "promoted_contract": {
                "template_id": 372,
                "template_version": 8,
                "template_name": "tpl_v8",
                "source": "contract_promotion",
                "captured_at": "2026-11-14T10:00:00+00:00",
            },
            "contract_promotion": {
                "from_template_id": 368,
                "from_template_version": 6,
                "to_template_id": 372,
                "to_template_version": 8,
            },
        },
    )

    from backend.services.template_contract_service import (
        read_contract_promotions,
        read_effective_contract,
    )

    effective = read_effective_contract(record)
    assert effective["template_id"] == 372

    history = read_contract_promotions(record)
    assert len(history) == 1
    assert history[0]["from_template_version"] == 6
    assert history[0]["to_template_version"] == 8

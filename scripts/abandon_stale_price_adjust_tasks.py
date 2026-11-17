#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作废「飞书调价记录」outbox 里因平台单选字段写错而卡死的积压任务。

背景
----
2026-11-07 的「底线下沉到 SKU × 平台」把 ``platform_code`` 放进了 outbox 载荷，
而投影服务把这个**小写 code**（``tiktok``）直接写进飞书「平台」单选字段。
飞书那张表的选项名是 ``TikTok`` / ``Shopee`` / ``Amazon``，匹配不上 ⇒
base/v3 的批量新增**整批拒绝**（``not_found``）。

⇒ 2026-11-08 起 461 条调价记录**一条都没写进飞书**；而且失败重试**没有次数上限**
（退避封顶 1 小时，见 ``backend/services/feishu_projection_service.py``），
于是每天再刷几百条失败日志。

v7.31.1 修好了写入（写飞书选项名）。但这些**旧任务**留着有两个坏处：

1. 无限重试 —— 每天几百条失败日志；
2. 修好之后它们会被**一次性重投**，把 461 行旧口径记录（无仓维度、
   「变动原因/变动方向」还是老取值）倒进飞书调价记录表 ——
   那张表是**只增不改**的，倒进去就删不掉了。

所以修好之后要把这批旧任务**显式作废**（不是删，是标成 ``abandoned``，
留审计痕迹），让新的检测流程从干净的基线重新开始。

安全边界（刻意收窄）
--------------------
* 只动 ``entity_type = 'price_adjust'`` 的**失败**任务；
* 只动 ``created_at < --before`` 的（默认 2026-11-16，即修复上线**之前**建的）；
* 只改状态，不删行、不改载荷；
* 默认 dry-run，必须显式 ``--apply`` 才动手。

用法
----
    python scripts/abandon_stale_price_adjust_tasks.py                     # 只报告
    python scripts/abandon_stale_price_adjust_tasks.py --apply             # 真正作废
    python scripts/abandon_stale_price_adjust_tasks.py --before 2026-11-16T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text

from backend.models.database import engine

#: 修复上线前建的任务（v7.31.1 发布于 2026-11-17）
DEFAULT_BEFORE = "2026-11-16T00:00:00+00:00"

#: 作废后用的状态值。
#: ⚠️ 投递查询只捞 ``pending`` 与「到期的 ``failed``」，
#:    所以这个状态既不会被重投、也不会被 ``retry_failed`` 复活。
ABANDONED_STATUS = "abandoned"


def _parse_before(raw: str) -> datetime:
    value = raw.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _target_db_label() -> str:
    """目标库标识（**不打印凭据**）：主机 + 库名。"""
    url = engine.url
    return "{0}/{1}".format(url.host, url.database)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="作废飞书调价记录 outbox 里卡死的旧任务(默认只报告)"
    )
    parser.add_argument(
        "--before",
        default=DEFAULT_BEFORE,
        help="只作废这个时刻之前建的任务(ISO8601, 默认 {0})".format(DEFAULT_BEFORE),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行作废; 不加此参数只打印清单",
    )
    args = parser.parse_args()

    before = _parse_before(args.before)
    print("=" * 72)
    print(
        "作废模式: {0}".format(
            "执行作废 (--apply)" if args.apply else "只报告 (dry-run)"
        )
    )
    print("目标库  : {0}".format(_target_db_label()))
    print("时间界限: created_at < {0}".format(before.isoformat()))
    print("=" * 72)

    where = """
        entity_type = 'price_adjust'
        AND status = 'failed'
        AND created_at < :before
    """

    with engine.begin() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM ops.feishu_projection_tasks WHERE " + where),
            {"before": before},
        ).scalar()
        by_day = conn.execute(
            text(
                "SELECT date_trunc('day', created_at)::date::text, count(*) "
                "FROM ops.feishu_projection_tasks WHERE "
                + where
                + " GROUP BY 1 ORDER BY 1"
            ),
            {"before": before},
        ).fetchall()
        by_reason = conn.execute(
            text(
                "SELECT coalesce(left(last_error, 60), '(空)'), count(*) "
                "FROM ops.feishu_projection_tasks WHERE "
                + where
                + " GROUP BY 1 ORDER BY 2 DESC"
            ),
            {"before": before},
        ).fetchall()

        print("")
        print("[待作废] 共 {0} 条".format(total))
        for day, count in by_day:
            print("  {0}  {1} 条".format(day, count))
        for err, count in by_reason:
            print("  失败原因 {0} —— {1} 条".format(err, count))

        if not args.apply:
            print("")
            print("[提示] 以上为 dry-run; 确认无误后加 --apply 执行")
            return 0

        if not total:
            print("")
            print("[跳过] 没有符合条件的任务")
            return 0

        result = conn.execute(
            text(
                "UPDATE ops.feishu_projection_tasks SET status = :status, "
                "next_retry_at = NULL, "
                "last_error = coalesce(last_error, '') || ' [abandoned by "
                "scripts/abandon_stale_price_adjust_tasks.py]' "
                "WHERE " + where
            ),
            {"before": before, "status": ABANDONED_STATUS},
        )

        remaining = conn.execute(
            text(
                "SELECT count(*) FROM ops.feishu_projection_tasks WHERE "
                "entity_type = 'price_adjust' AND status = 'failed'"
            )
        ).scalar()
        abandoned = conn.execute(
            text(
                "SELECT count(*) FROM ops.feishu_projection_tasks WHERE "
                "entity_type = 'price_adjust' AND status = :status"
            ),
            {"status": ABANDONED_STATUS},
        ).scalar()

    print("")
    print("[OK] 已作废 {0} 条（status={1}）".format(result.rowcount, ABANDONED_STATUS))
    print(
        "[现状] price_adjust 失败任务剩余 {0} 条 / 已作废 {1} 条".format(
            remaining, abandoned
        )
    )
    print("[说明] 作废的行不会再重投，也不会被写进飞书调价记录表")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

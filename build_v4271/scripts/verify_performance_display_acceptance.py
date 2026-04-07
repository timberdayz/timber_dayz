#!/usr/bin/env python3
"""验收脚本：6.3（绩效公示显示）与 6.4b（calculate 写入）。"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Tuple

from sqlalchemy import desc, func, or_, select, text
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.models.database import AsyncSessionLocal  # noqa: E402
from backend.routers.performance_management import (  # noqa: E402
    calculate_performance_scores,
    list_performance_scores,
)
from modules.core.db import EmployeePerformance, PerformanceConfig, PerformanceScore, TargetBreakdown  # noqa: E402


def _make_request() -> Request:
    app = SimpleNamespace(state=SimpleNamespace())
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/performance/scores",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


async def _pick_person_period() -> Optional[str]:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(EmployeePerformance.year_month, func.count().label("cnt"))
                .group_by(EmployeePerformance.year_month)
                .order_by(desc(EmployeePerformance.year_month))
                .limit(1)
            )
            row = result.first()
            return row.year_month if row else None
        except Exception:
            await db.rollback()
            result = await db.execute(
                text(
                    """
                    select "年月" as year_month, count(1) as cnt
                    from c_class.employee_performance
                    group by "年月"
                    order by "年月" desc
                    limit 1
                    """
                )
            )
            row = result.mappings().first()
            return row.get("year_month") if row else None


async def _pick_config_context() -> Optional[Tuple[int, str]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PerformanceConfig)
            .order_by(desc(PerformanceConfig.effective_from))
            .limit(1)
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            return None
        return cfg.id, cfg.effective_from.strftime("%Y-%m")


async def _pick_calculate_period() -> str:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(TargetBreakdown.period_label)
                .where(TargetBreakdown.period_label.is_not(None))
                .order_by(desc(TargetBreakdown.period_label))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row:
            val = str(row)
            return val[:7] if len(val) >= 7 else val
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _ensure_config_for_period(period: str) -> int:
    period_start = datetime.strptime(period, "%Y-%m").date().replace(day=1)
    async with AsyncSessionLocal() as db:
        cfg = (
            await db.execute(
                select(PerformanceConfig)
                .where(
                    PerformanceConfig.effective_from <= period_start,
                    or_(
                        PerformanceConfig.effective_to.is_(None),
                        PerformanceConfig.effective_to >= period_start,
                    ),
                )
                .order_by(desc(PerformanceConfig.effective_from))
                .limit(1)
            )
        ).scalar_one_or_none()
        if cfg:
            return cfg.id
        cfg = PerformanceConfig(
            config_name=f"auto-acceptance-{period}",
            sales_weight=30,
            profit_weight=25,
            key_product_weight=25,
            operation_weight=20,
            sales_max_score=30,
            profit_max_score=25,
            key_product_max_score=25,
            operation_max_score=20,
            is_active=True,
            effective_from=period_start,
            effective_to=None,
            created_by="acceptance-script",
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
        return cfg.id


async def _count_performance_scores(period: str) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count())
            .select_from(PerformanceScore)
            .where(PerformanceScore.period == period)
        )
        return int(result.scalar() or 0)


async def main() -> int:
    lines: list[str] = [
        "# 绩效公示验收自动化报告",
        "",
        f"- 生成时间(UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        "- 覆盖项: 6.3 / 6.4b",
        "",
        "## 验收结果",
        "",
    ]

    # 6.3: 绩效公示列表有数据时展示 total_score/rank
    period = await _pick_person_period()
    if not period:
        lines.append("- [FAIL] 6.3 未找到 employee_performance 有数据的月份")
    else:
        async with AsyncSessionLocal() as db:
            req = _make_request()
            resp = await list_performance_scores(
                request=req,
                period=period,
                platform_code=None,
                shop_id=None,
                group_by="person",
                page=1,
                page_size=20,
                db=db,
            )
            payload = json.loads(resp.body.decode("utf-8"))
            data = payload.get("data", [])
            has_rank_score = any(
                (row.get("total_score") is not None and row.get("rank") is not None) for row in data
            )
            lines.append(
                f"- {'[OK]' if has_rank_score else '[FAIL]'} 6.3 绩效公示有数据展示排名与得分: period={period}, rows={len(data)}, has_rank_score={has_rank_score}"
            )

    # 6.4b: calculate 后 c_class.performance_scores 新增记录（当前依赖外部提案）
    calc_period = await _pick_calculate_period()
    config_id = await _ensure_config_for_period(calc_period)
    if not config_id:
        lines.append("- [FAIL] 6.4b 未找到/创建绩效配置记录，无法调用 calculate")
    else:
        before = await _count_performance_scores(calc_period)
        async with AsyncSessionLocal() as db:
            resp = await calculate_performance_scores(period=calc_period, config_id=config_id, db=db)
            body = json.loads(resp.body.decode("utf-8"))
            error_code = (body.get("data") or {}).get("error_code")
        after = await _count_performance_scores(calc_period)
        ok_64b = after > before
        lines.append(
            f"- {'[OK]' if ok_64b else '[FAIL]'} 6.4b 调用 calculate 后新增 performance_scores: config_id={config_id}, period={calc_period}, before={before}, after={after}, error_code={error_code or 'N/A'}"
        )
        if not ok_64b and error_code == "PERF_CALC_NOT_READY":
            lines.append("- [INFO] 6.4b 当前受 add-performance-calculation-via-metabase 未落地影响，符合预期阻塞状态")

    report = ROOT / "reports" / "migration_reconciliation" / "performance_display_acceptance_20260315.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] report written: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

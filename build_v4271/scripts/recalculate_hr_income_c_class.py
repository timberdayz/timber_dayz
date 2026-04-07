#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工收入 C 类数据重算脚本

用途:
- 计算并写入 c_class.employee_commissions
- 计算并写入 c_class.employee_performance

可被定时任务调用:
  python scripts/recalculate_hr_income_c_class.py --year-month 2026-03
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from backend.models.database import AsyncSessionLocal
from backend.services.hr_income_calculation_service import HRIncomeCalculationService


def _default_year_month() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def _run(year_month: str) -> int:
    async with AsyncSessionLocal() as db:
        service = HRIncomeCalculationService(db=db)
        result = await service.calculate_month(year_month)
        print(
            f"[OK] income c_class recalculated: month={result['year_month']} "
            f"employees={result['employee_count']} "
            f"commission_upserts={result['commission_upserts']} "
            f"performance_upserts={result['performance_upserts']}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="重算员工收入 C 类数据")
    parser.add_argument("--year-month", dest="year_month", default=_default_year_month(), help="月份 YYYY-MM")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.year_month))
    except Exception as e:
        print(f"[FAIL] recalculate income c_class failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

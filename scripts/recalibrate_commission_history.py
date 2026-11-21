#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提成与绩效工资历史重算脚本（口径归一后）。

用途
====
把历史月份的提成与绩效工资，按 2026-11-21 归一后的口径重新算一遍：

* **提成** = 可分配利润 × 归属提成比（**零系数**；店铺赛马排名与个人分数档位
  都不参与金额）
* **绩效工资** = 绩效包金额 × **纯个人**绩效分数档位系数

口径依据：``docs/adr/2026-11-21-commission-and-performance-caliber-layering.md``
实施计划：``docs/superpowers/plans/2026-11-21-commission-and-performance-caliber-unification.md``

⚠️ 这是**不可逆**操作
----------------------
重算会覆盖历史工资单里的提成与绩效工资金额。执行前必须：

1. 生产库先跑 ``--dry-run``，把**逐人新旧对照表**交业务确认；
2. 确认发版流程的迁移前备份可用（``pg_restore --list`` 退出码 0）。

用法
====
::

    # 默认就是 dry-run：只打印「将改什么」，不写库
    python scripts/recalibrate_commission_history.py --year-month 2026-07

    # 区间 dry-run
    python scripts/recalibrate_commission_history.py --from 2026-03 --to 2026-11

    # 真写库（必须显式 --apply）
    python scripts/recalibrate_commission_history.py --from 2026-03 --to 2026-11 --apply

设计约束
--------
* **默认 dry-run**：不加 ``--apply`` 一律不写库；
* **幂等**：同一个区间重复执行，结果不变（重算写的是同一套确定值）；
* **事务包裹**：任一月份失败即整体回滚，不留半截数据；
* **逐人明细**：输出「月份 / 员工 / 项目 / 旧值 → 新值 / 差额」。
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from sqlalchemy import select

from backend.models.database import AsyncSessionLocal
from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.payroll_generation_service import PayrollGenerationService
from backend.services.profit_basis_service import ProfitBasisService
from modules.core.db import PayrollRecord

#: 现行唯一的利润基数口径（与 LaborCostPolicyService 保持一致）
CURRENT_BASIS_VERSION = LaborCostPolicyService.CURRENT_BASIS_VERSION


#: 需要重算的项目 —— 显示名 → payroll_records 列名
AMOUNT_FIELDS = (
    ("提成", "commission"),
    ("绩效工资", "performance_salary"),
)


def _default_year_month() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _month_range(from_month: str, to_month: str) -> list[str]:
    """闭区间月份列表（``2026-03`` ~ ``2026-11``）。"""
    start_y, start_m = (int(x) for x in from_month.split("-"))
    end_y, end_m = (int(x) for x in to_month.split("-"))
    months: list[str] = []
    year, month = start_y, start_m
    while (year, month) <= (end_y, end_m):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


async def _load_existing(db, year_month: str) -> dict[str, dict[str, float]]:
    """读出该月工资单里现有的（提成、绩效工资），用于新旧对照。"""
    rows = (
        (
            await db.execute(
                select(
                    PayrollRecord.employee_code,
                    PayrollRecord.commission,
                    PayrollRecord.performance_salary,
                ).where(PayrollRecord.year_month == year_month)
            )
        )
        .tuples()
        .all()
    )
    return {
        str(row[0]): {
            "commission": float(row[1] or 0),
            "performance_salary": float(row[2] or 0),
        }
        for row in rows
    }


async def _reopen_month_snapshots(db, year_month: str) -> int:
    """把该月所有利润基数快照解锁，允许重建。

    「锁定有明确边界和撤回路径」—— 发现口径要改时**显式重开**，
    而不是被隐式锁死（``profit_basis_service.reopen_profit_basis_snapshot`` 的设计意图）。

    ⚠️ 解锁要覆盖该店的**所有口径版本**（含 legacy）——
    ``upsert_profit_basis_snapshot`` 的锁检查是按「月份 + 店」找行的，
    **不看 basis_version** ⇒ legacy 行被锁住时，同样会挡住重建。

    返回解锁的条数。
    """
    from sqlalchemy import select

    from modules.core.db import EmployeeShopAssignment, ShopProfitBasis

    assignments = (
        (
            await db.execute(
                select(EmployeeShopAssignment).where(
                    EmployeeShopAssignment.year_month == year_month,
                    EmployeeShopAssignment.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    shops = sorted(
        {
            (
                str(getattr(row, "platform_code", "") or "").lower(),
                str(getattr(row, "shop_id", "") or ""),
            )
            for row in assignments
            if str(getattr(row, "platform_code", "") or "").strip()
            and str(getattr(row, "shop_id", "") or "").strip()
        }
    )

    reopened = 0
    for platform_code, shop_id in shops:
        records = (
            (
                await db.execute(
                    select(ShopProfitBasis).where(
                        ShopProfitBasis.period_month == year_month,
                        ShopProfitBasis.platform_code == platform_code,
                        ShopProfitBasis.shop_id == shop_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for record in records:
            if record.is_locked:
                record.is_locked = False
                reopened += 1
    return reopened


async def _compute_new_values(db, year_month: str) -> tuple[dict, dict]:
    """按现行口径算出该月每个人的新金额（**不写库**）。

    ⚠️ 顺序很关键：**先重建利润基数，再算提成**。
    历史月份的利润基数是 legacy 版本（``A_ONLY_V1`` / ``A_PRE_COMMISSION_LABOR_V2``），
    现行代码读它们时会跳过 ⇒ 不先重建的话，可分配利润全是 0，提成全被算成 0
    （实测 2026-07：5 名员工的提成从 276.23 / 39.53 / 645.47 … 全部变成 0）。

    返回 ``(按员工的提成, calculate_month 的原始返回)``。
    """
    # 1) 先解锁该月已锁定的利润基数（显式重开，允许按现行口径重建）
    await _reopen_month_snapshots(db, year_month)

    # 2) 再按现行口径重建该月所有店的利润基数（upsert，dry-run 时不提交）
    basis_service = ProfitBasisService(db=db)
    await basis_service.rebuild_month_v2(year_month, commit=False)

    # 2) 再算提成与绩效画像
    service = HRIncomeCalculationService(db=db)
    result = await service.calculate_month(year_month, commit=False)

    commission_by_employee: dict[str, float] = {}
    for allocation in result.get("commission_allocations") or []:
        code = str(allocation.get("employee_code") or "")
        if not code:
            continue
        commission_by_employee[code] = commission_by_employee.get(code, 0.0) + float(
            allocation.get("commission_amount") or 0
        )

    return commission_by_employee, result


async def _apply_month(db, year_month: str) -> tuple[int, list[str]]:
    """真正重算某月（**写库**）。

    走应用里的正规链路（与「店铺绩效管理」页刷新一致）：

    1. ``rebuild_month_v2`` —— 按现行口径重建利润基数；
    2. ``calculate_month(commit=False)`` —— 重算提成与绩效画像；
    3. ``PayrollGenerationService.generate_month(...)`` —— 重生成工资单。

    返回 ``(变更项数, 受影响员工列表)``。
    """
    await _reopen_month_snapshots(db, year_month)

    basis_service = ProfitBasisService(db=db)
    await basis_service.rebuild_month_v2(year_month, commit=False)

    service = HRIncomeCalculationService(db=db)
    result = await service.calculate_month(year_month, commit=False)

    employee_codes = result.get("payroll_refresh_employee_codes") or []
    changed = 0
    if employee_codes:
        payroll_service = PayrollGenerationService(db=db)
        await payroll_service.generate_month(
            year_month,
            employee_codes=employee_codes,
        )
        changed = len(employee_codes)
    return changed, list(employee_codes)


async def _run(months: list[str], apply: bool) -> int:
    changed_total = 0
    async with AsyncSessionLocal() as db:
        for year_month in months:
            existing = await _load_existing(db, year_month)
            if not existing:
                print(f"\n=== {year_month} ===")
                print("  （该月没有工资单记录，跳过）")
                continue

            print(f"\n=== {year_month} ===")
            commission_by_employee, _result = await _compute_new_values(db, year_month)

            month_changed = 0
            for code in sorted(set(existing) | set(commission_by_employee)):
                old = existing.get(code, {})
                old_commission = float(old.get("commission") or 0)
                new_commission = float(commission_by_employee.get(code, 0.0))
                if abs(old_commission - new_commission) < 0.005:
                    continue
                month_changed += 1
                changed_total += 1
                delta = new_commission - old_commission
                print(
                    f"  {code}  提成: {old_commission:>10.2f} -> {new_commission:>10.2f} "
                    f"({delta:>+9.2f})"
                )
                print(
                    f"          绩效工资: {float(old.get('performance_salary') or 0):>10.2f}"
                    f"  （随工资单重生成，金额以新口径为准）"
                )

            if month_changed == 0:
                print("  （提成无差异 —— 幂等：该月已是现行口径）")
                continue

            if not apply:
                print(f"  → {month_changed} 项待变更（dry-run，未写库）")
                continue

            changed, employee_codes = await _apply_month(db, year_month)
            print(f"  → 已重算 {changed} 名员工的工资单：{', '.join(employee_codes)}")

        if apply and changed_total:
            await db.commit()
            print(f"\n[OK] 已提交：共 {changed_total} 人次提成变更")
        elif apply:
            print("\n[OK] 无需变更")
        else:
            print(
                f"\n[DRY-RUN] 合计 {changed_total} 人次潜在变更，未写库。"
                "确认无误后加 --apply 执行。"
            )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按归一后的口径重算历史提成与绩效工资（默认 dry-run）"
    )
    parser.add_argument(
        "--year-month",
        dest="year_month",
        default=None,
        help="单月重算 YYYY-MM",
    )
    parser.add_argument(
        "--from",
        dest="from_month",
        default="2026-03",
        help="起始月份 YYYY-MM（默认 2026-03）",
    )
    parser.add_argument(
        "--to",
        dest="to_month",
        default=_default_year_month(),
        help="结束月份 YYYY-MM（默认当前月）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库（**不可逆**；不加此参数一律 dry-run）",
    )
    args = parser.parse_args()

    if args.year_month:
        months = [args.year_month]
    else:
        months = _month_range(args.from_month, args.to_month)

    try:
        return asyncio.run(_run(months, args.apply))
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] recalibrate commission history failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

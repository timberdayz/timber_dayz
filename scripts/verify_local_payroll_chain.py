"""本地端到端验证：提成 → 工资单 → 人力成本分摊 → 看板口径。

只允许连**本地开发库**（127.0.0.1:15432）。连别的库直接拒绝执行，
避免误连云库或生产库。

用法：
    python scripts/verify_local_payroll_chain.py --year-month 2026-07
    python scripts/verify_local_payroll_chain.py --year-month 2026-07 --skip-refresh

校验四个恒等式：
    1. 员工提成金额 == 工资单里的提成
    2. 分摊表提成合计 == 员工提成合计
    3. 看板口径(mart.shop_month_labor_cost) == 分摊表 shop 范围 V2 合计
    4. 逐人反算：提成 == Σ(max(利润基数,0) × 可分配利润率 × 个人比例) × 店铺绩效系数
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
LOCAL_PORT = 15432


def _require_local_database_url() -> str:
    """只允许本地开发库；CLOUD_DATABASE_URL 一律忽略（它指向云库隧道）。"""
    os.environ.pop("CLOUD_DATABASE_URL", None)
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit(
            "DATABASE_URL 未设置。本脚本只允许连本地开发库 "
            f"(127.0.0.1:{LOCAL_PORT}/xihong_erp)。"
        )
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    if parsed.hostname not in LOCAL_HOSTS or parsed.port != LOCAL_PORT:
        raise SystemExit(
            f"拒绝执行：{url} 不是本地开发库。"
            f"本脚本只允许 127.0.0.1:{LOCAL_PORT}，避免误连云库或生产库。"
        )
    os.environ["DATABASE_URL"] = url
    return url


def _money(value) -> str:
    return f"{float(value or 0):,.2f}"


async def _run(year_month: str, skip_refresh: bool) -> int:
    import psycopg2
    import psycopg2.extras

    from backend.models.database import AsyncSessionLocal
    from backend.services.v2_monthly_refresh_service import V2MonthlyRefreshService

    url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def rows(sql: str, params=None):
        cur.execute(sql, params or {})
        return cur.fetchall()

    if not skip_refresh:
        async with AsyncSessionLocal() as db:
            bound = db.bind.url.render_as_string(hide_password=False)
            if f":{LOCAL_PORT}" not in bound:
                raise SystemExit(f"拒绝执行：会话实际连的是 {bound}")
            result = await V2MonthlyRefreshService(db).refresh_month(year_month)
            await db.commit()
        print(f"===== V2MonthlyRefreshService.refresh_month({year_month}) =====")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    comm = rows(
        "SELECT employee_code, sales_amount, commission_rate, commission_amount, "
        "calculation_status, calculation_details "
        "FROM c_class.employee_commissions WHERE year_month=%s ORDER BY employee_code",
        (year_month,),
    )
    pay = rows(
        "SELECT employee_code, status, base_salary, performance_salary, commission, "
        "gross_salary, net_salary FROM a_class.payroll_records "
        "WHERE year_month=%s ORDER BY employee_code",
        (year_month,),
    )
    alloc = rows(
        "SELECT employee_code, platform_code, shop_id, allocation_scope, "
        "allocation_ratio, pre_commission_amount, performance_amount, "
        "commission_amount, total_amount, calculation_status, calculation_version "
        "FROM finance.employee_labor_cost_allocations WHERE period_month=%s "
        "ORDER BY employee_code, platform_code, shop_id",
        (year_month,),
    )
    kpi = rows(
        "SELECT platform_code, shop_id, pre_commission_labor_cost, "
        "performance_labor_cost, commission_labor_cost, total_labor_cost, cost_status "
        "FROM mart.shop_month_labor_cost WHERE to_char(period_month,'YYYY-MM')=%s "
        "ORDER BY platform_code, shop_id",
        (year_month,),
    )

    print(f"\n===== 1) 员工提成（{year_month}）=====")
    for r in comm:
        details = r["calculation_details"] or {}
        print(
            f"  {r['employee_code']}  销售={_money(r['sales_amount']):>14}  "
            f"rate={float(r['commission_rate'] or 0):.6f}  "
            f"提成={_money(r['commission_amount']):>10}  "
            f"状态={r['calculation_status']}  "
            f"比例来源={details.get('ratio_sources')}"
        )
    total_comm = sum(float(r["commission_amount"] or 0) for r in comm)
    print(f"  合计提成 = {_money(total_comm)}   ({len(comm)} 人)")

    print(f"\n===== 2) 工资单（{year_month}）=====")
    for r in pay:
        print(
            f"  {r['employee_code']}  {r['status']:<8} 基本={_money(r['base_salary']):>10} "
            f"绩效工资={_money(r['performance_salary']):>9} 提成={_money(r['commission']):>9} "
            f"应发={_money(r['gross_salary']):>11} 实发={_money(r['net_salary']):>11}"
        )

    print(f"\n===== 3) 人力成本分摊（{year_month}）=====")
    for r in alloc:
        print(
            f"  {r['employee_code']} {r['platform_code']}/{(r['shop_id'] or '(公司级)'):<34} "
            f"scope={r['allocation_scope']:<8} ver={r['calculation_version']} "
            f"预提成={_money(r['pre_commission_amount']):>9} "
            f"绩效={_money(r['performance_amount']):>9} "
            f"提成={_money(r['commission_amount']):>9} "
            f"合计={_money(r['total_amount']):>10} {r['calculation_status']}"
        )
    alloc_comm = sum(float(r["commission_amount"] or 0) for r in alloc)
    v2_shop_total = sum(
        float(r["total_amount"] or 0)
        for r in alloc
        if r["allocation_scope"] == "shop"
        and r["calculation_version"] == "LABOR_COST_V2"
    )
    print(f"  分摊提成合计 = {_money(alloc_comm)}")

    print(f"\n===== 4) 看板口径 mart.shop_month_labor_cost（{year_month}）=====")
    for r in kpi:
        print(
            f"  {r['platform_code']}/{r['shop_id']:<34} "
            f"total_labor_cost={_money(r['total_labor_cost']):>12} {r['cost_status']}"
        )
    kpi_total = sum(float(r["total_labor_cost"] or 0) for r in kpi)
    print(f"  看板 labor_cost 合计 = {_money(kpi_total)}")

    print(f"\n===== 5) 恒等式校验 =====")
    ok = True

    pay_comm = {r["employee_code"]: float(r["commission"] or 0) for r in pay}
    for r in comm:
        ec = r["employee_code"]
        want = float(r["commission_amount"] or 0)
        got = pay_comm.get(ec)
        if got is None:
            print(f"  [缺失] {ec}: 提成={_money(want)} 但没有工资单")
            ok = False
            continue
        if abs(want - got) > 0.02:
            print(f"  [FAIL] 恒等式1 {ec}: 提成表={_money(want)} 工资单={_money(got)}")
            ok = False
    print(f"  恒等式1（提成表 == 工资单提成）: {'PASS' if ok else 'FAIL'}")

    if abs(alloc_comm - total_comm) > 0.02:
        print(
            f"  [FAIL] 恒等式2 分摊提成={_money(alloc_comm)} 提成表={_money(total_comm)}"
            f"（差 {_money(total_comm - alloc_comm)}）"
        )
        ok = False
    else:
        print(f"  恒等式2（分摊提成合计 == 提成表合计）: PASS  ({_money(alloc_comm)})")

    if abs(kpi_total - v2_shop_total) > 0.02:
        print(
            f"  [FAIL] 恒等式3 看板={_money(kpi_total)} 分摊(shop+V2)={_money(v2_shop_total)}"
        )
        ok = False
    else:
        print(f"  恒等式3（看板 == 分摊 shop+V2 合计）: PASS  ({_money(kpi_total)})")

    print(f"\n===== 6) 逐人反算 =====")
    basis = {
        (r["platform_code"], r["shop_id"]): r
        for r in rows(
            "SELECT platform_code, shop_id, profit_basis_amount FROM finance.shop_profit_basis "
            "WHERE period_month=%s AND basis_version='A_PRE_COMMISSION_LABOR_V2'",
            (year_month,),
        )
    }
    rates = {
        (r["platform_code"], r["shop_id"]): float(r["allocatable_profit_rate"] or 0)
        for r in rows(
            "SELECT platform_code, shop_id, allocatable_profit_rate "
            "FROM a_class.shop_commission_config WHERE year_month=%s",
            (year_month,),
        )
    }
    assign = rows(
        "SELECT employee_code, platform_code, shop_id, commission_ratio "
        "FROM a_class.employee_shop_assignments WHERE year_month=%s AND status='active'",
        (year_month,),
    )
    coef = {
        (r["platform_code"], r["shop_id"]): float(r["performance_coefficient"] or 1.0)
        for r in rows(
            "SELECT platform_code, shop_id, performance_coefficient "
            "FROM c_class.performance_scores WHERE period=%s",
            (year_month,),
        )
    }
    sales = {
        (r["platform_code"], r["shop_id"]): float(r["gmv"] or 0)
        for r in rows(
            "SELECT platform_code, shop_id, gmv FROM api.business_overview_shop_racing_module "
            "WHERE granularity='monthly' AND period_key = to_date(%s || '-01', 'YYYY-MM-DD')",
            (year_month,),
        )
    }

    for r in comm:
        ec = r["employee_code"]
        raw = 0.0
        coef_num = 0.0
        coef_den = 0.0
        for a in [x for x in assign if x["employee_code"] == ec]:
            key = (a["platform_code"], a["shop_id"])
            b = basis.get(key)
            if not b:
                continue
            pb = float(b["profit_basis_amount"] or 0)
            rate = rates.get(key, 1.0)
            ratio = float(a["commission_ratio"] or 0)
            cf = coef.get(key, 1.0)
            raw += max(pb, 0) * rate * ratio
            # 真实实现按「销售额份额」加权：monthly_sales × ratio
            share = sales.get(key, 0.0) * ratio
            coef_num += cf * share
            coef_den += share
        inherited = coef_num / coef_den if coef_den else 1.0
        expected = raw * inherited
        actual = float(r["commission_amount"] or 0)
        diff = abs(expected - actual)
        if diff > 0.05:
            print(
                f"  [FAIL] {ec} 反算={_money(expected)} 实际={_money(actual)} 差={_money(diff)}"
            )
            ok = False
        else:
            print(
                f"  [OK]   {ec} 反算={_money(expected)} 实际={_money(actual)} 差={_money(diff)}"
            )

    print(f"\n结论: {'全部恒等式通过' if ok else '存在不一致'}")
    conn.close()
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year-month", required=True, help="月份，格式 YYYY-MM")
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="只对账，不重跑 V2 全链路（不写库）",
    )
    args = parser.parse_args()
    if len(args.year_month) != 7 or args.year_month[4] != "-":
        raise SystemExit("--year-month 格式应为 YYYY-MM")
    _require_local_database_url()
    return asyncio.run(_run(args.year_month, args.skip_refresh))


if __name__ == "__main__":
    sys.exit(main())

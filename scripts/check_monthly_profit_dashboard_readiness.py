#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月度利润看板上线前只读体检（口径切换前后同月对比）。

为什么需要它
------------
「财务结算中心」改成只读看板时，**公司留存这个数字的口径被修正了**：

1. **公司人力成本池被扣了两次** —— 利润基数里已经摊过一次，月结又减一次整池；
2. **人员成本被重复扣减** —— 审批落库时按工资单 ``total_cost`` 扣，
   而 ``total_cost = 提成前人力成本 + 绩效工资 + 提成``，
   提成前人力成本在利润基数里已经扣过一次（底薪那部分被扣了两遍）；
3. **人员成本查询缺版本过滤** —— 同月两版分摊行并存时，人力成本最高虚高一倍。

⇒ **切换后所有历史月份的公司留存数字都会变化。这是修正，不是回归。**
上线说明里必须写清楚这一点 ⇒ 先要有「口径切换前后同月对比」的数据。

本脚本回答四个问题
------------------
======  ==========================================  =====================================
 段     问题                                        依据
======  ==========================================  =====================================
 A      店铺利润基数的口径版本分布如何？同月混存吗？  ``finance.shop_profit_basis``
 B      人力成本分摊表的计算版本分布如何？同月混存吗？ ``finance.employee_labor_cost_allocations``
 C      公司人力成本池每月被二次扣减了多少？          同上（``allocation_scope='company'``）
 D      **同一个月，旧口径与新口径的公司留存差多少？** 上面三段 + 工资单
======  ==========================================  =====================================

口径常量全部**从仓库真源 import**，不在本脚本里另抄一份（律 1 / 律 3）：

* ``LABOR_COST_CALCULATION_VERSION`` —— ``backend/services/labor_cost_projection_service.py``
* ``PAYROLL_LOCKED_STATUSES`` —— ``backend/services/hr_employee_lifecycle.py``
* ``LaborCostPolicyService.LEGACY_BASIS_VERSIONS`` /
  ``is_legacy_basis_version`` —— ``backend/services/labor_cost_policy_service.py``
  （⚠️ 判「是不是历史口径」用 ``is_legacy_basis_version``；
  ``is_legacy_a_only_basis_version`` 判的是**成本构成**，只认 ``A_ONLY_V1``）

安全性
------
* **只读**：全程只有 ``SELECT``；连接显式 ``SET TRANSACTION READ ONLY``；
* 不写库、不改表、不建索引；
* 报告写到 ``docs/reports/``（``--out`` 可改），便于上线说明直接引用。

用法
----
```powershell
# 用环境变量 DATABASE_URL（推荐；.env 里就有）
python scripts/check_monthly_profit_dashboard_readiness.py

# 或显式指定连接串
python scripts/check_monthly_profit_dashboard_readiness.py --database-url "postgresql://..."

# 只看某个月
python scripts/check_monthly_profit_dashboard_readiness.py --month 2026-10
```

退出码：0 = 体检跑完（不代表没有风险）；2 = 环境/连接问题。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402

from backend.services.hr_employee_lifecycle import (  # noqa: E402
    PAYROLL_LOCKED_STATUSES,
)
from backend.services.labor_cost_policy_service import (  # noqa: E402
    LaborCostPolicyService,
)
from backend.services.labor_cost_projection_service import (  # noqa: E402
    LABOR_COST_CALCULATION_VERSION,
)

#: 报告默认落盘位置（上线说明会引用它）。
DEFAULT_REPORT_DIR = ROOT / "docs" / "reports"

#: 旧口径的利润基数去重规则 —— 与重构前的
#: ``_load_net_profit_amount`` 完全一致（真源同源，不是另抄一份）。
#:
#: ⚠️ 2026-11-21 修正：这里原先写成
#: ``tuple(v for v in LEGACY_BASIS_VERSIONS if is_legacy_a_only_basis_version(v))``，
#: 而 ``is_legacy_a_only_basis_version`` 只认 ``A_ONLY_V1``（它判的是**成本构成**，
#: 不是「是不是历史口径」）⇒ 过滤后只剩 ``A_ONLY_V1``，
#: ``A_PRE_COMMISSION_LABOR_V2`` 的行会被当成**现行口径**统计，
#: 于是「这个月有没有现行口径的结算数据」被答错。
#: 现在直接用策略服务里的 legacy 清单，并用 ``is_legacy_basis_version`` 判口径。
LEGACY_BASIS_VERSIONS = tuple(LaborCostPolicyService.LEGACY_BASIS_VERSIONS)


# --------------------------------------------------------------------------
# 取数
# --------------------------------------------------------------------------


def _fetch(
    conn: sa.Connection, sql: str, params: dict[str, Any] | None = None
) -> list[Any]:
    return list(conn.execute(sa.text(sql), params or {}))


def _fetch_in(conn: sa.Connection, sql: str, params: dict[str, Any]) -> list[Any]:
    """带 ``IN (:param)`` 的查询 —— 需要 expanding 绑定参数才能把元组展开成列表。"""
    statement = sa.text(sql).bindparams(sa.bindparam("locked", expanding=True))
    return list(conn.execute(statement, params or {}))


def collect_basis_rows(conn: sa.Connection, month: str | None) -> list[dict[str, Any]]:
    """店铺利润基数（去重后）—— 旧/新口径都用它，差别只在公司池。"""
    sql = """
        select period_month, platform_code, shop_id, basis_version,
               profit_basis_amount
        from finance.shop_profit_basis
    """
    params: dict[str, Any] = {}
    if month:
        sql += " where period_month = :month"
        params["month"] = month
    sql += " order by period_month, platform_code, shop_id"

    rows = _fetch(conn, sql, params)

    # 去重：同店同月可能有多行，**非 legacy 行优先**（沿用仓库既有规则）
    basis_by_shop: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        mapping = dict(row._mapping)
        key = (
            str(mapping["period_month"]),
            str(mapping["platform_code"] or "").lower(),
            str(mapping["shop_id"] or ""),
        )
        current = basis_by_shop.get(key)
        if current is None or (
            not LaborCostPolicyService.is_legacy_basis_version(
                mapping.get("basis_version") or ""
            )
            and LaborCostPolicyService.is_legacy_basis_version(
                current.get("basis_version") or ""
            )
        ):
            basis_by_shop[key] = mapping
    return list(basis_by_shop.values())


def collect_basis_version_distribution(
    conn: sa.Connection, month: str | None
) -> list[dict[str, Any]]:
    sql = """
        select period_month, basis_version,
               count(*) as row_count,
               count(distinct platform_code || '|' || shop_id) as shop_count,
               sum(profit_basis_amount) as basis_total
        from finance.shop_profit_basis
    """
    params: dict[str, Any] = {}
    if month:
        sql += " where period_month = :month"
        params["month"] = month
    sql += """
        group by period_month, basis_version
        order by period_month, basis_version
    """
    return [dict(row._mapping) for row in _fetch(conn, sql, params)]


def collect_allocation_version_distribution(
    conn: sa.Connection, month: str | None
) -> list[dict[str, Any]]:
    sql = """
        select period_month, calculation_version, allocation_scope,
               count(*) as row_count,
               sum(pre_commission_amount) as pre_commission_total,
               sum(performance_amount) as performance_total,
               sum(commission_amount) as commission_total
        from finance.employee_labor_cost_allocations
    """
    params: dict[str, Any] = {}
    if month:
        sql += " where period_month = :month"
        params["month"] = month
    sql += """
        group by period_month, calculation_version, allocation_scope
        order by period_month, calculation_version, allocation_scope
    """
    return [dict(row._mapping) for row in _fetch(conn, sql, params)]


def collect_monthly_amounts(
    conn: sa.Connection, month: str | None
) -> list[dict[str, Any]]:
    """一个月一张的「旧口径 vs 新口径」对照底稿。"""
    locked = tuple(PAYROLL_LOCKED_STATUSES)

    sql = """
        select
            a.period_month as period_month,
            coalesce(sum(a.pre_commission_amount) filter (
                where a.allocation_scope = 'company'
            ), 0) as company_pool_all_versions,
            coalesce(sum(a.pre_commission_amount) filter (
                where a.allocation_scope = 'company'
                  and a.calculation_version = :calc_version
            ), 0) as company_pool_current_version,
            coalesce(sum(a.performance_amount + a.commission_amount) filter (
                where a.source_payroll_status in :locked
            ), 0) as allocation_without_version_filter,
            coalesce(sum(a.performance_amount + a.commission_amount) filter (
                where a.source_payroll_status in :locked
                  and a.calculation_version = :calc_version
            ), 0) as allocation_with_version_filter
        from finance.employee_labor_cost_allocations a
    """
    params: dict[str, Any] = {
        "calc_version": LABOR_COST_CALCULATION_VERSION,
        "locked": locked,
    }
    if month:
        sql += " where a.period_month = :month"
        params["month"] = month
    sql += " group by a.period_month order by a.period_month"

    allocation_rows = [dict(row._mapping) for row in _fetch_in(conn, sql, params)]

    # 工资单 total_cost（旧审批落库口径：快照取的就是它，且**不看工资单状态**）
    payroll_sql = """
        select year_month as period_month,
               count(*) as payroll_rows,
               sum(total_cost) as payroll_total_cost,
               sum(base_salary + position_salary + allowances + bonus
                   + social_insurance_company + housing_fund_company)
                   as pre_commission_labor_cost
        from a_class.payroll_records
    """
    payroll_params: dict[str, Any] = {}
    if month:
        payroll_sql += " where year_month = :month"
        payroll_params["month"] = month
    payroll_sql += " group by year_month order by year_month"
    payroll_rows = {
        str(row._mapping["period_month"]): dict(row._mapping)
        for row in _fetch(conn, payroll_sql, payroll_params)
    }

    # 锁定状态工资单的 total_cost（员工口径只看锁定的单）
    locked_payroll_sql = """
        select year_month as period_month,
               count(*) as locked_payroll_rows,
               sum(total_cost) as locked_payroll_total_cost
        from a_class.payroll_records
        where status in :locked
    """
    locked_params: dict[str, Any] = {"locked": locked}
    if month:
        locked_payroll_sql += " and year_month = :month"
        locked_params["month"] = month
    locked_payroll_sql += " group by year_month order by year_month"
    locked_payroll_rows = {
        str(row._mapping["period_month"]): dict(row._mapping)
        for row in _fetch_in(conn, locked_payroll_sql, locked_params)
    }

    # 利润基数（去重后）按月汇总
    basis_rows = collect_basis_rows(conn, month)
    basis_by_month: dict[str, float] = {}
    for row in basis_rows:
        period = str(row["period_month"])
        basis_by_month[period] = basis_by_month.get(period, 0.0) + float(
            row.get("profit_basis_amount") or 0.0
        )

    months = sorted(
        set(basis_by_month)
        | {str(item["period_month"]) for item in allocation_rows}
        | set(payroll_rows)
        | set(locked_payroll_rows)
    )

    allocation_by_month = {str(item["period_month"]): item for item in allocation_rows}

    result: list[dict[str, Any]] = []
    for period in months:
        allocation = allocation_by_month.get(period, {})
        payroll = payroll_rows.get(period, {})
        locked_payroll = locked_payroll_rows.get(period, {})

        basis_total = basis_by_month.get(period, 0.0)
        company_pool = float(allocation.get("company_pool_current_version") or 0.0)
        allocation_old = float(
            allocation.get("allocation_without_version_filter") or 0.0
        )
        allocation_new = float(allocation.get("allocation_with_version_filter") or 0.0)
        payroll_total_cost = float(payroll.get("payroll_total_cost") or 0.0)

        # 旧口径：净利润 = Σ利润基数 − 公司池二次扣减
        net_profit_old = basis_total - company_pool
        # 新口径：净利润 = Σ利润基数（公司池已在各店利润基数里摊过，不再扣）
        net_profit_new = basis_total

        result.append(
            {
                "period_month": period,
                "profit_basis_total": basis_total,
                "company_pool_double_deducted": company_pool,
                "net_profit_old": net_profit_old,
                "net_profit_new": net_profit_new,
                "allocation_old_no_version_filter": allocation_old,
                "allocation_new_with_version_filter": allocation_new,
                "allocation_version_filter_delta": allocation_old - allocation_new,
                "payroll_rows": int(payroll.get("payroll_rows") or 0),
                "payroll_total_cost": payroll_total_cost,
                "locked_payroll_rows": int(
                    locked_payroll.get("locked_payroll_rows") or 0
                ),
                "locked_payroll_total_cost": float(
                    locked_payroll.get("locked_payroll_total_cost") or 0.0
                ),
                # 快照口径（旧审批落库）：按工资单 total_cost 扣
                "company_retained_old_snapshot": net_profit_old - payroll_total_cost,
                # 旧草稿口径（审批门槛校验用的）：按分摊表 performance+commission 扣
                "company_retained_old_draft": net_profit_old - allocation_old,
                # 新看板口径
                "company_retained_new": net_profit_new - allocation_new,
            }
        )
    return result


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------


def _money(value: Any) -> str:
    try:
        return "{:,.2f}".format(float(value or 0.0))
    except (TypeError, ValueError):
        return "—"


def _int(value: Any) -> str:
    try:
        return "{:,}".format(int(value or 0))
    except (TypeError, ValueError):
        return "—"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_（无数据）_\n"
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, sep] + body) + "\n"


def render_report(
    *,
    month: str | None,
    basis_distribution: list[dict[str, Any]],
    allocation_distribution: list[dict[str, Any]],
    monthly: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("# 月度利润看板 · 上线前只读体检（口径切换前后同月对比）\n")
    lines.append(
        "- 生成方式：`python scripts/check_monthly_profit_dashboard_readiness.py`（**只读**）\n"
        "- 口径常量来源：`backend/services/labor_cost_projection_service.py`"
        "（`LABOR_COST_CALCULATION_VERSION = {0}`）、"
        "`backend/services/hr_employee_lifecycle.py`"
        "（`PAYROLL_LOCKED_STATUSES = {1}`）、"
        "`backend/services/labor_cost_policy_service.py`（legacy 版本判定）\n".format(
            LABOR_COST_CALCULATION_VERSION, list(PAYROLL_LOCKED_STATUSES)
        )
    )
    lines.append(
        "- 覆盖范围：{0}\n".format(
            f"`period_month = {month}`" if month else "**全部月份**"
        )
    )

    lines.append("\n## A · 店铺利润基数的口径版本分布\n")
    lines.append(
        "真源表 `finance.shop_profit_basis`。同月内不同店可能落在不同版本上"
        "（历史 `A_ONLY_V1` 与当前 `SETTLEMENT_BASIS_V1` 混存）⇒ "
        "看板按「非 legacy 行优先」去重，不在看板里另写一套版本判定。\n"
    )
    rows = [
        [
            str(item["period_month"]),
            str(item["basis_version"]),
            _int(item["row_count"]),
            _int(item["shop_count"]),
            _money(item["basis_total"]),
        ]
        for item in basis_distribution
    ]
    lines.append(
        _table(["月份", "basis_version", "行数", "店铺数", "利润基数合计"], rows)
    )

    lines.append("\n## B · 人力成本分摊表的计算版本分布\n")
    lines.append(
        "真源表 `finance.employee_labor_cost_allocations`。"
        "唯一索引**含 `calculation_version`** ⇒ 同一员工同月可以并存两版 ⇒ "
        "**查询必须带版本过滤**（旧代码漏了，会把人力成本算两遍）。\n"
    )
    rows = [
        [
            str(item["period_month"]),
            str(item["calculation_version"]),
            str(item["allocation_scope"]),
            _int(item["row_count"]),
            _money(item["pre_commission_total"]),
            _money(item["performance_total"]),
            _money(item["commission_total"]),
        ]
        for item in allocation_distribution
    ]
    lines.append(
        _table(
            [
                "月份",
                "calculation_version",
                "scope",
                "行数",
                "pre_commission 合计",
                "performance 合计",
                "commission 合计",
            ],
            rows,
        )
    )

    lines.append("\n## C · 公司人力成本池被二次扣减的金额\n")
    lines.append(
        "旧口径在算完各店利润基数后，又把 `allocation_scope='company'` 的 "
        "`pre_commission_amount` 整池减了一次 —— 但这笔钱在利润基数里"
        "**已经摊过一次**（`profit_basis_service`）。下表是每月被多扣的金额。\n"
    )
    rows = [
        [
            str(item["period_month"]),
            _money(item["company_pool_double_deducted"]),
            _money(item["net_profit_old"]),
            _money(item["net_profit_new"]),
            _money(item["net_profit_new"] - item["net_profit_old"]),
        ]
        for item in monthly
    ]
    lines.append(
        _table(
            ["月份", "公司池二次扣减", "净利润（旧）", "净利润（新）", "差额"],
            rows,
        )
    )

    lines.append("\n## D · 口径切换前后同月对比（核心）\n")
    lines.append(
        "| 列 | 含义 |\n| --- | --- |\n"
        "| 净利润（旧） | Σ各店利润基数 − 公司池二次扣减 |\n"
        "| 净利润（新） | Σ各店利润基数（公司池不再扣） |\n"
        "| 员工侧分配（旧·无版本过滤） | Σ(绩效工资 + 提成)，**不过滤计算版本** |\n"
        "| 员工侧分配（新·有版本过滤） | 同上，但 `calculation_version = {0}` |\n"
        "| 工资单 total_cost | 旧审批落库口径扣的人员成本（快照取的就是它） |\n"
        "| 公司留存（旧·快照） | 净利润（旧） − 工资单 total_cost |\n"
        "| 公司留存（旧·草稿） | 净利润（旧） − 员工侧分配（旧·无版本过滤） |\n"
        "| **公司留存（新）** | 净利润（新） − 员工侧分配（新·有版本过滤） |\n\n".format(
            LABOR_COST_CALCULATION_VERSION
        )
    )
    rows = []
    for item in monthly:
        rows.append(
            [
                str(item["period_month"]),
                _money(item["net_profit_old"]),
                _money(item["net_profit_new"]),
                _money(item["allocation_old_no_version_filter"]),
                _money(item["allocation_new_with_version_filter"]),
                _money(item["payroll_total_cost"]),
                _money(item["company_retained_old_snapshot"]),
                _money(item["company_retained_old_draft"]),
                _money(item["company_retained_new"]),
            ]
        )
    lines.append(
        _table(
            [
                "月份",
                "净利润(旧)",
                "净利润(新)",
                "员工侧分配(旧·无版本过滤)",
                "员工侧分配(新·有版本过滤)",
                "工资单total_cost",
                "公司留存(旧·快照)",
                "公司留存(旧·草稿)",
                "公司留存(新)",
            ],
            rows,
        )
    )

    lines.append("\n## E · 结论与上线提示\n")
    months_with_pool = [
        item for item in monthly if abs(item["company_pool_double_deducted"]) > 0.005
    ]
    months_with_version_mix = [
        item for item in monthly if abs(item["allocation_version_filter_delta"]) > 0.005
    ]
    months_with_snapshot_gap = [
        item
        for item in monthly
        if abs(item["payroll_total_cost"] - item["allocation_new_with_version_filter"])
        > 0.005
    ]

    lines.append(
        "- **公司池二次扣减**：{0}\n".format(
            (
                "涉及 {0} 个月（{1}）".format(
                    len(months_with_pool),
                    "、".join(str(i["period_month"]) for i in months_with_pool),
                )
            )
            if months_with_pool
            else "**没有月份命中**（分摊表里没有 company scope 的成本池）"
        )
    )
    lines.append(
        "- **版本过滤缺口**：{0}\n".format(
            (
                "涉及 {0} 个月（{1}）—— 这些月份的旧口径人力成本虚高".format(
                    len(months_with_version_mix),
                    "、".join(str(i["period_month"]) for i in months_with_version_mix),
                )
            )
            if months_with_version_mix
            else "**没有月份命中**（同月只有一版计算结果）"
        )
    )
    lines.append(
        "- **快照口径重复扣减**：{0}\n".format(
            (
                "涉及 {0} 个月 —— 工资单 total_cost 与「绩效工资+提成」不等，"
                "差额部分在利润基数里已经扣过一次".format(len(months_with_snapshot_gap))
            )
            if months_with_snapshot_gap
            else "**没有月份命中**"
        )
    )

    months_negative_old = [
        item for item in monthly if item["company_retained_old_snapshot"] < -0.005
    ]
    months_negative_new = [
        item for item in monthly if item["company_retained_new"] < -0.005
    ]
    lines.append(
        "- **旧口径下公司留存为负的月份**：{0}\n".format(
            (
                "{0} —— 旧口径扣掉的人员成本**超过了当月利润**，"
                "公司在这些月份账面上是亏的（这是重复扣减最直观的症状）".format(
                    "、".join(str(i["period_month"]) for i in months_negative_old)
                )
            )
            if months_negative_old
            else "**没有月份命中**"
        )
    )
    lines.append(
        "- **新口径下公司留存为负的月份**：{0}\n".format(
            (
                "{0} —— 分配确实超过了利润（结算系数最高 1.2 + 不占利润基数的绩效工资，"
                "属设计内可能），需业务判断".format(
                    "、".join(str(i["period_month"]) for i in months_negative_new)
                )
            )
            if months_negative_new
            else "**没有月份命中**"
        )
    )
    lines.append(
        "\n> ⚠️ **上线必须写明**：看板口径修正了上述三处 ⇒ "
        "**切换后所有历史月份的公司留存数字都会变化**。"
        "这是**修正**，不是回归 —— 请提前向管理层说明。\n"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def _resolve_database_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_value = os.getenv("DATABASE_URL")
    if env_value:
        return env_value
    # 回落到仓库根的 .env（**不打印连接串**，避免凭据进日志）
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip().strip('"').strip("'")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="月度利润看板上线前只读体检（口径切换前后同月对比）"
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="数据库连接串（默认取环境变量 DATABASE_URL，其次读仓库根 .env）",
    )
    parser.add_argument("--month", default=None, help="只看某个月（YYYY-MM）")
    parser.add_argument(
        "--out",
        default=None,
        help="报告输出路径（默认写到 docs/reports/ 下带日期的文件）",
    )
    parser.add_argument(
        "--print",
        dest="print_report",
        action="store_true",
        help="同时把报告打到 stdout",
    )
    args = parser.parse_args(argv)

    database_url = _resolve_database_url(args.database_url)
    if not database_url:
        print("[FAIL] 找不到数据库连接串：请给 --database-url 或设置 DATABASE_URL")
        return 2

    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            # 只读事务：万一脚本里写错语句，数据库会直接拒绝
            conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            basis_distribution = collect_basis_version_distribution(conn, args.month)
            allocation_distribution = collect_allocation_version_distribution(
                conn, args.month
            )
            monthly = collect_monthly_amounts(conn, args.month)
    except Exception as exc:  # pragma: no cover - 环境问题
        print("[FAIL] 体检失败：{0}".format(exc))
        return 2
    finally:
        engine.dispose()

    report = render_report(
        month=args.month,
        basis_distribution=basis_distribution,
        allocation_distribution=allocation_distribution,
        monthly=monthly,
    )

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
    else:
        DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        scope = args.month or "all-months"
        out_path = DEFAULT_REPORT_DIR / (
            "monthly-profit-dashboard-readiness-{0}.md".format(scope)
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print("体检完成：{0} 个月，报告写入 {1}".format(len(monthly), out_path))
    if args.print_report:
        print()
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""自动化验收：我的收入链路（6.5/6.6/6.7/6.8/6.8a/6.8c）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import inspect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import and_, desc, exists, select, text
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.models.database import AsyncSessionLocal  # noqa: E402
from backend.routers.hr_employee import get_my_income  # noqa: E402
from modules.core.db import (  # noqa: E402
    DimUser,
    Employee,
    EmployeeShopAssignment,
    FactAuditLog,
    PayrollRecord,
)


@dataclass
class LinkedSample:
    user_id: int
    username: str
    employee_code: str
    sample_month: Optional[str] = None


async def _pick_linked_user() -> Optional[LinkedSample]:
    async with AsyncSessionLocal() as db:
        # 优先选择至少有一条“提成或绩效非零”样例月的已关联用户（兼容中文列环境）。
        raw = await db.execute(
            text(
                """
                select
                  u.user_id as user_id,
                  u.username as username,
                  e.employee_code as employee_code,
                  ec."年月" as sample_month
                from dim_users u
                join a_class.employees e on e.user_id = u.user_id
                left join c_class.employee_commissions ec
                  on ec."员工编号" = e.employee_code
                left join c_class.employee_performance ep
                  on ep."员工编号" = e.employee_code
                 and ep."年月" = ec."年月"
                where u.is_active = true
                  and u.status = 'active'
                  and (
                    coalesce(ec."提成金额", 0) > 0
                    or coalesce(ep."绩效得分", 0) > 0
                  )
                order by ec."年月" desc nulls last
                limit 1
                """
            )
        )
        row = raw.mappings().first()
        if row:
            return LinkedSample(
                user_id=row["user_id"],
                username=row["username"],
                employee_code=row["employee_code"],
                sample_month=row.get("sample_month"),
            )

        result = await db.execute(
            select(
                DimUser.user_id,
                DimUser.username,
                Employee.employee_code,
            )
            .join(Employee, Employee.user_id == DimUser.user_id)
            .where(
                DimUser.is_active.is_(True),
                DimUser.status == "active",
                Employee.user_id.is_not(None),
            )
            .order_by(Employee.updated_at.desc())
            .limit(1)
        )
        row = result.first()
        if not row:
            return None
        return LinkedSample(
            user_id=row.user_id,
            username=row.username,
            employee_code=row.employee_code,
                sample_month=None,
        )


async def _candidate_months(employee_code: str, preferred_month: Optional[str] = None) -> list[str]:
    months: list[str] = []
    if preferred_month:
        months.append(preferred_month)
    current = datetime.now().strftime("%Y-%m")
    months.append(current)
    async with AsyncSessionLocal() as db:
        r1 = await db.execute(
            select(EmployeeShopAssignment.year_month)
            .where(EmployeeShopAssignment.employee_code == employee_code)
            .order_by(desc(EmployeeShopAssignment.year_month))
            .limit(6)
        )
        months.extend([m for m in r1.scalars().all() if m])

        r2 = await db.execute(
            select(PayrollRecord.year_month)
            .where(PayrollRecord.employee_code == employee_code)
            .order_by(desc(PayrollRecord.year_month))
            .limit(6)
        )
        months.extend([m for m in r2.scalars().all() if m])
    # 去重并保持顺序
    uniq: list[str] = []
    for m in months:
        if m not in uniq:
            uniq.append(m)
    return uniq


async def _pick_unlinked_user_id() -> Optional[Tuple[int, str]]:
    async with AsyncSessionLocal() as db:
        has_employee = exists(select(Employee.id).where(Employee.user_id == DimUser.user_id))
        result = await db.execute(
            select(DimUser.user_id, DimUser.username)
            .where(
                DimUser.is_active.is_(True),
                DimUser.status == "active",
                ~has_employee,
            )
            .order_by(DimUser.user_id.asc())
            .limit(1)
        )
        row = result.first()
        if not row:
            return None
        return row.user_id, row.username


async def _count_me_income_audit(user_id: int, since: datetime) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FactAuditLog.log_id)
            .where(
                FactAuditLog.user_id == user_id,
                FactAuditLog.resource_type == "me/income",
                FactAuditLog.created_at >= since,
            )
        )
        return len(result.scalars().all())


async def _search_audit_by_user_and_time(user_id: int, start_at: datetime, end_at: datetime) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FactAuditLog.log_id)
            .where(
                and_(
                    FactAuditLog.user_id == user_id,
                    FactAuditLog.created_at >= start_at,
                    FactAuditLog.created_at <= end_at,
                )
            )
            .order_by(desc(FactAuditLog.created_at))
            .limit(200)
        )
        return len(result.scalars().all())


async def _invoke_me_income(user_id: int, year_month: Optional[str]) -> Optional[Dict[str, Any]]:
    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None
        resp = await get_my_income(
            request=request, year_month=year_month, current_user=user, db=db
        )
        if hasattr(resp, "model_dump"):
            return resp.model_dump()
        if isinstance(resp, dict):
            return resp
        return None


async def main() -> int:
    parser = argparse.ArgumentParser(description="验证我的收入验收项")
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "reports" / "migration_reconciliation" / "my_income_acceptance_20260315.md"),
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    lines = [
        "# 我的收入验收自动化报告",
        "",
        f"- 生成时间(UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "- 执行方式: 直接调用路由函数 + 真实数据库会话",
        "",
        "## 验收结果",
        "",
    ]

    linked = await _pick_linked_user()
    if not linked:
        lines.append("- [FAIL] 6.5/6.7/6.8a: 未找到已关联且存在非空收入样例的用户")
    else:
        months = await _candidate_months(linked.employee_code, linked.sample_month)
        chosen_month: Optional[str] = None
        data: Dict[str, Any] = {}
        status = "N/A"
        for month in months:
            payload = await _invoke_me_income(linked.user_id, month)
            if payload and isinstance(payload, dict):
                data = payload
                status = "200"
                commission = float(data.get("commission_amount", 0) or 0)
                score = float(data.get("performance_score", 0) or 0)
                if commission > 0 or score > 0:
                    chosen_month = month
                    break
        if not chosen_month and months:
            chosen_month = months[0]
            data = await _invoke_me_income(linked.user_id, chosen_month) or {}
            status = "200" if data else "N/A"
        ok_65 = isinstance(data, dict) and data.get("linked") is True
        lines.append(
            f"- {'[OK]' if ok_65 else '[FAIL]'} 6.5 已关联员工可查看本人收入: status={status}, linked={data.get('linked') if isinstance(data, dict) else 'N/A'}"
        )

        # 6.7：历史月份查询（使用样例月份）
        period = data.get("period") if isinstance(data, dict) else None
        ok_67 = period == chosen_month
        lines.append(
            f"- {'[OK]' if ok_67 else '[FAIL]'} 6.7 月份切换可查历史: query={chosen_month}, period={period}"
        )

        # 6.8a：至少一个自然月存在非空提成或绩效
        commission_amount = float(data.get("commission_amount", 0) or 0) if isinstance(data, dict) else 0.0
        performance_score = float(data.get("performance_score", 0) or 0) if isinstance(data, dict) else 0.0
        ok_68a = commission_amount > 0 or performance_score > 0
        lines.append(
            f"- {'[OK]' if ok_68a else '[FAIL]'} 6.8a 非空样例数据: month={chosen_month}, commission_amount={commission_amount}, performance_score={performance_score}"
        )

        # 6.8：安全与审计（接口只允许当前用户上下文）
        before = await _count_me_income_audit(linked.user_id, now - timedelta(minutes=5))
        _ = await _invoke_me_income(linked.user_id, chosen_month or datetime.now().strftime("%Y-%m"))
        after = await _count_me_income_audit(linked.user_id, now - timedelta(minutes=5))
        has_employee_param = "employee_code" in inspect.signature(get_my_income).parameters
        ok_68 = (not has_employee_param) and (after >= before + 1)
        lines.append(
            f"- {'[OK]' if ok_68 else '[FAIL]'} 6.8 非本人不可越权+审计可追溯: no_employee_param={not has_employee_param}, audit_delta={after - before}"
        )

        # 6.8c：按 user_id + 时间区间检索
        searched = await _search_audit_by_user_and_time(
            linked.user_id, now - timedelta(days=1), datetime.now(timezone.utc) + timedelta(minutes=1)
        )
        ok_68c = searched > 0
        lines.append(
            f"- {'[OK]' if ok_68c else '[FAIL]'} 6.8c 审计日志可检索(user_id+时间区间): hit={searched}"
        )

    unlinked = await _pick_unlinked_user_id()
    if not unlinked:
        lines.append("- [WARN] 6.6 未找到未关联员工的 active 用户，无法自动化验证")
    else:
        data = await _invoke_me_income(unlinked[0], None)
        ok_66 = isinstance(data, dict) and data.get("linked") is False
        lines.append(
            f"- {'[OK]' if ok_66 else '[FAIL]'} 6.6 未关联用户返回引导态: status=200, linked={data.get('linked') if isinstance(data, dict) else 'N/A'}"
        )

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本报告用于验收闭环；若出现 [WARN]/[FAIL]，需按结果补充人工点验或环境数据。",
        ]
    )

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] report written: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

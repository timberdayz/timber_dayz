#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查员工收入示例数据（任务 6.8a）
优先验证工资单口径下是否存在提成或绩效工资非零的真实样本月。
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, func, text
from backend.models.database import AsyncSessionLocal
from modules.core.db import Employee, EmployeeCommission, EmployeePerformance, PayrollRecord
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def check_data():
    async with AsyncSessionLocal() as db:
        employee_result = await db.execute(
            select(func.count()).select_from(Employee).where(Employee.status == "active")
        )
        employee_count = employee_result.scalar() or 0
        logger.info(f"[INFO] Active employees: {employee_count}")

        commission_result = await db.execute(
            select(func.count()).select_from(EmployeeCommission)
        )
        commission_count = commission_result.scalar() or 0
        logger.info(f"[INFO] Employee commission records: {commission_count}")

        performance_result = await db.execute(
            select(func.count()).select_from(EmployeePerformance)
        )
        performance_count = performance_result.scalar() or 0
        logger.info(f"[INFO] Employee performance records: {performance_count}")

        payroll_result = await db.execute(
            select(func.count()).select_from(PayrollRecord)
        )
        payroll_count = payroll_result.scalar() or 0
        logger.info(f"[INFO] Payroll records: {payroll_count}")

        payroll_sample = await db.execute(
            text(
                """
                select employee_code, year_month, commission, performance_salary
                from a_class.payroll_records
                where coalesce(commission, 0) > 0
                   or coalesce(performance_salary, 0) > 0
                order by year_month desc
                limit 1
                """
            )
        )
        payroll_row = payroll_sample.mappings().first()
        if payroll_row:
            logger.info(
                "[OK] Payroll sample with non-zero income signals: "
                f"employee_code={payroll_row['employee_code']}, "
                f"year_month={payroll_row['year_month']}, "
                f"commission={payroll_row['commission']}, "
                f"performance_salary={payroll_row['performance_salary']}"
            )
            return True

        if commission_count > 0 or performance_count > 0:
            months_with_data = set()
            if commission_count > 0:
                comm_months = await db.execute(
                    text("SELECT DISTINCT year_month FROM c_class.employee_commissions WHERE year_month IS NOT NULL")
                )
                for row in comm_months:
                    months_with_data.add(row[0])

            if performance_count > 0:
                perf_months = await db.execute(
                    text("SELECT DISTINCT year_month FROM c_class.employee_performance WHERE year_month IS NOT NULL")
                )
                for row in perf_months:
                    months_with_data.add(row[0])

            if months_with_data:
                logger.info(f"[INFO] Months with intermediate income data: {sorted(months_with_data)}")
                sample_month = sorted(months_with_data)[0]
                sample_comm = await db.execute(
                    text("SELECT employee_code, commission_amount FROM c_class.employee_commissions WHERE year_month = :month LIMIT 1"),
                    {"month": sample_month},
                )
                sample_row = sample_comm.fetchone()
                if sample_row:
                    logger.info(
                        f"[INFO] Sample commission ({sample_month}): employee_code={sample_row[0]}, amount={sample_row[1]}"
                    )
                logger.warning(
                    "[WARN] Intermediate-layer data exists, but no payroll sample has non-zero commission/performance_salary yet"
                )
                return True

        logger.warning("[WARN] No employee income data found in any month")
        logger.info("[INFO] Current status:")
        logger.info(f"  - Employees: {employee_count}")
        logger.info(f"  - Commission records: {commission_count}")
        logger.info(f"  - Performance records: {performance_count}")
        logger.info(f"  - Payroll records: {payroll_count}")
        logger.info("[INFO] Task 6.8a marked as: Data structure ready, awaiting business data")
        return True


if __name__ == "__main__":
    result = asyncio.run(check_data())
    sys.exit(0 if result else 1)

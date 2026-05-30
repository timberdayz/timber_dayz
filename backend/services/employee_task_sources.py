from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.employee_task_policy import validate_task_target_permission
from backend.services.employee_task_service import EmployeeTaskService
from modules.core.db import Employee, EmployeeShopAssignment


async def resolve_shop_supervisor_user_id(
    db: AsyncSession,
    *,
    year_month: str,
    platform_code: str,
    shop_id: str,
) -> int:
    result = await db.execute(
        select(EmployeeShopAssignment).where(
            EmployeeShopAssignment.year_month == year_month,
            EmployeeShopAssignment.platform_code == platform_code,
            EmployeeShopAssignment.shop_id == shop_id,
            EmployeeShopAssignment.role == "supervisor",
            EmployeeShopAssignment.status == "active",
        )
    )
    assignments = result.scalars().all()

    if not assignments:
        raise ValueError("No supervisor assignment found for this shop and month")
    if len(assignments) > 1:
        raise ValueError("Found multiple supervisor assignments for this shop and month")

    employee_code = assignments[0].employee_code
    employee_result = await db.execute(
        select(Employee).where(Employee.employee_code == employee_code)
    )
    employee = employee_result.scalar_one_or_none()
    if employee is None or not employee.user_id:
        raise ValueError("Supervisor employee is not linked to a user account")
    return int(employee.user_id)


async def sync_monthly_cost_entry_task(
    db: AsyncSession,
    *,
    year_month: str,
    platform_code: str,
    shop_id: str,
    created_by: int | None,
    owner_permissions: set[str] | None = None,
):
    owner_user_id = await resolve_shop_supervisor_user_id(
        db,
        year_month=year_month,
        platform_code=platform_code,
        shop_id=shop_id,
    )
    validate_task_target_permission("monthly_cost_entry", owner_permissions or {"expense-management"})
    service = EmployeeTaskService(db)
    task_id = f"monthly-cost:{year_month}:{platform_code}:{shop_id}"
    return await service.create_task(
        task_id=task_id,
        task_type="monthly_cost_entry",
        task_category="execution",
        title=f"Monthly cost entry for {shop_id} ({year_month})",
        owner_user_id=owner_user_id,
        created_by=created_by,
        source_type="system",
        source_module="expense-management",
        source_record_type="monthly_cost",
        source_record_id=f"{year_month}:{platform_code}:{shop_id}",
        completion_schema={
            "kind": "monthly_cost_entry",
            "required_fields": ["year_month", "shop_id"],
        },
    )


async def sync_performance_confirmation_task(
    db: AsyncSession,
    *,
    year_month: str,
    employee_code: str,
    created_by: int | None,
    owner_permissions: set[str] | None = None,
):
    employee_result = await db.execute(
        select(Employee).where(Employee.employee_code == employee_code)
    )
    employee = employee_result.scalar_one_or_none()
    if employee is None or not employee.user_id:
        raise ValueError("Employee is not linked to a user account")

    validate_task_target_permission("performance_confirmation", owner_permissions or {"performance:read"})
    service = EmployeeTaskService(db)
    task_id = f"performance-confirmation:{year_month}:{employee_code}"
    existing = await service.repository.get_task_by_task_id(task_id)
    if existing is not None:
        return await service.get_task_detail(task_id)
    return await service.create_task(
        task_id=task_id,
        task_type="performance_confirmation",
        task_category="confirmation",
        title=f"Performance confirmation for {employee_code} ({year_month})",
        owner_user_id=int(employee.user_id),
        created_by=created_by,
        source_type="system",
        source_module="performance-management",
        source_record_type="employee_performance",
        source_record_id=f"{year_month}:{employee_code}",
        completion_schema={
            "kind": "performance_confirmation",
            "required_fields": ["confirmation_result"],
        },
    )

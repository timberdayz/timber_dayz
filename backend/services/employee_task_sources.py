from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.employee_task_policy import validate_task_target_permission
from backend.services.employee_task_service import EmployeeTaskService
from modules.core.db import Employee

# ⚠️ 「每月成本录入」协同任务整条链路已下线（2026-11-26）。
# 原来那两个「按归属角色找店铺负责人」的函数依赖已退休的归属「角色」字段
# ⇒ 那条链路没有存在意义。
# 该任务生产上自 2026-06-18 起已停摆（归属表 0 行 ⇒ 必然找不到负责人，
# 异常又被吞成 warning），删除**不改变现状行为**，只是不再留半死代码。


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

    validate_task_target_permission(
        "performance_confirmation", owner_permissions or {"performance:read"}
    )
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

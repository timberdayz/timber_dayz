"""
用户管理API路由 - 管理员端点

包含: CRUD、恢复、密码重置、解锁、审批、拒绝、待审批列表、未关联用户、已删除用户
"""

# ⚠️ 本文件**故意不加** ``from __future__ import annotations``：
#    ``role_based_rate_limit`` 的装饰器会把路由函数包在**别的模块**里，
#    延迟求值的注解字符串会在那个模块的 globals 里找不到 ``UserIdBatchRequest``
#    ⇒ FastAPI 退化成「query 参数」⇒ 带 body 的路由直接 422。
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.auth import (
    ApproveUserRequest,
    PendingUserResponse,
    RejectUserRequest,
    UserIdBatchRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    UnlockAccountRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from backend.services.audit_service import audit_service
from backend.services.hr_employee_lifecycle import employee_status
from backend.utils.api_response import (
    error_response,
    get_timestamp,
    pagination_response,
    success_response,
)
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import DimRole, DimUser, Employee, UserApprovalLog, UserSession
from modules.core.logger import get_logger

try:
    from backend.middleware.rate_limiter import limiter, role_based_rate_limit
except ImportError:
    limiter = None
    role_based_rate_limit = None

router = APIRouter(prefix="/users", tags=["用户管理"])
logger = get_logger(__name__)


async def _get_employee_for_user(db: AsyncSession, user_id: int):
    """查询与 user_id 关联的员工，返回 (employee_id, employee_code, employee_name) 或 (None, None, None)。"""
    result = await db.execute(select(Employee).where(Employee.user_id == user_id))
    emp = result.scalar_one_or_none()
    if not emp:
        return None, None, None
    return emp.id, emp.employee_code, emp.name


async def _clear_employee_user_id(db: AsyncSession, user_id: int) -> None:
    """将 employees 中 user_id=user_id 的记录的 user_id 置空。"""
    await db.execute(
        update(Employee).where(Employee.user_id == user_id).values(user_id=None)
    )


async def _describe_account_occupant(db: AsyncSession, user_id: int) -> str:
    """描述占用某个员工档案的账号：``用户名（用户ID N）``。

    账号行可能已被物理删除（脏数据），此时只给出用户 ID，不臆造用户名。
    """
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    occupant = result.scalar_one_or_none()
    if occupant is None:
        return f"（用户ID {user_id}）"
    return f"{occupant.username}（用户ID {user_id}）"


@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """创建用户"""
    result = await db.execute(
        select(DimUser).where(DimUser.username == user_data.username)
    )
    existing_user = result.scalar_one_or_none()
    if existing_user:
        return error_response(
            code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
            message="Username already exists",
            error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
            recovery_suggestion="请使用不同的用户名",
            status_code=400,
        )

    result = await db.execute(select(DimUser).where(DimUser.email == user_data.email))
    existing_email = result.scalar_one_or_none()
    if existing_email:
        return error_response(
            code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
            message="Email already exists",
            error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
            recovery_suggestion="请使用不同的邮箱地址",
            status_code=400,
        )

    from backend.services.auth_service import auth_service

    user = DimUser(
        username=user_data.username,
        email=user_data.email,
        password_hash=auth_service.hash_password(user_data.password),
        full_name=user_data.full_name,
        is_active=user_data.is_active,
    )

    db.add(user)
    await db.flush()

    for role_name in user_data.roles:
        result = await db.execute(
            select(DimRole).where(
                or_(DimRole.role_name == role_name, DimRole.role_code == role_name)
            )
        )
        role = result.scalar_one_or_none()
        if role:
            user.roles.append(role)

    await db.commit()
    await db.refresh(user, ["roles"])

    await audit_service.log_action(
        user_id=current_user.user_id,
        action="create_user",
        resource="user",
        resource_id=str(user.user_id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details={"username": user.username, "email": user.email},
    )

    emp_id, emp_code, emp_name = await _get_employee_for_user(db, user.user_id)
    return UserResponse(
        id=user.user_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=[role.role_name for role in user.roles],
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login,
        employee_id=emp_id,
        employee_code=emp_code,
        employee_name=emp_name,
    )


@router.get("/")
async def get_users(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    active_only: bool = False,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """获取用户列表(分页)"""
    from sqlalchemy import func

    offset = (page - 1) * page_size

    conditions = [DimUser.status != "deleted"]
    if active_only:
        conditions.extend([DimUser.status == "active", DimUser.is_active.is_(True)])
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                DimUser.username.ilike(pattern),
                DimUser.email.ilike(pattern),
                DimUser.full_name.ilike(pattern),
            )
        )

    count_result = await db.execute(
        select(func.count(DimUser.user_id)).where(and_(*conditions))
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(and_(*conditions))
        .offset(offset)
        .limit(page_size)
        .order_by(DimUser.created_at.desc())
    )
    users = result.scalars().all()
    user_ids = [u.user_id for u in users]
    emp_result = await db.execute(
        select(Employee).where(Employee.user_id.in_(user_ids))
    )
    employees = emp_result.scalars().all()
    emp_by_user = {e.user_id: (e.id, e.employee_code, e.name) for e in employees}
    user_responses = [
        UserResponse(
            id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=[role.role_name for role in user.roles],
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login,
            employee_id=emp_by_user.get(user.user_id, (None, None, None))[0],
            employee_code=emp_by_user.get(user.user_id, (None, None, None))[1],
            employee_name=emp_by_user.get(user.user_id, (None, None, None))[2],
        )
        for user in users
    ]

    return pagination_response(
        data=[user.dict() for user in user_responses],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/unlinked")
async def get_unlinked_users(
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """获取账号池：尚未关联员工档案的账号 + 已被已离职员工占用的账号。

    返回结构（在原有结构上**新增字段**，不破坏既有契约）：

    * ``data`` —— 账号池里的账号，每项为 ``{id, username, email, blocked_by_employee}``。
      ``blocked_by_employee`` 为 ``None`` 表示「没有员工档案占用」；
      非空则说明这个号**被一个已离职员工占着**（管理员需要先解绑或换人）。
    * ``occupied_by_departed_employee`` —— 只含被已离职员工占用的账号，
      便于前端单独展示「这些号要处理」。

    ⚠️ 「已离职」口径来自 ``backend/services/hr_employee_lifecycle.py``（在职状态词表）。
    """
    from sqlalchemy import and_

    result = await db.execute(
        select(DimUser).where(and_(DimUser.is_active, DimUser.status != "deleted"))
    )
    users = result.scalars().all()
    unlinked: list[dict] = []
    occupied: list[dict] = []
    for u in users:
        r = await db.execute(select(Employee).where(Employee.user_id == u.user_id))
        emp = r.scalar_one_or_none()
        if emp is None:
            unlinked.append(
                {
                    "id": u.user_id,
                    "username": u.username,
                    "email": u.email or "",
                    "blocked_by_employee": None,
                }
            )
            continue
        if employee_status(emp) != "inactive":
            # 关联着在职员工 ⇒ 不在「账号池」里（正常占用）
            continue
        unlinked.append(
            {
                "id": u.user_id,
                "username": u.username,
                "email": u.email or "",
                "blocked_by_employee": {
                    "employee_code": emp.employee_code,
                    "employee_name": emp.name,
                    "employee_status": employee_status(emp),
                },
            }
        )
        occupied.append(
            {
                "id": u.user_id,
                "username": u.username,
                "email": u.email or "",
                "employee_code": emp.employee_code,
                "employee_name": emp.name,
            }
        )
    # ⚠️ ``success_response`` 不支持额外的顶层键 ⇒ 这里手工组装统一响应信封。
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": unlinked,
            "occupied_by_departed_employee": occupied,
            "timestamp": get_timestamp(),
        },
    )


@router.get("/deleted")
async def get_deleted_users(
    page: int = 1,
    page_size: int = 20,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """获取已删除用户列表(软删除)"""
    from sqlalchemy import func

    offset = (page - 1) * page_size

    count_result = await db.execute(
        select(func.count(DimUser.user_id)).where(DimUser.status == "deleted")
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.status == "deleted")
        .offset(offset)
        .limit(page_size)
        .order_by(DimUser.updated_at.desc())
    )
    users = result.scalars().all()

    user_responses = [
        UserResponse(
            id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=[role.role_name for role in user.roles],
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login,
        )
        for user in users
    ]

    return pagination_response(
        data=[user.dict() for user in user_responses],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{user_id:int}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """获取用户详情"""
    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="User not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确,或确认该用户已创建",
            status_code=404,
        )

    emp_id, emp_code, emp_name = await _get_employee_for_user(db, user.user_id)
    return UserResponse(
        id=user.user_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=[role.role_name for role in user.roles],
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login,
        employee_id=emp_id,
        employee_code=emp_code,
        employee_name=emp_name,
    )


@router.put("/{user_id:int}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """更新用户信息"""
    result = await db.execute(
        select(DimUser)
        .options(selectinload(DimUser.roles))
        .where(DimUser.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="User not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确,或确认该用户已创建",
            status_code=404,
        )

    if user_update.email is not None:
        result = await db.execute(
            select(DimUser).where(
                DimUser.email == user_update.email, DimUser.user_id != user_id
            )
        )
        existing_email = result.scalar_one_or_none()
        if existing_email:
            return error_response(
                code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
                message="Email already exists",
                error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
                recovery_suggestion="请使用不同的邮箱地址",
                status_code=400,
            )
        user.email = user_update.email

    if user_update.full_name is not None:
        user.full_name = user_update.full_name

    was_active = user.is_active
    if user_update.is_active is not None:
        user.is_active = user_update.is_active

        if user_update.is_active is False and was_active:
            user.status = "suspended"

            from backend.domains.platform.compat.notifications import (
                notify_user_suspended,
                revoke_all_user_sessions,
            )

            await revoke_all_user_sessions(
                db=db,
                user_id=user.user_id,
                reason="Account suspended by administrator, forced logout",
            )

            await notify_user_suspended(
                db=db,
                user_id=user.user_id,
                suspended_by=current_user.username,
                reason="Account suspended by administrator",
            )
        elif user_update.is_active is True and not was_active:
            if user.status != "deleted":
                user.status = "active"

    if user_update.roles is not None:
        user.roles.clear()
        for role_name in user_update.roles:
            result = await db.execute(
                select(DimRole).where(
                    or_(DimRole.role_name == role_name, DimRole.role_code == role_name)
                )
            )
            role = result.scalar_one_or_none()
            if role:
                user.roles.append(role)

    if user_update.employee_id is not None:
        # --- 账号 ↔ 员工绑定：与员工侧（PUT /api/hr/employees/{code}）同一套校验 ---
        # ⚠️ 绝不静默覆盖：员工已被别的账号绑定时报错点名占用者，
        #    否则旧账号侧毫无提示地「被抢走」员工。
        if user.status != "active" or not user.is_active:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="只能关联已审批且启用的账号",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请先审批该账号并启用,再关联员工",
                status_code=400,
            )
        result = await db.execute(
            select(Employee).where(Employee.id == user_update.employee_id)
        )
        emp = result.scalar_one_or_none()
        if not emp:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="Employee not found",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请选择有效的员工",
                status_code=404,
            )
        emp_status = employee_status(emp)
        if emp_status not in ("active", "probation"):
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="该员工已离职，不可关联账号",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion=f"员工编号 {emp.employee_code} 当前状态为 {emp_status},不可再关联新账号",
                status_code=400,
            )
        if emp.user_id is not None and int(emp.user_id) != int(user.user_id):
            occupant = await _describe_account_occupant(db, emp.user_id)
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message=f"该员工已关联账号 {occupant}，请先解除关联或从该账号侧解除",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请先在原账号侧解除关联,再把员工关联到本账号",
                status_code=400,
            )
        await _clear_employee_user_id(db, user.user_id)
        emp.user_id = user.user_id
    elif "employee_id" in user_update.model_fields_set:
        # 解除关联：**解绑总是允许的**（员工是否已离职都不拦截）。
        await _clear_employee_user_id(db, user.user_id)

    if user_update.is_active is False and was_active:
        await _clear_employee_user_id(db, user.user_id)

    await db.commit()
    await db.refresh(user, ["roles"])

    await audit_service.log_action(
        user_id=current_user.user_id,
        action="update_user",
        resource="user",
        resource_id=str(user.user_id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details=user_update.model_dump(exclude_unset=True),
    )

    emp_id, emp_code, emp_name = await _get_employee_for_user(db, user.user_id)
    return UserResponse(
        id=user.user_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=[role.role_name for role in user.roles],
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login,
        employee_id=emp_id,
        employee_code=emp_code,
        employee_name=emp_name,
    )


@router.delete("/{user_id:int}")
async def delete_user(
    user_id: int,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    reason: Optional[str] = None,
):
    """删除用户(软删除)"""
    try:
        result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查用户ID是否正确,或确认该用户已创建",
                status_code=404,
            )

        if user.status == "deleted":
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户已被删除",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="该用户已被删除,如需恢复请使用恢复接口",
                status_code=400,
            )

        if user.user_id == current_user.user_id:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="不能删除自己的账户",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="不能删除自己的账户",
                status_code=400,
            )

        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_active)
            .values(
                is_active=False,
                revoked_at=datetime.now(timezone.utc),
                revoked_reason="用户已删除",
            )
        )

        user.is_active = False
        user.status = "deleted"
        await _clear_employee_user_id(db, user_id)

        await audit_service.log_action(
            user_id=current_user.user_id,
            action="delete_user",
            resource="user",
            resource_id=str(user.user_id),
            ip_address="127.0.0.1",
            user_agent="Unknown",
            details={"username": user.username, "email": user.email, "reason": reason},
        )

        await db.commit()

        logger.info(
            f"用户已软删除: user_id={user_id}, username={user.username}, deleted_by={current_user.user_id}"
        )

        return success_response(
            data={"user_id": user_id}, message="用户已删除(软删除,数据已保留用于审计)"
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"删除用户失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除用户失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500,
        )


@router.post("/delete-batch", response_model=dict)
async def delete_users_batch(
    request_body: UserIdBatchRequest,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """批量删除用户(软删除, 最多200个)"""
    normalized_reason = (request_body.reason or "").strip() or None
    unique_user_ids = list(dict.fromkeys(request_body.user_ids))

    results: list[dict] = []

    for user_id in unique_user_ids:
        try:
            result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found")
            if user.status == "deleted":
                raise ValueError("User already deleted")
            if user.user_id == current_user.user_id:
                raise ValueError("Cannot delete current user")

            await db.execute(
                update(UserSession)
                .where(UserSession.user_id == user_id, UserSession.is_active)
                .values(
                    is_active=False,
                    revoked_at=datetime.now(timezone.utc),
                    revoked_reason="User deleted",
                )
            )

            user.is_active = False
            user.status = "deleted"
            await _clear_employee_user_id(db, user_id)

            await audit_service.log_action(
                user_id=current_user.user_id,
                action="delete_user",
                resource="user",
                resource_id=str(user.user_id),
                ip_address="127.0.0.1",
                user_agent="Unknown",
                details={
                    "username": user.username,
                    "email": user.email,
                    "reason": normalized_reason,
                    "batch": True,
                },
            )

            await db.commit()
            results.append({"user_id": user_id, "ok": True, "error_message": None})
        except Exception as exc:
            await db.rollback()
            results.append({"user_id": user_id, "ok": False, "error_message": str(exc)})

    success_count = sum(1 for item in results if item["ok"])
    failed_count = len(results) - success_count
    payload = {
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
        },
        "results": results,
    }
    return success_response(data=payload, message="Batch deletion completed")


@router.post("/{user_id:int}/restore")
async def restore_user(
    user_id: int,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """恢复已删除的用户(软删除恢复)"""
    try:
        result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查用户ID是否正确",
                status_code=404,
            )

        if user.status != "deleted":
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="用户未被删除",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="该用户未被删除,无需恢复",
                status_code=400,
            )

        user.status = "active"
        user.is_active = True

        await audit_service.log_action(
            user_id=current_user.user_id,
            action="restore_user",
            resource="user",
            resource_id=str(user.user_id),
            ip_address="127.0.0.1",
            user_agent="Unknown",
            details={"username": user.username, "email": user.email},
        )

        await db.commit()

        logger.info(
            f"用户已恢复: user_id={user_id}, username={user.username}, restored_by={current_user.user_id}"
        )

        return success_response(data={"user_id": user_id}, message="用户已恢复")

    except Exception as e:
        await db.rollback()
        logger.error(f"恢复用户失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="恢复用户失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限,或联系系统管理员",
            status_code=500,
        )


@router.post("/{user_id:int}/reset-password", response_model=ResetPasswordResponse)
async def reset_user_password(
    user_id: int,
    request_body: ResetPasswordRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """重置用户密码(管理员)"""
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404,
        )

    import secrets
    import string

    from backend.services.auth_service import auth_service

    if request_body.generate_temp_password or not request_body.new_password:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        temp_password = "".join(secrets.choice(alphabet) for i in range(12))
        new_password = temp_password
    else:
        temp_password = None
        new_password = request_body.new_password
        if len(new_password) < 8:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="密码长度至少8位",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请使用至少8位的密码",
                status_code=400,
            )

    user.password_hash = auth_service.hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None

    from backend.domains.platform.compat.notifications import (
        notify_password_reset,
        revoke_all_user_sessions,
    )

    revoked_count = await revoke_all_user_sessions(
        db=db,
        user_id=user.user_id,
        reason="Password reset by administrator, forced logout",
    )

    await db.commit()

    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")

    await audit_service.log_action(
        user_id=current_user.user_id,
        action="reset_password",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "username": user.username,
            "generated_temp": request_body.generate_temp_password
            or not request_body.new_password,
            "sessions_revoked": revoked_count,
        },
    )

    await notify_password_reset(
        db=db, user_id=user.user_id, reset_by=current_user.username
    )
    await db.commit()

    response_data = ResetPasswordResponse(
        user_id=user.user_id,
        username=user.username,
        temp_password=temp_password,
        message="密码重置成功" + (",临时密码已生成" if temp_password else ""),
    )

    return success_response(data=response_data.dict(), message="密码重置成功")


@router.post("/{user_id:int}/unlock")
async def unlock_user_account(
    user_id: int,
    request_body: UnlockAccountRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """解锁用户账户(管理员)"""
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404,
        )

    from datetime import datetime

    if not user.locked_until or user.locked_until <= datetime.now(timezone.utc):
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="账户未被锁定",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="该账户当前未被锁定,无需解锁",
            status_code=400,
        )

    user.locked_until = None
    user.failed_login_attempts = 0
    await db.commit()

    ip_address = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "Unknown")

    await audit_service.log_action(
        user_id=current_user.user_id,
        action="unlock_account",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "username": user.username,
            "reason": request_body.reason or "Administrator manual unlock",
        },
    )

    from backend.domains.platform.compat.notifications import notify_account_unlocked

    await notify_account_unlocked(
        db=db, user_id=user.user_id, unlocked_by=current_user.username
    )
    await db.commit()

    return success_response(
        data={"user_id": user.user_id, "username": user.username},
        message="账户解锁成功",
    )


@router.post("/{user_id:int}/approve")
@role_based_rate_limit(endpoint_type="default")
async def approve_user(
    user_id: int,
    request_body: ApproveUserRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """审批用户(将pending状态改为active)

    ``request_body.create_employee=True`` 时**审批即建档**：同一事务内完成
    激活账号 → 建立员工档案 → 绑定账号；该账号已有关联档案时**幂等跳过建档**。
    """
    result = await db.execute(
        select(DimUser)
        .where(DimUser.user_id == user_id)
        .options(selectinload(DimUser.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404,
        )

    if user.status != "pending":
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message=f"只能审批pending状态的用户,当前状态:{user.status}",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="只能审批待审批状态的用户",
            status_code=400,
        )

    from datetime import datetime

    user.status = "active"
    user.is_active = True
    user.approved_at = datetime.now(timezone.utc)
    user.approved_by = current_user.user_id

    if request_body.role_ids:
        result = await db.execute(
            select(DimRole).where(DimRole.role_id.in_(request_body.role_ids))
        )
        roles = result.scalars().all()
        found_role_ids = {role.role_id for role in roles}
        requested_role_ids = set(request_body.role_ids)

        if found_role_ids != requested_role_ids:
            missing_role_ids = requested_role_ids - found_role_ids
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message=f"以下角色ID不存在: {sorted(missing_role_ids)}",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查角色ID是否正确",
                status_code=400,
            )

        user.roles.clear()
        user.roles.extend(roles)
    else:
        result = await db.execute(
            select(DimRole).where(DimRole.role_code == "operator")
        )
        operator_role = result.scalar_one_or_none()
        if not operator_role:
            return error_response(
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="默认operator角色不存在",
                error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                recovery_suggestion="请联系系统管理员创建operator角色",
                status_code=500,
            )
        user.roles.clear()
        user.roles.append(operator_role)

    await db.flush()
    await db.refresh(user, ["roles"])

    # --- 审批即建档（create_employee=True）：同一事务内激活账号 + 建档 + 绑定 ---
    employee_created = False
    employee_code: Optional[str] = None
    if request_body.create_employee:
        # ⚠️ 复用人力侧的工号生成规则（EMP + 年月 + 4 位序号），不另写一份。
        #    放在函数内导入：避免 platform 域 → business 域的模块级导入环。
        from backend.domains.business.routers.hr_employee import (
            _generate_employee_code,
        )

        emp_result = await db.execute(
            select(Employee).where(Employee.user_id == user.user_id)
        )
        existing_employee = emp_result.scalar_one_or_none()
        if existing_employee is not None:
            # 幂等：该账号已有关联档案 ⇒ 复用它，不重复建档、不报错。
            employee_code = existing_employee.employee_code
        else:
            employee_code = await _generate_employee_code(db)
            employee = Employee(
                employee_code=employee_code,
                name=user.full_name or user.username,
                employee_identity_type="employee",
                status=request_body.employee_status or "probation",
                department_id=request_body.employee_department_id,
                position_id=request_body.employee_position_id,
                hire_date=request_body.employee_hire_date,
                user_id=user.user_id,
            )
            db.add(employee)
            employee_created = True

    approval_log = UserApprovalLog(
        user_id=user.user_id,
        action="approve",
        approved_by=current_user.user_id,
        reason=request_body.notes,
    )
    db.add(approval_log)

    ip_address = "127.0.0.1"
    user_agent = "Unknown"
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="user_approved",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "approved_user_id": user.user_id,
            "approved_username": user.username,
            "role_ids": (
                request_body.role_ids if request_body.role_ids else ["operator"]
            ),
            "notes": request_body.notes,
            "employee_created": employee_created,
            "employee_code": employee_code,
        },
    )

    try:
        from backend.services.approval_center_service import (
            sync_user_registration_approval_decision,
        )

        await sync_user_registration_approval_decision(
            db=db,
            user_id=user.user_id,
            actor_user_id=current_user.user_id,
            action="approve",
            comment=request_body.notes,
        )
    except Exception as exc:
        logger.warning(
            f"[approval-center] failed to sync user approval decision: {exc}"
        )

    from backend.domains.platform.compat.notifications import notify_user_approved

    await notify_user_approved(
        db=db, user_id=user.user_id, approved_by=current_user.username
    )

    await db.commit()
    await db.refresh(user)

    return success_response(
        data={
            "user_id": user.user_id,
            "username": user.username,
            "status": user.status,
            "employee_created": employee_created,
            "employee_code": employee_code,
        },
        message="用户审批成功",
    )


@router.post("/{user_id:int}/reject")
@role_based_rate_limit(endpoint_type="default")
async def reject_user(
    user_id: int,
    request_body: RejectUserRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """拒绝用户(将pending状态改为rejected)"""
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="用户不存在",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查用户ID是否正确",
            status_code=404,
        )

    if user.status != "pending":
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message=f"只能拒绝pending状态的用户,当前状态:{user.status}",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="只能拒绝待审批状态的用户",
            status_code=400,
        )

    normalized_reason = (request_body.reason or "").strip() or None

    user.status = "rejected"
    user.is_active = False
    user.rejection_reason = normalized_reason
    user.approved_by = current_user.user_id
    await _clear_employee_user_id(db, user_id)

    await db.flush()

    approval_log = UserApprovalLog(
        user_id=user.user_id,
        action="reject",
        approved_by=current_user.user_id,
        reason=normalized_reason,
    )
    db.add(approval_log)

    ip_address = "127.0.0.1"
    user_agent = "Unknown"
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="user_rejected",
        resource="user",
        resource_id=str(user.user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details={
            "rejected_user_id": user.user_id,
            "rejected_username": user.username,
            "reason": normalized_reason,
        },
    )

    try:
        from backend.services.approval_center_service import (
            sync_user_registration_approval_decision,
        )

        await sync_user_registration_approval_decision(
            db=db,
            user_id=user.user_id,
            actor_user_id=current_user.user_id,
            action="reject",
            comment=normalized_reason,
        )
    except Exception as exc:
        logger.warning(
            f"[approval-center] failed to sync user rejection decision: {exc}"
        )

    from backend.domains.platform.compat.notifications import notify_user_rejected

    await notify_user_rejected(
        db=db,
        user_id=user.user_id,
        rejected_by=current_user.username,
        reason=normalized_reason,
    )

    await db.commit()

    return success_response(
        data={
            "user_id": user.user_id,
            "username": user.username,
            "status": user.status,
        },
        message="用户已拒绝",
    )


@router.post("/reject-batch", response_model=dict)
@role_based_rate_limit(endpoint_type="default")
async def reject_users_batch(
    request_body: UserIdBatchRequest,
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """批量拒绝用户(仅 pending, 最多200个)"""
    normalized_reason = (request_body.reason or "").strip() or None
    unique_user_ids = list(dict.fromkeys(request_body.user_ids))

    results: list[dict] = []

    for user_id in unique_user_ids:
        try:
            result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found")
            if user.status != "pending":
                raise ValueError(
                    f"Only pending users can be rejected (current={user.status})"
                )

            user.status = "rejected"
            user.is_active = False
            user.rejection_reason = normalized_reason
            user.approved_by = current_user.user_id
            await _clear_employee_user_id(db, user_id)

            await db.flush()

            approval_log = UserApprovalLog(
                user_id=user.user_id,
                action="reject",
                approved_by=current_user.user_id,
                reason=normalized_reason,
            )
            db.add(approval_log)

            await audit_service.log_action(
                user_id=current_user.user_id,
                action="user_rejected",
                resource="user",
                resource_id=str(user.user_id),
                ip_address="127.0.0.1",
                user_agent="Unknown",
                details={
                    "rejected_user_id": user.user_id,
                    "rejected_username": user.username,
                    "reason": normalized_reason,
                    "batch": True,
                },
            )

            try:
                from backend.services.approval_center_service import (
                    sync_user_registration_approval_decision,
                )

                await sync_user_registration_approval_decision(
                    db=db,
                    user_id=user.user_id,
                    actor_user_id=current_user.user_id,
                    action="reject",
                    comment=normalized_reason,
                )
            except Exception as exc:
                logger.warning(
                    f"[approval-center] failed to sync user rejection decision: {exc}"
                )

            from backend.domains.platform.compat.notifications import (
                notify_user_rejected,
            )

            await notify_user_rejected(
                db=db,
                user_id=user.user_id,
                rejected_by=current_user.username,
                reason=normalized_reason,
            )

            await db.commit()
            results.append({"user_id": user_id, "ok": True, "error_message": None})
        except Exception as exc:
            await db.rollback()
            results.append({"user_id": user_id, "ok": False, "error_message": str(exc)})

    success_count = sum(1 for item in results if item["ok"])
    failed_count = len(results) - success_count
    payload = {
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
        },
        "results": results,
    }
    return success_response(data=payload, message="Batch rejection completed")


@router.get("/pending", response_model=List[PendingUserResponse])
@role_based_rate_limit(endpoint_type="default")
async def get_pending_users(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """获取待审批用户列表"""

    offset = (page - 1) * page_size
    result = await db.execute(
        select(DimUser)
        .where(DimUser.status == "pending")
        .order_by(DimUser.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()

    return [
        PendingUserResponse(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            department=user.department,
            status=user.status,
            created_at=user.created_at,
        )
        for user in users
    ]


@router.get("/pending-count")
@role_based_rate_limit(endpoint_type="default")
async def get_pending_users_count(
    request: Request,
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """获取待审批用户总数。"""
    from sqlalchemy import func

    result = await db.execute(
        select(func.count(DimUser.user_id)).where(DimUser.status == "pending")
    )
    pending_count = result.scalar() or 0
    return success_response(data={"pending_count": pending_count})

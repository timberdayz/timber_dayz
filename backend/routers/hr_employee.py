"""
HR - 员工档案与我的信息
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone
from decimal import Decimal

from backend.models.database import get_async_db
from backend.dependencies.auth import get_current_user
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.logger import get_logger

logger = get_logger(__name__)
from backend.schemas import MyIncomeResponse, IncomeCalculationResponse
from backend.schemas.hr import (
    EmployeeCreate, EmployeeResponse, EmployeeUpdate, MeProfileUpdate,
)
from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.base_service import provide_service
from backend.utils.year_month_utils import year_month_to_first_day
from modules.core.db import (
    Employee, DimUser, SalaryStructure, PayrollRecord,
    EmployeeCommission, EmployeePerformance,
)

router = APIRouter(prefix="/api/hr", tags=["HR-员工档案"])

# ============================================================================
# 员工管理API
# ============================================================================

async def _username_for_user_id(db: AsyncSession, user_id: Optional[int]) -> Optional[str]:
    """根据 dim_users.user_id 查询 username，用于 EmployeeResponse.username"""
    if not user_id:
        return None
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    return user.username if user else None


@router.get("/me/profile", response_model=EmployeeResponse)
async def get_me_profile(
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """我的档案：当前登录用户关联的员工档案；未关联时首次访问自动创建最小员工并关联（系统主要面向内部员工，注册并登录即可用）。路由须在 /employees/{employee_code} 之前。"""
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.user_id))
    employee = result.scalar_one_or_none()
    if not employee:
        # 首次访问自动创建最小员工并关联
        employee_code = await _generate_employee_code(db)
        name = (current_user.full_name or current_user.username or "员工").strip()
        if len(name) > 128:
            name = name[:128]
        employee = Employee(
            employee_code=employee_code,
            name=name,
            user_id=current_user.user_id,
            status="active",
            email=current_user.email,
        )
        db.add(employee)
        await db.commit()
        await db.refresh(employee)
        logger.info(f"我的档案自动创建员工: {employee_code} (user_id={current_user.user_id})")
    username = await _username_for_user_id(db, employee.user_id)
    resp = EmployeeResponse.model_validate(employee)
    return resp.model_copy(update={"username": username})


@router.put("/me/profile", response_model=EmployeeResponse)
async def put_me_profile(
    body: MeProfileUpdate,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """我的档案：仅接受白名单字段 phone/email/address/emergency_contact/emergency_phone。"""
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.user_id))
    employee = result.scalar_one_or_none()
    if not employee:
        return error_response(ErrorCode.DATA_NOT_FOUND, "您尚未关联员工档案，请联系管理员", status_code=404)
    update_data = body.model_dump(exclude_unset=True)
    for key in ("phone", "email", "address", "emergency_contact", "emergency_phone"):
        if key in update_data:
            setattr(employee, key, update_data[key])
    employee.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(employee)
    username = await _username_for_user_id(db, employee.user_id)
    resp = EmployeeResponse.model_validate(employee)
    return resp.model_copy(update={"username": username})


async def _log_me_income_access(
    request: Request, user_id: int, period: Optional[str], result_status: str, db: AsyncSession
) -> None:
    """记录「我的收入」访问审计（仅 endpoint/user_id/request_time/result_status，不记录敏感字段）。"""
    try:
        from backend.services.audit_service import audit_service
        client_host = request.client.host if request.client else ""
        user_agent = (request.headers.get("user-agent") or "")[:500]
        await audit_service.log_action(
            user_id=user_id,
            action="view",
            resource="me/income",
            ip_address=client_host,
            user_agent=user_agent,
            resource_id=period,
            details={"result_status": result_status},
            db=db
        )
    except Exception as e:
        logger.warning("me/income audit log write failed: %s", e)


@router.get("/me/income", response_model=MyIncomeResponse)
async def get_my_income(
    request: Request,
    year_month: Optional[str] = Query(None, description="月份(YYYY-MM)，不填则当月"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """我的收入：根据当前用户关联的员工返回收入数据；未关联时返回 200 + linked: false。仅允许本人访问，记录访问审计（不记录敏感薪资字段）。"""
    current_user_id = current_user.user_id
    result = await db.execute(select(Employee).where(Employee.user_id == current_user_id))
    employee = result.scalar_one_or_none()
    if not employee:
        await _log_me_income_access(request, current_user_id, year_month, "linked_false", db)
        return MyIncomeResponse(linked=False)
    period = year_month or datetime.now(timezone.utc).strftime("%Y-%m")
    employee_code = employee.employee_code
    base_salary = None
    commission_amount = 0.0
    performance_score = None
    achievement_rate = None
    breakdown = {}
    # 查询 payroll_records
    pr_result = await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.employee_code == employee_code,
            PayrollRecord.year_month == period
        )
    )
    pr = pr_result.scalar_one_or_none()
    if pr:
        base_salary = float(pr.base_salary) if pr.base_salary else None
        commission_amount = float(pr.commission or 0)
        breakdown["payroll"] = {"base_salary": base_salary, "commission": commission_amount, "net_salary": float(pr.net_salary or 0)}
    # 若无工资单，组合 salary_structures + employee_commissions + employee_performance
    if base_salary is None:
        ss_result = await db.execute(
            select(SalaryStructure).where(
                SalaryStructure.employee_code == employee_code,
                SalaryStructure.status == "active"
            ).order_by(SalaryStructure.effective_date.desc()).limit(1)
        )
        ss = ss_result.scalar_one_or_none()
        if ss:
            base_salary = float(ss.base_salary or 0) + float(ss.position_salary or 0)
            breakdown["salary_structure"] = {"base_salary": base_salary}
    try:
        ec_result = await db.execute(
            select(EmployeeCommission).where(
                EmployeeCommission.employee_code == employee_code,
                EmployeeCommission.year_month == period
            )
        )
        ec = ec_result.scalar_one_or_none()
        if ec:
            commission_amount = float(ec.commission_amount or 0)
            breakdown["commission"] = {"amount": commission_amount}
    except Exception:
        # 兼容历史中文列名表结构（当前环境仍存在），确保 /me/income 可用。
        await db.rollback()
        logger.warning("employee_commissions ORM query failed, fallback to CN column SQL")
        ec_raw = await db.execute(
            text(
                """
                select
                  "提成金额" as commission_amount
                from c_class.employee_commissions
                where "员工编号" = :employee_code
                  and "年月" = :year_month
                limit 1
                """
            ),
            {"employee_code": employee_code, "year_month": period},
        )
        ec_row = ec_raw.mappings().first()
        if ec_row:
            commission_amount = float(ec_row.get("commission_amount") or 0)
            breakdown["commission"] = {"amount": commission_amount}

    try:
        ep_result = await db.execute(
            select(EmployeePerformance).where(
                EmployeePerformance.employee_code == employee_code,
                EmployeePerformance.year_month == period
            )
        )
        ep = ep_result.scalar_one_or_none()
        if ep:
            performance_score = float(ep.performance_score or 0)
            achievement_rate = float(ep.achievement_rate or 0)
            breakdown["performance"] = {"score": performance_score, "achievement_rate": achievement_rate}
    except Exception:
        # 兼容历史中文列名表结构（当前环境仍存在），确保 /me/income 可用。
        await db.rollback()
        logger.warning("employee_performance ORM query failed, fallback to CN column SQL")
        ep_raw = await db.execute(
            text(
                """
                select
                  "绩效得分" as performance_score,
                  "达成率" as achievement_rate
                from c_class.employee_performance
                where "员工编号" = :employee_code
                  and "年月" = :year_month
                limit 1
                """
            ),
            {"employee_code": employee_code, "year_month": period},
        )
        ep_row = ep_raw.mappings().first()
        if ep_row:
            performance_score = float(ep_row.get("performance_score") or 0)
            achievement_rate = float(ep_row.get("achievement_rate") or 0)
            breakdown["performance"] = {
                "score": performance_score,
                "achievement_rate": achievement_rate,
            }
    total = (base_salary or 0) + commission_amount
    await _log_me_income_access(request, current_user_id, period, "success", db)
    return MyIncomeResponse(
        linked=True,
        period=period,
        base_salary=base_salary if base_salary is not None else 0.0,
        commission_amount=commission_amount,
        performance_score=performance_score if performance_score is not None else 0.0,
        achievement_rate=achievement_rate if achievement_rate is not None else 0.0,
        total_income=total,
        breakdown=breakdown if breakdown else {}
    )


hr_income_service_dep = provide_service(HRIncomeCalculationService)


@router.post("/income/calculate", response_model=IncomeCalculationResponse)
async def calculate_income_c_class(
    year_month: str = Query(..., description="月份(YYYY-MM)"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    service: HRIncomeCalculationService = Depends(hr_income_service_dep),
):
    """重算员工收入 C 类表（employee_commissions / employee_performance）。"""
    try:
        result = await service.calculate_month(year_month)
        return IncomeCalculationResponse(**result)
    except ValueError as e:
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            f"参数错误: {str(e)}",
            status_code=400,
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"重算员工收入C类数据失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"重算员工收入C类数据失败: {str(e)}",
            status_code=500,
        )


@router.get("/employees", response_model=List[EmployeeResponse])
async def list_employees(
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    position_id: Optional[int] = Query(None, description="职位ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选(active/inactive/probation/leave)"),
    keyword: Optional[str] = Query(None, description="关键字搜索(姓名/工号)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=500, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工列表(分页、筛选)"""
    try:
        query = select(Employee)
        conditions = []
        
        if department_id is not None:
            conditions.append(Employee.department_id == department_id)
        if position_id is not None:
            conditions.append(Employee.position_id == position_id)
        if status:
            conditions.append(Employee.status == status)
        if keyword:
            conditions.append(
                or_(
                    Employee.name.ilike(f"%{keyword}%"),
                    Employee.employee_code.ilike(f"%{keyword}%")
                )
            )
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(Employee.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        employees = result.scalars().all()
        out = []
        for emp in employees:
            resp = EmployeeResponse.model_validate(emp)
            resp = resp.model_copy(update={"username": await _username_for_user_id(db, emp.user_id)})
            out.append(resp)
        return out
    except Exception as e:
        logger.error(f"获取员工列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工列表失败: {str(e)}", status_code=500)


@router.get("/employees/count")
async def count_employees(
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工总数（用于人效计算等）"""
    try:
        query = select(func.count(Employee.id))
        
        if status:
            query = query.where(Employee.status == status)
        
        result = await db.execute(query)
        count = result.scalar()
        
        return {"count": count, "status": status or "all"}
    except Exception as e:
        logger.error(f"获取员工总数失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工总数失败: {str(e)}", status_code=500)


@router.get("/employees/{employee_code}", response_model=EmployeeResponse)
async def get_employee(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工详情"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {employee_code}", status_code=404)
        username = await _username_for_user_id(db, employee.user_id)
        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(update={"username": username})
    except Exception as e:
        logger.error(f"获取员工详情失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工详情失败: {str(e)}", status_code=500)


async def _generate_employee_code(db: AsyncSession) -> str:
    """生成员工编号：EMP + 年份后2位 + 4位流水号，如 EMP260001"""
    year_suffix = datetime.now().strftime("%y")
    prefix = f"EMP{year_suffix}"
    result = await db.execute(
        select(Employee.employee_code).where(Employee.employee_code.like(f"{prefix}%"))
    )
    rows = result.scalars().all()
    max_seq = 0
    for code in rows:
        try:
            seq = int(code[len(prefix):]) if len(code) > len(prefix) else 0
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:04d}"


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建员工；员工编号不传或为空时自动生成"""
    try:
        data = employee.model_dump()
        employee_code = data.get("employee_code") or None
        if not employee_code or not str(employee_code).strip():
            employee_code = await _generate_employee_code(db)
            data["employee_code"] = employee_code

        existing = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        if existing.scalar_one_or_none():
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"员工编号已存在: {employee_code}", status_code=400)
        user_id = data.get("user_id")
        if user_id is not None:
            other = await db.execute(select(Employee).where(Employee.user_id == user_id))
            if other.scalar_one_or_none():
                return error_response(ErrorCode.DATA_ALREADY_EXISTS, "该登录账号已关联其他员工", status_code=400)
        new_employee = Employee(**data)
        db.add(new_employee)
        await db.commit()
        await db.refresh(new_employee)
        logger.info(f"创建员工成功: {new_employee.employee_code} - {new_employee.name}")
        username = await _username_for_user_id(db, new_employee.user_id)
        resp = EmployeeResponse.model_validate(new_employee)
        return resp.model_copy(update={"username": username})
    except Exception as e:
        await db.rollback()
        logger.error(f"创建员工失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建员工失败: {str(e)}", status_code=500)


@router.put("/employees/{employee_code}", response_model=EmployeeResponse)
async def update_employee(
    employee_code: str,
    employee_update: EmployeeUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新员工信息"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {employee_code}", status_code=404)
        update_data = employee_update.model_dump(exclude_unset=True)
        if "user_id" in update_data and update_data["user_id"] is not None:
            other = await db.execute(
                select(Employee).where(
                    Employee.user_id == update_data["user_id"],
                    Employee.id != employee.id
                )
            )
            if other.scalar_one_or_none():
                return error_response(ErrorCode.DATA_ALREADY_EXISTS, "该登录账号已关联其他员工", status_code=400)
        for key, value in update_data.items():
            setattr(employee, key, value)
        employee.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(employee)
        logger.info(f"更新员工成功: {employee_code}")
        username = await _username_for_user_id(db, employee.user_id)
        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(update={"username": username})
    except Exception as e:
        await db.rollback()
        logger.error(f"更新员工失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新员工失败: {str(e)}", status_code=500)


@router.delete("/employees/{employee_code}", status_code=204)
async def delete_employee(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """删除员工(软删除:设置status为inactive)"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {employee_code}", status_code=404)
        assign_result = await db.execute(
            select(EmployeeShopAssignment).where(
                EmployeeShopAssignment.employee_code == employee_code
            )
        )
        if assign_result.scalars().first():
            return error_response(ErrorCode.DATA_INTEGRITY_VIOLATION, "请先解除该员工的店铺归属", status_code=400)
        employee.status = "inactive"
        employee.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"删除员工成功(软删除): {employee_code}")
        return None
    except Exception as e:
        await db.rollback()
        logger.error(f"删除员工失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"删除员工失败: {str(e)}", status_code=500)


# ============================================================================
# 排班班次API

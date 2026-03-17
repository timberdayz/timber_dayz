"""
HR - 绩效提成与店铺分配
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
from backend.schemas.hr import (
    EmployeePerformanceResponse,
    EmployeeCommissionResponse,
    ShopCommissionResponse,
    EmployeeShopAssignmentCreate, EmployeeShopAssignmentResponse, EmployeeShopAssignmentUpdate,
    ShopCommissionConfigUpdate,
    CopyFromPrevMonthBody,
)
from modules.core.db import (
    PlatformAccount, Employee, DimShop, DimUser,
    EmployeePerformance, EmployeeCommission, ShopCommission,
    EmployeeShopAssignment, ShopCommissionConfig, EmployeeTarget,
)

router = APIRouter(prefix="/api/hr", tags=["HR-绩效提成"])


@router.get("/performance", response_model=List[EmployeePerformanceResponse])
async def list_employee_performance(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工绩效列表(从employee_performance表读取,由Metabase定时计算)"""
    try:
        query = select(EmployeePerformance)
        conditions = []
        
        if employee_code:
            conditions.append(EmployeePerformance.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeePerformance.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(EmployeePerformance.year_month.desc(), EmployeePerformance.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        performances = result.scalars().all()
        
        return [EmployeePerformanceResponse.model_validate(perf) for perf in performances]
    except Exception as e:
        logger.error(f"获取员工绩效列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工绩效列表失败: {str(e)}", status_code=500)


# ============================================================================
# 提成查询API（只读）
# ============================================================================

@router.get("/commissions/employee", response_model=List[EmployeeCommissionResponse])
async def list_employee_commissions(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工提成列表(从employee_commissions表读取,由Metabase定时计算)"""
    try:
        query = select(EmployeeCommission)
        conditions = []
        
        if employee_code:
            conditions.append(EmployeeCommission.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeeCommission.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(EmployeeCommission.year_month.desc(), EmployeeCommission.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        commissions = result.scalars().all()
        
        return [EmployeeCommissionResponse.model_validate(comm) for comm in commissions]
    except Exception as e:
        logger.error(f"获取员工提成列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工提成列表失败: {str(e)}", status_code=500)


@router.get("/commissions/shop", response_model=List[ShopCommissionResponse])
async def list_shop_commissions(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取店铺提成列表(从shop_commissions表读取,由Metabase定时计算)"""
    try:
        query = select(ShopCommission)
        conditions = []
        
        if shop_id:
            conditions.append(ShopCommission.shop_id == shop_id)
        if year_month:
            conditions.append(ShopCommission.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(ShopCommission.year_month.desc(), ShopCommission.shop_id).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        commissions = result.scalars().all()
        
        return [ShopCommissionResponse.model_validate(comm) for comm in commissions]
    except Exception as e:
        logger.error(f"获取店铺提成列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取店铺提成列表失败: {str(e)}", status_code=500)


@router.get("/employee-shop-assignments")
async def list_employee_shop_assignments(
    year_month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="适用月份 YYYY-MM"),
    employee_code: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    platform_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_async_db),
):
    """获取归属列表（分页、筛选），按 year_month 过滤，LEFT JOIN 补全姓名和店铺名"""
    try:
        base_query = select(EmployeeShopAssignment)
        conditions = []
        if year_month:
            conditions.append(EmployeeShopAssignment.year_month == year_month)
        if employee_code:
            conditions.append(EmployeeShopAssignment.employee_code == employee_code)
        if shop_id:
            conditions.append(EmployeeShopAssignment.shop_id == shop_id)
        if platform_code:
            conditions.append(EmployeeShopAssignment.platform_code == platform_code)
        if status:
            conditions.append(EmployeeShopAssignment.status == status)
        if conditions:
            base_query = base_query.where(and_(*conditions))

        count_query = select(func.count(EmployeeShopAssignment.id)).select_from(
            base_query.subquery()
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = base_query.order_by(
            EmployeeShopAssignment.employee_code,
            EmployeeShopAssignment.platform_code,
            EmployeeShopAssignment.shop_id,
        ).offset(offset).limit(page_size)
        result = await db.execute(query)
        rows = result.scalars().all()

        items = []
        for r in rows:
            emp_name = None
            shop_name = None
            emp_res = await db.execute(select(Employee.name).where(Employee.employee_code == r.employee_code))
            if emp_row := emp_res.scalar_one_or_none():
                emp_name = emp_row
            shop_res = await db.execute(
                select(DimShop.shop_name).where(
                    DimShop.platform_code == r.platform_code,
                    DimShop.shop_id == r.shop_id,
                )
            )
            if shop_row := shop_res.scalar_one_or_none():
                shop_name = shop_row
            items.append(EmployeeShopAssignmentResponse(
                id=r.id,
                year_month=r.year_month,
                employee_code=r.employee_code,
                employee_name=emp_name,
                platform_code=r.platform_code,
                shop_id=r.shop_id,
                shop_name=shop_name,
                commission_ratio=r.commission_ratio,
                role=r.role,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
                status=r.status,
                created_at=r.created_at,
                updated_at=r.updated_at,
            ))
        return {"success": True, "data": {"items": items, "total": total}}
    except Exception as e:
        logger.error(f"获取归属列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取归属列表失败: {str(e)}", status_code=500)


@router.post("/employee-shop-assignments", status_code=201)
async def create_employee_shop_assignment(
    body: EmployeeShopAssignmentCreate,
    db: AsyncSession = Depends(get_async_db),
):
    """新增归属"""
    try:
        emp_res = await db.execute(select(Employee).where(Employee.employee_code == body.employee_code))
        if not emp_res.scalar_one_or_none():
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {body.employee_code}", status_code=400)
        shop_res = await db.execute(
            select(DimShop).where(
                DimShop.platform_code == body.platform_code,
                DimShop.shop_id == body.shop_id,
            )
        )
        if not shop_res.scalar_one_or_none():
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "该店铺尚未同步至系统，请先在账号管理中同步",
                status_code=400,
            )

        dup = await db.execute(
            select(EmployeeShopAssignment).where(
                EmployeeShopAssignment.employee_code == body.employee_code,
                EmployeeShopAssignment.platform_code == body.platform_code,
                EmployeeShopAssignment.shop_id == body.shop_id,
                EmployeeShopAssignment.year_month == body.year_month,
            )
        )
        if dup.scalar_one_or_none():
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, "该员工在该月已关联该店铺", status_code=409)

        rec = EmployeeShopAssignment(
            year_month=body.year_month,
            employee_code=body.employee_code,
            platform_code=body.platform_code.lower(),
            shop_id=body.shop_id,
            commission_ratio=body.commission_ratio,
            role=body.role,
            effective_from=body.effective_from,
            effective_to=body.effective_to,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        emp = (await db.execute(select(Employee.name).where(Employee.employee_code == rec.employee_code))).scalar_one_or_none()
        shop = (await db.execute(select(DimShop.shop_name).where(DimShop.platform_code == rec.platform_code, DimShop.shop_id == rec.shop_id))).scalar_one_or_none()
        resp = EmployeeShopAssignmentResponse.model_validate(rec)
        resp.employee_name = emp
        resp.shop_name = shop
        return {"success": True, "data": resp}
    except Exception as e:
        await db.rollback()
        logger.error(f"新增归属失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"新增归属失败: {str(e)}", status_code=500)


@router.put("/employee-shop-assignments/{id}")
async def update_employee_shop_assignment(
    id: int,
    body: EmployeeShopAssignmentUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    """更新归属"""
    try:
        result = await db.execute(select(EmployeeShopAssignment).where(EmployeeShopAssignment.id == id))
        rec = result.scalar_one_or_none()
        if not rec:
            return error_response(ErrorCode.DATA_NOT_FOUND, "归属记录不存在", status_code=404)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(rec, k, v)
        await db.commit()
        await db.refresh(rec)
        emp = (await db.execute(select(Employee.name).where(Employee.employee_code == rec.employee_code))).scalar_one_or_none()
        shop = (await db.execute(select(DimShop.shop_name).where(DimShop.platform_code == rec.platform_code, DimShop.shop_id == rec.shop_id))).scalar_one_or_none()
        resp = EmployeeShopAssignmentResponse.model_validate(rec)
        resp.employee_name = emp
        resp.shop_name = shop
        return {"success": True, "data": resp}
    except Exception as e:
        await db.rollback()
        logger.error(f"更新归属失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新归属失败: {str(e)}", status_code=500)


@router.delete("/employee-shop-assignments/{id}", status_code=204)
async def delete_employee_shop_assignment(
    id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """删除归属"""
    try:
        result = await db.execute(select(EmployeeShopAssignment).where(EmployeeShopAssignment.id == id))
        rec = result.scalar_one_or_none()
        if not rec:
            return error_response(ErrorCode.DATA_NOT_FOUND, "归属记录不存在", status_code=404)
        await db.delete(rec)
        await db.commit()
        return None
    except Exception as e:
        await db.rollback()
        logger.error(f"删除归属失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"删除归属失败: {str(e)}", status_code=500)


@router.get("/shop-commission-config")
async def get_shop_commission_config(
    year_month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="月份 YYYY-MM"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """获取店铺可分配利润率配置（按月份+店铺维度，用于配置页加载）"""
    try:
        shop_query = (
            select(PlatformAccount)
            .where(PlatformAccount.enabled == True)
            .order_by(PlatformAccount.platform, PlatformAccount.store_name)
        )
        shop_rows = (await db.execute(shop_query)).scalars().all()
        config_query = (
            select(ShopCommissionConfig)
            .where(ShopCommissionConfig.year_month == year_month)
        )
        config_rows = (await db.execute(config_query)).scalars().all()
        config_by_key = {
            f"{(c.platform_code or '').lower()}|{c.shop_id}": float(c.allocatable_profit_rate or 0)
            for c in config_rows
        }
        items = []
        for r in shop_rows:
            pc = (r.platform or "").lower()
            sid = r.shop_id or r.account_id or str(r.id)
            key = f"{pc}|{sid}"
            items.append({
                "platform_code": pc,
                "shop_id": sid,
                "allocatable_profit_rate": config_by_key.get(key, 0),
            })
        return {"success": True, "data": items}
    except Exception as e:
        logger.error(f"获取店铺可分配利润率配置失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取配置失败: {str(e)}", status_code=500)


@router.put("/shop-commission-config/{platform_code}/{shop_id}")
async def put_shop_commission_config(
    platform_code: str,
    shop_id: str,
    body: ShopCommissionConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """保存店铺可分配利润率（行内保存）"""
    try:
        pc = (platform_code or "").lower()
        sid = str(shop_id or "")
        shop_res = await db.execute(
            select(DimShop).where(DimShop.platform_code == pc, DimShop.shop_id == sid)
        )
        if not shop_res.scalar_one_or_none():
            return error_response(ErrorCode.DATA_NOT_FOUND, "该店铺尚未同步至系统，请先在账号管理中同步", status_code=400)
        existing = await db.execute(
            select(ShopCommissionConfig).where(
                ShopCommissionConfig.platform_code == pc,
                ShopCommissionConfig.shop_id == sid,
            )
        )
        rec = existing.scalar_one_or_none()
        rate = float(body.allocatable_profit_rate)
        if rec:
            rec.allocatable_profit_rate = rate
            rec.updated_at = datetime.now(timezone.utc)
        else:
            rec = ShopCommissionConfig(
                platform_code=pc,
                shop_id=sid,
                allocatable_profit_rate=rate,
            )
            db.add(rec)
        await db.commit()
        return {"success": True, "data": {"platform_code": pc, "shop_id": sid, "allocatable_profit_rate": rate}}
    except Exception as e:
        await db.rollback()
        logger.error(f"保存店铺可分配利润率失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"保存失败: {str(e)}", status_code=500)


@router.post("/employee-shop-assignments/copy-from-prev-month")
async def copy_employee_shop_assignments_from_prev_month(
    body: CopyFromPrevMonthBody,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """将上一月的归属配置复制到指定月份；若目标月已有配置则跳过（不覆盖）"""
    try:
        parts = body.year_month.split("-")
        y, m = int(parts[0]), int(parts[1])
        if m == 1:
            prev_month = f"{y - 1}-12"
        else:
            prev_month = f"{y}-{m - 1:02d}"
        # 查上月所有归属
        prev_query = (
            select(EmployeeShopAssignment)
            .where(EmployeeShopAssignment.year_month == prev_month)
            .where(EmployeeShopAssignment.status == "active")
        )
        prev_rows = (await db.execute(prev_query)).scalars().all()
        if not prev_rows:
            return {"success": True, "data": {"copied": 0, "message": f"上月 {prev_month} 无配置可复制"}}
        # 查目标月已有 (employee_code, platform_code, shop_id)
        target_query = (
            select(EmployeeShopAssignment.employee_code, EmployeeShopAssignment.platform_code, EmployeeShopAssignment.shop_id)
            .where(EmployeeShopAssignment.year_month == body.year_month)
        )
        target_set = {(r.employee_code, r.platform_code, r.shop_id) for r in (await db.execute(target_query)).scalars().all()}
        copied = 0
        for r in prev_rows:
            key = (r.employee_code, r.platform_code, r.shop_id)
            if key in target_set:
                continue
            new_rec = EmployeeShopAssignment(
                year_month=body.year_month,
                employee_code=r.employee_code,
                platform_code=r.platform_code,
                shop_id=r.shop_id,
                commission_ratio=r.commission_ratio,
                role=r.role,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
                status="active",
            )
            db.add(new_rec)
            copied += 1
        await db.commit()
        return {"success": True, "data": {"copied": copied, "from_month": prev_month, "to_month": body.year_month}}
    except Exception as e:
        await db.rollback()
        logger.error(f"复制上月配置失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"复制上月配置失败: {str(e)}", status_code=500)


@router.get("/shop-profit-statistics")
async def get_shop_profit_statistics(
    request: Request,
    month: str = Query(..., description="月份 YYYY-MM"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """获取店铺月度销售额与利润统计（用于人员店铺归属统计页）"""
    try:
        # 解析月份为月初日期
        try:
            month_date = year_month_to_first_day(month)
        except (ValueError, IndexError):
            return error_response(ErrorCode.PARAMETER_INVALID, "月份格式应为 YYYY-MM", status_code=400)

        cache_params = {"month": month}
        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("hr_shop_profit_statistics", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"

        # 1. 获取店铺列表（platform_accounts）
        shop_query = (
            select(PlatformAccount)
            .where(PlatformAccount.enabled == True)
            .order_by(PlatformAccount.platform, PlatformAccount.store_name)
        )
        shop_rows = (await db.execute(shop_query)).scalars().all()
        shop_list = [
            {
                "platform_code": (r.platform or "").lower(),
                "shop_id": r.shop_id or r.account_id or str(r.id),
                "shop_name": r.store_name or (r.account_alias or ""),
            }
            for r in shop_rows
        ]

        # 2. 尝试通过 Metabase 获取店铺月度销售额与利润
        metrics_by_shop: Dict[str, Dict] = {}
        try:
            from backend.services.metabase_question_service import get_metabase_service
            service = get_metabase_service()
            metabase_result = await service.query_question("hr_shop_monthly_metrics", {"month": month_date.isoformat()})
            if metabase_result and isinstance(metabase_result, list):
                for row in metabase_result:
                    if isinstance(row, dict):
                        pc = (row.get("platform_code") or row.get("平台") or "").lower()
                        sid = str(row.get("shop_id") or row.get("店铺ID") or "unknown").lower()
                        key = f"{pc}|{sid}"
                        ms = row.get("monthly_sales")
                        mp = row.get("monthly_profit")
                        metrics_by_shop[key] = {
                            "monthly_sales": float(ms) if ms is not None else 0,
                            "monthly_profit": float(mp) if mp is not None else 0,
                            "achievement_rate": row.get("achievement_rate"),
                        }
        except Exception as e:
            logger.warning(f"Metabase 店铺月度统计查询失败，将返回空数据: {e}")

        # 3. 获取店铺可分配利润率配置
        config_query = select(ShopCommissionConfig)
        config_rows = (await db.execute(config_query)).scalars().all()
        allocatable_by_shop: Dict[str, float] = {
            f"{(c.platform_code or '').lower()}|{c.shop_id}": float(c.allocatable_profit_rate or 0)
            for c in config_rows
        }

        # 4. 获取归属配置（用于计算主管/操作员利润）：仅取该月的配置
        assign_query = (
            select(EmployeeShopAssignment)
            .where(EmployeeShopAssignment.status == "active")
            .where(EmployeeShopAssignment.year_month == month)
        )
        assign_rows = (await db.execute(assign_query)).scalars().all()

        # 按店铺分组：supervisors 和 operators，各自 commission_ratio 列表
        assign_by_shop: Dict[str, Dict] = {}
        for a in assign_rows:
            key = f"{(a.platform_code or '').lower()}|{a.shop_id}"
            if key not in assign_by_shop:
                assign_by_shop[key] = {"supervisors": [], "operators": []}
            cr = float(a.commission_ratio or 0)
            if a.role == "supervisor":
                assign_by_shop[key]["supervisors"].append(cr)
            else:
                assign_by_shop[key]["operators"].append(cr)

        # 5. 合并：店铺列表 + 销售/利润 + 主管/操作员利润
        items = []
        for s in shop_list:
            key = f"{s['platform_code']}|{str(s['shop_id']).lower()}"
            m = metrics_by_shop.get(key) or metrics_by_shop.get(f"{s['platform_code']}|{s['shop_id']}") or {}
            monthly_sales = float(m.get("monthly_sales", 0))
            monthly_profit = float(m.get("monthly_profit", 0))
            achievement_rate = m.get("achievement_rate")
            allocatable_rate = allocatable_by_shop.get(key, 1.0)  # 无配置时默认 100% 可分配
            allocatable_profit = monthly_profit * allocatable_rate
            ass = assign_by_shop.get(key, {})
            sup_ratios = ass.get("supervisors", [])
            op_ratios = ass.get("operators", [])
            supervisor_profit = allocatable_profit * sum(sup_ratios) if sup_ratios else 0
            operator_profit = allocatable_profit * sum(op_ratios) if op_ratios else 0
            items.append({
                "platform_code": s["platform_code"],
                "shop_id": s["shop_id"],
                "shop_name": s["shop_name"],
                "monthly_sales": monthly_sales,
                "monthly_profit": monthly_profit,
                "achievement_rate": achievement_rate,
                "supervisor_profit": supervisor_profit,
                "operator_profit": operator_profit,
            })
        result = {"success": True, "data": items}
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("hr_shop_profit_statistics", result, **cache_params)
        return JSONResponse(content=result, headers={"X-Cache": cache_status})
    except Exception as e:
        logger.error(f"获取店铺利润统计失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取店铺利润统计失败: {str(e)}", status_code=500)


@router.get("/annual-profit-statistics")
async def get_annual_profit_statistics(
    request: Request,
    year: int = Query(..., ge=2000, le=2100, description="年份，如 2025"),
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    """获取年度店铺/人员利润统计：按人员展示各月利润收入，按店铺展示各月销售额/利润/达成率。"""
    try:
        cache_params = {"year": str(year)}
        cache_status = "BYPASS"
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            cached = await cache_service.get("hr_annual_profit_statistics", **cache_params)
            if cached is not None:
                return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
            cache_status = "MISS"

        # 1. 店铺列表（全年共用）
        shop_query = (
            select(PlatformAccount)
            .where(PlatformAccount.enabled == True)
            .order_by(PlatformAccount.platform, PlatformAccount.store_name)
        )
        shop_rows = (await db.execute(shop_query)).scalars().all()
        shop_list = [
            {
                "platform_code": (r.platform or "").lower(),
                "shop_id": r.shop_id or r.account_id or str(r.id),
                "shop_name": r.store_name or (r.account_alias or ""),
            }
            for r in shop_rows
        ]

        by_employee: Dict[str, Dict[str, Any]] = {}  # employee_code -> { months: {"01": profit}, year_total_profit }
        by_shop: Dict[str, Dict[str, Any]] = {}  # key -> { platform_code, shop_id, shop_name, months: {"01": {...}}, year_total_sales, year_total_profit }
        for s in shop_list:
            key = f"{s['platform_code']}|{str(s['shop_id']).lower()}"
            by_shop[key] = {
                "platform_code": s["platform_code"],
                "shop_id": s["shop_id"],
                "shop_name": s["shop_name"],
                "months": {},
                "year_total_sales": 0.0,
                "year_total_profit": 0.0,
            }

        # 加载店铺可分配利润率配置（年度统计共用）
        config_query = select(ShopCommissionConfig)
        config_rows = (await db.execute(config_query)).scalars().all()
        allocatable_by_shop: Dict[str, float] = {
            f"{(c.platform_code or '').lower()}|{c.shop_id}": float(c.allocatable_profit_rate or 0)
            for c in config_rows
        }

        metabase_svc = None
        try:
            from backend.services.metabase_question_service import get_metabase_service
            metabase_svc = get_metabase_service()
        except Exception as e:
            logger.warning(f"Metabase 服务不可用，年度统计将返回空指标: {e}")

        for month_num in range(1, 13):
            month_str = f"{year}-{month_num:02d}"
            try:
                month_date = date(year, month_num, 1)
            except (ValueError, TypeError):
                continue

            metrics_by_shop: Dict[str, Dict] = {}
            if metabase_svc:
                try:
                    metabase_result = await metabase_svc.query_question(
                        "hr_shop_monthly_metrics", {"month": month_date.isoformat()}
                    )
                    if metabase_result and isinstance(metabase_result, list):
                        for row in metabase_result:
                            if isinstance(row, dict):
                                pc = (row.get("platform_code") or row.get("平台") or "").lower()
                                sid = str(row.get("shop_id") or row.get("店铺ID") or "unknown").lower()
                                key = f"{pc}|{sid}"
                                ms = row.get("monthly_sales")
                                mp = row.get("monthly_profit")
                                metrics_by_shop[key] = {
                                    "monthly_sales": float(ms) if ms is not None else 0,
                                    "monthly_profit": float(mp) if mp is not None else 0,
                                    "achievement_rate": row.get("achievement_rate"),
                                }
                except Exception as e:
                    logger.warning(f"Metabase 月度 {month_str} 查询失败: {e}")

            assign_query = (
                select(EmployeeShopAssignment)
                .where(EmployeeShopAssignment.status == "active")
                .where(EmployeeShopAssignment.year_month == month_str)
            )
            assign_result = (await db.execute(assign_query)).all()
            # 兼容 Row/ORM：每行可能是 (entity,) 或 entity
            assign_rows = [
                (r[0] if hasattr(r, "__getitem__") and len(r) == 1 else r)
                for r in assign_result
            ]

            # 按店铺：主管/操作员 (employee_code, ratio) 列表，用于计算每人利润
            assign_by_shop: Dict[str, Dict[str, List[tuple]]] = {}
            for a in assign_rows:
                _platform = getattr(a, "platform_code", None) or ""
                _shop_id = getattr(a, "shop_id", None) or ""
                _emp_code = (getattr(a, "employee_code", None) or "").strip()
                _role = getattr(a, "role", None) or ""
                _cr = float(getattr(a, "commission_ratio", None) or 0)
                key = f"{(_platform or '').lower()}|{_shop_id}"
                if key not in assign_by_shop:
                    assign_by_shop[key] = {"supervisors": [], "operators": []}
                if _role == "supervisor":
                    assign_by_shop[key]["supervisors"].append((_emp_code, _cr))
                else:
                    assign_by_shop[key]["operators"].append((_emp_code, _cr))

            month_key = f"{month_num:02d}"

            for s in shop_list:
                key = f"{s['platform_code']}|{str(s['shop_id']).lower()}"
                m = metrics_by_shop.get(key) or metrics_by_shop.get(f"{s['platform_code']}|{s['shop_id']}") or {}
                monthly_sales = float(m.get("monthly_sales", 0))
                monthly_profit = float(m.get("monthly_profit", 0))
                achievement_rate = m.get("achievement_rate")
                allocatable_rate = allocatable_by_shop.get(key, 1.0)
                allocatable_profit = monthly_profit * allocatable_rate
                ass = assign_by_shop.get(key, {})
                sup_list = ass.get("supervisors", [])
                op_list = ass.get("operators", [])
                supervisor_profit = allocatable_profit * sum(r for _, r in sup_list)
                operator_profit = allocatable_profit * sum(r for _, r in op_list)

                by_shop[key]["months"][month_key] = {
                    "monthly_sales": monthly_sales,
                    "monthly_profit": monthly_profit,
                    "achievement_rate": achievement_rate,
                    "supervisor_profit": supervisor_profit,
                    "operator_profit": operator_profit,
                }
                by_shop[key]["year_total_sales"] += monthly_sales
                by_shop[key]["year_total_profit"] += monthly_profit

                for emp_code, ratio in sup_list + op_list:
                    if not emp_code:
                        continue
                    if emp_code not in by_employee:
                        by_employee[emp_code] = {"months": {}, "year_total_profit": 0.0}
                    profit_this_month = allocatable_profit * ratio
                    by_employee[emp_code]["months"][month_key] = (
                        by_employee[emp_code]["months"].get(month_key, 0.0) + profit_this_month
                    )
                    by_employee[emp_code]["year_total_profit"] = (
                        by_employee[emp_code].get("year_total_profit", 0.0) + profit_this_month
                    )

        # 补全 by_employee 各月键（无数据月份为 0）
        for emp_code, rec in by_employee.items():
            for m in range(1, 13):
                mk = f"{m:02d}"
                if mk not in rec["months"]:
                    rec["months"][mk] = 0.0

        # 员工姓名
        employee_codes = list(by_employee.keys())
        name_map: Dict[str, str] = {}
        if employee_codes:
            emp_name_query = select(Employee.employee_code, Employee.name).where(
                Employee.employee_code.in_(employee_codes)
            )
            emp_name_rows = (await db.execute(emp_name_query)).all()
            # 兼容 Row/tuple：用索引访问，避免 .employee_code 在 Row 上报错
            name_map = {}
            for r in emp_name_rows:
                if hasattr(r, "__getitem__") and len(r) >= 2:
                    name_map[r[0]] = r[1] or r[0]
                elif hasattr(r, "__getitem__") and len(r) == 1:
                    name_map[r[0]] = r[0]
                else:
                    code = getattr(r, "employee_code", "")
                    name_map[code] = getattr(r, "name", None) or code

        by_employee_list = [
            {
                "employee_code": ec,
                "employee_name": name_map.get(ec, ec),
                "months": {k: round(float(v), 2) for k, v in data["months"].items()},
                "year_total_profit": round(data["year_total_profit"], 2),
            }
            for ec, data in sorted(by_employee.items())
        ]
        by_shop_list = [
            {
                "platform_code": row["platform_code"],
                "shop_id": row["shop_id"],
                "shop_name": row["shop_name"],
                "months": row["months"],
                "year_total_sales": round(row["year_total_sales"], 2),
                "year_total_profit": round(row["year_total_profit"], 2),
            }
            for row in sorted(by_shop.values(), key=lambda x: (x["platform_code"], x["shop_id"]))
        ]

        result = {
            "success": True,
            "data": {
                "year": year,
                "by_employee": by_employee_list,
                "by_shop": by_shop_list,
            },
        }
        if request and hasattr(request.app.state, "cache_service"):
            await request.app.state.cache_service.set("hr_annual_profit_statistics", result, **cache_params)
        return JSONResponse(content=result, headers={"X-Cache": cache_status})
    except Exception as e:
        logger.error(f"获取年度利润统计失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取年度利润统计失败: {str(e)}", status_code=500)

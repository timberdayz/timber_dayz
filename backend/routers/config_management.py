"""
A类数据管理API路由
Description: 销售目标、战役目标、经营成本的CRUD操作
Created: 2025-11-22
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from dateutil.relativedelta import relativedelta

from backend.models.database import get_db, get_async_db
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/config", tags=["配置管理"])


# ============================================================================
# Pydantic模型
# ============================================================================

# 销售目标
class SalesTargetCreate(BaseModel):
    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(..., description="目标月份（YYYY-MM）", pattern=r"^\d{4}-\d{2}$")
    target_sales_amount: float = Field(..., ge=0, description="目标销售额")
    target_order_count: int = Field(..., ge=0, description="目标订单数")


class SalesTargetUpdate(BaseModel):
    target_sales_amount: Optional[float] = Field(None, ge=0)
    target_order_count: Optional[int] = Field(None, ge=0)


class SalesTargetResponse(BaseModel):
    id: UUID
    shop_id: str
    year_month: str
    target_sales_amount: float
    target_order_count: int
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


# 战役目标
class CampaignTargetCreate(BaseModel):
    platform_code: str = Field(..., description="平台代码")
    campaign_name: str = Field(..., description="战役名称")
    campaign_type: Optional[str] = Field(None, description="战役类型")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    target_gmv: float = Field(..., ge=0, description="目标GMV")
    target_roi: Optional[float] = Field(None, ge=0, description="目标ROI")
    budget_amount: Optional[float] = Field(None, ge=0, description="预算金额")


class CampaignTargetUpdate(BaseModel):
    campaign_name: Optional[str] = None
    campaign_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_gmv: Optional[float] = Field(None, ge=0)
    target_roi: Optional[float] = Field(None, ge=0)
    budget_amount: Optional[float] = Field(None, ge=0)


class CampaignTargetResponse(BaseModel):
    id: UUID
    platform_code: str
    campaign_name: str
    campaign_type: Optional[str]
    start_date: date
    end_date: date
    target_gmv: float
    target_roi: Optional[float]
    budget_amount: Optional[float]
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


# 经营成本
class OperatingCostCreate(BaseModel):
    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(..., description="成本月份（YYYY-MM）", pattern=r"^\d{4}-\d{2}$")
    rent: float = Field(0, ge=0, description="租金")
    salary: float = Field(0, ge=0, description="工资")
    marketing: float = Field(0, ge=0, description="营销费用")
    logistics: float = Field(0, ge=0, description="物流费用")
    utilities: float = Field(0, ge=0, description="水电费")
    other: float = Field(0, ge=0, description="其他费用")


class OperatingCostUpdate(BaseModel):
    rent: Optional[float] = Field(None, ge=0)
    salary: Optional[float] = Field(None, ge=0)
    marketing: Optional[float] = Field(None, ge=0)
    logistics: Optional[float] = Field(None, ge=0)
    utilities: Optional[float] = Field(None, ge=0)
    other: Optional[float] = Field(None, ge=0)


class OperatingCostResponse(BaseModel):
    id: UUID
    shop_id: str
    year_month: str
    rent: float
    salary: float
    marketing: float
    logistics: float
    utilities: float
    other: float
    total: float  # 自动计算
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


# ============================================================================
# 销售目标API
# ============================================================================

@router.get("/sales-targets", response_model=List[SalesTargetResponse])
async def list_sales_targets(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="月份筛选（YYYY-MM）"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取销售目标列表"""
    try:
        result = await db.execute(
            """
            SELECT id, shop_id, year_month, target_sales_amount, 
                   target_order_count, created_at, created_by
            FROM sales_targets
            WHERE ($1::text IS NULL OR shop_id = $1)
              AND ($2::text IS NULL OR year_month = $2)
            ORDER BY year_month DESC, shop_id
            """,
            [shop_id, year_month]
        )
        
        results = result.fetchall()
        return [
            SalesTargetResponse(
                id=row[0],
                shop_id=row[1],
                year_month=row[2],
                target_sales_amount=row[3],
                target_order_count=row[4],
                created_at=row[5],
                created_by=row[6]
            )
            for row in results
        ]
    except Exception as e:
        logger.error(f"获取销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sales-targets", response_model=SalesTargetResponse, status_code=201)
async def create_sales_target(
    target: SalesTargetCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建销售目标"""
    try:
        # 检查是否已存在
        result = await db.execute(
            """
            SELECT id FROM sales_targets 
            WHERE shop_id = $1 AND year_month = $2
            """,
            [target.shop_id, target.year_month]
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"店铺{target.shop_id}在{target.year_month}的销售目标已存在"
            )
        
        # 插入新记录
        target_id = uuid4()
        await db.execute(
            """
            INSERT INTO sales_targets (
                id, shop_id, year_month, target_sales_amount, 
                target_order_count, created_at, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            [
                target_id, target.shop_id, target.year_month,
                target.target_sales_amount, target.target_order_count,
                datetime.now(), 'system'
            ]
        )
        await db.commit()
        
        # 返回创建的记录
        result = await db.execute(
            """
            SELECT id, shop_id, year_month, target_sales_amount,
                   target_order_count, created_at, created_by
            FROM sales_targets WHERE id = $1
            """,
            [target_id]
        ).fetchone()
        
        return SalesTargetResponse(
            id=result[0],
            shop_id=result[1],
            year_month=result[2],
            target_sales_amount=result[3],
            target_order_count=result[4],
            created_at=result[5],
            created_by=result[6]
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sales-targets/{target_id}", response_model=SalesTargetResponse)
async def update_sales_target(
    target_id: UUID,
    target: SalesTargetUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新销售目标"""
    try:
        # 构建更新语句
        update_fields = []
        params = []
        param_count = 1
        
        if target.target_sales_amount is not None:
            update_fields.append(f"target_sales_amount = ${param_count}")
            params.append(target.target_sales_amount)
            param_count += 1
        
        if target.target_order_count is not None:
            update_fields.append(f"target_order_count = ${param_count}")
            params.append(target.target_order_count)
            param_count += 1
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="没有提供更新字段")
        
        update_fields.append(f"updated_at = ${param_count}")
        params.append(datetime.now())
        param_count += 1
        
        params.append(target_id)
        
        await db.execute(
            f"""
            UPDATE sales_targets 
            SET {', '.join(update_fields)}
            WHERE id = ${param_count}
            """,
            params
        )
        await db.commit()
        
        # 返回更新后的记录
        result = await db.execute(
            """
            SELECT id, shop_id, year_month, target_sales_amount,
                   target_order_count, created_at, created_by
            FROM sales_targets WHERE id = $1
            """,
            [target_id]
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="销售目标不存在")
        
        return SalesTargetResponse(
            id=result[0],
            shop_id=result[1],
            year_month=result[2],
            target_sales_amount=result[3],
            target_order_count=result[4],
            created_at=result[5],
            created_by=result[6]
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sales-targets/{target_id}", status_code=204)
async def delete_sales_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """删除销售目标"""
    try:
        result = await db.execute(
            "DELETE FROM sales_targets WHERE id = $1",
            [target_id]
        )
        await db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="销售目标不存在")
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sales-targets/copy-last-month")
async def copy_last_month_targets(
    target_month: str = Query(..., description="目标月份（YYYY-MM）", pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    复制上月目标到指定月份
    
    从上一个月的目标复制到目标月份，如果目标月份已存在目标则跳过
    """
    try:
        # 解析目标月份
        target_date = datetime.strptime(target_month, "%Y-%m")
        # 计算上个月
        last_month_date = target_date - relativedelta(months=1)
        last_month = last_month_date.strftime("%Y-%m")
        
        # 查询上个月的所有目标
        result = await db.execute(
            """
            SELECT shop_id, target_sales_amount, target_order_count
            FROM sales_targets
            WHERE year_month = $1
            """,
            [last_month]
        )
        last_month_targets = result.fetchall()
        
        if not last_month_targets:
            return {
                "success": True,
                "message": f"上个月（{last_month}）没有目标数据，无需复制",
                "copied_count": 0,
                "skipped_count": 0
            }
        
        copied_count = 0
        skipped_count = 0
        
        for row in last_month_targets:
            shop_id, target_sales_amount, target_order_count = row
            
            # 检查目标月份是否已存在
            result = await db.execute(
                """
                SELECT id FROM sales_targets 
                WHERE shop_id = $1 AND year_month = $2
                """,
                [shop_id, target_month]
            ).fetchone()
            
            if existing:
                skipped_count += 1
                continue
            
            # 复制目标
            target_id = uuid4()
            await db.execute(
                """
                INSERT INTO sales_targets (
                    id, shop_id, year_month, target_sales_amount, 
                    target_order_count, created_at, created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    target_id, shop_id, target_month,
                    target_sales_amount, target_order_count,
                    datetime.now(), 'system'
                ]
            )
            copied_count += 1
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"成功从{last_month}复制目标到{target_month}",
            "copied_count": copied_count,
            "skipped_count": skipped_count,
            "total_count": len(last_month_targets)
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"复制上月目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sales-targets/batch-calculate")
async def batch_calculate_achievement_rate(
    year_month: Optional[str] = Query(None, description="月份筛选（YYYY-MM），为空则计算所有月份"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量计算达成率
    
    根据实际销售数据计算每个店铺的达成率
    实际数据从B类数据表（fact_raw_data_orders_daily）中查询
    """
    try:
        # 构建查询条件
        where_clause = "WHERE 1=1"
        params = []
        
        if year_month:
            where_clause += " AND st.year_month = $1"
            params.append(year_month)
        
        # 查询所有销售目标
        # ⚠️ 注意：sales_targets表没有shop_id字段，需要通过target_breakdown表关联店铺
        # 但根据提案，用户确认sales_targets表需要platform_code
        # 这里先查询target_breakdown表获取店铺信息
        result = await db.execute(
            text(f"""
            SELECT DISTINCT ON (tb.target_id)
                st.id as target_id,
                tb.shop_id,
                tb.platform_code,
                st.period_start::text as year_month,
                st.target_amount as target_sales_amount,
                st.target_quantity as target_order_count
            FROM sales_targets st
            INNER JOIN target_breakdown tb ON st.id = tb.target_id
            WHERE tb.breakdown_type = 'shop'
            {where_clause.replace('st.', 'tb.') if where_clause else ''}
            ORDER BY tb.target_id, tb.platform_code, tb.shop_id
            """)
        ).fetchall()
        
        # 如果没有target_breakdown数据，返回空结果
        if not targets:
            return {
                "success": True,
                "message": "没有找到需要计算的目标（或目标未关联店铺）",
                "calculated_count": 0
            }
        
        if not targets:
            return {
                "success": True,
                "message": "没有找到需要计算的目标",
                "calculated_count": 0
            }
        
        calculated_count = 0
        errors = []
        
        # 导入PlatformTableManager
        from backend.services.platform_table_manager import get_platform_table_manager
        platform_table_manager = get_platform_table_manager(db)
        
        for target in targets:
            target_id, shop_id, platform_code, target_month, target_sales_amount, target_order_count = target
            
            # 处理platform_code为NULL的情况
            if not platform_code:
                platform_code = 'unknown'
            
            try:
                # 生成动态表名
                table_name = platform_table_manager.get_table_name(
                    platform=platform_code,
                    data_domain='orders',
                    sub_domain=None,
                    granularity='daily'
                )
                
                # 从B类数据表查询实际销售数据（使用动态表名）
                result = await db.execute(
                    text(f"""
                    SELECT 
                        COALESCE(SUM((raw_data->>'销售额')::numeric), 0) as actual_sales,
                        COUNT(*) as actual_orders
                    FROM b_class."{table_name}"
                    WHERE shop_id = :shop_id
                      AND DATE_TRUNC('month', metric_date) = :target_month::date
                    """),
                    {
                        "shop_id": shop_id,
                        "target_month": f"{target_month}-01"
                    }
                )
                actual_data = result.fetchone()
                
                if actual_data:
                    actual_sales = float(actual_data[0]) if actual_data[0] else 0.0
                    actual_orders = int(actual_data[1]) if actual_data[1] else 0
                    
                    # 计算达成率
                    sales_achievement_rate = (actual_sales / target_sales_amount * 100) if target_sales_amount > 0 else 0.0
                    order_achievement_rate = (actual_orders / target_order_count * 100) if target_order_count > 0 else 0.0
                    
                    # 更新目标记录（如果表中有达成率字段）
                    # 注意：这里假设表中有achievement_rate字段，如果没有需要先添加
                    try:
                        await db.execute(
                            text("""
                            UPDATE sales_targets
                            SET 
                                actual_sales_amount = :actual_sales,
                                actual_order_count = :actual_orders,
                                sales_achievement_rate = :sales_rate,
                                order_achievement_rate = :order_rate,
                                updated_at = NOW()
                            WHERE id = :target_id
                            """),
                            {
                                "target_id": target_id,
                                "actual_sales": actual_sales,
                                "actual_orders": actual_orders,
                                "sales_rate": sales_achievement_rate,
                                "order_rate": order_achievement_rate
                            }
                        )
                        calculated_count += 1
                    except Exception as e:
                        # 如果表结构中没有这些字段，记录错误但不中断
                        logger.warning(f"更新目标{target_id}失败（可能表结构不匹配）: {e}")
                        errors.append(f"目标{target_id}: {str(e)}")
                else:
                    # 没有实际数据
                    logger.info(f"目标{target_id}（{shop_id}，{target_month}）没有实际销售数据")
                    
            except Exception as e:
                logger.error(f"计算目标{target_id}达成率失败: {e}")
                errors.append(f"目标{target_id}: {str(e)}")
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"批量计算达成率完成",
            "calculated_count": calculated_count,
            "total_count": len(targets),
            "errors": errors if errors else None
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"批量计算达成率失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 战役目标API（Campaign Targets）
# ============================================================================

@router.get("/campaign-targets", response_model=List[CampaignTargetResponse])
async def list_campaign_targets(
    platform: Optional[str] = Query(None, description="平台筛选"),
    year_month: Optional[str] = Query(None, description="月份筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取战役目标列表"""
    try:
        # 构建查询条件
        where_conditions = []
        params = []
        param_count = 1
        
        if platform:
            where_conditions.append(f"platform_code = ${param_count}")
            params.append(platform)
            param_count += 1
        
        if year_month:
            # 筛选该月份内开始的战役
            where_conditions.append(
                f"TO_CHAR(start_date, 'YYYY-MM') = ${param_count}"
            )
            params.append(year_month)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"
        
        result = await db.execute(
            f"""
            SELECT id, platform_code, campaign_name, campaign_type,
                   start_date, end_date, target_gmv, target_roi,
                   budget_amount, created_at, created_by
            FROM campaign_targets
            WHERE {where_clause}
            ORDER BY start_date DESC
            """,
            params
        )
        
        results = query.fetchall()
        return [
            CampaignTargetResponse(
                id=row[0],
                platform_code=row[1],
                campaign_name=row[2],
                campaign_type=row[3],
                start_date=row[4],
                end_date=row[5],
                target_gmv=row[6],
                target_roi=row[7],
                budget_amount=row[8],
                created_at=row[9],
                created_by=row[10]
            )
            for row in results
        ]
    except Exception as e:
        logger.error(f"获取战役目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaign-targets", response_model=CampaignTargetResponse, status_code=201)
async def create_campaign_target(
    target: CampaignTargetCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建战役目标"""
    try:
        # 验证日期
        if target.end_date < target.start_date:
            raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")
        
        # 插入记录
        target_id = uuid4()
        await db.execute(
            """
            INSERT INTO campaign_targets (
                id, platform_code, campaign_name, campaign_type,
                start_date, end_date, target_gmv, target_roi,
                budget_amount, created_at, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            [
                target_id, target.platform_code, target.campaign_name,
                target.campaign_type, target.start_date, target.end_date,
                target.target_gmv, target.target_roi, target.budget_amount,
                datetime.now(), 'system'
            ]
        )
        await db.commit()
        
        # 返回创建的记录
        result = await db.execute(
            """
            SELECT id, platform_code, campaign_name, campaign_type,
                   start_date, end_date, target_gmv, target_roi,
                   budget_amount, created_at, created_by
            FROM campaign_targets WHERE id = $1
            """,
            [target_id]
        ).fetchone()
        
        return CampaignTargetResponse(
            id=result[0],
            platform_code=result[1],
            campaign_name=result[2],
            campaign_type=result[3],
            start_date=result[4],
            end_date=result[5],
            target_gmv=result[6],
            target_roi=result[7],
            budget_amount=result[8],
            created_at=result[9],
            created_by=result[10]
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建战役目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 经营成本API（Operating Costs）
# ============================================================================

@router.get("/operating-costs", response_model=List[OperatingCostResponse])
async def list_operating_costs(
    shop_id: Optional[str] = Query(None),
    year_month: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """获取经营成本列表（使用原始SQL，因为表可能不存在）"""
    try:
        # 检查表是否存在
        result = await db.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'operating_costs'
            )
            """
        )
        table_exists = result.scalar()
        
        if not table_exists:
            logger.warning("operating_costs表不存在，返回空列表")
            return []
        
        # 查询数据
        result = await db.execute(
            """
            SELECT id, shop_id, year_month, rent, salary, marketing,
                   logistics, utilities, other, 
                   (COALESCE(rent,0) + COALESCE(salary,0) + COALESCE(marketing,0) + 
                    COALESCE(logistics,0) + COALESCE(utilities,0) + COALESCE(other,0)) as total,
                   created_at, created_by
            FROM operating_costs
            WHERE ($1::text IS NULL OR shop_id = $1)
              AND ($2::text IS NULL OR year_month = $2)
            ORDER BY year_month DESC, shop_id
            """,
            [shop_id, year_month]
        )
        
        results = result.fetchall()
        return [
            OperatingCostResponse(
                id=row[0],
                shop_id=row[1],
                year_month=row[2],
                rent=row[3] or 0,
                salary=row[4] or 0,
                marketing=row[5] or 0,
                logistics=row[6] or 0,
                utilities=row[7] or 0,
                other=row[8] or 0,
                total=row[9] or 0,
                created_at=row[10],
                created_by=row[11]
            )
            for row in results
        ]
    except Exception as e:
        logger.error(f"获取经营成本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operating-costs", response_model=OperatingCostResponse, status_code=201)
async def create_operating_cost(
    cost: OperatingCostCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建经营成本（如果表不存在会先创建）"""
    try:
        # 确保表存在
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS operating_costs (
                id UUID PRIMARY KEY,
                shop_id VARCHAR(100) NOT NULL,
                year_month VARCHAR(7) NOT NULL,
                rent DECIMAL(15,2) DEFAULT 0,
                salary DECIMAL(15,2) DEFAULT 0,
                marketing DECIMAL(15,2) DEFAULT 0,
                logistics DECIMAL(15,2) DEFAULT 0,
                utilities DECIMAL(15,2) DEFAULT 0,
                other DECIMAL(15,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by VARCHAR(100),
                CONSTRAINT uq_operating_costs_shop_month UNIQUE (shop_id, year_month)
            )
            """
        )
        
        # 检查是否已存在
        result = await db.execute(
            "SELECT id FROM operating_costs WHERE shop_id = $1 AND year_month = $2",
            [cost.shop_id, cost.year_month]
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"店铺{cost.shop_id}在{cost.year_month}的经营成本已存在"
            )
        
        # 插入记录
        cost_id = uuid4()
        total = cost.rent + cost.salary + cost.marketing + cost.logistics + cost.utilities + cost.other
        
        await db.execute(
            """
            INSERT INTO operating_costs (
                id, shop_id, year_month, rent, salary, marketing,
                logistics, utilities, other, created_at, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            [
                cost_id, cost.shop_id, cost.year_month, cost.rent,
                cost.salary, cost.marketing, cost.logistics,
                cost.utilities, cost.other, datetime.now(), 'system'
            ]
        )
        await db.commit()
        
        return OperatingCostResponse(
            id=cost_id,
            shop_id=cost.shop_id,
            year_month=cost.year_month,
            rent=cost.rent,
            salary=cost.salary,
            marketing=cost.marketing,
            logistics=cost.logistics,
            utilities=cost.utilities,
            other=cost.other,
            total=total,
            created_at=datetime.now(),
            created_by='system'
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建经营成本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


"""
A类数据管理API路由
Description: 销售目标、战役目标、经营成本的CRUD操作
Created: 2025-11-22

v4.21.0+ 销售目标CRUD 使用 a_class.sales_targets_a（店铺月度聚合表）
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

# 销售目标（店铺月度聚合，对应 a_class.sales_targets_a）
class SalesTargetCreate(BaseModel):
    shop_id: str = Field(..., description="店铺ID")
    year_month: str = Field(..., description="目标月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$")
    target_sales_amount: float = Field(..., ge=0, description="目标销售额")
    target_order_count: int = Field(..., ge=0, description="目标订单数")


class SalesTargetUpdate(BaseModel):
    target_sales_amount: Optional[float] = Field(None, ge=0)
    target_order_count: Optional[int] = Field(None, ge=0)


class SalesTargetResponse(BaseModel):
    id: int
    shop_id: str
    year_month: str
    target_sales_amount: float
    target_order_count: int
    created_at: datetime
    created_by: Optional[str] = None

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


# ============================================================================
# 销售目标API - 使用 a_class.sales_targets_a（店铺月度聚合表）
# v4.21.0+ 从 public.sales_targets 迁移至 a_class.sales_targets_a
# 表结构：id, shop_id, year_month, target_sales_amount, target_quantity, created_at, updated_at
# 或中文字段：id, 店铺ID, 年月, 目标销售额, 目标订单数, 创建时间, 更新时间
# ============================================================================

@router.get("/sales-targets", response_model=List[SalesTargetResponse])
async def list_sales_targets(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="月份筛选(YYYY-MM)"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取销售目标列表（a_class.sales_targets_a）"""
    try:
        result = await db.execute(text("""
            SELECT id, shop_id, year_month, target_sales_amount, target_quantity,
                   created_at
            FROM a_class.sales_targets_a
            WHERE (:shop_id::text IS NULL OR shop_id = :shop_id)
              AND (:year_month::text IS NULL OR year_month = :year_month)
            ORDER BY year_month DESC, shop_id
        """), {"shop_id": shop_id, "year_month": year_month})
    except Exception:
        try:
            result = await db.execute(text("""
                SELECT id, "店铺ID", "年月", "目标销售额", "目标订单数", "创建时间"
                FROM a_class.sales_targets_a
                WHERE (:shop_id::text IS NULL OR "店铺ID" = :shop_id)
                  AND (:year_month::text IS NULL OR "年月" = :year_month)
                ORDER BY "年月" DESC, "店铺ID"
            """), {"shop_id": shop_id, "year_month": year_month})
        except Exception as e:
            logger.error(f"获取销售目标失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    rows = result.fetchall()
    return [
        SalesTargetResponse(
            id=row[0],
            shop_id=str(row[1]),
            year_month=str(row[2]),
            target_sales_amount=float(row[3]),
            target_order_count=int(row[4]) if row[4] is not None else 0,
            created_at=row[5],
            created_by=None
        )
        for row in rows
    ]


@router.post("/sales-targets", response_model=SalesTargetResponse, status_code=201)
async def create_sales_target(
    target: SalesTargetCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建销售目标（a_class.sales_targets_a，upsert）"""
    try:
        try:
            # 英文字段
            await db.execute(text("""
                INSERT INTO a_class.sales_targets_a
                (shop_id, year_month, target_sales_amount, target_quantity, created_at, updated_at)
                VALUES (:shop_id, :year_month, :target_sales_amount, :target_order_count, NOW(), NOW())
                ON CONFLICT (shop_id, year_month) DO UPDATE SET
                    target_sales_amount = EXCLUDED.target_sales_amount,
                    target_quantity = EXCLUDED.target_quantity,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "shop_id": target.shop_id,
                "year_month": target.year_month,
                "target_sales_amount": target.target_sales_amount,
                "target_order_count": target.target_order_count,
            })
        except Exception:
            # 中文字段
            await db.execute(text("""
                INSERT INTO a_class.sales_targets_a
                ("店铺ID", "年月", "目标销售额", "目标订单数", "创建时间", "更新时间")
                VALUES (:shop_id, :year_month, :target_sales_amount, :target_order_count, NOW(), NOW())
                ON CONFLICT ("店铺ID", "年月") DO UPDATE SET
                    "目标销售额" = EXCLUDED."目标销售额",
                    "目标订单数" = EXCLUDED."目标订单数",
                    "更新时间" = CURRENT_TIMESTAMP
            """), {
                "shop_id": target.shop_id,
                "year_month": target.year_month,
                "target_sales_amount": target.target_sales_amount,
                "target_order_count": target.target_order_count,
            })
        await db.commit()
        r = await db.execute(text("""
            SELECT id, shop_id, year_month, target_sales_amount, target_quantity, created_at
            FROM a_class.sales_targets_a WHERE shop_id = :shop_id AND year_month = :year_month
        """), {"shop_id": target.shop_id, "year_month": target.year_month})
        row = r.fetchone()
        if not row:
            r = await db.execute(text("""
                SELECT id, "店铺ID", "年月", "目标销售额", "目标订单数", "创建时间"
                FROM a_class.sales_targets_a WHERE "店铺ID" = :shop_id AND "年月" = :year_month
            """), {"shop_id": target.shop_id, "year_month": target.year_month})
            row = r.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="创建成功但查询失败")
        return SalesTargetResponse(
            id=row[0],
            shop_id=str(row[1]),
            year_month=str(row[2]),
            target_sales_amount=float(row[3]),
            target_order_count=int(row[4]) if row[4] is not None else 0,
            created_at=row[5],
            created_by=None
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sales-targets/{target_id}", response_model=SalesTargetResponse)
async def update_sales_target(
    target_id: int,
    target: SalesTargetUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新销售目标（a_class.sales_targets_a）"""
    try:
        updates = []
        params = {"target_id": target_id}
        if target.target_sales_amount is not None:
            updates.append("target_sales_amount = :target_sales_amount")
            params["target_sales_amount"] = target.target_sales_amount
        if target.target_order_count is not None:
            updates.append("target_quantity = :target_order_count")
            params["target_order_count"] = target.target_order_count
        if not updates:
            raise HTTPException(status_code=400, detail="没有提供更新字段")
        updates.append("updated_at = NOW()")
        try:
            await db.execute(text(f"""
                UPDATE a_class.sales_targets_a SET {", ".join(updates)}
                WHERE id = :target_id
            """), params)
        except Exception:
            u2 = []
            p2 = {"target_id": target_id}
            if target.target_sales_amount is not None:
                u2.append('"目标销售额" = :target_sales_amount')
                p2["target_sales_amount"] = target.target_sales_amount
            if target.target_order_count is not None:
                u2.append('"目标订单数" = :target_order_count')
                p2["target_order_count"] = target.target_order_count
            u2.append('"更新时间" = NOW()')
            await db.execute(text(f"""
                UPDATE a_class.sales_targets_a SET {", ".join(u2)}
                WHERE id = :target_id
            """), p2)
        await db.commit()
        r = await db.execute(text("SELECT id, shop_id, year_month, target_sales_amount, target_quantity, created_at FROM a_class.sales_targets_a WHERE id = :tid"), {"tid": target_id})
        row = r.fetchone()
        if not row:
            r = await db.execute(text('SELECT id, "店铺ID", "年月", "目标销售额", "目标订单数", "创建时间" FROM a_class.sales_targets_a WHERE id = :tid'), {"tid": target_id})
            row = r.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="销售目标不存在")
        return SalesTargetResponse(id=row[0], shop_id=str(row[1]), year_month=str(row[2]),
            target_sales_amount=float(row[3]), target_order_count=int(row[4]) if row[4] else 0,
            created_at=row[5], created_by=None)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sales-targets/{target_id}", status_code=204)
async def delete_sales_target(
    target_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除销售目标（a_class.sales_targets_a）"""
    try:
        result = await db.execute(text("DELETE FROM a_class.sales_targets_a WHERE id = :tid"), {"tid": target_id})
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="销售目标不存在")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sales-targets/copy-last-month")
async def copy_last_month_targets(
    target_month: str = Query(..., description="目标月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_async_db)
):
    """复制上月目标到指定月份（a_class.sales_targets_a）"""
    try:
        target_date = datetime.strptime(target_month, "%Y-%m")
        last_month = (target_date - relativedelta(months=1)).strftime("%Y-%m")
        result = await db.execute(text("""
            SELECT shop_id, target_sales_amount, target_quantity
            FROM a_class.sales_targets_a WHERE year_month = :lm
        """), {"lm": last_month})
        rows = result.fetchall()
    except Exception:
        result = await db.execute(text('SELECT "店铺ID", "目标销售额", "目标订单数" FROM a_class.sales_targets_a WHERE "年月" = :lm'), {"lm": last_month})
        rows = result.fetchall()
    if not rows:
        return {"success": True, "message": f"上月({last_month})无数据", "copied_count": 0, "skipped_count": 0}
    copied, skipped = 0, 0
    for r in rows:
        try:
            await db.execute(text("""
                INSERT INTO a_class.sales_targets_a (shop_id, year_month, target_sales_amount, target_quantity, created_at, updated_at)
                VALUES (:shop_id, :target_month, :amt, :qty, NOW(), NOW())
                ON CONFLICT (shop_id, year_month) DO NOTHING
            """), {"shop_id": r[0], "target_month": target_month, "amt": r[1], "qty": r[2]})
            copied += 1
        except Exception:
            try:
                await db.execute(text("""
                    INSERT INTO a_class.sales_targets_a ("店铺ID", "年月", "目标销售额", "目标订单数", "创建时间", "更新时间")
                    VALUES (:shop_id, :target_month, :amt, :qty, NOW(), NOW())
                    ON CONFLICT ("店铺ID", "年月") DO NOTHING
                """), {"shop_id": r[0], "target_month": target_month, "amt": r[1], "qty": r[2]})
                copied += 1
            except Exception:
                skipped += 1
    await db.commit()
    return {"success": True, "message": f"已从{last_month}复制到{target_month}", "copied_count": copied, "skipped_count": skipped, "total_count": len(rows)}


# ============================================================================
# 战役目标API (campaign_targets - 保留原实现)
# ============================================================================

@router.get("/campaign-targets", response_model=List[CampaignTargetResponse])
async def list_campaign_targets(
    platform: Optional[str] = Query(None, description="平台筛选"),
    year_month: Optional[str] = Query(None, description="月份筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取战役目标列表"""
    try:
        where_conditions = ["TRUE"]
        params = {}
        if platform:
            where_conditions.append("platform_code = :platform")
            params["platform"] = platform
        if year_month:
            where_conditions.append("TO_CHAR(start_date, 'YYYY-MM') = :year_month")
            params["year_month"] = year_month
        result = await db.execute(text(f"""
            SELECT id, platform_code, campaign_name, campaign_type,
                   start_date, end_date, target_gmv, target_roi,
                   budget_amount, created_at, created_by
            FROM campaign_targets
            WHERE {" AND ".join(where_conditions)}
            ORDER BY start_date DESC
        """), params)
        rows = result.fetchall()
        return [
            CampaignTargetResponse(
                id=row[0], platform_code=row[1], campaign_name=row[2],
                campaign_type=row[3], start_date=row[4], end_date=row[5],
                target_gmv=row[6], target_roi=row[7], budget_amount=row[8],
                created_at=row[9], created_by=row[10]
            )
            for row in rows
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
        if target.end_date < target.start_date:
            raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")
        target_id = uuid4()
        await db.execute(text("""
            INSERT INTO campaign_targets
            (id, platform_code, campaign_name, campaign_type,
             start_date, end_date, target_gmv, target_roi, budget_amount, created_at, created_by)
            VALUES (:id, :platform_code, :campaign_name, :campaign_type,
                    :start_date, :end_date, :target_gmv, :target_roi, :budget_amount, NOW(), 'system')
        """), {
            "id": str(target_id), "platform_code": target.platform_code,
            "campaign_name": target.campaign_name, "campaign_type": target.campaign_type or "",
            "start_date": target.start_date, "end_date": target.end_date,
            "target_gmv": target.target_gmv, "target_roi": target.target_roi or 0,
            "budget_amount": target.budget_amount or 0
        })
        await db.commit()
        r = await db.execute(text("""
            SELECT id, platform_code, campaign_name, campaign_type,
                   start_date, end_date, target_gmv, target_roi, budget_amount, created_at, created_by
            FROM campaign_targets WHERE id = :id
        """), {"id": str(target_id)})
        row = r.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="创建成功但查询失败")
        return CampaignTargetResponse(
            id=row[0], platform_code=row[1], campaign_name=row[2],
            campaign_type=row[3], start_date=row[4], end_date=row[5],
            target_gmv=row[6], target_roi=row[7], budget_amount=row[8],
            created_at=row[9], created_by=row[10]
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建战役目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


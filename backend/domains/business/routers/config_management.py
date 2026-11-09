"""
A类数据管理API路由
Description: 销售目标、战役目标、经营成本的CRUD操作
Created: 2025-11-22

v4.21.0+ 销售目标CRUD 使用店铺月度档位
第三批-C：真 SSOT = a_class.target_breakdown（breakdown_type='shop'）
  + 父目标 a_class.sales_targets；派生副本 a_class.sales_targets_a 已下线。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from dateutil.relativedelta import relativedelta

from backend.models.database import get_db, get_async_db
from backend.schemas.config import (
    SalesTargetCreate,
    SalesTargetUpdate,
    SalesTargetResponse,
    CampaignTargetCreate,
    CampaignTargetUpdate,
    CampaignTargetResponse,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/config", tags=["配置管理"])


# ============================================================================
# 销售目标API - 真 SSOT：a_class.target_breakdown（店铺 × 月档位）
#
# 第三批-C：a_class.sales_targets_a（派生副本）已下线（物理表被 DROP）。
# 「店铺月度目标」现在直接读写：
#   a_class.target_breakdown  (breakdown_type='shop'，period_label='YYYY-MM')
#   └─ 父目标 a_class.sales_targets (target_type='shop', status='active')
#
# 前端契约保持不变：GET/POST/PUT/DELETE /api/config/sales-targets
# 返回字段仍是 id / shop_id / year_month / target_sales_amount /
# target_order_count / created_at / created_by
# ============================================================================

#: 「店铺 × 月」的月份键表达式。
#: period_label 是仓库既有的「店铺月度档位」约定（'YYYY-MM'）；
#: 历史行可能还没写 period_label，回退到父目标周期推导。
_MONTH_EXPR = (
    "COALESCE(NULLIF(tb.period_label, ''), "
    "to_char(COALESCE(tb.period_start, st.period_start), 'YYYY-MM'))"
)


def _month_range(year_month: str) -> tuple[date, date]:
    """'YYYY-MM' → (月首日, 月末日)。"""
    year, month = (int(part) for part in year_month.split("-")[:2])
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year, 12, 31)
    else:
        month_end = date(year, month + 1, 1) - relativedelta(days=1)
    return month_start, month_end


async def _resolve_platform_code(db: AsyncSession, shop_id: str) -> Optional[str]:
    """从 core.dim_shops 反查店铺所属平台（target_breakdown 的外键需要它）。"""
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT platform_code
                FROM core.dim_shops
                WHERE shop_id = :shop_id
                """
            ),
            {"shop_id": shop_id},
        )
    ).scalars().all()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            f"[ConfigManagement] 店铺 {shop_id} 在 dim_shops 里对应多个平台 {rows}, 取第一个"
        )
    return str(rows[0])


async def _resolve_month_target_id(
    db: AsyncSession,
    year_month: str,
    month_start: date,
    month_end: date,
) -> int:
    """找到（或按需新建）该月的「店铺型」父目标 id。"""
    existing = (
        await db.execute(
            text(
                """
                SELECT id
                FROM a_class.sales_targets
                WHERE target_type = 'shop'
                  AND status = 'active'
                  AND period_start <= :month_end
                  AND period_end >= :month_start
                ORDER BY id
                LIMIT 1
                """
            ),
            {"month_start": month_start, "month_end": month_end},
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    inserted = await db.execute(
        text(
            """
            INSERT INTO a_class.sales_targets (
                target_name,
                target_type,
                scope_type,
                period_start,
                period_end,
                status,
                created_by,
                created_at,
                updated_at
            )
            VALUES (
                :target_name,
                'shop',
                'shop',
                :period_start,
                :period_end,
                'active',
                'config_management',
                NOW(),
                NOW()
            )
            RETURNING id
            """
        ),
        {
            "target_name": f"{year_month} 店铺销售目标",
            "period_start": month_start,
            "period_end": month_end,
        },
    )
    return int(inserted.scalar_one())


async def _find_shop_breakdown_id(
    db: AsyncSession,
    year_month: str,
    platform_code: str,
    shop_id: str,
) -> Optional[int]:
    """按 (月份, 平台, 店铺) 找已有的「店铺 × 月」档位行 id。"""
    row = (
        await db.execute(
            text(
                f"""
                SELECT tb.id
                FROM a_class.target_breakdown tb
                JOIN a_class.sales_targets st ON st.id = tb.target_id
                WHERE tb.breakdown_type = 'shop'
                  AND st.target_type = 'shop'
                  AND st.status = 'active'
                  AND tb.platform_code = :platform_code
                  AND tb.shop_id = :shop_id
                  AND {_MONTH_EXPR} = :year_month
                ORDER BY tb.id
                LIMIT 1
                """
            ),
            {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "year_month": year_month,
            },
        )
    ).scalar_one_or_none()
    return int(row) if row is not None else None


async def _refresh_parent_totals(db: AsyncSession, target_id: int) -> None:
    """父目标的公司级合计 = 其店铺档位行之和（只在存在店铺档位行时才重算）。"""
    await db.execute(
        text(
            """
            UPDATE a_class.sales_targets st
            SET target_amount = COALESCE((
                    SELECT SUM(tb.target_amount)
                    FROM a_class.target_breakdown tb
                    WHERE tb.target_id = st.id
                      AND tb.breakdown_type = 'shop'
                ), 0),
                target_quantity = COALESCE((
                    SELECT SUM(tb.target_quantity)
                    FROM a_class.target_breakdown tb
                    WHERE tb.target_id = st.id
                      AND tb.breakdown_type = 'shop'
                ), 0),
                updated_at = NOW()
            WHERE st.id = :target_id
              AND EXISTS (
                    SELECT 1
                    FROM a_class.target_breakdown tb
                    WHERE tb.target_id = st.id
                      AND tb.breakdown_type = 'shop'
              )
            """
        ),
        {"target_id": target_id},
    )


async def _load_shop_target_row(
    db: AsyncSession, breakdown_id: int
) -> Optional[tuple]:
    """按档位行 id 读出响应所需的字段。"""
    return (
        await db.execute(
            text(
                f"""
                SELECT tb.id,
                       tb.shop_id,
                       {_MONTH_EXPR} AS year_month,
                       tb.target_amount,
                       tb.target_quantity,
                       tb.created_at,
                       tb.target_id
                FROM a_class.target_breakdown tb
                JOIN a_class.sales_targets st ON st.id = tb.target_id
                WHERE tb.id = :breakdown_id
                """
            ),
            {"breakdown_id": breakdown_id},
        )
    ).fetchone()


@router.get("/sales-targets", response_model=List[SalesTargetResponse])
async def list_sales_targets(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="月份筛选(YYYY-MM)"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取销售目标列表（a_class.target_breakdown 店铺 × 月档位）"""
    try:
        result = await db.execute(
            text(
                f"""
                SELECT tb.id,
                       tb.shop_id,
                       {_MONTH_EXPR} AS year_month,
                       tb.target_amount,
                       tb.target_quantity,
                       tb.created_at
                FROM a_class.target_breakdown tb
                JOIN a_class.sales_targets st ON st.id = tb.target_id
                WHERE tb.breakdown_type = 'shop'
                  AND st.target_type = 'shop'
                  AND st.status = 'active'
                  AND (CAST(:shop_id AS text) IS NULL OR tb.shop_id = :shop_id)
                  AND (CAST(:year_month AS text) IS NULL OR {_MONTH_EXPR} = :year_month)
                ORDER BY {_MONTH_EXPR} DESC, tb.shop_id
                """
            ),
            {"shop_id": shop_id, "year_month": year_month},
        )
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
            created_by=None,
        )
        for row in rows
    ]


@router.post("/sales-targets", response_model=SalesTargetResponse, status_code=201)
async def create_sales_target(
    target: SalesTargetCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建销售目标（a_class.target_breakdown 店铺 × 月档位，upsert）"""
    try:
        year_month = target.year_month
        month_start, month_end = _month_range(year_month)

        platform_code = await _resolve_platform_code(db, target.shop_id)
        if not platform_code:
            raise HTTPException(
                status_code=400,
                detail=f"无法识别店铺 {target.shop_id} 所属平台，无法写入目标",
            )

        breakdown_id = await _find_shop_breakdown_id(
            db, year_month, platform_code, target.shop_id
        )
        if breakdown_id is None:
            target_id = await _resolve_month_target_id(
                db, year_month, month_start, month_end
            )
            inserted = await db.execute(
                text(
                    """
                    INSERT INTO a_class.target_breakdown (
                        target_id,
                        breakdown_type,
                        platform_code,
                        shop_id,
                        period_start,
                        period_end,
                        period_label,
                        target_amount,
                        target_quantity,
                        achieved_amount,
                        achieved_quantity,
                        achievement_rate,
                        target_profit_amount,
                        achieved_profit_amount,
                        target_profit_basis_amount
                    )
                    VALUES (
                        :target_id,
                        'shop',
                        :platform_code,
                        :shop_id,
                        :period_start,
                        :period_end,
                        :year_month,
                        :target_sales_amount,
                        :target_order_count,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0
                    )
                    RETURNING id
                    """
                ),
                {
                    "target_id": target_id,
                    "platform_code": platform_code,
                    "shop_id": target.shop_id,
                    "period_start": month_start,
                    "period_end": month_end,
                    "year_month": year_month,
                    "target_sales_amount": target.target_sales_amount,
                    "target_order_count": target.target_order_count,
                },
            )
            breakdown_id = int(inserted.scalar_one())
            await _refresh_parent_totals(db, target_id)
        else:
            updated = await db.execute(
                text(
                    """
                    UPDATE a_class.target_breakdown
                    SET target_amount = :target_sales_amount,
                        target_quantity = :target_order_count,
                        updated_at = NOW()
                    WHERE id = :breakdown_id
                    RETURNING target_id
                    """
                ),
                {
                    "breakdown_id": breakdown_id,
                    "target_sales_amount": target.target_sales_amount,
                    "target_order_count": target.target_order_count,
                },
            )
            parent_target_id = updated.scalar_one_or_none()
            if parent_target_id is not None:
                await _refresh_parent_totals(db, int(parent_target_id))

        await db.commit()

        row = await _load_shop_target_row(db, breakdown_id)
        if not row:
            raise HTTPException(status_code=500, detail="创建成功但查询失败")
        return SalesTargetResponse(
            id=row[0],
            shop_id=str(row[1]),
            year_month=str(row[2]),
            target_sales_amount=float(row[3]),
            target_order_count=int(row[4]) if row[4] is not None else 0,
            created_at=row[5],
            created_by=None,
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
    """更新销售目标（a_class.target_breakdown 店铺 × 月档位）"""
    try:
        updates = []
        params = {"breakdown_id": target_id}
        if target.target_sales_amount is not None:
            updates.append("target_amount = :target_sales_amount")
            params["target_sales_amount"] = target.target_sales_amount
        if target.target_order_count is not None:
            updates.append("target_quantity = :target_order_count")
            params["target_order_count"] = target.target_order_count
        if not updates:
            raise HTTPException(status_code=400, detail="没有提供更新字段")
        updates.append("updated_at = NOW()")

        updated = await db.execute(
            text(
                f"""
                UPDATE a_class.target_breakdown
                SET {", ".join(updates)}
                WHERE id = :breakdown_id
                RETURNING target_id
                """
            ),
            params,
        )
        parent_target_id = updated.scalar_one_or_none()
        if parent_target_id is None:
            await db.rollback()
            raise HTTPException(status_code=404, detail="销售目标不存在")
        await _refresh_parent_totals(db, int(parent_target_id))
        await db.commit()

        row = await _load_shop_target_row(db, target_id)
        if not row:
            raise HTTPException(status_code=404, detail="销售目标不存在")
        return SalesTargetResponse(
            id=row[0],
            shop_id=str(row[1]),
            year_month=str(row[2]),
            target_sales_amount=float(row[3]),
            target_order_count=int(row[4]) if row[4] is not None else 0,
            created_at=row[5],
            created_by=None,
        )
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
    """删除销售目标（a_class.target_breakdown 店铺 × 月档位）"""
    try:
        result = await db.execute(
            text(
                """
                DELETE FROM a_class.target_breakdown
                WHERE id = :breakdown_id
                RETURNING target_id
                """
            ),
            {"breakdown_id": target_id},
        )
        parent_target_id = result.scalar_one_or_none()
        if parent_target_id is None:
            await db.rollback()
            raise HTTPException(status_code=404, detail="销售目标不存在")
        await _refresh_parent_totals(db, int(parent_target_id))
        await db.commit()
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
    """复制上月目标到指定月份（a_class.target_breakdown 店铺 × 月档位）"""
    try:
        month_start, month_end = _month_range(target_month)
        last_month_date = month_start - relativedelta(months=1)
        last_month = last_month_date.strftime("%Y-%m")

        source_rows = (
            await db.execute(
                text(
                    f"""
                    SELECT tb.platform_code,
                           tb.shop_id,
                           tb.target_amount,
                           tb.target_quantity
                    FROM a_class.target_breakdown tb
                    JOIN a_class.sales_targets st ON st.id = tb.target_id
                    WHERE tb.breakdown_type = 'shop'
                      AND st.target_type = 'shop'
                      AND st.status = 'active'
                      AND {_MONTH_EXPR} = :last_month
                    """
                ),
                {"last_month": last_month},
            )
        ).fetchall()

        if not source_rows:
            return {
                "success": True,
                "message": f"上月({last_month})无数据",
                "copied_count": 0,
                "skipped_count": 0,
            }

        target_id = await _resolve_month_target_id(
            db, target_month, month_start, month_end
        )
        copied, skipped = 0, 0
        for platform_code, shop_id, amount, quantity in source_rows:
            existing_id = await _find_shop_breakdown_id(
                db, target_month, str(platform_code), str(shop_id)
            )
            if existing_id is not None:
                skipped += 1
                continue
            try:
                await db.execute(
                    text(
                        """
                        INSERT INTO a_class.target_breakdown (
                            target_id,
                            breakdown_type,
                            platform_code,
                            shop_id,
                            period_start,
                            period_end,
                            period_label,
                            target_amount,
                            target_quantity,
                            achieved_amount,
                            achieved_quantity,
                            achievement_rate,
                            target_profit_amount,
                            achieved_profit_amount,
                            target_profit_basis_amount
                        )
                        VALUES (
                            :target_id,
                            'shop',
                            :platform_code,
                            :shop_id,
                            :period_start,
                            :period_end,
                            :target_month,
                            :amount,
                            :quantity,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0
                        )
                        """
                    ),
                    {
                        "target_id": target_id,
                        "platform_code": platform_code,
                        "shop_id": shop_id,
                        "period_start": month_start,
                        "period_end": month_end,
                        "target_month": target_month,
                        "amount": amount,
                        "quantity": quantity,
                    },
                )
                copied += 1
            except Exception:
                await db.rollback()
                skipped += 1

        await _refresh_parent_totals(db, target_id)
        await db.commit()
        return {
            "success": True,
            "message": f"已从{last_month}复制到{target_month}",
            "copied_count": copied,
            "skipped_count": skipped,
            "total_count": len(source_rows),
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"复制上月销售目标失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


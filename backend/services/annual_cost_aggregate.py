"""
年度成本聚合服务 - add-orders-model-cost-and-annual-kpi

按 docs/COST_DATA_SOURCES_AND_DEFINITIONS.md 口径：
- A 类：a_class.operating_costs 四列之和（租金、工资、水电费、其他成本）
- B 类：订单事实表 monthly 粒度，采购金额 + 仓库操作费 + 平台费用
- 总成本 = A + B；GMV = paid_amount 汇总
- 比率：成本产出比、ROI、毛利率、净利率；分母为 0 时返回 None（前端展示 N/A）
- 按店铺下钻：A 类按「店铺ID」、B 类按 (platform_code, shop_id) 聚合；约定 店铺ID = 'platform_code|shop_id' 时与订单侧一致。

B 类解析规则与 docs/AMOUNT_QUANTITY_PARSING_CONVENTION.md 及 Orders 模型一致（保留符号，正则 [^0-9.-]），
待改为通过 Metabase Question（annual_summary_kpi / annual_summary_by_shop / annual_summary_trend）获取后删除此处对 raw_data 的解析。
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


async def get_annual_cost_aggregate(
    db: AsyncSession,
    granularity: str,
    period: str,
) -> Dict[str, Any]:
    """
    按周期聚合 A 类 + B 类成本与 GMV，并计算比率。
    granularity: monthly | yearly
    period: 月度 YYYY-MM | 年度 YYYY
    返回: total_cost_a, total_cost_b, total_cost, gmv, cost_to_revenue_ratio, roi, gross_margin, net_margin
    分母为 0 时比率为 None。
    """
    if granularity == "monthly":
        period_start = f"{period}-01"
        # 下月首日
        y, m = int(period[:4]), int(period[5:7])
        if m == 12:
            period_end = f"{y + 1}-01-01"
        else:
            period_end = f"{y}-{m + 1:02d}-01"
        year_month_filter = f'"{period}"'
        year_month_like = None
    else:
        period_start = f"{period}-01-01"
        period_end = f"{int(period) + 1}-01-01"
        year_month_filter = None
        year_month_like = f"{period}-%"

    # A 类：operating_costs 四列之和（表使用中文字段名）
    if year_month_filter:
        a_sql = text(
            """
            SELECT COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" = :ym
            """
        )
        a_params = {"ym": period[:7]}
    else:
        a_sql = text(
            """
            SELECT COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" LIKE :ym_prefix
            """
        )
        a_params = {"ym_prefix": year_month_like}

    try:
        a_row = (await db.execute(a_sql, a_params)).fetchone()
        total_a = _safe_float(a_row[0] if a_row else 0)
    except Exception as e:
        logger.warning(f"年度成本聚合 A 类查询失败: {e}")
        total_a = 0.0

    # B 类：三张月度订单表 raw_data 抽取并汇总（与 Orders 模型约定一致：保留符号，[^0-9.-]）
    b_sql = text(
        """
        WITH u AS (
            SELECT raw_data, period_start_date FROM b_class.fact_shopee_orders_monthly
            UNION ALL
            SELECT raw_data, period_start_date FROM b_class.fact_tiktok_orders_monthly
            UNION ALL
            SELECT raw_data, period_start_date FROM b_class.fact_miaoshou_orders_monthly
        )
        SELECT
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'采购金额', raw_data->>'采购价', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS purchase_amount,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'仓库操作费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS warehouse_operation_fee,
            (SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'运费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'推广费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台佣金', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台扣费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'代金券', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'服务费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
            ) AS platform_fees,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS paid_amount
        FROM u
        WHERE period_start_date >= :period_start AND period_start_date < :period_end
        """
    )
    b_params = {"period_start": period_start, "period_end": period_end}

    try:
        b_row = (await db.execute(b_sql, b_params)).fetchone()
        if b_row:
            purchase_amount = _safe_float(b_row[0])
            warehouse_operation_fee = _safe_float(b_row[1])
            platform_fees = _safe_float(b_row[2]) if b_row[2] is not None else 0.0
            paid_amount = _safe_float(b_row[3])
        else:
            purchase_amount = warehouse_operation_fee = platform_fees = paid_amount = 0.0
    except Exception as e:
        logger.warning(f"年度成本聚合 B 类查询失败: {e}")
        purchase_amount = warehouse_operation_fee = platform_fees = paid_amount = 0.0

    total_b = purchase_amount + warehouse_operation_fee + platform_fees
    total_cost = total_a + total_b
    gmv = paid_amount

    # 比率（分母为 0 时返回 None，前端展示 N/A）
    cost_to_revenue_ratio = (total_cost / gmv) if gmv and gmv != 0 else None
    roi = ((gmv - total_cost) / total_cost) if total_cost and total_cost != 0 else None
    gross_margin = ((gmv - purchase_amount) / gmv) if gmv and gmv != 0 else None
    net_margin = ((gmv - total_cost) / gmv) if gmv and gmv != 0 else None

    return {
        "total_cost_a": total_a,
        "total_cost_b": total_b,
        "total_cost": total_cost,
        "gmv": gmv,
        "cost_to_revenue_ratio": cost_to_revenue_ratio,
        "roi": roi,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
    }


def _shop_key(platform_code: str, shop_id: Optional[str]) -> str:
    """订单侧店铺键，与 operating_costs.店铺ID 约定一致时可用于 JOIN。"""
    if not shop_id:
        return platform_code or ""
    return f"{platform_code or ''}|{shop_id}"


async def get_annual_cost_aggregate_by_shop(
    db: AsyncSession,
    granularity: str,
    period: str,
) -> List[Dict[str, Any]]:
    """
    按店铺聚合 A 类 + B 类成本与 GMV（2.3 按店铺下钻）。
    约定：operating_costs.店铺ID 填写为 'platform_code|shop_id' 时与订单侧 (platform_code, shop_id) 一致。
    返回列表，每项: shop_key, total_cost_a, total_cost_b, total_cost, gmv, cost_to_revenue_ratio, roi, gross_margin, net_margin
    """
    if granularity == "monthly":
        period_start = f"{period}-01"
        y, m = int(period[:4]), int(period[5:7])
        period_end = f"{y + 1}-01-01" if m == 12 else f"{y}-{m + 1:02d}-01"
        year_month_filter = f'"{period}"'
        year_month_like = None
    else:
        period_start = f"{period}-01-01"
        period_end = f"{int(period) + 1}-01-01"
        year_month_filter = None
        year_month_like = f"{period}-%"

    # A 类按店铺ID汇总（中文字段名）
    if year_month_filter:
        a_sql = text(
            """
            SELECT "店铺ID" AS shop_key,
                   COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" = :ym
            GROUP BY "店铺ID"
            """
        )
        a_params = {"ym": period[:7]}
    else:
        a_sql = text(
            """
            SELECT "店铺ID" AS shop_key,
                   COALESCE(SUM("租金" + "工资" + "水电费" + "其他成本"), 0) AS total_a
            FROM a_class.operating_costs
            WHERE "年月" LIKE :ym_prefix
            GROUP BY "店铺ID"
            """
        )
        a_params = {"ym_prefix": year_month_like}

    a_by_shop: Dict[str, float] = {}
    try:
        a_rows = (await db.execute(a_sql, a_params)).fetchall()
        for row in a_rows or []:
            a_by_shop[str(row[0]) or ""] = _safe_float(row[1])
    except Exception as e:
        logger.warning(f"年度成本按店铺聚合 A 类查询失败: {e}")

    # B 类按 (platform_code, shop_id) 汇总（解析与 Orders 模型约定一致：保留符号，[^0-9.-]）
    b_sql = text(
        """
        WITH u AS (
            SELECT 'shopee' AS platform_code, shop_id, raw_data, period_start_date
            FROM b_class.fact_shopee_orders_monthly
            UNION ALL
            SELECT 'tiktok', shop_id, raw_data, period_start_date FROM b_class.fact_tiktok_orders_monthly
            UNION ALL
            SELECT 'miaoshou', shop_id, raw_data, period_start_date FROM b_class.fact_miaoshou_orders_monthly
        )
        SELECT
            platform_code,
            COALESCE(shop_id, '') AS shop_id,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'采购金额', raw_data->>'采购价', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS purchase_amount,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'仓库操作费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS warehouse_operation_fee,
            (SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'运费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'推广费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台佣金', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'平台扣费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'代金券', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
             + SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'服务费', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0))
            ) AS platform_fees,
            SUM(COALESCE(NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric, 0)) AS paid_amount
        FROM u
        WHERE period_start_date >= :period_start AND period_start_date < :period_end
        GROUP BY platform_code, shop_id
        """
    )
    b_params = {"period_start": period_start, "period_end": period_end}

    b_by_shop: Dict[str, Dict[str, Any]] = {}
    try:
        b_rows = (await db.execute(b_sql, b_params)).fetchall()
        for row in b_rows or []:
            pc, sid = (row[0] or ""), (row[1] or "")
            key = _shop_key(pc, sid)
            purchase = _safe_float(row[2])
            warehouse = _safe_float(row[3])
            platform_fees = _safe_float(row[4]) if row[4] is not None else 0.0
            paid = _safe_float(row[5])
            total_b = purchase + warehouse + platform_fees
            cost_to_revenue = (total_b / paid) if paid and paid != 0 else None
            roi = ((paid - total_b) / total_b) if total_b and total_b != 0 else None
            gross_margin = ((paid - purchase) / paid) if paid and paid != 0 else None
            net_margin = ((paid - total_b) / paid) if paid and paid != 0 else None
            b_by_shop[key] = {
                "total_cost_b": total_b,
                "purchase_amount": purchase,
                "gmv": paid,
                "cost_to_revenue_ratio": cost_to_revenue,
                "roi": roi,
                "gross_margin": gross_margin,
                "net_margin": net_margin,
            }
    except Exception as e:
        logger.warning(f"年度成本按店铺聚合 B 类查询失败: {e}")

    # 合并所有 shop_key（A 的 店铺ID + B 的 platform_code|shop_id）
    all_keys = set(a_by_shop) | set(b_by_shop)
    result: List[Dict[str, Any]] = []
    for shop_key in sorted(all_keys):
        total_a = a_by_shop.get(shop_key, 0.0)
        b_row = b_by_shop.get(shop_key) or {}
        total_b = b_row.get("total_cost_b", 0.0)
        gmv = b_row.get("gmv", 0.0)
        total_cost = total_a + total_b
        cost_to_revenue_ratio = (total_cost / gmv) if gmv and gmv != 0 else None
        roi = ((gmv - total_cost) / total_cost) if total_cost and total_cost != 0 else None
        gross_margin = ((gmv - b_row.get("purchase_amount", 0)) / gmv) if gmv and gmv != 0 else None
        net_margin = ((gmv - total_cost) / gmv) if gmv and gmv != 0 else None
        result.append({
            "shop_key": shop_key,
            "total_cost_a": total_a,
            "total_cost_b": total_b,
            "total_cost": total_cost,
            "gmv": gmv,
            "cost_to_revenue_ratio": cost_to_revenue_ratio,
            "roi": roi,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
        })
    return result

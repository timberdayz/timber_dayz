"""SKU 级历史成交价带（阶段 4 工具 4 · 偏差校验的数据来源）。

基准售价填错的最典型形态是「多打了一个零」（620 写成 62 的反面）。
要发现它，就得拿基准售价去比这个 SKU **实际卖出去过的价格**。

这一层提供的就是那个「实际卖出去的价格」：每个 SKU 的历史成交价中位数。

口径（写在这里是因为它很容易被第二个人重新想一遍）
--------------------------------------------------

**成交价 = 买家实付金额（人民币）/ 数量**

- Shopee 取 ``raw_data->>'买家支付(RMB)'``，TikTok 取 ``raw_data->>'买家实付金额(RMB)'``；
  两个键都取不到就跳过该行（宁可少样本，不可猜）。
- 用 **CNY**，与基准售价同币种。

  为什么不用语义视图的 ``order_original_amount``：那一列是**平台币种**（MYR）
  而且**含运费**。实测同一行的 ``订单原始金额`` = 264.0 而
  ``订单原始金额(RMB)`` = 28.17 —— 差 9 倍，差额是运费补贴与折扣。
  直接拿它当单价，中位数会被抬到 2~3 倍，偏差校验会变成「全线报警」的假阳性机器。
  用 ``(RMB)`` 版本还顺带绕开了汇率表（``core.dim_exchange_rates`` 的汇率是
  2025-11-01 的手工种子值，已经陈旧近一年）。

**只统计「已完成」的订单**：``已关闭``（取消）占 10%~14%、``待发货``/``已发货``/``退款中``
还没结算，混进来会把中位数拉偏。

**映射用 ``core.bridge_erp_sku_keys``**：``source_system='miaoshou'`` 且
``source_key_type='product_sku'`` 的那一组，是「平台商品键 → ERP SKU」的别名表。
实测订单侧 31,199 行商品键 **100%** 命中，且没有任何 ``source_key`` 对应多个 SKU
（无歧义）—— 这就是方案 §6.1 工具 4 说「补这个 join 即可得到 SKU 级成交价分布」的那张表。

  ⚠️ 别按 ``source_platform`` 一起 join：别名表里的 ``source_platform`` 是字面量
  ``'miaoshou'``（来源系统），不是 shopee/tiktok —— 加上这个条件会命中 **0 行**。

**窗口相对「数据里最新的那一天」而不是今天**：采集管道可能滞后，
按「今天往前 180 天」取窗口会取到空集。按数据最新的日期取，
窗口永远落在真正有数据的那一段上。

⚠️ 这一层**慢**：语义视图里有店铺身份解析的 LATERAL join，单 SKU 查询就要 20 秒。
所以它只用于**批量巡检**（一次扫全部 SKU），不进列表接口、不进交互式预览。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


#: 成交价带的统计窗口（天）。按数据最新日期往前推。
DEFAULT_LOOKBACK_DAYS = 180

#: 少于这么多成交行就不给中位数 —— 一两单说明不了「这个品卖多少钱」。
DEFAULT_MIN_SAMPLE_SIZE = 3

#: 只统计这些状态的订单。
#:
#: - ``已完成``：结算完成的真成交。
#: - ``已发货``：已发货但未结算的也是真订单，**算进来**（否则窗口会被压到很老的数据上）。
#
#: 排除：``已关闭``（取消）、``待发货``、``退款中``、``取消中``。
_INCLUDED_ORDER_STATUSES = ("已完成", "已发货")


#: 成交价取数 SQL。
#:
#: ⚠️ ``::`` 的优先级高于 ``->>``，取 raw_data 的值**必须**加括号，
#:    否则 PostgreSQL 会解析成 ``raw_data ->> ('key'::numeric)`` 直接报错。
#: ⚠️ 金额字段可能是空串或非数字（导出里常见），用正则守卫后再转 numeric。
#: ⚠️ 列表参数（订单状态、SKU 集合）一律用 SQLAlchemy 的 ``expanding=True``
#:    绑定渲染成 ``IN ('已完成', '已发货')``。
#:    **不要写成 ``IN :param``**：PostgreSQL 的语法要求 ``IN`` 后面必须跟
#:    括号里的表达式列表，``IN $1`` 直接是语法错误（asyncpg 下必炸），
#:    而 ``= ANY($1)`` 虽然语法对，但参数类型在 ``text()`` 里无法推断，
#:    换个驱动/后端就可能变成另一种错。``expanding`` 是唯一两种都安全的写法。
_BAND_SQL = """
WITH b AS (
    SELECT source_key, sku_id
      FROM core.bridge_erp_sku_keys
     WHERE active = true
       AND effective_to IS NULL
       AND source_system = 'miaoshou'
       AND source_key_type = 'product_sku'
       {sku_filter}
),
base AS (
    SELECT b.sku_id,
           o.metric_date,
           o.product_quantity AS qty,
           COALESCE(
               CASE WHEN (o.raw_data->>'买家支付(RMB)') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                    THEN (o.raw_data->>'买家支付(RMB)')::numeric END,
               CASE WHEN (o.raw_data->>'买家实付金额(RMB)') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                    THEN (o.raw_data->>'买家实付金额(RMB)')::numeric END
           ) AS paid_cny
      FROM semantic.fact_orders_atomic o
      JOIN b ON b.source_key = NULLIF(BTRIM(o.product_sku), '')
     WHERE o.product_quantity > 0
       AND COALESCE(o.raw_data->>'订单状态', '') IN :statuses
),
-- ⚠️ CTE 不能叫 ``window``：那是 PostgreSQL 的保留字（窗口函数帧的关键字），
--    拿来当 CTE 名会直接报 "syntax error at or near window"。
date_window AS (
    SELECT max(metric_date) AS max_date FROM base
),
selected AS (
    SELECT base.sku_id, base.paid_cny, base.qty
      FROM base, date_window
     WHERE date_window.max_date IS NOT NULL
       AND base.metric_date >= date_window.max_date - make_interval(days => :lookback_days)
)
SELECT sku_id,
       count(*) AS sample_size,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY paid_cny / qty) AS median_price,
       (SELECT max_date FROM date_window) AS window_end
  FROM selected
 WHERE paid_cny IS NOT NULL AND paid_cny > 0
 GROUP BY sku_id
"""


async def load_transaction_price_bands(
    db: AsyncSession,
    sku_ids: Optional[Iterable[int]] = None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> dict[int, dict]:
    """算一批 SKU 的历史成交价带。

    返回 ``{sku_id: {"median_price": Decimal, "sample_size": int,
    "window_start": date, "window_end": date}}``。

    ⚠️ **样本不足的 SKU 不会出现在结果里** —— 调用方必须把「没出现」理解为
    「算不出」，而不是「没有偏差」。这个区分是本模块存在的意义。

    ⚠️ 这一层慢（语义视图的店铺身份解析），一次调用扫全部 SKU 最划算；
    逐个 SKU 调用会重复付这条成本。
    """
    ids = [int(value) for value in (sku_ids or []) if value is not None]
    params: dict = {
        "lookback_days": int(lookback_days),
        "statuses": list(_INCLUDED_ORDER_STATUSES),
    }
    # ⚠️ expanding=True：把列表渲染成 `IN ('已完成', '已发货')` 这种字面量列表。
    #    见 _BAND_SQL 上面的说明 —— 写成 `IN :statuses` 在 PostgreSQL 上是语法错误。
    statement = text(_BAND_SQL.format(sku_filter="")).bindparams(
        bindparam("statuses", expanding=True)
    )
    if ids:
        statement = text(
            _BAND_SQL.format(sku_filter="AND sku_id IN :sku_ids")
        ).bindparams(
            bindparam("statuses", expanding=True),
            bindparam("sku_ids", expanding=True),
        )
        params["sku_ids"] = ids

    rows = (await db.execute(statement, params)).mappings().all()

    bands: dict[int, dict] = {}
    for row in rows:
        sample_size = int(row["sample_size"] or 0)
        if sample_size < min_sample_size:
            continue
        median = row["median_price"]
        if median is None:
            continue
        window_end = row["window_end"]
        window_start = None
        if window_end is not None:
            window_start = window_end - timedelta(days=lookback_days)
        bands[int(row["sku_id"])] = {
            # ⚠️ ``percentile_cont`` 返回 double precision，直接 ``Decimal(float)`` 会把
            #    二进制误差原样带进来（126.2 ⇒ 126.2000000000000028421709430404007...），
            #    页面会显示一串天书。走 ``str()`` 再转，十进制表示就干净了。
            "median_price": (
                median if isinstance(median, Decimal) else Decimal(str(median))
            ),
            "sample_size": sample_size,
            "window_start": window_start,
            "window_end": window_end,
        }
    return bands


def band_window(
    *, lookback_days: int = DEFAULT_LOOKBACK_DAYS, reference: Optional[date] = None
) -> tuple[date, date]:
    """统计窗口的起止日期（供展示用）。

    ⚠️ 实际窗口由**数据里最新的一天**决定（见模块说明），所以这里的起止只是
    「按参考日推算」的近似 —— 真正的窗口要等 SQL 跑完才知道。
    """
    end = reference or date.today()
    return end - timedelta(days=lookback_days), end

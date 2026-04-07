-- =====================================================
-- Question: hr_shop_monthly_metrics
-- 人员店铺归属 - 店铺月度销售额与利润统计
-- =====================================================
-- 用途：按店铺汇总当月销售额、利润、目标达成率（筛选粒度为月度）
-- 数据源：{{MODEL:Orders Model}}、a_class.target_breakdown、a_class.sales_targets
-- 参数：
--   {{month}} - 月份（必填，格式：YYYY-MM-DD，传入月初日期，如 2025-09-01）
-- 返回：platform_code, shop_id, shop_name, monthly_sales, monthly_profit, achievement_rate
-- 与业务概览数据对比约定一致：销售额=paid_amount，利润=profit
-- =====================================================

with
params as (
  select {{month}}::date as target_date
),

period_scope as (
  select
    (select target_date from params) as target_date,
    date_trunc('month', (select target_date from params))::date as period_start,
    (date_trunc('month', (select target_date from params)) + interval '1 month' - interval '1 day')::date as period_end
),

-- 行级数据：与 business_overview_comparison 一致，月度筛选
filtered_data as (
  select
    o.platform_code,
    o.shop_id,
    o.order_id,
    o.paid_amount,
    o.profit
  from {{MODEL:Orders Model}} o
  cross join period_scope s
  where (
      (o.granularity = 'monthly' and o.metric_date >= s.period_start and o.metric_date <= s.period_end)
      or (o.granularity = 'daily' and o.metric_date >= s.period_start and o.metric_date <= s.period_end)
    )
),

-- 店铺目标：a_class.target_breakdown（shop/shop_time）
shop_targets as (
  select
    tb.platform_code,
    lower(coalesce(nullif(trim(tb.shop_id::text), ''), 'unknown')) as shop_id_key,
    coalesce(sum(tb.target_amount), 0) as target_amount
  from a_class.target_breakdown tb
  inner join a_class.sales_targets st on st.id = tb.target_id and st.status = 'active'
  cross join period_scope s
  where tb.breakdown_type in ('shop', 'shop_time')
    and tb.platform_code is not null
    and tb.period_start <= s.period_end and tb.period_end >= s.period_start
  group by tb.platform_code, lower(coalesce(nullif(trim(tb.shop_id::text), ''), 'unknown'))
),

-- 店铺聚合：销售额、利润
shop_agg as (
  select
    platform_code,
    coalesce(nullif(lower(trim(shop_id::text)), ''), 'unknown') as shop_id_key,
    coalesce(sum(paid_amount), 0) as monthly_sales,
    coalesce(sum(profit), 0) as monthly_profit,
    max(shop_id)::text as shop_id_display
  from filtered_data
  group by platform_code, coalesce(nullif(lower(trim(shop_id::text)), ''), 'unknown')
)

select
  a.platform_code,
  case when a.shop_id_key in ('unknown', 'none') then 'unknown店铺' else coalesce(a.shop_id_display, 'unknown店铺') end as shop_name,
  a.shop_id_key as shop_id,
  round(a.monthly_sales::numeric, 2) as monthly_sales,
  round(a.monthly_profit::numeric, 2) as monthly_profit,
  coalesce(t.target_amount, 0) as target_amount,
  case when coalesce(t.target_amount, 0) > 0 then round((a.monthly_sales::numeric * 100 / t.target_amount)::numeric, 4) else null end as achievement_rate
from shop_agg a
left join shop_targets t on t.platform_code = a.platform_code and t.shop_id_key = a.shop_id_key
order by a.platform_code, a.shop_id_key

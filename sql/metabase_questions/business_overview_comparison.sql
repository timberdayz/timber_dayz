-- =====================================================
-- Question: business_overview_comparison
-- 业务概览 - 数据对比（当期 / 上期 / 平均 / 环比）
-- =====================================================
-- 用途：提供日/周/月度数据对比，单行多列供前端表格展示
-- 数据源：
--   - {{MODEL:Orders Model}}：销售额、订单数、利润、客单价等
--   - {{MODEL:Analytics Model}}：访客数（客流量）、转化率
--   - public.sales_targets：用户设定的销售目标（显式 schema 确保 Metabase 解析正确）
-- 参数：
--   {{granularity}} - 粒度（daily/weekly/monthly）
--   {{date}} - 对比日期（必填，YYYY-MM-DD）
--   {{platform}} - 平台筛选（可选）
-- 返回：单行，列名 xxx_today / xxx_yesterday / xxx_average / xxx_change / target_xxx
-- v4.21.0 优化：
--   1. 当期/上期统一用 metric_date 范围匹配（周=周一～周日，月=1～月末）
--   2. 平均：日度=本月平均(本月数据/本月天数)，周度=本周数据/7，月度=本月数据/本月天数
--   3. 转化率本期只算一个比率；日度筛选时平均列按本月平均实现
--   4. 集成用户设定的销售目标
-- =====================================================

with
params as (
  select
    {{date}}::date as target_date,
    {{granularity}} as granularity
),

-- 当期、上期、平均用时间范围
period_scope as (
  select
    (select target_date from params) as target_date,
    (select granularity from params) as gran,
    case (select granularity from params)
      when 'daily' then (select target_date from params)
      when 'weekly' then (date_trunc('week', (select target_date from params))::date)
      when 'monthly' then (date_trunc('month', (select target_date from params))::date)
    end as current_period_start,
    case (select granularity from params)
      when 'daily' then (select target_date from params)
      when 'weekly' then (date_trunc('week', (select target_date from params))::date + 6)
      when 'monthly' then (date_trunc('month', (select target_date from params))::date + interval '1 month' - interval '1 day')
    end::date as current_period_end,
    case (select granularity from params)
      when 'daily' then (select target_date from params) - 1
      when 'weekly' then (date_trunc('week', (select target_date from params))::date - 7)
      when 'monthly' then (date_trunc('month', (select target_date from params))::date - interval '1 month')::date
    end as prev_period_start,
    case (select granularity from params)
      when 'daily' then (select target_date from params) - 1
      when 'weekly' then (date_trunc('week', (select target_date from params))::date - 1)
      when 'monthly' then (date_trunc('month', (select target_date from params))::date - interval '1 month' + interval '1 month' - interval '1 day')::date
    end as prev_period_end
),

-- =====================================================
-- 当期订单汇总
-- 优化：统一使用 metric_date 范围匹配（period_start_date/period_end_date 存的是订单日期，非周期范围）
-- =====================================================
current_orders as (
  select
    coalesce(sum(o.paid_amount), 0) as sales,
    coalesce(sum(o.product_quantity), 0) as orders_cnt,
    coalesce(sum(o.profit), 0) as profit_val,
    count(distinct o.order_id) as order_count
  from {{MODEL:Orders Model}} o
  cross join period_scope s
  where (
      -- 日度：精确匹配 target_date
      (s.gran = 'daily' and o.granularity = 'daily' and o.metric_date = s.target_date)
      -- 周度：metric_date 落在当周范围内
      or (s.gran = 'weekly' and o.granularity = 'weekly'
          and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
      -- 月度：metric_date 落在当月范围内
      or (s.gran = 'monthly' and o.granularity = 'monthly'
          and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
      -- 月度回退：无月度预聚合时用日度数据汇总当月
      or (s.gran = 'monthly' and o.granularity = 'daily'
          and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
    )
    [[and o.platform_code = {{platform}}]]
),

-- =====================================================
-- 上期订单汇总
-- 优化：统一使用 metric_date 范围匹配
-- =====================================================
prev_orders as (
  select
    coalesce(sum(o.paid_amount), 0) as sales,
    coalesce(sum(o.product_quantity), 0) as orders_cnt,
    coalesce(sum(o.profit), 0) as profit_val,
    count(distinct o.order_id) as order_count
  from {{MODEL:Orders Model}} o
  cross join period_scope s
  where (
      -- 日度：精确匹配上一天
      (s.gran = 'daily' and o.granularity = 'daily' and o.metric_date = s.prev_period_start)
      -- 周度：metric_date 落在上周范围内
      or (s.gran = 'weekly' and o.granularity = 'weekly'
          and o.metric_date >= s.prev_period_start and o.metric_date <= s.prev_period_end)
      -- 月度：metric_date 落在上月范围内
      or (s.gran = 'monthly' and o.granularity = 'monthly'
          and o.metric_date >= s.prev_period_start and o.metric_date <= s.prev_period_end)
      -- 月度回退：无月度预聚合时用日度数据汇总上月
      or (s.gran = 'monthly' and o.granularity = 'daily'
          and o.metric_date >= s.prev_period_start and o.metric_date <= s.prev_period_end)
    )
    [[and o.platform_code = {{platform}}]]
),

-- =====================================================
-- 当期流量汇总
-- 优化：统一使用 metric_date 范围匹配
-- =====================================================
current_traffic as (
  select coalesce(sum(a.visitor_count), 0) as visitors
  from {{MODEL:Analytics Model}} a
  cross join period_scope s
  where (
      -- 日度：精确匹配 target_date
      (s.gran = 'daily' and a.granularity = 'daily' and a.metric_date = s.target_date)
      -- 周度：metric_date 落在当周范围内
      or (s.gran = 'weekly' and a.granularity = 'weekly'
          and a.metric_date >= s.current_period_start and a.metric_date <= s.current_period_end)
      -- 月度：metric_date 落在当月范围内
      or (s.gran = 'monthly' and a.granularity = 'monthly'
          and a.metric_date >= s.current_period_start and a.metric_date <= s.current_period_end)
      -- 月度回退：无月度预聚合时用日度数据汇总当月
      or (s.gran = 'monthly' and a.granularity = 'daily'
          and a.metric_date >= s.current_period_start and a.metric_date <= s.current_period_end)
    )
    [[and a.platform_code = {{platform}}]]
),

-- =====================================================
-- 上期流量汇总
-- 优化：统一使用 metric_date 范围匹配
-- =====================================================
prev_traffic as (
  select coalesce(sum(a.visitor_count), 0) as visitors
  from {{MODEL:Analytics Model}} a
  cross join period_scope s
  where (
      -- 日度：精确匹配上一天
      (s.gran = 'daily' and a.granularity = 'daily' and a.metric_date = s.prev_period_start)
      -- 周度：metric_date 落在上周范围内
      or (s.gran = 'weekly' and a.granularity = 'weekly'
          and a.metric_date >= s.prev_period_start and a.metric_date <= s.prev_period_end)
      -- 月度：metric_date 落在上月范围内
      or (s.gran = 'monthly' and a.granularity = 'monthly'
          and a.metric_date >= s.prev_period_start and a.metric_date <= s.prev_period_end)
      -- 月度回退：无月度预聚合时用日度数据汇总上月
      or (s.gran = 'monthly' and a.granularity = 'daily'
          and a.metric_date >= s.prev_period_start and a.metric_date <= s.prev_period_end)
    )
    [[and a.platform_code = {{platform}}]]
),

-- 本月天数（用于日度/月度平均除数）
month_days as (
  select
    ((date_trunc('month', (select target_date from params)) + interval '1 month' - interval '1 day')::date
     - date_trunc('month', (select target_date from params))::date + 1)::integer as days_in_month
),

-- =====================================================
-- 平均值计算（按约定简化）
-- 日度：平均 = 本月平均 = 本月日度汇总 / 本月天数
-- 周度：本周平均 = 本周数据 / 7
-- 月度：本月平均 = 本月数据 / 本月天数
-- 转化率/连带率：本期只算一个比率，不做“平均转化率”额外定义
-- =====================================================
month_daily_orders as (
  -- 本月整月日度订单汇总（仅用于日度粒度下的“本月平均”）
  select
    coalesce(sum(o.paid_amount), 0) as sales,
    coalesce(sum(o.product_quantity), 0) as orders_cnt,
    coalesce(sum(o.profit), 0) as profit_val,
    count(distinct o.order_id) as order_count
  from {{MODEL:Orders Model}} o
  cross join period_scope s
  where o.granularity = 'daily'
    and o.metric_date >= date_trunc('month', s.target_date)::date
    and o.metric_date <= (date_trunc('month', s.target_date) + interval '1 month' - interval '1 day')::date
    [[and o.platform_code = {{platform}}]]
),

month_daily_traffic as (
  select coalesce(sum(a.visitor_count), 0) as visitors
  from {{MODEL:Analytics Model}} a
  cross join period_scope s
  where a.granularity = 'daily'
    and a.metric_date >= date_trunc('month', s.target_date)::date
    and a.metric_date <= (date_trunc('month', s.target_date) + interval '1 month' - interval '1 day')::date
    [[and a.platform_code = {{platform}}]]
),

avg_orders as (
  -- 日度=本月日度汇总，周度/月度=本期汇总（本期/7 或 本期/本月天数 在最终 select 中除）
  -- order_count 用于连带率：日度=本月订单数，周/月=本期订单数
  select
    case s.gran
      when 'daily' then md.sales
      else co.sales
    end as sales,
    case s.gran
      when 'daily' then md.orders_cnt
      else co.orders_cnt
    end as orders_cnt,
    case s.gran
      when 'daily' then md.profit_val
      else co.profit_val
    end as profit_val,
    case s.gran
      when 'daily' then md.order_count
      else co.order_count
    end as order_count
  from period_scope s
  cross join current_orders co
  cross join month_daily_orders md
),

avg_traffic as (
  select
    case s.gran
      when 'daily' then mdt.visitors
      else ct.visitors
    end as visitors
  from period_scope s
  cross join current_traffic ct
  cross join month_daily_traffic mdt
),

days_elapsed as (
  -- 除数：日度=本月天数，周度=7，月度=本月天数
  select
    case (select gran from period_scope)
      when 'daily' then (select days_in_month from month_days)
      when 'weekly' then 7
      when 'monthly' then (select days_in_month from month_days)
    end as days
),

-- =====================================================
-- 用户设定的销售目标查询（按粒度分源）
-- 月度：public.sales_targets（仅存月度目标）
-- 日度/周度：a_class.target_breakdown（从日度分解表提取，周度=当周日度汇总）
-- =====================================================
user_target as (
  select
    coalesce(sum(u.target_amount), 0) as target_amount,
    coalesce(sum(u.target_quantity), 0) as target_quantity
  from (
    -- 月度：public.sales_targets 覆盖当月
    select t.target_amount, t.target_quantity
    from public.sales_targets t
    cross join period_scope s
    where s.gran = 'monthly'
      and t.status = 'active'
      and t.period_start <= s.current_period_start
      and t.period_end >= s.current_period_end
    union all
    -- 日度：a_class.target_breakdown 单日（time/shop_time 均含时间维度）
    select tb.target_amount, tb.target_quantity
    from a_class.target_breakdown tb
    inner join public.sales_targets st on st.id = tb.target_id and st.status = 'active'
    cross join period_scope s
    where s.gran = 'daily'
      and tb.breakdown_type in ('time', 'shop_time')
      and tb.period_start = s.target_date
      and tb.period_end = s.target_date
    union all
    -- 周度：a_class.target_breakdown 当周日度汇总（time/shop_time 均含时间维度）
    select tb.target_amount, tb.target_quantity
    from a_class.target_breakdown tb
    inner join public.sales_targets st on st.id = tb.target_id and st.status = 'active'
    cross join period_scope s
    where s.gran = 'weekly'
      and tb.breakdown_type in ('time', 'shop_time')
      and tb.period_start >= s.current_period_start
      and tb.period_end <= s.current_period_end
  ) u
),

combo as (
  select
    co.sales as cur_sales,
    po.sales as prev_sales,
    co.orders_cnt as cur_orders,
    po.orders_cnt as prev_orders,
    co.order_count as cur_order_count,
    po.order_count as prev_order_count,
    co.profit_val as cur_profit,
    po.profit_val as prev_profit,
    ct.visitors as cur_visitors,
    pt.visitors as prev_visitors,
    (select days from days_elapsed) as days_cnt,
    ao.sales as avg_sales,
    ao.orders_cnt as avg_orders,
    ao.order_count as avg_order_count,
    ao.profit_val as avg_profit,
    avt.visitors as avg_visitors,
    ut.target_amount as user_target_amount,
    ut.target_quantity as user_target_quantity
  from current_orders co
  cross join prev_orders po
  cross join current_traffic ct
  cross join prev_traffic pt
  cross join avg_orders ao
  cross join avg_traffic avt
  cross join user_target ut
)

-- 数值列统一使用 COALESCE 避免输出 null，保证前端 .toFixed() 等调用不报错
-- 优化：round 使用 ::numeric 避免 PostgreSQL round(double precision, integer) 不存在
select
  round(c.cur_sales::numeric, 2) as sales_amount_today,
  round(c.prev_sales::numeric, 2) as sales_amount_yesterday,
  coalesce(round((c.avg_sales / nullif(c.days_cnt, 0))::numeric, 2), 0) as sales_amount_average,
  coalesce(round(((c.cur_sales - c.prev_sales) * 100.0 / nullif(c.prev_sales, 0))::numeric, 2), 0) as sales_amount_change,

  c.cur_orders::numeric as sales_quantity_today,
  c.prev_orders::numeric as sales_quantity_yesterday,
  coalesce(round(c.avg_orders::numeric / nullif(c.days_cnt, 0), 2), 0) as sales_quantity_average,
  coalesce(round(((c.cur_orders - c.prev_orders) * 100.0 / nullif(c.prev_orders, 0))::numeric, 2), 0) as sales_quantity_change,

  c.cur_visitors::numeric as traffic_today,
  c.prev_visitors::numeric as traffic_yesterday,
  coalesce(round(c.avg_visitors::numeric / nullif(c.days_cnt, 0), 2), 0) as traffic_average,
  coalesce(round(((c.cur_visitors - c.prev_visitors) * 100.0 / nullif(c.prev_visitors, 0))::numeric, 2), 0) as traffic_change,

  case when c.cur_visitors > 0 then round((c.cur_orders::numeric * 100.0 / c.cur_visitors)::numeric, 2) else 0 end as conversion_rate_today,
  case when c.prev_visitors > 0 then round((c.prev_orders::numeric * 100.0 / c.prev_visitors)::numeric, 2) else 0 end as conversion_rate_yesterday,
  case when c.avg_visitors > 0 and c.days_cnt > 0 then round((c.avg_orders::numeric * 100.0 / c.avg_visitors)::numeric, 2) else 0 end as conversion_rate_average,
  case
    when c.prev_visitors > 0 and c.prev_orders > 0
    then round(
      ((c.cur_orders::numeric * 100.0 / nullif(c.cur_visitors, 0) - c.prev_orders::numeric * 100.0 / c.prev_visitors)
      * 100.0 / nullif(c.prev_orders::numeric * 100.0 / c.prev_visitors, 0))::numeric,
      2
    )
    else 0
  end as conversion_rate_change,

  case when c.cur_orders > 0 then round((c.cur_sales / c.cur_orders)::numeric, 2) else 0 end as avg_order_value_today,
  case when c.prev_orders > 0 then round((c.prev_sales / c.prev_orders)::numeric, 2) else 0 end as avg_order_value_yesterday,
  case when c.avg_orders > 0 and c.days_cnt > 0 then round((c.avg_sales / c.avg_orders)::numeric, 2) else 0 end as avg_order_value_average,
  case
    when c.prev_orders > 0 and c.prev_sales > 0
    then round(((c.cur_sales / nullif(c.cur_orders, 0) - c.prev_sales / c.prev_orders) * 100.0 / nullif(c.prev_sales / c.prev_orders, 0))::numeric, 2)
    else 0
  end as avg_order_value_change,

  -- 连带率 = 商品件数/订单数（与核心KPI/经营指标一致，order_count=count(distinct order_id)）
  case when c.cur_order_count > 0 then round((c.cur_orders::numeric / c.cur_order_count)::numeric, 2) else 0 end as attach_rate_today,
  case when c.prev_order_count > 0 then round((c.prev_orders::numeric / c.prev_order_count)::numeric, 2) else 0 end as attach_rate_yesterday,
  case when c.avg_order_count > 0 then round((c.avg_orders::numeric / c.avg_order_count)::numeric, 2) else 0 end as attach_rate_average,
  coalesce(round(((case when c.cur_order_count > 0 then c.cur_orders::numeric / c.cur_order_count else 0 end - case when c.prev_order_count > 0 then c.prev_orders::numeric / c.prev_order_count else 0 end) * 100.0 / nullif(case when c.prev_order_count > 0 then c.prev_orders::numeric / c.prev_order_count else 0 end, 0))::numeric, 2), 0) as attach_rate_change,

  round(c.cur_profit::numeric, 2) as profit_today,
  round(c.prev_profit::numeric, 2) as profit_yesterday,
  coalesce(round((c.avg_profit / nullif(c.days_cnt, 0))::numeric, 2), 0) as profit_average,
  coalesce(round(((c.cur_profit - c.prev_profit) * 100.0 / nullif(c.prev_profit, 0))::numeric, 2), 0) as profit_change,

  round(c.user_target_amount::numeric, 2) as target_sales_amount,
  c.user_target_quantity::numeric as target_sales_quantity,
  case when c.user_target_amount > 0 then round((c.cur_sales * 100.0 / c.user_target_amount)::numeric, 2) else 0 end as target_achievement_rate
from combo c

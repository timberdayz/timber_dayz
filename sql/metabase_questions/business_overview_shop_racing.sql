-- =====================================================
-- Question: business_overview_shop_racing
-- 业务概览 - 店铺赛马
-- =====================================================
-- 用途：店铺/账号排名对比（按GMV排序）
-- 数据源：{{MODEL:Orders Model}}（由 init_metabase 解析为实际 ID）
-- 参数（仅日期、粒度、分组维度，无平台筛选）：
--   {{granularity}} - 粒度（daily/weekly/monthly），与数据对比约定一致
--   {{date}} - 日期（必填，YYYY-MM-DD）
--   {{group_by}} - 分组维度（shop=店铺 / platform 或 account=账号），默认 shop
-- 日期约定（与数据对比一致）：
--   daily = 当天；weekly = 所选日期所在周（周一～周日）；monthly = 所选日期所在月（1日～月末）
-- shop_id 为空时显示为 unknown店铺，便于判断数据统计有效性
-- =====================================================

with
params as (
  select
    {{date}}::date as target_date,
    {{granularity}} as gran
),

-- 当期时间范围（与数据对比 business_overview_comparison 一致）
period_scope as (
  select
    (select target_date from params) as target_date,
    (select gran from params) as gran,
    case (select gran from params)
      when 'daily' then (select target_date from params)
      when 'weekly' then (date_trunc('week', (select target_date from params))::date)
      when 'monthly' then (date_trunc('month', (select target_date from params))::date)
    end as current_period_start,
    case (select gran from params)
      when 'daily' then (select target_date from params)
      when 'weekly' then (date_trunc('week', (select target_date from params))::date + 6)
      when 'monthly' then (date_trunc('month', (select target_date from params))::date + interval '1 month' - interval '1 day')
    end::date as current_period_end
),

-- 行级数据：与数据对比一致，用 paid_amount + count(distinct order_id) 计算 GMV/订单数（无买家数统计）
filtered_data as (
  select
    o.platform_code,
    o.shop_id,
    o.order_id,
    o.paid_amount
  from {{MODEL:Orders Model}} o
  cross join period_scope s
  where (
      (s.gran = 'daily' and o.granularity = 'daily' and o.metric_date = s.current_period_start)
      or (s.gran = 'weekly' and o.granularity = 'weekly' and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
      or (s.gran = 'weekly' and o.granularity = 'daily' and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
      or (s.gran = 'monthly' and o.granularity = 'monthly' and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
      or (s.gran = 'monthly' and o.granularity = 'daily' and o.metric_date >= s.current_period_start and o.metric_date <= s.current_period_end)
    )
),

-- 按店铺分组（与数据对比一致：GMV=sum(paid_amount)，订单数=count(distinct order_id)，无买家数）
shop_ranking as (
  select
    o.platform_code as "平台",
    case
      when coalesce(nullif(trim(o.shop_id::text), ''), 'unknown') = 'unknown' then 'unknown店铺'
      else coalesce(max(o.shop_id)::text, 'unknown店铺')
    end as "名称",
    coalesce(nullif(trim(max(o.shop_id)::text), ''), 'unknown') as "店铺ID",
    coalesce(sum(o.paid_amount), 0) as "GMV",
    count(distinct o.order_id) as "订单数",
    case
      when count(distinct o.order_id) > 0 then round(sum(o.paid_amount)::numeric / count(distinct o.order_id), 2)
      else 0
    end as "客单价",
    row_number() over (order by sum(o.paid_amount) desc) as "排名"
  from filtered_data o
  group by o.platform_code, coalesce(nullif(trim(o.shop_id::text), ''), 'unknown')
),

-- 按账号/平台分组（GMV/订单数/客单价同上，无买家数）
platform_ranking as (
  select
    platform_code as "平台",
    platform_code as "名称",
    'ALL' as "店铺ID",
    coalesce(sum(paid_amount), 0) as "GMV",
    count(distinct order_id) as "订单数",
    case
      when count(distinct order_id) > 0 then round(sum(paid_amount)::numeric / count(distinct order_id), 2)
      else 0
    end as "客单价",
    row_number() over (order by sum(paid_amount) desc) as "排名"
  from filtered_data
  group by platform_code
)

-- 根据 group_by 输出：shop=店铺，platform/account=账号
select * from shop_ranking
where {{group_by}} = 'shop' or {{group_by}} is null
union all
select * from platform_ranking
where {{group_by}} in ('platform', 'account')
order by "排名"
limit 50;

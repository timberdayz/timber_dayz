-- =====================================================
-- Question: business_overview_shop_racing
-- 业务概览 - 店铺赛马
-- =====================================================
-- 用途：店铺/账号排名对比（按GMV排序），含目标、完成率
-- 数据源：{{MODEL:Orders Model}}、a_class.target_breakdown、a_class.sales_targets
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

-- 店铺/账号目标：a_class.target_breakdown（shop/shop_time 含店铺维度），查不到则为 0
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
    and (
      (s.gran = 'daily' and tb.period_start = s.current_period_start and tb.period_end = s.current_period_end)
      or (s.gran = 'weekly' and tb.period_start >= s.current_period_start and tb.period_end <= s.current_period_end)
      or (s.gran = 'monthly' and tb.period_start <= s.current_period_end and tb.period_end >= s.current_period_start)
    )
  group by tb.platform_code, lower(coalesce(nullif(trim(tb.shop_id::text), ''), 'unknown'))
),
platform_targets as (
  select
    tb.platform_code,
    coalesce(sum(tb.target_amount), 0) as target_amount
  from a_class.target_breakdown tb
  inner join a_class.sales_targets st on st.id = tb.target_id and st.status = 'active'
  cross join period_scope s
  where tb.breakdown_type in ('shop', 'shop_time')
    and tb.platform_code is not null
    and (
      (s.gran = 'daily' and tb.period_start = s.current_period_start and tb.period_end = s.current_period_end)
      or (s.gran = 'weekly' and tb.period_start >= s.current_period_start and tb.period_end <= s.current_period_end)
      or (s.gran = 'monthly' and tb.period_start <= s.current_period_end and tb.period_end >= s.current_period_start)
    )
  group by tb.platform_code
),

-- 店铺聚合（先聚合再关联目标）
shop_agg as (
  select
    o.platform_code,
    coalesce(nullif(lower(trim(o.shop_id::text)), ''), 'unknown') as shop_id_key,
    coalesce(sum(o.paid_amount), 0) as gmv,
    count(distinct o.order_id) as order_cnt,
    max(o.shop_id)::text as shop_id_display
  from filtered_data o
  group by o.platform_code, coalesce(nullif(lower(trim(o.shop_id::text)), ''), 'unknown')
),
-- 按店铺分组（目标、完成率由 SQL 计算；shop_id 为 null/none/空 时名称显示 unknown店铺）
shop_ranking as (
  select
    a.platform_code as "平台",
    case
      when a.shop_id_key in ('unknown', 'none') then 'unknown店铺'
      else coalesce(a.shop_id_display, 'unknown店铺')
    end as "名称",
    a.shop_id_key as "店铺ID",
    a.gmv as "GMV",
    a.order_cnt as "订单数",
    case when a.order_cnt > 0 then round(a.gmv::numeric / a.order_cnt, 2) else 0 end as "客单价",
    coalesce(t.target_amount, 0) as "目标",
    case when coalesce(t.target_amount, 0) > 0 then round((a.gmv::numeric * 100 / t.target_amount)::numeric, 2) else 0 end as "完成率",
    row_number() over (order by a.gmv desc) as "排名"
  from shop_agg a
  left join shop_targets t on t.platform_code = a.platform_code and t.shop_id_key = a.shop_id_key
),

-- 按账号/平台分组
platform_ranking as (
  select
    fd.platform_code as "平台",
    fd.platform_code as "名称",
    'ALL' as "店铺ID",
    coalesce(sum(fd.paid_amount), 0) as "GMV",
    count(distinct fd.order_id) as "订单数",
    case when count(distinct fd.order_id) > 0 then round(sum(fd.paid_amount)::numeric / count(distinct fd.order_id), 2) else 0 end as "客单价",
    coalesce(pt.target_amount, 0) as "目标",
    case when coalesce(pt.target_amount, 0) > 0 then round((sum(fd.paid_amount)::numeric * 100 / pt.target_amount)::numeric, 2) else 0 end as "完成率",
    row_number() over (order by sum(fd.paid_amount) desc) as "排名"
  from filtered_data fd
  left join platform_targets pt on pt.platform_code = fd.platform_code
  group by fd.platform_code, pt.target_amount
)

-- 根据 group_by 输出：shop=店铺，platform/account=账号（含目标、完成率）
select "平台","名称","店铺ID","GMV","订单数","客单价","目标","完成率","排名" from shop_ranking
where {{group_by}} = 'shop' or {{group_by}} is null
union all
select "平台","名称","店铺ID","GMV","订单数","客单价","目标","完成率","排名" from platform_ranking
where {{group_by}} in ('platform', 'account')
order by "排名"
limit 50;

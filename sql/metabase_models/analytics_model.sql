-- ====================================================
-- Analytics Model - 分析数据域模型（CTE分层架构）
-- ====================================================
-- 用途：整合所有平台的分析数据（包含流量数据），统一字段名，为前端提供完整数据支持
-- 数据源：b_class schema 下的所有 analytics 相关表
-- 平台：shopee, tiktok, miaoshou
-- 粒度：daily, weekly, monthly
-- 去重策略：基于 data_hash，优先级 daily > weekly > monthly
-- 注意：traffic域已迁移到analytics域，流量数据存储在analytics表中
-- 优化：CTE分层架构，提升可读性和维护性
-- ====================================================

WITH 
-- ====================================================
-- 第1层：字段映射（提取所有候选字段，不做格式化）
-- ====================================================
field_mapping AS (
  -- Shopee 日度分析数据（包含流量数据）
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_analytics_daily
  
  UNION ALL
  
  -- Shopee 周度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_analytics_weekly
  
  UNION ALL
  
  -- Shopee 月度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_analytics_monthly
  
  UNION ALL
  
  -- TikTok 日度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_analytics_daily
  
  UNION ALL
  
  -- TikTok 周度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_analytics_weekly
  
  UNION ALL
  
  -- TikTok 月度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_analytics_monthly
  
  UNION ALL
  
  -- 妙手ERP 日度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_analytics_daily
  
  UNION ALL
  
  -- 妙手ERP 周度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_analytics_weekly
  
  UNION ALL
  
  -- 妙手ERP 月度分析数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'成交额') AS gmv_raw,
    COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'跳出访客数', raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'平均停留时长', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'平均会话时长') AS avg_session_duration_raw,
    COALESCE(raw_data->>'平均页面数', raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'平均每会话页面数') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_analytics_monthly
),

-- ====================================================
-- 第2层：数据清洗（统一格式化逻辑，处理破折号等特殊字符）
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS visitor_count,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS page_views,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS impressions,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS clicks,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC / 100.0 AS click_rate,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC / 100.0 AS conversion_rate,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS order_count,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS gmv,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_rate_raw, '%', ''), ',', '.'), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC / 100.0 AS bounce_rate,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_visitors_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS bounce_visitors,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(avg_session_duration_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS avg_session_duration,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(pages_per_session_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS pages_per_session,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM field_mapping
),

-- ====================================================
-- 第3层：去重（基于 data_hash，优先级 daily > weekly > monthly）
-- ====================================================
deduplicated AS (
  SELECT 
    *,
    ROW_NUMBER() OVER (
      PARTITION BY platform_code, shop_id, data_hash 
      ORDER BY 
        CASE granularity
          WHEN 'daily' THEN 1
          WHEN 'weekly' THEN 2
          WHEN 'monthly' THEN 3
        END ASC,
        ingest_timestamp DESC
    ) AS rn
  FROM cleaned
)

-- ====================================================
-- 第4层：最终输出（只保留去重后的数据，设置默认值）
-- ====================================================
SELECT 
  platform_code,
  COALESCE(NULLIF(TRIM(shop_id::text), ''), 'unknown') AS shop_id,
  data_domain, granularity,
  metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
  COALESCE(visitor_count, 0) AS visitor_count,
  COALESCE(page_views, 0) AS page_views,
  COALESCE(impressions, 0) AS impressions,
  COALESCE(clicks, 0) AS clicks,
  COALESCE(click_rate, 0) AS click_rate,
  COALESCE(conversion_rate, 0) AS conversion_rate,
  COALESCE(order_count, 0) AS order_count,
  COALESCE(gmv, 0) AS gmv,
  COALESCE(bounce_rate, 0) AS bounce_rate,
  COALESCE(bounce_visitors, 0) AS bounce_visitors,
  COALESCE(avg_session_duration, 0) AS avg_session_duration,
  COALESCE(pages_per_session, 0) AS pages_per_session,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM deduplicated
WHERE rn = 1

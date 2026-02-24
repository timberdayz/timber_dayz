-- ====================================================
-- Services Model - 服务数据域模型（CTE分层架构）
-- ====================================================
-- 用途：整合所有平台的服务数据（ai_assistant + agent），统一字段名，为前端提供完整数据支持
-- 数据源：b_class schema 下的所有 services 相关表
-- 平台：shopee, tiktok, miaoshou
-- 子类型：ai_assistant, agent
-- 粒度：daily, weekly, monthly
-- 去重策略：基于 data_hash，优先级 daily > weekly > monthly
-- 日期处理：直接使用数据同步阶段已清洗的日期字段（period_start_date, period_end_date, metric_date）
-- 优化：CTE分层架构，提升可读性和维护性
-- ====================================================

WITH 
-- ====================================================
-- 第1层：字段映射（提取所有候选字段，不做格式化）
-- ====================================================
field_mapping AS (
  -- Shopee Agent 日度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_agent_daily
  
  UNION ALL
  
  -- Shopee Agent 周度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_agent_weekly
  
  UNION ALL
  
  -- Shopee Agent 月度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_agent_monthly
  
  UNION ALL
  
  -- Shopee AI Assistant 日度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_ai_assistant_daily
  
  UNION ALL
  
  -- Shopee AI Assistant 周度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_ai_assistant_weekly
  
  UNION ALL
  
  -- Shopee AI Assistant 月度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_ai_assistant_monthly
  
  UNION ALL
  
  -- TikTok Agent 日度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_agent_daily
  
  UNION ALL
  
  -- TikTok Agent 周度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_agent_weekly
  
  UNION ALL
  
  -- TikTok Agent 月度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_agent_monthly
  
  UNION ALL
  
  -- TikTok AI Assistant 日度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_ai_assistant_daily
  
  UNION ALL
  
  -- TikTok AI Assistant 周度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_ai_assistant_weekly
  
  UNION ALL
  
  -- TikTok AI Assistant 月度服务数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
    COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
    COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
    COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_ai_assistant_monthly
),

-- ====================================================
-- 第2层：数据清洗（统一格式化逻辑，处理破折号等特殊字符）
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity, sub_domain,
    
    -- 日期字段：直接使用数据同步阶段已清洗的字段
    -- 统一锚点日期：使用 period_end_date（与系统设计一致）
    COALESCE(period_end_date, metric_date) AS service_date,
    -- 日期范围字段：直接使用已清洗的字段
    COALESCE(period_start_date, metric_date) AS service_start_date,
    COALESCE(period_end_date, metric_date) AS service_end_date,
    period_start_time, period_end_time,
    
    -- 数值字段清洗（先清洗再校验，仅合法数值才 ::NUMERIC，畸形数据兜底为 NULL）
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
          THEN c::NUMERIC ELSE NULL END
     FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s
    ) AS visitor_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
          THEN c::NUMERIC ELSE NULL END
     FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(chat_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s
    ) AS chat_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
          THEN c::NUMERIC ELSE NULL END
     FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s
    ) AS order_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
          THEN c::NUMERIC ELSE NULL END
     FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s
    ) AS gmv,
    -- 百分比字段（满意度）
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
          THEN (c::NUMERIC / 100.0) ELSE NULL END
     FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(satisfaction_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s
    ) AS satisfaction,
    
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
-- 第4层：最终输出（统一日期字段，设置默认值）
-- ====================================================
SELECT 
  platform_code, shop_id, data_domain, granularity, sub_domain,
  service_date,                    -- 统一锚点日期（使用 period_end_date，用于排序和聚合）
  service_start_date,              -- 日期范围开始日期（单个日期时 = service_date）
  service_end_date,                -- 日期范围结束日期（单个日期时 = service_date）
  period_start_time, period_end_time,
  COALESCE(visitor_count, 0) AS visitor_count,
  COALESCE(chat_count, 0) AS chat_count,
  COALESCE(order_count, 0) AS order_count,
  COALESCE(gmv, 0) AS gmv,
  COALESCE(satisfaction, 0) AS satisfaction,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM deduplicated
WHERE rn = 1

CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_services_atomic AS
-- ====================================================
-- Services Model - 鏈嶅姟鏁版嵁鍩熸ā鍨嬶紙CTE鍒嗗眰鏋舵瀯锛?
-- ====================================================
-- 鐢ㄩ€旓細鏁村悎鎵€鏈夊钩鍙扮殑鏈嶅姟鏁版嵁锛坅i_assistant + agent锛夛紝缁熶竴瀛楁鍚嶏紝涓哄墠绔彁渚涘畬鏁存暟鎹敮鎸?
-- 鏁版嵁婧愶細b_class schema 涓嬬殑鎵€鏈?services 鐩稿叧琛?
-- 骞冲彴锛歴hopee, tiktok, miaoshou
-- 瀛愮被鍨嬶細ai_assistant, agent
-- 绮掑害锛歞aily, weekly, monthly
-- 鍘婚噸绛栫暐锛氬熀浜?data_hash锛屼紭鍏堢骇 daily > weekly > monthly
-- 鏃ユ湡澶勭悊锛氱洿鎺ヤ娇鐢ㄦ暟鎹悓姝ラ樁娈靛凡娓呮礂鐨勬棩鏈熷瓧娈碉紙period_start_date, period_end_date, metric_date锛?
-- 浼樺寲锛欳TE鍒嗗眰鏋舵瀯锛屾彁鍗囧彲璇绘€у拰缁存姢鎬?
-- ====================================================

WITH 
-- ====================================================
-- 绗?灞傦細瀛楁鏄犲皠锛堟彁鍙栨墍鏈夊€欓€夊瓧娈碉紝涓嶅仛鏍煎紡鍖栵級
-- ====================================================
field_mapping AS (
  -- Shopee Agent 鏃ュ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_agent_daily
  
  UNION ALL
  
  -- Shopee Agent 鍛ㄥ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_agent_weekly
  
  UNION ALL
  
  -- Shopee Agent 鏈堝害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_agent_monthly
  
  UNION ALL
  
  -- Shopee AI Assistant 鏃ュ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_ai_assistant_daily
  
  UNION ALL
  
  -- Shopee AI Assistant 鍛ㄥ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_ai_assistant_weekly
  
  UNION ALL
  
  -- Shopee AI Assistant 鏈堝害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_services_ai_assistant_monthly
  
  UNION ALL
  
  -- TikTok Agent 鏃ュ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_agent_daily
  
  UNION ALL
  
  -- TikTok Agent 鍛ㄥ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_agent_weekly
  
  UNION ALL
  
  -- TikTok Agent 鏈堝害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'agent' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_agent_monthly
  
  UNION ALL
  
  -- TikTok AI Assistant 鏃ュ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_ai_assistant_daily
  
  UNION ALL
  
  -- TikTok AI Assistant 鍛ㄥ害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_ai_assistant_weekly
  
  UNION ALL
  
  -- TikTok AI Assistant 鏈堝害鏈嶅姟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    'ai_assistant' AS sub_domain,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'璁垮') AS visitor_count_raw,
    COALESCE(raw_data->>'鑱婂ぉ璇㈤棶', raw_data->>'chats', raw_data->>'Chats', raw_data->>'璇㈤棶', raw_data->>'鑱婂ぉ鏁?) AS chat_count_raw,
    COALESCE(raw_data->>'璁㈠崟', raw_data->>'orders', raw_data->>'Orders', raw_data->>'璁㈠崟鏁?, raw_data->>'涔板鏁?) AS order_count_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'鎴愪氦閲戦') AS gmv_raw,
    COALESCE(raw_data->>'婊℃剰搴?, raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'鐢ㄦ埛婊℃剰搴?) AS satisfaction_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_services_ai_assistant_monthly
),

-- ====================================================
-- 绗?灞傦細鏁版嵁娓呮礂锛堢粺涓€鏍煎紡鍖栭€昏緫锛屽鐞嗙牬鎶樺彿绛夌壒娈婂瓧绗︼級
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity, sub_domain,
    
    -- 鏃ユ湡瀛楁锛氱洿鎺ヤ娇鐢ㄦ暟鎹悓姝ラ樁娈靛凡娓呮礂鐨勫瓧娈?
    -- 缁熶竴閿氱偣鏃ユ湡锛氫娇鐢?period_end_date锛堜笌绯荤粺璁捐涓€鑷达級
    COALESCE(period_end_date, metric_date) AS service_date,
    -- 鏃ユ湡鑼冨洿瀛楁锛氱洿鎺ヤ娇鐢ㄥ凡娓呮礂鐨勫瓧娈?
    COALESCE(period_start_date, metric_date) AS service_start_date,
    COALESCE(period_end_date, metric_date) AS service_end_date,
    period_start_time, period_end_time,
    
    -- 鏁板€煎瓧娈垫竻娲楋紙鍏堟竻娲楀啀鏍￠獙锛屼粎鍚堟硶鏁板€兼墠 ::NUMERIC锛岀暩褰㈡暟鎹厹搴曚负 NULL锛?
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
    -- 鐧惧垎姣斿瓧娈碉紙婊℃剰搴︼級
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
          THEN (c::NUMERIC / 100.0) ELSE NULL END
     FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(satisfaction_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s
    ) AS satisfaction,
    
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM field_mapping
),

-- ====================================================
-- 绗?灞傦細鍘婚噸锛堝熀浜?data_hash锛屼紭鍏堢骇 daily > weekly > monthly锛?
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
-- 绗?灞傦細鏈€缁堣緭鍑猴紙缁熶竴鏃ユ湡瀛楁锛岃缃粯璁ゅ€硷級
-- ====================================================
SELECT 
  platform_code, shop_id, data_domain, granularity, sub_domain,
  service_date,                    -- 缁熶竴閿氱偣鏃ユ湡锛堜娇鐢?period_end_date锛岀敤浜庢帓搴忓拰鑱氬悎锛?
  service_start_date,              -- 鏃ユ湡鑼冨洿寮€濮嬫棩鏈燂紙鍗曚釜鏃ユ湡鏃?= service_date锛?
  service_end_date,                -- 鏃ユ湡鑼冨洿缁撴潫鏃ユ湡锛堝崟涓棩鏈熸椂 = service_date锛?
  period_start_time, period_end_time,
  COALESCE(visitor_count, 0) AS visitor_count,
  COALESCE(chat_count, 0) AS chat_count,
  COALESCE(order_count, 0) AS order_count,
  COALESCE(gmv, 0) AS gmv,
  COALESCE(satisfaction, 0) AS satisfaction,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM deduplicated
WHERE rn = 1


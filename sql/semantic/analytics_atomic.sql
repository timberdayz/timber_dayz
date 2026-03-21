CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_analytics_atomic AS
-- ====================================================
-- Analytics Model - 鍒嗘瀽鏁版嵁鍩熸ā鍨嬶紙CTE鍒嗗眰鏋舵瀯锛?
-- ====================================================
-- 鐢ㄩ€旓細鏁村悎鎵€鏈夊钩鍙扮殑鍒嗘瀽鏁版嵁锛堝寘鍚祦閲忔暟鎹級锛岀粺涓€瀛楁鍚嶏紝涓哄墠绔彁渚涘畬鏁存暟鎹敮鎸?
-- 鏁版嵁婧愶細b_class schema 涓嬬殑鎵€鏈?analytics 鐩稿叧琛?
-- 骞冲彴锛歴hopee, tiktok, miaoshou
-- 绮掑害锛歞aily, weekly, monthly
-- 鍘婚噸绛栫暐锛氬熀浜?data_hash锛屼紭鍏堢骇 daily > weekly > monthly
-- 娉ㄦ剰锛歵raffic鍩熷凡杩佺Щ鍒癮nalytics鍩燂紝娴侀噺鏁版嵁瀛樺偍鍦╝nalytics琛ㄤ腑
-- 浼樺寲锛欳TE鍒嗗眰鏋舵瀯锛屾彁鍗囧彲璇绘€у拰缁存姢鎬?
-- ====================================================

WITH 
-- ====================================================
-- 绗?灞傦細瀛楁鏄犲皠锛堟彁鍙栨墍鏈夊€欓€夊瓧娈碉紝涓嶅仛鏍煎紡鍖栵級
-- ====================================================
field_mapping AS (
  -- Shopee 鏃ュ害鍒嗘瀽鏁版嵁锛堝寘鍚祦閲忔暟鎹級
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_analytics_daily
  
  UNION ALL
  
  -- Shopee 鍛ㄥ害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_analytics_weekly
  
  UNION ALL
  
  -- Shopee 鏈堝害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_analytics_monthly
  
  UNION ALL
  
  -- TikTok 鏃ュ害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_analytics_daily
  
  UNION ALL
  
  -- TikTok 鍛ㄥ害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_analytics_weekly
  
  UNION ALL
  
  -- TikTok 鏈堝害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_analytics_monthly
  
  UNION ALL
  
  -- 濡欐墜ERP 鏃ュ害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_analytics_daily
  
  UNION ALL
  
  -- 濡欐墜ERP 鍛ㄥ害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_analytics_weekly
  
  UNION ALL
  
  -- 濡欐墜ERP 鏈堝害鍒嗘瀽鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv', raw_data->>'visitor_count') AS visitor_count_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'page_view') AS page_views_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount', raw_data->>'鎴愪氦棰?) AS gmv_raw,
    COALESCE(raw_data->>'璺冲嚭鐜?, raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
    COALESCE(raw_data->>'璺冲嚭璁垮鏁?, raw_data->>'bounce_visitors', raw_data->>'Bounce Visitors') AS bounce_visitors_raw,
    COALESCE(raw_data->>'骞冲潎鍋滅暀鏃堕暱', raw_data->>'avg_session_duration', raw_data->>'Avg Session Duration', raw_data->>'骞冲潎浼氳瘽鏃堕暱') AS avg_session_duration_raw,
    COALESCE(raw_data->>'骞冲潎椤甸潰鏁?, raw_data->>'pages_per_session', raw_data->>'Pages Per Session', raw_data->>'骞冲潎姣忎細璇濋〉闈㈡暟') AS pages_per_session_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_analytics_monthly
),

-- ====================================================
-- 绗?灞傦細鏁版嵁娓呮礂锛堢粺涓€鏍煎紡鍖栭€昏緫锛屽鐞嗙牬鎶樺彿绛夌壒娈婂瓧绗︼級
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    -- 瀹夊叏鏁板€艰浆鎹細浠呭悎娉曟暟鍊兼墠 ::NUMERIC锛岀暩褰㈡暟鎹厹搴曚负 NULL
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS visitor_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS page_views,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS impressions,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS clicks,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN (c::NUMERIC / 100.0) ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS click_rate,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN (c::NUMERIC / 100.0) ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS conversion_rate,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS order_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS gmv,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN (c::NUMERIC / 100.0) ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS bounce_rate,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_visitors_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS bounce_visitors,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(avg_session_duration_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS avg_session_duration,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(pages_per_session_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS pages_per_session,
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
-- 绗?灞傦細鏈€缁堣緭鍑猴紙鍙繚鐣欏幓閲嶅悗鐨勬暟鎹紝璁剧疆榛樿鍊硷級
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


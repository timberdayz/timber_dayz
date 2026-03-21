CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_products_atomic AS
-- ====================================================
-- Products Model - 浜у搧鏁版嵁鍩熸ā鍨嬶紙CTE鍒嗗眰鏋舵瀯锛?
-- ====================================================
-- 鐢ㄩ€旓細鏁村悎鎵€鏈夊钩鍙扮殑浜у搧鏁版嵁锛岀粺涓€瀛楁鍚嶏紝涓哄墠绔彁渚涘畬鏁存暟鎹敮鎸?
-- 鏁版嵁婧愶細b_class schema 涓嬬殑鎵€鏈?products 鐩稿叧琛?
-- 骞冲彴锛歴hopee, tiktok, miaoshou
-- 绮掑害锛歞aily, weekly, monthly
-- 鍘婚噸绛栫暐锛氬熀浜?data_hash锛屼紭鍏堢骇 daily > weekly > monthly
-- 浼樺寲锛欳TE鍒嗗眰鏋舵瀯锛屾彁鍗囧彲璇绘€у拰缁存姢鎬?
-- ====================================================

WITH 
-- ====================================================
-- 绗?灞傦細瀛楁鏄犲皠锛堟彁鍙栨墍鏈夊€欓€夊瓧娈碉紝涓嶅仛鏍煎紡鍖栵級
-- ====================================================
field_mapping AS (
  -- Shopee 鏃ュ害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_products_daily
  
  UNION ALL
  
  -- Shopee 鍛ㄥ害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_products_weekly
  
  UNION ALL
  
  -- Shopee 鏈堝害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_products_monthly
  
  UNION ALL
  
  -- TikTok 鏃ュ害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_products_daily
  
  UNION ALL
  
  -- TikTok 鍛ㄥ害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_products_weekly
  
  UNION ALL
  
  -- TikTok 鏈堝害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_products_monthly
  
  UNION ALL
  
  -- 濡欐墜ERP 鏃ュ害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_products_daily
  
  UNION ALL
  
  -- 濡欐墜ERP 鍛ㄥ害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_products_weekly
  
  UNION ALL
  
  -- 濡欐墜ERP 鏈堝害浜у搧鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'鍟嗗搧ID', raw_data->>'浜у搧ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'绫荤洰', raw_data->>'鍒嗙被', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'鍟嗗搧鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'鍙樹綋鐘舵€?, raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'浠锋牸', raw_data->>'鍗曚环', raw_data->>'鍞环', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'搴撳瓨', raw_data->>'搴撳瓨鏁伴噺', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'甯佺', raw_data->>'璐у竵', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'娴忚閲?, raw_data->>'椤甸潰娴忚娆℃暟', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'璁垮鏁?, raw_data->>'鐙珛璁垮', raw_data->>'鍘婚噸椤甸潰娴忚娆℃暟', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'鐐瑰嚮娆℃暟', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'鐐瑰嚮鐜?, raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'杞寲鐜?, raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'濂借瘎鐜?, raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'鍔犺喘娆℃暟', raw_data->>'鍔犺喘鏁?, raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'鍔犺喘璁垮鏁?, raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'鎴愪氦浠舵暟', raw_data->>'閿€閲?, raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'鎴愪氦閲戦', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'閿€閲?, raw_data->>'閿€鍞暟閲?, raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'璇勫垎', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'璇勪环鏁?, raw_data->>'璇勮鏁?, raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_products_monthly
),

-- ====================================================
-- 绗?灞傦細鏁版嵁娓呮礂锛堢粺涓€鏍煎紡鍖栭€昏緫锛屽鐞嗙牬鎶樺彿绛夌壒娈婂瓧绗︼級
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    product_id_raw AS product_id,
    product_name_raw AS product_name,
    platform_sku_raw AS platform_sku,
    category_raw AS category,
    item_status_raw AS item_status,
    variation_status_raw AS variation_status,
    -- 瀹夊叏鏁板€艰浆鎹細浠呭悎娉曟暟鍊兼墠 ::NUMERIC锛岀暩褰㈡暟鎹厹搴曚负 NULL
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(price_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS price,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS stock,
    currency_raw AS currency,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS page_views,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(unique_visitors_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS unique_visitors,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS impressions,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS clicks,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN (c::NUMERIC / 100.0) ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS click_rate,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN (c::NUMERIC / 100.0) ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS conversion_rate,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN (c::NUMERIC / 100.0) ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(positive_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS positive_rate,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(cart_add_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS cart_add_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(cart_add_visitors_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS cart_add_visitors,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS order_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sold_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS sold_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS gmv,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS sales_amount,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_volume_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS sales_volume,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(rating_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS rating,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(review_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS review_count,
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
  platform_code, shop_id, data_domain, granularity,
  metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
  product_id, product_name, platform_sku, category, item_status, variation_status,
  COALESCE(price, 0) AS price,
  COALESCE(stock, 0) AS stock,
  currency,
  COALESCE(page_views, 0) AS page_views,
  COALESCE(unique_visitors, 0) AS unique_visitors,
  COALESCE(impressions, 0) AS impressions,
  COALESCE(clicks, 0) AS clicks,
  COALESCE(click_rate, 0) AS click_rate,
  COALESCE(conversion_rate, 0) AS conversion_rate,
  COALESCE(positive_rate, 0) AS positive_rate,
  COALESCE(cart_add_count, 0) AS cart_add_count,
  COALESCE(cart_add_visitors, 0) AS cart_add_visitors,
  COALESCE(order_count, 0) AS order_count,
  COALESCE(sold_count, 0) AS sold_count,
  COALESCE(gmv, 0) AS gmv,
  COALESCE(sales_amount, 0) AS sales_amount,
  COALESCE(sales_volume, 0) AS sales_volume,
  COALESCE(rating, 0) AS rating,
  COALESCE(review_count, 0) AS review_count,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM deduplicated
WHERE rn = 1


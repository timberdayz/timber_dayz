-- ====================================================
-- Products Model - 产品数据域模型（CTE分层架构）
-- ====================================================
-- 用途：整合所有平台的产品数据，统一字段名，为前端提供完整数据支持
-- 数据源：b_class schema 下的所有 products 相关表
-- 平台：shopee, tiktok, miaoshou
-- 粒度：daily, weekly, monthly
-- 去重策略：基于 data_hash，优先级 daily > weekly > monthly
-- 优化：CTE分层架构，提升可读性和维护性
-- ====================================================

WITH 
-- ====================================================
-- 第1层：字段映射（提取所有候选字段，不做格式化）
-- ====================================================
field_mapping AS (
  -- Shopee 日度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_products_daily
  
  UNION ALL
  
  -- Shopee 周度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_products_weekly
  
  UNION ALL
  
  -- Shopee 月度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_products_monthly
  
  UNION ALL
  
  -- TikTok 日度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_products_daily
  
  UNION ALL
  
  -- TikTok 周度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_products_weekly
  
  UNION ALL
  
  -- TikTok 月度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_products_monthly
  
  UNION ALL
  
  -- 妙手ERP 日度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_products_daily
  
  UNION ALL
  
  -- 妙手ERP 周度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_products_weekly
  
  UNION ALL
  
  -- 妙手ERP 月度产品数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku_raw,
    COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category_raw,
    COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status_raw,
    COALESCE(raw_data->>'变体状态', raw_data->>'variation_status', raw_data->>'Variation Status') AS variation_status_raw,
    COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
    COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
    COALESCE(raw_data->>'币种', raw_data->>'货币', raw_data->>'currency', raw_data->>'Currency') AS currency_raw,
    COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
    COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'去重页面浏览次数', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
    COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
    COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
    COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
    COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
    COALESCE(raw_data->>'好评率', raw_data->>'positive_rate', raw_data->>'Positive Rate') AS positive_rate_raw,
    COALESCE(raw_data->>'加购次数', raw_data->>'加购数', raw_data->>'cart_add_count', raw_data->>'Cart Add Count', raw_data->>'add_to_cart') AS cart_add_count_raw,
    COALESCE(raw_data->>'加购访客数', raw_data->>'cart_add_visitors', raw_data->>'Cart Add Visitors') AS cart_add_visitors_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
    COALESCE(raw_data->>'成交件数', raw_data->>'销量', raw_data->>'sold_count', raw_data->>'Sold Count', raw_data->>'sales') AS sold_count_raw,
    COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'GMV') AS gmv_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
    COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
    COALESCE(raw_data->>'评分', raw_data->>'rating', raw_data->>'Rating') AS rating_raw,
    COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_products_monthly
),

-- ====================================================
-- 第2层：数据清洗（统一格式化逻辑，处理破折号等特殊字符）
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
    -- 安全数值转换：仅合法数值才 ::NUMERIC，畸形数据兜底为 NULL
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

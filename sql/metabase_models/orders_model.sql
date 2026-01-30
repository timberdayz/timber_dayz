-- ====================================================
-- Orders Model - 订单数据域模型（CTE分层架构）
-- ====================================================
-- 用途：整合所有平台的订单数据，统一字段名，为前端提供完整数据支持
-- 数据源：b_class schema 下的所有 orders 相关表
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
  -- Shopee 日度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_orders_daily
  
  UNION ALL
  
  -- Shopee 周度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_orders_weekly
  
  UNION ALL
  
  -- Shopee 月度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_orders_monthly
  
  UNION ALL
  
  -- TikTok 日度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_orders_daily
  
  UNION ALL
  
  -- TikTok 周度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_orders_weekly
  
  UNION ALL
  
  -- TikTok 月度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_orders_monthly
  
  UNION ALL
  
  -- 妙手ERP 日度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_orders_daily
  
  UNION ALL
  
  -- 妙手ERP 周度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_orders_weekly
  
  UNION ALL
  
  -- 妙手ERP 月度订单数据
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'订单编号', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV', raw_data->>'订单金额', raw_data->>'成交金额', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'实付金额', raw_data->>'买家实付金额', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'产品原价', raw_data->>'product_original_price', raw_data->>'原价', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'预估回款金额', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'净利润', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'下单时间', raw_data->>'订单时间', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'付款时间', raw_data->>'支付时间', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'订单日期', raw_data->>'日期', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'商品SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'商品货号') AS product_sku_raw,
    COALESCE(raw_data->>'商品类型', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'类型') AS product_type_raw,
    COALESCE(raw_data->>'出库仓库', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'仓库') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'买家数', raw_data->>'买家', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'产品数量', raw_data->>'商品数量', raw_data->>'数量', raw_data->>'件数', raw_data->>'销售数量', raw_data->>'出库数量', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_orders_monthly
),

-- ====================================================
-- 第2层：数据清洗（统一格式化逻辑，处理破折号等特殊字符）
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    order_id_raw AS order_id,
    order_status_raw AS order_status,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS sales_amount,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(paid_amount_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS paid_amount,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(product_original_price_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS product_original_price,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(estimated_settlement_amount_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS estimated_settlement_amount,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(profit_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS profit,
    -- 日期/时间字段：优先使用数据库已清洗的字段，其次从 raw_data 提取（假设数据同步已清洗）
    COALESCE(
      period_start_time,
      CASE 
        WHEN order_time_raw IS NOT NULL AND order_time_raw != '' AND order_time_raw != '—' AND order_time_raw != '–' AND order_time_raw != '-' THEN
          order_time_raw::TIMESTAMP
        ELSE NULL
      END,
      metric_date::TIMESTAMP
    ) AS order_time,
    CASE 
      WHEN payment_time_raw IS NOT NULL AND payment_time_raw != '' AND payment_time_raw != '—' AND payment_time_raw != '–' AND payment_time_raw != '-' THEN
        payment_time_raw::TIMESTAMP
      ELSE NULL
    END AS payment_time,
    -- order_date 直接使用数据库字段
    COALESCE(period_start_date, metric_date) AS order_date,
    product_name_raw AS product_name,
    product_id_raw AS product_id,
    platform_sku_raw AS platform_sku,
    sku_id_raw AS sku_id,
    product_sku_raw AS product_sku,
    product_type_raw AS product_type,
    outbound_warehouse_raw AS outbound_warehouse,
    NULLIF(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(buyer_count_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS buyer_count,
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
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(product_quantity_raw, ''), ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
        '[^0-9.]',
        '',
        'g'
      ),
      ''
    )::NUMERIC AS product_quantity,
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
  order_id, order_status,
  COALESCE(sales_amount, 0) AS sales_amount,
  COALESCE(paid_amount, 0) AS paid_amount,
  COALESCE(product_original_price, 0) AS product_original_price,
  COALESCE(estimated_settlement_amount, 0) AS estimated_settlement_amount,
  COALESCE(profit, 0) AS profit,
  order_time, payment_time, order_date,
  product_name, product_id, platform_sku, sku_id, product_sku, product_type, outbound_warehouse,
  COALESCE(buyer_count, 0) AS buyer_count,
  COALESCE(order_count, 0) AS order_count,
  COALESCE(product_quantity, 0) AS product_quantity,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM deduplicated
WHERE rn = 1

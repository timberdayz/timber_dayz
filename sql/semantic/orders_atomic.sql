CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_orders_atomic AS
-- ====================================================
-- Orders Model - 璁㈠崟鏁版嵁鍩熸ā鍨嬶紙CTE鍒嗗眰鏋舵瀯锛?
-- 鐗堟湰: add-metabase-sql-retain-amount-sign (淇濈暀绗﹀彿銆乻hop_id 鏄犲皠銆佺暩褰㈡暟鎹害瀹?
-- ====================================================
-- 鐢ㄩ€旓細鏁村悎鎵€鏈夊钩鍙扮殑璁㈠崟鏁版嵁锛岀粺涓€瀛楁鍚嶏紝涓哄墠绔彁渚涘畬鏁存暟鎹敮鎸?
-- 鏁版嵁婧愶細b_class schema 涓嬬殑鎵€鏈?orders 鐩稿叧琛?
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
  -- Shopee 鏃ュ害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_orders_daily
  
  UNION ALL
  
  -- Shopee 鍛ㄥ害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_orders_weekly
  
  UNION ALL
  
  -- Shopee 鏈堝害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_shopee_orders_monthly
  
  UNION ALL
  
  -- TikTok 鏃ュ害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_orders_daily
  
  UNION ALL
  
  -- TikTok 鍛ㄥ害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_orders_weekly
  
  UNION ALL
  
  -- TikTok 鏈堝害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_tiktok_orders_monthly
  
  UNION ALL
  
  -- 濡欐墜ERP 鏃ュ害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_orders_daily
  
  UNION ALL
  
  -- 濡欐墜ERP 鍛ㄥ害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_orders_weekly
  
  UNION ALL
  
  -- 濡欐墜ERP 鏈堝害璁㈠崟鏁版嵁
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    COALESCE(raw_data->>'璁㈠崟鍙?, raw_data->>'璁㈠崟ID', raw_data->>'璁㈠崟缂栧彿', raw_data->>'order_id', raw_data->>'Order ID', raw_data->>'order_no') AS order_id_raw,
    COALESCE(raw_data->>'璁㈠崟鐘舵€?, raw_data->>'鐘舵€?, raw_data->>'order_status', raw_data->>'Status') AS order_status_raw,
    COALESCE(raw_data->>'閿€鍞', raw_data->>'閿€鍞噾棰?, raw_data->>'GMV', raw_data->>'璁㈠崟閲戦', raw_data->>'鎴愪氦閲戦', raw_data->>'sales_amount', raw_data->>'Sales Amount') AS sales_amount_raw,
    COALESCE(raw_data->>'瀹炰粯閲戦', raw_data->>'涔板瀹炰粯閲戦', raw_data->>'paid_amount', raw_data->>'Paid Amount') AS paid_amount_raw,
    COALESCE(raw_data->>'浜у搧鍘熶环', raw_data->>'product_original_price', raw_data->>'鍘熶环', raw_data->>'Original Price') AS product_original_price_raw,
    COALESCE(raw_data->>'棰勪及鍥炴閲戦', raw_data->>'amount_yu_gu_hui_kuan', raw_data->>'estimated_settlement', raw_data->>'Estimated Settlement') AS estimated_settlement_amount_raw,
    COALESCE(raw_data->>'鍒╂鼎', raw_data->>'profit', raw_data->>'姣涘埄', raw_data->>'鍑€鍒╂鼎', raw_data->>'Profit') AS profit_raw,
    COALESCE(raw_data->>'涓嬪崟鏃堕棿', raw_data->>'璁㈠崟鏃堕棿', raw_data->>'order_time', raw_data->>'Order Time') AS order_time_raw,
    COALESCE(raw_data->>'浠樻鏃堕棿', raw_data->>'鏀粯鏃堕棿', raw_data->>'payment_time', raw_data->>'Payment Time') AS payment_time_raw,
    COALESCE(raw_data->>'璁㈠崟鏃ユ湡', raw_data->>'鏃ユ湡', raw_data->>'order_date', raw_data->>'Order Date') AS order_date_raw,
    COALESCE(raw_data->>'鍟嗗搧鍚嶇О', raw_data->>'浜у搧鍚嶇О', raw_data->>'鍟嗗搧鏍囬', raw_data->>'product_name', raw_data->>'Product Name') AS product_name_raw,
    COALESCE(raw_data->>'浜у搧ID', raw_data->>'鍟嗗搧ID', raw_data->>'product_id', raw_data->>'Product ID') AS product_id_raw,
    COALESCE(raw_data->>'骞冲彴SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU') AS platform_sku_raw,
    COALESCE(raw_data->>'SKU ID', raw_data->>'sku_id', raw_data->>'SKU_ID') AS sku_id_raw,
    COALESCE(raw_data->>'鍟嗗搧SKU', raw_data->>'product_sku', raw_data->>'Product SKU', raw_data->>'鍟嗗搧璐у彿') AS product_sku_raw,
    COALESCE(raw_data->>'鍟嗗搧绫诲瀷', raw_data->>'product_type', raw_data->>'Product Type', raw_data->>'绫诲瀷') AS product_type_raw,
    COALESCE(raw_data->>'鍑哄簱浠撳簱', raw_data->>'chu_ku_cang_ku', raw_data->>'outbound_warehouse', raw_data->>'浠撳簱') AS outbound_warehouse_raw,
    COALESCE(raw_data->>'涔板鏁?, raw_data->>'涔板', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
    COALESCE(raw_data->>'璁㈠崟鏁?, raw_data->>'璁㈠崟鏁伴噺', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
    COALESCE(raw_data->>'浜у搧鏁伴噺', raw_data->>'鍟嗗搧鏁伴噺', raw_data->>'鏁伴噺', raw_data->>'浠舵暟', raw_data->>'閿€鍞暟閲?, raw_data->>'鍑哄簱鏁伴噺', raw_data->>'product_quantity', raw_data->>'quantity', raw_data->>'qty', raw_data->>'item_quantity') AS product_quantity_raw,
    COALESCE(raw_data->>'閲囪喘閲戦', raw_data->>'閲囪喘浠?, raw_data->>'purchase_amount', raw_data->>'cogs', raw_data->>'浜у搧鎴愭湰') AS purchase_amount_raw,
    COALESCE(raw_data->>'璁㈠崟鍘熷閲戦', raw_data->>'浜у搧鎶樺悗浠锋牸', raw_data->>'浜у搧鎶樺悗閲戦', raw_data->>'order_original_amount', raw_data->>'浜у搧鍘熶环') AS order_original_amount_raw,
    COALESCE(raw_data->>'浠撳簱鎿嶄綔璐?, raw_data->>'warehouse_operation_fee', raw_data->>'璐村崟璐?) AS warehouse_operation_fee_raw,
    COALESCE(raw_data->>'杩愯垂', raw_data->>'鍟嗗杩愯垂', raw_data->>'shipping_fee') AS shipping_fee_raw,
    COALESCE(raw_data->>'鎺ㄥ箍璐?, raw_data->>'骞冲彴鎺ㄥ箍璐?, raw_data->>'骞冲彴鏀跺彇鎺ㄥ箍璐?, raw_data->>'promotion_fee', raw_data->>'钀ラ攢鎺ㄥ箍璐?) AS promotion_fee_raw,
    COALESCE(raw_data->>'骞冲彴浣ｉ噾', raw_data->>'浣ｉ噾', raw_data->>'鎬讳剑閲?, raw_data->>'platform_commission', raw_data->>'TikTok Shop骞冲彴浣ｉ噾') AS platform_commission_raw,
    COALESCE(raw_data->>'骞冲彴鎵ｈ垂', raw_data->>'TikTok Shop骞冲彴鎵ｈ垂', raw_data->>'platform_deduction_fee', raw_data->>'骞冲彴鎵ｆ') AS platform_deduction_fee_raw,
    COALESCE(raw_data->>'浠ｉ噾鍒?, raw_data->>'骞冲彴浠ｉ噾鍒?, raw_data->>'platform_voucher', raw_data->>'骞冲彴浼樻儬鍒?) AS platform_voucher_raw,
    COALESCE(raw_data->>'鏈嶅姟璐?, raw_data->>'骞冲彴鏈嶅姟璐?, raw_data->>'骞冲彴鏀跺彇鏈嶅姟璐?, raw_data->>'platform_service_fee', raw_data->>'TikTok Shop骞冲彴鏈嶅姟璐?) AS platform_service_fee_raw,
    raw_data, header_columns, data_hash, ingest_timestamp, currency_code
  FROM b_class.fact_miaoshou_orders_monthly
),

-- ====================================================
-- 绗?灞傦細鏁版嵁娓呮礂锛堢粺涓€鏍煎紡鍖栭€昏緫锛屽鐞嗙牬鎶樺彿绛夌壒娈婂瓧绗︼級
-- ====================================================
cleaned AS (
  SELECT 
    platform_code, shop_id, data_domain, granularity,
    metric_date, period_start_date, period_end_date, period_start_time, period_end_time,
    order_id_raw AS order_id,
    order_status_raw AS order_status,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS sales_amount,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(paid_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS paid_amount,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(product_original_price_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS product_original_price,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(estimated_settlement_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS estimated_settlement_amount,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(profit_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS profit,
    -- 鏃ユ湡/鏃堕棿瀛楁锛氫紭鍏堜娇鐢ㄦ暟鎹簱宸叉竻娲楃殑瀛楁锛屽叾娆′粠 raw_data 鎻愬彇锛堝亣璁炬暟鎹悓姝ュ凡娓呮礂锛?
    COALESCE(
      period_start_time,
      CASE 
        WHEN order_time_raw IS NOT NULL AND order_time_raw != '' AND order_time_raw != CHR(8212) AND order_time_raw != CHR(8211) AND order_time_raw != '-' THEN
          order_time_raw::TIMESTAMP
        ELSE NULL
      END,
      metric_date::TIMESTAMP
    ) AS order_time,
    CASE 
      WHEN payment_time_raw IS NOT NULL AND payment_time_raw != '' AND payment_time_raw != CHR(8212) AND payment_time_raw != CHR(8211) AND payment_time_raw != '-' THEN
        payment_time_raw::TIMESTAMP
      ELSE NULL
    END AS payment_time,
    -- order_date 鐩存帴浣跨敤鏁版嵁搴撳瓧娈?
    COALESCE(period_start_date, metric_date) AS order_date,
    product_name_raw AS product_name,
    product_id_raw AS product_id,
    platform_sku_raw AS platform_sku,
    sku_id_raw AS sku_id,
    product_sku_raw AS product_sku,
    product_type_raw AS product_type,
    outbound_warehouse_raw AS outbound_warehouse,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(buyer_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS buyer_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS order_count,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(product_quantity_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS product_quantity,
    -- 鎴愭湰鍒楋紙B 绫伙紝涓?docs/COST_DATA_SOURCES_AND_DEFINITIONS.md 涓€鑷达級
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(purchase_amount_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS purchase_amount,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(order_original_amount_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS order_original_amount,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(warehouse_operation_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS warehouse_operation_fee,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(shipping_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS shipping_fee,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(promotion_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS promotion_fee,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_commission_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS platform_commission,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_deduction_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS platform_deduction_fee,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_voucher_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS platform_voucher,
    (SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_service_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s) AS platform_service_fee,
    (COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(order_original_amount_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) - COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(purchase_amount_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) - COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(profit_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) - COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(warehouse_operation_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0)) AS platform_total_cost_derived,
    (COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(shipping_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) + COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(promotion_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) + COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_commission_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) + COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_deduction_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) + COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_voucher_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0) + COALESCE((SELECT CASE WHEN c ~ '^-?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+|[0-9]+)$' AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.' THEN c::NUMERIC ELSE NULL END FROM (SELECT REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(platform_service_fee_raw, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), $$[^0-9.-]$$, '', 'g') AS c) s), 0)) AS platform_total_cost_itemized,
    TRIM(COALESCE(raw_data->>'搴楅摵', raw_data->>'搴楅摵鍚嶇О', '')) AS store_alias_raw,
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
),

-- ====================================================
-- 绗?.5灞傦細shop_id 鏄犲皠锛堝簵閾哄埆绉?-> core.platform_accounts锛屾湭鍖归厤淇濈暀鍘?shop_id锛?
-- ====================================================
with_shop_resolved AS (
  SELECT
    d.platform_code,
    COALESCE(pa.mapped_shop_id, d.shop_id) AS shop_id,
    d.data_domain, d.granularity,
    d.metric_date, d.period_start_date, d.period_end_date, d.period_start_time, d.period_end_time,
    d.order_id, d.order_status,
    d.sales_amount, d.paid_amount, d.product_original_price, d.estimated_settlement_amount, d.profit,
    d.purchase_amount, d.order_original_amount, d.warehouse_operation_fee,
    d.shipping_fee, d.promotion_fee, d.platform_commission, d.platform_deduction_fee, d.platform_voucher, d.platform_service_fee,
    d.platform_total_cost_derived, d.platform_total_cost_itemized,
    d.order_time, d.payment_time, d.order_date,
    d.product_name, d.product_id, d.platform_sku, d.sku_id, d.product_sku, d.product_type, d.outbound_warehouse,
    d.buyer_count, d.order_count, d.product_quantity,
    d.raw_data, d.header_columns, d.data_hash, d.ingest_timestamp, d.currency_code
  FROM deduplicated d
  LEFT JOIN LATERAL (
    SELECT pa_inner.shop_id AS mapped_shop_id
    FROM core.platform_accounts pa_inner
    WHERE pa_inner.platform = d.platform_code
      AND (TRIM(COALESCE(d.store_alias_raw, '')) <> '' AND (TRIM(COALESCE(d.store_alias_raw, '')) = pa_inner.store_name OR TRIM(COALESCE(d.store_alias_raw, '')) = pa_inner.account_alias))
    ORDER BY pa_inner.id
    LIMIT 1
  ) pa ON true
  WHERE d.rn = 1
)

-- ====================================================
-- 绗?灞傦細鏈€缁堣緭鍑猴紙鍙繚鐣欏幓閲嶅悗鐨勬暟鎹紝璁剧疆榛樿鍊硷級
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
  COALESCE(purchase_amount, 0) AS purchase_amount,
  COALESCE(order_original_amount, 0) AS order_original_amount,
  COALESCE(warehouse_operation_fee, 0) AS warehouse_operation_fee,
  COALESCE(shipping_fee, 0) AS shipping_fee,
  COALESCE(promotion_fee, 0) AS promotion_fee,
  COALESCE(platform_commission, 0) AS platform_commission,
  COALESCE(platform_deduction_fee, 0) AS platform_deduction_fee,
  COALESCE(platform_voucher, 0) AS platform_voucher,
  COALESCE(platform_service_fee, 0) AS platform_service_fee,
  COALESCE(platform_total_cost_derived, 0) AS platform_total_cost_derived,
  COALESCE(platform_total_cost_itemized, 0) AS platform_total_cost_itemized,
  order_time, payment_time, order_date,
  product_name, product_id, platform_sku, sku_id, product_sku, product_type, outbound_warehouse,
  COALESCE(buyer_count, 0) AS buyer_count,
  COALESCE(order_count, 0) AS order_count,
  COALESCE(product_quantity, 0) AS product_quantity,
  raw_data, header_columns, data_hash, ingest_timestamp, currency_code
FROM with_shop_resolved


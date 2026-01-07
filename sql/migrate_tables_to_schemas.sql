-- ===================================================
-- 迁移表到对应Schema
-- ===================================================
-- 创建时间: 2025-11-26
-- 目的: 将表按数据分类迁移到对应Schema

-- A类数据表（7张）
ALTER TABLE IF EXISTS sales_targets_a SET SCHEMA a_class;
ALTER TABLE IF EXISTS sales_campaigns_a SET SCHEMA a_class;
ALTER TABLE IF EXISTS operating_costs SET SCHEMA a_class;
ALTER TABLE IF EXISTS employees SET SCHEMA a_class;
ALTER TABLE IF EXISTS employee_targets SET SCHEMA a_class;
ALTER TABLE IF EXISTS attendance_records SET SCHEMA a_class;
ALTER TABLE IF EXISTS performance_config_a SET SCHEMA a_class;

-- B类数据表（15张）
ALTER TABLE IF EXISTS fact_raw_data_orders_daily SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_orders_weekly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_orders_monthly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_products_daily SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_products_weekly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_products_monthly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_traffic_daily SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_traffic_weekly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_traffic_monthly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_services_daily SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_services_weekly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_services_monthly SET SCHEMA b_class;
ALTER TABLE IF EXISTS fact_raw_data_inventory_snapshot SET SCHEMA b_class;
ALTER TABLE IF EXISTS entity_aliases SET SCHEMA b_class;
ALTER TABLE IF EXISTS staging_raw_data SET SCHEMA b_class;

-- C类数据表（4张）
ALTER TABLE IF EXISTS employee_performance SET SCHEMA c_class;
ALTER TABLE IF EXISTS employee_commissions SET SCHEMA c_class;
ALTER TABLE IF EXISTS shop_commissions SET SCHEMA c_class;
ALTER TABLE IF EXISTS performance_scores_c SET SCHEMA c_class;

-- 核心ERP表（保留在public或移到core）
ALTER TABLE IF EXISTS catalog_files SET SCHEMA core;
ALTER TABLE IF EXISTS field_mapping_templates SET SCHEMA core;
ALTER TABLE IF EXISTS field_mapping_template_items SET SCHEMA core;
ALTER TABLE IF EXISTS field_mapping_dictionary SET SCHEMA core;
ALTER TABLE IF EXISTS dim_platform SET SCHEMA core;
ALTER TABLE IF EXISTS dim_shop SET SCHEMA core;
ALTER TABLE IF EXISTS dim_product SET SCHEMA core;
ALTER TABLE IF EXISTS fact_sales_orders SET SCHEMA core;
ALTER TABLE IF EXISTS fact_product_metrics SET SCHEMA core;
ALTER TABLE IF EXISTS data_quarantine SET SCHEMA core;
ALTER TABLE IF EXISTS accounts SET SCHEMA core;
ALTER TABLE IF EXISTS collection_tasks SET SCHEMA core;
ALTER TABLE IF EXISTS data_files SET SCHEMA core;
ALTER TABLE IF EXISTS data_records SET SCHEMA core;
ALTER TABLE IF EXISTS mapping_sessions SET SCHEMA core;
ALTER TABLE IF EXISTS staging_orders SET SCHEMA core;
ALTER TABLE IF EXISTS staging_product_metrics SET SCHEMA core;
ALTER TABLE IF EXISTS dim_metric_formulas SET SCHEMA core;
ALTER TABLE IF EXISTS sales_targets SET SCHEMA core;
ALTER TABLE IF EXISTS alembic_version SET SCHEMA core;

-- 注意：如果表不存在，ALTER TABLE IF EXISTS会静默跳过，不会报错


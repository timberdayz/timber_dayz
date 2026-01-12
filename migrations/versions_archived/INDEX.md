# 归档迁移文件索引
归档时间: 2026-01-12 11:49:55
归档文件数: 55

## 归档文件列表

| 文件名 | Revision | Down Revision |
|--------|----------|---------------|
| 20250126_0006_b_plus_upgrade.py | unknown | None |
| 20250128_0012_add_product_hierarchy_fields.py | unknown | None |
| 20250129_v4_4_0_finance_domain.py | v4_4_0_finance | 20250128_0012 |
| 20250131_0013_add_template_parsing_config.py | 20250131_0013 | v4_4_0_finance |
| 20250131_add_c_class_mv_indexes.py | 20250131_add_c_class_mv_indexes | 20250131_optimize_c_class_mv |
| 20250131_add_currency_policy_to_field_mapping.py | 20250131_add_currency_policy | 20251115_c_class_mv |
| 20250131_create_mv_shop_attach_rate_daily.py | 20250131_mv_attach_rate | 20250131_optimize_c_class_mv |
| 20250131_optimize_c_class_materialized_views.py | 20250131_optimize_c_class_mv | 20250131_add_currency_policy |
| 20250131_v4_6_0_pattern_based_mapping.py | v4_6_0 | 20250131_0013 |
| 20250829_1118_0af13b84ba3f_initial_database_schema.py | 0af13b84ba3f | None |
| 20250925_0001_init_unified_star_schema.py | unknown | None |
| 20250926_0002_add_product_images.py | unknown | None |
| 20251016_0003_add_data_quarantine.py | unknown | None |
| 20251016_0004_add_performance_indexes.py | 20251016_0004 | 20251016_0003 |
| 20251023_0005_add_erp_core_tables.py | 20251023_0005 | 20251016_0004 |
| 20251027_0007_catalog_phase1_indexes.py | unknown | None |
| 20251027_0008_partition_fact_tables.py | unknown | None |
| 20251027_0009_create_dim_date.py | unknown | None |
| 20251027_0010_type_convergence.py | unknown | None |
| 20251027_0011_create_product_images.py | 20251027_0011 | 20251027_0010 |
| 20251105_204106_create_mv_product_management.py | 20251105_204106 | add_field_usage_tracking |
| 20251105_204200_create_mv_refresh_log.py | 20251105_204200 | 20251105_204106 |
| 20251105_add_field_usage_tracking.py | add_field_usage_tracking | 20251027_0011 |
| 20251105_add_image_url_to_metrics.py | 20251105_add_image_url | 20251105_performance_indexes |
| 20251105_add_performance_indexes.py | 20251105_performance_indexes | 20251027_0011 |
| 20251109_v4_10_2_add_mv_display_field.py | v4_10_2 | 20251105_performance_indexes |
| 20251113_v4_11_0_add_sales_campaign_and_target_management.py | v4_11_0_sales_campaign_target | v4_10_2 |
| 20251115_add_c_class_performance_indexes.py | 20251115_c_class_indexes | v4_11_0_sales_campaign_target |
| 20251115_create_c_class_materialized_views.py | 20251115_c_class_mv | 20251115_c_class_indexes |
| 20251120_172442_add_product_id_to_fact_order_items.py | 20251120_172442 | v4_6_0 |
| 20251120_181500_fix_nullable_fields_for_critical_tables.py | 20251120_181500 | 20251120_172442 |
| 20251121_132800_create_operational_data_tables.py | 20251121_132800 | 20251120_181500 |
| 20251126_132151_v4_6_0_dss_architecture_tables.py | 20251126_132151 | 20251121_132800 |
| 20251204_151142_add_currency_code_to_fact_raw_data_tables.py | 20251204_151142 | 20251126_132151 |
| 20251205_153442_v4_16_0_add_analytics_and_sub_domain_tables.py | 20251205_153442 | 20251204_151142 |
| 20251209_v4_6_0_collection_module_tables.py | collection_module_v460 | 20251205_153442 |
| 20251211_v4_7_0_collection_task_granularity_optimization.py | collection_task_granularity_v470 | collection_module_v460 |
| 20251213_v4_7_0_add_platform_accounts_table.py | 20251213_platform_accounts | collection_task_granularity_v470 |
| 20251214_v4_7_0_add_account_alias_to_platform_accounts.py | 20251214_account_alias | 20251213_platform_accounts |
| 20251216_phase9_2_add_collection_sync_points_table.py | 20251216_sync_points | 20251214_account_alias |
| 20251216_phase9_4_add_component_versions_table.py | 20251216_component_versions | 20251216_sync_points |
| 20260101_v4_18_1_add_shop_id_to_platform_accounts.py | 20260101_shop_id | 20251216_component_versions |
| 20260104_add_user_registration_fields.py | 20260104_user_registration | 20260101_shop_id |
| 20260104_add_user_status_trigger.py | 20260104_user_status_trigger | 20260104_user_approval_logs |
| 20260104_create_user_approval_logs_table.py | 20260104_user_approval_logs | 20260104_user_registration |
| 20260104_ensure_operator_role.py | 20260104_operator_role | 20260104_user_status_trigger |
| 20260105_add_locked_until_field.py | 20260105_locked_until | 20260104_operator_role |
| 20260105_create_user_sessions_table.py | 20260105_user_sessions | 20260105_locked_until |
| 20260105_v4_19_4_add_rate_limit_config_tables.py | v4_19_4_rate_limit_config | 20260105_user_sessions |
| 20260106_v4_20_0_add_system_logs_table.py | v4_20_0_system_logs | v4_19_4_rate_limit_config |
| 20260108_v4_20_0_add_backup_records_table.py | v4_20_0_backup_records | v4_20_0_security_config |
| 20260108_v4_20_0_add_security_config_table.py | v4_20_0_security_config | v4_20_0_system_logs |
| 20260110_0001_complete_schema_base_tables.py | 20260110_complete_schema_base | v4_20_0_backup_records |
| 20260111_0001_complete_missing_tables.py | 20260111_complete_missing | 20260111_merge_all_heads |
| 20260111_merge_all_heads.py | 20260111_merge_all_heads | 
    '20260110_complete_schema_base',
    '20251105_204200',
    '20251105_add_image_url',
    '20250131_mv_attach_rate',
    '20250131_add_c_class_mv_indexes'
 |

## 说明

- 这些迁移文件已归档，不再作为迁移链的一部分
- 新的迁移起点是 `20260112_v5_0_0_schema_snapshot.py`
- 如需查看历史迁移，请参考此索引文件

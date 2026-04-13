[32m[INFO][0m 2026-04-10 20:28:36 - modules.core.config - 配置管理器初始化,配置目录: config
[32m[INFO][0m 2026-04-10 20:28:36 - modules.core.registry - 应用注册器初始化完成
# Schema Alignment Audit

## Summary

- Expected ORM tables: `134`
- Actual runtime table names: `218`
- Duplicate groups: `0`
- Misplaced tables: `0`
- Missing ORM tables: `0`
- Extra-only runtime tables: `84`

## Wave 1 Priority Tables

### catalog_files

- Priority: `P0`
- Wave: `wave_1`
- ORM schema: `public`
- Runtime schema: `public`
- Runtime schemas discovered: `['public']`
- Runtime time column: `first_seen_at`
- Migration evidence: `migrations/versions/20260112_v5_0_0_schema_snapshot.py`

### collection_tasks

- Priority: `P0`
- Wave: `wave_1`
- ORM schema: `core`
- Runtime schema: `core`
- Runtime schemas discovered: `['core']`
- Runtime time column: `created_at`
- Migration evidence: `migrations/versions/20260112_v5_0_0_schema_snapshot.py`

### collection_task_logs

- Priority: `P0`
- Wave: `wave_1`
- ORM schema: `core`
- Runtime schema: `core`
- Runtime schemas discovered: `['core']`
- Runtime time column: `timestamp`
- Migration evidence: `migrations/versions/20260112_v5_0_0_schema_snapshot.py`

### task_center_tasks

- Priority: `P1`
- Wave: `wave_1`
- ORM schema: `public`
- Runtime schema: `public`
- Runtime schemas discovered: `['public']`
- Runtime time column: `created_at`
- Migration evidence: `migrations/versions/20260328_add_task_center_tables.py`

### task_center_logs

- Priority: `P1`
- Wave: `wave_1`
- ORM schema: `public`
- Runtime schema: `public`
- Runtime schemas discovered: `['public']`
- Runtime time column: `created_at`
- Migration evidence: `migrations/versions/20260328_add_task_center_tables.py`

### task_center_links

- Priority: `P1`
- Wave: `wave_1`
- ORM schema: `public`
- Runtime schema: `public`
- Runtime schemas discovered: `['public']`
- Runtime time column: `None`
- Migration evidence: `migrations/versions/20260328_add_task_center_tables.py`

## Duplicate Groups

- None

## Misplaced Tables


## Missing Tables

- None

## Extra-Only Runtime Tables

- `alembic_version` in `['core']` class=`historical_migration_artifact` wave=`wave_3_ops_and_historical`
- `alembic_version__archive_retired` in `['public']` class=`historical_migration_artifact` wave=`wave_3_ops_and_historical`
- `apscheduler_jobs` in `['core']` class=`runtime_or_legacy_extra` wave=`wave_4_manual_review`
- `campaign_targets` in `['a_class']` class=`runtime_or_legacy_extra` wave=`wave_4_manual_review`
- `data_freshness_log` in `['ops']` class=`operations_runtime_table` wave=`wave_3_ops_and_historical`
- `data_lineage_registry` in `['ops']` class=`operations_runtime_table` wave=`wave_3_ops_and_historical`
- `dim_date` in `['core']` class=`runtime_or_legacy_extra` wave=`wave_4_manual_review`
- `fact_miaoshou_analytics_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_analytics_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_analytics_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_inventory_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_inventory_snapshot` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_inventory_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_orders_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_orders_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_orders_shopee_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_orders_shopee_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_orders_tiktok_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_orders_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_products_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_products_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_products_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_services_agent_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_services_agent_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_services_agent_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_services_ai_assistant_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_services_ai_assistant_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_services_ai_assistant_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_traffic_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_traffic_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_miaoshou_traffic_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_sales_orders` in `['core']` class=`runtime_or_legacy_extra` wave=`wave_4_manual_review`
- `fact_shopee_analytics_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_analytics_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_analytics_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_inventory_snapshot` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_orders_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_orders_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_orders_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_products_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_products_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_products_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_services_agent_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_services_agent_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_services_agent_weekly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_services_ai_assistant_daily` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- `fact_shopee_services_ai_assistant_monthly` in `['b_class']` class=`generated_runtime_fact` wave=`wave_2_runtime_generated`
- ... 34 more

## Follow-Up Waves

### wave_2_runtime_generated

- `fact_miaoshou_analytics_daily`
- `fact_miaoshou_analytics_monthly`
- `fact_miaoshou_analytics_weekly`
- `fact_miaoshou_inventory_monthly`
- `fact_miaoshou_inventory_snapshot`
- `fact_miaoshou_inventory_weekly`
- `fact_miaoshou_orders_daily`
- `fact_miaoshou_orders_monthly`
- `fact_miaoshou_orders_shopee_monthly`
- `fact_miaoshou_orders_shopee_weekly`
- `fact_miaoshou_orders_tiktok_weekly`
- `fact_miaoshou_orders_weekly`
- `fact_miaoshou_products_daily`
- `fact_miaoshou_products_monthly`
- `fact_miaoshou_products_weekly`
- `fact_miaoshou_services_agent_daily`
- `fact_miaoshou_services_agent_monthly`
- `fact_miaoshou_services_agent_weekly`
- `fact_miaoshou_services_ai_assistant_daily`
- `fact_miaoshou_services_ai_assistant_monthly`
- `fact_miaoshou_services_ai_assistant_weekly`
- `fact_miaoshou_traffic_daily`
- `fact_miaoshou_traffic_monthly`
- `fact_miaoshou_traffic_weekly`
- `fact_shopee_analytics_daily`
- `fact_shopee_analytics_monthly`
- `fact_shopee_analytics_weekly`
- `fact_shopee_inventory_snapshot`
- `fact_shopee_orders_daily`
- `fact_shopee_orders_monthly`
- ... 40 more

### wave_3_ops_and_historical

- `alembic_version`
- `alembic_version__archive_retired`
- `data_freshness_log`
- `data_lineage_registry`
- `pipeline_run_log`
- `pipeline_step_log`

### wave_4_manual_review

- `apscheduler_jobs`
- `campaign_targets`
- `dim_date`
- `fact_sales_orders`
- `field_alias_rules`
- `inventory_age_current`
- `inventory_age_history`
- `performance_scores_c`

## Wave 2 Governance

`wave_2_runtime_generated` contains generated runtime assets, not canonical business tables.

- generated runtime fact asset: `b_class.fact_*` tables produced by collection/data pipelines
- generated runtime API asset: `api.*_module` tables/materialized outputs used by dashboard/query paths
- these assets must not be treated as ORM-missing business-table drift
- these assets must not be targeted by duplicate/public cleanup waves
- later work should govern ownership, generation, refresh, and verification, not force ORM parity

## Wave 3 Governance

`wave_3_ops_and_historical` contains operations/support tables and migration-history artifacts.

- operations/support table: runtime infra or observability assets managed with ops ownership
- migration-history artifact: retained Alembic/version history artifacts that must stay outside business-table cleanup
- these assets must not be treated as business ORM drift
- these assets should be governed by retention, operational ownership, and migration-policy review

## Wave 4 Governance

`wave_4_manual_review` contains tables that require manual review before any cleanup, retirement, or ownership decision.

- these tables are neither automatically business drift nor automatically safe historical artifacts
- they may represent partial runtime assets, abandoned experiments, support tables, or legacy business models
- they must not be auto-retired or auto-aligned without explicit human review
- later work should classify each table into keep, migrate, archive, or remove

## First Repair Wave Recommendation

- Start with the wave-1 runtime-critical table family.
- Treat schema-placement mismatches and time-column mismatches as immediate alignment targets.
- Keep duplicate cleanup for non-wave-1 tables behind proof-based follow-up waves.

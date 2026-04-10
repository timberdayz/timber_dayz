[32m[INFO][0m 2026-04-10 19:34:44 - modules.core.config - 配置管理器初始化,配置目录: config
[32m[INFO][0m 2026-04-10 19:34:44 - modules.core.registry - 应用注册器初始化完成
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

- `alembic_version` in `['core']`
- `alembic_version__archive_retired` in `['public']`
- `apscheduler_jobs` in `['core']`
- `campaign_targets` in `['a_class']`
- `data_freshness_log` in `['ops']`
- `data_lineage_registry` in `['ops']`
- `dim_date` in `['core']`
- `fact_miaoshou_analytics_daily` in `['b_class']`
- `fact_miaoshou_analytics_monthly` in `['b_class']`
- `fact_miaoshou_analytics_weekly` in `['b_class']`
- `fact_miaoshou_inventory_monthly` in `['b_class']`
- `fact_miaoshou_inventory_snapshot` in `['b_class']`
- `fact_miaoshou_inventory_weekly` in `['b_class']`
- `fact_miaoshou_orders_daily` in `['b_class']`
- `fact_miaoshou_orders_monthly` in `['b_class']`
- `fact_miaoshou_orders_shopee_monthly` in `['b_class']`
- `fact_miaoshou_orders_shopee_weekly` in `['b_class']`
- `fact_miaoshou_orders_tiktok_weekly` in `['b_class']`
- `fact_miaoshou_orders_weekly` in `['b_class']`
- `fact_miaoshou_products_daily` in `['b_class']`
- `fact_miaoshou_products_monthly` in `['b_class']`
- `fact_miaoshou_products_weekly` in `['b_class']`
- `fact_miaoshou_services_agent_daily` in `['b_class']`
- `fact_miaoshou_services_agent_monthly` in `['b_class']`
- `fact_miaoshou_services_agent_weekly` in `['b_class']`
- `fact_miaoshou_services_ai_assistant_daily` in `['b_class']`
- `fact_miaoshou_services_ai_assistant_monthly` in `['b_class']`
- `fact_miaoshou_services_ai_assistant_weekly` in `['b_class']`
- `fact_miaoshou_traffic_daily` in `['b_class']`
- `fact_miaoshou_traffic_monthly` in `['b_class']`
- `fact_miaoshou_traffic_weekly` in `['b_class']`
- `fact_sales_orders` in `['core']`
- `fact_shopee_analytics_daily` in `['b_class']`
- `fact_shopee_analytics_monthly` in `['b_class']`
- `fact_shopee_analytics_weekly` in `['b_class']`
- `fact_shopee_inventory_snapshot` in `['b_class']`
- `fact_shopee_orders_daily` in `['b_class']`
- `fact_shopee_orders_monthly` in `['b_class']`
- `fact_shopee_orders_weekly` in `['b_class']`
- `fact_shopee_products_daily` in `['b_class']`
- `fact_shopee_products_monthly` in `['b_class']`
- `fact_shopee_products_shopee_daily` in `['b_class']`
- `fact_shopee_products_shopee_monthly` in `['b_class']`
- `fact_shopee_products_shopee_weekly` in `['b_class']`
- `fact_shopee_products_weekly` in `['b_class']`
- `fact_shopee_services_agent_daily` in `['b_class']`
- `fact_shopee_services_agent_monthly` in `['b_class']`
- `fact_shopee_services_agent_weekly` in `['b_class']`
- `fact_shopee_services_ai_assistant_daily` in `['b_class']`
- `fact_shopee_services_ai_assistant_monthly` in `['b_class']`
- ... 34 more

## First Repair Wave Recommendation

- Start with the wave-1 runtime-critical table family.
- Treat schema-placement mismatches and time-column mismatches as immediate alignment targets.
- Keep duplicate cleanup for non-wave-1 tables behind proof-based follow-up waves.


# PostgreSQL Dashboard Switch Quick Guide

## Enable

Set:

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=true
```

## Confirm

Check startup log for:

- `Dashboard router source: PostgreSQL`

## Verify

Smoke these endpoints:

- `/api/dashboard/business-overview/kpi`
- `/api/dashboard/business-overview/comparison`
- `/api/dashboard/business-overview/shop-racing`
- `/api/dashboard/business-overview/operational-metrics`
- `/api/dashboard/annual-summary/kpi`
- `/api/dashboard/annual-summary/trend`
- `/api/dashboard/annual-summary/platform-share`
- `/api/dashboard/annual-summary/by-shop`
- `/api/dashboard/annual-summary/target-completion`

Check these observability tables or routes:

- `ops.pipeline_run_log`
- `ops.data_freshness_log`
- `ops.data_lineage_registry`
- `/api/data-pipeline/status`
- `/api/data-pipeline/freshness`
- `/api/data-pipeline/lineage`

## Rollback

Set:

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=false
```

Check startup log for:

- `Dashboard router source: Metabase compatibility`

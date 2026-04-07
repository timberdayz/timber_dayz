# Cloud direct PostgreSQL Dashboard cutover report

## Summary

This report records the direct in-place cloud cutover of the dashboard runtime from the legacy Metabase-driven path to the PostgreSQL Dashboard primary path.

Target environment:

- host: `134.175.222.171`
- OS: Ubuntu Server 22.04 LTS 64bit
- operator path: direct SSH execution

## What Was Done

### Environment and runtime

- connected to the cloud server through SSH
- enabled PostgreSQL dashboard runtime:
  - `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
  - `ENABLE_METABASE_PROXY=false`
- verified backend startup logs show `Dashboard router source: PostgreSQL`
- verified Metabase proxy route is disabled

### Cloud deployment fixes

- fixed broken Docker registry mirror configuration on the cloud server
- fixed production compose so celery services receive required secrets and dashboard flags
- synchronized the PostgreSQL cutover branch code into the live backend/celery containers

### Data and schema compatibility

- preserved and re-solidified the `xihong` administrator account
- cleaned business test data only:
  - `a_class`
  - `b_class`
  - `c_class`
- preserved auth/system tables
- created `b_class` compatibility layer for environments still using `b_class_canonical`
- aligned dashboard SQL and service logic with the live cloud schema variants
- executed `semantic / mart / api / ops` SQL assets on the cloud database
- executed refresh plan successfully so `ops` tables contain real freshness and lineage records

### Legacy runtime retirement

- retired the cloud `xihong_erp_metabase` container
- removed the active `/metabase/` runtime proxy path from production Nginx

## Verification Results

### Dashboard smoke

All key smoke endpoints returned `200`:

- `/api/dashboard/business-overview/kpi`
- `/api/dashboard/business-overview/comparison`
- `/api/dashboard/business-overview/shop-racing`
- `/api/dashboard/business-overview/operational-metrics`
- `/api/dashboard/annual-summary/kpi`
- `/api/dashboard/annual-summary/trend`
- `/api/dashboard/annual-summary/platform-share`
- `/api/dashboard/annual-summary/by-shop`
- `/api/dashboard/annual-summary/target-completion`

### Runtime behavior

- `/` returns `200`
- `/api/dashboard/business-overview/kpi` returns `200`
- `/metabase/` now returns `404`

### Ops status

`ops` tables now contain successful runtime evidence:

- `ops.pipeline_run_log`
- `ops.pipeline_step_log`
- `ops.data_freshness_log`
- `ops.data_lineage_registry`

## Administrator account

The `xihong` account remains available after the cutover:

- username: `xihong`
- role: admin
- status: active
- is_superuser: true

## Remaining Notes

- the cloud environment is now operating on the PostgreSQL Dashboard primary path
- Metabase is no longer part of the cloud runtime path
- current smoke responses are valid but mostly zero-data because business test data was intentionally cleared

## Conclusion

The cloud direct PostgreSQL Dashboard cutover completed successfully.

Key acceptance points satisfied:

- all key smoke endpoints returned 200
- `xihong` administrator account remains usable
- business test data was reset without touching auth/system tables
- `/metabase/` no longer behaves as an active runtime entrypoint

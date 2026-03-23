# PostgreSQL Dashboard Pre-Prod Check Report

## Goal

在预发环境打开 `USE_POSTGRESQL_DASHBOARD_ROUTER=true` 之前与之后，使用统一模板记录切换前置条件、验证结果、风险和回退结论。

## Environment

- Date:
- Environment:
- Branch:
- Commit:
- Operator:

## Router Switch

- `USE_POSTGRESQL_DASHBOARD_ROUTER=true` applied: yes / no
- Startup log shows `Dashboard router source: PostgreSQL`: yes / no

## Automated Verification

- `python -m pytest backend/tests/data_pipeline -q`
- Result:

## HTTP Smoke Verification

| Endpoint | Status | Notes |
|---|---|---|
| `/api/dashboard/business-overview/kpi` |  |  |
| `/api/dashboard/business-overview/comparison` |  |  |
| `/api/dashboard/business-overview/shop-racing` |  |  |
| `/api/dashboard/business-overview/traffic-ranking` |  |  |
| `/api/dashboard/business-overview/inventory-backlog` |  |  |
| `/api/dashboard/business-overview/operational-metrics` |  |  |
| `/api/dashboard/clearance-ranking` |  |  |
| `/api/dashboard/annual-summary/kpi` |  |  |
| `/api/dashboard/annual-summary/trend` |  |  |
| `/api/dashboard/annual-summary/platform-share` |  |  |
| `/api/dashboard/annual-summary/by-shop` |  |  |
| `/api/dashboard/annual-summary/target-completion` |  |  |

## Ops Observability Check

- `ops.pipeline_run_log` checked: yes / no
- `ops.pipeline_step_log` checked: yes / no
- `ops.data_freshness_log` checked: yes / no
- `ops.data_lineage_registry` checked: yes / no

## Performance / Behavior Notes

- API latency observations:
- Data correctness observations:
- Cache behavior observations:

## Risk Assessment

- Remaining risk 1:
- Remaining risk 2:
- Remaining risk 3:

## Rollback Decision

- Ready to keep PostgreSQL router enabled: yes / no
- Rollback required: yes / no
- If rollback, reason:

# PostgreSQL Dashboard Pre-Prod Execution Checklist

## 1. Enable Router

Set in the target environment:

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=true
```

## 2. Confirm Startup Source

Check application logs for:

- `Dashboard router source: PostgreSQL`

## 3. Run Standard Verification

```bash
python scripts/run_postgresql_dashboard_preprod_check.py --base-url <base_url>
```

This runs:

1. `python -m pytest backend/tests/data_pipeline -q`
2. `python scripts/smoke_postgresql_dashboard_routes.py --base-url <base_url>`
3. `python scripts/check_postgresql_dashboard_ops.py`

## 4. Fill Pre-Prod Check Report

Use:

- `docs/development/POSTGRESQL_DASHBOARD_PREPROD_CHECK_REPORT_TEMPLATE.md`

## 5. Decide

- If all checks pass and observations look healthy: keep PostgreSQL router enabled
- If key checks fail: rollback by setting `USE_POSTGRESQL_DASHBOARD_ROUTER=false`

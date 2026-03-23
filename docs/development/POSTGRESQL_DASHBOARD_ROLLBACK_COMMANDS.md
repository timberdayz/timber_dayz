# PostgreSQL Dashboard Rollback Commands

## Router Rollback

Set:

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=false
```

Restart application.

## Confirm Rollback

Check startup log for:

- `Dashboard router source: Metabase compatibility`

## Quick Verification

Run:

```bash
python scripts/smoke_postgresql_dashboard_routes.py --base-url <base_url>
python scripts/check_postgresql_dashboard_ops.py
```

## Notes

- Rollback does not require dropping PostgreSQL `semantic / mart / api / ops` assets
- Rollback only changes the active HTTP router path

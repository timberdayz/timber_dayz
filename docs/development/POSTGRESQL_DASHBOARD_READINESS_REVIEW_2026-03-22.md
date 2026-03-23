# PostgreSQL Dashboard Readiness Review 2026-03-22

## Recommendation

**Recommended next step: enter pre-production gray validation.**

The branch is now in a state where pre-production verification is justified:

- SQL assets are executable
- refresh execution and observability exist
- PostgreSQL router is switchable by environment flag
- application-level HTTP verification exists
- rollout and rollback documents exist

## Readiness Summary

### Ready
- `semantic / mart / api / ops` assets exist
- `backend/tests/data_pipeline` is green
- PostgreSQL dashboard router can be enabled with `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
- startup logs explicitly show the active dashboard router source
- pre-prod and production operation documents exist
- smoke and ops helper scripts exist

### Still Open
- old `backend/routers/dashboard_api.py` remains as fallback and has not been retired
- not every PostgreSQL route has a real database HTTP integration test
- actual pre-production environment evidence has not yet been recorded in the report template

## Blocking Items

There are **no code-level blockers** remaining for pre-production gray validation.

## Non-Blocking Risks

1. Fallback path is still present and must remain stable until gray verification completes
2. Production rollout still depends on environment discipline and observation after the switch
3. Some integration coverage is still concentrated on the highest-value routes rather than every route

## Required Before Production Gray

1. Run:

```bash
python scripts/run_postgresql_dashboard_preprod_check.py --base-url <preprod_base_url>
```

2. Run:

```bash
python scripts/check_postgresql_dashboard_ops.py
```

3. Fill:

- `docs/development/POSTGRESQL_DASHBOARD_PREPROD_CHECK_REPORT_TEMPLATE.md`

4. Review:

- `docs/development/POSTGRESQL_DASHBOARD_PRODUCTION_GREY_RUNBOOK.md`
- `docs/development/POSTGRESQL_DASHBOARD_ROLLBACK_COMMANDS.md`

## Final Decision

**Go for pre-production gray validation.**

Do **not** retire the old dashboard router yet.  
Keep the PostgreSQL router behind the environment flag until pre-production verification is completed and reviewed.

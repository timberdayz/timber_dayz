# PostgreSQL Dashboard Stage Summary 2026-03-22

## Summary

The PostgreSQL dashboard cutover branch has moved beyond design and into executable, test-backed delivery.

Current branch:

- `codex/postgresql-api-semantic-mart-cutover`

Current remote:

- `cnb/codex/postgresql-api-semantic-mart-cutover`

## What Exists Now

### Database Layers
- `semantic` standardized views for the five core domains
- `mart` aggregate views for business overview, inventory backlog, clearance, and annual summary
- `api` module views aligned to frontend modules
- `ops` metadata tables for runs, steps, freshness, and lineage

### Runtime Layer
- PostgreSQL dashboard service methods for the main dashboard flows
- PostgreSQL dashboard router behind `USE_POSTGRESQL_DASHBOARD_ROUTER`
- refresh runner with:
  - dependency ordering
  - SQL execution
  - retry
  - savepoint isolation
  - partial failure and skipped downstream handling
  - observability metadata writes

### Delivery Assets
- rollout guide
- switch quick guide
- retirement checklist
- pre-prod check report template
- ops checker script
- dashboard smoke script

## Coverage Snapshot

### Verified through `backend/tests/data_pipeline`
- SQL asset presence
- SQL execution in PostgreSQL containers
- KPI chain integration
- inventory / clearance chain integration
- route switching
- HTTP-level PostgreSQL dashboard responses
- refresh runner observability
- retry / partial failure behavior

Current command:

```bash
python -m pytest backend/tests/data_pipeline -q
```

Current result:

```text
72 passed
```

## Remaining Risks

1. Old `backend/routers/dashboard_api.py` still exists as the fallback path and should stay until pre-prod and production gray checks complete.
2. Not every PostgreSQL dashboard route has a full real-database HTTP integration test yet.
3. Operational rollout still depends on disciplined environment configuration and post-switch observation.

## Suggested Next Step

Move to pre-production gray validation:

1. Set `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
2. Run `python -m pytest backend/tests/data_pipeline -q`
3. Run `python scripts/smoke_postgresql_dashboard_routes.py --base-url <base_url>`
4. Run `python scripts/check_postgresql_dashboard_ops.py`
5. Fill out `POSTGRESQL_DASHBOARD_PREPROD_CHECK_REPORT_TEMPLATE.md`

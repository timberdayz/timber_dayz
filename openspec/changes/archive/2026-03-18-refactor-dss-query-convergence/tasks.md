## 1. OpenSpec Alignment

- [x] 1.1 Add spec deltas that define dashboards as DSS-first
- [x] 1.2 Add spec deltas that define materialized views as legacy compatibility only
- [x] 1.3 Validate the change with strict OpenSpec validation

## 2. Legacy MV Compatibility

- [x] 2.1 Add regression tests for the legacy `/api/mv` router async execution path
- [x] 2.2 Repair the router so `AsyncSession` usage is consistent
- [x] 2.3 Mark the router as legacy compatibility in code comments and API tags where practical
- [x] 2.4 Deprecate legacy Celery MV refresh tasks so they no longer execute refresh SQL

## 3. Follow-up Convergence

- [x] 3.1 Update application wiring and docs so `/api/mv` is no longer described as a preferred path
- [x] 3.2 Audit dashboard/query handlers for DSS-vs-MV conflicts and queue the next cleanup change set

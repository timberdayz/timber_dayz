# Business Overview Phase-1 Acceptance Report (2026-05-07)

## Acceptance Target (Phase-1)

- `bootstrap` cache MISS P95 < 10s
- `bootstrap` cache HIT P95 < 200ms

## What Changed

- Observability
  - Backend logs now include a breakdown for `/api/dashboard/business-overview/bootstrap` (kpi/comparison/operational).
  - PostgreSQL is configured to emit slow SQL statements to `docker logs` during acceptance (via `log_min_duration_statement`).
- Performance
  - `semantic.shop_identity_resolution_candidates` is backed by a materialized view (`*_mv`) with indexes and exposed via a stable same-name view.
  - Identity resolution LATERAL join changed from `IN (...)` to `VALUES (...) JOIN` in analytics semantic views.

## Evidence

### Cache MISS sampling

- Endpoint: `/api/dashboard/business-overview/bootstrap`
- Params: `granularity=monthly`, `date=2026-05-01`, `month=2026-05-01`, `platform=tiktok`
- Method: invalidate dashboard cache between requests, then request once
- Samples: 15
- Result: P95 (wall clock) ≈ 4.4s

### Cache HIT sampling

- Endpoint: `/api/dashboard/business-overview/bootstrap`
- Params: `granularity=monthly`, `date=2026-05-01`, `month=2026-05-01`, `platform=tiktok`
- Samples: 30
- Result: P95 (wall clock) ≈ 20ms

## Notes

- After acceptance, restore PostgreSQL `log_min_duration_statement` to `-1` to reduce log volume.


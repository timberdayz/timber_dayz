# Dashboard Slow Query Observability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it easy to pinpoint which dashboard sub-query (kpi/comparison/operational_metrics) causes slow requests, and make PostgreSQL emit the actual slow SQL statements to Docker logs.

**Architecture:** Add per-subcall timing logs in the `business-overview/bootstrap` router and enable Postgres `log_min_duration_statement` so slow SQL appears in `docker logs xihong_erp_postgres`. Keep the change low-risk and dev-only in behavior (logging only).

**Tech Stack:** FastAPI, SQLAlchemy asyncpg, Docker Postgres 15

---

### Task 1: Add bootstrap subcall timing logs

**Files:**
- Modify: `backend/domains/business/routers/dashboard_api_postgresql.py`

- [ ] **Step 1: Add per-subcall timers**
  - Measure `kpi`, `comparison`, `operational_metrics` durations using `time.perf_counter()`.
  - Log one structured line (warning) when total > 1s (or any subcall > 1s), including the three durations and request path/query.

- [ ] **Step 2: Run targeted tests**
  - Run: `pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -q`
  - Expected: exit 0

### Task 2: Enable Postgres slow SQL logging in Docker

**Files:**
- No repo changes required (runtime config)

- [ ] **Step 1: Set slow SQL threshold**
  - Run (inside container): `ALTER SYSTEM SET log_min_duration_statement = 2000;`
  - Run: `SELECT pg_reload_conf();`
  - Verify: `SHOW log_min_duration_statement;` returns `2s` (or `2000ms` depending on Postgres formatting)

- [ ] **Step 2: Verify slow SQL shows up**
  - Trigger a known slow dashboard request.
  - Tail logs: `docker logs --since 5m xihong_erp_postgres`
  - Expected: statements exceeding threshold appear with duration.

### Task 3: Acceptance check

**Files:**
- None

- [ ] **Step 1: Re-run dashboard endpoints**
  - Call `/api/dashboard/business-overview/bootstrap` and `/api/dashboard/business-overview/traffic-ranking`.
  - Confirm backend logs include subcall breakdown and Postgres logs include slow SQL statements.



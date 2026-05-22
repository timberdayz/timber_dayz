# Dashboard SQL Assets & Database Migration Rules

This document defines *enforced* rules for how we manage database schema, dashboard SQL assets, and startup behavior.

目标：避免“启动期 SQL 把服务搞挂”、避免多环境 schema 漂移、避免 SQL 资产不可回滚/不可追踪。

## 1) Responsibilities (SSOT)

### 1.1 Schema (tables/columns/indexes/constraints)

- **SSOT**: Alembic migrations.
- **Rule**: Any change to tables/columns/indexes/constraints MUST be delivered via Alembic migration scripts.
- **Rule**: Do not rely on `init_db()` to create/alter schema for shared environments.

### 1.2 Dashboard data assets (semantic/mart/api views, matviews, refresh pipeline)

- **SSOT**: PostgreSQL Dashboard bootstrap pipeline (SQL assets + registry).
- **Rule**: Dashboard assets must be **idempotent** and **re-runnable**.
- **Rule**: Startup must not perform large/slow bootstrap work in a way that can take down core API traffic.

### 1.3 `init_db()`

- **Role**: Local developer convenience only (empty DB bring-up).
- **Rule**: Production MUST NOT depend on `init_db()` for correctness.
- **Rule**: For non-production, `init_db()` is allowed only as a fallback; Alembic remains the preferred path.

## 2) Environment policy

### 2.1 Startup bootstrap

- **Development / Local**:
  - Auto bootstrap may run for convenience.
  - Bootstrap failures MUST NOT crash the entire API server. Failures should be logged and dashboard endpoints should degrade gracefully.
- **Production**:
  - Prefer **deploy-time** bootstrap (explicit command) and **startup-time inspect** only.
  - If auto bootstrap is enabled in production, failure should be treated as a deployment failure (not a partial, silent state).

### 2.2 Recommended env flags

- `AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP`
  - `true` in local development if desired
  - `false` in production by default
- `DATA_SYNC_STRICT_ALLOWED_ROOTS`
  - `false` in local development
  - `true` in production

## 3) SQL asset hygiene rules (prevent “坏 SQL”进入主干)

### 3.1 Encoding and corruption

- **Rule**: SQL asset files must be UTF-8 readable.
- **Rule**: SQL asset files must NOT contain NUL bytes.
- **Rule**: SQL asset files must NOT contain the Unicode replacement character `�` (usually indicates encoding corruption).
- **Rule**: Quoted identifiers must not contain `?` or `�` (high chance of corrupted column names).

### 3.2 Dynamic SQL restriction

Dynamic SQL blocks like `DO $$ ... EXECUTE ... $$` are higher risk.

- **Rule**: New dynamic SQL in dashboard assets requires explicit review and must be added to the allowlist.
- **Rule**: Prefer static `CREATE OR REPLACE VIEW ...` / `CREATE MATERIALIZED VIEW ...` whenever possible.

## 4) How to work (developer workflow)

### 4.1 Schema change checklist

1. Update SQLAlchemy models (SSOT).
2. Generate Alembic migration (`alembic revision --autogenerate` when safe).
3. Run `alembic upgrade head` locally.
4. Add/adjust contracts tests if needed.

### 4.2 Dashboard asset change checklist

1. Edit SQL asset file(s).
2. Run asset hygiene check (see `scripts/verify_sql_asset_hygiene.py`).
3. Run bootstrap inspect/apply locally:
   - `python scripts/bootstrap_postgresql_dashboard.py --check`
   - `python scripts/bootstrap_postgresql_dashboard.py`
4. Ensure failure mode is non-blocking in dev; blocking in prod deploy step.


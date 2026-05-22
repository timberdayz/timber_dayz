# Dashboard Architecture

The active Dashboard direction is PostgreSQL-first.

## Runtime Direction

- PostgreSQL assets are the active runtime query path.
- Metabase is historical-only and must not be used as the default path for new production Dashboard work.
- New Dashboard work should prefer PostgreSQL semantic, mart, and API-layer assets.

## Data Flow

```text
b_class raw -> semantic -> mart -> api -> backend router -> frontend
```

## Layer Ownership

- `b_class`: raw collected data
- `sql/semantic/`: standardization and normalization
- `sql/mart/`: reusable aggregates
- `sql/api_modules/`: page-module query contracts
- `backend/routers/dashboard_api_postgresql.py`: backend route entrypoint
- `frontend/src/api/`: frontend API access

## Rules

- Do not add new production Dashboard dependencies on Metabase when equivalent PostgreSQL assets exist.
- Keep SQL assets idempotent and re-runnable.
- Prefer existing semantic and mart layers before adding page-specific SQL.
- Keep page-facing contracts in the API layer stable and explicit.

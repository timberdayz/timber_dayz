# Metabase legacy asset status

Metabase assets in this repository are retained for fallback/debug only.
They are no longer the primary dashboard architecture.

Current primary path:

- `b_class raw -> semantic -> mart -> api -> backend -> frontend`
- runtime switch: `USE_POSTGRESQL_DASHBOARD_ROUTER=true`

Retained for fallback/debug only:

- `backend/routers/metabase_proxy.py`
- `backend/services/metabase_question_service.py`
- `config/metabase_config.yaml`
- `docker-compose.metabase.yml`
- `docker-compose.metabase.dev.yml`

Retention policy:

- keep available while rollback is still required
- do not use for new dashboard features
- do not treat as the default runtime path
- archive or delete only after PostgreSQL dashboard production gray finishes and rollback is no longer required

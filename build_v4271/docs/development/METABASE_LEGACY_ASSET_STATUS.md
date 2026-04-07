# Metabase legacy asset status

Metabase assets in this repository are retained as historical assets only.
They are no longer part of the runtime dashboard architecture.

Current primary path:

- `b_class raw -> semantic -> mart -> api -> backend -> frontend`
- PostgreSQL Dashboard is the only runtime path

Historical assets still present in the repository:

- `archive/metabase/backend/routers/dashboard_api.py`
- `archive/metabase/backend/routers/metabase_proxy.py`
- `archive/metabase/backend/services/metabase_question_service.py`
- `archive/metabase/scripts/init_metabase.py`
- `archive/metabase/scripts/verify_deploy_phase35_local.py`
- `archive/metabase/scripts/verify_deploy_full_local.py`
- `archive/metabase/config/metabase_config.yaml`
- `archive/metabase/docker/docker-compose.metabase.yml`
- `archive/metabase/docker/docker-compose.metabase.dev.yml`
- `archive/metabase/docker/docker-compose.metabase.4c8g.yml`
- `archive/metabase/docker/docker-compose.metabase.lockdown.yml`

Policy:

- do not use for new dashboard features
- do not treat as runtime dependencies
- archive or delete when historical scripts and references are cleaned up

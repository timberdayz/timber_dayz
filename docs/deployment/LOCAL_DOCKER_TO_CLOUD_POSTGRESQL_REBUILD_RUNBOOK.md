# Local Docker To Cloud PostgreSQL Rebuild Runbook

## Purpose

Use the local Docker PostgreSQL database as the source of truth and perform a controlled rebuild or full restore of the cloud PostgreSQL database.

This runbook is intended for cases where:
- the cloud database has drifted from the local authoritative dataset
- the historical Alembic chain is not reliable for fresh-db bootstrap
- production release should use image deployment plus database restore, not full-chain fresh migration replay

## Preconditions

- Local Docker PostgreSQL is verified and contains the intended production dataset
- Cloud PostgreSQL credentials are valid
- A maintenance window is approved
- Cloud application containers can be stopped during restore
- A rollback backup will be created before any destructive action

## Source And Target

- Source: local Docker PostgreSQL `xihong_erp_postgres`
- Target: cloud PostgreSQL `xihong_erp`

## Safety Rules

- Always create a cloud backup immediately before restore
- Never restore over a running application stack
- Verify row counts and schema/version after restore before reopening traffic
- Keep the backup file until post-restore validation is complete

## Phase 1. Validate Local Source

Run on local machine:

```powershell
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -Atc "show search_path; select version_num from core.alembic_version;"
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -Atc "select count(*) from core.collection_configs;"
docker exec xihong_erp_postgres sh -lc "pg_dump -U erp_user -d xihong_erp -Fc -f /tmp/xihong_local.dump && ls -lh /tmp/xihong_local.dump"
docker cp xihong_erp_postgres:/tmp/xihong_local.dump xihong_local.dump
```

Expected:
- `search_path` is `core, a_class, b_class, c_class, finance, public`
- `core.alembic_version` is the intended release revision
- dump file is created successfully

## Phase 2. Backup Cloud Before Restore

Run on cloud server:

```bash
docker exec xihong_erp_postgres sh -lc "pg_dump -U erp_user -d xihong_erp -Fc -f /tmp/cloud_before_restore.dump"
docker cp xihong_erp_postgres:/tmp/cloud_before_restore.dump /home/deploy/cloud_before_restore.dump
ls -lh /home/deploy/cloud_before_restore.dump
```

Do not continue if this backup is missing.

## Phase 3. Stop Application Traffic

Stop cloud application containers but keep PostgreSQL available:

```bash
docker rm -f xihong_erp_backend xihong_erp_celery_worker xihong_erp_celery_beat xihong_erp_nginx
```

Optional:
- keep frontend stopped as well if you want zero read traffic during restore

## Phase 4. Rebuild Cloud Database

Upload `xihong_local.dump` to the cloud host, then run:

```bash
docker exec xihong_erp_postgres psql -U erp_user -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='xihong_erp' and pid <> pg_backend_pid();"
docker exec xihong_erp_postgres dropdb -U erp_user xihong_erp
docker exec xihong_erp_postgres createdb -U erp_user xihong_erp
docker cp /home/deploy/xihong_local.dump xihong_erp_postgres:/tmp/xihong_local.dump
docker exec xihong_erp_postgres pg_restore -U erp_user -d xihong_erp --no-owner --no-privileges /tmp/xihong_local.dump
docker exec xihong_erp_postgres psql -U erp_user -d postgres -c "ALTER DATABASE xihong_erp SET search_path = core, a_class, b_class, c_class, finance, public;"
```

## Phase 5. Verify Database Before Reopening

Run on cloud server:

```bash
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -Atc "show search_path; select version_num from core.alembic_version;"
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -Atc "select count(*) from core.collection_configs;"
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -Atc "select table_schema||'.'||table_name from information_schema.tables where table_schema='finance' and table_name in ('shop_profit_basis','follow_investments','follow_investment_settlements','follow_investment_details') order by 1;"
```

Recommended parity checks:
- row counts for `core.collection_configs`
- row counts for `core.collection_config_shop_scopes`
- row counts for `core.shop_accounts`
- row counts for `core.main_accounts`
- row counts for `finance.follow_investments` and `finance.shop_profit_basis`

If any critical count is off, stop and investigate before reopening traffic.

## Phase 6. Restart Application

```bash
cd /opt/xihong_erp
COMPOSE_PROJECT_NAME=xihong_erp docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud-4c8g.yml --profile production up -d --remove-orphans
COMPOSE_PROJECT_NAME=xihong_erp docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud-4c8g.yml --profile production ps
```

Then verify externally:

```bash
curl -k https://www.xihong.site/api/health
```

Expected:
- backend healthy
- nginx healthy
- health endpoint returns `200`

## Rollback

If restore validation fails:

```bash
docker exec xihong_erp_postgres dropdb -U erp_user xihong_erp
docker exec xihong_erp_postgres createdb -U erp_user xihong_erp
docker cp /home/deploy/cloud_before_restore.dump xihong_erp_postgres:/tmp/cloud_before_restore.dump
docker exec xihong_erp_postgres pg_restore -U erp_user -d xihong_erp --no-owner --no-privileges /tmp/cloud_before_restore.dump
docker exec xihong_erp_postgres psql -U erp_user -d postgres -c "ALTER DATABASE xihong_erp SET search_path = core, a_class, b_class, c_class, finance, public;"
```

Restart the application only after rollback verification passes.

## Recommendation

For production releases:
- deploy images normally
- validate critical schema contracts in CI
- treat local Docker PostgreSQL as the authoritative rebuild source when cloud drift occurs
- do not block production release on a full historical fresh-db Alembic replay until the migration chain is formally rebuilt

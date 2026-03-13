# deployment-ops Specification

## Purpose
定义生产环境部署与运维的基线规范，确保系统在生产部署后能够达到最小可用状态（可访问、可登录、可运行任务），并规范敏感配置管理和环境变量处理流程。
## Requirements
### Requirement: Production deployment SHALL include Day-1 Bootstrap
The system SHALL provide an idempotent Day-1 Bootstrap procedure for production deployments to ensure the application reaches a minimal usable state after deployment.

#### Scenario: First-time deployment to an empty database
- **WHEN** a release tag is deployed to a server with an empty PostgreSQL database
- **THEN** database migrations are applied successfully
- **AND** required baseline data (e.g., roles) are created if missing
- **AND** the application becomes healthy and reachable

#### Scenario: Re-deployment to an existing database
- **WHEN** a release tag is deployed to a server with an existing PostgreSQL database
- **THEN** the bootstrap procedure runs without harmful side effects
- **AND** migrations and bootstrap steps are safe to re-run (idempotent)

### Requirement: Production deployment MUST apply database migrations
The system MUST apply Alembic migrations during production deployment to ensure schema matches the running code version.

#### Scenario: Schema upgrade required
- **WHEN** a release includes new Alembic revisions
- **THEN** deployment runs `alembic upgrade head` successfully before starting application services
- **AND** deployment fails fast if migrations fail

### Requirement: Secrets MUST NOT be logged
The system MUST NOT log secrets in CI/CD logs or runtime logs.

#### Scenario: Deployment diagnostics on misconfiguration
- **WHEN** deployment fails due to misconfiguration (e.g., wrong Redis password)
- **THEN** logs include actionable diagnostics
- **AND** logs do not include plaintext secrets (only masked or presence indicators)

### Requirement: Admin bootstrap MUST be safe-by-default
The system MUST NOT create or modify a production admin user unless explicitly enabled, and MUST only do so under safe conditions.

#### Scenario: Default deployment does not create admin
- **WHEN** a release tag is deployed with bootstrap enabled but admin creation not explicitly enabled
- **THEN** no admin user is created or modified
- **AND** the system remains deployable and healthy

#### Scenario: Admin creation only allowed when no superuser exists
- **WHEN** admin creation is explicitly enabled (via `BOOTSTRAP_CREATE_ADMIN=true` environment variable)
- **AND** the database contains at least one existing superuser/admin account
- **THEN** the bootstrap procedure MUST NOT create or overwrite an admin account
- **AND** it MUST emit a non-sensitive warning indicating why it was skipped

#### Scenario: Superuser/admin account definition
- **WHEN** bootstrap checks for existing admin accounts
- **THEN** a "superuser/admin account" is defined as any user satisfying ANY of the following conditions:
  - `is_superuser = True`, OR
  - Bound to a role with `role_code == "admin"`, OR
  - Bound to a role with `role_name == "admin"`
- **AND** the bootstrap MUST check all three conditions before allowing admin creation

#### Scenario: Admin creation environment variables
- **WHEN** admin creation is enabled
- **THEN** the following environment variables MUST be defined:
  - `BOOTSTRAP_CREATE_ADMIN` (must be `true` to enable, default: `false`)
  - `BOOTSTRAP_ADMIN_USERNAME` (optional, default: `admin`)
  - `BOOTSTRAP_ADMIN_PASSWORD` (required, must not be default value)
  - `BOOTSTRAP_ADMIN_EMAIL` (optional, default: `admin@xihong.com`)
- **AND** all values MUST come from server `.env` file or secrets file (not hardcoded)

#### Scenario: Admin password is never defaulted or logged
- **WHEN** admin creation is explicitly enabled
- **THEN** the admin password MUST come from a secret source (not a default value)
- **AND** the password MUST NOT be printed in logs

### Requirement: Secrets sources and precedence MUST be defined
The system MUST define the precedence of secret sources for production deployments and MUST forbid unsafe defaults for production.

#### Scenario: Secret precedence is deterministic
- **WHEN** multiple sources provide the same secret key (e.g., JWT secret)
- **THEN** the deployment uses a deterministic precedence order
- **AND** the chosen source can be diagnosed without revealing the secret value

#### Scenario: Production forbids default secrets
- **WHEN** ENVIRONMENT is `production`
- **THEN** deployment MUST fail fast if any required secret uses a known default placeholder

### Requirement: Environment variable loading MUST be robust
The system MUST robustly load environment variables for production deployments, including normalization of CRLF line endings and trailing whitespace.

#### Scenario: CRLF `.env` file
- **WHEN** the server `.env` file uses CRLF line endings
- **THEN** the deployment MUST clean the `.env` file before passing it to Docker Compose (remove `\r` and trailing whitespace)
- **AND** the cleaning command MUST use full path: `sed -e 's/\r$//' -e 's/[ \t]*$//' "${PRODUCTION_PATH}/.env" > "${PRODUCTION_PATH}/.env.cleaned"`
- **AND** all `docker-compose` commands MUST use `--env-file "${PRODUCTION_PATH}/.env.cleaned"` (not rely on automatic `.env` reading, use full path)
- **AND** environment variables are parsed correctly in containers
- **AND** authentication/connection checks do not fail due to hidden `\r`
- **AND** the bootstrap script MUST validate that critical environment variables do not contain `\r` (fail fast if detected)

### Requirement: Bootstrap MUST be idempotent and concurrency-safe
The bootstrap procedure MUST be safe to run multiple times concurrently without harmful side effects.

#### Scenario: Concurrent bootstrap execution
- **WHEN** bootstrap is executed multiple times concurrently (e.g., retry after timeout)
- **THEN** no duplicate baseline data (roles, permissions) are created
- **AND** no duplicate admin users are created
- **AND** database unique constraints prevent duplicate entries
- **AND** all database operations are wrapped in transactions

#### Scenario: Idempotent baseline data creation
- **WHEN** bootstrap creates baseline data (roles, permissions)
- **THEN** it uses upsert logic (check existence + insert or skip)
- **AND** it uses database unique constraints as the primary protection mechanism
- **AND** it handles `ON CONFLICT DO NOTHING` or equivalent gracefully

#### Scenario: Required baseline roles
- **WHEN** bootstrap creates baseline roles
- **THEN** the following roles MUST be created if missing:
  - `role_code: "admin"`, `role_name: "管理员"`, `is_system: true`
  - `role_code: "manager"`, `role_name: "主管"`, `is_system: false`
  - `role_code: "operator"`, `role_name: "操作员"`, `is_system: false`
  - `role_code: "finance"`, `role_name: "财务"`, `is_system: false`
- **AND** roles are identified by `role_code` (unique constraint)
- **AND** if a role already exists, bootstrap MUST skip creation (idempotent)

#### Scenario: Bootstrap transaction atomicity
- **WHEN** bootstrap executes multiple steps (e.g., create roles, create admin user)
- **AND** a later step fails
- **THEN** all database operations MUST be rolled back (transaction atomicity)
- **AND** bootstrap MUST be safe to retry without manual cleanup
- **AND** bootstrap MUST output non-sensitive diagnostic information on failure

### Requirement: Migration failure MUST have a recovery path
The system MUST document and support a recovery path when migrations fail during deployment.

#### Scenario: Migration failure blocks deployment with actionable guidance
- **WHEN** `alembic upgrade head` fails during deployment
- **THEN** deployment stops before starting application services
- **AND** logs include actionable steps to recover (without revealing secrets)

### Requirement: Migration scripts SHALL be self-contained for schema dependencies
Alembic migration scripts that move tables into named schemas (e.g. `a_class`, `c_class`) SHALL create those schemas within the same migration's `upgrade()` before performing any table moves, so that a fresh database run of the full migration chain does not depend on the order of other migrations that create the schema.

#### Scenario: Fresh database full migration
- **WHEN** `alembic upgrade heads` is run on a brand-new PostgreSQL database (e.g. CI or temporary container)
- **THEN** no migration SHALL fail with "schema \"a_class\" does not exist" (or equivalent for `c_class`)
- **AND** any migration that moves tables into `a_class` or `c_class` SHALL execute `CREATE SCHEMA IF NOT EXISTS a_class` and `CREATE SCHEMA IF NOT EXISTS c_class` at the start of its `upgrade()` before moving tables

### Requirement: Local full-deploy verification SHALL fail when Phase 2 migration fails
The local full-deploy verification script (e.g. `verify_deploy_full_local.py`) SHALL treat Phase 2 (`alembic upgrade heads`) failure as a hard failure: it SHALL exit with non-zero status and SHALL NOT proceed to Phase 2.5 or later phases.

#### Scenario: Phase 2 migration failure stops verification
- **WHEN** Phase 2 runs `alembic upgrade heads` and it returns a non-zero exit code
- **THEN** the script SHALL print the migration command output (e.g. last N lines or full output)
- **AND** the script SHALL exit with return code 1
- **AND** Phase 2.5 and subsequent phases SHALL NOT be executed

### Requirement: Fresh-db migration gate script SHALL be provided and SHALL not touch development data
The project SHALL provide a script (e.g. `scripts/validate_migrations_fresh_db.py`) that runs `alembic upgrade heads` against a **temporary** PostgreSQL instance (e.g. a short-lived container on a non-default port such as 5433), equivalent to CI's "Validate Database Migrations" gate, and SHALL NOT modify or delete the development database or existing Compose Postgres volumes.

#### Scenario: Temporary Postgres and successful migration
- **WHEN** the user runs the fresh-db migration gate script (e.g. `python scripts/validate_migrations_fresh_db.py`)
- **THEN** the script SHALL start a temporary Postgres container (e.g. `docker run --rm -d ... -p 5433:5432 postgres:15`) with a dedicated test database
- **AND** after Postgres is ready, the script SHALL set `DATABASE_URL` to point at that temporary instance and run `alembic upgrade heads` from the project root
- **AND** on success the script SHALL exit with code 0 and SHALL stop/remove the temporary container before exiting

#### Scenario: Temporary Postgres and migration failure
- **WHEN** `alembic upgrade heads` fails inside the fresh-db migration gate script
- **THEN** the script SHALL exit with non-zero code and SHALL print the migration output
- **AND** the script SHALL stop/remove the temporary container before exiting

#### Scenario: No impact on development database
- **WHEN** the fresh-db migration gate script runs
- **THEN** it SHALL NOT connect to, truncate, or drop the development database (e.g. default port 5432 or existing Compose Postgres)
- **AND** it SHALL NOT perform `docker-compose down -v` or any operation that removes development data volumes

### Requirement: Deployment documentation SHALL describe local vs cloud database relationship and fresh-db gate
The deployment and local verification documentation (e.g. `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`) SHALL include: (1) that local Docker Postgres and cloud Postgres have no data sync and rely on the same migration files being run in each environment; (2) that for release alignment with CI, users may run the fresh-db migration gate script then the full local verification script; (3) a checklist item for the fresh-db migration gate; (4) a mapping that the fresh-db gate corresponds to CI's "Validate Database Migrations"; (5) that no option to wipe the development database (e.g. `--fresh-db`) is provided, to avoid accidental data loss.

#### Scenario: Local vs cloud DB relationship documented
- **WHEN** a maintainer reads the deployment/local verification doc
- **THEN** a dedicated section SHALL state that local Docker Postgres and cloud Postgres are not synchronized
- **AND** it SHALL state that schema consistency is achieved by running the same Alembic migrations in each environment

#### Scenario: Fresh-db gate in checklist and CI mapping
- **WHEN** a maintainer follows the local verification checklist
- **THEN** the checklist SHALL include an item: run `python scripts/validate_migrations_fresh_db.py` (migration gate on a fresh temporary Postgres, without touching the dev DB)
- **AND** the doc SHALL map this step to CI's "Validate Database Migrations" job
- **AND** the doc SHALL state that there is no `--fresh-db` or equivalent that clears the development database

### Requirement: Local and cloud deployments SHALL be distinguished by configuration and optional Docker image variant
The system SHALL support two deployment roles from the same codebase: **local** (collection, data sync, and local-to-cloud sync) and **cloud** (system operation only: dashboards, reports, API). The role SHALL be determined at runtime by configuration (e.g. `ENABLE_COLLECTION` or `DEPLOYMENT_ROLE`). When an image registry is used, the build SHALL support an optional variant that includes Playwright and browser dependencies for the local role; the cloud deployment SHALL use an image built without Playwright.

#### Scenario: Cloud deployment does not start collection scheduler
- **WHEN** the application starts with `ENABLE_COLLECTION=false` (or `DEPLOYMENT_ROLE=cloud`)
- **THEN** the collection scheduler SHALL NOT be created or started
- **AND** the application SHALL remain healthy and serve API and dashboards from the cloud database

#### Scenario: Local deployment starts collection scheduler
- **WHEN** the application starts with `ENABLE_COLLECTION=true` (or `DEPLOYMENT_ROLE=local`)
- **THEN** the collection scheduler MAY be created and started according to existing schedule configuration
- **AND** the same codebase SHALL be used as for cloud deployment

#### Scenario: Docker build argument controls Playwright installation
- **WHEN** the production Docker image is built with `--build-arg INSTALL_PLAYWRIGHT=false` (or omitted)
- **THEN** Playwright and browser dependencies SHALL NOT be installed in the image
- **AND** this image SHALL be suitable for cloud deployment

#### Scenario: Full image variant includes Playwright for local deployment
- **WHEN** the production Docker image is built with `--build-arg INSTALL_PLAYWRIGHT=true`
- **THEN** Playwright and required browser dependencies (e.g. Chromium) SHALL be installed in the image
- **AND** this image SHALL be suitable for the local (collection) deployment

#### Scenario: Deployment and daily operation flows are documented
- **WHEN** a maintainer or operator follows the deployment documentation
- **THEN** the documentation SHALL describe: (1) how to release a version (tag, push, CI building two images), (2) cloud deployment steps (pull default image, set ENABLE_COLLECTION=false, start), (3) local deployment steps (pull -full image, set ENABLE_COLLECTION=true and CLOUD_DATABASE_URL, configure Cron for local-to-cloud sync, start), (4) daily operation flow (four time slots for collection and data sync, staggered local-to-cloud sync, cloud read-only)

### Requirement: Deployment documentation SHALL describe cloud Metabase access URL and first-time setup
Deployment and operations documentation SHALL include a dedicated section or document describing how to access Metabase on a cloud deployment and how to complete first-time setup so that Metabase and backend proxy (e.g. Dashboard KPI, init_metabase.py) become usable.

#### Scenario: Maintainer follows doc to access and initialize cloud Metabase
- **WHEN** a maintainer or operator reads the deployment documentation after a first-time cloud deployment
- **THEN** the documentation SHALL state that cloud Metabase is only reachable at `http://<domain-or-IP>/metabase/` (no separate host port; Nginx reverse proxy)
- **AND** the documentation SHALL list the steps to complete first-time setup in the browser: setup wizard, create admin account, add PostgreSQL data source (same as backend business DB), create API Key in Metabase admin, and set `METABASE_API_KEY` in server `.env`
- **AND** the documentation SHALL describe that when using IP or a non-default domain, `MB_SITE_URL` and Nginx `proxy_set_header Host` SHALL match the actual access URL to avoid white screen or redirect errors
- **AND** the documentation SHALL warn about the Nginx variable `proxy_pass` trap: when using `set $var` + `proxy_pass http://$var` (for delayed DNS resolution), a `rewrite` directive MUST be used to strip the location prefix manually; otherwise the upstream receives the original path with prefix and returns wrong content (e.g. SPA HTML fallback with `Content-Type: text/html` for JS requests, causing MIME type white screen)

### Requirement: Production deployment on 4核8G cloud SHALL use resource-optimized configuration
When deploying to a production cloud server with 4 cores and 8GB RAM, the system SHALL provide and use resource-optimized Docker Compose overlays and environment variables to prevent OOM and system freeze, and SHALL document the recommended configuration.

#### Scenario: Metabase memory limits on 4核8G
- **WHEN** Metabase is deployed alongside the main stack on a 4核8G server
- **THEN** Metabase container memory limit SHALL be at most 2G
- **AND** Metabase JVM heap SHALL be configured with `-Xmx1g -Xms512m` or equivalent
- **AND** total memory limits (main stack + Metabase) SHALL be at most approximately 7G to reserve 1–1.5G for the OS
- **AND** deployment or validation SHALL verify total memory limits via `docker-compose config` or equivalent before deployment

#### Scenario: Compose overlay for 4核8G
- **WHEN** deploying to a 4核8G server
- **THEN** the deployment MAY use a dedicated overlay file (e.g., `docker-compose.cloud-4c8g.yml`) that adjusts backend workers and optionally celery concurrency
- **AND** the deployment MAY use a Metabase overlay (e.g., `docker-compose.metabase.4c8g.yml`) that sets Metabase resource limits as specified above
- **AND** deployment documentation SHALL describe the compose command and overlay usage for 4核8G, including that overlay files MUST be loaded after their base files (cloud-4c8g after cloud, metabase-4c8g after metabase)
- **AND** for production environments without collection, celery-worker concurrency SHALL remain low (e.g., 2–3) because it runs only scheduled tasks (backup, alerts), not Playwright-based collection

#### Scenario: Environment variables for 4核8G production (without collection)
- **WHEN** configuring production `.env` for a 4核8G server where production does NOT run collection
- **THEN** `RESOURCE_MONITOR_ENABLED` SHALL be set to `true`
- **AND** `RESOURCE_MONITOR_MEMORY_THRESHOLD` SHALL be set (e.g., 85) to enable memory alerting
- **AND** `MAX_COLLECTION_TASKS` SHALL NOT be required (production does not run collection; this variable is only for collection environment)

#### Scenario: .env.production as template for cloud .env
- **WHEN** deploying to a 4核8G production server
- **THEN** deployment documentation SHALL state that `.env.production` (local, gitignored) content SHALL match the cloud server `.env` (default `PRODUCTION_PATH/.env`, typically `/opt/xihong_erp/.env`)
- **AND** the deployer SHALL copy `.env.production` content to the cloud `.env` as a deployment step
- **AND** the implementation SHALL update `env.production.example` (committed template) with 4c8g variables, and CLOUD_4C8G_REFERENCE SHALL list the variables to add or change

#### Scenario: Emergency response for Metabase-induced freeze
- **WHEN** the production server freezes or becomes unresponsive, and Metabase is suspected
- **THEN** deployment documentation SHALL describe the emergency procedure (e.g., via VNC/console: `docker stop <metabase-container>`, then check `free -h` and `docker stats`)
- **AND** the procedure SHALL be discoverable in deployment or operations docs

#### Scenario: Deploy script and overlay loading for 4核8G
- **WHEN** deploying to a 4核8G production server
- **THEN** deployment documentation SHALL explicitly state that the deploy script (e.g., deploy_remote_production.sh) does NOT automatically load cloud-4c8g and metabase-4c8g overlays
- **AND** 4核8G users MUST either add overlay loading logic to the deploy script (e.g., via CLOUD_PROFILE=4c8g) or run compose manually with overlay files appended; otherwise Metabase memory limits will NOT take effect (Metabase will remain at 4G limit)
- **AND** the deployment checklist SHALL include a "4c8g overlay loaded" verification step

#### Scenario: Redis configuration and data flow documentation on 4核8G
- **WHEN** deploying to a 4核8G production server
- **THEN** deployment documentation SHALL describe Redis roles (Celery broker, result backend, rate limiter, Dashboard/query cache) and capacity assessment (e.g., 220M)
- **AND** deployment or architecture documentation SHALL describe the actual data flow: PostgreSQL <- Metabase (query) -> Backend (calls Metabase API) -> Redis (Backend writes/reads cache) -> Backend -> Frontend
- **AND** documentation SHALL clarify that the Frontend only calls the Backend API and does not access Redis directly; the Backend is the intermediary between Metabase and Redis

#### Scenario: Redis hardening on 4核8G (short-term optimization)
- **WHEN** deploying to a 4核8G production server
- **THEN** Redis SHALL be configured with `maxmemory=220m` and `maxmemory-policy=volatile-lru` (to avoid evicting Celery broker keys; note: Celery result keys have TTL and MAY be evicted when memory is tight)
- **AND** CacheService `delete_pattern` and maintenance_service `clear_cache` SHALL use SCAN instead of KEYS to avoid blocking
- **AND** the maintenance API (`GET /api/system/maintenance/cache/status`) MAY expose CacheService hit rate (hits, misses, hit_rate; per-worker sampling when multiple workers)

#### Scenario: Connection pool recommendation for 4核8G
- **WHEN** configuring production `.env` for a 4核8G server
- **THEN** deployment documentation SHALL recommend `DB_POOL_SIZE=30` and `DB_MAX_OVERFLOW=30` for Backend to support 50+ concurrent users
- **AND** documentation SHALL explain the relationship between Backend + Metabase + Celery connection counts and Postgres `max_connections`

#### Scenario: Slow query monitoring on 4核8G
- **WHEN** deploying to a 4核8G production server
- **THEN** production Postgres SHALL have `shared_preload_libraries=pg_stat_statements` and `log_min_duration_statement` (e.g., 1000ms) configured, requiring postgresql.conf or command change and Postgres restart
- **AND** deployment documentation SHALL describe configuration steps, and that `docker/postgres/init_monitoring.sql` (for `v_top_slow_queries`) requires manual DBA execution or addition to sql/init
- **AND** deployment checklist SHALL include a "slow query monitoring enabled" verification step (e.g. manual check of `SHOW shared_preload_libraries`)

#### Scenario: Scope - no separate Metabase deployment
- **WHEN** applying this change for short-term optimization
- **THEN** Metabase SHALL remain co-located with the main stack on the same server
- **AND** this change does NOT include separate Metabase deployment; that MAY be planned in a future change

### Requirement: 4c8g single-server follow-up optimizations SHALL be available
On a single 4-core 8GB production server (after `optimize-cloud-4c8g-production-config`), the system SHALL support the following in-server optimizations: Backend health check/circuit breaker for Metabase, frontend Dashboard timeout and error messaging, RESOURCE_MONITOR alerting (DingTalk/email/Webhook), cache warmup (startup or scheduled), write-through cache invalidation on data change, and Postgres `statement_timeout` configuration. The system SHALL NOT require Metabase Guest embedding evaluation or Redis/Celery separation to another instance for these optimizations.

#### Scenario: Metabase unhealthy or slow
- **WHEN** Backend calls Metabase API and Metabase is unhealthy or repeatedly times out
- **THEN** Backend SHALL fail fast with a clear error response instead of hanging
- **AND** optional health check or circuit breaker SHALL be documented for operators

#### Scenario: Dashboard request timeout or error
- **WHEN** the frontend requests Dashboard data and the request times out or returns an error (e.g. 5xx)
- **THEN** the frontend SHALL show a clear timeout or error message to the user
- **AND** the user SHALL not be left with a blank screen or misleading state

#### Scenario: Resource monitor threshold exceeded
- **WHEN** RESOURCE_MONITOR detects memory or CPU above configured thresholds
- **THEN** the system SHALL support sending alerts to at least one of: DingTalk, email, or Webhook
- **AND** alert configuration SHALL be driven by environment variables or config, not hardcoded

#### Scenario: Cache warmup for Dashboard
- **WHEN** Backend starts or a scheduled job runs
- **THEN** the system MAY warm up cache for Dashboard hotspot questions (e.g. KPI, comparison, shop racing)
- **AND** warmup scope and frequency SHALL be documented to avoid excessive load on Metabase/DB

#### Scenario: Cache invalidation on data change
- **WHEN** critical data changes (e.g. sync completion, config/target updates)
- **THEN** the system SHALL invalidate related cache keys (e.g. Dashboard-related prefix) so subsequent requests get fresh data
- **AND** which changes trigger invalidation and key naming SHALL be documented

#### Scenario: Postgres statement timeout
- **WHEN** production Postgres is used on the 4c8g single server
- **THEN** the deployment SHALL document how to set `statement_timeout` (e.g. 50–60s, and not above the Backend->Metabase HTTP timeout of 60s) to limit long-running queries
- **AND** the documentation SHALL note that changes require restart or affect only new connections and SHOULD be applied in a maintenance window, and MAY describe how to use role/session-level overrides for rare heavy reports instead of raising the global timeout beyond 120s

#### Scenario: Future considerations (out of scope)
- **WHEN** documenting or planning further optimizations
- **THEN** CLOUD_4C8G_REFERENCE SHALL include an "advanced/future planning" section describing optional follow-up work
- **AND** future considerations MAY include: Redis and Celery separation, Metabase standalone deployment, Metabase Guest embedding evaluation (Guest embedding is suitable only for single standalone report pages, NOT for multi-dimensional integrated pages like business overview with complex filtering)
- **AND** Backend->Metabase timeout (currently 60s in MetabaseQuestionService) SHALL be documented; adjust if Metabase queries frequently exceed it


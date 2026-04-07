## ADDED Requirements

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
- **AND** deployment or architecture documentation SHALL describe the actual data flow: PostgreSQL ← Metabase (query) → Backend (calls Metabase API) → Redis (Backend writes/reads cache) → Backend → Frontend
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

#### Scenario: Future considerations (out of scope)

- **WHEN** documenting or planning further optimizations
- **THEN** CLOUD_4C8G_REFERENCE SHALL include an "advanced/future planning" section describing optional follow-up work
- **AND** future considerations MAY include: Backend health check/circuit breaker for Metabase, frontend Dashboard timeout and error handling, RESOURCE_MONITOR alert integration (e.g. DingTalk/email/Webhook), Redis and Celery separation, cache warming, write-through cache invalidation, Metabase standalone deployment, Postgres statement_timeout, Metabase Guest embedding evaluation (Guest embedding is suitable only for single standalone report pages, NOT for multi-dimensional integrated pages like business overview with complex filtering)
- **AND** Backend→Metabase timeout (currently 60s in MetabaseQuestionService) SHALL be documented; adjust if Metabase queries frequently exceed it

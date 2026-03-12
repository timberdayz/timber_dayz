## ADDED Requirements

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
- **THEN** the deployment SHALL document how to set `statement_timeout` (e.g. 50–60s, and not above the Backend→Metabase HTTP timeout of 60s) to limit long-running queries
- **AND** the documentation SHALL note that changes require restart or affect only new connections and SHOULD be applied in a maintenance window, and MAY describe how to use role/session-level overrides for rare heavy reports instead of raising the global timeout beyond 120s

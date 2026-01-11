## ADDED Requirements

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


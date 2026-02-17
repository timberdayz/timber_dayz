## ADDED Requirements

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

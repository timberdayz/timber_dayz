## ADDED Requirements

### Requirement: Migration Pre-run on Staging
All Alembic migrations MUST be executed on a staging environment before production deployment. High-risk migrations MUST include backup confirmation, rollback steps, execution window, and a responsible person.

#### Scenario: Standard migration pre-run
- **WHEN** a new Alembic migration is ready for deployment
- **THEN** it MUST be executed on staging first and verified before production

#### Scenario: High-risk migration checklist
- **WHEN** a migration involves data changes, column drops, or table renames
- **THEN** the migration PR MUST include: idempotency proof, rollback steps, data impact assessment, backup confirmation, and designated responsible person

### Requirement: Feature Flag for High-Risk Changes
UI changes or core flow changes MUST use a feature flag. Feature flags MUST have a lifecycle of <= 30 days, after which they MUST be cleaned up.

#### Scenario: Feature flag naming
- **WHEN** a feature flag is created
- **THEN** it MUST follow the naming convention `ff_{domain}_{feature}_{date}`

### Requirement: Rollback Strategy
The system MUST have documented rollback procedures for three levels: code rollback (git revert), migration rollback (alembic downgrade), and data recovery (restore from backup).

#### Scenario: Code rollback
- **WHEN** a deployed feature causes runtime errors
- **THEN** the team SHALL execute `git revert` and redeploy within the rollback window

#### Scenario: Migration rollback
- **WHEN** a database migration causes data integrity issues
- **THEN** the team SHALL execute `alembic downgrade` within a maintenance window


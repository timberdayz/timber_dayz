## ADDED Requirements

### Requirement: RPO and RTO Targets
The system SHALL define and maintain Recovery Point Objective (RPO) and Recovery Time Objective (RTO) targets.

#### Scenario: RPO compliance
- **GIVEN** the system defines RPO <= 15 minutes
- **THEN** database WAL archiving SHALL run continuously and full backups SHALL run daily

#### Scenario: RTO compliance
- **GIVEN** the system defines RTO <= 2 hours
- **THEN** a full database restore from backup MUST complete within 2 hours

### Requirement: Recovery Drill
The team MUST perform a recovery drill at least once per month. The drill MUST include PostgreSQL full restore and critical table verification.

#### Scenario: Recovery drill passes
- **WHEN** a recovery drill is executed
- **THEN** `scripts/verify_restore.py` MUST pass, confirming critical table row counts, latest record timestamps, and referential integrity

### Requirement: Backup Strategy
PostgreSQL SHALL have daily full backups and continuous WAL archiving. Redis SHALL use AOF persistence with daily RDB snapshots.

#### Scenario: Backup verification
- **WHEN** a daily backup completes
- **THEN** the backup size and timestamp SHALL be logged for audit


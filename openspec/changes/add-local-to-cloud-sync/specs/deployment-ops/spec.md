## ADDED Requirements

### Requirement: Local-to-cloud B-class table sync SHALL run on a fixed schedule and use dynamic table enumeration
The system SHALL support scheduled synchronization of local PostgreSQL `b_class` schema tables to a cloud database, running at four fixed times per day (e.g. 06:30, 12:30, 18:30, 22:30) to avoid overlapping with collection runs (e.g. 06:00, 12:00, 18:00, 22:00). The set of tables to sync SHALL be determined at runtime by querying `information_schema.tables` for `table_schema = 'b_class'` and `table_type = 'BASE TABLE'`, and SHALL NOT rely on a hardcoded table list.

#### Scenario: Sync runs at four times daily, offset from collection
- **WHEN** the local-to-cloud sync is configured (e.g. via Cron)
- **THEN** the recommended schedule SHALL be `30 6,12,18,22 * * *` (06:30, 12:30, 18:30, 22:30)
- **AND** this SHALL be documented so that it stays offset from the collection schedule (e.g. `0 6,12,18,22 * * *`)

#### Scenario: Tables to sync are enumerated from b_class at runtime
- **WHEN** the sync script runs without an explicit table list (e.g. no `--tables` argument)
- **THEN** it SHALL query `information_schema.tables` with `table_schema = 'b_class'` and `table_type = 'BASE TABLE'`
- **AND** it SHALL sync each returned table (subject to incremental/error policy)
- **AND** the project SHALL NOT require maintaining a fixed list of b_class table names in code or config

#### Scenario: Incremental sync and idempotent writes
- **WHEN** syncing a b_class table that has a time column (e.g. `updated_at`, `created_at`)
- **THEN** the sync SHALL use a per-table last_sync checkpoint or time filter so that only new or updated rows are transferred
- **AND** writes to the cloud database SHALL be idempotent (e.g. upsert) so that re-runs do not create duplicate rows

#### Scenario: Single-table failure does not stop the run
- **WHEN** syncing one b_class table fails (e.g. permission, network, schema mismatch)
- **THEN** the script SHALL log the error and continue syncing the remaining tables
- **AND** the script SHALL exit with a non-zero code if any table failed, so that Cron or monitoring can detect partial or total failure

#### Scenario: Cloud connection and secrets
- **WHEN** the sync script connects to the cloud database
- **THEN** the connection URL SHALL be provided via environment variable (e.g. `CLOUD_DATABASE_URL`)
- **AND** the script SHALL NOT log connection strings or secrets in plaintext (only masked or presence indicators)

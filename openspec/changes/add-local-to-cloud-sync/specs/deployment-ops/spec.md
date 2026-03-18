## ADDED Requirements

### Requirement: Local-to-cloud B-class sync SHALL use canonical payload as the source of truth
The system SHALL synchronize local B-class data to the cloud using a canonical payload composed of fixed system fields plus `raw_data` and `header_columns`. Dynamic columns SHALL NOT be treated as the authoritative sync contract.

#### Scenario: Canonical payload is synchronized without depending on dynamic columns
- **WHEN** a local B-class row is selected for synchronization
- **THEN** the synchronized payload SHALL include the row's fixed metadata fields, `raw_data`, `header_columns`, `data_hash`, and related source metadata
- **AND** the sync process SHALL NOT require the corresponding dynamic columns to exist in the cloud database

#### Scenario: Dynamic column update failure does not imply payload loss
- **WHEN** dynamic columns are absent, stale, or not refreshed in the cloud
- **THEN** the B-class row SHALL still be considered synchronized if its canonical payload is safely written
- **AND** `raw_data` and `header_columns` SHALL remain sufficient to reconstruct or project the row later

### Requirement: Data transport SHALL be separated from projection and schema evolution
The system SHALL separate canonical data transport from analytics projection or schema evolution. The sync path SHALL NOT perform runtime cloud-side dynamic-column expansion as part of normal execution.

#### Scenario: Sync run does not add cloud dynamic columns at runtime
- **WHEN** the scheduled sync job processes a B-class table
- **THEN** it SHALL only read and write canonical fields defined by the sync contract
- **AND** it SHALL NOT issue runtime `ADD COLUMN` operations for dynamic business fields in the cloud

#### Scenario: Projection refresh is handled independently
- **WHEN** cloud-side analytics or reporting requires projected fields derived from `raw_data`
- **THEN** those fields SHALL be produced by a separate projection refresh process
- **AND** a projection refresh failure SHALL NOT invalidate a successful canonical sync run

### Requirement: Scheduled sync SHALL be checkpointed, idempotent, and observable
The system SHALL support scheduled local-to-cloud B-class synchronization with per-table checkpoints, idempotent writes, and failure isolation.

#### Scenario: Sync runs on a fixed schedule offset from collection
- **WHEN** the local-to-cloud sync is deployed with scheduled execution
- **THEN** the recommended schedule SHALL remain offset from collection execution windows, such as `30 6,12,18,22 * * *`
- **AND** the schedule SHALL be documented for operations use

#### Scenario: Per-table checkpoint prevents duplicate or missing data
- **WHEN** a B-class table is synchronized incrementally
- **THEN** the sync process SHALL maintain a per-table checkpoint based on a stable high-water mark
- **AND** the checkpoint SHALL only advance after the target-side write is committed successfully

#### Scenario: Idempotent cloud writes preserve update semantics
- **WHEN** a synchronized row conflicts with an existing cloud row representing the same business identity
- **THEN** the cloud write SHALL be idempotent and update the canonical payload fields rather than inserting a duplicate row

#### Scenario: Single-table failure does not stop the entire batch
- **WHEN** syncing one B-class table fails
- **THEN** the sync process SHALL log the failure and continue processing the remaining tables
- **AND** the overall process SHALL return a non-zero exit code if any table failed

#### Scenario: Secrets are injected securely
- **WHEN** the sync process connects to the cloud database
- **THEN** credentials SHALL be supplied through environment variables or equivalent secret injection
- **AND** logs SHALL NOT expose connection strings or secrets in plaintext

### Requirement: Field lineage SHALL be preserved across header evolution
The system SHALL preserve enough lineage information to interpret historical rows correctly even when templates, headers, or normalized field names evolve over time.

#### Scenario: Historical payload is not rewritten during sync
- **WHEN** a newer template or field naming convention is introduced
- **THEN** existing synchronized historical rows SHALL retain their original `raw_data` payload and `header_columns`
- **AND** the sync process SHALL NOT rewrite historical rows solely to align them with new field names

#### Scenario: Semantic alignment is handled by explicit projection rules
- **WHEN** old and new headers need to be interpreted as the same business concept in downstream analytics
- **THEN** that alignment SHALL be handled by explicit aliasing or versioned projection rules
- **AND** the sync process itself SHALL remain a high-fidelity transport layer rather than an implicit semantic remapping layer

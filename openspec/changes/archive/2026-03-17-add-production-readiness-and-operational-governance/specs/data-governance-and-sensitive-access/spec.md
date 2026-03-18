## ADDED Requirements

### Requirement: Four-Level Data Classification
All data in the system SHALL be classified into one of four levels: public, internal, sensitive, restricted. The classification SHALL be documented in `DATA_GOVERNANCE.md`.

#### Scenario: Restricted data identified
- **GIVEN** the system contains salary, performance, personal ID, phone numbers, and encryption keys
- **THEN** these fields SHALL be classified as `restricted`

### Requirement: Restricted Data Access Control
Restricted data SHALL only be accessible to Admin users or data owners. Export of restricted data SHALL require secondary confirmation and SHALL be logged in the audit trail.

#### Scenario: Restricted data export
- **WHEN** a user attempts to export restricted data (e.g., payroll records)
- **THEN** the system SHALL require secondary confirmation
- **AND** the export action SHALL be recorded in the audit log with user ID, timestamp, and data scope

### Requirement: Log Masking for Sensitive Fields
Sensitive and restricted fields MUST NOT appear in plain text in logger output. They MUST be masked (e.g., phone number displayed as `186****9999`).

#### Scenario: Phone number in log
- **WHEN** a logger statement includes a phone number field
- **THEN** the output MUST mask the middle digits (e.g., `186****9999`)

### Requirement: Audit Log Retention
Audit logs for restricted data access SHALL be retained for at least 180 days.

#### Scenario: Audit log retention check
- **WHEN** audit logs are queried
- **THEN** logs from the past 180 days SHALL be available


## ADDED Requirements

### Requirement: Legacy Materialized View Compatibility
Materialized views MAY remain available for compatibility and operational maintenance, but they MUST NOT be treated as the preferred dashboard or analytics query architecture.

#### Scenario: Legacy operational endpoint
- **WHEN** the system exposes a materialized-view management endpoint
- **THEN** the endpoint is documented and labeled as a legacy compatibility or operational tool
- **AND** it is not presented as the preferred data access path for dashboards

#### Scenario: New read-path decisions
- **WHEN** a new dashboard or analytics read path is designed
- **THEN** the implementation does not depend on a new primary materialized-view path
- **AND** any remaining materialized-view usage is justified as temporary compatibility

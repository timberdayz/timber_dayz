## ADDED Requirements

### Requirement: DSS-First Dashboard Read Path
Dashboard and analytical read APIs MUST prefer DSS/Metabase-backed queries or explicitly controlled backend query services.

#### Scenario: Preferred dashboard query source
- **WHEN** a dashboard endpoint is implemented or updated
- **THEN** the endpoint uses Metabase questions or an explicitly owned backend query service as the primary read path
- **AND** materialized views are not introduced as the default source for new dashboard reads

#### Scenario: Legacy compatibility during migration
- **WHEN** an existing dashboard still depends on a materialized view
- **THEN** that dependency is treated as transitional compatibility only
- **AND** the code and follow-up work identify the intended DSS replacement path

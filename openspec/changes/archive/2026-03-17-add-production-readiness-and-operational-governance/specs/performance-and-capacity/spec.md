## ADDED Requirements

### Requirement: API Performance SLO
All critical API endpoints MUST have defined performance targets (p95/p99 latency). New endpoints that involve database queries MUST declare their expected performance tier in the PR description.

#### Scenario: Read endpoint meets SLO
- **WHEN** a critical read endpoint (e.g., user list, target list) is called under normal load
- **THEN** its p95 latency SHALL be < 300ms and p99 latency SHALL be < 800ms

#### Scenario: Write endpoint meets SLO
- **WHEN** a critical write endpoint (e.g., create order, update target) is called under normal load
- **THEN** its p95 latency SHALL be < 800ms and p99 latency SHALL be < 2s

#### Scenario: Complex report endpoint meets SLO
- **WHEN** a complex report or export endpoint is called
- **THEN** its p95 latency SHALL be < 3s and p99 latency SHALL be < 8s

### Requirement: Slow Query Gate
New or modified database queries that exceed 1 second execution time MUST be documented with an explanation and optimization plan in the PR. Endpoints without a declared performance tier MUST NOT be merged.

#### Scenario: Slow query detected in PR
- **WHEN** a PR introduces a query that takes > 1s in testing
- **THEN** the PR MUST include a comment explaining the reason and planned optimization

### Requirement: Load Testing Gate
High-risk changes (database schema changes, connection pool changes, new complex queries, critical service refactors) MUST pass a load test before production deployment.

#### Scenario: Load test pass criteria
- **WHEN** a load test is executed with 50 concurrent users for 2 minutes
- **THEN** the error rate SHALL be < 1%
- **AND** p95 latency SHALL meet the SLO for each tested endpoint
- **AND** database connection pool SHALL NOT overflow

### Requirement: Capacity Baseline
The system SHALL document capacity baselines for database connections, Redis connections, Celery workers, and task queue depth. Exceeding these baselines SHALL trigger alerts.

#### Scenario: Connection pool overflow alert
- **WHEN** the database connection pool reaches max_overflow
- **THEN** the system SHALL log a warning with connection pool metrics


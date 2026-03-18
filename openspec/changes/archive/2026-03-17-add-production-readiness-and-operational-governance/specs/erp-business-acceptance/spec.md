## ADDED Requirements

### Requirement: Monetary Precision Standard
All monetary amounts in the system SHALL use `Decimal` type with 2 decimal places for CNY. Exchange rates and fee rates SHALL use 4 decimal places. Rounding SHALL use `ROUND_HALF_UP`.

#### Scenario: Amount precision in database
- **WHEN** a monetary amount is stored in the database
- **THEN** it SHALL be stored as `Numeric(15, 2)` for CNY amounts (consistent with existing schema.py convention)

#### Scenario: Percentage storage
- **WHEN** a percentage value is stored in the database
- **THEN** it SHALL be stored as a decimal (e.g., 0.15 for 15%) and displayed by multiplying by 100

### Requirement: Time Period Standard
The system SHALL use UTC for all server-side timestamps. "Month" SHALL default to calendar month unless explicitly labeled as "fiscal month". Data attribution SHALL be based on event occurrence time, not ingestion time.

#### Scenario: Cross-month data attribution
- **WHEN** an order occurs on Jan 31 but is ingested on Feb 1
- **THEN** the order SHALL be attributed to January

### Requirement: Domain Acceptance Checklists
Each critical business domain (income, performance, targets, finance) SHALL have a documented acceptance checklist with at least 3 verification items.

#### Scenario: Income acceptance
- **WHEN** the MyIncome module is verified
- **THEN** the following MUST hold: monthly income = base salary + commission + bonus - deductions; sum of all items = total amount

#### Scenario: Target acceptance
- **WHEN** the Target module is verified
- **THEN** the following MUST hold: monthly target = sum of daily breakdowns; completion rate = actual / target * 100

#### Scenario: Performance acceptance
- **WHEN** the Performance module is verified
- **THEN** the following MUST hold: calculated scores match manual computation; rankings have no ties incorrectly omitted

#### Scenario: Finance acceptance
- **WHEN** a finance report is verified
- **THEN** the following MUST hold: revenue - expenses = profit; current month + previous months = cumulative total


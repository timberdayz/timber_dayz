# Backend Architecture Specification Delta

## ADDED Requirements

### Requirement: ETL-Focused Backend Architecture
The backend SHALL focus on Extract-Transform-Load (ETL) operations, providing clean data to the BI layer rather than performing complex KPI calculations.

#### Scenario: Data ingestion flow
- **WHEN** Excel files are uploaded and field mapping is complete
- **THEN** the backend SHALL:
  1. Read Excel with header row identification
  2. Process merged cells (forward fill for critical columns like order_id, order_date)
  3. Store raw data in StagingRawData table (JSONB format with original headers)
  4. Perform multi-layer deduplication (file-level, in-file, cross-file, business semantic)
  5. Insert deduplicated data into FactRawData table
  6. Validate data alignment (header columns match data keys)
- **AND** SHALL NOT perform KPI calculations (delegated to BI layer)

#### Scenario: Merged cell processing
- **WHEN** Excel file contains merged cells (e.g., order_id spans 2-5 rows)
- **THEN** the system SHALL:
  1. Detect critical columns (order_id, order_date, product_id, etc.)
  2. Apply forward fill (ffill) for critical columns regardless of empty ratio
  3. Apply heuristic fill for other dimension columns (empty ratio > 20%)
  4. Never fill measure columns (quantity, amount, price, etc.)
- **AND** SHALL log filled columns and row counts

#### Scenario: Multi-layer deduplication
- **WHEN** data is ingested from staging to fact tables
- **THEN** the system SHALL:
  1. Check file-level deduplication (skip if file_hash exists)
  2. Calculate data_hash for each row (hash of all business fields)
  3. Batch query existing records (use IN query for performance)
  4. Insert new records using ON CONFLICT (database-level deduplication)
  5. Update staging record status (processed/duplicate)
- **AND** SHALL use batch processing for performance (1000 rows in 0.05-0.2 seconds)

#### Scenario: Direct table access for BI layer
- **WHEN** BI layer (Metabase) requests data
- **THEN** the backend SHALL provide direct access to PostgreSQL raw data tables (fact_raw_data_*)
- **AND** SHALL ensure tables are optimized with proper indexes (GIN index on JSONB fields)
- **AND** SHALL NOT create materialized views (Metabase queries raw tables directly)

### Requirement: Field Mapping System Refactoring
The field mapping system SHALL be refactored to directly save original headers without mapping to standard fields.

#### Scenario: Field mapping execution
- **WHEN** user confirms field mapping configuration
- **THEN** the system SHALL save original header columns (not mapped to standard fields)
- **AND** SHALL store data as JSONB with original column names as keys
- **AND** SHALL validate data alignment (header columns match data keys)
- **AND** SHALL NOT calculate derived metrics (e.g., conversion_rate)

#### Scenario: Template matching
- **WHEN** user uploads a file with known data domain and granularity
- **THEN** the system SHALL match template based on `platform + data_domain + granularity`
- **AND** SHALL compare current header columns with template header columns
- **AND** SHALL alert user if header columns changed (added/removed/renamed)
- **AND** SHALL allow user to update template with new header columns

#### Scenario: Header change detection
- **WHEN** header columns differ from template
- **THEN** the system SHALL detect added columns, removed columns, and renamed columns
- **AND** SHALL prompt user to update template
- **AND** SHALL allow user to proceed with current header columns (create new template)

#### Scenario: Data quality isolation
- **WHEN** validation fails for specific rows
- **THEN** the system SHALL isolate bad data to quarantine table
- **AND** SHALL log validation errors with details
- **AND** SHALL continue processing valid rows

### Requirement: A-Class Data Management API
The backend SHALL provide CRUD APIs for A-class data (targets, campaigns, costs) to enable user configuration.

#### Scenario: Sales target creation
- **WHEN** user submits sales target via API
- **THEN** the system SHALL validate period, platform, shop_id
- **AND** SHALL check for duplicates (same period + shop)
- **AND** SHALL insert into `sales_targets` table
- **AND** SHALL return target_id

#### Scenario: Sales target bulk update
- **WHEN** user requests "copy last month" operation
- **THEN** the system SHALL query previous month targets
- **AND** SHALL create new records with current month period
- **AND** SHALL set achieved amounts to 0 (reset)
- **AND** SHALL return count of copied targets

#### Scenario: Operating cost CRUD
- **WHEN** user edits cost configuration via inline table
- **THEN** the system SHALL validate cost values (>= 0)
- **AND** SHALL update `operating_costs` table
- **AND** SHALL invalidate Metabase query cache for affected shops

### Requirement: Metabase Integration Client
The backend SHALL provide a client service for interacting with Metabase.

#### Scenario: Metabase Question API proxy
- **WHEN** frontend requests Question query result
- **THEN** the system SHALL call Metabase REST API (`POST /api/card/{id}/query`)
- **AND** SHALL pass filters and granularity as query parameters
- **AND** SHALL return query result in JSON format
- **AND** SHALL handle errors and timeouts gracefully

#### Scenario: Dashboard data refresh trigger
- **WHEN** user clicks "Refresh Data" button
- **THEN** the system SHALL invalidate Metabase query cache
- **AND** SHALL trigger Metabase scheduled calculation tasks (if configured)
- **AND** SHALL return refresh status and timestamp
- **AND** SHALL NOT refresh materialized views (Metabase queries raw tables directly)

### Requirement: Metabase Query Cache Management
The backend SHALL provide cache invalidation capabilities for Metabase queries.

#### Scenario: Cache invalidation after data ingestion
- **WHEN** new data is ingested into B-class data tables
- **THEN** the system SHALL invalidate Metabase query cache for affected tables
- **AND** SHALL log cache invalidation events
- **AND** SHALL NOT refresh materialized views (not needed in DSS architecture)

#### Scenario: Manual cache refresh trigger
- **WHEN** admin requests manual cache refresh via API
- **THEN** the system SHALL validate user permission
- **AND** SHALL invalidate Metabase query cache
- **AND** SHALL return refresh status and timestamp

## MODIFIED Requirements

### Requirement: Data Import Service
The data import service SHALL be simplified to focus on data cleansing and insertion, removing KPI calculation logic.

**Previous behavior**: Service performed data transformation, validation, and KPI calculation.

**New behavior**: Service only performs data transformation and validation. KPI calculation is delegated to Metabase.

#### Scenario: Order data import (simplified)
- **WHEN** orders are ingested from staging table
- **THEN** the system SHALL transform to JSONB format with original Chinese headers
- **AND** SHALL validate required fields (order_id, platform_code, shop_id)
- **AND** SHALL insert into `b_class.fact_raw_data_orders_{granularity}` table
- **AND** SHALL NOT calculate derived metrics (conversion rate, profit)
- **AND** SHALL store data in JSONB format with Chinese column names as keys

#### Scenario: Product metrics import (simplified)
- **WHEN** product metrics are ingested
- **THEN** the system SHALL insert into `b_class.fact_raw_data_products_{granularity}` table
- **AND** SHALL NOT calculate additional metrics beyond raw data
- **AND** SHALL delegate conversion rate calculation to Metabase Custom Fields

## REMOVED Requirements

### Requirement: KPI Calculation Engine
**Reason**: KPI calculations are moved to BI layer (Metabase) for better maintainability and flexibility.

**Migration**: Existing KPIs will be reimplemented as Metabase Custom Fields (类似Excel公式) or PostgreSQL view columns.

**Affected code**:
- `backend/services/kpi_calculator.py` - DELETED
- `backend/services/metrics_engine.py` - DELETED
- Related unit tests moved to SQL view tests

### Requirement: Complex Backend Dashboard Aggregation
**Reason**: Dashboard aggregations are better handled by Metabase directly querying raw data tables.

**Migration**: Dashboard APIs are removed. Frontend calls Metabase Question API to get data and renders charts with ECharts.

**Affected endpoints**:
- `POST /api/dashboard/calculate-metrics` - REMOVED
- `GET /api/dashboard/shop-performance` - REMOVED (replaced by Metabase Dashboard)
- `GET /api/dashboard/product-ranking` - REMOVED (replaced by Metabase Dashboard)
- `GET /api/dashboard/overview` - REMOVED (replaced by Metabase Dashboard)


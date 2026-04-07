# Database Design Specification Delta

## ADDED Requirements

### Requirement: B-Class Data Tables (Partitioned by data_domain + granularity)
The database SHALL store B-class data (business operational data) in separate tables for each data_domain and granularity combination.

#### Scenario: Orders data storage
- **WHEN** orders data is ingested
- **THEN** the system SHALL store data in:
  - `fact_raw_data_orders_daily` for daily granularity
  - `fact_raw_data_orders_weekly` for weekly granularity
  - `fact_raw_data_orders_monthly` for monthly granularity
- **AND** each table SHALL have:
  - `raw_data` (JSONB) field with Chinese column names (e.g., `"订单号"`, `"订单日期"`, `"销售额"`)
  - `header_columns` (JSONB) field storing original header column list
  - `data_hash` (String, 64) for deduplication
  - Unique constraint: `(data_domain, granularity, data_hash)`
  - Indexes: `data_hash`, `data_domain + granularity + metric_date`, GIN index on `raw_data`

#### Scenario: Products data storage
- **WHEN** products data is ingested
- **THEN** the system SHALL store data in:
  - `fact_raw_data_products_daily`, `fact_raw_data_products_weekly`, `fact_raw_data_products_monthly`
- **AND** SHALL follow the same structure as orders tables

#### Scenario: Traffic data storage
- **WHEN** traffic data is ingested
- **THEN** the system SHALL store data in:
  - `fact_raw_data_traffic_daily`, `fact_raw_data_traffic_weekly`, `fact_raw_data_traffic_monthly`

#### Scenario: Services data storage
- **WHEN** services data is ingested
- **THEN** the system SHALL store data in:
  - `fact_raw_data_services_daily`, `fact_raw_data_services_weekly`, `fact_raw_data_services_monthly`

#### Scenario: Inventory data storage
- **WHEN** inventory data is ingested
- **THEN** the system SHALL store data in:
  - `fact_raw_data_inventory_snapshot` for snapshot granularity (existing)
  - `fact_raw_data_inventory_daily`, `fact_raw_data_inventory_weekly`, `fact_raw_data_inventory_monthly` (future)

**Rationale**: Separating tables by granularity avoids confusion when different granularities use the same Chinese header names (e.g., "日期" for daily vs. weekly).

### Requirement: Unified Entity Aliases Table
The database SHALL provide a unified `entity_aliases` table to manage all account and shop alias mappings.

#### Scenario: Account and shop alignment
- **WHEN** Metabase needs to align accounts and shops
- **THEN** the system SHALL use `entity_aliases` table
- **AND** the table SHALL store:
  - Source identifiers: `source_platform`, `source_type`, `source_name`, `source_account`, `source_site`
  - Target identifiers: `target_type`, `target_id`, `target_name`, `target_platform_code`
  - Metadata: `confidence`, `active`, `notes`
- **AND** SHALL replace both `dim_shops` and `account_aliases` tables
- **AND** SHALL support multiple mapping types: account aliases, shop aliases, shop names

#### Scenario: Query shop information
- **WHEN** Metabase queries shop information
- **THEN** the system SHALL:
  - Query `entity_aliases` WHERE `target_type = 'shop'`
  - JOIN with B-class data tables using `target_id = shop_id`
  - Display `target_name` (Chinese shop name) in Metabase

### Requirement: A-Class Data Tables (Chinese Column Names)
The database SHALL store A-class data (user-configured data) in tables with Chinese column names.

#### Scenario: Sales targets storage
- **WHEN** sales targets are configured
- **THEN** the system SHALL store in `sales_targets` table with Chinese column names:
  - `"店铺ID"` (shop_id)
  - `"年月"` (year_month, format: '2025-01')
  - `"目标销售额"` (target_sales_amount)
  - `"目标订单数"` (target_quantity)
- **AND** PostgreSQL SHALL support Chinese column names (using double quotes)
- **AND** Metabase SHALL display Chinese column names directly

#### Scenario: Operating costs storage
- **WHEN** operating costs are configured
- **THEN** the system SHALL store in `operating_costs` table with Chinese column names:
  - `"店铺ID"`, `"年月"`, `"租金"`, `"工资"`, etc.

#### Scenario: Employee data storage
- **WHEN** employee data is configured
- **THEN** the system SHALL store in:
  - `employees` table: `"员工编号"`, `"姓名"`, `"部门"`, etc.
  - `employee_targets` table: `"员工编号"`, `"年月"`, `"目标类型"`, `"目标值"`, etc.
  - `attendance_records` table: `"员工编号"`, `"考勤日期"`, `"上班时间"`, etc.

**Rationale**: Chinese column names are user-friendly for Chinese users, and both PostgreSQL and Metabase support them.

### Requirement: C-Class Data Tables (Chinese Column Names, Metabase Calculated)
The database SHALL store C-class data (system-calculated data) in tables with Chinese column names, updated by Metabase.

#### Scenario: Employee performance storage
- **WHEN** Metabase calculates employee performance
- **THEN** the system SHALL store in `employee_performance` table with Chinese column names:
  - `"员工编号"`, `"年月"`, `"实际销售额"`, `"达成率"`, etc.
- **AND** SHALL be updated every 20 minutes by Metabase scheduled tasks

#### Scenario: Commission storage
- **WHEN** Metabase calculates commissions
- **THEN** the system SHALL store in:
  - `employee_commissions` table: `"员工编号"`, `"年月"`, `"销售额"`, `"提成金额"`, etc.
  - `shop_commissions` table: `"店铺ID"`, `"年月"`, `"销售额"`, `"提成金额"`, etc.
- **AND** SHALL be updated every 20 minutes by Metabase scheduled tasks

### Requirement: Table Partitioning (Optional)
The database SHALL support table partitioning for B-class data tables when data volume is large.

#### Scenario: Partition by data_domain
- **WHEN** data volume exceeds threshold (e.g., 10 million rows per table)
- **THEN** the system SHALL partition tables by `data_domain`
- **AND** SHALL use PostgreSQL native partitioning (LIST or RANGE)
- **AND** SHALL maintain query performance < 100ms

### Requirement: Index Optimization for Metabase Queries
The database SHALL provide optimized indexes to accelerate Metabase queries.

#### Scenario: Composite index for shop-date queries
- **WHEN** Metabase queries filter by (shop_id, metric_date)
- **THEN** index `idx_raw_data_shop_date` SHALL be used
- **AND** query SHALL complete < 100ms

#### Scenario: GIN index for JSONB raw_data
- **WHEN** Metabase queries filter on JSONB raw_data fields
- **THEN** GIN index `idx_raw_data_gin` SHALL be used
- **AND** SHALL support containment queries (@>, ?, etc.)

#### Scenario: Index for entity_aliases lookups
- **WHEN** Metabase queries entity_aliases for alignment
- **THEN** indexes on `source_platform + source_type + source_name` and `target_type + target_id + active` SHALL be used
- **AND** lookup SHALL complete < 10ms

## MODIFIED Requirements

### Requirement: Data Storage Strategy
The data storage strategy SHALL be simplified from complex fact/dimension tables to raw data tables with JSONB.

**Previous design**: Complex fact tables (fact_orders, fact_order_items) with normalized structure

**New design**: Raw data tables (fact_raw_data_*) with JSONB storage, Chinese column names in JSONB

**Rationale**: 
- Simplifies data ingestion (no field mapping to standard fields)
- Supports dynamic fields without ALTER TABLE
- Leverages Metabase's Chinese column name support
- Reduces table count from 53 to 31-34 tables

#### Scenario: Orders data storage migration
- **WHEN** orders data is ingested from Excel files
- **THEN** the system SHALL store data in `fact_raw_data_orders_daily` table (or weekly/monthly based on granularity)
- **AND** SHALL store all columns as JSONB with Chinese column names as keys (e.g., `"订单号"`, `"订单日期"`, `"销售额"`)
- **AND** SHALL NOT require field mapping to standard English column names
- **AND** SHALL support dynamic columns without ALTER TABLE

### Requirement: Entity Alignment Strategy
The entity alignment strategy SHALL use a unified table instead of separate dimension and alias tables.

**Previous design**: `dim_shops` table + `account_aliases` table (separate)

**New design**: `entity_aliases` table (unified)

**Rationale**: 
- Single source of truth for all alignment information
- Simpler Metabase associations (one table instead of two)
- Easier to manage and maintain

#### Scenario: Shop and account alignment query
- **WHEN** Metabase needs to align shop information from different platforms
- **THEN** the system SHALL query `entity_aliases` table WHERE `target_type = 'shop'`
- **AND** SHALL use `target_id` to join with B-class data tables
- **AND** SHALL display `target_name` (Chinese shop name) in Metabase
- **AND** SHALL NOT require separate queries to `dim_shops` or `account_aliases` tables

## REMOVED Requirements

### Requirement: Three-Layer View Architecture
The three-layer view architecture (Atomic Views, Aggregate Views, Wide Views) SHALL be removed.

**Previous design**: 
- Layer 1: Atomic Views (6 views)
- Layer 2: Aggregate Materialized Views (8 views)
- Layer 3: Wide Views (2 views)

**New design**: Metabase directly queries raw data tables

**Rationale**: 
- Metabase can handle JOINs and aggregations natively
- No need for pre-computed views
- More flexible for ad-hoc queries
- Simpler architecture

### Requirement: Dimension Tables
All dimension tables (`dim_*`) SHALL be removed.

**Previous design**: `dim_shops`, `dim_products`, `dim_platforms`, etc.

**New design**: Information stored in `entity_aliases` or directly in raw data tables

**Rationale**: 
- Simplifies schema
- Reduces table count
- Metabase can create associations as needed

### Requirement: Complex Fact Tables
All complex fact tables (`fact_orders`, `fact_order_items`, etc.) SHALL be removed.

**Previous design**: Normalized fact tables with standard column names

**New design**: Raw data tables with JSONB storage

**Rationale**: 
- Eliminates need for field mapping to standard fields
- Supports dynamic fields
- Reduces maintenance overhead

## Implementation Notes

### Table Structure

#### B-Class Data Tables (Example: fact_raw_data_orders_daily)
```sql
CREATE TABLE fact_raw_data_orders_daily (
    id BIGSERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(256),
    data_domain VARCHAR(64) NOT NULL DEFAULT 'orders',
    granularity VARCHAR(32) NOT NULL DEFAULT 'daily',
    metric_date DATE NOT NULL,
    file_id INTEGER,
    raw_data JSONB NOT NULL,  -- Chinese column names as keys
    header_columns JSONB,     -- Original header column list
    data_hash VARCHAR(64) NOT NULL,
    ingest_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE (data_domain, granularity, data_hash),
    INDEX idx_raw_data_hash (data_hash),
    INDEX idx_raw_data_domain_gran_date (data_domain, granularity, metric_date),
    INDEX idx_raw_data_gin USING GIN (raw_data)
) PARTITION BY LIST (data_domain);  -- Optional partitioning
```

#### Entity Aliases Table
```sql
CREATE TABLE entity_aliases (
    id BIGSERIAL PRIMARY KEY,
    source_platform VARCHAR(32) NOT NULL,
    source_type VARCHAR(32) NOT NULL,  -- 'account' | 'shop' | 'store'
    source_name VARCHAR(256) NOT NULL,
    source_account VARCHAR(128),
    source_site VARCHAR(64),
    data_domain VARCHAR(64),
    target_type VARCHAR(32) NOT NULL,  -- 'account' | 'shop'
    target_id VARCHAR(256) NOT NULL,
    target_name VARCHAR(256),
    target_platform_code VARCHAR(32),
    confidence FLOAT DEFAULT 1.0,
    active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_by VARCHAR(64) DEFAULT 'system',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE (source_platform, source_type, source_name, source_account, source_site),
    INDEX idx_entity_aliases_source (source_platform, source_type, source_name),
    INDEX idx_entity_aliases_target (target_type, target_id, active)
);
```

#### A-Class Data Table (Example: sales_targets)
```sql
CREATE TABLE sales_targets (
    id BIGSERIAL PRIMARY KEY,
    "店铺ID" VARCHAR(256) NOT NULL,      -- Chinese column name
    "年月" VARCHAR(7) NOT NULL,           -- Format: '2025-01'
    "目标销售额" DECIMAL(15, 2) NOT NULL,
    "目标订单数" INTEGER NOT NULL,
    "创建时间" TIMESTAMP NOT NULL DEFAULT NOW(),
    "更新时间" TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE ("店铺ID", "年月")
);
```

### Performance Targets
- B-class data table queries: < 100ms (with indexes)
- Entity aliases lookups: < 10ms
- Metabase scheduled calculations: < 5 minutes per run (every 20 minutes)
- Table partitioning: Maintains performance for large datasets

### Data Consistency
- B-class data: Eventually consistent (deduplication on ingest)
- A-class data: User-configured, immediately consistent
- C-class data: Updated every 20 minutes by Metabase scheduled tasks
- Entity aliases: Immediately consistent (user-managed)

### Migration Strategy
- **Development environment**: Delete all old tables, create new structure
- **Production environment**: Provide migration scripts to migrate data from old tables to new structure
- **Backup**: Keep old table data for 3 months (read-only) for rollback

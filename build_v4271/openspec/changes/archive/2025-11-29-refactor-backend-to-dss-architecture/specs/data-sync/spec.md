# Data Sync Specification Delta

## MODIFIED Requirements

### Requirement: Data Ingestion Flow with Multi-Layer Deduplication
The data ingestion flow SHALL be simplified to focus on data transformation, validation, and multi-layer deduplication, delegating calculation logic to the database and BI layer.

**Previous behavior**: Ingestion included data transformation, validation, and KPI calculation.

**New behavior**: Ingestion performs transformation, validation, and multi-layer deduplication. Calculation is performed by Metabase (Custom Fields and Scheduled Questions).

#### Scenario: Simplified order ingestion with deduplication
- **WHEN** orders are synced from staging to fact table
- **THEN** the system SHALL:
  1. Check file-level deduplication (skip if file_hash exists in catalog_files)
  2. Process merged cells (forward fill for order_id, order_date)
  3. Calculate data_hash for each row (hash of all business fields, excluding metadata)
  4. Batch query existing records (use IN query with all data_hashes)
  5. Insert new records using ON CONFLICT (database-level deduplication)
  6. Update staging record status (processed/duplicate)
- **AND** SHALL NOT calculate:
  - Conversion rates (delegated to Metabase Custom Fields)
  - Profit margins (delegated to Metabase Custom Fields)
  - Achievement rates (delegated to Metabase Scheduled Questions)

#### Scenario: Multi-layer deduplication strategy
- **WHEN** data is ingested from staging to fact tables
- **THEN** the system SHALL apply four-layer deduplication:
  1. **File-level deduplication**: Check if file_hash exists in catalog_files, skip entire file if already processed
  2. **In-file deduplication**: Use `file_id + row_number + data_hash` for unique identification within a single file
  3. **Cross-file deduplication**: Use `data_hash` (full row hash of business fields) to identify identical records across different files
  4. **Business semantic judgment**: If business identifiers are the same but data differs, apply update strategy (e.g., "latest wins")
- **AND** SHALL use batch processing for performance:
  - Batch hash calculation (pandas vectorization, 1000 rows in 50-100ms)
  - Batch database query (1 IN query instead of 1000 individual queries)
  - Batch insert with ON CONFLICT (1 SQL statement for all data)
  - Expected performance: 1000 rows in 0.05-0.2 seconds (50-100x faster than row-by-row)

#### Scenario: Simplified product metrics ingestion
- **WHEN** product metrics are synced
- **THEN** the system SHALL:
  - Insert raw metrics (views, clicks, add_to_cart, orders)
  - Validate metric values >= 0
- **AND** SHALL NOT calculate:
  - CTR, cart_rate, conversion_rate (delegated to Metabase Custom Fields)

### Requirement: Data Quality Isolation
The data quality isolation mechanism SHALL continue to work with the simplified ingestion flow.

**No change in behavior**, but isolation now focuses purely on data quality issues, not calculation errors.

#### Scenario: Isolate invalid data rows
- **WHEN** validation fails for specific rows
- **THEN** the system SHALL:
  - Insert bad rows into `data_quarantine` table
  - Log error_type (ValueError, IntegrityError, etc.)
  - Log error_msg with details
  - Continue processing valid rows
- **AND** SHALL provide UI to view and reprocess quarantined data

### Requirement: Bulk Ingestion Progress Tracking
The bulk ingestion progress tracking SHALL continue to work with simplified logic.

**No change in behavior**, but tracking now focuses on ETL metrics, not calculation metrics.

#### Scenario: Track bulk ingestion progress
- **WHEN** bulk ingestion is in progress
- **THEN** the system SHALL track:
  - `total_files`, `processed_files`, `current_file`
  - `total_rows`, `processed_rows`, `valid_rows`, `error_rows`, `quarantined_rows`
  - `file_progress`, `row_progress` (percentages)
- **AND** SHALL persist progress to `sync_progress_tasks` table
- **AND** SHALL NOT track:
  - Calculated KPI metrics (no longer computed during ingestion)

### Requirement: Data Freshness Indicator
The system SHALL provide data freshness indicators to inform users when data was last ingested or calculated.

**New requirement** to show data freshness for both B-class (ingested) and C-class (calculated) data.

#### Scenario: Display last ingestion timestamp
- **WHEN** user views dashboard
- **THEN** the system SHALL display:
  - "B类数据更新至: 2025-11-22 01:00 AM" (last ingestion time for B-class data)
  - Source: `fact_raw_data_*` tables, latest `ingest_timestamp` (MAX across all B-class tables)

#### Scenario: Display last calculation timestamp
- **WHEN** user views C-class data (performance, commissions)
- **THEN** the system SHALL display:
  - "C类数据更新至: 2025-11-22 01:15 AM" (last calculation time for C-class data)
  - Source: `employee_performance`, `employee_commissions`, `shop_commissions` tables, latest `updated_at` timestamp
  - **Note**: C-class data is updated every 20 minutes by Metabase scheduled tasks

#### Scenario: Manual cache refresh trigger
- **WHEN** user clicks "Refresh Data" button
- **THEN** the system SHALL:
  - Trigger `POST /api/metabase/refresh-cache` (invalidate Metabase query cache)
  - Optionally trigger Metabase scheduled calculation tasks (if configured)
  - Show progress spinner
  - Update timestamp upon completion
  - **Note**: This does NOT refresh materialized views (DSS architecture queries raw tables directly)

## ADDED Requirements

### Requirement: User-Manual Header Row Selection ⭐ **新增（2025-01-31）**
The data sync system SHALL require users to manually select the header row for each data domain and sub-domain file, as automatic detection is unreliable for most files.

**Rationale**: Most Excel files have header rows not in the first row (row 0), and automatic detection often fails. Manual selection ensures accuracy.

#### Scenario: User selects header row before preview
- **WHEN** user opens a file in the data sync interface
- **THEN** the system SHALL:
  1. Display file details (platform, data_domain, granularity, sub_domain)
  2. Show header row selector (0-10, where 0=Excel row 1, 1=Excel row 2, etc.)
  3. Default to template's `header_row` if template exists, otherwise 0
  4. Display warning: "⚠️ Important: Please manually select the correct header row! Most files have header rows not in the first row, and automatic detection is unreliable."
- **AND** SHALL NOT automatically detect header row without user confirmation

#### Scenario: User previews data with selected header row
- **WHEN** user selects a header row and clicks "Preview Data"
- **THEN** the system SHALL:
  1. Read file using the selected header row (no automatic detection)
  2. Display data preview (first 100 rows)
  3. Display original header field list (序号, 原始表头字段, 示例数据)
  4. Allow user to verify:
     - Data preview is correct
     - Header fields are correctly identified
- **AND** if preview is incorrect:
  - User can adjust header row and re-preview
  - System SHALL NOT automatically change header row

#### Scenario: User saves template with header row
- **WHEN** user confirms preview is correct and clicks "Save as Template"
- **THEN** the system SHALL:
  1. Save `header_columns` (original header field list)
  2. Save `header_row` (user-selected header row) ⭐ **Critical**
  3. Save `platform`, `data_domain`, `granularity`, `sub_domain`
  4. Display success message: "Template saved successfully! Header row: {header_row} (Excel row {header_row+1})"
- **AND** SHALL store template in `field_mapping_templates` table with `header_row` field

#### Scenario: Automatic sync uses template header row
- **WHEN** automatic sync processes a file with an existing template
- **THEN** the system SHALL:
  1. Find template by `platform + data_domain + granularity + sub_domain`
  2. Use template's `header_row` to read file (strict enforcement, no automatic detection)
  3. Use template's `header_columns` to validate header match
  4. Log: "Using template header row: {header_row} (strict enforcement, no auto-detection)"
- **AND** SHALL NOT:
  - Automatically detect header row if template exists
  - Fall back to automatic detection if template header row fails
- **AND** if header match rate < 80%:
  - Log warning but continue sync
  - Allow user to manually adjust template later

#### Scenario: Template header row mismatch warning
- **WHEN** automatic sync uses template header row but header match rate < 80%
- **THEN** the system SHALL:
  1. Log warning: "Header match rate low: {match_rate}%, but continuing sync with template header row"
  2. Continue sync (do not fail)
  3. Record mismatch in sync history for user review
- **AND** SHALL provide UI for user to:
  - View sync history with mismatch warnings
  - Update template header row if needed
  - Re-sync file with corrected template

### Requirement: Independent Data Sync System ⭐ **新增（2025-01-31）**
The data sync system SHALL be completely independent from the field mapping audit system, with its own menu structure and UI.

#### Scenario: New data sync menu structure
- **WHEN** user navigates to "数据采集与管理" (Data Collection and Management)
- **THEN** the system SHALL display:
  - 采集配置 (Collection Config)
  - 采集任务 (Collection Tasks)
  - 采集历史 (Collection History)
  - **数据同步** ⭐ **New sub-menu**:
    - 文件列表 (File List - pending files)
    - 同步任务 (Sync Tasks - task management)
    - 同步历史 (Sync History - history records)
    - 模板管理 (Template Management - header templates)
  - 数据隔离区 (Data Quarantine)
  - 数据浏览器 (Data Browser)
  - 数据一致性验证 (Data Consistency)
- **AND** SHALL NOT display:
  - 字段映射审核 (Field Mapping Audit) - **Removed** (completely independent)

#### Scenario: Data sync file detail page UI
- **WHEN** user opens a file in data sync interface
- **THEN** the system SHALL display:
  1. **File Details Section**:
     - File name, platform, account, data_domain, granularity, sub_domain
     - Available template status (有模板/无模板)
  2. **Header Row Selector**:
     - Input field (0-10) with up/down arrows
     - Label: "表头行 (0=Excel第1行, 1=Excel第2行, ...)"
     - Warning message: "⚠️ Important: Please manually select the correct header row!"
  3. **Data Preview Section**:
     - Preview button: "◎预览数据"
     - Re-preview button: "重新预览"
     - Data preview table (first 100 rows)
     - "Collapse Preview" button
  4. **Original Header Field List Section**:
     - Table with columns: 序号, 原始表头字段, 示例数据
     - "Save as Template" button
- **AND** SHALL preserve existing UI design (file details, data preview, header field list) to ensure users can verify system recognition

### Requirement: Template Header Row Strict Enforcement ⭐ **新增（2025-01-31）**
The data sync service SHALL strictly enforce template header row settings during automatic sync, without automatic detection fallback.

#### Scenario: Strict template header row enforcement
- **WHEN** `DataSyncService.sync_single_file()` is called with `use_template_header_row=True`
- **THEN** the system SHALL:
  1. Find template by `platform + data_domain + granularity + sub_domain`
  2. If template exists:
     - Use `template.header_row` directly (no automatic detection)
     - Log: "[DataSync] Using template header row: {header_row} (strict enforcement, no auto-detection)"
     - Read file with `ExcelParser.read_excel(file_path, header=template.header_row)`
  3. If template does not exist:
     - Use default header_row=0
     - Log warning: "[DataSync] No template found, using default header_row=0"
     - Prompt user to create template
- **AND** SHALL NOT:
  - Automatically detect header row if template exists
  - Try multiple header rows (0-5) if template header row fails
  - Fall back to automatic detection

#### Scenario: Template header row validation
- **WHEN** template header row is used to read file
- **THEN** the system SHALL:
  1. Validate header match rate (expected vs actual headers)
  2. If match rate >= 80%:
     - Continue sync normally
     - Log: "Header match rate: {match_rate}%, sync proceeding"
  3. If match rate < 80%:
     - Log warning: "Header match rate low: {match_rate}%, but continuing sync with template header row"
     - Continue sync (do not fail)
     - Record warning in sync result for user review
- **AND** SHALL provide UI for user to:
  - View sync warnings
  - Update template if header row is incorrect
  - Re-sync file with corrected template

### Requirement: Metabase Cache Invalidation After Ingestion
The data sync service SHALL invalidate Metabase query cache after bulk ingestion completes.

#### Scenario: Auto-invalidate cache after ingestion
- **WHEN** bulk ingestion task status becomes 'completed'
- **THEN** the system SHALL:
  - Invalidate Metabase query cache for affected tables (e.g., `fact_raw_data_orders_daily` if orders data was ingested)
  - Call Metabase API: `POST /api/cache/invalidate` (if available) or use cache TTL
  - Log cache invalidation status
  - **Note**: This ensures next Metabase query fetches fresh data from newly ingested records

#### Scenario: Skip cache invalidation for small batches
- **WHEN** bulk ingestion processes < 100 rows
- **THEN** the system SHALL NOT invalidate cache immediately
- **AND** SHALL rely on cache TTL (5 minutes default)
- **REASON**: Avoid excessive cache invalidation overhead for small updates

### Requirement: Data Validation Enhancement
The data validation service SHALL add new validations specific to Metabase query requirements.

#### Scenario: Validate time dimension requirements
- **WHEN** validating order data
- **THEN** the system SHALL ensure:
  - `metric_date` field is valid Date (required for time-based queries)
  - JSONB `raw_data->>'订单日期'` field is valid Date format (if present)
  - If `metric_date` is NULL, row is quarantined

#### Scenario: Validate JSONB field consistency
- **WHEN** validating data for Metabase queries
- **THEN** the system SHALL ensure:
  - `header_columns` JSONB array matches keys in `raw_data` JSONB object
  - All required fields (based on data_domain) are present in `raw_data`
  - Field names are consistent (Chinese column names preserved)

## REMOVED Requirements

### Requirement: Real-time KPI Calculation During Ingestion
**Reason**: KPI calculation is moved to Metabase (Custom Fields and Scheduled Questions).

**Migration**: 
- Remove all inline calculation logic from `data_importer.py`
- Remove `calculate_conversion_rate()`, `calculate_profit_margin()` functions
- Remove unit tests for calculation logic (replaced by Metabase Custom Field tests)

**Affected code**:
- `backend/services/data_importer.py` - Remove calculation methods
- `backend/services/enhanced_data_validator.py` - Remove derived field validation

## Implementation Notes

### Simplified Data Importer
```python
# backend/services/data_importer.py (simplified)
class DataImporter:
    def import_orders(self, df: pd.DataFrame, file_id: int) -> ImportResult:
        """Import orders - ETL only, no KPI calculation"""
        
        # 1. Transform
        transformed = self._transform_orders(df)
        
        # 2. Validate
        valid_rows, quarantined_rows = self._validate_orders(transformed)
        
        # 3. Load (upsert to fact_raw_data_orders_{granularity})
        inserted = self._upsert_orders(valid_rows)
        
        # 4. Isolate bad data
        self._quarantine_rows(quarantined_rows, file_id)
        
        # 5. Return result (NO KPI calculation)
        return ImportResult(
            inserted=inserted,
            quarantined=len(quarantined_rows),
            valid=len(valid_rows)
        )
```

### Metabase-Based KPI Calculation
```sql
-- KPIs now calculated in Metabase Custom Fields, not Python

-- Conversion rate (Metabase Custom Field)
-- Formula: ([订单数] / [客流量]) * 100
-- SQL Expression: (raw_data->>'订单数')::numeric / NULLIF((raw_data->>'客流量')::numeric, 0) * 100

-- Profit margin (Metabase Custom Field)
-- Formula: ([销售额] - [运营成本]) / [销售额] * 100
-- SQL Expression: ((raw_data->>'销售额')::numeric - (operating_costs."运营成本")::numeric) / NULLIF((raw_data->>'销售额')::numeric, 0) * 100

-- Achievement rate (Metabase Scheduled Question, stored in C-class tables)
-- Calculated every 20 minutes and stored in employee_performance or shop_commissions tables
```

### Cache Invalidation Integration
```python
# backend/services/sync_service.py
class SyncService:
    async def complete_bulk_ingestion(self, task_id: str):
        """Complete ingestion and invalidate Metabase cache"""
        
        # 1. Update task status
        task = self._get_task(task_id)
        task.status = 'completed'
        task.end_time = datetime.now()
        
        # 2. Invalidate Metabase cache (if significant volume)
        if task.valid_rows >= 100:
            affected_tables = self._get_affected_tables(task)
            await self._invalidate_metabase_cache(affected_tables)
        
        # 3. Notify frontend
        await self._send_completion_notification(task_id)
```

### Performance Impact
- **Ingestion speed**: +30% faster (no Python calculation overhead)
- **Code complexity**: -50% (remove calculation logic)
- **Metabase query time**: < 2 seconds (queries raw tables directly, uses GIN indexes on JSONB)
- **Overall latency**: Real-time queries (no view refresh delay), Metabase caches results for 5 minutes

### Testing Strategy
- **Unit tests**: Focus on ETL logic (transform, validate, load)
- **Integration tests**: Test end-to-end flow (ingest → cache invalidation → Metabase query)
- **Metabase tests**: Test Custom Fields and Scheduled Questions
- **Performance tests**: Measure Metabase query performance on raw tables

### Migration Checklist
- [ ] Remove Python KPI calculation functions
- [ ] Remove related unit tests
- [ ] Configure Metabase Custom Fields for KPI calculations
- [ ] Configure Metabase Scheduled Questions for C-class data
- [ ] Update API documentation
- [ ] Update user documentation (explain Metabase-based calculations)
- [ ] Train team on new architecture


# Frontend API Contracts Specification

## MODIFIED Requirements

### Requirement: Simplified Field Mapping API
Field mapping preview and ingest APIs SHALL be simplified to remove redundant calculations.

#### Scenario: File preview without KPI calculation
- **WHEN** frontend calls `POST /api/field-mapping/preview`
- **THEN** backend SHALL return:
  - `preview_data`: First 100 rows of mapped data
  - `column_mapping`: Applied field mapping
  - `data_quality`: Basic stats (null_count, unique_count)
- **AND** SHALL NOT include derived KPI fields (conversion_rate, profit_margin, etc.)
- **AND** response time SHALL be < 2 seconds

#### Scenario: Bulk ingest with simplified validation
- **WHEN** frontend calls `POST /api/field-mapping/bulk-ingest`
- **THEN** backend SHALL:
  - Validate required fields only (platform_code, data_domain, date)
  - Stage data to staging tables
  - Upsert to fact tables
  - Return ingestion summary (success_count, error_count)
- **AND** SHALL NOT perform complex business rule validation
- **AND** response time SHALL be < 10 seconds for 10K rows

#### Scenario: Template application without preview
- **WHEN** user applies saved template
- **THEN** frontend SHALL call `POST /api/field-mapping/apply-template` with:
  - `file_id`: Catalog file ID
  - `template_id`: Saved template ID
  - `auto_ingest`: Boolean (optional, default: false)
- **AND** backend SHALL apply mapping and optionally trigger ingest
- **AND** SHALL return mapping result or ingest status

---

## ADDED Requirements

### Requirement: A-Class Data Management APIs
Backend SHALL provide CRUD APIs for campaign targets, sales targets, and operating costs.

#### Scenario: List sales targets
- **WHEN** frontend calls `GET /api/config/sales-targets?shop_id={shop_id}&year_month={year_month}`
- **THEN** backend SHALL return:
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "shop_id": "shop_001",
      "shop_name": "旗舰店",
      "year_month": "2025-01",
      "target_sales_amount": 1000000.00,
      "target_order_count": 5000,
      "created_at": "2025-01-15T10:00:00Z",
      "created_by": "admin"
    }
  ],
  "total": 12
}
```

#### Scenario: Create sales target
- **WHEN** frontend calls `POST /api/config/sales-targets` with:
```json
{
  "shop_id": "shop_001",
  "year_month": "2025-02",
  "target_sales_amount": 1200000.00,
  "target_order_count": 6000
}
```
- **THEN** backend SHALL:
  - Validate shop_id exists in entity_aliases table (target_type='shop', target_id=shop_id)
  - Check for duplicate (shop_id + year_month)
  - Insert to sales_targets_a table
  - Return created record with HTTP 201

#### Scenario: Batch update sales targets
- **WHEN** frontend calls `PUT /api/config/sales-targets/batch` with:
```json
{
  "targets": [
    { "id": "uuid1", "target_sales_amount": 1100000.00 },
    { "id": "uuid2", "target_sales_amount": 1300000.00 }
  ]
}
```
- **THEN** backend SHALL update all targets in single transaction
- **AND** SHALL return updated records

#### Scenario: Copy last month targets
- **WHEN** frontend calls `POST /api/config/sales-targets/copy-last-month` with:
```json
{
  "from_year_month": "2025-01",
  "to_year_month": "2025-02",
  "shop_ids": ["shop_001", "shop_002"]
}
```
- **THEN** backend SHALL:
  - Copy targets from 2025-01 to 2025-02 for specified shops
  - Generate new UUIDs for copied records
  - Return count of copied records

#### Scenario: List operating costs
- **WHEN** frontend calls `GET /api/config/operating-costs?shop_id={shop_id}&year_month={year_month}`
- **THEN** backend SHALL return:
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "shop_id": "shop_001",
      "year_month": "2025-01",
      "rent": 50000.00,
      "salary": 200000.00,
      "marketing": 100000.00,
      "logistics": 80000.00,
      "other": 30000.00,
      "total": 460000.00
    }
  ]
}
```

#### Scenario: Update operating costs
- **WHEN** frontend calls `PUT /api/config/operating-costs/{id}` with:
```json
{
  "rent": 55000.00,
  "salary": 210000.00,
  "marketing": 120000.00
}
```
- **THEN** backend SHALL:
  - Update specified fields
  - Recalculate total = sum of all cost fields
  - Return updated record

#### Scenario: List campaign targets
- **WHEN** frontend calls `GET /api/config/campaign-targets?platform={platform}&year_month={year_month}`
- **THEN** backend SHALL return:
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "platform_code": "shopee",
      "campaign_id": "double_11",
      "campaign_name": "双十一大促",
      "start_date": "2025-11-01",
      "end_date": "2025-11-11",
      "target_gmv": 5000000.00,
      "target_roi": 3.5
    }
  ]
}
```

### Requirement: Metabase Question API Proxy
Backend SHALL provide proxy APIs for calling Metabase Question API and returning query results.

#### Scenario: Get Question query result
- **WHEN** frontend calls `GET /api/metabase/question/{question_id}/query?filters={filters}`
- **THEN** backend SHALL:
  - Validate request parameters
  - Call Metabase REST API: `POST /api/card/{question_id}/query`
  - Pass filters as query parameters
  - Return query result in JSON format
```json
{
  "success": true,
  "data": {
    "columns": [
      {"name": "date", "type": "date"},
      {"name": "gmv", "type": "number"}
    ],
    "rows": [
      ["2025-01-01", 10000],
      ["2025-01-02", 12000]
    ],
    "row_count": 2
  },
  "question_id": 1
}
```

#### Scenario: Question API with filters
- **WHEN** frontend calls `GET /api/metabase/question/{question_id}/query` with filters:
  - `filters`: JSON string containing `date_range`, `platform`, `shop_id`, `granularity`
- **THEN** backend SHALL:
  - Parse filters JSON
  - Convert filters to Metabase query parameters
  - Call Metabase Question API with parameters
  - Return filtered query result

#### Scenario: Refresh Metabase query cache
- **WHEN** frontend calls `POST /api/metabase/refresh-cache` with:
```json
{
  "question_ids": [1, 2, 3],
  "table_names": ["fact_raw_data_orders_daily", "fact_raw_data_products_daily"]
}
```
- **THEN** backend SHALL:
  - Invalidate Metabase query cache for specified questions (if question_ids provided)
  - Invalidate Metabase query cache for specified tables (if table_names provided)
  - Return refresh status
```json
{
  "success": true,
  "data": {
    "refreshed_questions": [1, 2, 3],
    "refreshed_tables": ["fact_raw_data_orders_daily", "fact_raw_data_products_daily"],
    "duration_seconds": 0.5
  }
}
```
- **Note**: Cache invalidation is fast (< 1 second) as it only clears cache, does not refresh materialized views

### Requirement: Unified Error Response Format
ALL APIs SHALL return consistent error response format.

#### Scenario: Validation error
- **WHEN** API receives invalid input (e.g., missing required field)
- **THEN** SHALL return HTTP 400 with:
```json
{
  "success": false,
  "error_code": "VALIDATION_ERROR",
  "message": "销售目标金额不能为负数",
  "details": {
    "field": "target_sales_amount",
    "value": -1000,
    "constraint": "must be >= 0"
  }
}
```

#### Scenario: Authentication error
- **WHEN** JWT token is invalid or expired
- **THEN** SHALL return HTTP 401 with:
```json
{
  "success": false,
  "error_code": "UNAUTHORIZED",
  "message": "Token已过期，请重新登录"
}
```

#### Scenario: Permission error
- **WHEN** user lacks permission for requested resource
- **THEN** SHALL return HTTP 403 with:
```json
{
  "success": false,
  "error_code": "FORBIDDEN",
  "message": "您无权访问此店铺的数据"
}
```

#### Scenario: Server error
- **WHEN** internal error occurs (database connection, Metabase API failure, etc.)
- **THEN** SHALL return HTTP 500 with:
```json
{
  "success": false,
  "error_code": "INTERNAL_ERROR",
  "message": "服务器内部错误，请稍后重试",
  "request_id": "uuid"
}
```

---

## REMOVED Requirements

### Requirement: Complex KPI Calculation in Preview API
Preview API SHALL NOT calculate derived KPI fields.

**Reason**: KPI calculation moved to Metabase BI layer for flexibility and non-technical user accessibility.

**Migration**: 
- Remove `calculate_kpis()` function from preview endpoint
- Remove derived fields from preview response
- Frontend SHALL display raw data only in preview

### Requirement: Multi-Step Validation Pipeline
Ingest API SHALL NOT perform complex multi-step validation.

**Reason**: Simplified validation focuses on data integrity, not business rules.

**Migration**:
- Remove `enhanced_data_validator.py` complex validation
- Keep only basic validation (required fields, data types, foreign keys)
- Business rule validation moved to Metabase table and question configuration

### Requirement: Template Auto-Application
Backend SHALL NOT auto-apply templates during file upload.

**Reason**: User should explicitly choose template to avoid unexpected results.

**Migration**:
- Remove auto-template logic from file upload endpoint
- Frontend SHALL provide explicit "Apply Template" button
- Save user preference for default template (optional)

### Requirement: Data Sync APIs ⭐ **新增（2025-01-31）**
Backend SHALL provide APIs for the new independent data sync system, supporting user-manual header row selection.

#### Scenario: Preview file with selected header row
- **WHEN** frontend calls `POST /api/data-sync/preview` with:
```json
{
  "file_id": 1106,
  "header_row": 2
}
```
- **THEN** backend SHALL:
  - Read file using the selected header row (no automatic detection)
  - Return data preview (first 100 rows)
  - Return original header field list with sample data
  - Response format:
```json
{
  "success": true,
  "data": {
    "preview_data": [...],
    "header_columns": ["日期期间", "访客数", "聊天询问", ...],
    "row_count": 1000,
    "column_count": 16
  }
}
```

#### Scenario: List pending sync files
- **WHEN** frontend calls `GET /api/data-sync/files?platform=shopee&domain=services&status=pending`
- **THEN** backend SHALL return:
  - List of pending files with metadata
  - Template match status (has_template: true/false)
  - Response format:
```json
{
  "success": true,
  "data": {
    "files": [
      {
        "id": 1106,
        "file_name": "shopee_services_agent_monthly_xxx.xlsx",
        "platform": "shopee",
        "domain": "services",
        "granularity": "monthly",
        "sub_domain": "agent",
        "has_template": true,
        "template_name": "shopee_services_agent_monthly_v1"
      }
    ],
    "total": 5
  }
}
```

#### Scenario: Save template with header row
- **WHEN** frontend calls `POST /api/data-sync/templates` with:
```json
{
  "platform": "shopee",
  "data_domain": "services",
  "granularity": "monthly",
  "sub_domain": "agent",
  "header_columns": ["日期期间", "访客数", "聊天询问", ...],
  "header_row": 2,
  "template_name": "shopee_services_agent_monthly_v1"
}
```
- **THEN** backend SHALL:
  - Save `header_columns` (original header field list)
  - Save `header_row` (user-selected header row) ⭐ **Critical**
  - Save other template metadata
  - Return template_id

#### Scenario: Sync file using template header row
- **WHEN** frontend calls `POST /api/data-sync/single` with:
```json
{
  "file_id": 1106,
  "use_template_header_row": true
}
```
- **THEN** backend SHALL:
  - Find template by `platform + data_domain + granularity + sub_domain`
  - Use template's `header_row` to read file (strict enforcement, no automatic detection)
  - Validate header match (if match rate < 80%, log warning but continue)
  - Sync data to B-class tables
  - Return sync result with task_id

---

## API Summary Table

| Endpoint | Method | Purpose | Phase |
|----------|--------|---------|-------|
| `/api/field-mapping/preview` | POST | Preview file with mapping (simplified) | Phase 2 |
| `/api/field-mapping/bulk-ingest` | POST | Bulk ingest with simplified validation | Phase 2 |
| `/api/field-mapping/apply-template` | POST | Apply saved template | Phase 2 |
| `/api/config/sales-targets` | GET/POST/PUT/DELETE | CRUD sales targets | Phase 3 |
| `/api/config/sales-targets/batch` | PUT | Batch update targets | Phase 3 |
| `/api/config/sales-targets/copy-last-month` | POST | Copy last month targets | Phase 3 |
| `/api/config/operating-costs` | GET/POST/PUT/DELETE | CRUD operating costs | Phase 3 |
| `/api/config/campaign-targets` | GET/POST/PUT/DELETE | CRUD campaign targets | Phase 3 |
| `/api/metabase/embedding-token` | POST | Generate Metabase embedding token | Phase 3 |
| `/api/metabase/dashboard/{id}/embed-url` | GET | Get embedded dashboard URL (with filters and granularity) | Phase 3 |
| `/api/metabase/refresh-cache` | POST | Invalidate Metabase query cache | Phase 4 |
| `/api/metabase/question/{id}/query` | GET | Get Metabase Question query result | Phase 4 |
| `/api/metabase/health` | GET | Check Metabase health status | Phase 3 |
| `/api/data-sync/files` | GET | List pending sync files (with filters) | Phase 0.8 ⭐ |
| `/api/data-sync/preview` | POST | Preview file with selected header row | Phase 0.8 ⭐ |
| `/api/data-sync/single` | POST | Sync single file (use template header row) | Phase 0.8 ⭐ |
| `/api/data-sync/batch` | POST | Batch sync files | Phase 0.8 ⭐ |
| `/api/data-sync/progress/{task_id}` | GET | Get sync task progress | Phase 0.8 ⭐ |
| `/api/data-sync/templates` | GET/POST/PUT/DELETE | CRUD header templates | Phase 0.8 ⭐ |

---

## Authentication and Authorization

ALL APIs SHALL require JWT authentication via `Authorization: Bearer {token}` header.

### Token Claims
```json
{
  "user_id": "uuid",
  "username": "zhangsan@example.com",
  "roles": ["Manager", "Finance"],
  "shop_access": ["shop_001", "shop_002"],
  "exp": 1700000000
}
```

### Role-Based Access Control
- **Admin**: Full access to all APIs
- **Manager**: Read/write access to own shops' data and config
- **Finance**: Read-only access to financial data
- **Operator**: Read-only access to operational data
- **Viewer**: Read-only access to dashboards

---

## Testing Requirements

### Unit Tests
- [ ] Validate request schemas with Pydantic
- [ ] Test error handling for all scenarios
- [ ] Test JWT token validation

### Integration Tests
- [ ] Test full CRUD flow for A-class data
- [ ] Test Metabase embedding token generation
- [ ] Test granularity parameter passing to Metabase
- [ ] Test Metabase cache refresh
- [ ] Test Metabase Question API proxy

### Contract Tests
- [ ] Validate response schemas match documentation
- [ ] Test backward compatibility with existing frontend

---

**Specification Version**: 1.0  
**Last Updated**: 2025-11-22  
**Status**: Proposed


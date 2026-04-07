# API Design, Contracts & Review

**Version**: v4.20.0
**Standard**: RESTful API + OpenAPI 3.0 + Contract-First

---

## 1. API Contract Standard

### 1.1 Unified Response Format

All APIs must follow a unified response format. See `docs/API_CONTRACTS.md` for full details.

**Core patterns**:
- Success: `{"success": true, "data": {...}, "timestamp": "..."}`
- Error: `{"success": false, "error": {...}, "message": "...", "timestamp": "..."}`
- Pagination: `{"success": true, "data": [...], "pagination": {...}, "timestamp": "..."}`
- Auto-formatting: datetime (ISO 8601), amounts (Decimal -> float)

**Implementation files**:
- Backend: `backend/utils/api_response.py` (success_response, error_response, pagination_response)
- Backend: `backend/utils/data_formatter.py` (auto-format datetime and amounts)
- Frontend: `frontend/src/api/index.js` (response interceptor)
- Frontend: `frontend/src/utils/errorHandler.js` (unified error handling)
- Frontend: `frontend/src/utils/dataFormatter.js` (null-data formatting)

### 1.2 Success Response

```json
{
  "success": true,
  "data": {},
  "message": "OK",
  "timestamp": "2025-01-16T10:30:00Z"
}
```

```python
from backend.utils.api_response import success_response

return success_response(data={"id": 1, "name": "order"})
```

### 1.3 Error Response

```json
{
  "success": false,
  "error": {
    "code": 2001,
    "type": "BusinessError",
    "detail": "Order not found",
    "recovery_suggestion": "Check the order ID"
  },
  "message": "Business error: Order not found",
  "timestamp": "2025-01-16T10:30:00Z"
}
```

```python
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type

return error_response(
    code=ErrorCode.ORDER_NOT_FOUND,
    message="Order not found",
    error_type=get_error_type(ErrorCode.ORDER_NOT_FOUND),
    detail="Order ID: 12345 not found",
    recovery_suggestion="Check the order ID"
)
```

### 1.4 Pagination Response

```json
{
  "success": true,
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5,
    "has_previous": false,
    "has_next": true
  },
  "timestamp": "2025-01-16T10:30:00Z"
}
```

```python
from backend.utils.api_response import pagination_response

return pagination_response(data=order_list, page=1, page_size=20, total=100)
```

### 1.5 Data Auto-Formatting

- `datetime` -> ISO 8601 string (`2025-01-16T10:30:00Z`)
- `date` -> ISO 8601 date (`2025-01-16`)
- `Decimal` -> `float` (2 decimal places)

Implementation: `backend/utils/data_formatter.py` handles this automatically.

---

## 2. Data Classification (A/B/C)

### A-Class: User Configuration Data

- Small volume (<1000 records), low update frequency
- Full CRUD support, requires validation and business rules
- Response time: <200ms
- Examples: sales campaigns, targets, performance config, field mapping dictionary

### B-Class: Business Data

- Large volume (millions+), high update frequency
- Primarily query (GET), requires pagination and multi-dimension filtering
- Response time: <500ms (simple), <2s (complex aggregation)
- Examples: orders, products, inventory, finance, field mapping ingestion

### C-Class: Computed Data

- Medium volume (10K-1M), medium update frequency
- Query-only, real-time or pre-computed (materialized views)
- Response time: <1s (pre-computed), <3s (real-time)
- Cache strategy: health scores (5min TTL), achievement rate (1min), rankings (5min)
- Examples: dashboards, store analytics, health scores

See `docs/DATA_CLASSIFICATION_API_GUIDE.md` for full details.

---

## 3. RESTful Design Principles

### 3.1 HTTP Methods

| Method | Purpose | Idempotent |
|--------|---------|------------|
| GET | Query resources | Yes |
| POST | Create resources | No |
| PUT | Full update | Yes |
| DELETE | Delete resources | Yes |
| PATCH | Partial update | Yes |

### 3.2 URL Design

- Resource names: plural nouns (`/api/orders`, not `/api/order`)
- Hierarchy: reflect relationships (`/api/orders/{order_id}/items`)
- Lowercase with underscores
- No verbs in URLs (verbs come from HTTP methods)

```
GET    /api/orders              # List orders
GET    /api/orders/{order_id}   # Get single order
POST   /api/orders              # Create order
PUT    /api/orders/{order_id}   # Update order
DELETE /api/orders/{order_id}   # Delete order
PATCH  /api/orders/{order_id}   # Partial update
```

---

## 4. HTTP Status Codes & Error Codes

### 4.1 Standard Status Codes

| Code | Meaning | Usage |
|------|---------|-------|
| 200 | OK | Success (legacy: business errors also return 200 with `success: false`) |
| 201 | Created | Resource created |
| 204 | No Content | Deletion success (no body) |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Not authenticated |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Unique constraint violation |
| 422 | Unprocessable Entity | Validation failure |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Maintenance |

### 4.2 Business Error Code Categories

- **1xxx** - System errors (database, cache, message queue, filesystem, network)
- **2xxx** - Business errors (orders, inventory, finance, sales, data sync)
- **3xxx** - Data errors (validation, format, integrity, isolation)
- **4xxx** - User errors (auth, permissions, parameters, rate limiting)

See `backend/utils/error_codes.py` for the authoritative list of error codes (IntEnum SSOT).

---

## 5. Rate Limiting

### Default Limits

| API Type | Limit |
|----------|-------|
| Normal API | 100 req/min/user |
| Write API | 50 req/min/user |
| Batch API | 10 req/min/user |

### Exceeded Response

```json
{
  "success": false,
  "message": "Rate limit exceeded",
  "error_code": "429",
  "retry_after": 60
}
```

Headers: `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

---

## 6. Pagination

### Request Parameters

- `page`: page number (starts from 1)
- `page_size`: items per page (default 20, max 100)

### Performance Requirements

- Large dataset queries MUST be paginated
- Never load all data at once
- Default page_size=20, max 100

---

## 7. Sorting and Filtering

- Sort: `?sort=order_date&order=desc`
- Filter: `?platform=shopee&start_date=2025-01-01&end_date=2025-01-31`
- Date range: `start_date` and `end_date` (ISO 8601)

---

## 8. API Versioning

- **Path versioning (preferred)**: `/api/v1/orders`, `/api/v2/orders`
- **Header versioning (alternative)**: `X-API-Version: 1.0`
- Backward compatible: support at least 2 major versions
- Deprecation: 3-month notice, remove after 1 year
- Breaking changes: must increment major version

---

## 9. API Documentation

- OpenAPI 3.0: FastAPI auto-generates Swagger docs at `/api/docs`
- All endpoints must have clear descriptions
- All parameters must have type, default, required flag
- All possible response status codes must be documented
- Must include request and error response examples

---

## 10. API Security

- Bearer Token: `Authorization: Bearer <token>`
- Token expiry: Access Token (15min), Refresh Token (7d)
- Permission check required on every endpoint
- Resource-level permissions (e.g., only own shop data)
- Pydantic validation for all request parameters

---

## 11. Performance Requirements

| Query Type | P95 Target |
|-----------|------------|
| List query | < 500ms |
| Detail query | < 200ms |
| TopN query | < 2s |
| P&L report | < 2s |

- Index optimization for query fields
- Avoid N+1 queries (use joinedload)
- Paginate large dataset queries

---

## 12. Best Practices

### Use Unified Response Helpers

```python
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type

return success_response(data={"id": 1})
return error_response(code=ErrorCode.ORDER_NOT_FOUND, message="Order not found",
                      error_type=get_error_type(ErrorCode.ORDER_NOT_FOUND))
return pagination_response(data=order_list, page=1, page_size=20, total=100)
```

### Frontend API Conventions

- Unified instance: `frontend/src/api/index.js`
- Method naming: `getXxx`, `createXxx`, `updateXxx`, `deleteXxx`
- Params: GET uses `params`, POST/PUT/DELETE uses `data`
- Error handling: `handleApiError()` for unified error handling
- Null data: use `formatNumber()`, `formatDate()` formatters

### Idempotency

- GET/PUT/DELETE: must be idempotent
- POST: non-idempotent (use idempotency key when needed)

### Caching

- GET: cacheable (ETag or Cache-Control)
- POST/PUT/DELETE: not cached

---

## 13. Code Review Process

### 13.1 Roles and Responsibilities

**Developer**:
- Follow all design rules
- Complete self-check before submitting code
- Fix issues found during review
- Update related documentation

**Reviewer**:
- Check code against design rules using checklists
- Provide fix suggestions
- Approve or reject merge

**DBA** (for database changes):
- Review table structure, index, and foreign key changes
- Execute migrations
- Monitor database performance

### 13.2 Review Workflow

1. **Pre-submission self-check**:
   - Run `python scripts/review_schema_compliance.py`
   - Run `python scripts/verify_contract_first.py`
   - Verify code meets all checklist items

2. **Code review**:
   - Reviewer checks database model definitions, ingestion flow, field mapping, materialized views, data validation
   - Records issues by severity

3. **Database change review** (when applicable):
   - Developer creates Alembic migration
   - DBA reviews migration script
   - Test in dev environment
   - Execute in production
   - Verify results

4. **Periodic review**:
   - Weekly during development phase
   - Monthly in production phase

### 13.3 Issue Severity Levels

| Level | Action |
|-------|--------|
| Error | Must fix, cannot merge |
| Warning | Should fix, can merge but must track |
| Info | Optional fix, can merge |

### 13.4 Quality Targets

- Error-level issues: 0
- Warning-level issues: <= 5
- Code review coverage: 100%
- Database change review coverage: 100%
- Code review time: <= 2 hours
- Database change review time: <= 4 hours
- Issue fix time: <= 1 day

---

## 14. Code Review Checklist

### 14.1 Database Model Review

**Primary key design**:
- [ ] Operational data tables use business identifiers as PK (platform_code, shop_id, order_id, platform_sku)?
- [ ] Business data tables use auto-increment ID + unique business index?
- [ ] PK fields are NOT NULL?
- [ ] Composite PK includes all required business dimensions?

**NULL rules**:
- [ ] Critical business fields (quantity, unit_price, total_amount) are NOT NULL with defaults?
- [ ] Optional fields allow NULL but have defaults?

**Unique indexes**:
- [ ] Tables with auto-increment ID have business unique indexes?
- [ ] Unique index includes all necessary business dimensions?

### 14.2 Data Ingestion Review

- [ ] shop_id: sourced from data first, then AccountAlias mapping, then file metadata, then default?
- [ ] platform_code: sourced from file metadata (CatalogFile), validated against DimPlatform?
- [ ] AccountAlias mapping used for non-standard shop names?

### 14.3 Field Mapping Review

- [ ] Standard fields used (from FieldMappingDictionary)?
- [ ] Mapping output matches fact table structure?
- [ ] Unmapped fields go to attributes JSON?
- [ ] Pattern-based mappings have field_pattern, target_table, dimension_config?

### 14.4 Materialized View Review

- [ ] Main views include all core fields for the data domain?
- [ ] Unique indexes created for CONCURRENTLY refresh?
- [ ] Auxiliary views have clear dependency on main views or base data?

### 14.5 Data Validation Review

- [ ] Numeric field types validated (Float, Integer)?
- [ ] Date field formats validated?
- [ ] NULL and empty string handling?
- [ ] Required fields validated?
- [ ] Value ranges checked (e.g., amount >= 0)?
- [ ] Business rules validated (e.g., total = items + shipping - discount)?

### 14.6 Validation Tools

```bash
python scripts/review_schema_compliance.py
curl http://localhost:8001/api/database-design/validate
curl http://localhost:8001/api/database-design/validate/data-ingestion
curl http://localhost:8001/api/database-design/validate/field-mapping
```

---

## 15. HTTP Status Code Gradual Migration Strategy

### Current State (Legacy)

Legacy endpoints return HTTP 200 with `success: false` for business errors:

```json
HTTP 200
{
  "success": false,
  "error": {"code": 2001, "type": "BusinessError"},
  "message": "Order not found"
}
```

### Target State (New Endpoints)

New endpoints use semantic HTTP status codes via `error_response_v2()`:

```
HTTP 404  ->  Resource not found
HTTP 409  ->  Conflict (unique constraint violation)
HTTP 422  ->  Validation failure
```

### Migration Rules

1. **Legacy endpoints**: Keep HTTP 200 with `success: false` pattern. Do NOT change existing behavior.
2. **New endpoints** (created after this rule): Use semantic HTTP status codes (404/409/422) via `error_response_v2()`.
3. **Frontend Axios interceptor**: Handles both modes -- checks `success` field for 200 responses, and handles HTTP error status codes via `error.response.status`.
4. **Full migration**: Converting all legacy endpoints to semantic HTTP status codes will be done as a separate future change, requiring coordinated frontend/backend updates.

---

## Related Documents

- [API Contract Guide](../API_CONTRACTS.md)
- [Data Classification Guide](../DATA_CLASSIFICATION_API_GUIDE.md)
- [API Endpoints Inventory](../API_ENDPOINTS_INVENTORY.md)
- [C-Class Cache Implementation](../C_CLASS_CACHE_IMPLEMENTATION.md)

---

**Last updated**: 2026-03-16
**Status**: Production-ready (v4.20.0)

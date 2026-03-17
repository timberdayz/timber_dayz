# Error Handling & Logging

**Version**: v4.20.0
**Standard**: Enterprise-grade error handling and log management

---

## 1. Error Code System

### 1.1 Error Code Categories

- **1xxx** - System errors (database, cache, message queue, external API, filesystem)
- **2xxx** - Business errors (orders, inventory, finance, sales, data sync)
- **3xxx** - Data errors (validation, format, integrity, isolation, duplicates)
- **4xxx** - User errors (parameters, missing params, permissions, not found, rate limit)

**SSOT**: See `backend/utils/error_codes.py` for the authoritative list of error codes (IntEnum SSOT). Do NOT duplicate specific error code values in documentation.

---

## 2. Error Classification

### ValidationError (Data validation failure)
- **Trigger**: Pydantic validation failure, data format error
- **HTTP Status**: 422 Unprocessable Entity
- **Handling**: Return detailed validation error info

```python
raise HTTPException(
    status_code=422,
    detail={
        "error_code": "3001",
        "message": "Data validation failed",
        "errors": [
            {"field": "order_id", "message": "Order ID cannot be empty"},
            {"field": "total_amount", "message": "Amount must be > 0"}
        ]
    }
)
```

### BusinessError (Business rule violation)
- **Trigger**: Insufficient stock, invalid order state transition
- **HTTP Status**: 400 Bad Request or 409 Conflict
- **Handling**: Return business error with suggested action

```python
raise HTTPException(
    status_code=409,
    detail={
        "error_code": "2003",
        "message": "Insufficient stock",
        "details": {"sku": "SKU123", "requested": 100, "available": 50}
    }
)
```

### SystemError (System exception)
- **Trigger**: Database error, network error, resource exhaustion
- **HTTP Status**: 500 Internal Server Error or 503 Service Unavailable
- **Handling**: Log full error details, return user-friendly message

```python
try:
    # database operation
except Exception as e:
    logger.error(f"Database operation failed: {e}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail={"error_code": "1001", "message": "System error, please retry later",
                "request_id": request_id}
    )
```

### AuthenticationError
- **Trigger**: Invalid/expired token, not logged in
- **HTTP Status**: 401 Unauthorized

### AuthorizationError
- **Trigger**: User lacks permission for resource
- **HTTP Status**: 403 Forbidden

### NotFoundError
- **Trigger**: Queried resource does not exist
- **HTTP Status**: 404 Not Found

---

## 3. Error Handling Strategy

### 3.1 Exception Catching

- Use try-except for all potential exceptions
- Catch specific exception types, not bare `Exception`
- Preserve exception chain with `raise ... from e`

```python
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from modules.core.db import FactOrder

async def get_order_or_fail(db: AsyncSession, order_id: int) -> FactOrder:
    try:
        result = await db.execute(
            select(FactOrder).where(FactOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundError(f"Order not found: {order_id}")
        return order
    except SQLAlchemyError as e:
        logger.error(f"Database query failed: {e}", exc_info=True)
        raise SystemError("Database error") from e
```

### 3.2 Exception Scope and Error Message Alignment (MANDATORY)

To prevent misattribution -- e.g., reporting a serialization error as "parameter format error" -- follow these rules:

- **Keep exception scope narrow**: Only wrap the code that corresponds to a specific error message in try/except. Do NOT wrap "param validation + business logic + serialization" in one big try with a single except returning the same message.
- **One error message per failure cause**: The message (and error code) returned to users MUST match the actual failure reason. Param validation -> param error; Pydantic/serialization -> data validation/processing error; DB failure -> system/query error.

**Bad** (prohibited):
```python
try:
    normalized = validate_param(raw)     # only this is "param format error"
    result = do_query(normalized)
    data = serialize(result)             # may throw serialization error
    return JSONResponse(data)
except (ValueError, TypeError):
    return error_response(message="Parameter format error")  # misattributes serialization errors
```

**Good** (recommended):
```python
try:
    normalized = validate_param(raw)
except (ValueError, TypeError):
    return error_response(message="Parameter format error")

try:
    result = do_query(normalized)
    data = serialize(result)
    return JSONResponse(data)
except Exception as e:
    logger.error("Query/serialization failed", exc_info=True)
    return error_response(message="Processing failed", detail=str(e))
```

### 3.3 Error Logging

- Log complete error info including stack trace
- Include context: request_id, user_id, action
- Sanitize sensitive info (passwords, tokens)

```python
logger.error(
    "Order creation failed",
    extra={
        "request_id": request_id,
        "user_id": user_id,
        "action": "create_order",
        "order_id": order_id,
        "error": str(e)
    },
    exc_info=True
)
```

### 3.4 User-Friendly Messages

- Return meaningful error messages (no system internals)
- Use business error codes (2xxx series)
- Provide recovery suggestions ("Check the order ID")

### 3.5 Error Recovery

- **Retry**: Auto-retry for transient errors (network, DB connection)
- **Degradation**: Graceful fallback when services unavailable (e.g., return cached data)
- **Circuit breaker**: Prevent cascade failures

---

## 4. Log Level Standards

| Level | When to Use | Content | Action |
|-------|------------|---------|--------|
| ERROR | Must-handle errors (system exceptions, business failures) | Full error, stack trace, context | Send alert, log to error file |
| WARNING | Needs attention (data quality, performance) | Problem description, impact, suggestion | Log, optionally alert |
| INFO | Key business flow (API calls, ingestion, state changes) | Operation type, key params, result | Log to info file |
| DEBUG | Debug info (dev only, disabled in production) | Detailed execution flow, intermediate values | Dev environment only |

### Examples

```python
logger.error("Order creation failed",
    extra={"order_id": order_id, "error": str(e)}, exc_info=True)

logger.warning("Order amount abnormal",
    extra={"order_id": order_id, "amount": amount, "threshold": 10000})

logger.info("Order created successfully",
    extra={"order_id": order_id, "amount": amount, "platform": platform})

logger.debug("Processing order data",
    extra={"order_data": order_data, "step": "validation"})
```

---

## 5. Structured Logging

### JSON Format

Use JSON-structured logs for log aggregation (ELK/Splunk):

```python
logger.info(
    "Order created successfully",
    extra={
        "request_id": request_id,
        "user_id": user_id,
        "action": "create_order",
        "order_id": order_id,
        "platform": platform,
        "amount": amount,
        "duration_ms": duration_ms,
        "status": "success"
    }
)
```

### Standard Fields

| Field | Description |
|-------|-------------|
| request_id | Unique request identifier (traces full call chain) |
| user_id | User performing the action |
| action | Operation type (create_order, update_order) |
| duration | Operation time in ms |
| status | success / failure |
| error_code | Error code (on failure) |
| error_message | Error message (on failure) |

### Sensitive Data Sanitization

- Passwords: replace with `***`
- Tokens: log only first 8 characters
- Credit card numbers: log only last 4 digits
- ID numbers: partial masking

---

## 6. Log Retention Policy

| Tier | Duration | Storage | Purpose |
|------|----------|---------|---------|
| Hot | 30 days | SSD | Troubleshooting, performance analysis |
| Warm | 90 days | HDD | Data audit, compliance |
| Cold | 365 days | Archive | Historical audit, compliance |
| Audit | Permanent | Immutable archive | Financial/security audit |

---

## 7. Log Aggregation and Analysis

### Tools
- ELK Stack (Elasticsearch + Logstash + Kibana)
- Splunk (enterprise)
- AWS CloudWatch (cloud)

### Query Capabilities
- Time range filtering
- Keyword search
- Multi-dimension filtering (user_id, action, status)

### Alert Rules
- Error rate > 5% -> alert
- Response time > 2s -> alert
- Anomaly patterns (e.g., mass login failures) -> alert

---

## 8. Frontend Error Handling

### 8.1 Vue Component Error Handling

```vue
<script setup>
import { computed, onErrorCaptured } from 'vue'
import { ElMessage } from 'element-plus'

onErrorCaptured((err, instance, info) => {
  console.error('Component error:', err, info)
  ElMessage.error('Component failed to load, please refresh')
  return false
})

const currentUser = computed(() => {
  try {
    if (authStore.user) return authStore.user
  } catch (error) {
    console.error('Failed to get user info:', error)
    return { id: 1, username: 'user', name: 'User', roles: [] }
  }
})
</script>
```

### 8.2 API Error Interceptor

The Axios interceptor in `frontend/src/api/index.js` handles:
- `success: false` responses (business errors via 200 status)
- Network errors (no response)
- HTTP errors (401/403/404/422/500+)
- User-friendly messages per error type

### 8.3 Frontend Error Logging

```javascript
export const logError = (error, context = {}) => {
  const errorInfo = {
    message: error.message,
    stack: error.stack,
    type: error.constructor.name,
    timestamp: new Date().toISOString(),
    url: window.location.href,
    ...context
  }
  if (import.meta.env.DEV) console.error('Frontend error:', errorInfo)
  // Production: report to error service (Sentry, LogRocket, etc.)
}
```

### 8.4 User-Friendly Error Messages

- Simple and clear, user-understandable
- Provide action suggestions ("please refresh", "please retry later")
- Classify by error type (network/auth/permission/general)
- Never show technical terms to users

### 8.5 Frontend Error Handling Checklist

**Component development**:
- [ ] Critical logic wrapped in try-catch
- [ ] Computed properties have error handling and defaults
- [ ] Async functions have error handling
- [ ] Errors return defaults so component still renders

**API calls**:
- [ ] Response interceptor handles errors uniformly
- [ ] Error classification correct (network/business/system)
- [ ] User messages friendly (no tech jargon)
- [ ] Errors logged

---

**Last updated**: 2026-03-16
**Status**: Production-ready (v4.20.0)

## ADDED Requirements

### Requirement: Async CRUD Base Service
The system SHALL provide a generic `AsyncCRUDService` base class in `backend/services/base_service.py` that implements standard Create, Read, Update, Delete operations for any SQLAlchemy model with corresponding Pydantic schemas. The base class SHALL only support async operations (no sync `CRUDService`), enforcing the project's async-first mandate. All newly created Service classes MUST inherit from this base class. Existing Service classes MAY optionally migrate.

#### Scenario: Create entity via base service
- **WHEN** a Service inheriting `AsyncCRUDService` calls `await create(obj_in=schema_instance)`
- **THEN** the system SHALL persist a new record to the database and return the created model instance

#### Scenario: Read single entity
- **WHEN** a Service inheriting `AsyncCRUDService` calls `await get(id=entity_id)`
- **THEN** the system SHALL return the model instance if found, or `None` if not found

#### Scenario: Read paginated list
- **WHEN** a Service inheriting `AsyncCRUDService` calls `await get_multi(skip=0, limit=20)`
- **THEN** the system SHALL return a list of model instances with the specified offset and limit applied

#### Scenario: Update entity
- **WHEN** a Service inheriting `AsyncCRUDService` calls `await update(db_obj=existing, obj_in=update_schema)`
- **THEN** the system SHALL update only the fields present in the update schema and return the updated model instance

#### Scenario: Delete entity
- **WHEN** a Service inheriting `AsyncCRUDService` calls `await remove(id=entity_id)`
- **THEN** the system SHALL delete the record and return the deleted model instance, or `None` if not found

#### Scenario: Soft delete entity
- **WHEN** a Service inheriting `AsyncCRUDService` calls `await soft_delete(id=entity_id)` and the model has a `deleted_at` column
- **THEN** the system SHALL set `deleted_at` to the current UTC timestamp instead of physically deleting the record

#### Scenario: Soft delete auto-filtering on queries
- **WHEN** a Service with soft delete enabled calls `await get(id=entity_id)` or `await get_multi()`
- **THEN** the system SHALL automatically add a `WHERE deleted_at IS NULL` filter, excluding soft-deleted records from results

#### Scenario: Query includes soft-deleted records
- **WHEN** a Service calls `await get(id=entity_id, include_deleted=True)` or `await get_multi(include_deleted=True)`
- **THEN** the system SHALL NOT add the `deleted_at IS NULL` filter, returning all records including soft-deleted ones

### Requirement: Audit Hook Integration
The `AsyncCRUDService` SHALL provide optional audit hook methods (`on_after_create`, `on_after_update`, `on_after_delete`) that subclasses can override to log audit trail entries. A class attribute `enable_audit: bool` SHALL control whether hooks are invoked.

#### Scenario: Audit hook triggered on create
- **WHEN** a Service with `enable_audit = True` creates an entity
- **THEN** the system SHALL invoke `on_after_create(obj)` after the database commit

#### Scenario: Audit hook not triggered when disabled
- **WHEN** a Service with `enable_audit = False` (default) creates an entity
- **THEN** the system SHALL NOT invoke `on_after_create(obj)`

### Requirement: Optimistic Locking Support
The `AsyncCRUDService` SHALL support optimistic locking via an optional `version` column. A class attribute `enable_optimistic_lock: bool` SHALL control whether version checks are performed during update and remove operations.

#### Scenario: Optimistic lock conflict on update
- **WHEN** a Service with `enable_optimistic_lock = True` calls `await update(db_obj=obj, obj_in=data)` and the database `version` differs from `obj.version`
- **THEN** the system SHALL raise `OptimisticLockError` without modifying the record

#### Scenario: Version auto-increment on successful update
- **WHEN** a Service with `enable_optimistic_lock = True` successfully updates an entity
- **THEN** the system SHALL automatically increment the `version` field by 1

#### Scenario: Optimistic lock disabled by default
- **WHEN** a Service with `enable_optimistic_lock = False` (default) updates an entity
- **THEN** the system SHALL NOT check the `version` field and SHALL update unconditionally

### Requirement: Transaction Management
The system SHALL provide a `@transactional` decorator in `backend/services/base_service.py` that wraps Service methods in a savepoint-based transaction. The decorator MUST coordinate with `get_async_db()` which handles the request-level commit/rollback.

#### Scenario: Successful savepoint release
- **WHEN** a Service method decorated with `@transactional` completes without exception
- **THEN** the system SHALL release the savepoint (changes remain in the outer request-level transaction)
- **AND** the final commit SHALL be performed by `get_async_db()` at request end

#### Scenario: Savepoint rollback on exception
- **WHEN** a Service method decorated with `@transactional` raises an exception
- **THEN** the system SHALL rollback the savepoint (only this method's changes are reverted)
- **AND** the exception SHALL be re-raised to the caller

#### Scenario: Multiple @transactional methods in one request
- **WHEN** a router calls two `@transactional` Service methods sequentially and the second method raises an exception
- **THEN** the first method's savepoint SHALL already be released (changes preserved)
- **AND** the second method's savepoint SHALL be rolled back (changes reverted)
- **AND** if the exception propagates to `get_async_db()`, the entire request-level transaction SHALL be rolled back

#### Scenario: Nested @transactional calls
- **WHEN** a `@transactional` method calls another `@transactional` method
- **THEN** the inner method SHALL create a deeper-level savepoint via `begin_nested()`
- **AND** rollback of the inner savepoint SHALL NOT affect the outer savepoint

#### Scenario: Manual savepoint within @transactional
- **WHEN** a Service method uses `async with self.db.begin_nested()` within a `@transactional` method
- **THEN** the system SHALL create an additional PostgreSQL savepoint that can be independently rolled back

### Requirement: Unified Pagination Utility
The system SHALL provide an `async_paginate_query()` function in `backend/utils/pagination.py` that accepts a SQLAlchemy query, async database session, page number, and page size, and returns a tuple of `(data_list, total_count)` compatible with the existing `pagination_response()` function in `api_response.py`.

#### Scenario: Standard pagination
- **WHEN** `async_paginate_query(query, db, page=2, page_size=10)` is called
- **THEN** the system SHALL return `(items, total)` where `items` contains at most 10 records from the correct offset and `total` is the full count

#### Scenario: Page size clamping
- **WHEN** `async_paginate_query(query, db, page=1, page_size=500)` is called with default `max_page_size=100`
- **THEN** the system SHALL clamp `page_size` to 100 and return at most 100 items

#### Scenario: Empty result set
- **WHEN** `async_paginate_query(query, db, page=1, page_size=20)` is called and the query matches zero records
- **THEN** the system SHALL return `([], 0)`

### Requirement: Test Infrastructure Fixtures
The system SHALL provide shared pytest fixtures in `backend/tests/conftest.py` that enable isolated, repeatable testing with dual database modes.

#### Scenario: SQLite session fixture for unit tests
- **WHEN** a test function uses the `sqlite_session` fixture
- **THEN** the system SHALL provide an async SQLAlchemy session backed by an in-memory SQLite database, and all changes SHALL be rolled back after each test

#### Scenario: PostgreSQL session fixture for integration tests
- **WHEN** a test function marked with `@pytest.mark.pg_only` uses the `pg_session` fixture
- **THEN** the system SHALL provide an async SQLAlchemy session backed by a PostgreSQL container (via testcontainers), and all changes SHALL be rolled back after each test

#### Scenario: API test client fixture
- **WHEN** a test function uses the `async_client` fixture
- **THEN** the system SHALL provide an httpx `AsyncClient` instance with the `get_async_db` dependency overridden to use the test database session

#### Scenario: Auth mock fixture
- **WHEN** a test function uses the `auth_headers` fixture
- **THEN** the system SHALL provide a dictionary with a valid mock JWT Authorization header suitable for authenticated endpoint testing

### Requirement: Contract-First Schema Organization
All Pydantic request/response models for API endpoints MUST be defined in `backend/schemas/{domain}.py` files. Router files MUST NOT define inline Pydantic `BaseModel` subclasses. The `backend/schemas/__init__.py` file MUST re-export all schema classes.

#### Scenario: New endpoint requires request model
- **WHEN** a developer creates a new API endpoint that accepts a JSON body
- **THEN** the request model MUST be defined in the corresponding `backend/schemas/{domain}.py` file and imported into the router

#### Scenario: Existing inline model migration
- **WHEN** a router file contains an inline `BaseModel` subclass
- **THEN** the model MUST be migrated to `backend/schemas/{domain}.py` with the same class name and fields, and the router MUST import it from the new location

#### Scenario: Backward-compatible re-export during migration
- **WHEN** external modules import a Pydantic model from a router file
- **THEN** the router file MUST temporarily re-export the model with a `# DEPRECATED` comment until all consumers are updated

### Requirement: Datetime Standard
All Python code MUST use `datetime.now(timezone.utc)` instead of the deprecated `datetime.utcnow()`. ORM column defaults MUST use `server_default=func.now()` for database-side timestamp generation. All `DateTime` columns MUST use `DateTime(timezone=True)` for timezone-aware storage.

#### Scenario: New code uses timezone-aware datetime
- **WHEN** a developer writes code that requires the current UTC time
- **THEN** the code MUST use `from datetime import datetime, timezone` and `datetime.now(timezone.utc)`

#### Scenario: ORM default timestamp
- **WHEN** a developer defines a `created_at` or `updated_at` column in schema.py
- **THEN** the column MUST use `server_default=func.now()` and `DateTime(timezone=True)`

### Requirement: Service Dependency Injection
Router endpoint functions MUST receive Service instances via FastAPI `Depends()` rather than instantiating them directly within the function body.

#### Scenario: Service injected via Depends
- **WHEN** a router endpoint needs to use a Service class
- **THEN** the endpoint function signature MUST include a parameter like `service: MyService = Depends(get_my_service)` where `get_my_service` is a factory function

#### Scenario: Service testability
- **WHEN** a test needs to mock a Service dependency
- **THEN** the test SHALL override the `Depends()` factory using `app.dependency_overrides` to inject a mock service

### Requirement: Router Size Limit
Each router file MUST contain no more than 15 API endpoint functions. Router files exceeding this limit MUST be split into sub-domain files that share the same URL prefix.

#### Scenario: Router exceeds size limit
- **WHEN** a router file contains more than 15 endpoint functions
- **THEN** it MUST be refactored into multiple sub-domain router files each with <= 15 endpoints

#### Scenario: Split routers preserve URL structure
- **WHEN** a router is split into sub-domain files
- **THEN** all endpoint URLs MUST remain unchanged (same prefix and paths as before the split)

### Requirement: Caching Strategy Standard
The system SHALL define standardized caching patterns documented in `CODE_PATTERNS.md`, leveraging the existing `CacheService`. Caching SHALL be categorized into tiers: L1 in-process (config, enums, TTL 300s), L2 Redis (sessions, frequent queries, TTL 600s), and no-cache (transactional data, audit logs).

#### Scenario: Cache-aside pattern for read-heavy data
- **WHEN** a Service needs to read frequently-accessed, slowly-changing data
- **THEN** the Service SHOULD implement the cache-aside pattern: check cache first, fetch from DB on miss, populate cache on fetch, invalidate cache on write

#### Scenario: Cache invalidation on write
- **WHEN** a Service updates or deletes a cached entity
- **THEN** the Service MUST invalidate the corresponding cache entry before or after the database write

### Requirement: Shared Dependency Extraction Before Router Split
Before any router file is split into sub-domain files, all shared symbols imported by multiple router files MUST be extracted to dedicated modules. This prevents import chain breakage during router splitting.

#### Scenario: Authentication dependencies extracted
- **GIVEN** `get_current_user` is imported by 14+ router files from `auth.py`
- **AND** `require_admin` is imported by 9+ router files from `users.py`
- **WHEN** router splitting is planned
- **THEN** these symbols MUST be moved to `backend/dependencies/auth.py` BEFORE any router is split
- **AND** the original files (`auth.py`, `users.py`) MUST re-export the symbols for backward compatibility

#### Scenario: WebSocket manager extracted
- **GIVEN** `ConnectionManager` is imported by 2 services and 3 tests from `collection_websocket.py`
- **WHEN** `collection.py` splitting is planned
- **THEN** `ConnectionManager` MUST be moved to `backend/services/websocket_manager.py` BEFORE the split

#### Scenario: Split router preserves re-export shim
- **WHEN** a router file is split into sub-domain files
- **THEN** the original router file MUST be preserved as a re-export shim with `# DEPRECATED` comments
- **AND** external scripts and tests importing from the original file SHALL continue to work without modification

### Requirement: Phase Gate Validation
Each implementation phase MUST pass a validation gate before the next phase begins. A phase gate failure blocks progression.

#### Scenario: Post-phase system health check
- **WHEN** a phase is completed
- **THEN** the following checks MUST pass:
  - `python run.py --local` starts without errors
  - `/docs` Swagger page renders with all expected endpoints
  - `pytest backend/tests/` passes with zero new failures
  - `python scripts/verify_architecture_ssot.py` returns 100%

#### Scenario: Post-datetime critical flow verification
- **WHEN** Phase 3 (datetime standardization) is completed
- **THEN** the following time-sensitive flows MUST be manually verified:
  - JWT token expiration and refresh
  - Collection task scheduling (time comparisons)
  - Audit log time-range queries
  - Dashboard date filters

#### Scenario: Post-router-split endpoint count verification
- **WHEN** Phase 6 (router splitting) is completed
- **THEN** the total number of Swagger endpoints MUST equal the count recorded before the split
- **AND** all endpoint URLs MUST remain unchanged

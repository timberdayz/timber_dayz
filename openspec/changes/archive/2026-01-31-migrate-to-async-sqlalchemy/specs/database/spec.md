# Database Capability Spec Delta

## ADDED Requirements

### Requirement: Async Database Session Management
The system SHALL provide asynchronous database session management using SQLAlchemy 2.0 async extension.

#### Scenario: Async session creation
- **WHEN** an API endpoint requires database access
- **THEN** an `AsyncSession` is provided via `get_async_db()` dependency injection
- **AND** the session is automatically closed after request completion

#### Scenario: Async session in background tasks
- **WHEN** a background task needs database access
- **THEN** it creates an independent `AsyncSession` using `AsyncSessionLocal()`
- **AND** each concurrent coroutine has its own isolated session

#### Scenario: Non-blocking database queries
- **WHEN** an async database query is executed using `await db.execute(select(...))`
- **THEN** the event loop is NOT blocked
- **AND** other requests can be processed concurrently

### Requirement: Async Database Connection Pool
The system SHALL maintain an async database connection pool for PostgreSQL using asyncpg driver.

#### Scenario: Async connection pool configuration
- **WHEN** the application starts
- **THEN** an async engine is created with `create_async_engine()`
- **AND** connection pool parameters (pool_size, max_overflow) are applied

#### Scenario: Async connection pool warm-up
- **WHEN** `warm_up_async_pool()` is called
- **THEN** connections are pre-established
- **AND** first request latency is reduced

### Requirement: Async Query Execution
The system SHALL execute all database queries asynchronously in async contexts.

#### Scenario: Select query execution
- **WHEN** fetching records using `await db.execute(select(Model).where(...))`
- **THEN** results are returned via `result.scalars().all()` or `result.scalar_one_or_none()`
- **AND** the query does NOT block the event loop

#### Scenario: Insert/Update/Delete execution
- **WHEN** modifying data using `session.add()`, `await session.delete()`
- **THEN** changes are committed using `await session.commit()`
- **AND** the operation does NOT block the event loop

#### Scenario: Transaction rollback
- **WHEN** an error occurs during database operations
- **THEN** the transaction is rolled back using `await session.rollback()`
- **AND** the session is properly cleaned up

## MODIFIED Requirements

### Requirement: Database Configuration Layer
The system SHALL support both synchronous and asynchronous database access during migration period.

#### Scenario: Dual-mode database configuration
- **WHEN** the application initializes database connections
- **THEN** both `engine` (sync) and `async_engine` (async) are available
- **AND** both `SessionLocal` (sync) and `AsyncSessionLocal` (async) are exported

#### Scenario: Gradual migration support
- **WHEN** new code is written
- **THEN** it uses `get_async_db()` and `AsyncSession`
- **AND** legacy code can still use `get_db()` and `Session` temporarily

### Requirement: Background Task Database Access
The system SHALL use independent async sessions for each background task coroutine.

#### Scenario: Concurrent background task execution
- **WHEN** multiple files are processed concurrently in background tasks
- **THEN** each coroutine creates its own `AsyncSession` via `AsyncSessionLocal()`
- **AND** sessions are properly closed in `finally` blocks
- **AND** no session conflicts occur between coroutines

#### Scenario: Error handling in background tasks
- **WHEN** an error occurs in a background task database operation
- **THEN** `await session.rollback()` is called
- **AND** the session is closed
- **AND** the error is logged with context

## REMOVED Requirements

### Requirement: Synchronous-only Database Access (Deprecated)
**Reason**: Synchronous database access in async contexts blocks the event loop, causing frontend unresponsiveness during data synchronization.

**Migration**: 
1. Replace `db: Session = Depends(get_db)` with `db: AsyncSession = Depends(get_async_db)`
2. Replace `db.query(Model)` with `await db.execute(select(Model))`
3. Replace `db.commit()` with `await db.commit()`

### Requirement: time.sleep() in Database Operations (Deprecated)
**Reason**: Blocking `time.sleep()` calls in async contexts block the event loop.

**Migration**: Replace `time.sleep(n)` with `await asyncio.sleep(n)` in all async functions.


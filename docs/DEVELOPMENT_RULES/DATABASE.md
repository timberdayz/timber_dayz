# Database Design, Migration & Checklists

**Version**: v4.20.0
**Standard**: SAP/Oracle ERP database design standards + PostgreSQL best practices

---

## 1. Table Design Principles

### 1.1 Primary Key Design

- All tables MUST have a primary key
- PK types: `INTEGER` (auto-increment) or `BIGINT` (large volumes)
- PK naming: `id` (unified convention)
- Composite PK: only when business requires (e.g., `(order_id, line_id)`)

**Operational data**: use business identifiers as PK:
```python
class FactOrder(Base):
    __tablename__ = "fact_orders"
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)
```

**Business data**: use auto-increment ID + unique business index:
```python
class FactProductMetric(Base):
    __tablename__ = "fact_product_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    __table_args__ = (
        Index("ix_product_unique", "platform_code", "shop_id", "platform_sku",
              "metric_date", "granularity", "data_domain", unique=True),
    )
```

### 1.2 Foreign Key Constraints

- Foreign keys MUST be explicitly declared
- Cascade strategies:
  - `CASCADE`: delete children when parent deleted (e.g., order -> order items)
  - `SET NULL`: set FK to NULL when parent deleted (e.g., category -> product)
  - `RESTRICT`: prevent parent deletion if children exist (default)
- Naming: `fk_table_name_field_name`

### 1.3 Field Type Conventions

| Type | Usage | Notes |
|------|-------|-------|
| `VARCHAR(n)` | Strings | n must match actual need; no blanket `VARCHAR(255)` |
| `TEXT` | Long text | descriptions, notes |
| `INTEGER` / `BIGINT` / `SMALLINT` | Numbers | choose by range |
| `DECIMAL(15, 2)` | Monetary amounts | avoid float for currency |
| `BOOLEAN` | True/false | not INTEGER(0/1) |
| `DATE` | Date only | e.g., order_date_local |
| `TIMESTAMP` / `TIMESTAMPTZ` | Date+time | use TZ variant when timezone needed |
| `JSONB` | Structured data | e.g., attributes field |

Platform code: `VARCHAR(32)`, Order ID: `VARCHAR(128)`, Product name: `VARCHAR(512)`.

### 1.4 NOT NULL and Default Values

- Business identifiers (platform_code, shop_id, order_id): MUST be NOT NULL
- Monetary fields (total_amount, quantity): MUST be NOT NULL (NULL breaks calculations)
- Timestamps (created_at, updated_at): MUST be NOT NULL
- Optional fields: may allow NULL but document the business rationale
- Status fields: default to most common initial state (e.g., `status='pending'`)
- Numeric fields: default 0 instead of NULL
- Boolean fields: default False

### 1.5 Audit Fields (Required)

```python
class FactOrder(Base):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(64), nullable=True)
    updated_by = Column(String(64), nullable=True)
    deleted_at = Column(Date, nullable=True)  # soft delete
```

---

## 2. Index Design

### 2.1 Unique Indexes

- Use `UniqueConstraint` for business uniqueness
- Naming: `uq_table_name_field_name`

```python
__table_args__ = (
    UniqueConstraint("platform_code", "shop_id", "order_id",
                     name="uq_fact_orders_order_id"),
)
```

### 2.2 Composite Indexes

- Follow leftmost-prefix rule: index column order must match WHERE clause order
- Create for frequently queried field combinations
- Avoid too many columns per index (hurts write performance)

```python
Index("ix_fact_orders_platform_shop_date", "platform_code", "shop_id", "order_date_local")
```

### 2.3 Partial Indexes

```python
Index("ix_fact_orders_active", "order_id", postgresql_where=text("status = 'active'"))
```

### 2.4 GIN Indexes (JSONB)

```python
Index("ix_fact_orders_attributes", "attributes", postgresql_using="gin")
```

### 2.5 Expression Indexes

```python
Index("ix_users_email_lower", func.lower(User.email))
```

### 2.6 Index Rules

- Max ~10 indexes per table (more hurts write performance)
- No duplicate indexes (same column combinations)
- Create for WHERE, JOIN, ORDER BY fields
- Monitor index usage; drop unused indexes

---

## 3. Constraint Design

### CHECK Constraints

```python
__table_args__ = (
    CheckConstraint("total_amount >= 0", name="ck_fact_orders_amount_positive"),
    CheckConstraint("quantity > 0", name="ck_fact_orders_quantity_positive"),
)
```

### Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Table | `snake_case`, plural | `fact_orders` |
| Field | `snake_case` | `order_time_utc` |
| Index | `ix_table_field` | `ix_fact_orders_platform_code` |
| Unique | `uq_table_field` | `uq_fact_orders_order_id` |
| Check | `ck_table_field_rule` | `ck_fact_orders_amount_positive` |
| Foreign key | `fk_table_field` | `fk_fact_orders_platform_code` |

Table prefixes: `fact_` (fact tables), `dim_` (dimension tables), `staging_` (temp tables).

---

## 4. Product ID Atomic Design (v4.12.0)

### Redundant product_id Field

- Add `product_id` to FactOrderItem etc. as a redundant lookup field
- Keep existing PK unchanged
- Auto-associate via BridgeProductKeys during ingestion
- Allow NULL if no matching product_id found (log warning, support later fix)

```python
class FactOrderItem(Base):
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)
    product_id = Column(Integer, ForeignKey("dim_product_master.product_id",
                        ondelete="SET NULL"), nullable=True)
    __table_args__ = (
        Index("ix_fact_items_product_id", "product_id"),
    )
```

---

## 5. Performance Optimization

### Table Partitioning

- Time-based partitioning for large tables (monthly/yearly)
- Partition pruning improves query performance

### Materialized Views

- Pre-compute aggregation results
- Refresh strategy: scheduled or incremental
- Main views must have unique indexes for CONCURRENTLY refresh

### Query Optimization

- Never `SELECT *` -- list only needed fields
- Use `LIMIT` for large dataset queries
- Prefer JOINs over subqueries

---

## 6. SQL Writing Standards (Metabase Model SQL)

### 6.1 Format Rules

- Keywords: lowercase (`select`, `from`, `where`)
- Indentation: 2 spaces (no tabs)
- Field list: one field per line, comma at end
- Line length: max 120 characters
- Short COALESCE (<=120 chars): single line; long: multi-line with aligned params

### 6.2 Field Mapping Rules

**String fields**: use `COALESCE()` with 3-5 candidate column names:
```sql
coalesce(raw_data->>'order_id_cn', raw_data->>'order_id', raw_data->>'Order ID') as order_id,
```

**Numeric fields**: strip thousands separator and spaces, cast to numeric:
```sql
coalesce(nullif(replace(replace(raw_data->>'sales_amount', ',', ''), ' ', ''), '')::numeric, 0) as sales_amount,
```

**Percentage fields**: remove %, handle European format (comma -> dot), divide by 100:
```sql
coalesce(nullif(replace(replace(replace(raw_data->>'conversion_rate', '%', ''), ',', '.'), ' ', ''), '')::numeric / 100.0, 0) as conversion_rate,
```

**Timestamp fields**: use NULLIF to handle empty strings before casting:
```sql
coalesce(nullif(raw_data->>'order_time', '')::timestamp, period_start_time) as order_time,
```

### 6.3 CTE Layered Architecture (Mandatory)

All Metabase Model SQL MUST use 4-layer CTE architecture:

**Layer 1 -- Field Mapping**: extract all candidate fields, NO formatting:
```sql
field_mapping AS (
  SELECT
    platform_code, shop_id,
    COALESCE(raw_data->>'visitor_count_cn', raw_data->>'unique_visitors') AS visitor_count_raw,
    -- ...
  FROM b_class.fact_shopee_analytics_daily
)
```

**Layer 2 -- Data Cleaning**: unified formatting logic, written ONCE:
```sql
cleaned AS (
  SELECT
    platform_code, shop_id,
    NULLIF(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), '')::NUMERIC AS visitor_count,
    NULLIF(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), '')::NUMERIC / 100.0 AS click_rate,
    -- ...
  FROM field_mapping
)
```

**Layer 3 -- Deduplication**: based on data_hash, priority daily > weekly > monthly:
```sql
deduplicated AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY platform_code, shop_id, data_hash
      ORDER BY
        CASE granularity WHEN 'daily' THEN 1 WHEN 'weekly' THEN 2 WHEN 'monthly' THEN 3 END ASC,
        ingest_timestamp DESC
    ) AS rn
  FROM cleaned
)
```

**Layer 4 -- Final Output**: only deduplicated rows, set defaults:
```sql
SELECT
  platform_code, shop_id,
  COALESCE(visitor_count, 0) AS visitor_count,
  COALESCE(click_rate, 0) AS click_rate
FROM deduplicated
WHERE rn = 1
```

**CTE Performance Note**: PostgreSQL 12+ inlines single-reference CTEs -- zero performance cost, potentially better optimization.

### 6.4 SQL Comment Standards

- File header: model name, purpose, data sources, platforms, granularity
- Group fields with comments (system fields, base fields, amount fields)
- Comment each UNION ALL block with platform and granularity
- Comment each CTE with layer purpose

---

## 7. Database Migration (Alembic)

### 7.1 Core Principle: Idempotency

**All migrations MUST be repeatable without errors.**

```python
# Table creation
if 'table_name' not in existing_tables:
    op.create_table(...)
else:
    safe_print("[SKIP] table_name already exists")

# Column addition
existing_columns = {c['name'] for c in inspector.get_columns('table_name')}
if 'new_column' not in existing_columns:
    op.add_column('table_name', sa.Column('new_column', ...))

# Index creation
existing_indexes = {idx['name'] for idx in inspector.get_indexes('table_name')}
if 'idx_name' not in existing_indexes:
    op.create_index('idx_name', 'table_name', ['column_name'])
```

### 7.2 Migration Development Flow

**Method 1: autogenerate (preferred)**

1. Modify `modules/core/db/schema.py`
2. `alembic revision --autogenerate -m "add_new_table"`
3. Manually check generated file, ADD idempotency checks (autogenerate does not add them)
4. Test: `alembic upgrade heads` -> `alembic downgrade -1` -> `alembic upgrade heads`

**Method 2: Manual template**

1. Copy `migrations/templates/idempotent_migration.py.template`
2. Fill in `revision`, `down_revision`, `message`
3. Implement `upgrade()` and `downgrade()` with idempotency checks
4. Test as above

**autogenerate limitations**: cannot detect table/column renames (causes data loss), does not handle data migrations or complex constraints.

### 7.3 Schema Snapshot Migration

Current snapshot: `migrations/versions/20260112_v5_0_0_schema_snapshot.py`

- First incremental migration after snapshot: `down_revision = 'v5_0_0_schema_snapshot'`
- Subsequent migrations: chain to previous migration normally
- New environments: `alembic upgrade v5_0_0_schema_snapshot`
- Existing environments: `alembic upgrade heads`
- Regenerate snapshot: `python scripts/generate_schema_snapshot.py`

### 7.4 Common Migration Errors

| Error | Cause | Solution |
|-------|-------|----------|
| DuplicateTable | Migration re-run | Add existence check |
| DuplicateColumn | Migration re-run | Add column existence check |
| FeatureNotSupported (partitioned) | `INCLUDING INDEXES` on partitioned table | Don't use `INCLUDING ALL/INDEXES` |
| Multiple head revisions | Branched history | Use `alembic upgrade heads` (plural) or merge migration |

### 7.5 Migration File Archiving

Old migrations archived to `migrations/versions_archived/`. Index at `migrations/versions_archived/INDEX.md`. Archive script: `scripts/archive_old_migrations.py`.

---

## 8. Database Design Checklist

### 8.1 Table Design

- [ ] All tables have a primary key
- [ ] PK fields are NOT NULL
- [ ] Operational data tables: PK includes platform_code, shop_id, business identifier
- [ ] Business data tables: auto-increment ID + business unique index
- [ ] Business identifier fields NOT NULL (platform_code, shop_id, order_id, platform_sku)
- [ ] Monetary fields NOT NULL with default=0.0
- [ ] Timestamp fields (created_at, updated_at) NOT NULL
- [ ] FK fields: type matches referenced field; appropriate cascade strategy
- [ ] String field lengths match actual need (no blanket VARCHAR(255))
- [ ] Monetary fields use DECIMAL(15,2) or Float
- [ ] Date/time fields use DATE/TIMESTAMP/TIMESTAMPTZ (not VARCHAR)
- [ ] Boolean fields use BOOLEAN (not INTEGER)

### 8.2 Index Design

- [ ] Business unique indexes exist on auto-increment ID tables
- [ ] Query performance indexes for common query fields
- [ ] Index naming follows convention (ix_/uq_/fk_)
- [ ] No excessive indexes (max ~10 per table)

### 8.3 Materialized View Design

- [ ] Main views include all core fields for the data domain
- [ ] Unique indexes for CONCURRENTLY refresh support
- [ ] Naming: `mv_domain_summary` (main), `mv_domain_analysis_type` (auxiliary)
- [ ] Refresh order: main views first, then auxiliary
- [ ] Auxiliary views have clear dependency relationships

### 8.4 Data Ingestion Flow

- [ ] shop_id: priority from source data -> AccountAlias mapping -> file metadata -> default
- [ ] platform_code: from CatalogFile.platform_code, validated against DimPlatform
- [ ] Field mapping output matches fact table structure
- [ ] Field types match between mapping and fact table
- [ ] Required fields have mappings or defaults
- [ ] Data type validation (string, number, date)
- [ ] Value range validation (amount >= 0, quantity > 0)

---

## 9. Database Change Checklist

### 9.1 New Table

- [ ] Table name follows convention (snake_case, plural)
- [ ] Has primary key, follows PK design rules
- [ ] Has created_at and updated_at timestamp fields
- [ ] Appropriate indexes (unique, query)
- [ ] Foreign key constraints where needed
- [ ] Run `python scripts/review_schema_compliance.py`

### 9.2 Modify Table Structure

- [ ] Alembic migration script created
- [ ] Migration has both upgrade and downgrade
- [ ] Impact on existing data assessed (need data migration?)
- [ ] Impact on existing queries assessed
- [ ] Impact on existing APIs assessed
- [ ] Related code and documentation updated

### 9.3 Delete Table

- [ ] No other tables depend on it (FK constraints)
- [ ] No materialized views depend on it
- [ ] No API endpoints use it
- [ ] Data backed up if needed

### 9.4 Field Changes

**Add field**:
- [ ] Name follows snake_case convention
- [ ] Appropriate type and length
- [ ] NULL/NOT NULL correct for business context
- [ ] Default value set if needed
- [ ] Index created if needed for queries

**Modify field**:
- [ ] Data compatibility checked (type conversion)
- [ ] Related queries and APIs updated

**Delete field**:
- [ ] No FK/view/API dependencies
- [ ] Data backed up if needed

### 9.5 Index Changes

- [ ] Name follows convention
- [ ] Column order follows leftmost-prefix principle
- [ ] Write performance impact assessed
- [ ] Query performance impact assessed

### 9.6 Materialized View Changes

- [ ] Unique index created
- [ ] Fields complete for data domain (main view)
- [ ] Dependency relationships clear (auxiliary view)
- [ ] MaterializedViewService updated

### 9.7 Migration Submission Checklist

- [ ] All `op.create_table()` have existence checks
- [ ] All `op.add_column()` have existence checks
- [ ] All `op.create_index()` have existence checks
- [ ] Uses `safe_print()` instead of `print()`
- [ ] `downgrade()` is also idempotent
- [ ] Migration can be repeated without errors
- [ ] No `INCLUDING ALL` or `INCLUDING INDEXES`
- [ ] `revision` and `down_revision` correctly set
- [ ] Tested upgrade and rollback
- [ ] Idempotency verified (repeated execution)

### 9.8 Change Workflow

1. **Prepare**: clarify requirements, assess impact, plan rollback
2. **Implement**: create migration, review, test in dev
3. **Execute**: deploy to production
4. **Verify**: run validation tools, check data integrity, check query performance, update docs

---

## Related Documents

- [V4.6.0 Architecture Guide](../architecture/V4_6_0_ARCHITECTURE_GUIDE.md) - dimension table design
- [Main Views Usage Guide](../MAIN_VIEWS_USAGE_GUIDE.md)
- [Data Migration Guide](../guides/DATA_MIGRATION_GUIDE.md)

---

**Last updated**: 2026-03-16
**Status**: Production-ready (v4.20.0)

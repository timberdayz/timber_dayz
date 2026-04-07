# Local-to-Cloud B-Class Canonical Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reliable local-to-cloud B-class sync path that transports canonical payloads to the cloud with checkpoints and idempotent upserts.

**Architecture:** Local `b_class` tables remain the ingestion landing zone. A dedicated sync worker enumerates local B-class tables, reads canonical fields in checkpointed batches, writes them into cloud-side canonical mirror tables, and records per-table progress and run outcomes. Dynamic columns are excluded from the sync contract and remain a separate projection concern.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, PostgreSQL 15, existing `backend/models/database.py` session factories, existing `modules/core/db/schema.py` SSOT models, pytest

---

### Task 1: Add Local Sync State Tables

**Files:**
- Create: `tests/test_cloud_b_class_sync_schema.py`
- Modify: `modules/core/db/schema.py`
- Modify: `modules/core/db/__init__.py`
- Modify: `backend/models/database.py`
- Create: `scripts/migrate_cloud_sync_tables.py`

- [ ] **Step 1: Write the failing schema contract test**

```python
from modules.core.db import Base


def test_cloud_sync_state_tables_are_registered():
    assert "cloud_b_class_sync_checkpoints" in Base.metadata.tables
    assert "cloud_b_class_sync_runs" in Base.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cloud_b_class_sync_schema.py -v`
Expected: FAIL because the new tables are not registered yet.

- [ ] **Step 3: Add the new ORM models**

Add two SSOT models in `modules/core/db/schema.py`:
- `CloudBClassSyncCheckpoint`
- `CloudBClassSyncRun`

Suggested shape:

```python
class CloudBClassSyncCheckpoint(Base):
    __tablename__ = "cloud_b_class_sync_checkpoints"
    id = Column(Integer, primary_key=True, autoincrement=True)
    table_schema = Column(String(64), nullable=False, default="b_class")
    table_name = Column(String(255), nullable=False)
    last_ingest_timestamp = Column(DateTime(timezone=True), nullable=True)
    last_source_id = Column(BigInteger, nullable=True)
    last_status = Column(String(32), nullable=False, default="pending")
```

```python
class CloudBClassSyncRun(Base):
    __tablename__ = "cloud_b_class_sync_runs"
    run_id = Column(String(100), primary_key=True)
    status = Column(String(32), nullable=False, default="pending")
    total_tables = Column(Integer, nullable=False, default=0)
    succeeded_tables = Column(Integer, nullable=False, default=0)
    failed_tables = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 4: Export the models through package boundaries**

Update `modules/core/db/__init__.py` and `backend/models/database.py` so the new models are available through the project's normal import paths.

- [ ] **Step 5: Add a one-shot migration/bootstrap script**

Create `scripts/migrate_cloud_sync_tables.py` that imports `Base` and creates the new local state tables if they do not already exist.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cloud_b_class_sync_schema.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_cloud_b_class_sync_schema.py modules/core/db/schema.py modules/core/db/__init__.py backend/models/database.py scripts/migrate_cloud_sync_tables.py
git commit -m "feat(sync): add cloud b-class sync state tables"
```

### Task 2: Build Canonical Mirror Table Manager

**Files:**
- Create: `tests/test_cloud_b_class_mirror_manager.py`
- Create: `backend/services/cloud_b_class_mirror_manager.py`

- [ ] **Step 1: Write the failing table-manager test**

```python
from backend.services.cloud_b_class_mirror_manager import build_canonical_columns


def test_build_canonical_columns_excludes_dynamic_fields():
    columns = build_canonical_columns()
    assert "raw_data" in columns
    assert "header_columns" in columns
    assert "dynamic_text_field" not in columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cloud_b_class_mirror_manager.py -v`
Expected: FAIL because the module does not exist yet.

- [ ] **Step 3: Implement the mirror manager**

Create `backend/services/cloud_b_class_mirror_manager.py` with responsibilities:
- define the canonical column contract
- ensure cloud schema exists
- ensure one cloud canonical mirror table exists for a given local B-class table
- apply the correct unique index for `services` vs non-`services`

Keep this file focused on remote DDL only. Do not mix in checkpoint or batch-reading logic.

- [ ] **Step 4: Verify the canonical contract in tests**

Expand the test to assert:
- canonical fields include all fixed sync fields
- no dynamic business columns are part of the contract
- the conflict-key helper returns different keys for `services` and non-`services`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cloud_b_class_mirror_manager.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_cloud_b_class_mirror_manager.py backend/services/cloud_b_class_mirror_manager.py
git commit -m "feat(sync): add cloud b-class canonical mirror manager"
```

### Task 3: Build Checkpointed Cloud Sync Service

**Files:**
- Create: `tests/test_cloud_b_class_sync_service.py`
- Create: `backend/services/cloud_b_class_sync_service.py`
- Create: `backend/services/cloud_b_class_sync_checkpoint_service.py`

- [ ] **Step 1: Write the failing service test**

```python
def test_checkpoint_advances_only_after_successful_write():
    service = CloudBClassSyncService(...)
    result = service._should_advance_checkpoint(write_succeeded=False)
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cloud_b_class_sync_service.py -v`
Expected: FAIL because the service modules do not exist yet.

- [ ] **Step 3: Implement checkpoint read/write service**

Create `backend/services/cloud_b_class_sync_checkpoint_service.py` with methods for:
- `get_checkpoint(table_name)`
- `create_or_get_checkpoint(table_name)`
- `advance_checkpoint(table_name, ingest_timestamp, source_id, status)`
- `mark_failure(table_name, message)`

Reuse the current service style found in `backend/services/sync_point_service.py`, but design the key around B-class table identity instead of platform/account/domain.

- [ ] **Step 4: Implement the cloud sync service**

Create `backend/services/cloud_b_class_sync_service.py` with responsibilities:
- enumerate local `b_class` tables
- read batches ordered by `(ingest_timestamp, id)`
- select only canonical fields
- call the mirror manager to ensure the remote table exists
- perform remote upsert
- advance checkpoint only after successful commit
- continue on single-table failure and collect structured run stats

Suggested public interface:

```python
class CloudBClassSyncService:
    async def sync_all_tables(self, batch_size: int = 1000) -> dict: ...
    async def sync_table(self, table_name: str, batch_size: int = 1000) -> dict: ...
```

- [ ] **Step 5: Add focused tests**

Cover at least:
- table enumeration filtering to `b_class`
- checkpoint WHERE clause generation
- conflict-key routing for `services`
- checkpoint advancement only after success
- single-table failure isolation

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cloud_b_class_sync_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_cloud_b_class_sync_service.py backend/services/cloud_b_class_sync_service.py backend/services/cloud_b_class_sync_checkpoint_service.py
git commit -m "feat(sync): add checkpointed cloud b-class sync service"
```

### Task 4: Add CLI Entry Point And Operational Logging

**Files:**
- Create: `tests/test_cloud_b_class_sync_cli.py`
- Create: `scripts/sync_b_class_to_cloud.py`
- Modify: `backend/services/cloud_b_class_sync_service.py`

- [ ] **Step 1: Write the failing CLI test**

```python
def test_cli_returns_non_zero_when_any_table_fails():
    code = main(["--batch-size", "100"])
    assert code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cloud_b_class_sync_cli.py -v`
Expected: FAIL because the CLI entry point does not exist yet.

- [ ] **Step 3: Implement the script**

Create `scripts/sync_b_class_to_cloud.py` to:
- read `DATABASE_URL` and `CLOUD_DATABASE_URL`
- support `--batch-size`
- support `--table`
- support `--dry-run`
- print ASCII-safe logs only
- return `0` on full success, non-zero on partial or total failure

Suggested skeleton:

```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    service = build_service_from_env(args)
    result = asyncio.run(service.sync_all_tables(batch_size=args.batch_size))
    return 0 if result["failed_tables"] == 0 else 2
```

- [ ] **Step 4: Persist run summaries**

Update `backend/services/cloud_b_class_sync_service.py` so each run writes one `CloudBClassSyncRun` row with:
- start time
- end time
- table counts
- status
- error summary

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cloud_b_class_sync_cli.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_cloud_b_class_sync_cli.py scripts/sync_b_class_to_cloud.py backend/services/cloud_b_class_sync_service.py
git commit -m "feat(sync): add cloud b-class sync cli and run logging"
```

### Task 5: Documentation And End-to-End Verification

**Files:**
- Modify: `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`
- Modify: `docs/guides/DATA_MIGRATION_GUIDE.md`
- Create: `tests/test_cloud_b_class_sync_e2e_contract.py`

- [ ] **Step 1: Write the failing end-to-end contract test**

```python
def test_sync_contract_uses_raw_data_and_header_columns():
    result = build_sync_payload(sample_row)
    assert "raw_data" in result
    assert "header_columns" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cloud_b_class_sync_e2e_contract.py -v`
Expected: FAIL until the payload builder is importable and stable.

- [ ] **Step 3: Document deployment and operations**

Update deployment docs to include:
- required env vars
- cron example
- dry-run usage
- failure modes
- checkpoint reset procedure
- statement that dynamic columns are not part of the cloud sync contract

- [ ] **Step 4: Add a smoke verification path**

Document and verify:

Run:
`python scripts/migrate_cloud_sync_tables.py`

Then:
`python scripts/sync_b_class_to_cloud.py --dry-run --batch-size 100`

Expected:
- local checkpoint tables exist
- local B-class tables are enumerated
- payloads are prepared from canonical fields only
- no cloud dynamic-column DDL is attempted

- [ ] **Step 5: Run all targeted tests**

Run: `pytest tests/test_cloud_b_class_sync_schema.py tests/test_cloud_b_class_mirror_manager.py tests/test_cloud_b_class_sync_service.py tests/test_cloud_b_class_sync_cli.py tests/test_cloud_b_class_sync_e2e_contract.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md docs/guides/DATA_MIGRATION_GUIDE.md tests/test_cloud_b_class_sync_e2e_contract.py
git commit -m "docs(sync): document canonical cloud b-class sync"
```

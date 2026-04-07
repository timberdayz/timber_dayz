# Catalog File Delete Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single-file delete support to the data sync file list, including impact analysis for ingested files and precise cleanup of catalog, quarantine, staging, and B-class records.

**Architecture:** Keep the existing file list page and field-mapping router as the UI/API entry points, but move deletion logic into a dedicated backend service centered on `catalog_files.id`. The UI will call an impact-analysis endpoint first for ingested files, then confirm deletion through a dedicated delete endpoint.

**Tech Stack:** FastAPI, SQLAlchemy async, Vue 3, Element Plus, pytest

---

### Task 1: Add Backend Service Tests First

**Files:**
- Create: `backend/tests/test_catalog_file_delete_service.py`
- Create: `backend/tests/test_field_mapping_file_delete_api.py`
- Reference: `backend/tests/conftest.py`

- [ ] **Step 1: Write a failing service test for pending files**

```python
async def test_analyze_pending_file_delete_returns_local_and_catalog_impact():
    impact = await service.analyze_delete_impact(file_id)
    assert impact.can_delete is True
    assert impact.fact_rows == 0
```

- [ ] **Step 2: Write a failing service test for ingested files**

```python
async def test_delete_ingested_file_removes_fact_and_catalog_rows():
    result = await service.delete_catalog_file(file_id, force=True)
    assert result.deleted_fact_rows == 3
    assert result.deleted_catalog is True
```

- [ ] **Step 3: Write a failing API test for impact analysis**

```python
async def test_get_delete_impact_returns_platform_and_fact_counts(pg_async_client):
    response = await pg_async_client.get(f"/api/field-mapping/files/{file_id}/delete-impact")
    assert response.status_code == 200
    assert response.json()["data"]["file_id"] == file_id
```

- [ ] **Step 4: Write a failing API test for delete execution**

```python
async def test_delete_file_endpoint_removes_file_record(pg_async_client):
    response = await pg_async_client.delete(f"/api/field-mapping/files/{file_id}")
    assert response.status_code == 200
```

- [ ] **Step 5: Run the tests to verify RED**

Run: `pytest backend/tests/test_catalog_file_delete_service.py backend/tests/test_field_mapping_file_delete_api.py -q`

Expected: FAIL because the delete service and endpoints do not exist yet.

### Task 2: Implement Catalog File Delete Service

**Files:**
- Create: `backend/services/catalog_file_delete_service.py`
- Modify: `backend/services/platform_table_manager.py` (only if a shared table-name helper is needed and no suitable public helper exists)
- Reference: `modules/core/db/schema.py`

- [ ] **Step 1: Create service dataclasses or plain result payload builders for impact analysis and delete execution**

- [ ] **Step 2: Implement `analyze_delete_impact(file_id)`**

```python
async def analyze_delete_impact(self, file_id: int) -> DeleteImpact:
    catalog = await self._get_catalog_file(file_id)
    fact_table = self._resolve_fact_table_name(catalog)
    return DeleteImpact(...)
```

- [ ] **Step 3: Implement `delete_catalog_file(file_id, force=True)` with transaction-first ordering**

```python
async def delete_catalog_file(self, file_id: int, force: bool = True) -> DeleteResult:
    # fact -> staging -> quarantine -> catalog -> commit -> local files
```

- [ ] **Step 4: Handle missing local files and missing meta files as warnings, not hard failures**

- [ ] **Step 5: Run the service tests**

Run: `pytest backend/tests/test_catalog_file_delete_service.py -q`

Expected: PASS

### Task 3: Expose Delete APIs

**Files:**
- Modify: `backend/routers/field_mapping_files.py`
- Create: `backend/schemas/catalog_file_delete.py`

- [ ] **Step 1: Add Pydantic response models for delete impact and delete result**

```python
class CatalogFileDeleteImpactResponse(BaseModel):
    file_id: int
    platform_code: str | None
    fact_rows: int
```

- [ ] **Step 2: Add `GET /api/field-mapping/files/{file_id}/delete-impact`**

- [ ] **Step 3: Add `DELETE /api/field-mapping/files/{file_id}`**

- [ ] **Step 4: Return 404 for unknown file IDs and propagate safe validation errors**

- [ ] **Step 5: Run the API tests**

Run: `pytest backend/tests/test_field_mapping_file_delete_api.py -q`

Expected: PASS

### Task 4: Add Frontend Delete Flow

**Files:**
- Modify: `frontend/src/views/DataSyncFiles.vue`
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add API wrappers for delete impact and delete execution**

```javascript
async getFileDeleteImpact(fileId) {
  return await this._get(`/field-mapping/files/${fileId}/delete-impact`)
}

async deleteFile(fileId) {
  return await this._delete(`/field-mapping/files/${fileId}`)
}
```

- [ ] **Step 2: Add a `删除` action button beside existing file actions**

- [ ] **Step 3: For pending files, show a simple confirmation dialog**

- [ ] **Step 4: For ingested files, load delete impact and show a second confirmation dialog with counts**

- [ ] **Step 5: Refresh the file list and governance stats after successful deletion**

- [ ] **Step 6: Run an adjacent UI-related backend regression to make sure file list flows still work**

Run: `pytest backend/tests/test_field_mapping_scan_pure_registration.py -q`

Expected: PASS

### Task 5: Final Verification

**Files:**
- Test: `backend/tests/test_catalog_file_delete_service.py`
- Test: `backend/tests/test_field_mapping_file_delete_api.py`
- Test: `backend/tests/test_field_mapping_scan_pure_registration.py`
- Test: `backend/tests/test_miaoshou_orders_file_platform_semantics.py`

- [ ] **Step 1: Run the focused backend verification suite**

Run: `pytest backend/tests/test_catalog_file_delete_service.py backend/tests/test_field_mapping_file_delete_api.py backend/tests/test_field_mapping_scan_pure_registration.py backend/tests/test_miaoshou_orders_file_platform_semantics.py -q`

Expected: PASS

- [ ] **Step 2: Manually verify the UI flow in the browser**

Manual checks:
- Pending file shows direct delete confirmation
- Ingested file shows delete impact before final confirmation
- Delete success refreshes the file list
- Deleted file no longer appears in the list

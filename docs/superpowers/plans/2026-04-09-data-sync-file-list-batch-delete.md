# Data Sync File List Batch Delete Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为文件列表页面增加多选删除能力，并补强删除/清理相关接口的认证与页面治理按钮的语义一致性。

**Architecture:** 后端新增批量删除 contract 与路由，内部复用现有 `CatalogFileDeleteService` 做逐文件删除和 impact 汇总；前端在现有批量操作卡片中新增“删除选中”，调用新的批量 impact / delete API，并在完成后刷新列表与统计。顺带修复删除影响查询、单文件删除、清理数据库的认证缺口，并调整页面文案使治理按钮与实际行为一致。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, Vite, pytest

---

### Task 1: Add Backend Batch Delete Contracts

**Files:**
- Modify: `backend/schemas/catalog_file_delete.py`
- Test: `backend/tests/test_data_sync_batch_delete_api.py`

- [ ] **Step 1: Write the failing schema / API tests**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Add Pydantic request and response models**
- [ ] **Step 4: Run test to verify partial progress**
- [ ] **Step 5: Commit**

### Task 2: Implement Backend Batch Delete Service Flow

**Files:**
- Modify: `backend/services/catalog_file_delete_service.py`
- Test: `backend/tests/test_catalog_file_delete_service.py`

- [ ] **Step 1: Write the failing service tests**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Add minimal batch helpers to the delete service**
- [ ] **Step 4: Keep deletion behavior source-of-truth in the existing single delete path**
- [ ] **Step 5: Run service tests**
- [ ] **Step 6: Commit**

### Task 3: Add Backend Routes And Authentication Guards

**Files:**
- Modify: `backend/routers/data_sync.py`
- Test: `backend/tests/test_data_sync_batch_delete_api.py`
- Test: `backend/tests/test_data_sync_file_delete_api.py`

- [ ] **Step 1: Extend tests for route behavior and authentication**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Add route handlers and explicit `get_current_user` dependencies**
- [ ] **Step 4: Add explicit auth dependencies to existing sensitive routes**
- [ ] **Step 5: Run backend delete tests**
- [ ] **Step 6: Commit**

### Task 4: Add Frontend Batch Delete API Calls

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add API helpers**
- [ ] **Step 2: Run frontend build**
- [ ] **Step 3: Commit**

### Task 5: Add Frontend Batch Delete Interaction

**Files:**
- Modify: `frontend/src/views/DataSyncFiles.vue`

- [ ] **Step 1: Add the new batch delete button and handler**
- [ ] **Step 2: Refresh list and stats, then clear selection**
- [ ] **Step 3: Adjust governance button copy for semantic accuracy**
- [ ] **Step 4: Run frontend verification**
- [ ] **Step 5: Commit**

### Task 6: Final Verification

**Files:**
- Modify: `progress.md` (if needed for verification notes)

- [ ] **Step 1: Run backend verification**
- [ ] **Step 2: Run frontend verification**
- [ ] **Step 3: Re-read the spec and check all requirements**
- [ ] **Step 4: Summarize any residual risks**
- [ ] **Step 5: Commit**

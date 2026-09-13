# Internal Product Category Taxonomy v1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the approved 13-level-1 / 65-level-2 internal product category contract into Product Center without changing platform mappings or silently reclassifying existing SPUs.

**Architecture:** Add one forward-only current-schema migration that declares and idempotently seeds the complete v1 category dictionary. Add an `is_selectable` distinction so the full v1 directory can be used for internal master data while legacy `PET_DAILY` stays readable but cannot be selected again. Keep Product Center's two-level cascade; make new SPU assignment mandatory and enforce parent/child lifecycle transitions transactionally in the category API.

**Tech Stack:** PostgreSQL, Alembic current-schema migrations, SQLAlchemy async, FastAPI, Pydantic, pytest, Vue 3 existing category cascade.

---

## File Structure

- Create: `current_migrations/versions/20260911_internal_product_category_taxonomy_v1.py` — self-contained, idempotent v1 dictionary seed and `is_selectable` migration.
- Modify: `modules/core/db/schema_parts/dimensions.py` — expose `is_selectable` in the ORM model.
- Modify: `backend/schemas/product_center.py` — expose the selection flag in category responses.
- Modify: `backend/domains/business/routers/product_center.py` — return only selectable categories by default; require a secondary category for new SPUs; preserve an unchanged legacy category during non-category edits; enforce parent/child lifecycle transitions.
- Modify: `frontend/src/domains/business/views/ProductCenter.vue` — render an existing non-selectable category as a disabled historical option, without making it selectable for new assignments.
- Modify: `frontend/tests/productCenterUi.test.mjs` — cover the disabled legacy category presentation.
- Modify: `backend/tests/test_product_category_contract.py` — execute contract-level assertions against an independent golden mapping and runtime API helpers.
- Modify: `docs/superpowers/specs/2026-09-11-product-category-taxonomy-v1-design.md` — record rollout semantics.

### Task 1: Define the migration contract with a failing test

**Files:**
- Modify: `backend/tests/test_product_category_contract.py`
- Create: `current_migrations/versions/20260911_internal_product_category_taxonomy_v1.py`

- [ ] **Step 1: Write the failing test**

Add an independent golden mapping in the test that loads `CATEGORY_ROWS` from the new migration and asserts exactly 78 unique codes, 13 roots, 65 children, every approved code/name/parent/path, `active` status, and `is_selectable=True`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_product_category_contract.py -q`

Expected: FAIL because the v1 migration module and `CATEGORY_ROWS` do not exist.

- [ ] **Step 3: Implement the minimal migration**

Create a forward-only migration with `down_revision = "current_schema_20260911_company_product_categories"`. Add `is_selectable` as `nullable=False` with a server default of true, and mirror that non-null default in the ORM; define the 78 approved rows as immutable module data; then insert or update those rows idempotently with v1 metadata. Never rewrite an SPU category. Set legacy `PET_DAILY.is_selectable = false`; retain its status so existing SPU history remains readable.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_product_category_contract.py -q`

Expected: PASS.

### Task 2: Enforce category selection and lifecycle invariants with failing tests

**Files:**
- Modify: `backend/tests/test_product_category_contract.py`
- Modify: `backend/domains/business/routers/product_center.py`

- [ ] **Step 1: Write the failing test**

Add focused behavior tests requiring: default category reads exclude non-selectable `PET_DAILY`; a new SPU without a secondary category is rejected; an existing SPU can retain unchanged `PET_DAILY` through a non-category edit but cannot assign it during a category change; a level-1 parent cannot be deactivated while active children remain; and a level-2 category cannot be activated when its parent is inactive. Add a frontend test requiring the legacy option to be disabled rather than omitted from an existing row.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_product_category_contract.py -q`

Expected: FAIL because the current API has no selection flag, permits new SPUs without a secondary category, and writes category status without complete parent/child checks.

- [ ] **Step 3: Implement the minimal router check**

Add `is_selectable` to category response data and make list reads filter `status == active` and `is_selectable == true` unless an administrative flag opts in. Require a selected active/selectable secondary category for create and bulk-create paths. For an existing SPU, permit a non-selectable secondary category only when the submitted code equals the persisted code; reject every attempted reassignment to that code. Add a disabled legacy option to the row's category selector so the current label remains readable but cannot be newly selected. In category create/update transitions, lock the relevant parent row and reject parent deactivation with active children or child activation with an inactive parent. Do not add platform behavior or alter legacy SPU categories.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_product_category_contract.py -q`

Expected: PASS.

### Task 3: Verify migration safety and Product Center availability

**Files:**
- Modify: `docs/superpowers/specs/2026-09-11-product-category-taxonomy-v1-design.md`

- [ ] **Step 1: Update the approved design record**

Record that all approved v1 categories are selectable for internal master-data classification, while `PET_DAILY` remains readable but is not selectable for new or reclassified SPUs.

- [ ] **Step 2: Run targeted regression tests**

Run: `pytest backend/tests/test_product_category_contract.py -q`

Expected: PASS with no failures.

- [ ] **Step 3: Run the migration against a temporary PostgreSQL database**

Create an isolated test database at the prior migration head, seed referenced and unreferenced legacy category fixtures, run `python scripts/run_current_schema_migrations.py --database-url <temporary-url>`, and assert the revision graph, `is_selectable` is `NOT NULL` with default true, all 78 rows, legacy `PET_DAILY.is_selectable = false`, preserved SPU category values, and a safe repeated run. Tear down only the named temporary database.

- [ ] **Step 4: Run repository checks for touched surfaces**

Run: `python scripts/verify_architecture_ssot.py`

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Run: `python scripts/verify_utf8_source_hygiene.py`

Expected: both commands exit 0.

- [ ] **Step 5: Inspect the final diff**

Run: `git diff --check` and `git diff -- current_migrations/versions/20260911_internal_product_category_taxonomy_v1.py modules/core/db/schema_parts/dimensions.py backend/schemas/product_center.py backend/domains/business/routers/product_center.py backend/tests/test_product_category_contract.py frontend/src/domains/business/views/ProductCenter.vue frontend/tests/productCenterUi.test.mjs docs/superpowers/specs/2026-09-11-product-category-taxonomy-v1-design.md`

Expected: no whitespace errors; changes limited to the category taxonomy contract.

# Canonical Collection Components Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将三平台的成熟采集组件收敛为唯一 canonical 逻辑槽位，并让后续用户只围绕这些 canonical 组件进行测试和优化。

**Architecture:** 先做“组件清单治理”，再做“注册/页面展示治理”，最后再进入脚本内容优化。正式组件统一保留在 `modules/platforms/<platform>/components/`，旧重复组件、测试件和非业务入口组件不再作为默认维护对象暴露。版本管理页继续使用 `ComponentVersion`，但注册和展示逻辑应围绕 canonical 组件槽位收口。

**Tech Stack:** FastAPI, SQLAlchemy Async, Vue 3, Python ComponentVersion registry, Playwright-based collection components

---

## File Structure

- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
  - 三平台 canonical 槽位清单与成熟度评估
- `docs/guides/COMPONENT_REUSE_WORKFLOW.md`
  - 复用成熟 export 的操作说明
- `backend/routers/component_versions.py`
  - 后续应收口 batch register 逻辑，只注册/展示 canonical 组件
- `frontend/src/views/ComponentVersions.vue`
  - 后续应按 canonical 槽位展示组件，而不是把测试件/别名平铺给用户
- `modules/platforms/*/components/*.py`
  - canonical 组件基础实现

## Task 1: Lock The Canonical Inventory

**Files:**
- Create: `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
- Modify: `docs/guides/COLLECTION_SCRIPT_REFERENCE.md`
- Modify: `docs/guides/COMPONENT_REUSE_WORKFLOW.md`

- [ ] **Step 1: Review current platform component files**

Run:
```powershell
Get-ChildItem modules\platforms\shopee\components,modules\platforms\tiktok\components,modules\platforms\miaoshou\components -File -Filter *.py
```

Expected: 仅列出当前现役组件文件。

- [ ] **Step 2: Mark canonical vs excluded files**

Write down for each platform:
- canonical slots
- current basis file
- maturity (`成熟` / `可用` / `排除`)

- [ ] **Step 3: Save the inventory doc**

Expected:
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md` exists
- excludes test/generated aliases like `recorder_test_login.py`

- [ ] **Step 4: Update reference docs to point to the canonical inventory**

Expected:
- `COLLECTION_SCRIPT_REFERENCE.md` links to the new canonical inventory
- `COMPONENT_REUSE_WORKFLOW.md` remains the operational guide

## Task 2: Define Registration Rules

**Files:**
- Modify: `backend/routers/component_versions.py`
- Test: `backend/tests/test_component_versions_canonical_registration.py`

- [ ] **Step 1: Write the failing test for batch register filtering**

Test should assert:
- canonical components are registered
- excluded files are skipped

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest backend/tests/test_component_versions_canonical_registration.py -q
```

Expected: FAIL because canonical filtering is not implemented yet.

- [ ] **Step 3: Implement canonical registration filtering**

Implement in `backend/routers/component_versions.py`:
- define allowlist/skiplist based on canonical inventory
- skip test files, aliases, generic wrappers, config files, tool files

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest backend/tests/test_component_versions_canonical_registration.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/routers/component_versions.py backend/tests/test_component_versions_canonical_registration.py docs/guides/CANONICAL_COLLECTION_COMPONENTS.md docs/guides/COLLECTION_SCRIPT_REFERENCE.md docs/guides/COMPONENT_REUSE_WORKFLOW.md
git commit -m "feat: enforce canonical collection component registration"
```

## Task 3: Make Component Management UI Canonical-First

**Files:**
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `frontend` manual verification

- [ ] **Step 1: Decide canonical-first grouping rule**

Expected behavior:
- only canonical logical slots shown by default
- versions remain secondary detail under the slot, not first-class duplicates

- [ ] **Step 2: Implement UI filtering/grouping**

Update `ComponentVersions.vue` to:
- hide excluded components by default
- group rows by canonical `component_name`
- keep testing/promote actions on the canonical row

- [ ] **Step 3: Run manual verification**

Manual checks:
- open `/component-versions`
- confirm users no longer see duplicate aliases/test components
- confirm canonical slots remain testable/promotable

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/views/ComponentVersions.vue
git commit -m "feat: make component version manager canonical-first"
```

## Task 4: Canonicalize Platform Entry Components

**Files:**
- Modify: `modules/platforms/miaoshou/components/login.py`
- Modify: `modules/platforms/miaoshou/components/miaoshou_login.py`
- Modify: `modules/platforms/shopee/components/export.py`
- Modify: `modules/platforms/shopee/components/recorder_test_login.py`
- Modify: `modules/platforms/shopee/components/metrics_selector.py`

- [ ] **Step 1: Write failing tests or assertions for excluded/non-canonical files**

Goals:
- canonical entry files remain usable
- excluded files are not chosen as default maintenance targets

- [ ] **Step 2: Normalize entry semantics**

Implement minimal cleanup:
- `miaoshou/login.py` remains canonical entry
- `miaoshou_login.py` becomes internal implementation detail only
- `shopee/export.py` stays helper, not canonical domain export
- `recorder_test_login.py` clearly marked test-only or removed from registration
- `metrics_selector.py` clearly marked non-canonical until implemented

- [ ] **Step 3: Re-run component registration and verify UI**

Run:
```powershell
python -m pytest backend/tests/test_component_versions_canonical_registration.py -q
```

Then verify UI manually.

- [ ] **Step 4: Commit**

```powershell
git add modules/platforms/miaoshou/components/login.py modules/platforms/miaoshou/components/miaoshou_login.py modules/platforms/shopee/components/export.py modules/platforms/shopee/components/recorder_test_login.py modules/platforms/shopee/components/metrics_selector.py
git commit -m "refactor: align canonical collection component entry files"
```

## Task 5: Start Content Optimization On Canonical Components

**Files:**
- Modify only canonical files listed in `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
- Test via `ComponentVersions` page and `tools/test_component.py`

- [ ] **Step 1: Pick one canonical component**

Suggested first targets:
- `modules/platforms/miaoshou/components/login.py`
- `modules/platforms/shopee/components/products_export.py`
- `modules/platforms/tiktok/components/export.py`

- [ ] **Step 2: Test the component from version manager**

Expected:
- failures now map to a single canonical component
- user no longer guesses between duplicate files

- [ ] **Step 3: Apply minimal fix**

Fix only:
- login
- navigation/date picker/shop selector prerequisite
- export-specific blocker

- [ ] **Step 4: Re-test and verify**

Run:
```powershell
python tools/test_component.py --platform <platform> --component <component_name>
```

Expected: PASS or one clear actionable failure.

- [ ] **Step 5: Commit**

```powershell
git add <canonical files>
git commit -m "fix: improve canonical collection component"
```

# Products Semantic Template Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Shopee `products` files with `已确认订单 / 已确定订单` variants to reuse the current semantic template without blocking sync.

**Architecture:** Add alias rules in the template alias registry, then rely on the existing `TemplateMatcher` semantic comparison path to classify these files as `alias_only` instead of `update_required`. Cover the behavior with focused template status tests.

**Tech Stack:** Python, FastAPI backend services, SQLAlchemy async tests, pytest

---

### Task 1: Add failing tests for Shopee products semantic aliases

**Files:**
- Modify: `backend/tests/test_data_sync_template_status_service.py`

- [ ] Add a failing test where a Shopee products monthly template uses `已付款订单` fields and the incoming file uses `已确认订单 / 已确定订单`.
- [ ] Assert `template_status == "ready"` or semantic pass behavior is wrong before the alias rules exist.
- [ ] Run the focused pytest target and confirm the new test fails for the expected reason.

### Task 2: Implement products semantic aliases

**Files:**
- Modify: `backend/services/template_alias_registry.py`

- [ ] Add alias mappings for Shopee `products` across the relevant business status fields.
- [ ] Keep scope limited to the confirmed fields from the current drift sample.
- [ ] Re-run the focused pytest target and confirm it passes.

### Task 3: Verify no regression in existing template status behavior

**Files:**
- Modify: `backend/tests/test_data_sync_template_status_service.py`

- [ ] Run the existing template status test file.
- [ ] Confirm currency-suffix-only matching still passes and true structural drift still returns `update_required`.

### Task 4: Record findings

**Files:**
- Modify: `findings.md`
- Modify: `progress.md`

- [ ] Summarize the new semantic alias behavior and the scope boundary.
- [ ] Note that field whitelist/hash configuration is deferred to a later phase.

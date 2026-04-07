# Shopee Login V2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a canonical Shopee China login component that supports credential entry, phone-OTP-only verification, email-to-phone OTP switching, and homepage-based success detection.

**Architecture:** Keep the component self-contained in `modules/platforms/shopee/components/login.py` and mirror the existing canonical login style used by Miaoshou: helper-driven detection, explicit failure messages, and verification pause-resume through `VerificationRequiredError`. Add focused unit tests that lock down runtime behavior before implementation.

**Tech Stack:** Python, Playwright async API, pytest, existing collection executor verification flow

---

### Task 1: Add Shopee Login Tests

**Files:**
- Create: `backend/tests/test_shopee_login_component.py`
- Test: `backend/tests/test_shopee_login_component.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- homepage success URL detection
- sign-in URL rejection
- OTP mode helper detection for phone vs email
- missing `login_url`
- already-logged-in short-circuit
- OTP-required raises `VerificationRequiredError("otp", screenshot_path)`

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_shopee_login_component.py -q`

- [ ] **Step 3: Implement the minimal production code**

Create the canonical login component with only the helpers and runtime paths needed to satisfy the tests.

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `pytest backend/tests/test_shopee_login_component.py -q`

### Task 2: Implement Canonical Shopee Login

**Files:**
- Create: `modules/platforms/shopee/components/login.py`
- Modify: `modules/platforms/shopee/components/__init__.py`

- [ ] **Step 1: Add component metadata and URL detection helpers**

Implement:
- `platform = "shopee"`
- `component_type = "login"`
- `_login_looks_successful(...)`
- `_otp_mode(...)`

- [ ] **Step 2: Add login form helpers**

Implement focused locators for:
- username
- password
- login button
- OTP input
- OTP confirm
- email-to-phone switch

- [ ] **Step 3: Add OTP verification helpers**

Implement:
- phone-mode enforcement
- OTP error detection
- screenshot capture for verification-required

- [ ] **Step 4: Implement `run(...)`**

Implement:
- already-logged-in short-circuit
- login page navigation
- credential submission
- OTP pause-resume
- homepage success detection

### Task 3: Verify Integration

**Files:**
- Test: `backend/tests/test_shopee_login_component.py`
- Test: `backend/tests/test_component_versions_canonical_registration.py`

- [ ] **Step 1: Run the new Shopee login tests**

Run: `pytest backend/tests/test_shopee_login_component.py -q`

- [ ] **Step 2: Run canonical registration coverage**

Run: `pytest backend/tests/test_component_versions_canonical_registration.py -q`

- [ ] **Step 3: Review file diff for canonical-only surface**

Confirm only canonical Shopee login files and test coverage were changed for this task.

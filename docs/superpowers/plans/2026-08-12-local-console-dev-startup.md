# Local Console Development Startup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Local Console as a one-click local development startup that does not run formal migration or cloud-takeover workflows, while allowing a rebuilt local database to receive an explicitly configured development administrator.

**Architecture:** The Console service specification will point to the existing local collection wrapper, which starts local backend and frontend processes on top of Docker infrastructure. The wrapper will invoke a small idempotent local-admin initializer before `run.py --local`; it accepts only an explicit local development password environment variable and performs no work when an account already exists.

**Tech Stack:** Python 3.13, PowerShell, SQLAlchemy async, PostgreSQL Docker, pytest.

---

### Task 1: Route Console to the development startup wrapper

**Files:**
- Modify: `scripts/local_console_processes.py`
- Modify: `tests/test_local_console_processes.py`

- [ ] **Step 1: Write the failing regression test**
  Assert the local collection service command contains `start_local_collection_mode.ps1`, uses the matching command marker, and does not contain `start_collection_formal.ps1`.
- [ ] **Step 2: Run the focused test and verify it fails on the current formal-wrapper command.**
- [ ] **Step 3: Change only the Console service specification and marker to the existing development wrapper.**
- [ ] **Step 4: Run the focused Console tests and verify they pass.**

### Task 2: Add opt-in, idempotent local development admin initialization

**Files:**
- Create: `scripts/ensure_local_dev_admin.py`
- Modify: `scripts/start_local_collection_mode.ps1`
- Modify: `env.development.example`
- Create: `tests/test_ensure_local_dev_admin.py`
- Modify: `backend/tests/test_collection_startup_scripts.py`

- [ ] **Step 1: Write failing unit tests for the initializer policy:** it rejects an absent password when initialization is requested, creates only a missing named user, does not reset an existing account, and never exposes the password in its returned or logged messages.
- [ ] **Step 2: Run the new tests and verify they fail because the initializer does not exist.**
- [ ] **Step 3: Implement the smallest async initializer:** load only `LOCAL_DEV_ADMIN_USERNAME`, `LOCAL_DEV_ADMIN_PASSWORD`, and optional email; use parameterized SQLAlchemy operations; hash the supplied password; create/assign the existing admin role only for a missing account; make the wrapper invoke it only with `LOCAL_DEV_BOOTSTRAP_ADMIN=true`.
- [ ] **Step 4: Document the opt-in local-only variables in `env.development.example`, with placeholder values only.**
- [ ] **Step 5: Run focused unit and PowerShell-contract tests and verify they pass.**

### Task 3: Verify development startup behavior and security boundaries

**Files:**
- Verify only

- [ ] **Step 1: Run Python compilation and Ruff for modified Python files.**
- [ ] **Step 2: Run the targeted Local Console, startup-wrapper, and initializer test suites.**
- [ ] **Step 3: Parse the changed PowerShell script and run UTF-8 source hygiene.**
- [ ] **Step 4: Perform the required OWASP-focused review of the credential initializer and environment example; confirm no password literal or database URL is logged.**
- [ ] **Step 5: Start Local Console through its token-protected API, then verify managed status is `running`, `/healthz/ready` is HTTP 200, and no backup/migration stage is reported.**
- [ ] **Step 6: Commit the scoped fix and merge it to `main` after verification.**

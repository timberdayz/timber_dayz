# Local Collection Migration Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Make the local collection startup path automatically diagnose and safely recover approved migration states while failing closed for schema drift and presenting actionable, redacted evidence in Local Console.

**Architecture:** The current migration wrapper remains the sole DDL entrypoint. It produces a stable JSON diagnosis, verifies a Docker PostgreSQL custom-format backup before non-empty-database writes, and serializes writes with an advisory lock. The PowerShell launcher emits a fixed status protocol that Local Console parses into token-protected status and bounded redacted logs.

**Tech Stack:** Python 3.13, Alembic, SQLAlchemy async, Docker PostgreSQL tools, PowerShell, FastAPI, psutil, static HTML/CSS/JavaScript, pytest.

---

## Scope Contract

- Environment: Windows local development, local Docker PostgreSQL, local loopback Local Console.
- In scope: migration diagnosis, backup validation guard, advisory lock, approved-source manifest metadata, formal launcher result protocol, Local Console observability, tests, and local runbook.
- Out of scope: cloud database, cloud synchronization, browser profiles and session files, automatic recovery/rebuild/deletion, approval-policy changes, and new business schema migrations.
- Safety invariant: a non-empty database is never stamped or upgraded until a matching, readable local backup succeeds; drift and unapproved sources perform no DDL/DML.

## Tasks

- [x] Add red tests for stable migration diagnoses, exact protected historical artifacts, and no-write rejection behavior.
- [x] Implement migration failure contracts, JSON diagnostics, schema object summaries, versioned manifest validation, and advisory-lock recheck.
- [x] Add red tests for Docker backup metadata/readability validation and non-empty migration backup guard.
- [x] Implement the local custom-format backup utility and connect it only to the migration write path.
- [x] Add red tests for PowerShell result markers and original exit-code preservation; update the formal launcher.
- [x] Add red tests for Local Console failure propagation, bounded token-protected logs, redaction, and launch-stage state.
- [x] Implement Local Console protocol parsing, status fields, fixed logs endpoint, and UI status rendering.
- [x] Add PostgreSQL integration coverage for empty, approved, drift, archived metadata, and lock contention behavior where the local test environment supports it.
- [x] Update the local collection runbook and structured audit logging guidance; complete the required security review and verification matrix.

## Verification

- Targeted migration, backup, launcher, and Local Console pytest suites.
- PostgreSQL integration contract suite when Docker services are available.
- `python -m py_compile` for edited Python modules.
- PowerShell parser/syntax validation for the launcher.
- `python scripts/verify_utf8_source_hygiene.py` after static UI edits.
- Security review of every changed token/API/log path and dependency audit where available.

## Verification Results

- `pytest -q tests/test_current_schema_migration_contract.py tests/test_local_migration_backup.py tests/test_local_console_processes.py tests/test_local_console.py backend/tests/test_collection_startup_scripts.py backend/tests/test_remote_deploy_migration_contract.py`: 84 passed.
- `pytest -q tests/test_current_schema_migration_postgres_contract.py -k advisory_lock_rejects`: 1 passed. The full PostgreSQL suite was also exercised during implementation; temporary containers are stopped after each case.
- `python -m py_compile scripts/run_current_schema_migrations.py scripts/local_migration_backup.py scripts/local_console_processes.py scripts/local_console.py`: passed.
- `python scripts/verify_utf8_source_hygiene.py`: passed for 13 files.
- PowerShell parser validation of `scripts/start_collection_formal.ps1`: passed.

## Security Review

**Security-Sensitive:** YES. Reviewed `scripts/local_console.py`, `scripts/local_console_processes.py`, `scripts/run_current_schema_migrations.py`, `scripts/local_migration_backup.py`, and `scripts/start_collection_formal.ps1`.

| OWASP area | Result | Notes |
| --- | --- | --- |
| A01 Access control | PASS | New log routes are fixed per service and require the existing loopback controller token. |
| A02 Data exposure | PASS | Logs are redacted on capture and response; diagnostics avoid connection strings and business rows. |
| A03 Injection | PASS | No user-selected command, service, file path, Docker container, or SQL fragment is accepted. |
| A04 Insecure design | PASS | Non-empty local writes require a verified custom-format backup; unknown sources and drift fail closed. |
| A05 Misconfiguration | PASS | Existing security headers, loopback binding, and no-store responses remain in place. |
| A06 Components | BLOCKED | `pip-audit -r requirements.txt` could not parse the pre-existing UTF-8 requirements file under the Windows GBK locale. No dependencies were changed. |
| A07 Authentication | PASS | Token check applies to status, actions, and both new log endpoints. |
| A08 Integrity | PASS | Manifest hash is checked before legacy adoption; backups include archive SHA-256 and `pg_restore --list` evidence. |
| A09 Logging | PASS | Failure audit is structured, bounded by fixed fields, and redacted. |
| A10 SSRF | N/A | New routes perform no user-directed network request. |

**Security Review Status:** PASS with dependency-audit environment limitation recorded above.

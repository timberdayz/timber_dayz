# Xihong ERP Local Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` to
> implement this plan task by task.

**Goal:** Provide a repository-root, double-click Windows launcher for safely
starting, opening, and stopping the existing formal collection system and PWCLI
inspection panel.

**Architecture:** `local_console.cmd` starts a singleton, loopback-only FastAPI
controller. A fixed-command process supervisor owns validated child PIDs and a
small static browser UI calls token-protected, service-specific routes. Existing
collection and PWCLI behavior remains unchanged.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, psutil, HTML, CSS, JavaScript,
PowerShell, Windows CMD.

---

## Tasks

- [x] Add failing tests for fixed service definitions, idempotent start, PID
  identity validation, persisted recovery, external-instance detection, startup
  timeout, and per-service stop boundaries.
- [x] Implement `scripts/local_console_processes.py` with immutable command
  tuples, atomic runtime state, output draining, readiness checks, redacted log
  access, and validated termination.
- [x] Add failing tests for token authentication, explicit routes, security
  headers, sanitized errors, log redaction, and existing-controller recovery.
- [x] Implement `scripts/local_console.py`, binding only `127.0.0.1`, with a
  singleton lock, URL token, strict CSP, fixed endpoints, and no arbitrary
  command input.
- [x] Add the root `local_console.cmd` launcher and separate static HTML/CSS/JS
  assets for the two-service status console.
- [x] Update active startup and PWCLI guides, then run targeted tests, security
  review, source hygiene checks, and desktop/mobile browser QA.

## Acceptance

- Repeated launcher or start actions do not create duplicate managed processes.
- Closing the browser tab leaves services running and re-running the launcher
  opens the existing controller.
- Collection stop leaves Docker infrastructure and the SSH tunnel running.
- Inspection-panel stop never closes PWCLI platform browsers or modifies saved
  session/profile data.
- External processes are visible but cannot be stopped through the console.
- No HTTP input can select an executable, path, command, service, or argument.

## Security Review

**Security-Sensitive:** YES
**Reviewed By:** Codex
**OWASP Categories Checked:** 10/10

| Category | Status | Notes |
| --- | --- | --- |
| A01 Broken Access Control | PASS | API binds to loopback and every API route requires the random request-header token. |
| A02 Cryptographic Failures | PASS | No secrets are returned by the API; token comparison uses `secrets.compare_digest`; visible logs are redacted. |
| A03 Injection | PASS | The browser selects only fixed service-specific routes; subprocess commands and working directory are immutable. |
| A04 Insecure Design | PASS | Managed PID identity includes creation time and command markers; external processes cannot be stopped. |
| A05 Security Misconfiguration | PASS | OpenAPI is disabled; CORS is absent; CSP, frame, content-type, referrer, and cache headers are set. |
| A06 Vulnerable Components | DEFERRED | `pip-audit -r requirements.txt` identified 9 advisories for the pre-existing `starlette 0.36.3` constraint. Updating FastAPI/Starlette is a shared backend dependency migration and is tracked as post-launch V2 dependency work, outside this isolated console change. |
| A07 Authentication Failures | PASS | Token is random per controller process, retained only in local state, and removed from the visible URL after the page loads. |
| A08 Software and Data Integrity Failures | PASS | State documents are JSON only and writes are replace-based; no untrusted deserialization or download path exists. |
| A09 Security Logging Failures | PASS | Local service logs are retained without returning environment values, and failed actions return generic errors. |
| A10 SSRF | N/A | The controller makes no user-directed outbound requests. |

**Dependency audit:** `pip-audit -r requirements.txt` completed its advisory scan after Windows UTF-8 mode was enabled. It reported 9 known vulnerabilities in the existing `starlette 0.36.3` requirement. The audit process did not exit before the external query timeout, but the returned findings were captured.

**Security Review Status:** ISSUES_DEFERRED

# Cloud Sync Admin Console Security Review

**Date:** 2026-03-26  
**Scope:** collection-to-cloud admin console implementation in `codex/cloud-sync-admin-console-implementation`

## Reviewed Areas

- admin router:
  - `backend/routers/cloud_sync.py`
- admin read-side services:
  - `backend/services/cloud_sync_admin_query_service.py`
  - `backend/schemas/cloud_sync_admin.py`
- admin command-side services:
  - `backend/services/cloud_sync_admin_command_service.py`
- worker/runtime:
  - `backend/services/cloud_b_class_auto_sync_runtime.py`
  - `backend/services/cloud_b_class_auto_sync_worker.py`
- frontend admin surface:
  - `frontend/src/api/cloudSync.js`
  - `frontend/src/stores/cloudSync.js`
  - `frontend/src/views/CloudSyncManagement.vue`

## Findings

### Fixed During Review

1. Sensitive error detail exposure
- Risk: `last_error` was being returned to the browser without sanitization.
- Impact: a failed cloud DB or tunnel error could leak credential-bearing DSN fragments or secret-like query parameters into the admin UI.
- Fix: added centralized sanitization in `cloud_sync_admin_query_service.py` for:
  - DSN credentials in `scheme://user:password@host`
  - `password=...`
  - `secret=...`
  - `token=...`

2. Missing admin action audit logs
- Risk: trigger/retry/cancel/repair/projection-refresh actions were not explicitly logged.
- Impact: weak operator accountability and poor post-incident traceability.
- Fix: added minimal admin action logging in `backend/routers/cloud_sync.py`.

## OWASP-Oriented Checks

- A01 Broken Access Control:
  - PASS
  - all cloud sync admin endpoints require `require_admin`
- A02 Sensitive Data Exposure:
  - PASS after fix
  - no raw credential-bearing error strings should reach the browser
- A03 Injection:
  - PASS for current scope
  - table names validated with strict `fact_[a-z0-9_]+`
- A05 Security Misconfiguration:
  - PASS for current scope
  - worker enablement is explicit and role-gated
- A09 Logging and Monitoring:
  - PASS with residual risk
  - sensitive admin actions now emit server-side logs

## Residual Risks

- `GET /api/cloud-sync/events` is currently derived from task state, not a dedicated audit/event store.
  - acceptable for V1
  - should be upgraded if operational volume grows
- `dry-run`, `repair-checkpoint`, and `refresh-projection` still return placeholder acceptance responses in the command service.
  - not a direct vulnerability
  - but they should be completed before production rollout to avoid misleading operators
- tunnel and cloud DB health are still placeholder `unknown` in the current query service.
  - once real SSH/tunnel integration is wired in, re-review secret handling and failure surfaces

## Recommendation

This implementation slice is acceptable for continued development.

Before merge or rollout, still complete:
1. real tunnel/cloud DB health implementation
2. soak / resilience validation
3. final deployment-role verification in production-like configuration

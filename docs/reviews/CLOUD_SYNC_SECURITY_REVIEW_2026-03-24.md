# Cloud Sync Security Review

**Date:** 2026-03-24
**Scope:** collection-to-cloud sync implementation in `codex/collection-to-cloud-auto-sync`

## Reviewed Areas

- manual sync CLI
- cloud sync task API
- task dispatch / worker / runtime
- source-table name validation
- environment-based database wiring
- dry-run behavior

## Findings

No critical or high-severity findings in the current implementation slice.

## Checks Performed

- verified cloud sync API endpoints require `require_admin`
- verified manual trigger request validates `source_table_name` with a strict `fact_[a-z0-9_]+` pattern
- verified table names are revalidated before SQL generation
- verified SQL identifier quoting is centralized instead of using raw string interpolation alone
- verified `--dry-run` does not write to cloud DB and does not advance checkpoints
- verified code does not log `CLOUD_DATABASE_URL` or credentials directly
- verified current cloud sync code does not introduce `StrictHostKeyChecking=no`

## Residual Risks

- runtime health currently reports tunnel state as `unknown`; when SSH tunnel integration lands, health and secret-handling paths should be re-reviewed
- cloud sync admin endpoints currently expose queue/task state but not full pagination or audit logging; if task volume grows, add paging and operator audit logs
- real cloud deployment still needs a final environment review for:
  - `CLOUD_DATABASE_URL`
  - SSH key path / known-host configuration
  - worker enable flags in production vs local roles

## Recommendation

Current implementation is acceptable for continued development and local verification.
Run one more security review before merge after:

1. real cloud tunnel integration lands
2. production worker enablement is configured
3. final deployment docs are updated

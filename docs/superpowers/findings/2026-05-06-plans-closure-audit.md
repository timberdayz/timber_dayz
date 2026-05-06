# Plans Closure Audit

- Date: 2026-05-06
- Scope: `docs/superpowers/plans/*.md` (excluding `STATUS.md`)

## Summary

- Total plan docs scanned: **110**
- Marked complete via explicit `Status:`: **8**
- Has `Status:` but not recognized as complete: **1**
- No `Status:` and has unchecked tasks (`- [ ]`): **97**
- No tasks (no checkbox and no `Status:`): **4**

## Interpretation

- This audit checks *documentation closure* only. It does NOT prove code/feature completion.
- `No Status + unchecked tasks` usually means the plan was not updated after execution, but it can also mean the work was never finished.

## Marked Complete (explicit Status)

- `2026-03-19-collection-canonical-runtime-cutover.md` - completed on 2026-03-20 and merged into `main`
- `2026-04-30-project-simplification-phase1-plan.md` - complete (merged to `main`)
- `2026-05-04-project-simplification-phase2-domain-registration-plan.md` - complete (merged to `main`)
- `2026-05-05-business-overview-read-model-unification.md` - Implemented and merged to `main` on 2026-05-05
- `2026-05-05-project-simplification-phase3-service-and-shared-boundaries.md` - complete (merged to `main`)
- `2026-05-05-project-simplification-phase4-frontend-domain-reorg.md` - complete (merged to `main`)
- `2026-05-05-project-simplification-phase5-schema-ssot-decomposition.md` - complete (merged to `main`)
- `2026-05-05-project-simplification-phase6-closure.md` - complete (merged to `main`)

## Status Other (needs review)

- `2026-03-24-recording-gates-and-export-container-alignment.md` - GateStatus

## No Tasks (no checkbox, no Status)

- `2026-03-22-metabase-postgresql-cleanup.md`
- `2026-03-23-canonical-collection-handoff.md`
- `2026-03-28-database-schema-cleanup-wave1.md`
- `2026-03-28-database-schema-cleanup-wave2.md`

## Candidates Missing Closure Update (no Status, has unchecked tasks)

Grouped by month. Recommendation: confirm each as `complete`, `archived`, or `superseded-by ...` (and then add an explicit `Status:` line).

### 2026-04 (65)

- `2026-04-02-main-account-shop-account-domain-chain-implementation.md`
- `2026-04-02-tiktok-products-export-boundaries.md`
- `2026-04-03-data-sync-schema-guardrails.md`
- `2026-04-03-hr-income-payroll-closure.md`
- `2026-04-03-inventory-ledger-first-refactor-implementation.md`
- `2026-04-03-postgresql-dashboard-granularity-alignment.md`
- `2026-04-03-shop-discovery-current-only-implementation.md`
- `2026-04-04-b-class-cost-analysis-implementation.md`
- `2026-04-04-miaoshou-inventory-snapshot-and-backlog-implementation.md`
- `2026-04-04-real-inventory-aging-implementation.md`
- `2026-04-05-collection-config-granularity-coverage.md`
- `2026-04-05-collection-coverage-audit-batch-remediation.md`
- `2026-04-05-frontend-page-permission-unification.md`
- `2026-04-05-login-entry-de-shopification.md`
- `2026-04-05-main-account-session-coordination.md`
- `2026-04-05-miaoshou-inventory-snapshot-export-component.md`
- `2026-04-06-account-management-frontend-optimization.md`
- `2026-04-06-b-class-cloud-catch-up-console-implementation.md`
- `2026-04-06-collection-config-main-account-scoping.md`
- `2026-04-06-collection-config-shop-scope-scheduler-implementation.md`
- `2026-04-06-data-sync-template-management-update-workbench.md`
- `2026-04-06-employee-salary-single-page.md`
- `2026-04-06-follow-investment-profit-sharing.md`
- `2026-04-06-tiktok-analytics-services-agent-export.md`
- `2026-04-07-collection-execution-mode-and-verification-preview.md`
- `2026-04-07-data-sync-covered-template-manual-update.md`
- `2026-04-07-investor-architecture-canvas.md`
- `2026-04-07-orders-rmb-field-preservation.md`
- `2026-04-09-cross-platform-notification-overlay-stabilization.md`
- `2026-04-09-data-sync-file-list-batch-delete.md`
- `2026-04-09-snapshot-continuous-inventory-aging.md`
- `2026-04-10-collection-config-queue-runner-implementation.md`
- `2026-04-10-miaoshou-orders-export-confirm-dialog.md`
- `2026-04-10-monthly-profit-settlement-center.md`
- `2026-04-10-schema-alignment-program.md`
- `2026-04-10-shopee-latest-report-row-binding.md`
- `2026-04-11-employee-collaboration-task-center-v1.md`
- `2026-04-11-performance-profit-basis-alignment.md`
- `2026-04-11-store-analysis-redesign.md`
- `2026-04-12-docker-migration-and-celery-readiness.md`
- `2026-04-12-employee-task-center-phase2-enhancements.md`
- `2026-04-12-formal-training-management-module.md`
- `2026-04-12-shopee-export-component-boundary-refactor.md`
- `2026-04-12-tiktok-export-download-boundary-refactor.md`
- `2026-04-12-training-management-phase1.md`
- `2026-04-13-approval-center-unified-implementation.md`
- `2026-04-13-collection-runtime-session-unification.md`
- `2026-04-13-data-ingested-refresh-serial-queue.md`
- `2026-04-13-queued-config-run-cancel-implementation.md`
- `2026-04-13-shopee-login-shell-stability.md`
- `2026-04-13-startup-latest-entrypoint.md`
- `2026-04-14-account-alignment-claim-filtering.md`
- `2026-04-14-business-overview-stagnant-board-limits.md`
- `2026-04-14-data-sync-template-drift-and-inventory-granularity.md`
- `2026-04-14-operating-costs-marketing-fee-physical-column-migration.md`
- `2026-04-14-storage-state-first-formal-collection.md`
- `2026-04-15-business-overview-annual-summary-aggregate-fix.md`
- `2026-04-15-c-class-employee-metrics-cleanup-phase.md`
- `2026-04-15-c-class-employee-metrics-english-column-migration.md`
- `2026-04-15-labor-efficiency-employee-identity.md`
- `2026-04-15-operation-score-minimal-closure.md`
- `2026-04-15-unified-shop-identity-resolution-plan.md`
- `2026-04-16-metric-date-template-governance.md`
- `2026-04-16-products-semantic-template.md`
- `2026-04-16-tiktok-edge-profile-semi-automatic-collection.md`

### 2026-03 (32)

- `2026-03-18-local-cloud-b-class-canonical-sync.md`
- `2026-03-21-playwright-frontend-smoke.md` (partial checked)
- `2026-03-21-postgresql-api-semantic-mart-cutover.md`
- `2026-03-22-canonical-collection-components.md`
- `2026-03-23-collection-to-cloud-auto-sync-preparation.md`
- `2026-03-24-user-approval-menu-notifications.md`
- `2026-03-25-cloud-mainstation-memory-tuning.md`
- `2026-03-25-collection-config-recorder-hardening.md`
- `2026-03-25-collection-to-cloud-admin-console-implementation.md`
- `2026-03-25-deploy-bundle-upload.md`
- `2026-03-25-recorder-segment-validation-implementation-plan.md`
- `2026-03-26-verification-pause-resume-implementation-plan.md`
- `2026-03-27-active-components-and-archive-isolation.md`
- `2026-03-27-collection-architecture-v2-phase-1.md`
- `2026-03-27-collection-output-path-unification.md`
- `2026-03-27-collection-verification-workbench.md`
- `2026-03-27-miaoshou-login-v2-migration.md`
- `2026-03-27-miaoshou-orders-export-v2-migration.md`
- `2026-03-27-persistent-task-center.md`
- `2026-03-27-time-selection-unification.md`
- `2026-03-28-database-schema-cleanup.md`
- `2026-03-28-dim-shops-core-canonical.md`
- `2026-03-28-platform-adapter-surface-convergence.md`
- `2026-03-28-pwcli-minimal-command-workflow.md`
- `2026-03-28-shopee-login-v2.md`
- `2026-03-29-shopee-products-export.md`
- `2026-03-31-catalog-file-delete.md`
- `2026-03-31-collection-config-alignment.md`
- `2026-03-31-collection-module-boundaries-implementation.md`
- `2026-03-31-login-headful-fallback.md`
- `2026-03-31-miaoshou-orders-file-platform-semantics.md`
- `2026-03-31-tiktok-products-export.md`

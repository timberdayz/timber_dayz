# Verification Matrix

This file maps changed surfaces to repository-specific checks. The active verification workflow remains `superpowers`.

## Rule And Documentation Changes

- Run `python scripts/verify_rules_completeness.py`.
- Run `python scripts/verify_root_md_whitelist.py` when root Markdown or documentation policy changes.
- Run `python -m py_compile scripts/verify_rules_completeness.py scripts/verify_root_md_whitelist.py scripts/verify_architecture_ssot.py` when verification scripts change.
- Run `powershell -ExecutionPolicy Bypass -File .\scripts\verify_pwcli_helpers.ps1` when `pwcli` helper rules or wrappers change.

## Architecture Changes

- Run `python scripts/verify_architecture_ssot.py` for ORM, schema, or architecture-boundary changes.
- Inspect `docs/architecture/PROJECT_STRUCTURE.md` and `docs/architecture/BOUNDARIES.md` for placement rules.

## Backend Changes

- Prefer targeted backend tests under `backend/tests/`.
- Check async database usage when touching runtime database code.
- Verify typed endpoints use schemas from `backend/schemas/`.
- The repository carries a pre-existing failing-test baseline, so "no new failures" must be
  proven by a **failure-set diff**, not by a count. Produce a junit XML for both the base
  revision and the changed revision
  (`python -m pytest <target> -q --tb=no --junitxml=<file>.xml`), then run
  `python scripts/diff_pytest_junit.py <before.xml> <after.xml>` — it prints
  `NEW` / `FIXED` / `COMMON` and exits `1` when new failures appear. See
  `docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md` Task 10.
- Beware the **order-dependent pollution** below when comparing baselines: a failure that
  only appears in a full-suite run may be caused by an earlier test leaking environment
  state, not by the change under review. When a diff reports a single new failure,
  reproduce it at the base revision with the *same* test set before treating it as a
  regression.

### Known baseline pollution (post-launch V2 debt, recorded 2026-11-04)

`backend/tests/test_project_env.py::test_load_project_env_applies_later_files_as_overrides`
calls the project env loader, which writes `DEPLOYMENT_ROLE=local` into `os.environ`.
`monkeypatch.delenv()` only restores variables that existed before the test, so the value
written *during* the test leaks into every later test in the same session.

Consequence: `backend/tests/test_runtime_mode_route_registration.py::test_collector_mode_exposes_collection_but_not_dashboard`
fails in any full-suite run (collector mode + `DEPLOYMENT_ROLE=local` also registers the
dashboard routes) while passing when the file runs alone. Reproduced identically at the
pre-v7.12.9 base revision, so it is **not** a v7.12.9 regression.

This is non-blocking debt: CI only runs the test files changed by the commit, so it does
not gate the release. Fix it in the post-launch V2 rebuild — the fix is to make the env
loader restore `os.environ` after the test (or to use `monkeypatch.setenv` for the values
it writes).

### Inventory backlog age-tier mismatch (post-launch V2 debt, recorded 2026-11-04)

`api.inventory_backlog_summary_module` buckets stock by `days_since_restock` as
active `<30`, mid `90-180`, deep `>=180`, which leaves **30-90 days unbucketed**, while the
business pricing tiers in `finance.sku_pricing_policies` (`min_restock_days` 0 / 60 / 90 /
120) already count stock as stale at **60 days**. Measured in production on 2026-11-04:
167 rows / 167 SKUs / value 47,430.31 are already "stale 30 days" for pricing but show up
as `mid=0, deep=0, active=30` on the dashboard card, and a further 321 rows
(value 150,756.31, 63% of the 239,733.02 total) fall into neither tier system. The card's
`total_value` is a full total while its row/SKU counters cover only 30 rows, so the card
reads as "almost no backlog" while the clearance list holds 513 SKUs.

Non-blocking: the underlying data is correct, only the display buckets disagree. Fix it in
the post-launch V2 rebuild by aligning the view buckets with
`finance.sku_pricing_policies` (or adding the 30-90 band). Do **not** change the
`days_since_restock` source or the clearance criterion — the current numbers are real.

## Frontend Changes

- Prefer targeted frontend checks for the affected module.
- Verify API access stays under `frontend/src/api/`.
- Run `python scripts/verify_utf8_source_hygiene.py` when editing frontend templates or other UTF-8 text-heavy source files on Windows.
- Use a syntax-level frontend check such as `vite build` or `vue-tsc --noEmit` for Vue template changes.

## Collection Changes

- Use `pwcli` evidence for page behavior changes.
- Use `docs/guides/COLLECTION_AUTHORING_RULES.md` as the clean active collection authoring entrypoint.
- Verify canonical components under `modules/platforms/<platform>/components/`.
- Preserve Markdown snapshots and notes when evidence is needed for agent handoff.

## Agent Rules

- Start with the narrowest check that proves the changed behavior.
- Do not claim completion without fresh verification output.

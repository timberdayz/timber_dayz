## Context

The codebase has already partially migrated to a DSS/Metabase architecture, but the migration stopped in the middle. As a result, docs, specs, route registration, and legacy compatibility code describe different sources of truth.

## Goals / Non-Goals

- Goals:
  - establish a single preferred query architecture
  - keep legacy materialized-view operations available only as compatibility tooling
  - make the first repaired legacy surface safe to operate during the wider migration
- Non-Goals:
  - remove every materialized-view dependency in one change
  - fully rewrite dashboard query handlers in this initial convergence step

## Decisions

- Decision: treat DSS/Metabase as the preferred read architecture
  - Alternatives considered: keep a hybrid model indefinitely; restore MV-first semantics
- Decision: keep `/api/mv` temporarily, but explicitly as a legacy compatibility surface
  - Alternatives considered: remove it immediately and risk breaking dependent tooling
- Decision: repair `AsyncSession` correctness before broader cleanup
  - Alternatives considered: defer fixes until the entire MV path is removed

## Risks / Trade-offs

- Risk: some internal tooling may still rely on `/api/mv`
  - Mitigation: keep the API available while relabeling it as legacy
- Risk: docs and runtime wiring may remain partially inconsistent during the transition
  - Mitigation: capture the direction in OpenSpec first and use follow-up changes to complete convergence

## Migration Plan

1. Add OpenSpec deltas for DSS-first dashboard reads and legacy-only MV behavior
2. Repair and test the legacy `/api/mv` router
3. Update runtime wiring and documentation to remove MV as a recommended path
4. Queue follow-up cleanup for remaining MV-backed dashboard/query handlers

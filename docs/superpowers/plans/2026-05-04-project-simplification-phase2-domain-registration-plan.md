# Project Simplification Phase 2 Domain Registration Plan

## Metadata
- Date: 2026-05-04
- Phase: 2
- Focus: Introduce backend domain registration ownership without changing runtime behavior

## Objective

Move router-registration ownership one layer deeper than `backend/app/bootstrap/` by introducing explicit backend domain registration modules.

This phase is still composition-only. It does not physically move router files out of `backend/routers/`, and it does not change route paths, tags, dependencies, or runtime-mode behavior.

## Scope

In scope:

- `backend/domains/collection/`
- `backend/domains/data_platform/`
- `backend/domains/business/`
- `backend/domains/platform/`
- bootstrap wrappers under `backend/app/bootstrap/`
- route-registration contract tests

Out of scope:

- moving routers physically into domain folders
- moving services or schemas
- changing `modules/core/db/schema.py`
- changing frontend structure
- changing route contracts or auth behavior

## Target Outcomes

After this phase:

- backend domain boundaries exist as importable Python packages
- bootstrap modules delegate to domain-owned registration functions
- runtime mode behavior remains unchanged
- later router relocation can happen domain by domain without expanding `backend/main.py`

## Work Breakdown

### Step 1: Create Domain Registration Packages

Create:

- `backend/domains/collection/routes.py`
- `backend/domains/data_platform/routes.py`
- `backend/domains/business/routes.py`
- `backend/domains/platform/routes.py`
- `backend/domains/platform/development.py`

Each file should own one bounded route-registration surface.

### Step 2: Rehome Registration Ownership

Move the `include_router(...)` ownership from:

- `backend/app/bootstrap/common.py`
- `backend/app/bootstrap/collector.py`
- `backend/app/bootstrap/production.py`
- `backend/app/bootstrap/development.py`

into the new domain modules, then convert the bootstrap files into compatibility wrappers.

### Step 3: Add Domain Registration Tests

Add focused tests that register each domain surface onto a blank `FastAPI()` app and assert representative routes exist.

Representative checks:

- collection: `/api/collection/configs`
- data platform: `/api/data-pipeline/status`
- business: `/api/dashboard/business-overview/kpi`
- platform: `/api/users/`
- development support: `/api/system/performance/test/health`

### Step 4: Re-verify Runtime Modes

Re-run the existing runtime-mode and route-contract tests to prove the new domain layer does not change behavior for:

- `production`
- `collector`
- `development`

## Verification Strategy

Minimum verification:

1. `python -m pytest backend/tests/test_domain_route_registration.py -q`
2. `python -m pytest backend/tests/test_runtime_mode_route_registration.py backend/tests/data_pipeline/test_postgresql_dashboard_entrypoints.py backend/tests/test_cloud_sync_app_registration.py backend/tests/test_exceptions.py backend/tests/data_pipeline/test_run_py_runtime_mode.py backend/tests/data_pipeline/test_run_py.py -q`
3. `python -m py_compile` across changed bootstrap and domain modules

## Risks And Controls

### Risk: Domain Split Accidentally Changes Runtime Surfaces
- Control: keep all route wiring identical and re-run runtime-mode contract tests

### Risk: Bootstrap And Domain Layers Diverge
- Control: make bootstrap files thin wrappers with no extra route logic

### Risk: Phase 2 Grows Into Physical Router Migration Too Early
- Control: stop at registration ownership; leave file relocation for the next slice

## Next Slice

After this registration phase is stable, the next slice should be physical router relocation for one domain at a time, starting with the least coupled domain surface rather than moving everything at once.

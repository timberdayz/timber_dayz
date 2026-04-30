# Project Simplification Phase 1 Plan

## Metadata
- Date: 2026-04-30
- Phase: 1
- Focus: Runtime composition split and implementation guardrails

## Objective

Complete the first implementation phase of project simplification without changing business behavior.

Phase 1 focuses on:

- splitting backend runtime composition
- making runtime modes explicit
- preparing the codebase for later domain relocation

## Scope

In scope:

- `backend/main.py`
- new bootstrap files under `backend/app/bootstrap/`
- new application entry under `backend/app/main.py`
- `run.py` runtime mode handoff
- planning and documentation updates

Out of scope:

- moving all routers physically
- moving all services physically
- decomposing `schema.py`
- frontend physical migration
- deleting historical scripts or archives

## Target Outcomes

After Phase 1:

- runtime composition is explicit for `production`, `collector`, and `development`
- router registration logic is separated from the legacy all-in-one backend entry
- old import and startup paths still work
- later domain migration can proceed against a stable bootstrap structure

## Work Breakdown

### Step 1: Inventory Existing Backend Composition

Actions:

- enumerate all current `include_router` registrations
- classify each router into `collection`, `data_platform`, `business`, or `platform`
- identify any router that is development-only or compatibility-only

Output:

- stable grouping map for router composition

### Step 2: Introduce Bootstrap Structure

Actions:

- create `backend/app/bootstrap/common.py`
- create `backend/app/bootstrap/register_production.py`
- create `backend/app/bootstrap/register_collector.py`
- create `backend/app/bootstrap/register_development.py`
- create `backend/app/main.py`

Rules:

- do not change route paths
- do not change tags
- do not change dependencies
- do not modify router internals in this phase

### Step 3: Move Registration Logic

Actions:

- move common router registration into `common.py`
- move production-specific registration into `register_production.py`
- move collector-specific registration into `register_collector.py`
- move development-only registration into `register_development.py`

Rules:

- preserve router order where order may matter
- preserve startup and middleware behavior
- preserve compatibility behavior through wrapper entry points

### Step 4: Convert Legacy Backend Entry into Compatibility Shim

Actions:

- keep `backend/main.py` as the compatibility import path
- delegate app creation to `backend.app.main`

Rules:

- existing startup commands must continue to work
- external references to `backend.main:app` or `backend.main:create_app` must not break

### Step 5: Add Runtime Mode Selection

Actions:

- define runtime mode handling in `backend/app/main.py`
- update `run.py` to pass explicit mode values where applicable

Mode intent:

- `production`: business + data platform + platform
- `collector`: collection + data platform + platform
- `development`: diagnostics, test helpers, compatibility surfaces, and optional full stack composition

### Step 6: Verify Behavior Preservation

Actions:

- verify app import and startup still succeed
- verify existing route presence for representative endpoints in each runtime mode
- verify no unexpected route loss

Minimum verification areas:

- auth and user management
- dashboard API
- collection API
- field mapping or data pipeline API

## Verification Strategy

Phase 1 completion claims require fresh evidence.

Recommended verification:

1. Static import verification
   - import app from legacy backend entry
   - import app from new backend entry
2. Router presence verification
   - inspect OpenAPI route list or runtime route table
3. Targeted tests
   - run the smallest relevant backend tests for startup and route contracts

The exact command set should be selected during implementation based on the existing test layout.

## Rollback Strategy

If the new bootstrap assembly causes route loss or startup instability:

- keep `backend/main.py` intact enough to restore the prior registration path quickly
- revert only the new bootstrap integration layer
- do not partially revert router files individually unless route mapping has changed physically

Because Phase 1 is composition-only, rollback should remain low risk if physical file movement is deferred.

## Risks and Controls

### Risk: Route Missing in One Runtime Mode
- Control: verify representative routes per mode before claiming completion

### Risk: Hidden Dependency on Registration Order
- Control: preserve current grouping order during migration and verify startup/import behavior

### Risk: Development Helpers Leak into Production Mode
- Control: isolate development registration in a dedicated bootstrap file

### Risk: Collector Environment Loses Necessary Data-Platform APIs
- Control: keep collector mode coupled to required data ingestion and mapping surfaces

## Follow-Up Phases

Phase 2:
- introduce backend `domains/` structure
- start relocating routers by domain

Phase 3:
- relocate services and schemas by domain
- narrow shared utility surfaces

Phase 4:
- reorganize frontend by the same domain model

Phase 5:
- decompose `modules/core/db/schema.py` internally while preserving the SSOT rule

Parallel follow-up track:
- unify business overview read models and page loading tiers as defined in `docs/superpowers/specs/2026-04-30-business-overview-read-model-unification-design.md`

## Exit Criteria

Phase 1 is complete when:

- new bootstrap files exist and are active
- legacy startup compatibility remains intact
- runtime modes are explicit in code
- representative startup and route verification pass
- planning and design documents reflect the implemented composition model

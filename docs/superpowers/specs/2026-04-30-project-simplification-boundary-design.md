# Project Simplification Boundary Design

## Metadata
- Date: 2026-04-30
- Scope: Repository structure, backend runtime composition, frontend domain organization, environment boundaries
- Status: Draft for implementation

## Context

The current repository preserves substantial business capability and should continue to do so. The problem is not that the system has too many business modules. The problem is that code organization, runtime assembly, support assets, and historical assets are mixed together, which makes the system harder to use, harder to maintain, and riskier to evolve.

The system currently serves three distinct runtime purposes:

1. Production environment
   - Primary responsibility: persist, calculate, query, and display business data
2. Collector environment
   - Primary responsibility: execute collection flows, manage browser and account sessions, and persist collected data
3. Development environment
   - Primary responsibility: local development, testing, diagnosis, and verification

These three purposes should remain distinct after the simplification effort.

## Problem Statement

The current structure creates the following maintenance problems:

- The repository root mixes runtime code, support tooling, diagnostics, historical assets, and runtime outputs.
- Backend runtime composition is oversized and centralized in a single assembly surface.
- The project contains multiple business domains, but those domains are not expressed clearly in the directory structure.
- Production, collector, and development concerns are assembled from largely the same entry surfaces without a sufficiently explicit mode boundary.
- Shared assets such as scripts, SQL, tools, and archive material increase navigation noise and make change scope harder to reason about.

## Goals

This simplification effort aims to achieve the following:

- Preserve all current business capability that remains operationally relevant
- Make domain boundaries explicit
- Separate production, collector, and development runtime composition
- Reduce the size and responsibility of central entry points
- Make future upgrades safer by reducing cross-domain accidental coupling
- Improve onboarding and change navigation for developers

## Non-Goals

This effort does not aim to:

- Delete major business modules by default
- Introduce microservices
- Change business behavior in the first phase
- Replace the ORM SSOT rule in `modules/core/db/schema.py`
- Rebuild the application architecture from scratch

## Target Architecture Direction

The recommended target is a modular monolith with explicit runtime modes.

### Runtime Modes

The codebase should support three clear runtime modes:

- `production`
  - Registers business display, business calculation, data platform, and platform management surfaces
- `collector`
  - Registers collection execution, session management, data platform, and platform management surfaces
- `development`
  - Registers development-only diagnostics, test helpers, and optional compatibility surfaces

### Domain Boundaries

The backend should be reorganized around four top-level domains:

1. `collection`
   - Browser automation
   - collection execution
   - component runtime
   - account and shop session management
   - collection scheduling
2. `data_platform`
   - field mapping
   - ingestion
   - standardization
   - data quality
   - quarantine
   - SQL semantic, mart, and API assets
   - cloud sync and data pipeline control
3. `business`
   - dashboard
   - sales
   - inventory
   - finance
   - HR
   - performance
   - profit and settlement
4. `platform`
   - auth
   - users
   - permissions
   - system configuration
   - logs
   - monitoring
   - rate limiting
   - backup and notifications

## Repository Structure Direction

The simplification should move the repository toward explicit layers of concern:

```text
backend/
  app/
  domains/
  shared/
frontend/src/
  app/
  domains/
  shared/
ops/
archive/
runtime/
```

The first phase does not need to reach this full target physically. The first phase should begin by introducing the structure and moving assembly logic into it.

## Backend Composition Direction

The highest-value first move is to split runtime assembly away from the current central entry point.

Recommended intermediate target:

```text
backend/
  app/
    main.py
    bootstrap/
      common.py
      register_production.py
      register_collector.py
      register_development.py
```

This preserves all existing routers while making environment intent explicit.

## Frontend Structure Direction

The frontend should mirror the same four domains:

- `collection`
- `data-platform`
- `business`
- `platform`

Views, APIs, stores, and route metadata should converge around those domain boundaries over time. The first phase does not need to physically move all frontend files, but future page and API work should align with the target grouping.

### Dashboard Read Model Alignment

Within the `business` domain, the business overview page should be treated as a production homepage surface rather than a loose collection of analytical requests.

Its optimization direction is captured separately in:

- `docs/superpowers/specs/2026-04-30-business-overview-read-model-unification-design.md`

That design establishes:

- critical vs secondary module loading tiers
- read-model-first homepage queries
- a bootstrap-style aggregate endpoint for first-screen dashboard data

## Data Model Direction

`modules/core/db/schema.py` remains the ORM SSOT. The simplification path should preserve that rule while allowing internal logical decomposition.

Recommended later target:

```text
modules/core/db/
  schema/
    collection.py
    data_platform.py
    business_sales.py
    business_inventory.py
    business_finance.py
    business_hr.py
    business_profit.py
    platform.py
    __init__.py
```

External code should continue importing from a single SSOT entry.

## Change Strategy

The implementation should proceed in small, behavior-preserving steps:

1. Introduce new bootstrap composition files
2. Move router registration logic into mode-specific composition functions
3. Keep old entry points as compatibility shims
4. Introduce domain directories
5. Gradually relocate routers and services by domain
6. Reorganize frontend by domain
7. Decompose model and support asset structure

## Risks

- If router registration is changed too aggressively, environment-specific routes may disappear unexpectedly.
- If collector surfaces are mixed into production during the transition, runtime scope will remain unclear.
- If the schema decomposition begins before runtime composition is stabilized, migration risk will rise sharply.
- If support assets are moved before ownership is documented, operators may lose working paths.

## Success Criteria

This design is considered successful when:

- Production, collector, and development runtime composition are explicit and testable
- Backend entry assembly is no longer concentrated in a single oversized file
- New work can be assigned to one of the four main domains with little ambiguity
- Repository navigation cost decreases because active runtime code is easier to distinguish from support assets
- The system remains behaviorally compatible throughout the first phase

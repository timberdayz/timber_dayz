# Business Overview Read Model Unification Design

## Metadata
- Date: 2026-04-30
- Scope: Business overview page, PostgreSQL dashboard read path, frontend loading strategy
- Status: Draft for implementation

## Context

The business overview page is one of the most visible production surfaces in the system. It represents the production environment's core purpose: persist, calculate, query, and display business data.

The current codebase already uses the PostgreSQL-first dashboard path and already contains:

- `b_class -> semantic -> mart -> api` layering
- dashboard API routes
- cache and warmup support
- generated SQL assets under `sql/api_modules/`

However, the business overview page still mixes multiple retrieval patterns:

- some modules read pre-aggregated API-layer assets
- some modules still perform runtime-heavy aggregation in the service layer
- the frontend page triggers many parallel requests in a single refresh cycle

This creates uneven performance and makes the page harder to optimize systematically.

## Problem Statement

The current business overview implementation has three main issues:

1. The page is over-fragmented at request time
   - the frontend refresh path requests many modules concurrently
   - first paint latency becomes coupled to the slowest secondary module

2. Read paths are inconsistent
   - some modules read stable `api.*` read models
   - some modules still aggregate from raw fact tables and raw JSON at runtime

3. The page lacks explicit read-tier prioritization
   - critical above-the-fold modules and secondary analytical modules are refreshed together
   - expensive analysis modules compete with homepage KPIs for the same user-visible latency budget

## Goals

- Make business overview read behavior consistent
- Ensure first-screen dashboard blocks read from stable read models
- Reduce first-screen latency by separating critical and secondary data loading
- Preserve current business semantics while simplifying the read path
- Align dashboard optimization with the broader modular simplification effort

## Non-Goals

- Redesigning all dashboard pages in one step
- Changing business formulas in this design
- Deleting analytical modules from the product
- Replacing the PostgreSQL dashboard architecture

## Design Principles

### Principle 1: Homepages must read from read models

The business overview page should not perform runtime-heavy aggregation from raw fact JSON when serving user-facing production traffic.

For high-frequency homepage reads:

- `b_class` is for raw persistence
- `semantic` is for normalization
- `mart` is for reusable aggregates
- `api` is for page-facing read shapes

Production homepage reads should stop at `api` whenever possible.

### Principle 2: First-screen data is not the same as secondary analytics

The page should distinguish between:

- critical modules required for first-screen business understanding
- secondary modules that support deeper browsing and analysis

These two classes should not share the same loading contract.

### Principle 3: Dashboard pages should use stable read contracts

The frontend should not own complexity that belongs in backend read models. Page code should consume stable response shapes rather than orchestrate many unrelated low-level requests as if it were its own reporting engine.

## Target Loading Model

### Critical Tier

These modules are treated as first-screen content:

- `kpi`
- `comparison`
- `operational_metrics`

Requirements:

- must read from stable `api.*` read models
- should be eligible for warmup
- should have tighter cache invalidation discipline
- should be loaded first

### Secondary Tier

These modules remain available on the page but should not block first-screen usefulness:

- `shop_racing`
- `traffic_ranking`
- `inventory_backlog`
- `clearance_ranking`

Requirements:

- may load after critical tier
- may use looser cache freshness
- should continue moving toward read-model-first implementation

## Backend Read Path Direction

### Current Direction to Preserve

The existing `sql/api_modules/` layer is the correct place to define business-overview page-facing read assets.

### Required Unification

The following rules should apply:

- `api.*` assets may reshape data for page use
- `api.*` assets should not become a place for heavyweight runtime-only business recomputation
- service methods should prefer reading `api.*` assets over stitching raw `b_class` JSON in request time

### KPI Path

The monthly KPI path currently has a heavier runtime aggregation shape than the rest of the page.

Target:

- move monthly KPI reads to a stable `mart/api` read model
- eliminate homepage dependence on request-time raw JSON parsing and deduplication

### Clearance and Inventory Modules

These modules are analytically useful but more expensive.

Target:

- keep them available
- evaluate whether they should remain homepage-synchronous
- move more of their logic into reusable `mart` or `api` assets if they remain part of the homepage experience

## API Contract Direction

### Introduce a Bootstrap Endpoint

Add a homepage-focused aggregate endpoint, for example:

- `/api/dashboard/business-overview/bootstrap`

This endpoint should return the critical tier in one backend-composed response:

- KPI
- comparison
- operational metrics

Purpose:

- reduce frontend request fan-out
- centralize critical-tier caching and warmup
- make the business overview page behave like a production homepage, not a collection of unrelated mini-reports

### Keep Secondary Endpoints

Existing module endpoints should remain available for:

- secondary page sections
- independent refresh actions
- internal drill-down or future reuse

## Frontend Loading Direction

The frontend page should move from a full-page `Promise.all` refresh to staged loading:

1. load critical tier
2. paint first-screen dashboard state
3. load secondary tier in the background
4. allow module-level refresh for expensive analytical sections

This provides a better production experience even if total page data volume remains unchanged.

## Caching Direction

### Critical Tier Caching

Critical business overview data should use:

- stronger warmup coverage
- more predictable invalidation
- shorter user-visible latency target

### Secondary Tier Caching

Secondary modules can use:

- broader TTLs
- less aggressive invalidation
- optional stale-while-revalidate style behavior if introduced later

## Integration with Simplification Program

This design fits within the broader project simplification effort as follows:

- domain placement: `business/dashboard`
- runtime mode relevance: primarily `production`
- backend structure implication: dashboard read models should be treated as business-facing production assets, not ad hoc cross-domain utilities

The business overview optimization should therefore be treated as part of the broader boundary cleanup, not as an isolated page tweak.

## Implementation Sequence

1. Document critical vs secondary business overview modules
2. Introduce the business overview bootstrap endpoint
3. Shift KPI monthly path to a stable read model
4. Update frontend loading strategy to staged refresh
5. Reassess secondary modules for additional `mart/api` downshifting

## Risks

- If read-model unification changes formulas unintentionally, business trust will drop
- If bootstrap aggregation is introduced without preserving existing contracts, dependent callers may break
- If expensive secondary modules remain synchronous, first-screen improvement will be limited
- If KPI migration happens before the replacement read model is validated, homepage correctness may regress

## Success Criteria

This design is successful when:

- business overview critical modules no longer depend on runtime raw JSON aggregation
- first-screen business overview data loads independently from slower secondary modules
- the dashboard read path is more uniform and easier to reason about
- business overview performance work aligns with the repository simplification strategy rather than living as a separate special case


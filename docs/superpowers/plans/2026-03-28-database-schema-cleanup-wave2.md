# Database Schema Cleanup Wave 2

## Goal

Keep the higher-risk duplicate groups in proof-and-alignment mode until runtime ownership, foreign-key dependencies, and historical schema drift are fully understood.

## Scope

- `public.entity_aliases` vs `b_class.entity_aliases`
- `public.staging_raw_data` vs `b_class.staging_raw_data`
- `public.dim_shops` vs `core.dim_shops`

## Why these are not wave 1

All three still have active blockers that are qualitatively different from `target_breakdown`:

- ORM models still resolve to the default schema
- runtime references are broad or ambiguous
- table semantics overlap with lineage, aliasing, or foreign-key-heavy dimension usage
- historical docs and migration notes disagree about the canonical schema

## Risk profile by table

### `entity_aliases`

- current ORM model resolves to `public`
- schema comments describe it as a unifying replacement for `dim_shops` and `account_aliases`
- migration/docs history claims `b_class` is canonical
- cleanup risk:
  - alias resolution drift
  - hidden read paths in alignment or mapping workflows

### `staging_raw_data`

- current ORM model resolves to `public`
- migration/docs history claims `b_class` is canonical
- cleanup risk:
  - staging pipeline read/write breakage
  - retention/debug workflows losing access to operational raw rows

### `dim_shops`

- current ORM model resolves to `public`
- production duplicate group claims `core` copy also exists
- the table is referenced by many composite foreign keys and joins
- cleanup risk:
  - breakage across target management, performance, campaign, and dimension-based SQL
  - FK or join failures if canonical ownership is misidentified

## Required proof before any wave 2 migration

1. ORM ownership proof
   - confirm model schema
   - confirm whether runtime can tolerate schema reassignment
2. Runtime read-path proof
   - grep-backed evidence for router/service/SQL reads
   - identify explicit schema-qualified reads vs search-path reads
3. Runtime write-path proof
   - identify create/update/sync paths
   - confirm which physical copy receives writes in current environments
4. Production row-state proof
   - compare row counts and freshness between duplicate copies
   - verify whether one copy is stale, mirrored, or independently mutated
5. Safety strategy decision
   - `archive_rename`
   - view/synonym compatibility layer
   - schema/ORM alignment first, cleanup later

## Recommended execution order

### Step 1: Proof tests and helpers

- add focused proof helpers for:
  - `entity_aliases`
  - `staging_raw_data`
  - `dim_shops`
- output must distinguish:
  - model schema
  - runtime read files
  - runtime write files
  - explicit schema-qualified references

### Step 2: Production-state inventory

- inspect both schema copies for:
  - row count
  - latest update timestamp if available
  - obvious divergence

Current status:

- completed for the first production snapshot
- result:
  - `entity_aliases`: both copies empty
  - `staging_raw_data`: both copies empty
  - `dim_shops`: `public` empty, `core` populated

### Step 3: Candidate split

After proof, split wave 2 into:

- `wave 2a`: potentially alignable alias/staging tables
- `wave 2b`: `dim_shops` and any FK-heavy dependents

### Step 4: Only then write migration contracts

- no migration file before the proof matrix exists
- each table group gets its own contract and rehearsal path

## Non-goals

- do not fold these tables into the already-validated wave 1 path
- do not write a production migration in this stage
- do not assume docs claiming `core` or `b_class` are canonical are automatically true

## Exit criteria

Wave 2 planning is complete only when:

- all 3 tables have explicit proof notes
- production duplicate-state evidence is recorded
- candidate groups are split by risk
- the next migration contract scope is narrow enough to rehearse independently

## Current recommendation after production evidence

- `entity_aliases` and `staging_raw_data` can continue on a lower-risk proof track
- `dim_shops` should be treated as a separate runtime/schema-alignment investigation before any cleanup design

# Schema Cleanup Wave 2 Production Evidence

**Date:** 2026-03-28
**Source:** live production PostgreSQL inspection via host-level read-only query

## Scope

- `public.entity_aliases` vs `b_class.entity_aliases`
- `public.staging_raw_data` vs `b_class.staging_raw_data`
- `public.dim_shops` vs `core.dim_shops`

## Summary

The three wave-2 duplicate groups do not share the same production state:

- `entity_aliases`: both copies exist but both are empty
- `staging_raw_data`: both copies exist but both are empty
- `dim_shops`: `public` is empty, while `core` contains live rows

This means wave 2 must remain split:

- alias/staging tables: empty-state ownership decision
- dim_shops: live-dimension ownership and runtime inconsistency investigation

## Evidence Snapshot

| Table | Public Count | Target Count | Public Latest | Target Latest | Public Only | Target Only |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| `entity_aliases` | 0 | 0 | null | null | 0 | 0 |
| `staging_raw_data` | 0 | 0 | null | null | 0 | 0 |
| `dim_shops` | 0 | 29 | null | 2026-01-27 13:51:47.359293+00 | 0 | 29 |

## Interpretation

### `entity_aliases`

- production currently provides no row-level signal for ownership
- because both copies are empty, the main blocker is runtime ownership proof, not data migration risk

### `staging_raw_data`

- production currently provides no row-level signal for ownership
- because both copies are empty, the main blocker is runtime ownership proof, not live data divergence

### `dim_shops`

- production clearly shows the duplicate copies are not mirrors
- `core.dim_shops` is populated and `public.dim_shops` is empty
- this is the strongest evidence that `dim_shops` is not a normal duplicate-cleanup case
- before any cleanup, we need to resolve why current ORM/runtime still points to `public` while the live rows are in `core`

## Resulting Recommendation

1. Keep `entity_aliases` and `staging_raw_data` in proof mode, but treat them as lower operational risk because both copies are empty in production.
2. Escalate `dim_shops` as a runtime/schema-alignment issue, not just a cleanup candidate.
3. Do not draft a shared wave-2 migration for all three tables.

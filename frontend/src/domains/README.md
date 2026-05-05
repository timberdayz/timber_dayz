# Frontend Domains

This folder mirrors backend domain boundaries:

- `collection`
- `data_platform`
- `business`
- `platform`
- `shared`

Phase 4 cutover rule:

- New code should be added under `src/domains/<domain>/...`.
- During migration, legacy locations (`src/views`, `src/api`, `src/stores`, `src/services`) may provide thin bridge modules that re-export domain-owned implementations.

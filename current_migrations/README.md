# Current Schema Migration Chain

`current_migrations/` is the independent, post-history Alembic chain.
Historical `migrations/versions/` remains read-only and is never used by the
deployment or application startup migration entrypoints.

`current_schema_20260805` is a reviewed static DDL baseline generated from the
read-only production schema at legacy revision `20260805_payroll_backfill_audit`.
It includes the schemas, tables, constraints, indexes, functions, triggers,
views, materialized views, and required catalog data present in that source.
Archived `core.alembic_version` and `public.alembic_version` tables are excluded:
new databases are versioned only by `public.current_schema_alembic_version`.
The baseline generator also excludes retired `public.sales_targets` and the
retired `core.data_quarantine.platform` / `data_type` fields.

`current_schema_20260808_operation_performance_workbench` is the first
increment after that production baseline. It adds the operation-performance
workbench catalog and rules. It does not silently collapse duplicate shop
overrides; legacy adoption is rejected before any write when a manual data
resolution is required.

The only approved legacy adoption mapping is version-controlled in
`support_policy.json`. The wrapper performs read-only revision and schema
fingerprint checks, stamps `current_schema_20260805` only after they pass, and
then upgrades to the current head. A production database retains its legacy
version table and business data; a fresh database does not create any archived
version table. Dashboard runtime bootstrap may still refresh its assets, but
the static schema objects that existed in the approved source are part of this
baseline. `scripts/bootstrap_postgresql_dashboard.py` remains the lifecycle
owner for dashboard refresh operations after deployment.

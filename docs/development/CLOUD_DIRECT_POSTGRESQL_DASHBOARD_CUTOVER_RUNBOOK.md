# single-environment direct PostgreSQL Dashboard cutover

## Goal

Use the current single cloud environment for a controlled in-place switch to the PostgreSQL Dashboard primary path, while keeping the `xihong` administrator account usable and clearing only business test data.

## Principle

- do not rebuild a fake preprod environment
- do not delete auth/system tables first
- preserve or recreate `xihong`
- clean only business schemas:
  - `a_class`
  - `b_class`
  - `c_class`

## Step 1: Stabilize the administrator account

Run on the cloud server:

```bash
python scripts/query_admin_users.py
python scripts/ensure_all_roles.py
python scripts/create_admin_user.py
```

Expected result:

- `xihong` exists
- `xihong` has admin role
- `xihong` can be used after the cutover

## Step 2: Clean business test data only

Dry-run first:

```bash
python scripts/run_single_env_postgresql_dashboard_cutover.py
```

Execute cleanup only after reviewing the listed tables:

```bash
python scripts/run_single_env_postgresql_dashboard_cutover.py --execute-cleanup
```

This cleanup is intentionally limited to:

- `a_class`
- `b_class`
- `c_class`

Do not directly delete from:

- user/auth tables
- role tables
- session tables
- audit tables
- notification tables
- system/config/security tables

## Step 3: Switch the cloud environment to PostgreSQL Dashboard

Set:

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=true
ENABLE_METABASE_PROXY=false
```

Then deploy using the existing tag-driven production path.

## Step 4: Verify immediately after deployment

Run:

```bash
python scripts/run_postgresql_dashboard_preprod_check.py --base-url <cloud_base_url>
python scripts/check_postgresql_dashboard_ops.py
python scripts/generate_postgresql_dashboard_preprod_report.py --base-url <cloud_base_url> --output <report_path>
```

Manually check:

- `business-overview/kpi`
- `business-overview/comparison`
- `business-overview/shop-racing`
- `business-overview/operational-metrics`
- `annual-summary/kpi`
- `annual-summary/trend`
- `annual-summary/platform-share`
- `annual-summary/by-shop`
- `annual-summary/target-completion`

## Step 5: Rollback if needed

If the new dashboard path shows obvious issues:

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=false
ENABLE_METABASE_PROXY=false
```

Redeploy or restart, then confirm logs show:

- `Dashboard router source: Metabase compatibility`

## Why this approach

- no extra cloud server needed
- no risky direct user-table deletion
- `xihong` remains usable
- business test data can still be reset
- the deployment path stays aligned with your existing tag-driven release model

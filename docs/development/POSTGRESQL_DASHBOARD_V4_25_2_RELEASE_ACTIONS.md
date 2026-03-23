# PostgreSQL Dashboard v4.25.2 release actions

## Why v4.25.2 is needed

`v4.25.1` deployed successfully through GitHub Actions, but it was released from `main` rather than from the cloud-validated PostgreSQL Dashboard cutover line.

That means:

- `v4.25.1` runtime on the server required direct cloud hotfix work
- `main` and the real cloud state are not yet equivalent
- the next correct release should be a patch release that carries the cloud-validated PostgreSQL Dashboard fixes

## Source of truth for the fixes

Use:

- `codex/postgresql-api-semantic-mart-cutover`

This branch contains the cloud-validated PostgreSQL Dashboard state.

## Must-ship areas

At minimum, `v4.25.2` should include these areas:

- `docker-compose.prod.yml`
- `nginx/nginx.prod.conf`
- `backend/main.py`
- `backend/services/postgresql_dashboard_service.py`
- `backend/services/data_pipeline/refresh_registry.py`
- PostgreSQL dashboard SQL assets under `sql/semantic/`, `sql/mart/`, and `sql/api_modules/`
- compatibility helper `scripts/ensure_b_class_compat.py`
- release/runbook docs that explain the new PostgreSQL Dashboard operating model

## Required release sequence

1. Merge or cherry-pick the cloud-validated PostgreSQL Dashboard fixes from `codex/postgresql-api-semantic-mart-cutover` into `main`.
2. Re-run:

```bash
python -m pytest backend/tests/data_pipeline -q
```

3. Confirm the branch intended for release reflects the current cloud state.
4. Create the patch tag:

```bash
git tag v4.25.2
git push origin v4.25.2
```

5. Watch the deployment workflow and confirm success.

## Post-release verification

After `v4.25.2` deploys:

- confirm backend/frontend are on the new released version
- confirm `Dashboard router source: PostgreSQL`
- confirm `/metabase/` remains retired
- confirm all key PostgreSQL Dashboard smoke endpoints still return `200`
- confirm `ops` freshness and lineage records remain healthy

## Recommendation

Recommended next step:

**go for origin tag release of `v4.25.2` after merging the PostgreSQL Dashboard cutover branch into main.**

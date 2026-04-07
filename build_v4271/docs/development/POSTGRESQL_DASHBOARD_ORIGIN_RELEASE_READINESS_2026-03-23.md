# Origin tag release readiness review

## Recommendation

**Recommended next step: go for origin tag release.**

This recommendation is based on both local verification and direct cloud validation already completed on the current PostgreSQL cutover branch.

## Evidence

### Local branch state

- branch: `codex/postgresql-api-semantic-mart-cutover`
- local verification is green
- latest local verification command:

```bash
python -m pytest backend/tests/data_pipeline -q
```

- result during the latest validation cycle: passing

### Cloud runtime state

- cloud host `134.175.222.171` is already running PostgreSQL Dashboard as the primary dashboard path
- backend logs confirm `Dashboard router source: PostgreSQL`
- key dashboard smoke endpoints return `200`
- `ops` observability tables contain successful refresh/freshness records
- `xihong` admin account remains usable
- `/metabase/` no longer behaves as a live runtime feature entrypoint

## Why origin tag release is now appropriate

- the cloud environment has already served as the highest-value real-world validation target
- the key compatibility issues discovered during direct cloud cutover have been fixed in the branch
- the branch now reflects the actual cloud-compatible PostgreSQL Dashboard behavior
- delaying `origin` tag release further would mostly keep repository history behind the already validated runtime state

## Preconditions before tag push

1. confirm the current branch is the exact commit you want to release
2. re-run:

```bash
python -m pytest backend/tests/data_pipeline -q
```

3. choose the release tag version
4. push the release tag through the existing deployment flow

## Recommended release commands

```bash
git tag v4.24.xx
git push origin v4.24.xx
```

If you prefer using the helper:

```powershell
.\scripts\deploy_tag_and_watch.ps1 v4.24.xx
```

## Non-blocking follow-up after origin release

- keep watching cloud dashboard behavior after the tag deployment completes
- preserve rollback docs until you are comfortable removing the last legacy files from the repository
- optionally generate a final polished release note from the cloud cutover report

## Final Decision

**Go for origin tag release.**

The branch is no longer in an “exploratory cloud debugging” state.  
It is now in a “cloud-validated, releaseable” state.

# Deploy Bundle Upload Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated deployment SCP uploads with a single deploy bundle upload and remote extraction path.

**Architecture:** Add a small bundle-builder shell script, then update both release deployment sync steps to upload `deploy_bundle.tgz` and extract it remotely before running the existing remote deploy script.

**Tech Stack:** GitHub Actions workflow YAML, Bash, pytest

---

### Task 1: Lock Bundle Workflow Expectations

**Files:**
- Modify: `backend/tests/data_pipeline/test_release_deployment_pipeline.py`

- [ ] Write failing tests asserting:
  - workflow builds `deploy_bundle.tgz`
  - workflow uploads the bundle once
  - workflow extracts the bundle remotely
  - workflow no longer individually SCP uploads `sql/init` and `nginx.prod.conf`

- [ ] Run:

```bash
python -m pytest backend/tests/data_pipeline/test_release_deployment_pipeline.py -q
```

Expected: fail before implementation.

### Task 2: Implement Bundle Builder And Workflow Refactor

**Files:**
- Create: `scripts/build_deploy_bundle.sh`
- Modify: `.github/workflows/deploy-production.yml`

- [ ] Add bundle-builder script that stages:
  - `docker-compose*.yml`
  - `scripts/deploy_remote_production.sh`
  - `config/*.yaml`
  - `config/*.py`
  - `sql/init/*.sql`
  - `nginx/nginx.prod.conf`
  - while skipping legacy `metabase_config.yaml`

- [ ] Replace both workflow sync steps with:
  - SSH test
  - bundle creation
  - single bundle upload
  - remote extract + chmod

### Task 3: Verify

**Files:**
- Modify: `.github/workflows/deploy-production.yml`
- Modify: `scripts/build_deploy_bundle.sh`
- Modify: `backend/tests/data_pipeline/test_release_deployment_pipeline.py`

- [ ] Run:

```bash
python -m pytest backend/tests/data_pipeline/test_release_deployment_pipeline.py backend/tests/test_runtime_config_alignment.py -q
```

- [ ] Run:

```bash
bash -n scripts/build_deploy_bundle.sh
```

- [ ] Run one real local bundle build and inspect the archive contents.

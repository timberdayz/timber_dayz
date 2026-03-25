# Cloud Mainstation Memory Tuning Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the 4C8G cloud mainstation by removing `celery-exporter` from the default cloud startup path and widening the tightest always-on memory limits.

**Architecture:** Keep the change limited to deployment/runtime configuration. Encode new limits in the cloud overlays and adjust the remote production startup chain so the cloud mainstation no longer starts `celery-exporter` by default.

**Tech Stack:** Docker Compose, Bash deploy script, pytest, YAML

---

## File Structure

### Existing Files To Modify

- `docker-compose.cloud.yml`
  - keep shared cloud defaults
  - widen `celery-beat` memory limit to remove the tightest bottleneck

- `docker-compose.cloud-4c8g.yml`
  - encode the recommended 4C8G app-layer memory targets
  - align `backend` and `celery-worker` with the approved balanced tuning

- `scripts/deploy_remote_production.sh`
  - stop starting `celery-exporter` by default on the cloud mainstation

- `backend/tests/test_runtime_config_alignment.py`
  - assert the new cloud overlay memory targets
  - assert the remote deploy script no longer starts `celery-exporter` in the default app layer startup command

### New Files

- None

---

### Task 1: Lock The Expected Runtime Shape With Tests

**Files:**
- Modify: `backend/tests/test_runtime_config_alignment.py`

- [ ] **Step 1: Write failing tests for cloud memory targets**

Add assertions for:

- `docker-compose.cloud.yml`
  - `celery-beat` memory limit is `256M`
- `docker-compose.cloud-4c8g.yml`
  - `backend` memory limit is `1.5G`
  - `celery-worker` memory limit is `768M`

- [ ] **Step 2: Write a failing test for deploy startup services**

Add an assertion that the default app-layer startup command in `scripts/deploy_remote_production.sh` does not include `celery-exporter`.

- [ ] **Step 3: Run the targeted tests and verify RED**

Run:

```bash
python -m pytest backend/tests/test_runtime_config_alignment.py -q
```

Expected:

- FAIL because current config still uses the old limits and still starts `celery-exporter`

---

### Task 2: Apply Minimal Cloud Mainstation Tuning

**Files:**
- Modify: `docker-compose.cloud.yml`
- Modify: `docker-compose.cloud-4c8g.yml`
- Modify: `scripts/deploy_remote_production.sh`

- [ ] **Step 1: Update shared cloud overlay**

Set:

- `celery-beat` memory limit to `256M`

- [ ] **Step 2: Update 4C8G overlay**

Set:

- `backend` memory limit to `1536M` / `1.5G`
- `celery-worker` memory limit to `768M`

Do not widen unrelated services in this first pass.

- [ ] **Step 3: Remove `celery-exporter` from default cloud app-layer startup**

Change the remote production startup command so the default app-layer startup set is:

- `backend`
- `celery-worker`
- `celery-beat`

and not `celery-exporter`.

- [ ] **Step 4: Keep the rest of the deploy flow unchanged**

Do not alter:

- infrastructure startup order
- migration flow
- frontend/nginx startup
- legacy Metabase cleanup logic

---

### Task 3: Verify GREEN

**Files:**
- Modify: `backend/tests/test_runtime_config_alignment.py`
- Modify: `docker-compose.cloud.yml`
- Modify: `docker-compose.cloud-4c8g.yml`
- Modify: `scripts/deploy_remote_production.sh`

- [ ] **Step 1: Re-run the targeted tests**

Run:

```bash
python -m pytest backend/tests/test_runtime_config_alignment.py -q
```

Expected:

- PASS

- [ ] **Step 2: Run one additional focused sanity read**

Check the final service startup command and memory values directly in the modified files.

- [ ] **Step 3: Record the effective intended cloud mainstation envelope**

Document in the final summary:

- `postgres`: `1.5G`
- `redis`: `256M`
- `backend`: `1.5G`
- `celery-worker`: `768M`
- `celery-beat`: `256M`
- `frontend`: `256M`
- `nginx`: `128M`
- `celery-exporter`: not started by default

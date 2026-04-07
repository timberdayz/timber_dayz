# Cloud Mainstation Memory Tuning Design

**Date:** 2026-03-25  
**Last Updated:** 2026-03-25

## Goal

Improve stability of the 4C8G cloud mainstation with the smallest safe production change set.

The target outcome is:

- remove `celery-exporter` from the cloud mainstation default runtime
- widen the most constrained always-on service memory limits
- keep PostgreSQL-first mainstation behavior intact

## Non-Goals

Out of scope for this design:

- collection-role isolation and route hardening
- cloud-sync runtime activation
- monitoring-stack rollout
- broader compose cleanup across all environments

## Current Reality

The live cloud mainstation is currently running:

- `frontend`
- `backend`
- `postgres`
- `redis`
- `nginx`
- `celery-worker`
- `celery-beat`
- `celery-exporter`

Observed live memory pressure shows:

- `celery-beat` is near its limit
- `backend` and `celery-worker` still have headroom but not much margin for spikes
- `postgres` is not currently the memory bottleneck
- no dedicated monitoring stack is running on this host

## Recommended Change

### 1. Stop `celery-exporter` on the cloud mainstation by default

`celery-exporter` is optional for the current host role. Since Prometheus/Grafana/Alertmanager are not running on the same cloud mainstation, keeping the exporter always-on consumes memory without current operational value.

This change should affect the default production startup chain, while still allowing operators to start the exporter explicitly later if needed.

### 2. Retune cloud-mainstation memory limits for the 4C8G shape

Recommended targets:

- `postgres`: `1.5G`
- `redis`: `256M`
- `backend`: `1.5G`
- `celery-worker`: `768M`
- `celery-beat`: `256M`
- `frontend`: `256M`
- `nginx`: `128M`
- `celery-exporter`: removed from default startup

This keeps the total runtime envelope around `4.7G`, leaving meaningful memory for:

- host OS
- Docker overhead
- filesystem cache
- temporary runtime spikes

### 3. Keep the change cloud-scoped

The base production compose should remain broadly usable. The main tuning should live in cloud overlays and the remote deploy startup sequence, so the change is explicitly about the cloud mainstation and not every production-like environment.

## Approach Options

### Option A: Only increase `celery-beat`

Pros:

- smallest change
- directly addresses the tightest service

Cons:

- leaves `backend` and `celery-worker` with limited buffer
- keeps `celery-exporter` consuming memory without current value

### Option B: Balanced mainstation tuning

Pros:

- fixes the tightest service
- adds moderate headroom to app-layer services
- recovers memory by dropping `celery-exporter`
- stays well within 4C8G limits

Cons:

- slightly larger compose/deploy change set

### Option C: Aggressive app-layer widening

Pros:

- maximum runtime buffer for `backend` and `celery-worker`

Cons:

- reduces safe margin for OS/page cache
- too large for a “minimal risk” first step

## Recommendation

Use **Option B**.

It matches the user’s stated goal:

- start with the simplest practical improvement
- make the current system more stable
- avoid premature architecture changes

## Testing Strategy

Use targeted config tests first:

- cloud 4C8G overlay should encode the new memory targets
- deployment startup logic should no longer start `celery-exporter` by default

Then run focused pytest coverage against the updated config assertions.

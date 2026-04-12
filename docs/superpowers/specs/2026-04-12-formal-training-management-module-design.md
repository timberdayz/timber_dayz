# Formal Training Management Module Design

**Date:** 2026-04-12
**Last Updated:** 2026-04-12

## Goal

Replace the temporary training pilot entry with a formally integrated training module in XiHong ERP, including both management-side and employee-side entry points.

## Product Positioning

The training capability should be a first-class ERP module rather than a pilot-only page. The ERP owns training management, assignment, result visibility, and employee entry. External platforms continue to own learning and exam delivery.

## Scope

This design covers:
- formal management-side training pages
- employee-side `我的培训` entry
- formal `/api/training/*` backend routes
- promotion of current pilot data into the formal module
- route, menu, and permission integration

This design does not cover:
- a custom LMS
- custom exam playback
- deep external platform sync in this iteration
- database persistence in this first formal UI/API pass

## Recommended Architecture

### Backend

Expose a formal `training` domain router with read-first APIs:
- `/api/training/overview`
- `/api/training/programs`
- `/api/training/assignments`
- `/api/training/results`
- `/api/training/my-overview`

The first implementation may continue using an in-memory/service-backed dataset so long as the route contract is formal and stable.

### Frontend

Create a formal training module with:
- management-side routes under `/training/*`
- employee-side route `/my-training`
- shared detail language and consistent ERP product styling

### Data Promotion

Current pilot summary data should be promoted into the formal service layer rather than deleted outright. The pilot route may remain temporarily for compatibility, but it must no longer be the primary entry.

## Page Structure

### Management Side

- `培训总览`
- `培训项目`
- `培训分配`
- `培训结果`

These pages should look like a real ERP operations module:
- summary cards first
- filtered lists second
- status visibility and action entry points clearly surfaced

### Employee Side

- `我的培训`
- training detail entry from employee route, and later from tasks/notifications

Employee pages should be lighter and action-driven:
- what to learn
- current status
- due date
- next action
- external learning / exam link

## UI Direction

Follow the existing ERP UI language, but increase product clarity:
- stronger first-screen hierarchy
- more deliberate status cards
- clearer action affordances
- cleaner grouping of summary, list, and detail sections

Do not turn this into a marketing page or a standalone LMS aesthetic.

## Recommended Outcome

XiHong ERP gains a formally integrated `培训管理` module with both management and employee entry points, while preserving the external learning-platform strategy.

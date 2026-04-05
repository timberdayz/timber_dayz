# Main Account Session Coordination Design

**Date:** 2026-04-05

**Goal:** Eliminate same-main-account concurrent collection failures by introducing a main-account-level session coordination model that serializes shared-state operations while preserving safe downstream concurrency.

## 1. Background

The current collection runtime already uses `main_account_id` as the session owner for formal collection and component testing. That fixed the earlier shop-scoped session duplication problem, but it also exposed a new class of failures:

- multiple shop tasks under the same main account can start at the same time
- each task loads the same main-account session state
- each task then independently enters login and shop-context preparation
- shared-state operations can race

Observed evidence from the latest Shopee failures:

- two shop tasks under `chenewei666:main` started almost simultaneously
- both reused the same main-account session
- both failed during the login component stage
- failure screenshots showed the seller shell was already open, meaning the issue was not simple network timeout or inability to reach the platform

This means the current runtime boundary is too coarse:

- session ownership is already main-account scoped
- but shared-state execution is still task-local and concurrent

That combination is unstable.

## 2. Core Principle

The system must distinguish between two execution phases:

1. **Shared-state phase**
   Includes:
   - login
   - session refresh
   - shop switching
   - target shop readiness confirmation

2. **Task-private phase**
   Includes:
   - data-domain navigation
   - export
   - download
   - file processing

The shared-state phase must be serialized per `platform + main_account_id`.
The task-private phase may remain concurrent.

## 3. Final Ownership Model

### 3.1 Main Account Owns Authentication State

The following remain owned by `main_account_id`:

- session storage state
- persistent browser profile
- device fingerprint identity
- refresh authority for platform authentication

### 3.2 Shop Account Owns Collection Intent

The following remain owned by shop account:

- collection config
- collection coverage
- collection task identity
- collection history
- target shop context

This preserves the current business model:

- main account manages platform identity
- shop account remains the final collection object

## 4. Main Account Session Coordinator

Introduce a platform-agnostic coordinator:

`MainAccountSessionCoordinator`

Its only job is to coordinate shared-state access for the same main account.

### 4.1 Lock Key

Lock by:

- `platform`
- `main_account_id`

Example keys:

- `shopee:chenewei666:main`
- `miaoshou:miaoshou_real_001`
- `tiktok:foo@example.com`

Different main accounts may proceed concurrently.
The same main account must serialize shared-state preparation.

### 4.2 Lock Scope

The lock covers:

1. validating whether the current main-account session is still usable
2. refreshing login if needed
3. landing in an authenticated platform shell
4. switching into the task’s target shop context
5. confirming the target shop page is stable and ready

The lock does **not** cover:

- domain exports
- file downloads
- file registration
- downstream task processing

### 4.3 Single-Writer Session Policy

Only code running inside the main-account coordinator lock may write:

- storage state
- persistent profile state
- refreshed authentication artifacts

All task-private execution outside the lock must treat session state as read-only.

## 5. Execution Flow

## 5.1 Revised Runtime Phases

Each collection task becomes:

1. **Main-account session preparation**
2. **Target-shop readiness**
3. **Domain collection**

### Phase 1: Main-Account Session Preparation

Inside the lock:

- load current main-account session
- check whether login is still valid
- if invalid, run login
- save refreshed session

### Phase 2: Target-Shop Readiness

Still inside the lock:

- derive the target shop context from the shop account
- execute platform-specific shop switching if needed
- confirm the task is now operating in the correct shop
- confirm the page is ready for collection

### Phase 3: Domain Collection

Outside the lock:

- continue using a task-private browser context
- execute exports and file handling
- allow concurrency with other tasks

## 5.2 Example

For two shops under the same main account:

- Task A acquires the main-account lock
- Task A validates or refreshes the shared login state
- Task A switches to Shop A
- Task A confirms Shop A is ready
- Task A releases the lock and starts exporting
- Task B then acquires the same main-account lock
- Task B reuses the latest session
- Task B switches to Shop B
- Task B confirms Shop B is ready
- Task B releases the lock and starts exporting

This preserves concurrency where it is safe while removing concurrency where it is unsafe.

## 6. Login Entry Rules

## 6.1 Login Must Be Shop-Neutral

`main_account.login_url` must no longer encode a specific shop context.

Login should only enter:

- platform login page
- platform seller shell
- authenticated platform home

It must not encode:

- `shop_id`
- `cnsc_shop_id`
- any other store-specific context parameter

### Why

If a main-account login URL already points at one concrete shop, all tasks under that main account inherit the wrong starting context.

That is especially dangerous under concurrency.

## 6.2 Shop Context Must Be Derived From Shop Account Records

Shop-specific runtime context should come from shop account data such as:

- `shop_account_id`
- `platform_shop_id`
- `shop_region`
- platform-specific identifiers

This should happen after login, not during login.

## 7. Responsibility Split

## 7.1 Login Component

The login component should only answer:

> Has the runtime entered a valid authenticated platform shell?

It should not be responsible for proving the final target shop is ready.

## 7.2 Shop Switch Component

The shop-switch component should only answer:

> Has the runtime switched into the requested target shop?

## 7.3 Readiness Gate

The readiness gate should answer:

> Is the current task now inside the correct shop and on a stable, collectable page?

These responsibilities must remain separate.

## 8. Status Model

The task status or step model must make shared-state waiting visible.

Recommended task-facing intermediate states or step labels:

- `waiting_for_main_account_session`
- `preparing_main_account_session`
- `switching_target_shop`
- `target_shop_ready`

Even if the persisted status field remains limited, the current-step messaging must expose this clearly in the task UI.

## 9. Backend Scope

This phase should modify only the runtime boundary needed for stability:

- `executor_v2`
- task step/status reporting
- login entry derivation
- shop-switch and readiness sequencing
- session write rules

This phase should **not** include:

- collection config model redesign
- coverage model redesign
- template system changes
- scheduler redesign
- full per-platform component rewrites

## 10. Rollout Strategy

Implement in phases:

1. add coordinator and same-main-account lock behavior
2. split shared-state phase from task-private phase in executor runtime
3. remove shop-specific login URL usage
4. re-sequence login -> shop switch -> readiness gate
5. expose waiting/preparing states in task UI
6. verify with same-main-account concurrent multi-shop tasks

## 11. Testing Strategy

### Backend Runtime Tests

Add tests for:

- same-main-account tasks waiting on the same lock
- different main accounts proceeding concurrently
- session writes happening only inside the lock
- shop switching occurring after login and before export
- no direct use of shop-specific login URLs in formal collection

### Contract Tests

Add tests for:

- visible waiting/current-step transitions
- stable per-task status after lock release

### Manual Validation

Manual validation should include:

- same-main-account two-shop concurrent Shopee collection
- same-main-account multi-shop Miaoshou collection
- same-main-account multi-shop TikTok collection

## 12. Recommendation

The recommended solution is:

- serialize same-main-account shared-state preparation
- keep downstream per-task collection concurrent
- make login shop-neutral
- make shop selection explicit and post-login

This is the minimal architecture change that actually addresses the root cause instead of patching one platform at a time.

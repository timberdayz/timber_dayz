# Collection Runtime Session Unification Design

**Date:** 2026-04-13

## Goal

Unify component testing and formal collection execution onto the same runtime session model so that stable persistent-session behavior in component tests also becomes the default behavior for real collection tasks.

The immediate business goal is to eliminate the current runtime split:

- component tests can reuse long-lived account sessions and only re-login when the login gate is no longer ready
- formal collection tasks still primarily rely on `storage_state + new_context()`
- the same account therefore behaves differently between "tested" and "actually collected"

## Problem Statement

The repository currently has two different runtime session models.

### Component test runtime

The component tester in [`tools/test_component.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/tools/test_component.py) already has stable session-oriented behavior:

- it resolves a session owner (`main_account_id`) for shop-account execution
- it can open a persistent Playwright context via `launch_persistent_context(...)`
- it probes the login gate before deciding whether login is needed
- when the gate is not ready, it runs the login component and saves the refreshed session
- non-login component tests therefore behave like "reuse session first, login only if actually needed"

### Formal collection runtime

The collection executor in [`modules/apps/collection_center/executor_v2.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/executor_v2.py) only partially aligns with that model:

- it resolves the same session owner
- it loads saved `storage_state`
- if no `storage_state` is available, it bootstraps one from a persistent profile
- but the actual runtime still opens a fresh `browser.new_context(...)`

This means the formal collection runtime treats persistent profiles as an input artifact rather than the primary runtime context.

## Why This Causes Real Failures

For low-risk flows, `storage_state` can be close enough to a persistent profile.

For real production collection flows, especially login-sensitive and risk-sensitive sites, `storage_state` is weaker than a live persistent profile because it does not guarantee continuity for all browser-managed state. In practice this produces the current mismatch:

- component test says session reuse is healthy
- formal collection opens a fresh context anyway
- the platform falls back to login or verification
- operators conclude the component is unstable even though the tested runtime was not the runtime actually used in collection

This is a system-level architecture issue, not a single-platform issue.

## Constraints

- Do not redesign platform business components (`login`, `navigation`, `date_picker`, `export`) as part of this work.
- Keep existing session ownership semantics based on `main_account_id` for shop-account runs.
- Preserve existing fingerprint generation through `DeviceFingerprintManager`.
- Preserve existing session persistence through `SessionManager`.
- Keep parallel collection support, but do not let multiple concurrent workers directly share one persistent profile directory.
- Do not regress current component-test stability while aligning formal collection.

## Observed Architectural Mismatch

Today the repository has three related but different runtime assumptions:

1. component tests assume persistent profile continuity is the strongest source of truth
2. formal collection assumes `storage_state` is sufficient for the primary runtime
3. parallel collection assumes fan-out contexts are necessary for throughput

The mismatch is not in business steps. It is in runtime entry semantics.

As long as those semantics remain split, the repository will continue to produce this failure pattern:

- "the component is stable in tests"
- "the collection task still re-enters login"
- "operators suspect platform-specific bugs even when the main problem is runtime divergence"

## Options Considered

### Option A: Keep the current executor and tune timeouts/platform-specific login logic

This is the smallest patch but the wrong abstraction.

Trade-offs:

- lowest short-term churn
- continues duplicating fixes across `shopee`, `tiktok`, and `miaoshou`
- does not make the tested runtime equal the production runtime
- future platform issues will continue to reappear under different labels

### Option B: Copy the component tester's persistent-session logic directly into the collection executor

This improves runtime alignment, but only temporarily.

Trade-offs:

- faster than a full architectural cleanup
- still leaves two owners of runtime session behavior
- future fixes will drift again between test and collection code
- hard to maintain and reason about

### Option C: Introduce a shared runtime session layer and make both component tests and formal collection consume it

This addresses the root cause.

Trade-offs:

- moderate refactor cost
- establishes one canonical runtime model
- keeps platform business components simpler
- makes future session/login fixes land once instead of twice

**Recommendation:** Option C.

## Design Summary

Introduce a shared runtime session layer for collection-related browser execution.

This layer must become the only place that decides:

- which account owns the session
- whether runtime should start from a persistent profile or a `storage_state`
- how Playwright context options are derived from account fingerprint
- how login-gate probing is performed before login
- when automatic login should run
- how refreshed session state is persisted after login

Business components should no longer care whether the runtime came from:

- an already-authenticated persistent profile
- a session cache
- or a login refresh

They should receive a ready runtime page and execute only their domain behavior.

## Target Architecture

### New Shared Module

Create a new module:

- [`modules/apps/collection_center/runtime_session.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/apps/collection_center/runtime_session.py)

This module owns runtime-session orchestration for both:

- formal collection tasks
- component tests

### Responsibilities of `runtime_session.py`

The module should provide a small set of explicit functions or classes:

- resolve session scope from shop account and main account
- build fingerprint-backed Playwright context options
- open a persistent runtime context using `launch_persistent_context(...)`
- open a `storage_state`-backed runtime context using `new_context(...)`
- probe login readiness on a page before login
- run login recovery in the same runtime context when the gate is not ready
- persist refreshed session state after successful login
- export a fresh `storage_state` snapshot when parallel fan-out is required

### Runtime Modes

The repository should explicitly distinguish two runtime modes:

1. `persistent_profile`
2. `storage_state_fanout`

These are not equivalent and should no longer be hidden behind one generic "session reuse" label.

## Canonical Runtime Rules

### Rule 1: Sequential collection uses `persistent_profile`

For a normal non-parallel collection task:

1. resolve session owner
2. open the account's persistent profile
3. probe login gate
4. if gate is ready, skip login
5. if gate is not ready, run the login component in the same persistent context
6. continue `navigation -> date_picker -> export` in the same persistent context

This makes formal collection match the strongest current test behavior.

### Rule 2: Parallel collection uses `persistent_profile` only for the shared login phase

Parallel collection cannot allow multiple concurrent workers to directly mutate the same profile directory.

For `parallel_mode=True`:

1. open the account persistent profile
2. probe login gate
3. if needed, complete login in that persistent context
4. snapshot fresh `storage_state`
5. close the persistent context
6. create per-domain fan-out contexts with `new_context(storage_state=...)`

So parallel fan-out remains supported, but the fragile login phase still uses the stronger runtime model.

### Rule 3: `storage_state` is a derived cache, not the primary runtime

`storage_state` should remain useful for:

- parallel fan-out
- explicit fallback paths
- quick compatibility checks

But it should no longer be the default runtime for formal sequential collection.

## Shared Login-Gate Contract

The runtime session layer should own the login-gate contract used by both component tests and collection tasks.

Required behavior:

- if a page opened from a persistent profile already satisfies the login gate, no automatic login runs
- if the page instead shows the login form or fails login-gate readiness, the runtime invokes the stable login component
- after successful login, refreshed session state is persisted
- the next task/test therefore benefits from the updated authenticated session

This is the key behavior that users already observe as stable in component tests and need in formal collection.

## Integration Changes

### `tools/test_component.py`

The component tester should stop carrying its own partial runtime-session implementation once the shared module exists.

It should delegate to the shared runtime session layer for:

- session-owner resolution
- persistent runtime opening
- `storage_state` fallback opening
- login-gate probing
- session persistence after login

This reduces future drift.

### `executor_v2.py`

The collection executor should stop constructing the sequential runtime from:

- `storage_state`
- `new_context()`

for the primary collection path.

Instead:

- sequential collection should request a persistent-profile runtime bundle
- parallel collection should request a persistent-profile login bundle followed by a `storage_state` fan-out bundle

### Session and Fingerprint Utilities

Existing utilities remain authoritative:

- [`modules/utils/sessions/session_manager.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/utils/sessions/session_manager.py)
- [`modules/utils/sessions/device_fingerprint.py`](/F:/Vscode/python_programme/AI_code/xihong_erp/modules/utils/sessions/device_fingerprint.py)

This design does not replace them. It reuses them through a canonical orchestration layer.

## Failure Classification Improvements

This design should also make runtime failures easier to understand.

Instead of collapsing all session-related issues into "had to login again", the runtime layer should make it explicit whether the failure happened because:

- persistent profile was unavailable
- persistent profile was available but login gate was not ready
- automatic login failed inside the persistent runtime
- parallel fan-out could not derive a valid `storage_state`

That classification reduces wasted platform-specific debugging.

## Testing Strategy

Required coverage for the shared runtime layer:

1. sequential runtime opens persistent profile directly when a session owner exists
2. sequential runtime skips login when login gate is already ready
3. sequential runtime runs login when the gate is not ready
4. sequential runtime saves refreshed session after login
5. parallel runtime performs login in persistent context and then snapshots `storage_state`
6. parallel runtime fans out domain contexts from the refreshed `storage_state`
7. component tester and collection executor both call the shared runtime layer instead of maintaining separate session orchestration

Required non-regression coverage:

- existing login-gate contract tests still pass
- existing collection executor session tests still pass after refactor
- existing component tester gate tests still pass after refactor

## Migration Order

Recommended order:

1. create the shared runtime session module
2. move session-scope resolution and context-opening logic into that module
3. switch sequential collection runtime to `persistent_profile`
4. switch parallel login phase to `persistent_profile -> storage_state_fanout`
5. update component tester to consume the same shared module
6. remove duplicated runtime session helpers from `tools/test_component.py` and `executor_v2.py` where possible
7. run targeted verification for both component tests and formal collection session paths

## Explicit Non-Goals

This design does not:

- redesign any platform business component selectors
- replace the current login component architecture
- change the shop-account/main-account domain model
- eliminate `storage_state` entirely
- attempt direct profile sharing across multiple concurrent workers

## Final Recommendation

The repository should stop treating persistent profiles as an optional session bootstrap detail.

They should become the canonical runtime for real sequential collection tasks.

The correct long-term model is:

- sequential collection: `persistent_profile`
- parallel collection: `persistent_profile` for login, then `storage_state_fanout`
- component tests: same shared runtime layer, not a separate runtime implementation

This is the smallest architectural change that turns "component tests are stable" into "formal collection behaves the same way".

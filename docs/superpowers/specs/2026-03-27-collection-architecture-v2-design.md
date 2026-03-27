# Collection Architecture V2 Design

## Goal

Build a new collection architecture that treats `pwcli + agent` as the default development workflow, freezes legacy component structures, and converges future collection work onto a simpler, more stable Python component model.

This design assumes:

- Old collection components are no longer the source of truth for new work
- New collection development should optimize for simplicity, stability, and debuggability
- `pwcli` is used to explore live pages and collect evidence
- Formal runtime continues to execute Python async components only

## Non-Goals

- This design does not immediately delete all legacy files
- This design does not redesign the data sync path in the same phase
- This design does not migrate output paths in the same phase

Legacy assets may remain on disk temporarily, but they should stop participating in the default development and runtime path.

---

## 1. Core Direction

The current architecture contains migration-era complexity:

- one logical component may involve canonical alias files, recorder-generated files, and versioned runtime files
- component testing, formal collection, and recorder output use different parameter shapes
- canonical registration depends on curated file allowlists
- old large exporter files still carry cross-domain and cross-era fallback logic

With `pwcli + agent`, page discovery is no longer the bottleneck. The architecture should therefore stop optimizing for "record once, patch forever" and instead optimize for:

- single-purpose components
- explicit runtime contracts
- evidence-driven selector and state design
- minimal compatibility layers

The V2 principle is:

> A logical component should have one canonical source file, one stable runtime contract, and one testing model.

---

## 2. V2 File Topology

### 2.1 Canonical source files

Future-maintained components live only under:

`modules/platforms/<platform>/components/`

Each logical component keeps exactly one canonical source file:

- `login.py`
- `navigation.py`
- `date_picker.py`
- `shop_switch.py`
- `filters.py`
- `orders_export.py`
- `products_export.py`
- `analytics_export.py`
- `finance_export.py`
- `services_export.py`

Not every platform needs every slot, but if a slot exists, it should use this naming convention.

### 2.2 Versioned runtime files

Versioned files may still exist because component version management requires a stable file path per saved version, for example:

- `login_v1_0_3.py`
- `orders_export_v1_0_0.py`

These files are runtime artifacts, not primary maintenance entrypoints.

### 2.3 Files that should stop being primary maintenance targets

These should be treated as archive or compatibility-only:

- recorder-only intermediate implementations such as `miaoshou_login.py`
- legacy monolithic exporters carrying historical fallback logic across domains
- direct YAML-era compatibility shells
- helper/config/tool files presented as if they were logical components

If they remain temporarily, they must not be the default file a developer edits for new work.

---

## 3. Component Boundaries

### 3.1 Required top-level logical units

Every platform should converge to the same logical component boundary model:

- `login`
- `navigation`
- `date_picker`
- `shop_switch`
- `filters`
- domain-specific `*_export`

### 3.2 Export components remain container components

An export component is still the formal runtime container for a domain flow, but it should call or embed well-bounded helpers rather than becoming a monolith.

Canonical export flow shape:

1. `wait_navigation_ready()`
2. `ensure_subtype_selected()` if needed
3. `ensure_popup_closed()`
4. `ensure_time_selected()`
5. `ensure_filters_applied()`
6. `click_search()`
7. `wait_search_results_ready()`
8. `ensure_export_menu_open()`
9. `click_export_target()`
10. `wait_export_progress_ready()` if applicable
11. `wait_export_complete()`

### 3.3 Shared rule for internal method naming

All new formal components should converge on:

- `detect_*` for read-only observation
- `ensure_*` for state-changing convergence
- `wait_*` for completion confirmation

This rule applies across all platforms.

---

## 4. Runtime Contract

### 4.1 Single execution context shape

Formal runtime should pass one stable config model to all components. New work should treat this as the source of truth:

- `platform`
- `account`
- `data_domain`
- `sub_domain`
- `granularity`
- `time_selection`
- `task.download_dir`
- `task.screenshot_dir`

### 4.2 Time selection model

Time interaction must be unified across testing, formal collection, script generation, and component runtime:

```json
{
  "time_selection": {
    "mode": "preset",
    "preset": "today"
  }
}
```

or

```json
{
  "time_selection": {
    "mode": "custom",
    "start_date": "2026-03-01",
    "end_date": "2026-03-31",
    "start_time": "00:00:00",
    "end_time": "23:59:59"
  }
}
```

### 4.3 Global hard mapping between preset and granularity

This mapping is global and non-overridable:

- `today` -> `daily`
- `yesterday` -> `daily`
- `last_7_days` -> `weekly`
- `last_30_days` -> `monthly`

For `custom`, `granularity` must be explicitly provided by the caller.

### 4.4 Keep `granularity`, but narrow its responsibility

`granularity` remains required for:

- output naming
- ingest classification
- scheduled collection intent
- downstream page/data use

It should no longer decide which page-side date interaction to execute.

---

## 5. Testing Model

### 5.1 `pwcli` is development-only

`pwcli` belongs to the development path:

- page exploration
- evidence capture
- hover/menu/dialog inspection
- selector discovery

It should not become part of formal runtime execution.

### 5.2 Formal component testing

Component testing should follow one chain:

1. `pwcli` explores the live page
2. agent designs component structure
3. canonical Python component is updated
4. local component test validates behavior
5. component version management tests the registered component
6. stable version promotion happens only after evidence

### 5.3 Test UI contract

The component test UI should not expose conflicting time inputs. It must present:

- preset mode with fixed preset choices
- custom mode with manual date range and manual granularity

This is a UI expression of the same runtime contract, not a separate model.

---

## 6. Registration and Version Management

### 6.1 Replace hardcoded component allowlists over time

The current file allowlist model is acceptable as a short-term migration gate but not as the long-term V2 design.

Long-term registration rule:

- fixed logical component filenames auto-register:
  - `login.py`
  - `navigation.py`
  - `date_picker.py`
  - `shop_switch.py`
  - `filters.py`
- domain exporters auto-register:
  - `*_export.py`

Exclude:

- `*_config.py`
- `overlay_guard.py`
- registry/helper files
- temporary compatibility wrappers

### 6.2 Stable runtime remains version-based

Runtime may still resolve to stable versioned files, but the maintenance source of truth should remain the canonical source file.

This yields a clean two-layer model:

- canonical maintenance file
- stable/runtime file path

V2 explicitly rejects a third permanent compatibility layer.

---

## 7. Legacy Strategy

### 7.1 Freeze legacy files

Legacy components should be marked as:

- archive-only
- compatibility-only
- not a default maintenance target

### 7.2 No new work on monolithic legacy exporters

Do not add new business logic to historical monoliths such as old cross-domain `export.py` files when a domain-specific component can be created instead.

### 7.3 Migrate by slot, not by file count

Migration order should be by logical slot:

1. login
2. orders export
3. products export
4. analytics export
5. finance export
6. services export

Each slot should become independently maintainable.

---

## 8. Recommended First Execution Order

The first V2 migration wave should focus on the highest-value paths:

1. `miaoshou/login`
2. `miaoshou/orders_export`
3. `shopee/login`
4. `shopee/orders_export`
5. `tiktok/login`
6. `tiktok/orders_export`

These are enough to validate the architecture before migrating every other domain.

---

## 9. Decision Summary

V2 should standardize on:

- one canonical file per logical component
- one stable runtime contract
- one time selection model
- one formal test model
- one registration rule model

The architecture should explicitly prefer:

- fewer layers
- fewer hidden compatibility behaviors
- fewer fallback-only branches
- more evidence-driven state handling

The new default development path becomes:

`pwcli exploration -> agent analysis -> canonical Python component -> local verification -> version management test -> stable`

This design intentionally treats old collection structures as migration baggage rather than a foundation for future work.

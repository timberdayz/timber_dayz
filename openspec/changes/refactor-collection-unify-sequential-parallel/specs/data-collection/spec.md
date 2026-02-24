# 数据采集能力 - 执行器修复与架构简化 变更增量

## ADDED Requirements

### Requirement: 顺序与并行采集 SHALL 使用同一套组件执行模型
Sequential and parallel collection execution SHALL use the same component execution model so that behavior is consistent and dual maintenance is avoided. Only concurrency strategy and browser context allocation MAY differ (e.g. sequential uses one page; parallel uses multiple contexts with shared storage_state).

#### Scenario: Phase 1 — Sequential execution uses adapter
- **WHEN** a collection task runs in sequential mode (one page, one context) and the system has not yet migrated to CollectionRunner
- **THEN** the executor SHALL create a PythonComponentAdapter via create_adapter(platform, account, config) and SHALL execute login via adapter.login(page) and export via adapter.export(page, data_domain)
- **AND** config SHALL contain at least task (including task.download_dir for file output path), params, account, and platform so that components read domain-level parameters (e.g. date_range, granularity, data_domain) from config, not as a separate params argument to export
- **AND** the executor SHALL NOT use component_loader.load for login or export in the sequential path

#### Scenario: Phase 1 — Parallel execution uses same adapter model
- **WHEN** a collection task runs in parallel mode (multiple domains in parallel contexts with shared login state) and the system has not yet migrated to CollectionRunner
- **THEN** the executor SHALL use the same PythonComponentAdapter and Python components for login and for each domain export (adapter.login(page) and adapter.export(page, data_domain))
- **AND** for each domain export, the executor SHALL create an adapter with config containing that domain's parameters, or otherwise ensure config is available to the component via the adapter's context
- **AND** the executor SHALL NOT use component_loader.load for login or export in the parallel path
- **AND** only the concurrency (e.g. asyncio.gather per batch) and browser context allocation (one context per domain with storage_state) SHALL differ from sequential mode

#### Scenario: Phase 2 — CollectionRunner and convention-based script loading
- **WHEN** a collection task runs (sequential or parallel) after migration to CollectionRunner
- **THEN** the runner SHALL load login and export scripts by convention from a defined directory (e.g. `modules/platforms/{platform}/components/` where platform SHALL correspond 1:1 to the directory name, or any mapping SHALL be done by the caller before invoking the runner; `login.py` and `{domain}_export.py`; when sub_domains exist, either `{domain}_{sub_domain}_export.py` or the same `{domain}_export.py` with sub_domain in config)
- **AND** the runner SHALL invoke the component contract: login SHALL return a result that indicates success or failure (e.g. `{ success: bool, message?: str }` or AdapterResult); export SHALL be either a callable `run(page, account, config)` or a class instance with a `run` method (for backward compatibility)
- **AND** config SHALL include step_callback (and optional task_id) so that scripts MAY report sub-step details for observability; domain-level parameters (date_range, granularity, data_domain, sub_domain) SHALL be supplied via config
- **AND** in parallel mode the runner SHALL save storage_state after successful login and SHALL use it when creating context/page for each domain export; when run() throws an exception the runner SHALL record that domain in failed_domains and continue with other domains (retry per runner policy)
- **AND** the runner SHALL NOT rely on PlatformAdapter._export_map or get_export(domain) for the main collection flow; the runner SHALL discover and invoke scripts directly
- **AND** when no script exists for a requested domain (or domain+sub_domain), the runner SHALL record that domain in failed_domains and continue with other domains, or SHALL perform a prior capability check and only execute domains that have a script

#### Scenario: Single maintenance surface for components
- **WHEN** a platform adds or updates a login or export component
- **THEN** the change SHALL apply to both sequential and parallel execution without separate code paths for component_loader vs adapter (Phase 1) or without duplicate adapter layers (Phase 2: runner loads scripts by convention; no _export_map).

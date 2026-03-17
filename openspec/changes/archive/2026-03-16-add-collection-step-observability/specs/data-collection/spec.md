# 数据采集能力 - 步骤可观测与组件契约变更增量

## ADDED Requirements

### Requirement: 采集任务步骤 SHALL be logged and progress SHALL be persisted during execution
The system SHALL record step-level logs during collection task execution and SHALL persist task progress (current step, progress percentage) so that operators can see which step succeeded or failed without relying only on server logs or the final error_message.

#### Scenario: Step-level log written during execution
- **WHEN** a collection task runs (login, export per data domain, file processing)
- **THEN** the executor or injected callback SHALL write records to the task log store (e.g. CollectionTaskLog) at key step boundaries (e.g. login start/end, export start/end per domain, file processing start/end)
- **AND** each log record SHALL include at least a human-readable message and SHALL include structured details (e.g. step_id, component, data_domain, success, duration_ms, error) where available
- **AND** failed steps SHALL be logged with level error and SHALL include the error reason in message or details

#### Scenario: Task progress persisted during execution
- **WHEN** the executor updates progress (e.g. via status_callback)
- **THEN** the task record (e.g. CollectionTask) SHALL be updated with current_step and progress (and optionally updated_at) so that clients polling the task see the latest step and percentage
- **AND** the callback or logging SHALL be injected when the executor is created in the background task so that progress is not only in-memory

#### Scenario: Task detail shows step timeline
- **WHEN** a user opens the task detail view for a collection task (by task_id)
- **THEN** the UI SHALL display a timeline of steps derived from the task logs (e.g. CollectionTaskLog for that task_id, ordered by timestamp)
- **AND** each step SHALL show at least timestamp, message, and success/failure; if details contain step_id or component, the UI MAY display them as step names
- **AND** failed steps MAY be highlighted and MAY show details.error when expanded

### Requirement: Collection component run() SHALL be async and use async Playwright API
All collection components (Login, Export, Navigation, DatePicker) SHALL implement run() as async (async def run(...)) and SHALL use the async Playwright API (e.g. await page.goto) so that the adapter and executor can consistently await component.run(page) without blocking or type errors.

#### Scenario: Base classes declare async run
- **WHEN** a developer implements a new platform component (e.g. Login, Export)
- **THEN** the base class (LoginComponent, ExportComponent, etc.) SHALL define run() as async def run(...) and SHALL document that implementations MUST be async
- **AND** implementations SHALL use await for page and context operations (e.g. await page.goto, await page.wait_for_timeout)

#### Scenario: Adapter awaits component run
- **WHEN** the Python component adapter invokes login(page), export(page, data_domain), or similar
- **THEN** it SHALL call await component.run(page) (or equivalent) so that all platforms are invoked in the same way
- **AND** no platform component SHALL implement a synchronous run() that returns a result without being async, to avoid await on a non-coroutine

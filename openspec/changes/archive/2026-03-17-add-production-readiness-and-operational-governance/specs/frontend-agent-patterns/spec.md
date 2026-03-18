## ADDED Requirements

### Requirement: Frontend Code Patterns Document
The system SHALL maintain `docs/DEVELOPMENT_RULES/FRONTEND_CODE_PATTERNS.md` as the single source of truth for frontend development templates.

#### Scenario: FRONTEND_CODE_PATTERNS.md contains required templates
- **GIVEN** `FRONTEND_CODE_PATTERNS.md` exists
- **THEN** it SHALL contain at minimum the following templates:
  - Async-friendly API function template
  - Pinia store template
  - List page template
  - Form page template
  - Permission button template (using `hasPermission()` function + `v-if` pattern, which is the project's actual approach)
  - Partial loading template
  - Background refresh template

### Requirement: API Layer Encapsulation
All frontend API calls MUST go through `frontend/src/api/*.js`. Pages and components MUST NOT use `axios` directly.

#### Scenario: Direct axios usage prohibited
- **WHEN** a Vue component calls `axios.get()` or `axios.post()` directly
- **THEN** it SHALL be flagged as a rule violation and MUST be refactored to use an API function

### Requirement: Store State Mutation
Pinia store state MUST only be modified within `actions` or via `$patch()`. Direct state mutation outside actions is prohibited. Note: although Pinia natively allows direct state mutation (unlike Vuex), this project enforces this stricter convention for consistency, traceability, and easier debugging across a multi-Agent development team.

#### Scenario: State mutation outside actions
- **WHEN** a component directly modifies `store.someState = newValue` outside of a store action or `$patch()` call
- **THEN** it SHALL be flagged as a project convention violation

#### Scenario: State mutation via $patch
- **WHEN** a component needs to update multiple state fields atomically
- **THEN** it SHOULD use `store.$patch({ field1: value1, field2: value2 })` within an action

### Requirement: Unified List Page Pattern
All list pages MUST follow the unified query/pagination/filter/loading pattern defined in `FRONTEND_CODE_PATTERNS.md`. New list pages MUST use the template. Existing list pages SHOULD be migrated when modified.

#### Scenario: New list page uses template
- **WHEN** a developer creates a new list page
- **THEN** it MUST follow the template in `FRONTEND_CODE_PATTERNS.md` with unified pagination, filter state management, and partial loading


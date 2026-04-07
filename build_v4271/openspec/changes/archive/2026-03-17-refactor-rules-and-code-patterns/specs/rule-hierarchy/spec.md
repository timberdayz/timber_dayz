## ADDED Requirements

### Requirement: Three-Layer Rule Hierarchy
The project SHALL maintain a three-layer rule file hierarchy with clear separation of concerns. Each layer has a defined purpose and content boundary. Cross-duplication between layers is prohibited.

#### Scenario: L1 Quick Entry (CLAUDE.md)
- **GIVEN** `CLAUDE.md` serves as the L1 quick entry layer
- **THEN** it SHALL contain ONLY: command cheat sheet, one-screen architecture overview, and document navigation links
- **AND** it SHALL NOT contain development rules, code templates, or zero-tolerance rules
- **AND** its total length SHALL NOT exceed 150 lines

#### Scenario: L2 Development Rules (.cursorrules)
- **GIVEN** `.cursorrules` serves as the L2 development rules layer
- **THEN** it SHALL contain ONLY: zero-tolerance rules, architecture constraints, and one-line pointers to L3 documents
- **AND** it SHALL NOT contain code templates, historical narratives, or star-rating markers
- **AND** its total length SHALL NOT exceed 300 lines after V1 completion (subsequent approved changes MAY add up to 10 lines of pointers, soft cap 310 lines)

#### Scenario: L3 Detailed Reference (docs/DEVELOPMENT_RULES/)
- **GIVEN** `docs/DEVELOPMENT_RULES/` serves as the L3 detailed reference layer
- **THEN** it SHALL contain at minimum 7 core thematic files: `API_AND_CONTRACTS.md`, `DATABASE.md`, `TESTING_AND_QUALITY.md`, `ERROR_AND_LOGGING.md`, `SECURITY_AND_DEPLOYMENT.md`, `UI_DESIGN.md`, `CODE_PATTERNS.md`
- **AND** additional extension files MAY be added by later approved OpenSpec changes (for example production governance or frontend-specific guides)
- **AND** each file SHALL be self-contained for its topic without requiring cross-reference to other L3 files for basic understanding
- **AND** a `README.md` index SHALL list all files with one-line descriptions

### Requirement: CODE_PATTERNS.md as Template Repository
The system SHALL maintain `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md` as the single source of truth for code templates that Agent can copy when creating new files.

#### Scenario: CODE_PATTERNS.md contains required templates
- **GIVEN** `CODE_PATTERNS.md` exists in `docs/DEVELOPMENT_RULES/`
- **THEN** it SHALL contain at minimum the following templates:
  - AsyncCRUDService subclass template
  - Router file template (with response_model, Depends injection)
  - Schema file template (request + response models)
  - conftest.py fixture usage template
  - Transaction management pattern (decorator + savepoint)
  - Cache-aside pattern
  - Optimistic locking pattern
  - Dependency injection factory function pattern

#### Scenario: .cursorrules references CODE_PATTERNS.md
- **GIVEN** `.cursorrules` contains zero-tolerance rules
- **THEN** it SHALL include a directive: "Before creating a new Service, Router, or Schema file, consult `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`"

### Requirement: Rule Completeness Verification
The system SHALL provide a verification script that validates `.cursorrules` contains all required zero-tolerance rule keywords.

#### Scenario: Verify rules after simplification
- **WHEN** `python scripts/verify_rules_completeness.py` is executed
- **THEN** it SHALL check `.cursorrules` for the presence of all critical keywords (e.g., "schema.py", "get_async_db", "response_model", "emoji", "SSOT", "Contract-First", "AsyncCRUDService")
- **AND** it SHALL report any missing keywords with severity level

### Requirement: No Star-Rating Markers
The `.cursorrules` file SHALL NOT contain star-rating markers in any form.

#### Scenario: Star markers prohibited
- **WHEN** `.cursorrules` is validated
- **THEN** it SHALL NOT contain any of the following patterns: emoji stars, `[*]`, `[**]`, `[***]`, `[****]`, `[*****]`

### Requirement: Error Code SSOT in Documentation
The `ERROR_AND_LOGGING.md` file SHALL reference `backend/utils/error_codes.py` as the single source of truth for error code definitions. It SHALL NOT duplicate specific error code values.

#### Scenario: Error code documentation
- **GIVEN** `ERROR_AND_LOGGING.md` describes the error code system
- **THEN** it SHALL explain the error code categorization (1xxx system, 2xxx business, 3xxx data, 4xxx user)
- **AND** it SHALL state "See `backend/utils/error_codes.py` for the authoritative list of error codes"
- **AND** it SHALL NOT enumerate individual error code values (to avoid SSOT violation)

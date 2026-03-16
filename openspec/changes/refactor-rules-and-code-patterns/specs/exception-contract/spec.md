## ADDED Requirements

### Requirement: Unified Exception Hierarchy (SSOT)
The system SHALL maintain a single exception hierarchy rooted at `ERPException` (defined in `modules/core/exceptions.py`). API-layer exceptions SHALL be defined in `backend/utils/exceptions.py` as subclasses of `ERPException`. No parallel exception base class (e.g., `AppException`) SHALL be created.

#### Scenario: ERPException error_code type unification
- **GIVEN** `ERPException` currently uses `str` for `error_code`
- **WHEN** the unification is applied
- **THEN** `ERPException.error_code` SHALL accept `Union[str, IntEnum]` for backward compatibility
- **AND** all API-layer exceptions SHALL use `ErrorCode` (IntEnum from `backend/utils/error_codes.py`) exclusively

#### Scenario: API exception inherits ERPException
- **WHEN** a new API-layer exception (e.g., `NotFoundError`) is defined in `backend/utils/exceptions.py`
- **THEN** it SHALL inherit from `ERPException`
- **AND** it SHALL carry an `error_code` of type `ErrorCode` (IntEnum)
- **AND** it SHALL carry a `http_status_code` class attribute indicating the HTTP status code mapping

### Requirement: API Exception Types
The system SHALL provide the following API-layer exception types in `backend/utils/exceptions.py`:

#### Scenario: NotFoundError raises HTTP 404
- **WHEN** a Service raises `NotFoundError(error_code=ErrorCode.RESOURCE_NOT_FOUND, message="...")`
- **THEN** the global exception handler SHALL return HTTP 404 with `{"success": false, "error": {"code": <int>, "type": "NotFoundError"}, "message": "...", "timestamp": "..."}`

#### Scenario: BusinessValidationError raises HTTP 422
- **WHEN** a Service raises `BusinessValidationError(error_code=ErrorCode.VALIDATION_FAILED, message="...")`
- **THEN** the global exception handler SHALL return HTTP 422 with the standard error response body

#### Scenario: PermissionDeniedError raises HTTP 403
- **WHEN** a Service raises `PermissionDeniedError(error_code=ErrorCode.PERMISSION_DENIED, message="...")`
- **THEN** the global exception handler SHALL return HTTP 403 with the standard error response body

#### Scenario: ConflictError raises HTTP 409
- **WHEN** a Service raises `ConflictError(error_code=ErrorCode.DUPLICATE_ENTRY, message="...")`
- **THEN** the global exception handler SHALL return HTTP 409 with the standard error response body

#### Scenario: ExternalServiceError raises HTTP 502
- **WHEN** a Service raises `ExternalServiceError(error_code=ErrorCode.NETWORK_ERROR, message="...")`
- **THEN** the global exception handler SHALL return HTTP 502 with the standard error response body

#### Scenario: Unhandled ERPException returns HTTP 500
- **WHEN** an `ERPException` subclass (not an API-layer exception) propagates to the global handler
- **THEN** the system SHALL return HTTP 500 with a generic error message and log the full traceback

#### Scenario: Unhandled Python exception returns HTTP 500
- **WHEN** an unhandled Python exception propagates to the global handler
- **THEN** the system SHALL return HTTP 500 with a generic error message and log the full traceback

### Requirement: Gradual HTTP Status Code Migration
The system SHALL support a gradual migration from HTTP 200-wrapped business errors to semantic HTTP status codes, without breaking existing API consumers.

#### Scenario: error_response_v2 uses semantic status codes
- **WHEN** a new API endpoint uses the exception-based error handling
- **THEN** errors SHALL be returned with semantic HTTP status codes (404, 409, 422, etc.) via `error_response_v2()`

#### Scenario: Legacy error_response preserved
- **WHEN** an existing API endpoint uses `error_response()` with default `status_code=200`
- **THEN** it SHALL continue to return HTTP 200 with `{"success": false, ...}` response body
- **AND** no migration SHALL be forced on existing endpoints

#### Scenario: Response body format consistency
- **WHEN** either `error_response()` or `error_response_v2()` returns an error
- **THEN** the response body structure SHALL be identical: `{"success": false, "error": {"code": <int>, "type": "..."}, "message": "...", "timestamp": "..."}`
- **AND** the only difference SHALL be the HTTP status code

### Requirement: Frontend Compatibility
The exception contract SHALL remain compatible with the existing frontend Axios interceptor that handles both HTTP 200+success:false and 4xx/5xx error responses.

#### Scenario: Frontend handles semantic status codes
- **GIVEN** the frontend Axios interceptor already processes 4xx/5xx responses by parsing the standard error response body
- **WHEN** a new endpoint returns HTTP 422 with `{"success": false, "error": {...}}`
- **THEN** the frontend interceptor SHALL parse it correctly without modification

#### Scenario: Frontend handles legacy 200 errors
- **GIVEN** the frontend Axios interceptor checks `data.success === false` for HTTP 200 responses
- **WHEN** a legacy endpoint returns HTTP 200 with `{"success": false, "error": {...}}`
- **THEN** the frontend interceptor SHALL parse it correctly without modification

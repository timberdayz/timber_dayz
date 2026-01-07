## MODIFIED Requirements

### Requirement: API错误处理标准
系统 **SHALL** 提供统一的错误处理机制，包括HTTP状态码、业务错误码和错误信息格式。

#### Scenario: Metabase Question未配置错误
- **WHEN** 前端调用 Dashboard API，但 Metabase Question ID 未配置
- **THEN** 后端返回 HTTP 400 错误
- **AND** 错误响应格式：`{"success": false, "error": {"code": "QUESTION_NOT_CONFIGURED", "type": "ConfigurationError", "detail": "Question ID未配置: {question_key}。请在环境变量中设置METABASE_QUESTION_{question_key.upper()}"}, "message": "Question ID未配置", "timestamp": "..."}`
- **AND** 前端显示友好错误提示："数据源未配置，请联系管理员配置 Metabase Question"

#### Scenario: Metabase Question配置错误
- **WHEN** 前端调用 Dashboard API，但 Metabase Question ID 配置错误（如 Question 不存在）
- **THEN** 后端返回 HTTP 400 或 404 错误（根据 Metabase API 响应）
- **AND** 错误响应格式：`{"success": false, "error": {"code": "METABASE_QUERY_FAILED", "type": "ExternalServiceError", "detail": "Metabase查询失败: HTTP {status_code}"}, "message": "数据查询失败", "timestamp": "..."}`
- **AND** 前端显示友好错误提示："数据查询失败，请稍后重试"

#### Scenario: Metabase服务不可用错误
- **WHEN** 前端调用 Dashboard API，但 Metabase 服务不可用（连接超时、服务宕机等）
- **THEN** 后端返回 HTTP 503 错误
- **AND** 错误响应格式：`{"success": false, "error": {"code": "METABASE_UNAVAILABLE", "type": "ServiceUnavailableError", "detail": "Metabase服务不可用: {error_message}"}, "message": "数据服务暂时不可用", "timestamp": "..."}`
- **AND** 前端显示友好错误提示："数据服务暂时不可用，请稍后重试"，并提供"重试"按钮


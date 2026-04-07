## MODIFIED Requirements

### Requirement: API错误处理标准
系统 **SHALL** 提供统一的错误处理机制，包括HTTP状态码、业务错误码和错误信息格式。

#### Scenario: 旧 Dashboard API 已删除（Agent 友好性）
- **WHEN** Agent 或开发者尝试查找 Dashboard 相关 API
- **THEN** 系统 **SHALL** 仅提供有效的 Metabase Question API（`/api/dashboard/business-overview/*`）
- **AND** 系统 **SHALL** 不包含任何无效的旧 Dashboard API（如 `/api/dashboard/overview`、`/api/dashboard/sales-trend` 等）
- **AND** 所有无效的旧 API 调用代码已**直接删除**（不保留废弃标记）
- **AND** **原因**：避免 Agent 误解，防止 Agent 选择不存在的 API 或尝试实现已废弃的功能

#### Scenario: Metabase Question API 错误处理
- **WHEN** 前端调用 Metabase Question API，但 Question ID 未配置
- **THEN** 后端返回 HTTP 400 错误
- **AND** 错误响应格式：`{"success": false, "error": {"code": "QUESTION_NOT_CONFIGURED", "type": "ConfigurationError", "detail": "Question ID未配置: {question_key}"}, "message": "Question ID未配置"}`
- **AND** 前端显示友好错误提示："数据源未配置，请联系管理员配置 Metabase Question"

#### Scenario: Metabase 服务不可用错误处理
- **WHEN** 前端调用 Metabase Question API，但 Metabase 服务不可用（连接超时、服务宕机等）
- **THEN** 后端返回 HTTP 503 错误
- **AND** 错误响应格式：`{"success": false, "error": {"code": "METABASE_UNAVAILABLE", "type": "ServiceUnavailableError", "detail": "Metabase服务不可用: {error_message}"}, "message": "数据服务暂时不可用"}`
- **AND** 前端显示友好错误提示："数据服务暂时不可用，请稍后重试"，并提供「重试」按钮


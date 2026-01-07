## MODIFIED Requirements

### Requirement: 销售看板
系统 **SHALL** 提供实时销售看板，包含关键绩效指标（KPI）和可视化。

#### Scenario: 前端调用 Metabase Question API
- **WHEN** 前端需要获取业务概览 KPI 数据
- **THEN** 前端通过后端代理 API `/api/dashboard/business-overview/kpi` 调用 Metabase Question
- **AND** 前端使用 `frontend/src/services/metabase.js` 服务封装统一调用
- **AND** 前端在 `frontend/src/api/dashboard.js` 中提供 `queryBusinessOverviewKpi(filters)` 方法
- **AND** 前端不再调用旧的 Dashboard API（如 `/api/dashboard/overview`）

#### Scenario: 数据格式转换
- **WHEN** Metabase Question API 返回数据
- **THEN** 前端在 `metabase.js` 服务层统一进行数据格式转换
- **AND** 将 Metabase 返回的数据格式转换为前端组件期望的格式
- **AND** 处理日期格式、数字格式等转换
- **AND** 确保前端组件无需修改即可使用新 API

#### Scenario: 错误处理和降级策略
- **WHEN** Metabase Question API 调用失败（网络错误、服务不可用等）
- **THEN** 前端在顶部展示友好错误提示
- **AND** 图表区域显示占位提示（"数据加载失败，请稍后重试"）
- **AND** 提供「重试」按钮，重新拉取数据
- **AND** 可选：展示上次缓存数据（如果存在）

#### Scenario: 清理旧 API 调用（Agent 友好性）
- **WHEN** 前端代码中存在无效的旧 Dashboard API 调用
- **THEN** 系统 **SHALL** 直接删除这些无效代码（不保留废弃标记）
- **AND** 删除 `frontend/src/api/dashboard.js` 中所有调用不存在后端 API 的方法（15个方法）
- **AND** 删除 `frontend/src/stores/dashboard.js` 中对旧 API 的调用
- **AND** 删除 `frontend/src/views/Dashboard.vue` 中对旧 API 的调用
- **AND** 通过代码搜索和运行时日志确认所有旧 API 调用已完全移除
- **AND** **原因**：避免 Agent 误解，防止 Agent 选择不存在的 API 或尝试实现已废弃的功能


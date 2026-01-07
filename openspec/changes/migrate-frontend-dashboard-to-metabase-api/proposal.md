# Change: 将前端 Dashboard 迁移到 Metabase Question API

## Why

当前系统已完成 DSS 架构重构，后端已统一通过 Metabase Question 提供 Dashboard 数据，但前端仍有大量页面依赖旧的 Dashboard API 和物化视图语义层：

- `Dashboard.vue` 和多个分析页面仍调用历史 KPI 接口（如 `/api/dashboard/overview`、`/api/dashboard/calculate-metrics`）
- Dashboard 相关路由和 store 状态管理与 DSS 架构不完全匹配
- Metabase 不可用时的降级逻辑尚未在前端实现和验证

**根本原因**：DSS 架构重构完成了后端和数据库层面的改造，但前端迁移工作尚未完成，导致前后端架构不一致。

## What Changes

### 核心变更

1. **清理旧 API 依赖（最高优先级 - Agent 友好性）** ⭐⭐⭐
   - **直接删除**所有无效的旧 Dashboard API 调用代码（不保留废弃标记）
   - 删除 `frontend/src/api/dashboard.js` 中所有调用不存在后端 API 的方法（15个方法）
   - 删除 `frontend/src/stores/dashboard.js` 中对旧 API 的调用
   - 删除 `frontend/src/views/Dashboard.vue` 中对旧 API 的调用
   - **原因**：避免 Agent 误解，防止 Agent 选择不存在的 API 或尝试实现已废弃的功能
   - **验证**：通过代码搜索和运行时日志确认所有旧 API 调用已完全移除

2. **业务概览页面迁移（高优先级）**
   - 将 `Dashboard.vue` 的所有数据获取逻辑改为调用 Metabase Question 代理 API
   - 修改 `dashboard.js` store，将状态源头改为 Metabase Question 数据结构
   - 修改 `frontend/src/api/dashboard.js`，添加新的 Metabase 代理 API 调用方法

3. **其他核心分析页面迁移（中优先级）**
   - 对 Store Analytics、Sales Detail、Inventory Health 等核心分析页面，分阶段迁移到 Metabase Question API
   - 为这些页面设计对应的 Metabase Question（由 `configure-metabase-dashboard-questions` change 提供）
   - 更新组件数据获取逻辑，替换旧 API 为 Metabase Question API

4. **实现降级策略**
   - 实现 Metabase 宕机时的前端降级逻辑（错误提示 + 可选静态数据）
   - 为关键错误路径编写最小单元测试/组件测试

### 技术细节

- **前端服务封装**：
  - 创建/完善 `frontend/src/services/metabase.js`
  - 封装 `getQuestionData(questionKeyOrId, filters)`，统一调用后端 Metabase 代理 API
  - 处理加载状态、错误信息、取消请求

- **数据格式转换**：
  - Metabase Question API 返回的数据格式可能与前端组件期望的格式不一致
  - 需要在 `metabase.js` 服务层进行数据格式转换，确保前端组件无需修改

- **降级策略**：
  - Metabase 调用失败时，在顶部展示友好错误提示
  - 图表区域显示占位提示（可选：展示上次缓存数据）
  - 提供「重试」按钮，重新拉取数据

## Impact

### 受影响的规格（Affected Specs）

- **dashboard** (修改规格) - 补充前端组件与 Metabase Question API 的契约
  - 明确前端如何调用 Metabase Question API
  - 定义数据格式转换规则
  - 说明错误处理和降级策略

- **frontend-api-contracts** (修改规格) - 标记旧 Dashboard 相关 API 为废弃
  - 明确哪些 API 已废弃，不应再使用
  - 说明新 API 的行为和参数

### 受影响的代码（Affected Code）

#### 需要修改的文件
- `frontend/src/views/Dashboard.vue` - 迁移数据获取逻辑
- `frontend/src/stores/dashboard.js` - 迁移状态管理
- `frontend/src/api/dashboard.js` - 清理旧 API，添加新 API
- `frontend/src/services/metabase.js` - 创建/完善 Metabase 服务封装
- `frontend/src/views/store/StoreAnalytics.vue` - 迁移到 Metabase API（中优先级）
- `frontend/src/views/sales/SalesDetailByProduct.vue` - 迁移到 Metabase API（中优先级）
- `frontend/src/views/FinancialOverview.vue` - 迁移到 Metabase API（中优先级）
- `frontend/src/views/ProductQualityDashboard.vue` - 迁移到 Metabase API（中优先级）
- `frontend/src/views/InventoryHealthDashboard.vue` - 迁移到 Metabase API（中优先级）

#### 不需要修改的文件
- `backend/routers/dashboard_api.py` - 已实现 Metabase Question 代理 API，无需修改
- `backend/services/metabase_question_service.py` - 已实现 Question 查询逻辑，无需修改

### 破坏性变更（Breaking Changes）

**有破坏性变更** - 本 change 将**直接删除**所有无效的旧 Dashboard API 调用代码，不保留废弃标记。原因：
- **Agent 友好性**：避免 Agent 误解，防止 Agent 选择不存在的 API 或尝试实现已废弃的功能
- **代码清晰性**：删除无效代码，保持代码库清晰，减少维护成本
- **架构一致性**：确保前后端架构完全统一，都通过 Metabase Question API 获取数据

**迁移策略**：先清理无效代码，再迁移到新 API，确保每一步都是可验证的。

## Non-Goals

- ❌ **不在本 change 中引入新的业务指标**：仅迁移现有指标的数据来源，不添加新功能
- ❌ **不对 Metabase 内部 Question 做大规模重构**：只消费已有 Question，不修改 Question 设计
- ❌ **不实现 HR 相关看板**：HR 管理相关看板由单独 change 负责
- ❌ **不做性能优化**：图表渲染性能优化、数据缓存优化等工作不在本 change 范围内

## 成功标准

### Phase 1: 清理旧 API 依赖完成（最高优先级）⭐⭐⭐
- ✅ `frontend/src/api/dashboard.js` 中所有无效的旧 API 方法已**直接删除**（15个方法）
- ✅ `frontend/src/stores/dashboard.js` 中对旧 API 的调用已**直接删除**
- ✅ `frontend/src/views/Dashboard.vue` 中对旧 API 的调用已**直接删除**
- ✅ 通过代码搜索确认前端代码中已无对旧 Dashboard API 的直接调用
- ✅ 运行时日志确认不再访问不存在的旧 API 路径
- ✅ **Agent 友好性**：代码库清晰，无无效代码，避免 Agent 误解

### Phase 2: 业务概览页面迁移完成
- ✅ `Dashboard.vue` 通过 Metabase Question API 获取数据
- ✅ `dashboard.js` store 使用 Metabase Question 数据结构
- ✅ `frontend/src/api/dashboard.js` 添加了新的 Metabase 代理 API 调用方法
- ✅ 业务概览页面可以正常加载和显示数据（即使数据为空）

### Phase 3: 其他核心页面迁移完成
- ✅ 至少 1-2 个核心分析页面已迁移到 Metabase API
- ✅ 这些页面可以正常加载和显示数据

### Phase 4: 降级策略和验证完成
- ✅ 运行时日志确认 Dashboard 请求全部走 Metabase 代理 API
- ✅ 降级策略已实现并验证

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据格式不一致 | 中 | 在 `metabase.js` 服务层统一进行数据格式转换 |
| 旧 API 调用遗漏 | 低 | 通过代码搜索和运行时日志确认所有旧 API 调用已移除 |
| 降级策略未测试 | 低 | 编写最小单元测试/组件测试，验证降级逻辑 |

## 预期收益

1. **Agent 友好性**：删除无效代码，避免 Agent 误解，防止 Agent 选择不存在的 API 或尝试实现已废弃的功能 ⭐⭐⭐
2. **架构一致性**：前后端架构完全统一，都通过 Metabase Question API 获取数据
3. **代码简化**：移除对旧 Dashboard API 和物化视图语义层的依赖，代码更简洁
4. **可维护性提升**：统一的 Metabase API 调用方式，便于后续维护和扩展
5. **代码清晰性**：删除无效代码，保持代码库清晰，减少维护成本


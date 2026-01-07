# 实施任务清单：前端 Dashboard 迁移到 Metabase API

## Phase 0: 清理旧 API 依赖（最高优先级 - Agent 友好性）⭐⭐⭐

### 0.1 识别无效的旧 API 调用
- [x] 0.1.1 搜索前端代码中所有旧 Dashboard API 调用
  - [x] 搜索 `/api/dashboard/overview`
  - [x] 搜索 `/api/dashboard/sales-trend`
  - [x] 搜索 `/api/dashboard/profit-analysis`
  - [x] 搜索 `/api/dashboard/top-products`
  - [x] 搜索 `/api/dashboard/platform-comparison`
  - [x] 搜索 `/api/dashboard/shop-comparison`
  - [x] 搜索 `/api/dashboard/order-statistics`
  - [x] 搜索 `/api/dashboard/avg-order-value`
  - [x] 搜索 `/api/dashboard/conversion-funnel`
  - [x] 搜索 `/api/dashboard/realtime`
  - [x] 搜索 `/api/dashboard/yoy-mom`
  - [x] 搜索 `/api/dashboard/kpi-cards`
  - [x] 搜索 `/api/dashboard/traffic-source`
  - [x] 搜索 `/api/dashboard/user-profile`
  - [x] 搜索 `/api/dashboard/export`
  - [x] 搜索 `/api/dashboard/calculate-metrics`
- [x] 0.1.2 确认后端不存在这些 API 路径（验证 `backend/routers/dashboard_api.py`）
- [x] 0.1.3 整理需要删除的文件和方法清单：
  - [x] `frontend/src/api/dashboard.js` - 15个无效方法
  - [x] `frontend/src/stores/dashboard.js` - 所有对旧 API 的调用
  - [x] `frontend/src/views/Dashboard.vue` - 所有对旧 API 的调用
  - [x] `frontend/src/api/test.js` - 测试中对旧 API 的调用

### 0.2 直接删除无效代码（不保留废弃标记）
- [x] 0.2.1 删除 `frontend/src/api/dashboard.js` 中所有无效的旧 API 方法
  - [x] 删除 `getOverview()` 方法
  - [x] 删除 `getSalesTrend()` 方法
  - [x] 删除 `getProfitAnalysis()` 方法
  - [x] 删除 `getTopProducts()` 方法
  - [x] 删除 `getPlatformComparison()` 方法
  - [x] 删除 `getShopComparison()` 方法
  - [x] 删除 `getOrderStatistics()` 方法
  - [x] 删除 `getAvgOrderValueAnalysis()` 方法
  - [x] 删除 `getConversionFunnel()` 方法
  - [x] 删除 `getRealtimeData()` 方法
  - [x] 删除 `getYoYMoMData()` 方法
  - [x] 删除 `getKPICards()` 方法
  - [x] 删除 `getTrafficSource()` 方法
  - [x] 删除 `getUserProfile()` 方法
  - [x] 删除 `exportDashboard()` 方法
  - [x] **注意**：直接删除，不添加 `@deprecated` 注释，避免 Agent 误解
  - [x] **新增**：添加了7个新的 Metabase Question API 方法
- [x] 0.2.2 删除 `frontend/src/stores/dashboard.js` 中对旧 API 的调用
  - [x] 删除 `import dashboardApi from '@/api/dashboard'`
  - [x] 删除所有 `dashboardApi.getOverview()` 调用
  - [x] 删除所有 `dashboardApi.getSalesTrend()` 调用
  - [x] 删除所有 `dashboardApi.getProfitAnalysis()` 调用
  - [x] 删除所有 `dashboardApi.getTopProducts()` 调用
  - [x] 删除所有 `dashboardApi.getPlatformComparison()` 调用
  - [x] 删除所有 `dashboardApi.getOrderStatistics()` 调用
  - [x] 删除所有 `dashboardApi.getConversionFunnel()` 调用
  - [x] 删除所有 `dashboardApi.getRealtimeData()` 调用
  - [x] 删除所有其他旧 API 调用
  - [x] **新增**：方法改为 TODO 占位符，等待迁移到新 API
- [x] 0.2.3 删除 `frontend/src/views/Dashboard.vue` 中对旧 API 的调用
  - [x] 删除所有对旧 API 的 import
  - [x] 删除所有对旧 API 的调用代码（`/dashboard/overview` 和 `/dashboard/gmv-trend`）
  - [x] **新增**：方法改为 TODO 占位符，等待迁移到新 API
- [x] 0.2.4 删除其他组件中对旧 API 的调用
  - [x] 搜索所有使用 `dashboardApi` 的文件
  - [x] 删除 `frontend/src/api/test.js` 中对旧 API 的测试调用

### 0.3 验证删除完整性
- [x] 0.3.1 代码搜索验证
  - [x] 搜索 `dashboardApi.getOverview` - 无结果 ✅
  - [x] 搜索 `dashboardApi.getSalesTrend` - 无结果 ✅
  - [x] 搜索 `/api/dashboard/overview` - 无结果 ✅
  - [x] 搜索 `/api/dashboard/sales-trend` - 无结果 ✅
  - [x] 搜索所有其他旧 API 路径 - 无结果 ✅
- [x] 0.3.2 运行时验证
  - [x] 代码搜索确认：无旧 API 调用 ✅
  - [x] `Dashboard.vue` 中的旧 API 调用已删除，改为 TODO 占位符 ✅
  - [x] 运行时验证：需要用户启动服务后手动测试 Network 面板
- [x] 0.3.3 编译验证
  - [x] 运行 `npm run build`，确认无编译错误 ✅
  - [x] 修复了 `PerformanceManagement.vue` 中重复声明的 `formatCurrency` 函数 ✅
  - [x] 确认删除的代码不会导致编译失败 ✅

## Phase 1: 现状梳理（1天）

### 1.1 代码搜索（Phase 0 已清理旧 API，此阶段仅梳理新 API 需求）
- [x] 1.1.1 确认 Phase 0 清理工作已完成
  - [x] 确认所有无效的旧 API 调用已删除 ✅
  - [x] 确认代码搜索无旧 API 调用结果 ✅
- [x] 1.1.2 梳理需要迁移的组件和对应的 Metabase Question
  - [x] 高优先级：`Dashboard.vue` + `dashboard.js` store + `dashboard.js` api ✅
    - [x] `Dashboard.vue` - 需要 KPI、GMV趋势、平台占比、TOP商品数据
    - [x] `dashboard.js` store - 需要 overview、salesTrend、platformComparison、topProducts 等数据
    - [x] `dashboard.js` api - 已有7个新的 Metabase Question API 方法
  - [x] 中优先级：StoreAnalytics、SalesDetailByProduct、FinancialOverview、ProductQualityDashboard、InventoryHealthDashboard ✅
  - [x] 低优先级：SalesTrendChart、TopProducts 等辅助视图 ✅
  - [x] **分析文档**: `temp/development/phase1_analysis.md` ✅

### 1.2 依赖分析
- [x] 1.2.1 分析每个组件依赖的数据结构 ✅
  - [x] `Dashboard.vue` - kpiData（total_gmv, total_orders, avg_order_value, total_products, conversion_rate）
  - [x] `dashboard.js` store - overview, salesTrend, profitAnalysis, topProducts, platformComparison, orderStatistics, conversionFunnel, realtimeData, trafficRanking
- [x] 1.2.2 确认每个组件需要调用哪些 Metabase Question ✅
  - [x] `Dashboard.vue` → `business_overview_kpi`, `business_overview_comparison`, `business_overview_shop_racing`, `clearance_ranking`
  - [x] `dashboard.js` store → `business_overview_kpi`, `business_overview_comparison`, `business_overview_shop_racing`, `business_overview_traffic_ranking`, `clearance_ranking`
  - [x] 需要确认的 Question：profitAnalysis, orderStatistics, conversionFunnel, realtimeData（可能没有对应的 Question）
- [x] 1.2.3 记录数据格式差异（旧 API 格式 vs Metabase Question API 格式） ✅
  - [x] 字段名映射：Metabase 使用 `snake_case`，前端期望 `camelCase`
  - [x] 日期格式：Metabase 返回 ISO 8601，前端需要 `YYYY-MM-DD`
  - [x] 数字格式：Metabase 可能返回字符串，前端需要数字类型
  - [x] 数组格式：Metabase 返回对象数组，前端可能需要特定结构
  - [x] 响应格式：`{ success: true, data: {...}, message: "..." }`

## Phase 2: Metabase 前端服务封装（1天）

### 2.1 创建/完善 Metabase 服务
- [ ] 2.1.1 创建/检查 `frontend/src/services/metabase.js` 文件
- [ ] 2.1.2 实现 `getQuestionData(questionKeyOrId, filters)` 函数
  - [ ] 统一调用后端 Metabase 代理 API（`/api/metabase/question/{id}/query`）
  - [ ] 处理加载状态（loading）
  - [ ] 处理错误信息（error）
  - [ ] 支持取消请求（abort controller）
- [ ] 2.1.3 实现数据格式转换函数
  - [ ] 将 Metabase Question API 返回的数据格式转换为前端组件期望的格式
  - [ ] 处理日期格式、数字格式等

### 2.2 业务概览相关封装
- [ ] 2.2.1 为业务概览相关 Question 提供简化调用封装：
  - [ ] `fetchBusinessOverviewKpi(filters)`
  - [ ] `fetchBusinessOverviewComparison(filters)`
  - [ ] `fetchBusinessOverviewShopRacing(filters)`
  - [ ] `fetchBusinessOverviewTrafficRanking(filters)`
  - [ ] `fetchBusinessOverviewInventoryBacklog(filters)`
  - [ ] `fetchBusinessOverviewOperationalMetrics(filters)`
  - [ ] `fetchClearanceRanking(filters)`

## Phase 3: 业务概览页面迁移（高优先级，2-3天）

### 3.1 修改 Dashboard.vue
- [ ] 3.1.1 移除对旧 Dashboard API 的调用
  - [ ] 移除 `import { getDashboardOverview } from '@/api/dashboard'`
  - [ ] 移除 `import { calculateMetrics } from '@/api/dashboard'`
  - [ ] 移除所有旧 API 调用代码
- [ ] 3.1.2 使用 `metabase.js` 服务调用 Metabase Question API
  - [ ] 调用 `fetchBusinessOverviewKpi` 获取 KPI 数据
  - [ ] 调用 `fetchBusinessOverviewComparison` 获取对比数据
  - [ ] 调用 `fetchBusinessOverviewInventoryBacklog` 获取库存积压数据
  - [ ] 调用其他需要的 Question API
- [ ] 3.1.3 使用 ECharts 渲染图表
  - [ ] 保持现有布局和样式
  - [ ] 确保图表类型正确（折线图、柱状图、饼图等）
  - [ ] 确保图表数据格式正确

### 3.2 修改 dashboard.js store
- [ ] 3.2.1 移除对旧 Dashboard API 的调用
- [ ] 3.2.2 将状态源头改为 Metabase Question 数据结构
  - [ ] 修改 `state` 定义，匹配 Metabase Question API 返回的数据结构
  - [ ] 修改 `actions`，使用 `metabase.js` 服务获取数据
- [ ] 3.2.3 保留原有筛选器功能
  - [ ] 日期范围筛选器
  - [ ] 平台筛选器
  - [ ] 店铺筛选器
  - [ ] 粒度切换（日/周/月）

### 3.3 修改 frontend/src/api/dashboard.js
- [ ] 3.3.1 确认 Phase 0 已删除所有无效的旧 API 方法
  - [ ] 确认 `getOverview`、`getSalesTrend` 等15个方法已删除
  - [ ] 确认文件结构清晰，无废弃代码
- [ ] 3.3.2 添加新的基于 Metabase 代理 API 的调用函数
  - [ ] `queryBusinessOverviewKpi(filters)` - 调用 `/api/dashboard/business-overview/kpi`
  - [ ] `queryBusinessOverviewComparison(filters)` - 调用 `/api/dashboard/business-overview/comparison`
  - [ ] `queryBusinessOverviewShopRacing(filters)` - 调用 `/api/dashboard/business-overview/shop-racing`
  - [ ] `queryBusinessOverviewTrafficRanking(filters)` - 调用 `/api/dashboard/business-overview/traffic-ranking`
  - [ ] `queryBusinessOverviewInventoryBacklog(filters)` - 调用 `/api/dashboard/business-overview/inventory-backlog`
  - [ ] `queryBusinessOverviewOperationalMetrics(filters)` - 调用 `/api/dashboard/business-overview/operational-metrics`
  - [ ] `queryClearanceRanking(filters)` - 调用 `/api/dashboard/clearance-ranking`

### 3.4 测试业务概览页面
- [ ] 3.4.1 在浏览器中访问业务概览页面（`http://localhost:5173`）
- [ ] 3.4.2 确认页面可以正常加载
- [ ] 3.4.3 确认所有 KPI 卡片正常显示（即使数据为 0）
- [ ] 3.4.4 确认所有图表正常渲染（即使数据为空）
- [ ] 3.4.5 测试筛选器功能（日期范围、平台、店铺、粒度切换）

## Phase 4: 其他核心分析页面迁移（中优先级，2-3天）

### 4.1 选择优先迁移的页面
- [ ] 4.1.1 选定 1-2 个代表性页面优先迁移
  - [ ] 建议：`StoreAnalytics.vue`、`SalesDetailByProduct.vue`
  - [ ] 记录选择理由

### 4.2 为选定页面设计 Metabase Question
- [ ] 4.2.1 分析页面需要的数据
- [ ] 4.2.2 确认对应的 Metabase Question（由 `configure-metabase-dashboard-questions` change 提供）
- [ ] 4.2.3 如果 Question 不存在，记录需求，后续创建

### 4.3 迁移选定页面
- [ ] 4.3.1 修改 `StoreAnalytics.vue`（如果选定）
  - [ ] 移除对旧 API 的调用
  - [ ] 使用 `metabase.js` 服务调用 Metabase Question API
  - [ ] 使用 ECharts 渲染图表
  - [ ] 测试页面功能
- [ ] 4.3.2 修改 `SalesDetailByProduct.vue`（如果选定）
  - [ ] 移除对旧 API 的调用
  - [ ] 使用 `metabase.js` 服务调用 Metabase Question API
  - [ ] 使用 ECharts 渲染图表
  - [ ] 测试页面功能

### 4.4 迁移其他页面（可选）
- [ ] 4.4.1 迁移 `FinancialOverview.vue`（如果时间允许）
- [ ] 4.4.2 迁移 `ProductQualityDashboard.vue`（如果时间允许）
- [ ] 4.4.3 迁移 `InventoryHealthDashboard.vue`（如果时间允许）

## Phase 5: 降级策略与错误处理（1天）

### 5.1 错误处理
- [ ] 5.1.1 在 `metabase.js` 中集中处理错误
  - [ ] 区分网络错误（Network Error）
  - [ ] 区分认证错误（Authentication Error）
  - [ ] 区分 Question 配置错误（Question ID 未配置）
  - [ ] 区分 Metabase 服务不可用（Service Unavailable）
  - [ ] 返回统一错误对象给组件
- [ ] 5.1.2 在组件中处理错误
  - [ ] 显示友好错误提示
  - [ ] 记录错误日志

### 5.2 降级策略实现
- [ ] 5.2.1 在 Dashboard 页面实现降级逻辑
  - [ ] Metabase 调用失败时，在顶部展示友好错误提示
  - [ ] 图表区域显示占位提示（"数据加载失败，请稍后重试"）
  - [ ] 可选：展示上次缓存数据（如果存在）
  - [ ] 提供「重试」按钮，重新拉取数据
- [ ] 5.2.2 实现健康检查
  - [ ] 在应用启动时检查 Metabase 服务可用性
  - [ ] 在 Dashboard 页面加载时检查 Metabase 服务可用性

### 5.3 测试降级策略
- [ ] 5.3.1 停止 Metabase 服务
- [ ] 5.3.2 访问业务概览页面
- [ ] 5.3.3 确认显示友好错误提示
- [ ] 5.3.4 确认「重试」按钮功能正常
- [ ] 5.3.5 恢复 Metabase 服务，确认自动恢复

## Phase 6: 最终验证（1天）

### 6.1 代码验证（Phase 0 已完成清理）
- [ ] 6.1.1 再次搜索前端代码，确认已无对旧 Dashboard API 的直接调用
  - [ ] 确认 Phase 0 的清理工作完整
  - [ ] 确认无遗漏的旧 API 调用
- [ ] 6.1.2 更新相关注释和文档
  - [ ] 更新 `frontend/src/api/dashboard.js` 的注释，说明使用 Metabase Question API
  - [ ] 更新组件注释，说明数据来源为 Metabase

### 6.2 运行时验证
- [ ] 6.2.1 启动前端和后端服务
- [ ] 6.2.2 打开浏览器开发者工具，查看 Network 面板
- [ ] 6.2.3 访问业务概览页面，确认：
  - [ ] 所有请求都走 Metabase 代理 API（`/api/metabase/question/*`）
  - [ ] 不再访问旧 Dashboard API（`/api/dashboard/overview` 等）
  - [ ] 不再访问物化视图相关旧路由

### 6.3 功能验证
- [ ] 6.3.1 在 Chrome 浏览器中验证：
  - [ ] 业务概览页面加载成功
  - [ ] 主要图表和 KPI 正常显示
  - [ ] 筛选器功能正常
- [ ] 6.3.2 在 Edge 浏览器中验证（如果时间允许）
- [ ] 6.3.3 在 Firefox 浏览器中验证（如果时间允许）

### 6.4 文档更新
- [ ] 6.4.1 更新 `docs/AGENT_START_HERE.md`，说明前端 Dashboard 已迁移到 Metabase API
- [ ] 6.4.2 在 `openspec/changes/migrate-frontend-dashboard-to-metabase-api` 目录中记录：
  - [ ] 迁移完成的组件清单
  - [ ] 潜在后续改进建议
  - [ ] 已知问题和限制

## Phase 7: 验收（1天）

### 7.1 功能验收
- [ ] 7.1.1 业务概览页面迁移完成，功能正常
- [ ] 7.1.2 至少 1-2 个核心分析页面已迁移，功能正常
- [ ] 7.1.3 降级策略已实现并验证

### 7.2 代码验收
- [ ] 7.2.1 前端代码中已无对旧 Dashboard API 的直接调用
- [ ] 7.2.2 运行时日志确认 Dashboard 请求全部走 Metabase 代理 API
- [ ] 7.2.3 运行 `openspec validate migrate-frontend-dashboard-to-metabase-api --strict`，确认通过

### 7.3 提交代码
- [ ] 7.3.1 提交代码：`git commit -m "feat: migrate frontend Dashboard to Metabase Question API"`


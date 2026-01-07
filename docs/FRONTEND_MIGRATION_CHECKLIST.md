# 前端组件迁移清单 - DSS架构重构

## 概述

本文档列出了需要从后端API迁移到Metabase Dashboard嵌入的前端组件。所有迁移工作将在Phase 4完成。

**迁移原则**：
- 高优先级组件优先迁移（核心功能）
- 保留现有页面布局和交互逻辑
- 使用MetabaseChart组件嵌入Metabase Dashboard
- 提供降级策略（Metabase不可用时显示静态图表）

---

## 高优先级（核心功能）

### 1. Dashboard.vue - 业务概览页面 ⚠️ **关键**

**文件路径**: `frontend/src/views/Dashboard.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 移除对`/api/dashboard/overview`的API调用
- [ ] 移除对`/api/dashboard/calculate-metrics`的API调用
- [ ] 移除KPI卡片的数据获取逻辑（改为Metabase Dashboard）
- [ ] 移除图表组件的数据获取逻辑（改为Metabase嵌入）
- [ ] 使用`MetabaseChart.vue`组件嵌入Metabase Dashboard
- [ ] 保留自定义筛选器组件（Vue），添加粒度切换（日/周/月）
- [ ] 添加"刷新数据"按钮（触发Metabase定时计算任务刷新C类数据）
- [ ] 添加降级策略：Metabase不可用时显示静态图表

**Metabase Dashboard ID**: 待创建（Phase 2）

**迁移计划**: Phase 4 - 3.2节

---

### 2. dashboard.js - Dashboard状态管理 ⚠️ **关键**

**文件路径**: `frontend/src/stores/dashboard.js`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 移除对后端Dashboard API的调用
- [ ] 改为调用Metabase代理API（`/api/metabase/*`）
- [ ] 保留筛选器状态管理（日期范围、平台、店铺、粒度）
- [ ] 添加Metabase Dashboard状态管理（加载状态、错误处理）

**迁移计划**: Phase 4 - 3.2节

---

### 3. dashboard.js (API) - Dashboard API调用 ⚠️ **关键**

**文件路径**: `frontend/src/api/dashboard.js`（如果存在）

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查文件是否存在
- [ ] 如果存在，标记为废弃或删除
- [ ] 改为使用`frontend/src/services/metabase.js`（Metabase API客户端）

**迁移计划**: Phase 4 - 3.2节

---

## 中优先级（分析功能）

### 4. StoreAnalytics.vue - 店铺分析页面

**文件路径**: `frontend/src/views/store/StoreAnalytics.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Dashboard嵌入
- [ ] 保留店铺筛选器功能

**Metabase Dashboard ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

### 5. SalesDetailByProduct.vue - 产品销售详情

**文件路径**: `frontend/src/views/sales/SalesDetailByProduct.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Dashboard嵌入
- [ ] 保留产品筛选器功能

**Metabase Dashboard ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

### 6. FinancialOverview.vue - 财务概览

**文件路径**: `frontend/src/views/FinancialOverview.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Dashboard嵌入
- [ ] 保留财务筛选器功能

**Metabase Dashboard ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

### 7. ProductQualityDashboard.vue - 产品质量看板

**文件路径**: `frontend/src/views/ProductQualityDashboard.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Dashboard嵌入

**Metabase Dashboard ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

### 8. InventoryHealthDashboard.vue - 库存健康看板

**文件路径**: `frontend/src/views/InventoryHealthDashboard.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Dashboard嵌入

**Metabase Dashboard ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

## 低优先级（辅助功能）

### 9. SalesTrendChart.vue - 销售趋势图表

**文件路径**: `frontend/src/views/SalesTrendChart.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Question嵌入（单个图表）

**Metabase Question ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

### 10. TopProducts.vue - Top产品排行

**文件路径**: `frontend/src/views/TopProducts.vue`

**当前状态**: 待迁移

**迁移内容**:
- [ ] 检查当前使用的API端点
- [ ] 替换为Metabase Question嵌入（单个图表）

**Metabase Question ID**: 待创建（Phase 2或Phase 4）

**迁移计划**: Phase 4

---

## 迁移状态跟踪

| 组件 | 优先级 | 状态 | 计划完成时间 | 实际完成时间 | 备注 |
|------|--------|------|-------------|-------------|------|
| Dashboard.vue | 高 | 待迁移 | Phase 4 | - | 核心功能 |
| dashboard.js (store) | 高 | 待迁移 | Phase 4 | - | 核心功能 |
| dashboard.js (api) | 高 | 待迁移 | Phase 4 | - | 核心功能 |
| StoreAnalytics.vue | 中 | 待迁移 | Phase 4 | - | - |
| SalesDetailByProduct.vue | 中 | 待迁移 | Phase 4 | - | - |
| FinancialOverview.vue | 中 | 待迁移 | Phase 4 | - | - |
| ProductQualityDashboard.vue | 中 | 待迁移 | Phase 4 | - | - |
| InventoryHealthDashboard.vue | 中 | 待迁移 | Phase 4 | - | - |
| SalesTrendChart.vue | 低 | 待迁移 | Phase 4 | - | - |
| TopProducts.vue | 低 | 待迁移 | Phase 4 | - | - |

---

## 迁移步骤

### Phase 4迁移流程

1. **准备阶段**（Phase 2完成后）
   - [ ] 确认Metabase Dashboard已创建
   - [ ] 确认MetabaseChart组件已创建
   - [ ] 确认Metabase代理API已实现

2. **高优先级组件迁移**（Phase 4 - 3.2节）
   - [ ] Dashboard.vue迁移
   - [ ] dashboard.js (store)迁移
   - [ ] dashboard.js (api)迁移或删除

3. **中优先级组件迁移**（Phase 4）
   - [ ] StoreAnalytics.vue迁移
   - [ ] SalesDetailByProduct.vue迁移
   - [ ] FinancialOverview.vue迁移
   - [ ] ProductQualityDashboard.vue迁移
   - [ ] InventoryHealthDashboard.vue迁移

4. **低优先级组件迁移**（Phase 4）
   - [ ] SalesTrendChart.vue迁移
   - [ ] TopProducts.vue迁移

5. **测试和验证**（Phase 4验收）
   - [ ] 所有组件迁移完成
   - [ ] 降级策略测试通过
   - [ ] 浏览器兼容性测试通过

---

## 注意事项

1. **向后兼容**: 迁移过程中保持现有功能可用，使用渐进式迁移策略
2. **降级策略**: 所有组件必须实现降级策略（Metabase不可用时显示静态图表或错误提示）
3. **性能优化**: 使用Metabase缓存机制，避免频繁查询
4. **用户体验**: 保持现有页面布局和交互逻辑，只替换数据源

---

**创建时间**: 2025-11-27  
**最后更新**: 2025-11-27  
**维护**: AI Agent Team


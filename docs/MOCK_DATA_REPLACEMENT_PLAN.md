# 前端Mock数据替换计划

**创建时间**: 2025-01-16  
**状态**: 📋 规划阶段  
**预计完成时间**: 2-3周

---

## 📊 Mock数据使用情况梳理

### 1. Mock数据开关机制

**位置**: `frontend/src/api/index.js`

```javascript
// Mock数据开关（从环境变量读取）
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'
```

**当前状态**: Mock数据通过环境变量控制，默认关闭（使用真实API）

---

## 🔍 Mock数据使用清单

### 1. 销售相关API（Sales APIs）

**位置**: `frontend/src/api/index.js` (行907-998)

**使用Mock数据的API**:
- ✅ `getSalesCampaigns()` - 获取销售战役列表
- ✅ `getSalesCampaignDetail(id)` - 获取销售战役详情
- ✅ `createSalesCampaign(data)` - 创建销售战役
- ✅ `updateSalesCampaign(id, data)` - 更新销售战役
- ✅ `deleteSalesCampaign(id)` - 删除销售战役
- ✅ `getSalesCampaignPerformance(id)` - 获取销售战役绩效
- ✅ `getSalesCampaignComparison(id1, id2)` - 获取销售战役对比

**Mock数据来源**: `useSalesStore()` (Pinia store)

**对应后端API**:
- `/api/sales-campaign/*` (需要确认是否存在)

**优先级**: ⭐⭐⭐ 高（业务核心功能）

---

### 2. 人力资源API（HR APIs）

**位置**: `frontend/src/api/index.js` (行999-1069)

**使用Mock数据的API**:
- ✅ `getEmployees(params)` - 获取员工列表
- ✅ `getEmployeeDetail(id)` - 获取员工详情
- ✅ `createEmployee(data)` - 创建员工
- ✅ `updateEmployee(id, data)` - 更新员工
- ✅ `deleteEmployee(id)` - 删除员工
- ✅ `getEmployeePerformance(id, period)` - 获取员工绩效

**Mock数据来源**: `useHRStore()` (Pinia store)

**对应后端API**:
- `/api/hr/*` (需要确认是否存在)

**优先级**: ⭐⭐ 中（辅助功能）

---

### 3. 目标管理API（Target Management APIs）

**位置**: `frontend/src/api/index.js` (行1071-1138)

**使用Mock数据的API**:
- ✅ `getTargets(params)` - 获取目标列表
- ✅ `getTargetDetail(id)` - 获取目标详情
- ✅ `createTarget(data)` - 创建目标
- ✅ `updateTarget(id, data)` - 更新目标
- ✅ `deleteTarget(id)` - 删除目标
- ✅ `getTargetBreakdown(id)` - 获取目标分解

**Mock数据来源**: `useTargetStore()` (Pinia store)

**对应后端API**:
- `/api/target-management/*` (✅ 已存在)

**优先级**: ⭐⭐⭐ 高（业务核心功能）

---

### 4. 库存API（Inventory APIs）

**位置**: `frontend/src/api/index.js` (行1139-1152)

**使用Mock数据的API**:
- ✅ `getInventory(params)` - 获取库存列表
- ✅ `getInventoryDetail(id)` - 获取库存详情

**Mock数据来源**: `useInventoryStore()` (Pinia store)

**对应后端API**:
- `/api/inventory/*` (✅ 已存在)
- `/api/products/*` (✅ 已存在)

**优先级**: ⭐⭐⭐ 高（业务核心功能）

---

### 5. 店铺分析API（Store Analytics APIs）

**位置**: `frontend/src/api/index.js` (行1153-1300)

**使用Mock数据的API**:
- ✅ `getStoreHealthScores(params)` - 获取店铺健康度评分
- ✅ `getStoreAlerts(params)` - 获取店铺预警
- ✅ `getStoreTrends(params)` - 获取店铺趋势
- ✅ `getStoreComparison(params)` - 获取店铺对比

**Mock数据来源**: `useStoreStore()` (Pinia store)

**对应后端API**:
- `/api/store-analytics/*` (✅ 已存在)

**优先级**: ⭐⭐⭐ 高（业务核心功能）

---

### 6. 绩效管理API（Performance Management APIs）

**位置**: `frontend/src/api/index.js` (行1049-1069)

**使用Mock数据的API**:
- ✅ `calculatePerformanceScores(period, configId)` - 计算绩效评分

**Mock数据来源**: `usePerformanceStore()` (Pinia store)

**对应后端API**:
- `/api/performance-management/*` (✅ 已存在)

**优先级**: ⭐⭐ 中（辅助功能）

---

## 📋 Mock数据替换优先级和时间表

### 阶段1：核心功能（第1周，3-5天）⭐⭐⭐

**目标**: 替换核心业务功能的Mock数据，确保系统基本可用

#### 1.1 Dashboard业务概览（1天）
- ✅ 替换KPI数据Mock（GMV、订单数、转化率等）
- ✅ 对接`/api/dashboard/overview` API（✅已存在）
- ✅ 更新`frontend/src/views/BusinessOverview.vue`
- ✅ 测试业务概览显示

#### 1.2 店铺健康度评分（1天）
- ✅ 对接`/api/store-analytics/health-scores` API（✅已存在）
- ✅ 更新`frontend/src/stores/store.js`
- ✅ 支持多维度筛选（平台、店铺、时间）
- ✅ 测试健康度评分显示

#### 1.3 目标管理（1-2天）
- ✅ 替换目标列表Mock数据
- ✅ 对接`/api/target-management/*` API（✅已存在）
- ✅ 更新`frontend/src/stores/target.js`
- ✅ 测试目标管理功能（CRUD）

#### 1.4 库存管理（1天）
- ✅ 替换库存列表Mock数据
- ✅ 对接`/api/inventory/*` 或 `/api/products/*` API（✅已存在）
- ✅ 更新`frontend/src/stores/inventory.js`
- ✅ 测试库存管理功能

**阶段1总计**: 4-5天

---

### 阶段2：业务功能（第2周，5-7天）⭐⭐

**目标**: 替换业务功能的Mock数据，完善系统功能

#### 2.1 店铺分析（2天）
- ⏳ 替换店铺GMV趋势Mock数据
- ⏳ 替换店铺流量分析Mock数据
- ⏳ 替换店铺转化率分析Mock数据
- ⏳ 替换店铺预警Mock数据
- ⏳ 对接`/api/store-analytics/*` API（✅已存在）
- ⏳ 更新`frontend/src/stores/store.js`
- ⏳ 测试店铺分析功能

#### 2.2 销售战役管理（2-3天）
- ⏳ 替换销售战役列表Mock数据
- ⏳ 替换销售战役详情Mock数据
- ⏳ 对接`/api/sales-campaign/*` API（需要确认是否存在）
- ⏳ 更新`frontend/src/stores/sales.js`
- ⏳ 测试销售战役管理功能（CRUD）

#### 2.3 绩效管理（1-2天）
- ⏳ 替换绩效评分计算Mock数据
- ⏳ 对接`/api/performance-management/*` API（✅已存在）
- ⏳ 更新`frontend/src/stores/performance.js`
- ⏳ 测试绩效管理功能

**阶段2总计**: 5-7天

---

### 阶段3：辅助功能（第3周，3-5天）⭐

**目标**: 替换辅助功能的Mock数据，完善系统功能

#### 3.1 人力资源管理（2-3天）
- ⏳ 替换员工列表Mock数据
- ⏳ 替换员工详情Mock数据
- ⏳ 对接`/api/hr/*` API（需要确认是否存在）
- ⏳ 更新`frontend/src/stores/hr.js`
- ⏳ 测试人力资源管理功能（CRUD）

#### 3.2 其他辅助功能（1-2天）
- ⏳ 替换其他辅助功能的Mock数据
- ⏳ 测试辅助功能

**阶段3总计**: 3-5天

---

## 🎯 替换策略

### 策略1：渐进式替换（推荐）

**优点**:
- 风险低，可以逐步验证
- 不影响现有功能
- 可以分阶段上线

**步骤**:
1. 先替换核心功能（阶段1）
2. 验证核心功能正常后，替换业务功能（阶段2）
3. 最后替换辅助功能（阶段3）

### 策略2：一次性替换（不推荐）

**缺点**:
- 风险高，可能影响多个功能
- 测试工作量大
- 回滚困难

---

## 📝 替换步骤（每个API）

### 步骤1：确认后端API存在
- [ ] 检查后端API是否存在
- [ ] 确认API响应格式符合统一标准
- [ ] 确认API功能完整（CRUD）

### 步骤2：更新前端API调用
- [ ] 移除Mock数据判断逻辑（`if (USE_MOCK_DATA)`）
- [ ] 直接调用真实API
- [ ] 确保参数格式正确
- [ ] 确保错误处理正确

### 步骤3：更新Store（如需要）
- [ ] 移除Mock数据相关代码
- [ ] 更新Store使用真实API
- [ ] 确保状态管理正确

### 步骤4：更新View组件
- [ ] 移除Mock数据相关代码
- [ ] 确保数据展示正确
- [ ] 确保错误处理正确

### 步骤5：测试验证
- [ ] 测试API调用正常
- [ ] 测试数据展示正确
- [ ] 测试错误处理正确
- [ ] 测试边界情况

---

## ✅ 替换检查清单

### 每个API替换后检查：
- [ ] API调用成功（无网络错误）
- [ ] 数据格式正确（符合统一响应格式）
- [ ] 数据展示正确（前端显示正常）
- [ ] 错误处理正确（显示错误信息）
- [ ] 空数据处理正确（显示"-"或默认值）
- [ ] 加载状态正确（显示loading）
- [ ] 分页功能正常（如有分页）

---

## 📊 进度跟踪

### 阶段1：核心功能（4-5天）
- [ ] Dashboard业务概览（1天）
- [ ] 店铺健康度评分（1天）
- [ ] 目标管理（1-2天）
- [ ] 库存管理（1天）

### 阶段2：业务功能（5-7天）
- [ ] 店铺分析（2天）
- [ ] 销售战役管理（2-3天）
- [ ] 绩效管理（1-2天）

### 阶段3：辅助功能（3-5天）
- [ ] 人力资源管理（2-3天）
- [ ] 其他辅助功能（1-2天）

---

## 🚨 注意事项

1. **环境变量控制**: Mock数据开关通过`VITE_USE_MOCK_DATA`环境变量控制，替换后可以保留作为降级方案
2. **向后兼容**: 替换时确保不影响现有功能，可以先保留Mock数据代码，通过环境变量切换
3. **错误处理**: 确保错误处理机制正确，使用统一的错误处理工具函数
4. **数据格式**: 确保API响应格式符合统一标准（success、data、timestamp字段）
5. **测试验证**: 每个API替换后必须进行完整测试，确保功能正常

---

## 📚 相关文档

- [API契约开发指南](API_CONTRACTS.md)
- [错误处理测试文档](ERROR_HANDLING_TEST.md)
- [端到端测试指南](E2E_TEST_GUIDE.md)
- [前端API调用规范验证](FRONTEND_API_CALL_VALIDATION.md)

---

**最后更新**: 2025-01-16  
**维护**: AI Agent Team  
**状态**: 📋 规划阶段，待开始执行


# Mock数据替换执行指南

**创建时间**: 2025-01-16  
**状态**: 📋 执行准备阶段  
**目的**: 提供详细的Mock数据替换执行步骤和检查清单

---

## 📋 执行前准备

### 1. 确认后端API可用性

在执行Mock数据替换前，需要确认以下后端API是否可用：

#### ✅ 已确认存在的API
- `/api/dashboard/overview` - Dashboard业务概览
- `/api/store-analytics/health-scores` - 店铺健康度评分
- `/api/store-analytics/alerts` - 店铺预警
- `/api/target-management/*` - 目标管理API
- `/api/inventory/*` - 库存管理API
- `/api/products/*` - 产品管理API
- `/api/performance-management/*` - 绩效管理API

#### ⚠️ 需要确认的API
- `/api/sales-campaign/*` - 销售战役管理API（需要确认是否存在）

### 2. 环境变量配置

确保前端环境变量配置正确：

```bash
# .env.development 或 .env.production
VITE_USE_MOCK_DATA=false  # 设置为false以使用真实API
```

### 3. 测试环境准备

- ✅ 后端服务运行正常（`http://localhost:8001`）
- ✅ 数据库连接正常
- ✅ 有测试数据可用

---

## 🔧 执行步骤

### 阶段1：核心功能Mock数据替换（第1周，3-5天）

#### 1.1 Dashboard业务概览（1天）

**文件**: `frontend/src/views/BusinessOverview.vue`

**步骤**:
1. 检查当前使用的Mock数据来源
   ```javascript
   // 查找 USE_MOCK_DATA 或 useDashboardStore 的使用
   ```

2. 确认后端API端点
   ```javascript
   // 确认使用 /api/dashboard/overview
   ```

3. 替换Mock数据调用
   ```javascript
   // 从：
   if (USE_MOCK_DATA) {
     const { useDashboardStore } = await import('@/stores/dashboard')
     return await dashboardStore.getOverview(params)
   }
   
   // 改为：
   return await api._get('/dashboard/overview', { params })
   ```

4. 更新错误处理
   ```javascript
   // 使用统一的错误处理工具
   import { handleApiError } from '@/utils/errorHandler'
   ```

5. 测试验证
   - [ ] KPI数据正确显示（GMV、订单数、转化率等）
   - [ ] 时间范围筛选正常工作
   - [ ] 平台/店铺筛选正常工作
   - [ ] 错误处理正常（网络错误、业务错误）

**检查清单**:
- [ ] Mock数据调用已移除
- [ ] API调用使用统一格式（`api._get`）
- [ ] 错误处理使用统一工具（`handleApiError`）
- [ ] 数据格式化使用统一工具（`formatValue`、`formatNumber`等）
- [ ] 测试通过（功能正常、错误处理正常）

---

#### 1.2 店铺健康度评分（1天）

**文件**: `frontend/src/stores/store.js` 或相关视图文件

**步骤**:
1. 检查当前使用的Mock数据来源
   ```javascript
   // 查找 getStoreHealthScores 方法
   ```

2. 确认后端API端点
   ```javascript
   // 确认使用 /api/store-analytics/health-scores
   ```

3. 替换Mock数据调用
   ```javascript
   // 从：
   if (USE_MOCK_DATA) {
     const { useStoreStore } = await import('@/stores/store')
     return await storeStore.getHealthScores(params)
   }
   
   // 改为：
   return await api._get('/store-analytics/health-scores', { params })
   ```

4. 更新参数格式
   ```javascript
   // 确保参数格式符合后端API要求
   // platform, shop_id, start_date, end_date, granularity
   ```

5. 测试验证
   - [ ] 健康度评分正确显示
   - [ ] 多维度筛选正常工作（平台、店铺、时间）
   - [ ] 评分详情正确显示
   - [ ] 错误处理正常

**检查清单**:
- [ ] Mock数据调用已移除
- [ ] API调用使用统一格式
- [ ] 参数格式正确（符合后端API要求）
- [ ] 错误处理使用统一工具
- [ ] 测试通过

---

#### 1.3 目标管理（1-2天）

**文件**: `frontend/src/stores/target.js` 或相关视图文件

**步骤**:
1. 检查当前使用的Mock数据来源
   ```javascript
   // 查找 getTargets, getTargetDetail, createTarget 等方法
   ```

2. 确认后端API端点
   ```javascript
   // 确认使用 /api/target-management/*
   // GET /api/target-management/targets - 获取目标列表
   // GET /api/target-management/targets/{id} - 获取目标详情
   // POST /api/target-management/targets - 创建目标
   // PUT /api/target-management/targets/{id} - 更新目标
   // DELETE /api/target-management/targets/{id} - 删除目标
   ```

3. 替换Mock数据调用
   ```javascript
   // 列表查询
   async getTargets(params = {}) {
     return await api._get('/target-management/targets', { params })
   }
   
   // 详情查询
   async getTargetDetail(id) {
     return await api._get(`/target-management/targets/${id}`)
   }
   
   // 创建
   async createTarget(data) {
     return await api._post('/target-management/targets', data)
   }
   
   // 更新
   async updateTarget(id, data) {
     return await api._put(`/target-management/targets/${id}`, data)
   }
   
   // 删除
   async deleteTarget(id) {
     return await api._delete(`/target-management/targets/${id}`)
   }
   ```

4. 更新CRUD操作
   - 确保创建/更新时数据验证正确
   - 确保删除时确认提示正常
   - 确保操作后列表自动刷新

5. 测试验证
   - [ ] 目标列表正确显示
   - [ ] 目标详情正确显示
   - [ ] 创建目标功能正常
   - [ ] 更新目标功能正常
   - [ ] 删除目标功能正常
   - [ ] 错误处理正常（验证错误、业务错误）

**检查清单**:
- [ ] 所有CRUD操作的Mock数据调用已移除
- [ ] API调用使用统一格式（`api._get`、`api._post`、`api._put`、`api._delete`）
- [ ] 数据验证正确（前端验证 + 后端验证）
- [ ] 错误处理使用统一工具
- [ ] 操作后列表自动刷新
- [ ] 测试通过（所有CRUD操作正常）

---

#### 1.4 库存管理（1天）

**文件**: `frontend/src/stores/inventory.js` 或相关视图文件

**步骤**:
1. 检查当前使用的Mock数据来源
   ```javascript
   // 查找 getInventory, getProductInventory 等方法
   ```

2. 确认后端API端点
   ```javascript
   // 确认使用 /api/inventory/* 或 /api/products/*
   ```

3. 替换Mock数据调用
   ```javascript
   // 库存列表
   async getInventory(params = {}) {
     return await api._get('/inventory', { params })
   }
   
   // 产品库存
   async getProductInventory(productId, params = {}) {
     return await api._get(`/products/${productId}/inventory`, { params })
   }
   ```

4. 测试验证
   - [ ] 库存列表正确显示
   - [ ] 产品库存正确显示
   - [ ] 筛选功能正常工作
   - [ ] 错误处理正常

**检查清单**:
- [ ] Mock数据调用已移除
- [ ] API调用使用统一格式
- [ ] 错误处理使用统一工具
- [ ] 测试通过

---

## 🧪 测试验证标准

### 功能测试
- ✅ 数据正确显示（与Mock数据格式一致）
- ✅ 筛选功能正常工作
- ✅ CRUD操作正常工作（如适用）
- ✅ 分页功能正常工作（如适用）

### 错误处理测试
- ✅ 网络错误处理正常（显示友好错误提示）
- ✅ 业务错误处理正常（显示错误码和恢复建议）
- ✅ 空数据处理正常（显示"-"而非错误）

### 性能测试
- ✅ API响应时间正常（<2s）
- ✅ 大数据量分页正常（不卡顿）
- ✅ 多次请求不重复（避免重复调用）

---

## 📝 替换后清理

### 1. 移除Mock数据开关

替换完成后，可以移除Mock数据开关：

```javascript
// 从 frontend/src/api/index.js 移除
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'
```

### 2. 移除Mock数据Store

如果不再需要Mock数据Store，可以移除：
- `frontend/src/stores/dashboard.js`（如果只用于Mock）
- `frontend/src/stores/sales.js`（如果只用于Mock）
- 其他仅用于Mock的Store文件

### 3. 更新文档

- [ ] 更新API文档（移除Mock数据说明）
- [ ] 更新开发文档（移除Mock数据使用说明）
- [ ] 更新用户文档（如有）

---

## ⚠️ 常见问题

### 1. API响应格式不一致

**问题**: 后端API返回格式与前端期望不一致

**解决**:
- 检查后端API是否使用统一响应格式（`success_response`）
- 检查前端响应拦截器是否正确处理（`frontend/src/api/index.js`）

### 2. 参数格式不匹配

**问题**: 前端传递的参数格式与后端API要求不一致

**解决**:
- 检查后端API文档（`/api/docs`）
- 确认参数名称和格式（如日期格式：`YYYY-MM-DD`）

### 3. 错误处理不统一

**问题**: 错误处理方式不一致

**解决**:
- 使用统一的错误处理工具（`frontend/src/utils/errorHandler.js`）
- 确保所有错误都通过响应拦截器处理

### 4. 空数据处理问题

**问题**: 空数据时显示错误而非"-"

**解决**:
- 使用统一的数据格式化工具（`frontend/src/utils/dataFormatter.js`）
- 区分空数据（API成功但无数据）和API错误

---

## 📚 相关文档

- [Mock数据替换计划](MOCK_DATA_REPLACEMENT_PLAN.md) - 详细的替换计划和优先级
- [API契约开发指南](API_CONTRACTS.md) - API响应格式和调用规范
- [错误处理测试文档](ERROR_HANDLING_TEST.md) - 错误处理测试场景
- [前端API调用规范验证](FRONTEND_API_CALL_VALIDATION.md) - 前端API调用规范

---

**最后更新**: 2025-01-16  
**维护**: AI Agent Team  
**状态**: 📋 执行准备阶段，待实际执行


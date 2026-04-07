# Mock数据替换指南

**创建时间**: 2025-01-31  
**状态**: ✅ 已完成  
**目的**: 指导开发者如何识别、替换和验证Mock数据

---

## 📋 概述

本指南说明如何将前端Mock数据替换为真实API调用，确保系统使用真实数据。

---

## 🔍 如何识别Mock数据

### 1. 检查API调用代码

**位置**: `frontend/src/api/index.js`

**识别方法**:
1. 查找`USE_MOCK_DATA`变量
2. 查找`if (USE_MOCK_DATA)`条件判断
3. 查找`return mockData`或`return Promise.resolve(mockData)`

**示例**:
```javascript
// ❌ Mock数据示例
if (USE_MOCK_DATA) {
  return Promise.resolve(mockSalesCampaigns)
}

// ✅ 真实API调用
return this._get('/sales-campaigns', { params })
```

### 2. 检查Pinia Store

**位置**: `frontend/src/stores/*.js`

**识别方法**:
1. 查找`mockData`或`mock`开头的变量
2. 查找硬编码的测试数据
3. 查找`useMockData()`或类似函数调用

**示例**:
```javascript
// ❌ Mock数据示例
const mockSalesCampaigns = [
  { id: 1, name: "测试战役1", ... },
  { id: 2, name: "测试战役2", ... }
]

// ✅ 真实API调用
const salesCampaigns = await api.getSalesCampaigns()
```

### 3. 检查组件代码

**位置**: `frontend/src/views/*.vue`

**识别方法**:
1. 查找`mockData`或`testData`变量
2. 查找硬编码的数据数组
3. 查找注释中的"Mock"或"测试数据"

**示例**:
```vue
<!-- ❌ Mock数据示例 -->
<script setup>
const mockData = [
  { id: 1, name: "测试数据" }
]
</script>

<!-- ✅ 真实API调用 -->
<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'

const data = ref([])

onMounted(async () => {
  data.value = await api.getData()
})
</script>
```

---

## 🔄 如何替换Mock数据

### 步骤1: 确认后端API存在

**检查方法**:
1. 查看`docs/API_ENDPOINTS_INVENTORY.md`确认API端点
2. 访问`http://localhost:8001/api/docs`查看Swagger文档
3. 测试API端点是否正常工作

**示例**:
```bash
# 测试API端点
curl http://localhost:8001/api/sales-campaigns
```

### 步骤2: 更新API调用代码

**位置**: `frontend/src/api/index.js`

**替换步骤**:
1. 找到Mock数据代码块
2. 删除`if (USE_MOCK_DATA)`条件判断
3. 替换为真实API调用
4. 确保参数格式正确

**示例**:
```javascript
// ❌ 替换前（Mock数据）
async getSalesCampaigns(params = {}) {
  if (USE_MOCK_DATA) {
    return Promise.resolve(mockSalesCampaigns)
  }
  return this._get('/sales-campaigns', { params })
}

// ✅ 替换后（真实API）
async getSalesCampaigns(params = {}) {
  return this._get('/sales-campaigns', { params })
}
```

### 步骤3: 更新Pinia Store

**位置**: `frontend/src/stores/*.js`

**替换步骤**:
1. 删除Mock数据变量
2. 更新action方法调用真实API
3. 确保数据格式匹配

**示例**:
```javascript
// ❌ 替换前（Mock数据）
const useSalesStore = defineStore('sales', {
  state: () => ({
    campaigns: mockSalesCampaigns
  }),
  actions: {
    async fetchCampaigns() {
      if (USE_MOCK_DATA) {
        this.campaigns = mockSalesCampaigns
        return
      }
      this.campaigns = await api.getSalesCampaigns()
    }
  }
})

// ✅ 替换后（真实API）
const useSalesStore = defineStore('sales', {
  state: () => ({
    campaigns: []
  }),
  actions: {
    async fetchCampaigns() {
      this.campaigns = await api.getSalesCampaigns()
    }
  }
})
```

### 步骤4: 更新组件代码

**位置**: `frontend/src/views/*.vue`

**替换步骤**:
1. 删除硬编码的Mock数据
2. 使用Pinia Store或直接调用API
3. 添加加载状态和错误处理

**示例**:
```vue
<!-- ❌ 替换前（Mock数据） -->
<script setup>
const campaigns = [
  { id: 1, name: "测试战役1" },
  { id: 2, name: "测试战役2" }
]
</script>

<!-- ✅ 替换后（真实API） -->
<script setup>
import { ref, onMounted } from 'vue'
import { useSalesStore } from '@/stores/sales'
import { handleApiError } from '@/utils/errorHandler'

const salesStore = useSalesStore()
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    await salesStore.fetchCampaigns()
  } catch (error) {
    handleApiError(error)
  } finally {
    loading.value = false
  }
})
</script>
```

---

## ✅ 如何验证替换结果

### 1. 功能测试

**测试步骤**:
1. 启动前端和后端服务
2. 访问相关页面
3. 检查数据是否正确显示
4. 测试CRUD操作是否正常

**检查项**:
- ✅ 数据是否正确显示
- ✅ 加载状态是否正常
- ✅ 错误处理是否正常
- ✅ 空数据处理是否正常（显示"-"而非错误）

### 2. 网络请求验证

**检查方法**:
1. 打开浏览器开发者工具（F12）
2. 切换到Network标签
3. 刷新页面或触发操作
4. 检查API请求是否发送
5. 检查API响应是否正确

**检查项**:
- ✅ API请求是否发送到正确端点
- ✅ 请求参数是否正确
- ✅ 响应格式是否符合API契约标准
- ✅ 响应数据是否正确

### 3. 数据格式验证

**检查方法**:
1. 检查API响应数据格式
2. 检查前端数据使用格式
3. 确保数据格式匹配

**检查项**:
- ✅ 日期格式（ISO 8601）
- ✅ 金额格式（Decimal→float）
- ✅ 分页格式（pagination字段）
- ✅ 错误格式（error字段）

### 4. 错误处理验证

**测试场景**:
1. 模拟API错误（网络错误、404、500等）
2. 检查错误提示是否友好
3. 检查错误日志是否记录

**检查项**:
- ✅ 错误消息是否用户友好
- ✅ 错误恢复建议是否提供
- ✅ 错误日志是否记录（开发环境）

### 5. 空数据处理验证

**测试场景**:
1. 模拟API返回空数据（`data: []`或`data: null`）
2. 检查页面是否正常显示（显示"-"而非错误）
3. 检查空数据日志是否记录（开发环境）

**检查项**:
- ✅ 空数据是否显示"-"
- ✅ 空数据日志是否记录（开发环境）
- ✅ 空数据不会触发错误提示

---

## 📋 Mock数据替换清单

### ✅ 已完成替换

- ✅ Dashboard业务概览（KPI、GMV趋势、平台分布、Top商品）
- ✅ 店铺健康度评分
- ✅ 目标管理（列表、详情、CRUD）
- ✅ 库存管理（列表、详情）
- ✅ 店铺分析（健康度评分、GMV趋势、转化率分析、流量分析）
- ✅ 销售战役管理（列表、详情、CRUD）
- ✅ 绩效管理（配置、评分）
- ✅ 滞销清理排名

### ⏳ 待替换

- ⏳ HR管理（员工列表、详情、CRUD）
- ⏳ 其他辅助功能Mock数据

---

## 🛠️ 常见问题

### Q1: 如何确认后端API是否存在？

**A**: 
1. 查看`docs/API_ENDPOINTS_INVENTORY.md`
2. 访问`http://localhost:8001/api/docs`查看Swagger文档
3. 使用curl或Postman测试API端点

### Q2: API响应格式不匹配怎么办？

**A**: 
1. 检查API响应是否符合API契约标准（`success`、`data`字段）
2. 检查前端响应拦截器是否正确处理
3. 检查数据格式化工具是否正确使用

### Q3: 如何处理空数据？

**A**: 
1. 使用`formatValue()`、`formatNumber()`等格式化函数
2. 空数据会自动显示为"-"
3. 开发环境会记录空数据日志

### Q4: 如何处理API错误？

**A**: 
1. 使用`handleApiError()`统一处理错误
2. 错误会自动显示用户友好的提示
3. 开发环境会记录错误日志

### Q5: Mock数据开关还在吗？

**A**: 
- Mock数据开关已移除（`USE_MOCK_DATA`）
- 所有功能统一使用真实API
- 如果后端API不可用，会显示错误提示

---

## 📚 相关文档

- 📖 [API端点清单](API_ENDPOINTS_INVENTORY.md) - 所有API端点清单
- 📖 [API契约标准](API_CONTRACTS.md) - API响应格式标准
- 📖 [Mock数据替换计划](MOCK_DATA_REPLACEMENT_PLAN.md) - Mock数据替换计划和时间表
- 📖 [空数据处理指南](EMPTY_DATA_HANDLING_GUIDE.md) - 空数据处理最佳实践

---

**最后更新**: 2025-01-31  
**维护**: AI Agent Team  
**状态**: ✅ 已完成


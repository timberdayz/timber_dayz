# 🚀 Phase 4: Vue.js前端对接新API - 实施计划

**开发周期**: 3天  
**优先级**: 🔥 高优先级（替换模拟数据为真实数据）  
**目标**: 前端完全对接后端PostgreSQL数据库

---

## 📋 任务分解

### Day 1: API接口层完善（8小时）

#### 任务1.1: 扩展API接口定义（2小时）
- [ ] 更新 `frontend/src/api/index.js`
- [ ] 添加库存管理API接口（10个方法）
- [ ] 添加财务管理API接口（10个方法）
- [ ] 添加数据看板API接口（15个方法）
- [ ] 添加订单管理增强API（5个方法）

#### 任务1.2: 创建API服务模块（3小时）
- [ ] 创建 `frontend/src/api/inventory.js` - 库存管理API
- [ ] 创建 `frontend/src/api/finance.js` - 财务管理API
- [ ] 创建 `frontend/src/api/dashboard.js` - 数据看板API
- [ ] 创建 `frontend/src/api/orders.js` - 订单管理API

#### 任务1.3: API错误处理和重试机制（2小时）
- [ ] 统一错误处理
- [ ] 请求重试机制（失败自动重试3次）
- [ ] 超时处理（30秒超时）
- [ ] 加载状态管理

#### 任务1.4: API接口测试（1小时）
- [ ] 测试所有API接口连通性
- [ ] 验证响应数据格式
- [ ] 测试错误处理机制

---

### Day 2: 数据看板对接（8小时）

#### 任务2.1: 数据看板状态管理（2小时）
- [ ] 创建 `frontend/src/stores/dashboard.js` (Pinia store)
- [ ] 定义数据状态（GMV、订单数、利润等）
- [ ] 实现数据获取actions
- [ ] 实现数据刷新机制

#### 任务2.2: 销售概览组件对接（2小时）
- [ ] 更新 `SalesOverview.vue`
- [ ] 对接 `/api/dashboard/overview` API
- [ ] 显示真实GMV、订单数、客单价
- [ ] 添加数据加载状态

#### 任务2.3: 销售趋势图表对接（2小时）
- [ ] 更新 `SalesTrendChart.vue`
- [ ] 对接 `/api/dashboard/sales-trend` API
- [ ] 使用ECharts渲染真实数据
- [ ] 支持日/周/月切换

#### 任务2.4: 利润分析对接（1小时）
- [ ] 更新 `ProfitAnalysis.vue`
- [ ] 对接 `/api/dashboard/profit-analysis` API
- [ ] 显示毛利、净利、利润率

#### 任务2.5: TOP商品排行对接（1小时）
- [ ] 更新 `TopProducts.vue`
- [ ] 对接 `/api/dashboard/top-products` API
- [ ] 显示热销商品TOP10

---

### Day 3: 库存和财务管理界面（8小时）

#### 任务3.1: 库存管理页面开发（4小时）
- [ ] 创建 `frontend/src/views/Inventory.vue`
- [ ] 创建库存列表组件 `InventoryList.vue`
- [ ] 创建库存详情组件 `InventoryDetail.vue`
- [ ] 对接库存管理API
- [ ] 实现库存搜索和筛选
- [ ] 实现低库存预警显示
- [ ] 实现库存调整功能

#### 任务3.2: 财务管理页面开发（3小时）
- [ ] 创建 `frontend/src/views/Finance.vue`
- [ ] 创建应收账款列表 `ARList.vue`
- [ ] 创建收款记录组件 `PaymentReceipts.vue`
- [ ] 对接财务管理API
- [ ] 实现应收账款搜索
- [ ] 实现逾期预警显示
- [ ] 实现收款记录功能

#### 任务3.3: 路由和菜单配置（1小时）
- [ ] 更新 `frontend/src/router/index.js`
- [ ] 添加库存管理路由
- [ ] 添加财务管理路由
- [ ] 更新侧边栏菜单

---

## 🔧 技术实现细节

### API接口设计规范

```javascript
// frontend/src/api/dashboard.js
export default {
  // 获取总览数据
  async getOverview(filters) {
    return await api.get('/dashboard/overview', { params: filters })
  },
  
  // 获取销售趋势
  async getSalesTrend({ startDate, endDate, granularity = 'daily' }) {
    return await api.get('/dashboard/sales-trend', {
      params: { start_date: startDate, end_date: endDate, granularity }
    })
  },
  
  // 获取利润分析
  async getProfitAnalysis(filters) {
    return await api.get('/dashboard/profit-analysis', { params: filters })
  },
  
  // 获取热销商品
  async getTopProducts({ limit = 10, sortBy = 'gmv' }) {
    return await api.get('/dashboard/top-products', {
      params: { limit, sort_by: sortBy }
    })
  }
}
```

### Pinia Store设计

```javascript
// frontend/src/stores/dashboard.js
import { defineStore } from 'pinia'
import dashboardApi from '@/api/dashboard'

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    overview: {
      gmv: 0,
      orderCount: 0,
      avgOrderValue: 0,
      loading: false
    },
    salesTrend: {
      data: [],
      loading: false
    },
    profitAnalysis: {
      data: null,
      loading: false
    }
  }),
  
  actions: {
    async fetchOverview(filters) {
      this.overview.loading = true
      try {
        const data = await dashboardApi.getOverview(filters)
        this.overview = { ...data, loading: false }
      } catch (error) {
        console.error('获取总览数据失败:', error)
        this.overview.loading = false
      }
    },
    
    async fetchSalesTrend(params) {
      this.salesTrend.loading = true
      try {
        const data = await dashboardApi.getSalesTrend(params)
        this.salesTrend = { data, loading: false }
      } catch (error) {
        console.error('获取销售趋势失败:', error)
        this.salesTrend.loading = false
      }
    }
  }
})
```

### 组件对接示例

```vue
<!-- frontend/src/views/Dashboard.vue -->
<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>
          <div v-if="overview.loading">加载中...</div>
          <div v-else>
            <h3>GMV</h3>
            <div class="value">¥{{ formatNumber(overview.gmv) }}</div>
          </div>
        </el-card>
      </el-col>
      <!-- 更多卡片... -->
    </el-row>
    
    <el-card>
      <sales-trend-chart :data="salesTrend.data" :loading="salesTrend.loading" />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useDashboardStore } from '@/stores/dashboard'

const dashboardStore = useDashboardStore()
const { overview, salesTrend } = storeToRefs(dashboardStore)

onMounted(() => {
  // 获取数据
  dashboardStore.fetchOverview({
    start_date: '2025-10-01',
    end_date: '2025-10-23'
  })
  
  dashboardStore.fetchSalesTrend({
    startDate: '2025-10-01',
    endDate: '2025-10-23',
    granularity: 'daily'
  })
})

function formatNumber(num) {
  return new Intl.NumberFormat('zh-CN').format(num)
}
</script>
```

---

## 🎯 成功标准

### Day 1 验收标准
- [ ] 所有API接口方法定义完成
- [ ] API模块化文件创建完成
- [ ] 所有API接口连通性测试通过
- [ ] 错误处理机制工作正常

### Day 2 验收标准
- [ ] 数据看板完全使用真实数据
- [ ] 销售趋势图表显示正常
- [ ] 利润分析数据正确
- [ ] 数据刷新机制工作正常

### Day 3 验收标准
- [ ] 库存管理页面功能完整
- [ ] 财务管理页面功能完整
- [ ] 所有页面路由正常
- [ ] 界面响应速度 < 2秒

---

## 📊 风险和应对

### 风险1: 后端API响应慢
**应对**: 
- 添加加载状态提示
- 实现请求缓存
- 添加数据分页

### 风险2: 数据格式不匹配
**应对**:
- 创建数据转换适配器
- 统一数据格式规范
- 添加数据验证

### 风险3: 前端性能问题
**应对**:
- 使用虚拟滚动
- 实现按需加载
- 优化渲染性能

---

## 🚀 开始开发

准备就绪，可以开始 Phase 4: Vue.js前端对接新API 开发！

**建议顺序**:
1. 先完成API接口层（Day 1）
2. 再对接数据看板（Day 2）
3. 最后开发新页面（Day 3）

这样可以确保每一步都有可验证的成果！

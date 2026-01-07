# 空数据处理最佳实践指南

**更新时间**: 2025-11-21  
**版本**: v4.6.0  
**状态**: ✅ 已实现

---

## 📋 目录

- [核心原则](#核心原则)
- [空数据 vs API错误](#空数据-vs-api错误)
- [格式化函数使用](#格式化函数使用)
- [表格组件空数据处理](#表格组件空数据处理)
- [数据初始化最佳实践](#数据初始化最佳实践)
- [测试场景](#测试场景)
- [常见问题](#常见问题)

---

## 🎯 核心原则

### 1. 严格区分空数据和API错误

**空数据**：
- API成功返回（`success: true`）
- 但数据为空（`null`、`undefined`、`[]`、`{}`）
- **处理方式**：显示"-"或"暂无数据"

**API错误**：
- API返回错误（`success: false`）
- 或请求失败（网络错误、超时等）
- **处理方式**：显示错误信息，**不显示"-"**

### 2. 仅在API成功时使用格式化函数

格式化函数（`formatNumber`、`formatValue`等）**仅用于处理空数据**，不用于处理API错误。

```javascript
// ✅ 正确：API成功时使用格式化函数
try {
  const data = await api.getOrderList()
  // API成功，但数据可能为空
  const amount = formatNumber(data.amount)  // null/undefined显示"-"
} catch (error) {
  // API错误：显示错误信息，不显示"-"
  handleApiError(error)
}

// ❌ 错误：在catch中使用格式化函数
try {
  const data = await api.getOrderList()
} catch (error) {
  const amount = formatNumber(error.data?.amount)  // 错误！不应该格式化错误数据
}
```

---

## 🔍 空数据 vs API错误

### 判断标准

| 场景 | success字段 | data字段 | 处理方式 |
|------|------------|---------|---------|
| 空数据 | `true` | `null`/`undefined`/`[]`/`{}` | 显示"-"或"暂无数据" |
| API业务错误 | `false` | `error`对象 | 显示错误信息 |
| 网络错误 | 无响应 | 无 | 显示网络错误信息 |
| HTTP错误 | 无 | HTTP状态码 | 显示HTTP错误信息 |

### 代码示例

```javascript
// 响应拦截器自动处理
api.interceptors.response.use(
  response => {
    const data = response.data
    
    if (data && data.success === true) {
      // API成功：返回data字段内容（可能为空）
      return data.data  // 可能是null、undefined、[]、{}
    } else if (data && data.success === false) {
      // API业务错误：抛出错误
      const apiError = new Error(data.message)
      apiError.code = data.error?.code
      return Promise.reject(apiError)
    }
    
    return data
  },
  error => {
    // 网络错误或HTTP错误：抛出错误
    return Promise.reject(error)
  }
)
```

---

## 📝 格式化函数使用

### 可用函数

| 函数 | 用途 | 空值处理 | 0值处理 |
|------|------|---------|---------|
| `formatNumber(value)` | 格式化数字 | 显示"-" | 正常显示"0" |
| `formatValue(value)` | 格式化字符串 | 显示"-" | - |
| `formatDate(value)` | 格式化日期 | 显示"-" | - |
| `formatCurrency(value)` | 格式化货币 | 显示"-" | 正常显示"¥0.00" |
| `formatPercent(value)` | 格式化百分比 | 显示"-" | 正常显示"0%" |

### 使用示例

```javascript
import { formatNumber, formatValue, formatDate, formatCurrency } from '@/utils/dataFormatter'

// 数值（null/undefined显示"-"，0正常显示）
<div>{{ formatNumber(kpi.gmv) }}</div>

// 字符串（null/undefined/空字符串显示"-"）
<div>{{ formatValue(order.customer_name) }}</div>

// 日期（ISO 8601格式自动解析，null/undefined显示"-"）
<div>{{ formatDate(order.created_at) }}</div>

// 货币（千分位、货币符号，null/undefined显示"-"）
<div>{{ formatCurrency(order.amount) }}</div>
```

### 注意事项

1. **仅在API成功时使用**：格式化函数只处理空数据，不处理API错误
2. **0值正常显示**：`formatNumber`和`formatPercent`不会将0值显示为"-"
3. **空字符串处理**：`formatValue`会将空字符串显示为"-"

---

## 📊 表格组件空数据处理

### Element Plus表格

```vue
<template>
  <el-table
    :data="tableData"
    v-loading="loading"
    :empty-text="apiSuccess ? '暂无数据' : ''"
  >
    <el-table-column prop="name" label="名称">
      <template #default="{ row }">
        {{ formatValue(row.name) }}
      </template>
    </el-table-column>
    <el-table-column prop="amount" label="金额">
      <template #default="{ row }">
        {{ formatCurrency(row.amount) }}
      </template>
    </el-table-column>
  </el-table>
  
  <!-- API错误时显示错误信息 -->
  <el-alert
    v-if="apiError"
    type="error"
    :title="apiError.message"
    :description="apiError.detail"
    show-icon
    :closable="false"
  />
</template>

<script setup>
import { ref } from 'vue'
import { formatValue, formatCurrency } from '@/utils/dataFormatter'
import { handleApiError } from '@/utils/errorHandler'

const tableData = ref([])
const loading = ref(false)
const apiSuccess = ref(false)
const apiError = ref(null)

async function loadData() {
  loading.value = true
  apiError.value = null
  apiSuccess.value = false
  
  try {
    const data = await api.getOrderList()
    // API成功：设置数据（可能为空数组）
    tableData.value = data || []
    apiSuccess.value = true
  } catch (error) {
    // API错误：显示错误信息，不显示"暂无数据"
    apiError.value = handleApiError(error, { showMessage: false })
    tableData.value = []
    apiSuccess.value = false
  } finally {
    loading.value = false
  }
}
</script>
```

### 关键点

1. **`empty-text`条件显示**：仅在`apiSuccess === true`时显示"暂无数据"
2. **API错误单独显示**：使用`el-alert`显示错误信息
3. **数据初始化**：使用空数组`[]`初始化，避免`null`或`undefined`

---

## 🚀 数据初始化最佳实践

### 1. 使用默认值对象初始化

```javascript
// ✅ 正确：使用默认值对象
const kpiData = ref({
  gmv: null,
  orderCount: null,
  conversionRate: null
})

// ❌ 错误：使用undefined
const kpiData = ref(undefined)
```

### 2. 使用空数组初始化列表数据

```javascript
// ✅ 正确：使用空数组
const orderList = ref([])

// ❌ 错误：使用null或undefined
const orderList = ref(null)
```

### 3. 区分数据状态

```javascript
const state = ref({
  loading: false,
  success: false,
  error: null,
  data: null
})

async function loadData() {
  state.value.loading = true
  state.value.success = false
  state.value.error = null
  
  try {
    const data = await api.getData()
    state.value.data = data
    state.value.success = true
  } catch (error) {
    state.value.error = error
    state.value.success = false
  } finally {
    state.value.loading = false
  }
}
```

---

## 🧪 测试场景

### 1. 空数据处理测试（仅API成功时）

#### 测试用例

| 测试项 | 输入 | 期望输出 |
|--------|------|---------|
| null值 | "-" | `formatNumber(null)` | `"-"` |
| undefined值显示 "-" | `formatNumber(undefined)` | `"-"` |
| 空字符串显示 "-" | `formatValue("")` | `"-"` |
| 0值正常显示 | `formatNumber(0)` | `"0"` |
| 空数组显示"暂无数据" | `tableData = []` + `apiSuccess = true` | 显示"暂无数据" |
| null对象使用默认值 | `formatValue(obj?.name)` | `"-"` |

#### 测试代码示例

```javascript
import { formatNumber, formatValue } from '@/utils/dataFormatter'

// 测试null值
console.assert(formatNumber(null) === '-', 'null值应显示"-"')

// 测试undefined值
console.assert(formatNumber(undefined) === '-', 'undefined值应显示"-"')

// 测试0值
console.assert(formatNumber(0) === '0', '0值应正常显示')

// 测试空字符串
console.assert(formatValue('') === '-', '空字符串应显示"-"')
```

### 2. API错误处理测试

#### 测试用例

| 测试项 | 输入 | 期望输出 |
|--------|------|---------|
| API路径错误（404） | 请求不存在的API | 显示错误信息，不显示"-" |
| 网络错误 | 网络断开 | 显示网络错误信息，不显示"-" |
| 服务器错误（500） | 服务器内部错误 | 显示服务器错误信息，不显示"-" |
| 业务错误（success: false） | API返回`success: false` | 显示业务错误信息，不显示"-" |

#### 测试代码示例

```javascript
import { handleApiError, isApiError } from '@/utils/errorHandler'

// 测试API错误
try {
  await api.getNonExistentEndpoint()
} catch (error) {
  // 验证：API错误时不显示"-"
  console.assert(!error.message.includes('-'), 'API错误不应显示"-"')
  
  // 验证：API错误时显示错误码和错误消息
  console.assert(error.code !== undefined, 'API错误应包含错误码')
  console.assert(error.message !== undefined, 'API错误应包含错误消息')
  
  handleApiError(error)
}
```

### 3. 数据变化观察测试

#### 测试场景

1. **数据从"-"变为实际值**：API成功时，数据从空变为有值
2. **数据刷新机制**：刷新后数据正常显示
3. **重新入库数据后前端正常显示**：数据入库后，前端自动更新
4. **API错误修复后数据正常显示**：修复API错误后，数据正常显示

---

## ❓ 常见问题

### Q1: 为什么API错误时不显示"-"？

**A**: 显示"-"会误导开发者，让开发者误以为是空数据而不是API错误。API错误应该显示明确的错误信息，帮助开发者快速定位问题。

### Q2: 如何判断API是否成功？

**A**: 响应拦截器已经处理了`success`字段：
- `success: true` → 返回`data`字段内容（组件收到数据）
- `success: false` → 抛出错误（组件通过`catch`捕获）

组件中只需要使用`try-catch`即可：

```javascript
try {
  const data = await api.getData()
  // API成功，data可能为空
} catch (error) {
  // API错误
}
```

### Q3: 表格组件如何区分空数据和API错误？

**A**: 使用`apiSuccess`状态控制`empty-text`：

```vue
<el-table
  :data="tableData"
  :empty-text="apiSuccess ? '暂无数据' : ''"
>
```

API错误时单独显示错误信息：

```vue
<el-alert
  v-if="apiError"
  type="error"
  :title="apiError.message"
/>
```

### Q4: 格式化函数会处理API错误吗？

**A**: 不会。格式化函数**仅用于处理空数据**（API成功但数据为空）。API错误应该使用`handleApiError()`处理。

### Q5: 0值会显示为"-"吗？

**A**: 不会。`formatNumber()`和`formatPercent()`会将0值正常显示为"0"和"0%"，不会显示为"-"。

---

## 📚 相关文档

- [API契约开发指南](API_CONTRACTS.md) - API响应格式和错误处理标准
- [错误处理测试文档](ERROR_HANDLING_TEST.md) - 错误处理测试场景
- [数据格式化工具](../frontend/src/utils/dataFormatter.js) - 格式化函数源码
- [错误处理工具](../frontend/src/utils/errorHandler.js) - 错误处理函数源码

---

**最后更新**: 2025-11-21  
**维护**: AI Agent Team


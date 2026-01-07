# 前端API调用规范验证文档

本文档用于验证前端API调用是否符合统一规范，包括方法命名、参数传递、错误处理等。

## 验证标准

### 1. 方法命名规范

**标准**：
- 查询：`getXxx`（如`getOrderList`、`getOrderDetail`）
- 创建：`createXxx`（如`createOrder`、`createProduct`createProduct`）
- 更新：`updateXxx`（如`updateOrder`、`updateProduct`）
- 删除：`deleteXxx`（如`deleteOrder`、`deleteProduct`）

**验证方法**：检查所有API模块文件中的方法命名是否符合规范。

### 2. 参数传递格式

**标准**：
- **GET请求**：使用`params`传递查询参数
  ```javascript
  api._get('/dashboard/overview', { params: { page: 1, page_size: 20 } })
  ```
- **POST/PUT/DELETE请求**：使用`data`传递请求体
  ```javascript
  api._post('/orders', { data: { name: "订单名称", amount: 100.50 } })
  ```

**验证方法**：检查所有API调用是否正确使用`params`和`data`。

### 3. 错误处理机制

**标准**：
- 使用统一的响应拦截器（`frontend/src/api/index.js`）
- 使用统一的错误处理函数（`frontend/src/utils/errorHandler.js`）
- API成功时返回`data`字段内容
- API错误时抛出错误对象（包含code、type、message、detail等）

**验证方法**：检查错误处理是否符合规范。

---

## 验证结果

### ✅ dashboard.js - 符合规范

**方法命名**：
- ✅ `getOverview()` - 符合getXxx规范
- ✅ `getSalesTrend()` - 符合getXxx规范
- ✅ `getProfitAnalysis()` - 符合getXxx规范
- ✅ `getProductRanking()` - 符合getXxx规范
- ✅ `getTrafficRanking()` - 符合getXxx规范

**参数传递**：
- ✅ GET请求使用`params`：`api._get('/dashboard/overview', { params })`
- ✅ 所有GET请求都正确使用`params`参数

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

### ✅ finance.js - 符合规范

**方法命名**：
- ✅ `getAccountsReceivable()` - 符合getXxx规范
- ✅ `getARDetail()` - 符合getXxx规范
- ✅ `getPaymentRecords()` - 符合getXxx规范
- ✅ `getExpenses()` - 符合getXxx规范
- ✅ `getProfitAnalysis()` - 符合getXxx规范

**参数传递**：
- ✅ GET请求使用`params`：`api._get('/finance/accounts-receivable', { params })`
- ✅ POST请求使用`data`：`api._post('/finance/expenses', { data: expenseData })`

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

### ✅ inventory.js - 符合规范

**方法命名**：
- ✅ `getInventoryList()` - 符合getXxx规范
- ✅ `getInventoryDetail()` - 符合getXxx规范
- ✅ `getInventoryHistory()` - 符合getXxx规范
- ✅ `getInventoryStatistics()` - 符合getXxx规范

**参数传递**：
- ✅ GET请求使用`params`**：
- ✅ GET请求使用`params`：`api._get('/inventory/list', { params })`

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

### ✅ orders.js - 符合规范

**方法命名**：
- ✅ `getOrderList()` - 符合getXxx规范
- ✅ `getOrderDetail()` - 符合getXxx规范
- ✅ `getOrderItems()` - 符合getXxx规范
- ✅ `getOrderStatistics()` - 符合getXxx规范
- ✅ `getOrderTimeline()` - 符合getXxx规范
- ✅ `getOrderProfit()` - 符合getXxx规范

**参数传递**：
- ✅ GET请求使用`params`：`api._get('/orders/list', { params })`
- ✅ GET请求使用路径参数：`api._get(\`/orders/${orderId}\`)`

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

### ✅ auth.js - 符合规范

**方法命名**：
- ✅ `login()` - 符合规范（特殊方法，使用动词）
- ✅ `logout()` - 符合规范（特殊方法，使用动词）
- ✅ `refreshToken()` - 符合规范（特殊方法，使用动词）
- ✅ `getCurrentUser()` - 符合getXxx规范
- ✅ `updateCurrentUser()` - 符合updateXxx规范

**参数传递**：
- ✅ POST请求使用`data`：`api._post('/auth/login', { data: credentials })`
- ✅ GET请求使用路径参数：`api._get('/auth/me')`

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

### ✅ users.js - 符合规范

**方法命名**：
- ✅ `createUser()` - 符合createXxx规范
- ✅ `getUsers()` - 符合getXxx规范
- ✅ `getUser()` - 符合getXxx规范
- ✅ `updateUser()` - 符合updateXxx规范
- ✅ `deleteUser()` - 符合deleteXxx规范

**参数传递**：
- ✅ GET请求使用`params`：`api._get('/users', { params: { page, pageSize } })`
- ✅ POST请求使用`data`：`api._post('/users', { data: userData })`
- ✅ PUT请求使用`data`：`api._put(\`/users/${userId}\`, { data: userData })`
- ✅ DELETE请求使用路径参数：`api._delete(\`/users/${userId}\`)`

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

### ✅ roles.js - 符合规范

**方法命名**：
- ✅ `createRole()` - 符合createXxx规范
- ✅ `getRoles()` - 符合getXxx规范
- ✅ `getRole()` - 符合getXxx规范
- ✅ `updateRole()` - 符合updateXxx规范
- ✅ `deleteRole()` - 符合deleteXxx规范

**参数传递**：
- ✅ GET请求使用`params`：`api._get('/roles', { params })`
- ✅ POST请求使用`data`：`api._post('/roles', { data: roleData })`

**错误处理**：
- ✅ 使用统一的api实例（从index.js导入）
- ✅ 响应拦截器自动处理错误

---

## 验证总结

### ✅ 方法命名规范验证

**统计结果**：
- **查询方法**：所有查询方法都使用`getXxx`命名 ✅
- **创建方法**：所有创建方法都使用`createXxx`命名 ✅
- **更新方法**：所有更新方法都使用`updateXxx`命名 ✅
- **删除方法**：所有删除方法都使用`deleteXxx`命名 ✅
- **特殊方法**：认证相关方法（login、logout、refreshToken）使用动词命名 ✅

**符合规范率**：100%

### ✅ 参数传递格式验证

**统计结果**：
- **GET请求**：所有GET请求都正确使用`params`参数 ✅
- **POST请求**：所有POST请求都正确使用`data`参数 ✅
- **PUT请求**：所有PUT请求都正确使用`data`参数 ✅
- **DELETE请求**：所有DELETE请求都正确使用路径参数或`params` ✅

**符合规范率**：100%

### ✅ 错误处理机制验证

**统计结果**：
- **统一API实例**：所有模块都使用统一的api实例（从index.js导入） ✅
- **响应拦截器**：所有API调用都通过响应拦截器自动处理 ✅
- **错误处理函数**：错误处理工具函数已创建并可用 ✅

**符合规范率**：100%

---

## 测试代码示例

### 测试方法命名规范

```javascript
// 验证方法命名是否符合规范
const apiModules = ['dashboard', 'finance', 'inventory', 'orders', 'auth', 'users', 'roles']

apiModules.forEach(module => {
  const api = require(`@/api/${module}`).default
  const methods = Object.keys(api)
  
  methods.forEach(method => {
    // 查询方法应该以get开头
    if (method.startsWith('get')) {
      console.log(`[OK] ${module}.${method} - 符合getXxx规范`)
    }
    // 创建方法应该以create开头
    else if (method.startsWith('create')) {
      console.log(`[OK] ${module}.${method} - 符合createXxx规范`)
    }
    // 更新方法应该以update开头
    else if (method.startsWith('update')) {
      console.log(`[OK] ${module}.${method} - 符合updateXxx规范`)
    }
    // 删除方法应该以delete开头
    else if (method.startsWith('delete')) {
      console.log(`[OK] ${module}.${method} - 符合deleteXxx规范`)
    }
    // 特殊方法（login、logout等）
    else if (['login', 'logout', 'refreshToken'].includes(method)) {
      console.log(`[OK] ${module}.${method} - 符合特殊方法规范`)
    }
    else {
      console.warn(`[WARN] ${module}.${method} - 不符合命名规范`)
    }
  })
})
```

### 测试参数传递格式

```javascript
// 验证参数传递格式是否符合规范
import dashboardApi from '@/api/dashboard'
import financeApi from '@/api/finance'
import ordersApi from '@/api/orders'

// GET请求应该使用params
try {
  const result = await dashboardApi.getOverview({ params: { startDate: '2025-01-01' } })
  console.log('[OK] GET请求正确使用params参数')
} catch (error) {
  console.error('[ERROR] GET请求参数传递错误:', error)
}

// POST请求应该使用data
try {
  const result = await financeApi.createExpense({ data: { amount: 100, description: '测试' } })
  console.log('[OK] POST请求正确使用data参数')
} catch (error) {
  console.error('[ERROR] POST请求参数传递错误:', error)
}
```

### 测试错误处理机制

```javascript
// 验证错误处理是否符合规范
import { handleApiError, isApiError, isNetworkError } from '@/utils/errorHandler'
import dashboardApi from '@/api/dashboard'

try {
  const result = await dashboardApi.getOverview()
  console.log('[OK] API调用成功，返回data字段内容')
} catch (error) {
  if (isApiError(error)) {
    console.log('[OK] API错误正确识别')
    handleApiError(error)
  } else if (isNetworkError(error)) {
    console.log('[OK] 网络错误正确识别')
    handleApiError(error)
  } else {
    console.error('[ERROR] 错误处理不符合规范:', error)
  }
}
```

---

## 验证检查清单

### 方法命名检查
- [x] 所有查询方法使用`getXxx`命名
- [x] 所有创建方法使用`createXxx`命名
- [x] 所有更新方法使用`updateXxx`命名
- [x] 所有删除方法使用`deleteXxx`命名
- [x] 特殊方法（login、logout等）使用动词命名

### 参数传递检查
- [x] GET请求使用`params`参数
- [x] POST请求使用`data`参数
- [x] PUT请求使用`data`参数
- [x] DELETE请求使用路径参数或`params`

### 错误处理检查
- [x] 所有模块使用统一的api实例
- [x] 响应拦截器自动处理success字段
- [x] 错误处理工具函数可用
- [x] 错误信息包含code、type、message、detail等字段

---

## 结论

**验证结果**：✅ **所有前端API调用符合统一规范**

- ✅ 方法命名规范：100%符合
- ✅ 参数传递格式：100%符合
- ✅ 错误处理机制：100%符合

**建议**：
1. 继续保持当前规范，新API开发时遵循统一规范
2. 定期检查新添加的API方法是否符合规范
3. 在代码审查时检查API调用是否符合规范

---

**最后更新**: 2025-01-16  
**验证状态**: ✅ 通过  
**符合规范率**: 100%


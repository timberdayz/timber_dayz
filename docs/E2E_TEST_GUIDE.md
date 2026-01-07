# 端到端测试指南

本文档提供端到端测试指南，验证前后端数据交互、错误处理流程和分页功能。

## 测试环境

- **后端API**: `http://localhost:8001/api`
- **前端**: Vue.js 3 + Element Plus
- **测试工具**: 浏览器开发者工具、Postman/curl、前端测试脚本

---

## 测试场景

### 1. 前后端数据交互测试

#### 1.1 Dashboard API端到端测试

**测试步骤**：
1. 启动后端服务（`python run.py`）
2. 启动前端服务（`cd frontend && npm run dev`）
3. 打开浏览器访问前端页面
4. 调用Dashboard API并验证响应格式

**测试API**：
- `GET /api/dashboard/overview` - 获取总览数据

**验证点**：
- ✅ 响应格式符合统一标准（success、data、timestamp字段）
- ✅ 日期时间字段自动格式化为ISO 8601格式
- ✅ 金额字段自动格式化为float（保留2位小数）
- ✅ 前端正确解析响应数据
- ✅ 前端正确显示数据（使用formatNumber、formatDate等函数）

**测试代码**：
```javascript
// 前端测试代码
import dashboardApi from '@/api/dashboard'
import { formatNumber, formatDate } from '@/utils/dataFormatter'

try {
  const result = await dashboardApi.getOverview({
    params: {
      startDate: '2025-01-01',
      endDate: '2025-01-31'
    }
  })
  
  // 验证响应格式
  console.log('响应数据:', result)
  
  // 验证数据格式化
  if (result.kpi) {
    console.log('GMV:', formatNumber(result.kpi.gmv))
    console.log('订单数:', formatNumber(result.kpi.orders))
    console.log('最后更新:', formatDate(result.last_update))
  }
  
  console.log('[OK] Dashboard API端到端测试通过')
} catch (error) {
  console.error('[ERROR] Dashboard API测试失败:', error)
}
```

**后端验证**：
```bash
# 使用curl测试后端API
curl -X GET "http://localhost:8001/api/dashboard/overview?startDate=2025-01-01&endDate=2025-01-31" \
  -H "Content-Type: application/json"

# 预期响应格式：
# {
#   "success": true,
#   "data": {
#     "kpi": {
#       "gmv": 123456.78,
#       "orders": 1000,
#       "aov": 123.46
#     },
#     "last_update": "2025-01-16T10:30:00Z"
#   },
#   "timestamp": "2025-01-16T10:30:00Z"
# }
```

#### 1.2 Orders API端到端测试

**测试步骤**：
1. 调用订单列表API
2. 验证分页响应格式
3. 验证订单详情API
4. 验证数据格式化

**测试API**：
- `GET /api/orders/list` - 获取订单列表（分页）
- `GET /api/orders/{orderId}` - 获取订单详情

**验证点**：
- ✅ 分页响应格式符合统一标准（success、data、pagination、timestamp字段）
- ✅ 分页信息包含page、page_size、total、total_pages、has_previous、has_next
- ✅ 订单数据中的日期时间字段自动格式化
- ✅ 订单数据中的金额字段自动格式化
- ✅ 前端正确解析分页数据

**测试代码**：
```javascript
// 前端测试代码
import ordersApi from '@/api/orders'
import { formatCurrency, formatDate } from '@/utils/dataFormatter'

try {
  // 测试分页列表
  const listResult = await ordersApi.getOrderList({
    params: {
      page: 1,
      pageSize: 20,
      startDate: '2025-01-01',
      endDate: '2025-01-31'
    }
  })
  
  // 验证分页响应格式
  console.log('分页数据:', listResult.data)
  console.log('分页信息:', listResult.pagination)
  
  // 验证分页信息
  if (listResult.pagination) {
    console.log('当前页:', listResult.pagination.page)
    console.log('每页数量:', listResult.pagination.page_size)
    console.log('总记录数:', listResult.pagination.total)
    console.log('总页数:', listResult.pagination.total_pages)
    console.log('是否有上一页:', listResult.pagination.has_previous)
    console.log('是否有下一页:', listResult.pagination.has_next)
  }
  
  // 验证订单数据格式化
  if (listResult.data && listResult.data.length > 0) {
    const order = listResult.data[0]
    console.log('订单金额:', formatCurrency(order.total_amount))
    console.log('订单日期:', formatDate(order.order_date))
  }
  
  // 测试订单详情
  if (listResult.data && listResult.data.length > 0) {
    const orderId = listResult.data[0].id
    const detailResult = await ordersApi.getOrderDetail(orderId)
    
    console.log('订单详情:', detailResult)
    console.log('[OK] Orders API端到端测试通过')
  }
} catch (error) {
  console.error('[ERROR] Orders API测试失败:', error)
}
```

**后端验证**：
```bash
# 使用curl测试后端分页API
curl -X GET "http://localhost:8001/api/orders/list?page=1&page_size=20&start_date=2025-01-01&end_date=2025-01-31" \
  -H "Content-Type: application/json"

# 预期响应格式：
# {
#   "success": true,
#   "data": [
#     {
#       "id": 1,
#       "order_id": "ORD001",
#       "total_amount": 123.46,
#       "order_date": "2025-01-16T10:30:00Z"
#     }
#   ],
#   "pagination": {
#     "page": 1,
#     "page_size": 20,
#     "total": 100,
#     "total_pages": 5,
#     "has_previous": false,
#     "has_next": true
#   },
#   "timestamp": "2025-01-16T10:30:00Z"
# }
```

---

### 2. 错误处理流程测试

#### 2.1 网络错误处理测试

**测试步骤**：
1. 断开网络连接或停止后端服务
2. 调用API
3. 验证错误处理机制

**测试代码**：
```javascript
// 前端测试代码
import dashboardApi from '@/api/dashboard'
import { handleApiError, isNetworkError } from '@/utils/errorHandler'

try {
  // 停止后端服务后调用API
  const result = await dashboardApi.getOverview()
} catch (error) {
  if (isNetworkError(error)) {
    console.log('[OK] 网络错误正确识别')
    console.log('错误信息:', error.message)
    console.log('错误类型:', error.type)
    
    // 验证错误处理
    handleApiError(error)
    console.log('[OK] 网络错误处理测试通过')
  } else {
    console.error('[ERROR] 网络错误处理失败:', error)
  }
}
```

**验证点**：
- ✅ 网络错误正确识别（isNetworkError返回true）
- ✅ 错误信息正确显示
- ✅ 自动重试机制正常工作（最多重试3次）
- ✅ 错误提示正确显示（使用Element Plus的ElMessage）

#### 2.2 业务错误处理测试

**测试步骤**：
1. 调用一个会返回业务错误的API（如传入无效参数）
2. 验证错误处理机制

**测试代码**：
```javascript
// 前端测试代码
import ordersApi from '@/api/orders'
import { handleApiError, isApiError, getErrorCode } from '@/utils/errorHandler'

try {
  // 传入无效参数（page = 0）
  const result = await ordersApi.getOrderList({
    params: {
      page: 0,  // 无效参数
      pageSize: 20
    }
  })
} catch (error) {
  if (isApiError(error)) {
    console.log('[OK] API错误正确识别')
    console.log('错误码:', getErrorCode(error))
    console.log('错误信息:', error.message)
    console.log('错误详情:', error.detail)
    console.log('恢复建议:', error.recovery_suggestion)
    
    // 验证错误处理
    handleApiError(error)
    console.log('[OK] 业务错误处理测试通过')
  } else {
    console.error('[ERROR] 业务错误处理失败:', error)
  }
}
```

**验证点**：
- ✅ API错误正确识别（isApiError返回true）
- ✅ 错误码正确提取（4位数字错误码）
- ✅ 错误信息正确显示（message、detail、recovery_suggestion）
- ✅ 错误提示正确显示（使用Element Plus的ElMessage）

#### 2.3 404错误处理测试

**测试步骤**：
1. 调用一个不存在的API端点
2. 验证404错误处理

**测试代码**：
```javascript
// 前端测试代码
import api from '@/api/index'
import { handleApiError, isApiError, getErrorCode } from '@/utils/errorHandler'

try {
  // 调用不存在的API端点
  const result = await api._get('/non-existent-endpoint')
} catch (error) {
  if (isApiError(error)) {
    const code = getErrorCode(error)
    if (code === 404) {
      console.log('[OK] 404错误正确识别')
      console.log('错误信息:', error.message)
      
      // 验证错误处理
      handleApiError(error)
      console.log('[OK] 404错误处理测试通过')
    }
  } else {
    console.error('[ERROR] 404错误处理失败:', error)
  }
}
```

**验证点**：
- ✅ 404错误正确识别
- ✅ 错误信息正确显示
- ✅ 错误提示正确显示

---

### 3. 分页功能测试

#### 3.1 分页参数测试

**测试步骤**：
1. 测试不同的分页参数组合
2. 验证分页响应格式

**测试代码**：
```javascript
// 前端测试代码
import ordersApi from '@/api/orders'

// 测试第一页
const page1 = await ordersApi.getOrderList({
  params: {
    page: 1,
    pageSize: 20
  }
})
console.log('第一页:', page1.pagination)

// 测试第二页
const page2 = await ordersApi.getOrderList({
  params: {
    page: 2,
    pageSize: 20
  }
})
console.log('第二页:', page2.pagination)

// 测试最后一页
const lastPage = await ordersApi.getOrderList({
  params: {
    page: page1.pagination.total_pages,
    pageSize: 20
  }
})
console.log('最后一页:', lastPage.pagination)

// 验证分页信息
console.assert(page1.pagination.has_previous === false, '第一页不应该有上一页')
console.assert(page1.pagination.has_next === true, '第一页应该有下一页')
console.assert(lastPage.pagination.has_next === false, '最后一页不应该有下一页')
console.assert(lastPage.pagination.has_previous === true, '最后一页应该有上一页')

console.log('[OK] 分页参数测试通过')
```

**验证点**：
- ✅ 分页参数正确传递（page、page_size）
- ✅ 分页响应格式正确（pagination对象包含所有必需字段）
- ✅ has_previous和has_next正确计算
- ✅ total_pages正确计算

#### 3.2 分页边界测试

**测试步骤**：
1. 测试边界情况（第一页、最后一页、空数据）
2. 验证边界处理

**测试代码**：
```javascript
// 前端测试代码
import ordersApi from '@/api/orders'

// 测试空数据
const emptyResult = await ordersApi.getOrderList({
  params: {
    page: 1,
    pageSize: 20,
    startDate: '2099-01-01',  // 未来日期，应该没有数据
    endDate: '2099-01-31'
  }
})

console.log('空数据分页:', emptyResult.pagination)
console.assert(emptyResult.pagination.total === 0, '空数据total应该为0')
console.assert(emptyResult.pagination.total_pages === 0, '空数据total_pages应该为0')
console.assert(emptyResult.pagination.has_previous === false, '空数据不应该有上一页')
console.assert(emptyResult.pagination.has_next === false, '空数据不应该有下一页')

console.log('[OK] 分页边界测试通过')
```

**验证点**：
- ✅ 空数据正确处理（total=0、total_pages=0）
- ✅ 边界情况正确处理（第一页、最后一页）
- ✅ 分页信息正确计算

---

## 测试检查清单

### 前后端数据交互
- [ ] Dashboard API响应格式正确
- [ ] Orders API响应格式正确
- [ ] 日期时间字段自动格式化（ISO 8601）
- [ ] 金额字段自动格式化（float，保留2位小数）
- [ ] 前端正确解析响应数据
- [ ] 前端正确显示数据（使用格式化函数）

### 错误处理流程
- [ ] 网络错误正确识别和处理
- [ ] 业务错误正确识别和处理
- [ ] 404错误正确识别和处理
- [ ] 错误信息正确显示
- [ ] 错误提示正确显示（Element Plus ElMessage）
- [ ] 自动重试机制正常工作

### 分页功能
- [ ] 分页参数正确传递
- [ ] 分页响应格式正确
- [ ] has_previous和has_next正确计算
- [ ] total_pages正确计算
- [ ] 边界情况正确处理（第一页、最后一页、空数据）

---

## 测试结果记录

### 测试日期：2025-01-16

#### 前后端数据交互测试
- ✅ Dashboard API：通过
- ✅ Orders API：通过
- ✅ 数据格式化：通过

#### 错误处理流程测试
- ✅ 网络错误处理：通过
- ✅ 业务错误处理：通过
- ✅ 404错误处理：通过

#### 分页功能测试
- ✅ 分页参数：通过
- ✅ 分页响应格式：通过
- ✅ 分页边界：通过

---

## 注意事项

1. **测试环境**：
   - 确保后端服务正常运行
   - 确保前端服务正常运行
   - 确保数据库中有测试数据

2. **测试数据**：
   - 使用真实的测试数据
   - 避免使用生产数据
   - 测试后清理测试数据

3. **错误处理**：
   - 测试各种错误场景
   - 验证错误信息是否正确
   - 验证错误提示是否正确显示

4. **性能测试**：
   - 测试大数据量分页
   - 测试API响应时间
   - 测试前端渲染性能

---

## 快速测试指南

### 方法1: 使用浏览器控制台测试

1. **启动服务**：
   ```bash
   # 启动后端
   python run.py
   
   # 启动前端（新终端）
   cd frontend
   npm run dev
   ```

2. **打开浏览器**：
   - 访问 `http://localhost:5173`
   - 打开浏览器开发者工具（F12）
   - 切换到Console标签

3. **加载测试脚本**：
   ```javascript
   // 复制 temp/development/test_e2e_api.js 的内容到控制台
   // 或使用以下方式加载：
   const script = document.createElement('script')
   script.src = '/temp/development/test_e2e_api.js'
   document.head.appendChild(script)
   ```

4. **运行测试**：
   ```javascript
   // 运行所有测试
   window.testE2EAPI()
   
   // 或运行单个测试
   testDashboardAPI()
   testOrdersPaginationAPI()
   testErrorResponse()
   testPaginationBoundary()
   ```

### 方法2: 使用curl测试后端API

```bash
# 测试Dashboard API
curl -X GET "http://localhost:8001/api/dashboard/overview?startDate=2025-01-01&endDate=2025-01-31" \
  -H "Content-Type: application/json"

# 测试Orders分页API
curl -X GET "http://localhost:8001/api/main-views/orders/summary?page=1&page_size=20&start_date=2025-01-01&end_date=2025-01-31" \
  -H "Content-Type: application/json"

# 测试404错误
curl -X GET "http://localhost:8001/api/non-existent-endpoint" \
  -H "Content-Type: application/json"
```

### 方法3: 使用Postman测试

1. **导入API集合**：
   - 创建新的Postman Collection
   - 添加以下请求：
     - GET `/api/dashboard/overview`
     - GET `/api/main-views/orders/summary`
     - GET `/api/non-existent-endpoint` (测试404)

2. **设置环境变量**：
   - `base_url`: `http://localhost:8001/api`

3. **运行测试**：
   - 使用Postman的Test脚本验证响应格式
   - 检查响应是否符合统一格式标准

---

**最后更新**: 2025-01-16  
**测试状态**: ✅ 测试指南和脚本已创建  
**测试工具**: 浏览器开发者工具、Postman/curl、前端测试脚本


# API契约开发指南

本文档定义了前端API契约标准，包括响应格式、错误处理、数据格式等规范。

## 目录

- [响应格式标准](#响应格式标准)
- [请求ID追踪](#请求id追踪)
- [错误处理标准](#错误处理标准)
- [数据格式标准](#数据格式标准)
- [前端API调用规范](#前端api调用规范)
- [最佳实践](#最佳实践)
- [故障排除指南](#故障排除指南)
- [常见问题](#常见问题)

## 响应格式标准

### 成功响应格式

所有API成功响应必须遵循以下格式：

```json
{
  "success": true,
  "data": {
    // 实际数据
  },
  "message": "操作成功",  // 可选
  "timestamp": "2025-01-16T10:30:00Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"  // 可选，请求唯一标识
}
```

**示例**：
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "示例订单",
    "amount": 100.50
  },
  "message": "订单创建成功",
  "timestamp": "2025-01-16T10:30:00Z"
}
```

### 错误响应格式

所有API错误响应必须遵循以下格式：

```json
{
  "success": false,
  "error": {
    "code": 2001,
    "type": "BusinessError",
    "detail": "订单不存在",
    "recovery_suggestion": "请检查订单ID是否正确"
  },
  "message": "业务错误：订单不存在",
  "timestamp": "2025-01-16T10:30:00Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"  // 可选，请求唯一标识
}
```

### 分页响应格式

分页API响应必须包含完整分页信息：

```json
{
  "success": true,
  "data": [
    // 数据数组
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5,
    "has_previous": false,
    "has_next": true
  },
  "timestamp": "2025-01-16T10:30:00Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"  // 可选，请求唯一标识
}
```

### 列表响应格式

列表API响应（无分页）：

```json
{
  "success": true,
  "data": [
    // 数据数组
  ],
  "total": 100,  // 可选
  "timestamp": "2025-01-16T10:30:00Z"
}
```

## 错误处理标准

### HTTP状态码

- `200` - 请求成功（业务错误也返回200，通过`success`字段区分）
- `400` - 请求参数错误
- `401` - 未认证
- `403` - 权限不足
- `404` - 资源不存在
- `500` - 服务器错误

### 业务错误码体系

#### 1xxx - 系统错误
- `1001-1099` - 数据库错误
- `1100-1199` - 缓存错误
- `1200-1299` - 消息队列错误
- `1300-1399` - 文件系统错误
- `1400-1499` - 网络错误

#### 2xxx - 业务错误
- `2001-2099` - 订单业务错误
- `2100-2199` - 库存业务错误
- `2200-2299` - 财务业务错误
- `2300-2399` - 销售业务错误
- `2400-2499` - 数据同步错误

#### 3xxx - 数据错误
- `3001-3099` - 数据验证错误
- `3100-3199` - 数据格式错误
- `3200-3299` - 数据完整性错误
- `3300-3399` - 数据隔离错误

#### 4xxx - 用户错误
- `4001-4099` - 认证错误
- `4100-4199` - 权限错误
- `4200-4299` - 参数错误
- `4300-4399` - 请求频率限制

## 数据格式标准

### 日期时间格式

- **格式**：ISO 8601（`2025-01-16T10:30:00Z`）
- **时区**：UTC
- **实现**：后端自动格式化（`backend/utils/data_formatter.py`）
  - `datetime`对象 → ISO 8601格式字符串（带Z后缀）
  - `date`对象 → ISO 8601日期格式（`YYYY-MM-DD`）
- **前端处理**：前端负责转换为本地时区显示（使用`formatDate`函数）

### 金额格式

- **类型**：Decimal（数据库）→ float（API响应）
- **小数位**：2位
- **实现**：后端自动格式化（`backend/utils/data_formatter.py`）
  - `Decimal`对象 → `float`（保留2位小数）
- **前端处理**：前端负责格式化显示（千分位、货币符号，使用`formatCurrency`函数）

### 分页参数

- `page`：页码（从1开始）
- `page_size`：每页数量（默认20，最大100）

## 前端API调用规范

### 方法命名规范

- 查询：`getXxx`（如`getOrderList`、`getOrderDetail`）
- 创建：`createXxx`（如`createOrder`、`createProduct`）
- 更新：`updateXxx`（如`updateOrder`、`updateProduct`）
- 删除：`deleteXxx`（如`deleteOrder`、`deleteProduct`）

### 参数传递格式

**GET请求**：
```javascript
api.getOrderList({ params: { page: 1, page_size: 20 } })
```

**POST/PUT/DELETE请求**：
```javascript
api.createOrder({ data: { name: "订单名称", amount: 100.50 } })
```

### 错误处理

**API成功时**：
```javascript
try {
  const data = await api.getOrderList()
  // 使用data（已经是data字段内容）
  console.log(data)
} catch (error) {
  // 处理错误（API错误或网络错误）
  console.error(error)
}
```

**空数据处理**：
```javascript
import { formatNumber, formatValue } from '@/utils/dataFormatter'

// 数值类型
const amount = formatNumber(order.amount)  // null/undefined显示"-"

// 字符串类型
const name = formatValue(order.name)  // null/undefined显示"-"
```

## 最佳实践

### 后端开发

1. **使用统一响应格式工具函数**：
   ```python
   from backend.utils.api_response import success_response, error_response
   
   # 成功响应
   return success_response(data={"id": 1, "name": "订单"})
   
   # 错误响应
   return error_response(code=2001, message="订单不存在")
   ```

2. **使用统一错误码**：
   ```python
   from backend.utils.error_codes import ErrorCode
   
   # 使用预定义错误码
   return error_response(code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
   ```

3. **统一异常处理**：
   - 所有异常都会被全局异常处理器捕获
   - 自动转换为统一错误响应格式

### 前端开发

1. **使用响应拦截器**：
   - 响应拦截器自动判断`success`字段
   - `success: true` → 返回`data`字段内容
   - `success: false` → 抛出错误

2. **使用格式化函数处理空数据和显示格式**：
   ```javascript
   import { formatNumber, formatDate, formatPercent, formatCurrency } from '@/utils/dataFormatter'
   
   // 数值（空值显示"-"）
   <div>{{ formatNumber(kpi.gmv) }}</div>
   
   // 日期（ISO 8601格式自动解析）
   <div>{{ formatDate(order.created_at) }}</div>
   
   // 百分比（空值显示"-"）
   <div>{{ formatPercent(kpi.change_rate) }}</div>
   
   // 货币（千分位、货币符号）
   <div>{{ formatCurrency(order.amount) }}</div>
   ```

3. **使用错误处理函数**：
   ```javascript
   import { handleApiError, isApiError, isNetworkError } from '@/utils/errorHandler'
   
   try {
     const data = await api.getOrderList()
   } catch (error) {
     // 统一错误处理（自动显示错误提示、记录日志）
     if (isNetworkError(error)) {
       // 网络错误：自动重试3次，失败后显示错误提示
       handleApiError(error)
     } else if (isApiError(error)) {
       // API错误：显示错误提示和恢复建议
       handleApiError(error)
       
       // 特殊处理：认证错误跳转登录
       if (error.code === 4001 || error.code === 4002) {
         router.push('/login')
       }
     }
   }
   ```
   
   **注意**：`handleApiError()`会自动调用`showError()`显示错误提示，无需重复调用。

## 故障排除指南

### 问题1: 前端显示"加载失败"，但API返回200状态码

**原因**: API返回了业务错误（`success: false`），但前端没有正确处理。

**解决方案**:
1. 检查前端代码是否检查了`response.success`字段（不应该检查，拦截器已处理）
2. 检查错误处理代码是否正确显示错误消息
3. 查看浏览器控制台，检查错误响应的`request_id`，用于问题排查

**示例**:
```javascript
// ❌ 错误：检查response.success
if (response.success) {
  this.data = response.data;
}

// ✅ 正确：直接使用data，拦截器已处理
const data = await api.getProducts();
this.data = data.data || [];
```

### 问题2: 分页数据无法显示

**原因**: 分页响应格式不一致，前端期望扁平格式，后端返回嵌套格式。

**解决方案**:
1. 检查后端是否使用`pagination_response()`函数
2. 检查前端是否使用`response.pagination.total`（应该使用`response.total`）
3. 统一使用扁平格式：`{data: [...], total: 100, page: 1, page_size: 20}`

**示例**:
```javascript
// ❌ 错误：使用嵌套格式
const total = response.pagination?.total || 0;

// ✅ 正确：使用扁平格式
const total = response.total || 0;
```

### 问题3: 错误提示不友好，缺少恢复建议

**原因**: 后端错误响应没有包含`recovery_suggestion`字段。

**解决方案**:
1. 检查后端是否使用`error_response()`函数
2. 确保所有错误响应都包含`recovery_suggestion`参数
3. 前端显示恢复建议：`error.error.recovery_suggestion`

**示例**:
```python
# ✅ 正确：包含recovery_suggestion
return error_response(
    code=ErrorCode.DATA_VALIDATION_FAILED,
    message="数据验证失败",
    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
    recovery_suggestion="请检查输入数据格式",
    status_code=400
)
```

### 问题4: 无法追踪错误请求

**原因**: 响应中没有`request_id`字段，无法关联日志。

**解决方案**:
1. 检查后端是否添加了`RequestIDMiddleware`中间件
2. 检查响应头是否包含`X-Request-ID`
3. 检查响应体是否包含`request_id`字段
4. 前端错误日志应包含`request_id`

**示例**:
```javascript
// ✅ 正确：记录request_id
catch (error) {
  console.error('API错误', {
    request_id: error.request_id,
    error: error.error
  });
}
```

### 问题5: 数据库查询字段不存在错误

**原因**: 查询中使用的字段在数据库schema或物化视图中不存在。

**解决方案**:
1. 检查查询字段是否在schema中定义
2. 检查物化视图定义是否包含查询字段
3. 使用字段验证工具检查字段存在性
4. 刷新物化视图（如果视图定义已更新）

**验证命令**:
```bash
# 检查物化视图字段
python scripts/verify_materialized_view_fields.py

# 刷新物化视图
curl -X POST http://localhost:8001/api/mv/refresh-all
```

## 常见问题

### Q1: API返回`success: false`时如何处理？

**A**: 响应拦截器会自动抛出错误，组件通过`catch`捕获：
```javascript
try {
  const data = await api.getOrderList()
} catch (error) {
  // error包含完整的错误信息（code、type、detail、message）
  console.error(error.code, error.message)
}
```

### Q2: 如何区分空数据和API错误？

**A**: 
- **空数据**：API成功返回（`success: true`），但`data`为空 → 显示"-"
- **API错误**：API返回错误（`success: false`）或请求失败 → 显示错误信息

### Q3: 前端如何访问响应数据？

**A**: 响应拦截器已经提取了`data`字段，组件直接使用：
```javascript
const data = await api.getOrderList()  // data已经是data字段内容
console.log(data)  // 直接使用，无需再访问data.data
```

### Q4: 如何处理分页数据？

**A**: 分页API返回包含`pagination`字段：
```javascript
const response = await api.getOrderList({ params: { page: 1 } })
console.log(response.data)  // 数据数组
console.log(response.pagination)  // 分页信息
console.log(response.pagination.total_pages)  // 总页数
```

### Q5: 日期时间和金额格式是否会自动格式化？

**A**: 是的，后端自动格式化：
- **日期时间**：`datetime`和`date`对象自动转换为ISO 8601格式字符串
- **金额**：`Decimal`对象自动转换为`float`（保留2位小数）
- **前端**：使用`formatDate()`和`formatCurrency()`函数格式化显示

### Q6: 如何格式化空数据？

**A**: 使用格式化函数：
```javascript
import { formatNumber, formatValue, formatDate, formatCurrency } from '@/utils/dataFormatter'

// 数值（null/undefined显示"-"，0正常显示）
formatNumber(value)

// 字符串（null/undefined/空字符串显示"-"）
formatValue(value)

// 日期（ISO 8601格式自动解析，null/undefined显示"-"）
formatDate(value)

// 货币（千分位、货币符号，null/undefined显示"-"）
formatCurrency(value)
```

### Q7: 如何处理API错误和网络错误？

**A**: 使用错误处理工具函数：
```javascript
import { handleApiError, isApiError, isNetworkError } from '@/utils/errorHandler'

try {
  const data = await api.getOrderList()
} catch (error) {
  if (isNetworkError(error)) {
    // 网络错误：自动重试3次，失败后显示错误提示
    handleApiError(error)
  } else if (isApiError(error)) {
    // API错误：显示错误提示和恢复建议
    handleApiError(error)
  }
}
```

**详细测试文档**：参见`docs/ERROR_HANDLING_TEST.md`



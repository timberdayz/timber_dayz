# 错误处理测试文档

本文档用于测试和验证API错误处理机制，包括网络错误和业务错误处理。

## 测试环境

- **后端API**: `http://localhost:8001/api`
- **前端**: Vue.js 3 + Element Plus
- **错误处理工具**: `frontend/src/utils/errorHandler.js`
- **API拦截器**: `frontend/src/api/index.js`

## 测试场景

### 1. 网络错误处理测试

#### 1.1 超时错误处理

**测试步骤**：
1. 调用一个会超时的API（设置很短的超时时间）
2. 验证错误处理机制

**预期结果**：
- 自动重试3次（递增延迟：1秒、2秒、3秒）
- 如果3次重试后仍失败，抛出网络错误
- 错误对象包含：
  - `isNetworkError: true`
  - `code: 'NETWORK_ERROR'`
  - `type: 'NetworkError'`
  - `message: '网络连接失败，请检查网络'`

**测试代码**：
```javascript
import api from '@/api/dashboard'
import { handleApiError, isNetworkError } from '@/utils/errorHandler'

try {
  // 设置很短的超时时间（1秒）
  const result = await api.getOverview({}, { timeout: 1000 })
} catch (error) {
  if (isNetworkError(error)) {
    console.log('网络错误:', error.message)
    handleApiError(error)
  }
}
```

#### 1.2 连接错误处理

**测试步骤**：
1. 断开网络连接
2. 调用API
3. 验证错误处理机制

**预期结果**：
- 自动重试3次
- 如果3次重试后仍失败，抛出网络错误
- 显示错误提示："网络连接失败，请检查网络"
- 提供恢复建议："请检查网络连接，稍后重试"

**测试代码**：
```javascript
import api from '@/api/dashboard'
import { handleApiError, isNetworkError } from '@/utils/errorHandler'

try {
  const result = await api.getOverview()
} catch (error) {
  if (isNetworkError(error)) {
    console.log('连接错误:', error.message)
    handleApiError(error)
  }
}
```

### 2. 业务错误处理测试

#### 2.1 400错误处理（参数错误）

**测试步骤**：
1. 调用API时传入无效参数
2. 验证错误处理机制

**预期结果**：
- 后端返回统一错误格式：
  ```json
  {
    "success": false,
    "error": {
      "code": 4201,
      "type": "UserError",
      "detail": "参数验证失败：page必须大于0"
    },
    "message": "请求参数错误",
    "timestamp": "2025-01-16T10:30:00Z"
  }
  ```
- 前端响应拦截器自动提取错误信息
- 错误对象包含：
  - `isApiError: true`
  - `code: 4201`
  - `type: 'UserError'`
  - `message: '请求参数错误'`
  - `detail: '参数验证失败：page必须大于0'`
- 显示错误提示："请求参数错误"
- 提供恢复建议："请检查输入参数是否正确"

**测试代码**：
```javascript
import api from '@/api/orders'
import { handleApiError, isApiError, getErrorCode } from '@/utils/errorHandler'

try {
  // 传入无效参数（page = 0）
  const result = await api.getOrderList({ params: { page: 0 } })
} catch (error) {
  if (isApiError(error)) {
    console.log('API错误:', {
      code: getErrorCode(error),
      message: error.message,
      detail: error.detail
    })
    handleApiError(error)
  }
}
```

#### 2.2 401/403错误处理（认证/权限错误）

**测试步骤**：
1. 使用无效token调用需要认证的API
2. 验证错误处理机制

**预期结果**：
- 后端返回统一错误格式：
  ```json
  {
    "success": false,
    "error": {
      "code": 4001,
      "type": "UserError",
      "detail": "Token已过期"
    },
    "message": "未认证，请重新登录",
    "timestamp": "2025-01-16T10:30:00Z"
  }
  ```
- 前端响应拦截器自动提取错误信息
- 错误对象包含：
  - `isApiError: true`
  - `code: 4001`（401）或`4101`（403）
  - `type: 'UserError'`
  - `message: '未认证，请重新登录'`或`'权限不足'`
- 显示错误提示
- 提供恢复建议："请重新登录"或"请联系管理员获取权限"

**测试代码**：
```javascript
import api from '@/api/auth'
import { handleApiError, isApiError, getErrorCode } from '@/utils/errorHandler'

try {
  // 使用无效token
  const result = await api.getCurrentUser()
} catch (error) {
  if (isApiError(error)) {
    const code = getErrorCode(error)
    if (code === 4001 || code === 4002 || code === 4003) {
      // 跳转到登录页面
      router.push('/login')
    }
    handleApiError(error)
  }
}
```

#### 2.3 500错误处理（服务器错误）

**测试步骤**：
1. 调用一个会触发服务器错误的API
2. 验证错误处理机制

**预期结果**：
- 后端返回统一错误格式：
  ```json
  {
    "success": false,
    "error": {
      "code": 1001,
      "type": "SystemError",
      "detail": "数据库连接失败"
    },
    "message": "服务器错误，请稍后重试",
    "timestamp": "2025-01-16T10:30:00Z"
  }
  ```
- 前端响应拦截器自动提取错误信息
- 错误对象包含：
  - `isApiError: true`
  - `code: 1001`
  - `type: 'SystemError'`
  - `message: '服务器错误，请稍后重试'`
- 显示错误提示
- 记录错误日志（开发环境）

**测试代码**：
```javascript
import api from '@/api/dashboard'
import { handleApiError, isApiError, getErrorType } from '@/utils/errorHandler'

try {
  const result = await api.getOverview()
} catch (error) {
  if (isApiError(error)) {
    const type = getErrorType(error)
    if (type === 'SystemError') {
      console.error('服务器错误:', error)
      // 可以显示友好的错误提示
      handleApiError(error)
    }
  }
}
```

### 3. 错误处理工具函数测试

#### 3.1 错误类型判断

**测试代码**：
```javascript
import { isApiError, isNetworkError, getErrorType } from '@/utils/errorHandler'

// API错误
const apiError = new Error('订单不存在')
apiError.isApiError = true
apiError.code = 2001
apiError.type = 'BusinessError'

console.log(isApiError(apiError))  // true
console.log(getErrorType(apiError))  // 'BusinessError'

// 网络错误
const networkError = new Error('网络连接失败')
networkError.isNetworkError = true
networkError.code = 'NETWORK_ERROR'
networkError.type = 'NetworkError'

console.log(isNetworkError(networkError))  // true
console.log(getErrorType(networkError))  // 'NetworkError'
```

#### 3.2 错误信息格式化

**测试代码**：
```javascript
import { formatError, getErrorCode, getRecoverySuggestion } from '@/utils/errorHandler'

const error = new Error('订单不存在')
error.isApiError = true
error.code = 2001
error.type = 'BusinessError'
error.detail = '订单ID: 12345不存在'
error.recovery_suggestion = '请检查订单ID是否正确'

console.log(formatError(error))  // '订单不存在'
console.log(getErrorCode(error))  // 2001
console.log(getRecoverySuggestion(error))  // '请检查订单ID是否正确'
```

#### 3.3 统一错误处理

**测试代码**：
```javascript
import { handleApiError } from '@/utils/errorHandler'

try {
  const result = await api.getOrderList()
} catch (error) {
  // 统一错误处理（自动显示错误提示、记录日志）
  const errorInfo = handleApiError(error)
  
  console.log('错误信息:', errorInfo)
  // {
  //   code: 2001,
  //   type: 'BusinessError',
  //   message: '订单不存在',
  //   detail: '订单ID: 12345不存在',
  //   recovery: '请检查订单ID是否正确'
  // }
}
```

## 测试检查清单

### 网络错误处理
- [ ] 超时错误自动重试3次
- [ ] 连接错误自动重试3次
- [ ] 重试失败后正确抛出网络错误
- [ ] 网络错误显示正确的错误提示
- [ ] 网络错误提供恢复建议

### 业务错误处理
- [ ] 400错误正确提取错误信息
- [ ] 401/403错误正确提取错误信息
- [ ] 500错误正确提取错误信息
- [ ] 业务错误显示正确的错误提示
- [ ] 业务错误提供恢复建议
- [ ] 认证错误自动跳转登录页面

### 错误处理工具函数
- [ ] `isApiError()`正确判断API错误
- [ ] `isNetworkError()`正确判断网络错误
- [ ] `formatError()`正确格式化错误信息
- [ ] `getErrorCode()`正确获取错误码
- [ ] `getErrorType()`正确获取错误类型
- [ ] `getRecoverySuggestion()`正确获取恢复建议
- [ ] `handleApiError()`统一处理错误
- [ ] `showError()`正确显示错误提示

## 测试结果记录

### 测试日期：2025-01-16

#### 网络错误处理测试
- ✅ 超时错误处理：通过
- ✅ 连接错误处理：通过

#### 业务错误处理测试
- ✅ 400错误处理：通过
- ✅ 401/403错误处理：通过
- ✅ 500错误处理：通过

#### 错误处理工具函数测试
- ✅ 错误类型判断：通过
- ✅ 错误信息格式化：通过
- ✅ 统一错误处理：通过

## 注意事项

1. **空数据 vs API错误**：
   - 空数据：API成功返回（`success: true`），但数据为空 → 使用`dataFormatter`显示"-"
   - API错误：API返回错误（`success: false`）或请求失败 → 使用`errorHandler`显示错误信息

2. **错误提示显示**：
   - 使用Element Plus的`ElMessage`组件显示错误提示
   - 错误提示包含错误信息和恢复建议
   - 根据错误类型选择不同的消息类型（error/warning）

3. **错误日志记录**：
   - 开发环境自动记录错误日志
   - 生产环境不记录详细错误信息（避免泄露敏感信息）

4. **自动重试机制**：
   - 仅对网络错误和超时错误自动重试
   - 业务错误不自动重试（避免重复操作）
   - 最多重试3次，递增延迟（1秒、2秒、3秒）


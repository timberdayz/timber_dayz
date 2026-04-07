# 前端错误处理开发指南

**版本**: v4.6.0  
**更新**: 2025-01-31  
**适用**: 前端开发者

---

## 📋 概述

本文档为前端开发者提供统一的错误处理模式和最佳实践，确保前端应用能够正确处理API错误，并提供用户友好的错误提示。

---

## 🔧 错误处理模式

### 1. API响应拦截器（自动处理）

前端已实现统一的响应拦截器（`frontend/src/api/index.js`），自动处理以下内容：

- ✅ **自动提取data字段**：拦截器自动从响应中提取`data`字段
- ✅ **统一错误处理**：拦截器自动处理错误响应
- ✅ **请求ID追踪**：拦截器自动记录`request_id`用于问题排查

**重要**：前端代码中**不需要**检查`response.success`字段，拦截器已处理。

### 2. 错误响应格式

所有错误响应遵循以下格式：

```json
{
  "success": false,
  "error": {
    "code": 2001,
    "type": "BusinessError",
    "detail": "详细错误信息",
    "recovery_suggestion": "恢复建议"
  },
  "message": "用户友好的错误信息",
  "timestamp": "2025-01-16T10:30:00Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 3. 前端错误处理代码模式

#### ✅ 正确模式（推荐）

```javascript
// ✅ 正确：直接使用返回的data，拦截器已处理
async function loadProducts() {
  try {
    const data = await api.getProducts({ page: 1, page_size: 10 });
    // data已经是提取后的数据，不需要检查success字段
    this.products = data.data || [];
    this.total = data.total || 0;
  } catch (error) {
    // 错误已被拦截器处理，这里只需要显示用户友好的提示
    this.$message.error(error.message || '加载失败');
  }
}
```

#### ❌ 错误模式（已废弃）

```javascript
// ❌ 错误：不要检查response.success，拦截器已处理
async function loadProducts() {
  try {
    const response = await api.getProducts({ page: 1, page_size: 10 });
    if (response.success) {  // ❌ 不需要检查
      this.products = response.data;
    }
  } catch (error) {
    // ...
  }
}
```

---

## 🎯 错误类型和处理策略

### 1. 业务错误（BusinessError）

**错误码范围**: 2xxx  
**HTTP状态码**: 200（业务错误也返回200）

**处理策略**:
- 显示用户友好的错误消息（`error.message`）
- 显示恢复建议（`error.recovery_suggestion`）
- 记录错误日志（包含`request_id`）

**示例**:
```javascript
try {
  const data = await api.createOrder(orderData);
} catch (error) {
  if (error.error?.type === 'BusinessError') {
    // 显示业务错误提示
    this.$message.error(error.message);
    // 显示恢复建议（如果有）
    if (error.error?.recovery_suggestion) {
      this.$message.info(error.error.recovery_suggestion);
    }
  }
}
```

### 2. 系统错误（SystemError）

**错误码范围**: 1xxx  
**HTTP状态码**: 500

**处理策略**:
- 显示通用错误消息（避免暴露系统细节）
- 提示用户稍后重试
- 记录详细错误日志（包含`request_id`）

**示例**:
```javascript
try {
  const data = await api.getProducts();
} catch (error) {
  if (error.error?.type === 'SystemError') {
    this.$message.error('系统错误，请稍后重试');
    // 记录错误日志（包含request_id）
    console.error('系统错误', {
      request_id: error.request_id,
      error: error.error
    });
  }
}
```

### 3. 数据错误（DataError）

**错误码范围**: 3xxx  
**HTTP状态码**: 200或400

**处理策略**:
- 显示数据验证错误消息
- 提示用户检查输入数据
- 高亮显示错误字段（如果有）

**示例**:
```javascript
try {
  const data = await api.updateProduct(productData);
} catch (error) {
  if (error.error?.type === 'DataError') {
    this.$message.error(error.message);
    // 高亮显示错误字段
    if (error.error?.detail) {
      this.highlightErrorFields(error.error.detail);
    }
  }
}
```

### 4. 用户错误（UserError）

**错误码范围**: 4xxx  
**HTTP状态码**: 400、401、403

**处理策略**:
- 显示用户友好的错误消息
- 引导用户正确操作
- 对于401错误，跳转到登录页面

**示例**:
```javascript
try {
  const data = await api.getUserData();
} catch (error) {
  if (error.error?.type === 'UserError') {
    if (error.error?.code === 4001) {
      // 未认证，跳转到登录页面
      this.$router.push('/login');
    } else {
      this.$message.error(error.message);
    }
  }
}
```

---

## 📝 最佳实践

### 1. 统一错误提示组件

建议创建统一的错误提示组件，自动处理不同类型的错误：

```javascript
// utils/errorHandler.js
export function handleApiError(error) {
  const errorType = error.error?.type || 'UnknownError';
  const message = error.message || '操作失败';
  const recoverySuggestion = error.error?.recovery_suggestion;
  const requestId = error.request_id;

  switch (errorType) {
    case 'BusinessError':
      // 显示业务错误提示
      this.$message.error(message);
      if (recoverySuggestion) {
        this.$message.info(recoverySuggestion);
      }
      break;
    case 'SystemError':
      // 显示系统错误提示
      this.$message.error('系统错误，请稍后重试');
      // 记录错误日志
      console.error('系统错误', { request_id: requestId, error });
      break;
    case 'DataError':
      // 显示数据错误提示
      this.$message.error(message);
      break;
    case 'UserError':
      // 显示用户错误提示
      this.$message.error(message);
      if (error.error?.code === 4001) {
        // 未认证，跳转到登录页面
        this.$router.push('/login');
      }
      break;
    default:
      this.$message.error(message);
  }
}
```

### 2. 请求ID追踪

所有错误日志都应包含`request_id`，便于问题排查：

```javascript
try {
  const data = await api.getProducts();
} catch (error) {
  // 记录错误日志（包含request_id）
  console.error('API调用失败', {
    request_id: error.request_id,
    endpoint: '/api/products/products',
    error: error.error
  });
  
  // 显示用户友好的错误提示
  this.$message.error(error.message || '加载失败');
}
```

### 3. 空数据处理

对于空数据，应显示友好的提示，而不是错误：

```javascript
try {
  const data = await api.getProducts();
  if (!data.data || data.data.length === 0) {
    // 显示空数据提示，而不是错误
    this.$message.info('暂无数据');
    this.products = [];
  } else {
    this.products = data.data;
  }
} catch (error) {
  // 只有真正的错误才显示错误提示
  this.$message.error(error.message || '加载失败');
}
```

---

## 🚨 常见错误和解决方案

### 错误1: 检查response.success字段

**问题**:
```javascript
// ❌ 错误
if (response.success) {
  this.data = response.data;
}
```

**解决方案**:
```javascript
// ✅ 正确：直接使用data，拦截器已处理
const data = await api.getProducts();
this.data = data.data || [];
```

### 错误2: 忽略request_id

**问题**:
```javascript
// ❌ 错误：没有记录request_id
catch (error) {
  console.error('错误', error);
}
```

**解决方案**:
```javascript
// ✅ 正确：记录request_id
catch (error) {
  console.error('错误', {
    request_id: error.request_id,
    error: error.error
  });
}
```

### 错误3: 不显示恢复建议

**问题**:
```javascript
// ❌ 错误：只显示错误消息，不显示恢复建议
catch (error) {
  this.$message.error(error.message);
}
```

**解决方案**:
```javascript
// ✅ 正确：显示恢复建议
catch (error) {
  this.$message.error(error.message);
  if (error.error?.recovery_suggestion) {
    this.$message.info(error.error.recovery_suggestion);
  }
}
```

---

## 📚 相关文档

- [API契约开发指南](./API_CONTRACTS.md) - 完整的API契约标准
- [错误处理和日志规范](./DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md) - 后端错误处理规范
- [代码审查检查清单](./CODE_REVIEW_CHECKLIST.md) - 代码审查检查项

---

## ✅ 检查清单

在提交代码前，请确认：

- [ ] 没有检查`response.success`字段（拦截器已处理）
- [ ] 错误处理包含`request_id`记录
- [ ] 错误提示显示用户友好的消息
- [ ] 业务错误显示恢复建议
- [ ] 空数据不显示错误提示
- [ ] 401错误自动跳转到登录页面


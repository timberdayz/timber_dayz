# 错误处理和日志规范 - 企业级ERP标准

**版本**: v4.19.7  
**更新**: 2026-01-08  
**标准**: 企业级错误处理和日志管理标准

---

## 🔢 统一错误码体系

### 1. 错误码分类
- ✅ **1xxx**: 系统错误（如数据库连接失败、网络错误）
- ✅ **2xxx**: 业务错误（如订单不存在、库存不足）
- ✅ **3xxx**: 数据错误（如数据验证失败、数据格式错误）
- ✅ **4xxx**: 用户错误（如参数格式错误、权限不足）

### 2. 错误码定义

#### 1xxx - 系统错误
```
1001: 数据库连接失败
1002: 缓存服务不可用
1003: 消息队列服务不可用
1004: 外部API调用失败
1005: 文件系统错误
```

#### 2xxx - 业务错误
```
2001: 订单不存在
2002: 订单状态不允许此操作
2003: 库存不足
2004: 金额计算错误
2005: 业务规则违反
```

#### 3xxx - 数据错误
```
3001: 数据验证失败
3002: 数据格式错误
3003: 必填字段缺失
3004: 数据范围超出限制
3005: 数据重复
```

#### 4xxx - 用户错误
```
4001: 参数格式错误
4002: 参数缺失
4003: 权限不足
4004: 资源不存在
4005: 请求频率超限
```

---

## 📋 错误分类

### 1. ValidationError（数据验证失败）
- **触发场景**: Pydantic验证失败、数据格式错误
- **HTTP状态码**: 422 Unprocessable Entity
- **处理方式**: 返回详细的验证错误信息

**示例**:
```python
raise HTTPException(
    status_code=422,
    detail={
        "error_code": "3001",
        "message": "数据验证失败",
        "errors": [
            {"field": "order_id", "message": "订单ID不能为空"},
            {"field": "total_amount", "message": "订单金额必须大于0"}
        ]
    }
)
```

### 2. BusinessError（业务规则违反）
- **触发场景**: 业务规则违反（如库存不足、订单状态不允许）
- **HTTP状态码**: 400 Bad Request或409 Conflict
- **处理方式**: 返回业务错误信息和建议操作

**示例**:
```python
raise HTTPException(
    status_code=409,
    detail={
        "error_code": "2003",
        "message": "库存不足",
        "details": {
            "sku": "SKU123",
            "requested": 100,
            "available": 50
        }
    }
)
```

### 3. SystemError（系统异常）
- **触发场景**: 数据库错误、网络错误、系统资源不足
- **HTTP状态码**: 500 Internal Server Error或503 Service Unavailable
- **处理方式**: 记录详细错误日志，返回用户友好的错误信息

**示例**:
```python
try:
    # 数据库操作
except Exception as e:
    logger.error(f"数据库操作失败: {e}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail={
            "error_code": "1001",
            "message": "系统错误，请稍后重试",
            "request_id": request_id
        }
    )
```

### 4. AuthenticationError（认证失败）
- **触发场景**: Token无效、Token过期、未登录
- **HTTP状态码**: 401 Unauthorized
- **处理方式**: 返回认证错误信息，引导用户登录

### 5. AuthorizationError（权限不足）
- **触发场景**: 用户没有权限访问资源
- **HTTP状态码**: 403 Forbidden
- **处理方式**: 返回权限错误信息

### 6. NotFoundError（资源不存在）
- **触发场景**: 查询的资源不存在
- **HTTP状态码**: 404 Not Found
- **处理方式**: 返回资源不存在的信息

---

## 🔧 错误处理策略

### 1. 异常捕获
- ✅ **try-except**: 使用try-except处理所有可能的异常
- ✅ **具体异常**: 捕获具体异常类型，而非通用Exception
- ✅ **异常链**: 保留异常链（使用`raise ... from e`）

**示例**:
```python
try:
    order = db.query(FactOrder).filter(FactOrder.id == order_id).first()
    if not order:
        raise NotFoundError(f"订单不存在: {order_id}")
except SQLAlchemyError as e:
    logger.error(f"数据库查询失败: {e}", exc_info=True)
    raise SystemError("数据库错误") from e
```

### 2. 错误日志
- ✅ **完整信息**: 记录完整错误信息（包括堆栈）
- ✅ **上下文信息**: 包含request_id、user_id、action等上下文
- ✅ **敏感信息**: 敏感信息必须脱敏（密码、token等）

**示例**:
```python
logger.error(
    "订单创建失败",
    extra={
        "request_id": request_id,
        "user_id": user_id,
        "action": "create_order",
        "order_id": order_id,
        "error": str(e)
    },
    exc_info=True
)
```

### 3. 用户友好
- ✅ **错误信息**: 向用户返回有意义的错误信息（不暴露系统细节）
- ✅ **错误码**: 使用业务错误码（2xxx系列）
- ✅ **建议操作**: 提供建议的操作（如"请检查订单ID是否正确"）

### 4. 错误恢复
- ✅ **重试机制**: 临时错误自动重试（如网络错误、数据库连接失败）
- ✅ **降级策略**: 服务不可用时优雅降级（如返回缓存数据）
- ✅ **断路器**: 使用断路器模式防止级联故障

---

## 📊 日志级别规范

### 1. ERROR（错误）
- **使用场景**: 必须处理的错误（系统异常、业务失败）
- **记录内容**: 完整的错误信息、堆栈、上下文
- **处理方式**: 发送告警、记录到错误日志文件

**示例**:
```python
logger.error(
    "订单创建失败",
    extra={"order_id": order_id, "error": str(e)},
    exc_info=True
)
```

### 2. WARNING（警告）
- **使用场景**: 需要关注的问题（数据质量、性能警告）
- **记录内容**: 问题描述、影响范围、建议操作
- **处理方式**: 记录到警告日志，可选发送告警

**示例**:
```python
logger.warning(
    "订单金额异常",
    extra={"order_id": order_id, "amount": amount, "threshold": 10000}
)
```

### 3. INFO（信息）
- **使用场景**: 关键业务流程（API调用、数据入库、状态变更）
- **记录内容**: 操作类型、关键参数、结果状态
- **处理方式**: 记录到信息日志

**示例**:
```python
logger.info(
    "订单创建成功",
    extra={"order_id": order_id, "amount": amount, "platform": platform}
)
```

### 4. DEBUG（调试）
- **使用场景**: 调试信息（仅开发环境，生产环境禁用）
- **记录内容**: 详细的执行流程、中间变量值
- **处理方式**: 仅在开发环境记录

**示例**:
```python
logger.debug(
    "处理订单数据",
    extra={"order_data": order_data, "step": "validation"}
)
```

---

## 📝 结构化日志

### 1. JSON格式
- ✅ **结构化**: 使用JSON格式便于日志聚合（ELK/Splunk）
- ✅ **字段标准**: 使用标准字段（request_id、user_id、action等）
- ✅ **上下文**: 包含足够的上下文便于问题定位

**示例**:
```python
logger.info(
    "订单创建成功",
    extra={
        "request_id": request_id,
        "user_id": user_id,
        "action": "create_order",
        "order_id": order_id,
        "platform": platform,
        "amount": amount,
        "duration_ms": duration_ms,
        "status": "success"
    }
)
```

### 2. 标准字段
- ✅ **request_id**: 请求唯一标识（贯穿全链路）
- ✅ **user_id**: 用户ID（操作人）
- ✅ **action**: 操作类型（如create_order、update_order）
- ✅ **duration**: 操作耗时（毫秒）
- ✅ **status**: 操作状态（success、failure）
- ✅ **error_code**: 错误码（失败时）
- ✅ **error_message**: 错误信息（失败时）

### 3. 敏感信息脱敏
- ✅ **密码**: 不记录密码（用`***`替代）
- ✅ **Token**: 不记录完整Token（只记录前8位）
- ✅ **信用卡号**: 不记录完整卡号（只记录后4位）
- ✅ **身份证号**: 不记录完整身份证号（只记录部分）

---

## 💾 日志保留策略

### 1. 热数据（30天）
- **内容**: 最近的日志（频繁查询）
- **存储**: 高性能存储（SSD）
- **用途**: 问题排查、性能分析

### 2. 温数据（90天）
- **内容**: 中等历史的日志（偶尔查询）
- **存储**: 标准存储（HDD）
- **用途**: 数据审计、合规检查

### 3. 冷数据（365天）
- **内容**: 历史日志（很少查询）
- **存储**: 归档存储（低成本）
- **用途**: 历史审计、合规要求

### 4. 审计日志（永久）
- **内容**: 财务、安全相关的审计日志
- **存储**: 归档存储（不可篡改）
- **用途**: 合规审计、安全审计

---

## 🔍 日志聚合和分析

### 1. 集中式日志
- ✅ **ELK Stack**: Elasticsearch + Logstash + Kibana
- ✅ **Splunk**: 企业级日志分析平台
- ✅ **AWS CloudWatch**: AWS云日志服务

### 2. 日志查询
- ✅ **时间范围**: 支持时间范围查询
- ✅ **关键词搜索**: 支持关键词搜索
- ✅ **过滤条件**: 支持多维度过滤（user_id、action、status等）

### 3. 日志告警
- ✅ **错误率告警**: 错误率 > 5% 触发告警
- ✅ **性能告警**: 响应时间 > 2s 触发告警
- ✅ **异常告警**: 异常模式检测（如大量登录失败）

---

## 🎨 前端错误处理规范（v4.19.7新增）⭐⭐⭐

### 1. Vue组件错误处理

#### 组件级错误处理
- ✅ **try-catch包装**: 关键逻辑使用try-catch包装
- ✅ **错误边界**: 使用Vue 3错误边界（onErrorCaptured）
- ✅ **默认值**: 错误时返回默认值，确保组件可渲染
- ✅ **用户提示**: 向用户显示友好的错误信息

**示例**：
```vue
<script setup>
import { computed, onErrorCaptured } from 'vue'
import { ElMessage } from 'element-plus'

// 错误边界
onErrorCaptured((err, instance, info) => {
  console.error('组件错误:', err, info)
  ElMessage.error('组件加载失败，请刷新页面')
  return false  // 阻止错误继续传播
})

// 计算属性错误处理
const currentUser = computed(() => {
  try {
    if (authStore.user) {
      return authStore.user
    }
    // ...
  } catch (error) {
    console.error('获取用户信息失败:', error)
    // 返回默认值，确保组件可以渲染
    return {
      id: 1,
      username: 'user',
      name: '用户',
      roles: []
    }
  }
})

// 异步函数错误处理
const loadUserInfo = async () => {
  try {
    const response = await authApi.getCurrentUser()
    if (response && response.roles) {
      authStore.user = response
    }
  } catch (error) {
    console.error('加载用户信息失败:', error)
    ElMessage.error('加载用户信息失败，请刷新页面重试')
    // 使用降级数据
    if (userStore.userInfo) {
      authStore.user = userStore.userInfo
    }
  }
}
</script>
```

### 2. API调用错误处理

#### 统一错误拦截
- ✅ **响应拦截器**: 统一处理API响应错误
- ✅ **错误分类**: 区分网络错误、业务错误、系统错误
- ✅ **用户提示**: 根据错误类型显示不同的用户提示
- ✅ **错误日志**: 记录详细的错误信息

**示例**：
```javascript
// frontend/src/api/index.js
import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000
})

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    const data = response.data
    // 统一响应格式处理
    if (data && typeof data === "object" && "success" in data) {
      if (data.success === true) {
        return data.data || data
      } else {
        // 业务错误
        const error = new Error(data.message || "操作失败")
        error.code = data.error?.code
        error.type = data.error?.type
        return Promise.reject(error)
      }
    }
    return data
  },
  async (error) => {
    // 网络错误
    if (!error.response) {
      console.error('网络错误:', error)
      ElMessage.error('网络连接失败，请检查网络设置')
      return Promise.reject(error)
    }
    
    // HTTP错误
    const status = error.response.status
    const data = error.response.data
    
    // 401: 未授权
    if (status === 401) {
      ElMessage.error('登录已过期，请重新登录')
      // 清除token，跳转到登录页
      localStorage.removeItem('access_token')
      window.location.href = '/login'
      return Promise.reject(error)
    }
    
    // 403: 权限不足
    if (status === 403) {
      ElMessage.error('权限不足，无法执行此操作')
      return Promise.reject(error)
    }
    
    // 404: 资源不存在
    if (status === 404) {
      ElMessage.error('请求的资源不存在')
      return Promise.reject(error)
    }
    
    // 422: 数据验证失败
    if (status === 422) {
      const message = data?.message || '数据验证失败'
      ElMessage.error(message)
      return Promise.reject(error)
    }
    
    // 500: 服务器错误
    if (status >= 500) {
      console.error('服务器错误:', error)
      ElMessage.error('服务器错误，请稍后重试')
      return Promise.reject(error)
    }
    
    // 其他错误
    const message = data?.message || error.message || '操作失败'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)
```

### 3. 前端错误日志

#### 错误日志记录
- ✅ **控制台日志**: 开发环境记录详细错误信息
- ✅ **错误上报**: 生产环境上报错误到日志服务
- ✅ **上下文信息**: 包含用户ID、页面路径、操作类型等
- ✅ **敏感信息脱敏**: 不记录密码、token等敏感信息

**示例**：
```javascript
// frontend/src/utils/errorLogger.js
export const logError = (error, context = {}) => {
  const errorInfo = {
    message: error.message,
    stack: error.stack,
    type: error.constructor.name,
    code: error.code,
    timestamp: new Date().toISOString(),
    userAgent: navigator.userAgent,
    url: window.location.href,
    ...context
  }
  
  // 开发环境：控制台输出
  if (import.meta.env.DEV) {
    console.error('前端错误:', errorInfo)
  }
  
  // 生产环境：上报到日志服务
  if (import.meta.env.PROD) {
    // 上报到日志服务（如Sentry、LogRocket等）
    // errorReportingService.captureException(error, errorInfo)
  }
}

// 使用示例
try {
  await api.getUserInfo()
} catch (error) {
  logError(error, {
    action: 'getUserInfo',
    userId: authStore.user?.id
  })
  ElMessage.error('获取用户信息失败')
}
```

### 4. 用户友好的错误提示

#### 错误提示规范
- ✅ **简洁明了**: 错误信息简洁明了，用户易于理解
- ✅ **操作建议**: 提供操作建议（如"请刷新页面重试"）
- ✅ **错误分类**: 根据错误类型显示不同的提示
- ✅ **避免技术术语**: 避免显示技术术语（如"500 Internal Server Error"）

**错误提示示例**：
```javascript
// ✅ 正确：用户友好的错误提示
if (error.code === 'NETWORK_ERROR') {
  ElMessage.error('网络连接失败，请检查网络设置后重试')
} else if (error.code === 'AUTH_FAILED') {
  ElMessage.error('登录已过期，请重新登录')
} else if (error.code === 'PERMISSION_DENIED') {
  ElMessage.error('权限不足，无法执行此操作')
} else {
  ElMessage.error('操作失败，请稍后重试')
}

// ❌ 错误：显示技术术语
ElMessage.error(`Error: ${error.message} (${error.code})`)
```

### 5. 前端错误处理检查清单

#### 组件开发
- [ ] 关键逻辑使用try-catch包装
- [ ] 计算属性有错误处理和默认值
- [ ] 异步函数有错误处理
- [ ] 错误时返回默认值，确保组件可渲染

#### API调用
- [ ] 响应拦截器已统一处理错误
- [ ] 错误分类正确（网络错误、业务错误、系统错误）
- [ ] 用户提示友好（不显示技术术语）
- [ ] 错误日志已记录

#### 错误日志
- [ ] 开发环境记录详细错误信息
- [ ] 生产环境上报错误到日志服务
- [ ] 包含足够的上下文信息
- [ ] 敏感信息已脱敏

### 6. 前端错误处理最佳实践

#### DO（推荐）
- ✅ 使用try-catch包装关键逻辑
- ✅ 计算属性返回默认值
- ✅ 统一错误拦截和处理
- ✅ 记录详细的错误日志
- ✅ 向用户显示友好的错误提示
- ✅ 错误时使用降级策略

#### DON'T（禁止）
- ❌ 忽略错误处理（缺少try-catch）
- ❌ 向用户显示技术术语
- ❌ 不记录错误日志
- ❌ 错误时导致整个应用崩溃
- ❌ 不提供降级策略

---

**最后更新**: 2026-01-08  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准（v4.19.7新增前端错误处理规范）


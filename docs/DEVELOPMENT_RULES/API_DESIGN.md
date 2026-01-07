# API设计规范 - 企业级ERP标准

**版本**: v4.6.0  
**更新**: 2025-01-16  
**标准**: RESTful API + OpenAPI 3.0 + 统一API契约

---

## 📋 API契约标准（v4.6.0新增）⭐

### 统一响应格式

所有API必须遵循统一的响应格式，详见`docs/API_CONTRACTS.md`。

**核心原则**：
- ✅ **成功响应**：`{"success": true, "data": {...}, "timestamp": "..."}`
- ✅ **错误响应**：`{"success": false, "error": {...}, "message": "...", "timestamp": "..."}`
- ✅ **分页响应**：`{"success": true, "data": [...], "pagination": {...}, "timestamp": "..."}`
- ✅ **自动格式化**：日期时间（ISO 8601）、金额（Decimal→float）自动格式化

**实现工具**：
- 后端：`backend/utils/api_response.py`（success_response、error_response、pagination_response）
- 后端：`backend/utils/data_formatter.py`（自动格式化日期时间和金额）
- 前端：`frontend/src/api/index.js`（响应拦截器自动处理）
- 前端：`frontend/src/utils/errorHandler.js`（统一错误处理）
- 前端：`frontend/src/utils/dataFormatter.js`（空数据格式化）

**详细文档**：
- 📖 [API契约开发指南](../API_CONTRACTS.md) - 完整的API契约标准和最佳实践
- 📖 [错误处理测试文档](../ERROR_HANDLING_TEST.md) - 错误处理测试场景和代码示例
- 📖 [数据分类传输规范指南](../DATA_CLASSIFICATION_API_GUIDE.md) - A/B/C类数据API传输规范
- 📖 [API端点清单](../API_ENDPOINTS_INVENTORY.md) - 所有API端点清单（按数据分类）

---

## 📊 数据分类传输规范（v4.6.0新增）⭐

### A类数据：用户配置数据

**特点**：
- 数据量小（通常<1000条）
- 更新频率低（按需更新）
- 需要CRUD操作（创建、读取、更新、删除）
- 需要版本控制和审计

**典型API**：
- 销售战役管理：`/api/sales-campaigns/*`
- 目标管理：`/api/targets/*`
- 绩效配置：`/api/performance/config/*`
- 字段映射辞典：`/api/field-mapping/dictionary/*`

**API特点**：
- ✅ 支持完整的CRUD操作
- ✅ 需要数据验证和业务规则检查
- ✅ 响应时间要求：<200ms
- ✅ 更新后自动触发C类数据重新计算（事件驱动）

**详细说明**：参见[数据分类传输规范指南](../DATA_CLASSIFICATION_API_GUIDE.md#a类数据用户配置数据)

### B类数据：业务数据

**特点**：
- 数据量大（百万级到千万级）
- 更新频率高（实时或准实时）
- 主要是查询操作（很少更新）
- 需要高效查询和聚合

**典型API**：
- 订单数据：`/api/main-views/orders/*`
- 产品数据：`/api/products/*`
- 库存数据：`/api/inventory/*`
- 财务数据：`/api/finance/*`
- 字段映射入库：`/api/field-mapping/ingest`

**API特点**：
- ✅ 主要支持查询操作（GET）
- ✅ 需要分页支持（大数据量）
- ✅ 需要多维度筛选（平台、店铺、时间范围）
- ✅ 响应时间要求：<500ms（简单查询）、<2s（复杂聚合）
- ✅ 入库后自动触发物化视图刷新（事件驱动）

**详细说明**：参见[数据分类传输规范指南](../DATA_CLASSIFICATION_API_GUIDE.md#b类数据业务数据)

### C类数据：计算数据

**特点**：
- 数据量中等（万级到百万级）
- 更新频率中等（定时计算或按需计算）
- 主要是查询操作（计算后存储）
- 需要实时计算或预计算

**典型API**：
- 数据看板：`/api/dashboard/*`
- 店铺分析：`/api/store-analytics/*`
- 健康度评分：`/api/store-analytics/health-scores`
- 达成率：`/api/sales-campaigns/{id}/calculate`、`/api/targets/{id}/calculate`

**API特点**：
- ✅ 主要支持查询操作（GET）
- ✅ 需要实时计算或预计算（物化视图）
- ✅ 需要多维度筛选（平台、店铺、时间范围）
- ✅ 需要对比分析（同比、环比）
- ✅ 响应时间要求：<1s（预计算）、<3s（实时计算）
- ✅ 支持缓存策略（健康度5分钟、达成率1分钟、排名5分钟）

**详细说明**：参见[数据分类传输规范指南](../DATA_CLASSIFICATION_API_GUIDE.md#c类数据计算数据)

**缓存策略**：
- ✅ 健康度评分缓存（5分钟TTL）
- ✅ 达成率缓存（1分钟TTL）
- ✅ 排名数据缓存（5分钟TTL）
- ✅ 数据更新时自动失效缓存（事件驱动）

**详细说明**：参见[C类数据缓存策略实现文档](../C_CLASS_CACHE_IMPLEMENTATION.md)

---

## 📋 RESTful设计原则

### 1. HTTP方法规范
- ✅ **GET**: 查询资源（幂等，不修改数据）
- ✅ **POST**: 创建资源（非幂等）
- ✅ **PUT**: 更新资源（幂等，完整更新）
- ✅ **DELETE**: 删除资源（幂等）
- ✅ **PATCH**: 部分更新资源（幂等，部分更新）

### 2. URL设计规范
- ✅ **资源命名**: 使用名词复数（如`/api/orders`，而非`/api/order`）
- ✅ **层次结构**: 反映资源关系（如`/api/orders/{order_id}/items`）
- ✅ **小写字母**: URL使用小写字母和下划线
- ✅ **避免动词**: URL中不使用动词（动词由HTTP方法表达）

**示例**:
```
GET    /api/orders              # 查询订单列表
GET    /api/orders/{order_id}    # 查询单个订单
POST   /api/orders               # 创建订单
PUT    /api/orders/{order_id}    # 更新订单
DELETE /api/orders/{order_id}    # 删除订单
PATCH  /api/orders/{order_id}    # 部分更新订单
```

---

## 📦 统一响应格式（v4.6.0统一标准）⭐

### 1. 成功响应
```json
{
  "success": true,
  "data": {
    // 实际数据（自动格式化日期时间和金额）
  },
  "message": "操作成功",  // 可选
  "timestamp": "2025-01-16T10:30:00Z"
}
```

**实现**：
```python
from backend.utils.api_response import success_response

return success_response(data={"id": 1, "name": "订单"})
```

### 2. 错误响应
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
  "timestamp": "2025-01-16T10:30:00Z"
}
```

**实现**：
```python
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type

return error_response(
    code=ErrorCode.ORDER_NOT_FOUND,
    message="订单不存在",
    error_type=get_error_type(ErrorCode.ORDER_NOT_FOUND),
    detail="订单ID: 12345不存在",
    recovery_suggestion="请检查订单ID是否正确"
)
```

### 3. 分页响应
```json
{
  "success": true,
  "data": [
    // 数据数组（自动格式化日期时间和金额）
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5,
    "has_previous": false,
    "has_next": true
  },
  "timestamp": "2025-01-16T10:30:00Z"
}
```

**实现**：
```python
from backend.utils.api_response import pagination_response

return pagination_response(
    data=order_list,
    page=1,
    page_size=20,
    total=100
)
```

### 4. 数据格式自动格式化

**日期时间格式**：
- `datetime`对象 → ISO 8601格式字符串（`2025-01-16T10:30:00Z`）
- `date`对象 → ISO 8601日期格式（`2025-01-16`）

**金额格式**：
- `Decimal`对象 → `float`（保留2位小数）

**实现**：`backend/utils/data_formatter.py`自动处理，无需手动格式化。

---

## 🔢 HTTP状态码规范

### 标准状态码
- ✅ **200 OK**: 请求成功（业务错误也返回200，通过`success`字段区分）
- ✅ **201 Created**: 资源创建成功
- ✅ **204 No Content**: 删除成功（无响应体）
- ✅ **400 Bad Request**: 请求参数错误
- ✅ **401 Unauthorized**: 未认证（需要登录）
- ✅ **403 Forbidden**: 权限不足
- ✅ **404 Not Found**: 资源不存在
- ✅ **409 Conflict**: 资源冲突（如唯一约束违反）
- ✅ **422 Unprocessable Entity**: 数据验证失败
- ✅ **429 Too Many Requests**: 请求频率超限
- ✅ **500 Internal Server Error**: 服务器内部错误
- ✅ **503 Service Unavailable**: 服务不可用（维护中）

### 业务错误码体系（v4.6.0新增）⭐

**错误码分类**：
- **1xxx** - 系统错误（数据库、缓存、消息队列、文件系统、网络）
- **2xxx** - 业务错误（订单、库存、财务、销售、数据同步）
- **3xxx** - 数据错误（验证、格式、完整性、隔离）
- **4xxx** - 用户错误（认证、权限、参数、频率限制）

**实现**：`backend/utils/error_codes.py`定义所有错误码。

---

## 🔐 API版本控制

### 1. 路径版本（推荐）
```
/api/v1/orders
/api/v2/orders
```

### 2. Header版本（备选）
```
X-API-Version: 1.0
```

### 3. 版本策略
- ✅ **向后兼容**: 至少支持2个主要版本
- ✅ **弃用策略**: 提前3个月通知，1年后移除
- ✅ **破坏性变更**: 必须升级主版本号（v1 → v2）

---

## 🚦 Rate Limiting（速率限制）

### 1. 默认限制
- ✅ **普通API**: 100 req/min/user
- ✅ **关键API**: 50 req/min/user（写操作）
- ✅ **批量API**: 10 req/min/user（资源密集型）

### 2. 超出限制响应
```json
{
  "success": false,
  "message": "请求频率超限",
  "error_code": "429",
  "retry_after": 60
}
```

**HTTP Header**:
```
Retry-After: 60
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1640995200
```

---

## 📄 分页规范

### 1. 请求参数
- ✅ **page**: 页码（从1开始）
- ✅ **page_size**: 每页数量（默认20，最大100）

### 2. 响应格式
```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

### 3. 性能要求
- ✅ 大数据量查询必须分页
- ✅ 避免一次性加载所有数据
- ✅ 默认page_size=20，最大不超过100

---

## 🔍 排序和筛选

### 1. 排序参数
- ✅ **sort**: 排序字段（如`sort=order_date`）
- ✅ **order**: 排序顺序（`asc`或`desc`，默认`desc`）

**示例**:
```
GET /api/orders?sort=order_date&order=desc
```

### 2. 筛选参数
- ✅ **查询参数**: 使用查询参数进行筛选（如`?platform=shopee&status=active`）
- ✅ **日期范围**: `start_date`和`end_date`（ISO 8601格式：`2025-01-30`）

**示例**:
```
GET /api/orders?platform=shopee&start_date=2025-01-01&end_date=2025-01-31
```

---

## 📚 API文档标准

### 1. OpenAPI 3.0规范
- ✅ **自动生成**: FastAPI自动生成swagger文档（`/api/docs`）
- ✅ **请求示例**: 必须包含请求示例
- ✅ **响应示例**: 必须包含成功和失败响应示例
- ✅ **字段说明**: 所有字段必须有说明和类型

### 2. 文档要求
- ✅ **端点说明**: 每个端点必须有清晰的说明
- ✅ **参数说明**: 所有参数必须有类型、默认值、是否必填
- ✅ **响应说明**: 所有可能的响应状态码必须有说明
- ✅ **错误示例**: 必须包含常见错误的响应示例

---

## 🔒 安全规范

### 1. 认证
- ✅ **Bearer Token**: `Authorization: Bearer <token>`
- ✅ **Token过期**: Access Token（15分钟），Refresh Token（7天）

### 2. 授权
- ✅ **权限检查**: 每个API端点必须检查权限
- ✅ **资源权限**: 基于资源的权限（如只能访问自己的店铺数据）

### 3. 输入验证
- ✅ **Pydantic验证**: 使用Pydantic自动验证请求参数
- ✅ **类型检查**: 自动检查参数类型
- ✅ **范围检查**: 检查数值范围（如page_size ≤ 100）

---

## 📊 性能要求

### 1. 响应时间
- ✅ **列表查询**: P95 < 500ms
- ✅ **详情查询**: P95 < 200ms
- ✅ **TopN查询**: P95 < 2s
- ✅ **P&L报表**: P95 < 2s

### 2. 查询优化
- ✅ **索引优化**: 为查询字段创建索引
- ✅ **预加载**: 避免N+1查询问题（使用joinedload）
- ✅ **分页**: 大数据量查询必须分页

---

## 🎯 最佳实践

### 1. 使用统一响应格式工具函数
```python
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type

# 成功响应
return success_response(data={"id": 1, "name": "订单"})

# 错误响应
return error_response(
    code=ErrorCode.ORDER_NOT_FOUND,
    message="订单不存在",
    error_type=get_error_type(ErrorCode.ORDER_NOT_FOUND)
)

# 分页响应
return pagination_response(data=order_list, page=1, page_size=20, total=100)
```

### 2. 错误处理
- ✅ **统一格式**: 所有错误返回统一格式（使用`error_response`）
- ✅ **错误码**: 使用预定义错误码（`ErrorCode`枚举）
- ✅ **错误信息**: 用户友好的错误提示和恢复建议
- ✅ **自动格式化**: 日期时间和金额自动格式化（无需手动处理）

### 3. 前端API调用规范
- ✅ **统一实例**: 使用`frontend/src/api/index.js`的统一api实例
- ✅ **方法命名**: `getXxx`、`createXxx`、`updateXxx`、`deleteXxx`
- ✅ **参数传递**: GET使用`params`，POST/PUT/DELETE使用`data`
- ✅ **错误处理**: 使用`handleApiError()`统一处理错误
- ✅ **空数据处理**: 使用`formatNumber()`、`formatDate()`等格式化函数

### 4. 幂等性
- ✅ **GET/PUT/DELETE**: 必须是幂等的
- ✅ **POST**: 非幂等（需要幂等时使用幂等键）

### 5. 缓存策略
- ✅ **GET请求**: 可以缓存（使用ETag或Cache-Control）
- ✅ **POST/PUT/DELETE**: 不缓存

---

## 📚 相关文档

- 📖 [API契约开发指南](../API_CONTRACTS.md) - 完整的API契约标准和最佳实践
- 📖 [错误处理测试文档](../ERROR_HANDLING_TEST.md) - 错误处理测试场景和代码示例
- 📖 [数据分类传输规范指南](../DATA_CLASSIFICATION_API_GUIDE.md) - A/B/C类数据API传输规范
- 📖 [API端点清单](../API_ENDPOINTS_INVENTORY.md) - 所有API端点清单（按数据分类）
- 📖 [C类数据缓存策略实现文档](../C_CLASS_CACHE_IMPLEMENTATION.md) - C类数据缓存实现
- 📖 [数据流转流程自动化实现文档](../DATA_FLOW_AUTOMATION_IMPLEMENTATION.md) - 事件驱动数据流转
- 📖 [OpenSpec规范](../../openspec/specs/frontend-api-contracts/spec.md) - API契约规范定义

---

**最后更新**: 2025-01-31  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准（v4.6.0统一API契约 + 数据流转流程自动化）


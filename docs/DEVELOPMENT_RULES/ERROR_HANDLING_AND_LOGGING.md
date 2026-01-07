# 错误处理和日志规范 - 企业级ERP标准

**版本**: v4.4.0  
**更新**: 2025-01-30  
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

**最后更新**: 2025-01-30  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准


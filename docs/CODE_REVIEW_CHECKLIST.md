# 代码审查检查清单

**版本**: v4.6.0  
**更新**: 2025-01-31  
**用途**: 代码审查时使用，确保代码符合前后端数据流转标准

---

## 📋 API响应格式检查项

### ✅ 后端检查项

- [ ] **使用统一响应函数**
  - [ ] 成功响应使用 `success_response()`
  - [ ] 错误响应使用 `error_response()`（不使用`raise HTTPException`）
  - [ ] 分页响应使用 `pagination_response()`
  - [ ] 列表响应使用 `list_response()`

- [ ] **响应格式完整性**
  - [ ] 包含`success`字段（true/false）
  - [ ] 包含`data`字段（成功时）或`error`字段（失败时）
  - [ ] 包含`timestamp`字段
  - [ ] 包含`request_id`字段（通过中间件自动添加）

- [ ] **错误响应完整性**
  - [ ] `error.code`字段存在（4位数字错误码）
  - [ ] `error.type`字段存在（SystemError/BusinessError/DataError/UserError）
  - [ ] `error.detail`字段存在（详细错误信息）
  - [ ] `error.recovery_suggestion`字段存在（恢复建议）
  - [ ] `message`字段存在（用户友好的错误信息）

### ✅ 前端检查项

- [ ] **不使用response.success检查**
  - [ ] 没有检查`response.success`字段（拦截器已处理）
  - [ ] 直接使用返回的`data`字段
  - [ ] 没有使用`response.pagination?.total`（统一使用`response.total`）

- [ ] **错误处理完整性**
  - [ ] 使用try-catch处理错误
  - [ ] 显示用户友好的错误消息（`error.message`）
  - [ ] 显示恢复建议（`error.recovery_suggestion`）
  - [ ] 记录错误日志（包含`request_id`）

---

## 🔧 错误处理检查项

### ✅ 后端检查项

- [ ] **错误码使用**
  - [ ] 使用`ErrorCode`枚举，不使用硬编码数字
  - [ ] 错误码符合分类（1xxx系统错误、2xxx业务错误、3xxx数据错误、4xxx用户错误）
  - [ ] 使用`get_error_type()`获取错误类型

- [ ] **错误日志**
  - [ ] 所有异常都记录日志（`logger.error()`）
  - [ ] 日志包含`exc_info=True`（记录堆栈信息）
  - [ ] 日志包含上下文信息（method、path、query_params等）
  - [ ] 日志包含`request_id`（通过`request.state.request_id`获取）

- [ ] **恢复建议**
  - [ ] 所有错误响应都包含`recovery_suggestion`字段
  - [ ] 恢复建议清晰、可操作
  - [ ] 恢复建议使用中文

### ✅ 前端检查项

- [ ] **错误类型处理**
  - [ ] 根据错误类型（SystemError/BusinessError/DataError/UserError）采用不同处理策略
  - [ ] 401错误自动跳转到登录页面
  - [ ] 系统错误显示通用提示，不暴露系统细节

- [ ] **错误日志**
  - [ ] 错误日志包含`request_id`
  - [ ] 错误日志包含端点信息
  - [ ] 错误日志包含错误详情

---

## 🔍 字段验证检查项

### ✅ 数据库字段验证

- [ ] **查询字段存在性**
  - [ ] 查询中使用的字段在schema中存在
  - [ ] 物化视图查询的字段在视图定义中存在
  - [ ] 使用`ORDER BY`的字段在查询结果中存在

- [ ] **字段类型匹配**
  - [ ] 查询字段类型与schema定义一致
  - [ ] 日期时间字段使用正确的格式（ISO 8601）
  - [ ] 金额字段使用DECIMAL类型

### ✅ API字段验证

- [ ] **请求参数验证**
  - [ ] 使用Pydantic进行参数验证
  - [ ] 必填字段有明确标识
  - [ ] 参数类型和格式正确

- [ ] **响应字段验证**
  - [ ] 响应字段与API文档一致
  - [ ] 日期时间字段格式化为ISO 8601
  - [ ] 金额字段格式化为float（保留2位小数）

---

## 📡 前端API方法检查项

### ✅ API方法存在性

- [ ] **方法定义**
  - [ ] 前端调用的API方法在`frontend/src/api/index.js`中定义
  - [ ] 方法名称符合命名规范（camelCase）
  - [ ] 方法参数格式正确

- [ ] **方法调用**
  - [ ] 使用统一API客户端（`api.methodName()`）
  - [ ] 不使用直接HTTP调用（`axios.get()`等）
  - [ ] 参数传递正确

### ✅ API响应处理

- [ ] **响应格式**
  - [ ] 不检查`response.success`字段
  - [ ] 直接使用返回的`data`字段
  - [ ] 分页数据使用扁平格式（`response.total`，不是`response.pagination.total`）

- [ ] **错误处理**
  - [ ] 使用try-catch处理错误
  - [ ] 错误提示用户友好
  - [ ] 错误日志包含`request_id`

---

## 🧪 测试检查项

### ✅ 单元测试

- [ ] **API端点测试**
  - [ ] 成功响应格式测试
  - [ ] 错误响应格式测试
  - [ ] 分页响应格式测试

- [ ] **错误处理测试**
  - [ ] 各种错误类型测试
  - [ ] 错误码测试
  - [ ] 恢复建议测试

### ✅ 集成测试

- [ ] **API集成测试**
  - [ ] 前后端数据流转测试
  - [ ] 错误处理路径测试
  - [ ] 请求ID追踪测试

---

## 📝 文档检查项

### ✅ API文档

- [ ] **响应格式文档**
  - [ ] API文档包含响应格式示例
  - [ ] 响应格式包含`request_id`字段说明
  - [ ] 错误响应包含`recovery_suggestion`字段说明

- [ ] **错误处理文档**
  - [ ] API文档包含错误码说明
  - [ ] API文档包含错误类型说明
  - [ ] API文档包含恢复建议说明

### ✅ 代码注释

- [ ] **函数注释**
  - [ ] 函数有docstring说明
  - [ ] 参数和返回值有类型注解
  - [ ] 错误情况有说明

---

## 🚨 常见问题检查

### ❌ 禁止的模式

- [ ] **后端禁止**
  - [ ] 不使用`raise HTTPException`（使用`error_response()`）
  - [ ] 不在响应中硬编码字段（使用统一响应函数）
  - [ ] 不忽略错误日志（所有异常都要记录）

- [ ] **前端禁止**
  - [ ] 不检查`response.success`字段
  - [ ] 不使用`response.pagination?.total`
  - [ ] 不忽略`request_id`（错误日志要包含）

---

## 📚 相关文档

- [API契约开发指南](./API_CONTRACTS.md)
- [前端错误处理开发指南](./FRONTEND_ERROR_HANDLING_GUIDE.md)
- [错误处理和日志规范](./DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md)

---

## ✅ 快速检查命令

```bash
# 检查后端HTTPException使用（应该只有410 Gone废弃API）
grep -r "raise HTTPException" backend/routers/ | grep -v "410"

# 检查前端response.success使用（应该为0）
grep -r "response.success" frontend/src/views/ | wc -l

# 检查前端response.pagination使用（应该为0）
grep -r "response.pagination" frontend/src/views/ | wc -l

# 运行验证脚本
python scripts/verify_data_flow_fixes.py
```


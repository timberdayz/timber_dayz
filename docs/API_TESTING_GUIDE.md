# API测试和验证指南

**创建时间**: 2025-01-31  
**状态**: ✅ 已完成  
**目的**: 提供API测试和验证的完整指南

---

## 📋 概述

本文档提供API测试和验证的完整指南，包括响应格式测试、API调用测试、C类数据查询策略测试、数据流转流程测试和端到端测试。

---

## 🧪 17.1 API响应格式测试

### 17.1.1 测试成功响应格式

**测试目标**: 验证所有API返回统一格式

**测试步骤**:

1. **验证响应结构**
   ```bash
   # 测试Dashboard API
   curl http://localhost:8001/api/dashboard/overview
   
   # 预期响应格式
   {
     "success": true,
     "data": {...},
     "timestamp": "2025-01-31T10:30:00Z"
   }
   ```

2. **验证data字段结构**
   - ✅ data字段存在
   - ✅ data字段类型正确（对象或数组）
   - ✅ data字段内容符合API契约

3. **验证timestamp字段格式**
   - ✅ timestamp字段存在
   - ✅ timestamp格式为ISO 8601（`2025-01-31T10:30:00Z`）

**测试API列表**:
- `/api/dashboard/overview` - Dashboard总览
- `/api/store-analytics/health-scores` - 健康度评分
- `/api/sales-campaigns` - 销售战役列表
- `/api/targets` - 目标列表

**检查清单**:
- [ ] 所有API返回`success: true`
- [ ] 所有API返回`data`字段
- [ ] 所有API返回`timestamp`字段
- [ ] timestamp格式为ISO 8601

---

### 17.1.2 测试错误响应格式

**测试目标**: 验证错误响应格式统一

**测试步骤**:

1. **测试400错误（参数验证错误）**
   ```bash
   # 测试无效参数
   curl http://localhost:8001/api/dashboard/overview?page=-1
   
   # 预期响应格式
   {
     "success": false,
     "error": {
       "code": 4001,
       "type": "ValidationError",
       "detail": "参数验证失败：page必须>=1",
       "recovery_suggestion": "请检查请求参数"
     },
     "message": "参数验证失败",
     "timestamp": "2025-01-31T10:30:00Z"
   }
   ```

2. **测试401错误（认证错误）**
   ```bash
   # 测试未认证请求
   curl http://localhost:8001/api/users
   
   # 预期响应格式
   {
     "success": false,
     "error": {
       "code": 4001,
       "type": "AuthenticationError",
       "detail": "未提供认证Token",
       "recovery_suggestion": "请先登录"
     },
     "message": "认证失败",
     "timestamp": "2025-01-31T10:30:00Z"
   }
   ```

3. **测试404错误（资源不存在）**
   ```bash
   # 测试不存在的资源
   curl http://localhost:8001/api/sales-campaigns/99999
   
   # 预期响应格式
   {
     "success": false,
     "error": {
       "code": 2301,
       "type": "BusinessError",
       "detail": "销售战役不存在：ID=99999",
       "recovery_suggestion": "请检查销售战役ID是否正确"
     },
     "message": "销售战役不存在",
     "timestamp": "2025-01-31T10:30:00Z"
   }
   ```

4. **测试500错误（服务器错误）**
   ```bash
   # 模拟服务器错误（需要后端代码触发）
   # 预期响应格式
   {
     "success": false,
     "error": {
       "code": 1002,
       "type": "SystemError",
       "detail": "数据库查询失败：...",
       "recovery_suggestion": "请稍后重试，如问题持续请联系管理员"
     },
     "message": "服务器内部错误",
     "timestamp": "2025-01-31T10:30:00Z"
   }
   ```

**检查清单**:
- [ ] 所有错误响应返回`success: false`
- [ ] 所有错误响应返回`error`字段
- [ ] 错误码为4位数字（1xxx/2xxx/3xxx/4xxx）
- [ ] 错误类型正确（SystemError/BusinessError/ValidationError/AuthenticationError）
- [ ] 错误信息清晰（包含恢复建议）
- [ ] timestamp字段存在

---

## 🔌 17.2 前端API调用测试

### 17.2.1 测试API调用方法

**测试目标**: 验证方法命名规范和参数传递格式

**测试步骤**:

1. **验证方法命名规范**
   ```javascript
   // ✅ 正确命名
   api.getSalesCampaigns()      // GET请求
   api.createSalesCampaign()    // POST请求
   api.updateSalesCampaign()    // PUT请求
   api.deleteSalesCampaign()    // DELETE请求
   
   // ❌ 错误命名
   api.salesCampaigns()         // 缺少动词
   api.fetchSalesCampaigns()    // 使用fetch而非get
   ```

2. **验证参数传递格式**
   ```javascript
   // ✅ GET请求使用params
   api.getSalesCampaigns({ params: { page: 1, page_size: 20 } })
   
   // ✅ POST请求使用data
   api.createSalesCampaign({ data: { name: "战役1", ... } })
   
   // ✅ PUT请求使用data
   api.updateSalesCampaign(id, { data: { name: "战役2", ... } })
   
   // ✅ DELETE请求使用data（可选）
   api.deleteSalesCampaign(id)
   ```

3. **验证响应处理逻辑**
   ```javascript
   // ✅ 正确处理响应
   try {
     const result = await api.getSalesCampaigns()
     // result已经是data字段内容，无需再检查success
     console.log(result) // 直接使用data内容
   } catch (error) {
     // 错误处理
     handleApiError(error)
   }
   ```

**检查清单**:
- [ ] 所有GET方法使用`get`前缀
- [ ] 所有POST方法使用`create`前缀
- [ ] 所有PUT方法使用`update`前缀
- [ ] 所有DELETE方法使用`delete`前缀
- [ ] GET请求使用`params`传递参数
- [ ] POST/PUT请求使用`data`传递参数
- [ ] 响应处理正确（直接使用data，无需检查success）

---

### 17.2.2 测试错误处理

**测试目标**: 验证错误处理逻辑

**测试步骤**:

1. **测试网络错误处理**
   ```javascript
   // 模拟网络错误（断开网络）
   try {
     await api.getSalesCampaigns()
   } catch (error) {
     // 预期：显示网络错误提示
     // 预期：自动重试（如果配置）
     handleApiError(error)
   }
   ```

2. **测试业务错误处理（根据错误码分类处理）**
   ```javascript
   // 测试400错误
   try {
     await api.createSalesCampaign({ data: { /* 无效数据 */ } })
   } catch (error) {
     // 预期：显示参数验证错误提示
     // 预期：提供恢复建议
     handleApiError(error)
   }
   
   // 测试401/403错误
   try {
     await api.getUsers()
   } catch (error) {
     // 预期：显示认证/权限错误提示
     // 预期：跳转到登录页面（401）
     handleApiError(error)
   }
   
   // 测试500错误
   try {
     await api.getData()
   } catch (error) {
     // 预期：显示服务器错误提示
     // 预期：提供恢复建议（稍后重试）
     handleApiError(error)
   }
   ```

3. **验证错误提示显示（用户友好）**
   - ✅ 错误消息清晰易懂
   - ✅ 错误消息包含恢复建议
   - ✅ 错误消息不包含技术细节（生产环境）
   - ✅ 错误消息包含错误码（开发环境）

**检查清单**:
- [ ] 网络错误正确处理（显示友好提示）
- [ ] 400错误正确处理（显示参数验证错误）
- [ ] 401/403错误正确处理（显示认证/权限错误）
- [ ] 500错误正确处理（显示服务器错误）
- [ ] 错误提示用户友好（包含恢复建议）
- [ ] 错误日志记录（开发环境）

---

## 🎯 17.3 C类数据查询策略测试

### 17.3.1 测试智能路由

**测试目标**: 验证自动选择最优查询方式

**测试步骤**:

1. **测试标准时间维度查询（使用物化视图）**
   ```bash
   # 测试2年内数据（daily粒度）
   curl "http://localhost:8001/api/store-analytics/health-scores?start_date=2024-01-01&end_date=2024-12-31&granularity=daily"
   
   # 预期：使用物化视图查询（响应时间<100ms）
   # 预期：响应中包含query_type: "materialized_view"
   ```

2. **测试自定义时间范围查询（实时计算）**
   ```bash
   # 测试超过2年数据
   curl "http://localhost:8001/api/store-analytics/health-scores?start_date=2020-01-01&end_date=2024-12-31&granularity=daily"
   
   # 预期：使用实时计算查询（响应时间<3s）
   # 预期：响应中包含query_type: "realtime"
   ```

3. **测试多年数据对比查询（分层查询）**
   ```bash
   # 测试5年以上数据（未来实现归档表查询）
   curl "http://localhost:8001/api/store-analytics/health-scores?start_date=2018-01-01&end_date=2024-12-31&granularity=monthly"
   
   # 预期：使用分层查询（物化视图+实时计算）
   # 预期：响应中包含query_type: "hybrid"
   ```

**检查清单**:
- [ ] 标准时间维度查询使用物化视图（<100ms）
- [ ] 自定义时间范围查询使用实时计算（<3s）
- [ ] 多年数据对比查询使用分层查询
- [ ] 响应中包含query_type字段
- [ ] 查询性能满足要求

---

### 17.3.2 测试多维度判断

**测试目标**: 验证路由规则正确

**测试步骤**:

1. **测试店铺维度判断**
   ```bash
   # 单店铺查询（≤10个）
   curl "http://localhost:8001/api/store-analytics/health-scores?shop_ids=shop1"
   
   # 预期：使用物化视图查询
   
   # 多店铺查询（>10个）
   curl "http://localhost:8001/api/store-analytics/health-scores?shop_ids=shop1,shop2,...,shop11"
   
   # 预期：使用实时计算查询
   ```

2. **测试账号维度判断**
   ```bash
   # 单账号查询（≤5个）
   curl "http://localhost:8001/api/store-analytics/health-scores?account_ids=account1"
   
   # 预期：使用物化视图查询
   
   # 多账号查询（>5个）
   curl "http://localhost:8001/api/store-analytics/health-scores?account_ids=account1,account2,...,account6"
   
   # 预期：使用实时计算查询
   ```

3. **测试平台维度判断**
   ```bash
   # 单平台查询（≤3个）
   curl "http://localhost:8001/api/store-analytics/health-scores?platform_codes=shopee"
   
   # 预期：使用物化视图查询
   
   # 多平台查询（>3个）
   curl "http://localhost:8001/api/store-analytics/health-scores?platform_codes=shopee,tiktok,amazon,lazada"
   
   # 预期：使用实时计算查询
   ```

**检查清单**:
- [ ] 单店铺查询使用物化视图
- [ ] 多店铺查询使用实时计算
- [ ] 单账号查询使用物化视图
- [ ] 多账号查询使用实时计算
- [ ] 单平台查询使用物化视图
- [ ] 多平台查询使用实时计算
- [ ] 路由规则正确（符合多维度判断矩阵）

---

## 🔄 17.4 数据流转流程测试

### 17.4.1 测试B类数据入库后自动刷新物化视图

**测试目标**: 验证B类数据入库后自动触发物化视图刷新

**测试步骤**:

1. **准备测试数据**
   ```bash
   # 上传订单数据文件
   curl -X POST http://localhost:8001/api/field-mapping/ingest \
     -F "file_id=123" \
     -F "template_id=456"
   ```

2. **验证事件触发**
   ```bash
   # 检查日志（应该看到DATA_INGESTED事件）
   # 预期日志：
   # [Event] 异步触发事件: DATA_INGESTED (Payload: {...})
   ```

3. **验证物化视图刷新**
   ```bash
   # 检查物化视图刷新状态
   curl http://localhost:8001/api/materialized-views/mv_shop_daily_performance/status
   
   # 预期：物化视图已刷新
   # 预期：刷新时间在数据入库后
   ```

**检查清单**:
- [ ] B类数据入库后触发DATA_INGESTED事件
- [ ] 事件监听器正确处理事件
- [ ] 物化视图自动刷新
- [ ] 物化视图刷新顺序正确（依赖关系）
- [ ] 刷新完成后触发MV_REFRESHED事件

---

### 17.4.2 测试物化视图刷新后自动计算C类数据

**测试目标**: 验证物化视图刷新后自动计算C类数据

**测试步骤**:

1. **触发物化视图刷新**
   ```bash
   # 手动刷新物化视图
   curl -X POST http://localhost:8001/api/materialized-views/mv_shop_daily_performance/refresh
   ```

2. **验证事件触发**
   ```bash
   # 检查日志（应该看到MV_REFRESHED事件）
   # 预期日志：
   # [Event] 异步触发事件: MV_REFRESHED (Payload: {...})
   ```

3. **验证C类数据计算**
   ```bash
   # 查询健康度评分（应该使用最新数据）
   curl "http://localhost:8001/api/store-analytics/health-scores?start_date=2025-01-01&end_date=2025-01-31"
   
   # 预期：数据已更新
   # 预期：计算结果正确
   ```

**检查清单**:
- [ ] 物化视图刷新后触发MV_REFRESHED事件
- [ ] 事件监听器正确处理事件
- [ ] C类数据自动计算
- [ ] C类数据计算结果正确
- [ ] 缓存自动失效（如果配置）

---

### 17.4.3 测试A类数据更新后自动重新计算C类数据

**测试目标**: 验证A类数据更新后自动触发C类数据重新计算

**测试步骤**:

1. **更新销售战役**
   ```bash
   # 更新销售战役
   curl -X PUT http://localhost:8001/api/sales-campaigns/1 \
     -H "Content-Type: application/json" \
     -d '{"target_amount": 200000}'
   ```

2. **验证事件触发**
   ```bash
   # 检查日志（应该看到A_CLASS_UPDATED事件）
   # 预期日志：
   # [Event] 异步触发事件: A_CLASS_UPDATED (Payload: {...})
   ```

3. **验证C类数据重新计算**
   ```bash
   # 查询达成率（应该使用最新数据）
   curl http://localhost:8001/api/sales-campaigns/1/calculate
   
   # 预期：达成率已重新计算
   # 预期：计算结果正确
   ```

**检查清单**:
- [ ] A类数据更新后触发A_CLASS_UPDATED事件
- [ ] 事件监听器正确处理事件
- [ ] C类数据自动重新计算
- [ ] 重新计算结果正确
- [ ] 缓存自动失效（如果配置）

---

## 🎮 17.5 端到端测试

### 17.5.1 测试核心功能

**测试目标**: 验证核心功能正常工作

**测试步骤**:

1. **测试Dashboard功能**
   - ✅ 访问Dashboard页面
   - ✅ 验证KPI数据正常显示
   - ✅ 验证图表正常渲染
   - ✅ 验证数据刷新正常

2. **测试业务概览功能**
   - ✅ 访问业务概览页面
   - ✅ 验证业务数据正常显示
   - ✅ 验证筛选功能正常
   - ✅ 验证对比功能正常

3. **测试数据采集功能**
   - ✅ 上传数据文件
   - ✅ 验证文件扫描正常
   - ✅ 验证字段映射正常
   - ✅ 验证数据入库正常

**检查清单**:
- [ ] Dashboard功能正常
- [ ] 业务概览功能正常
- [ ] 数据采集功能正常
- [ ] 数据正常显示
- [ ] 功能响应时间满足要求

---

### 17.5.2 测试业务功能

**测试目标**: 验证业务功能正常工作

**测试步骤**:

1. **测试店铺管理功能**
   - ✅ 查看店铺列表
   - ✅ 查看店铺详情
   - ✅ 验证店铺健康度评分正常显示

2. **测试销售战役功能**
   - ✅ 创建销售战役
   - ✅ 更新销售战役
   - ✅ 删除销售战役
   - ✅ 查看销售战役列表
   - ✅ 计算达成率

3. **测试目标管理功能**
   - ✅ 创建目标
   - ✅ 更新目标
   - ✅ 删除目标
   - ✅ 查看目标列表
   - ✅ 计算达成率

4. **测试库存管理功能**
   - ✅ 查看库存列表
   - ✅ 查看库存详情
   - ✅ 库存调整
   - ✅ 低库存预警

**检查清单**:
- [ ] 店铺管理功能正常
- [ ] 销售战役功能正常
- [ ] 目标管理功能正常
- [ ] 库存管理功能正常
- [ ] CRUD操作正常
- [ ] 数据计算正常

---

### 17.5.3 测试Mock数据替换

**测试目标**: 验证所有Mock数据已替换

**测试步骤**:

1. **验证Mock数据已替换**
   - ✅ 检查前端代码（无Mock数据开关）
   - ✅ 检查API调用（使用真实API）
   - ✅ 检查数据来源（数据库查询）

2. **验证真实数据正常显示**
   - ✅ 数据正常显示（非Mock数据）
   - ✅ 空数据处理正常（显示"-"）
   - ✅ 错误处理正常（显示错误提示）

3. **验证功能正常工作**
   - ✅ 所有功能正常
   - ✅ 数据刷新正常
   - ✅ 性能满足要求

4. **验证性能满足要求**
   - ✅ 物化视图查询<100ms
   - ✅ 实时计算查询<3s
   - ✅ API响应时间<500ms（简单查询）

**检查清单**:
- [ ] 所有Mock数据已替换
- [ ] 真实数据正常显示
- [ ] 功能正常工作
- [ ] 性能满足要求
- [ ] 空数据处理正常
- [ ] 错误处理正常

---

## 📊 测试报告模板

### 测试执行报告

**测试日期**: YYYY-MM-DD  
**测试人员**: XXX  
**测试环境**: 开发/测试/生产

**测试结果**:
- ✅ 通过
- ❌ 失败
- ⚠️ 部分通过

**测试详情**:
- 测试用例数: XX
- 通过数: XX
- 失败数: XX
- 通过率: XX%

**问题记录**:
1. 问题描述
2. 重现步骤
3. 预期结果
4. 实际结果
5. 优先级

---

## 📚 相关文档

- 📖 [API契约标准](API_CONTRACTS.md) - API响应格式标准
- 📖 [错误处理测试文档](ERROR_HANDLING_TEST.md) - 错误处理测试场景
- 📖 [C类数据查询策略指南](C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md) - 查询策略说明
- 📖 [数据流转流程自动化实现文档](DATA_FLOW_AUTOMATION_IMPLEMENTATION.md) - 事件驱动数据流转

---

**最后更新**: 2025-01-31  
**维护**: AI Agent Team  
**状态**: ✅ 已完成


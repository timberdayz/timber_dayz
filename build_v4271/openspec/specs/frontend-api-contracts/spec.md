# 前端API契约能力

## ADDED Requirements

### Requirement: API响应格式标准
系统应提供统一的API响应格式，包含成功响应、错误响应、分页响应和列表响应格式。

#### Scenario: 成功响应格式
- **WHEN** API请求成功
- **THEN** 系统返回统一格式：`{"success": true, "data": {...}, "message": "...", "timestamp": "..."}`
- **AND** `success`字段为`true`
- **AND** `data`字段包含实际数据
- **AND** `message`字段包含用户友好的提示信息（可选）
- **AND** `timestamp`字段包含ISO 8601格式的时间戳

#### Scenario: 错误响应格式
- **WHEN** API请求失败
- **THEN** 系统返回统一格式：`{"success": false, "error": {...}, "message": "...", "timestamp": "..."}`
- **AND** `success`字段为`false`
- **AND** `error`字段包含错误详情（code、type、detail）
- **AND** `message`字段包含用户友好的错误信息
- **AND** `timestamp`字段包含ISO 8601格式的时间戳

#### Scenario: 分页响应格式
- **WHEN** API返回分页数据
- **THEN** 系统返回统一格式：`{"success": true, "data": [...], "pagination": {...}, "timestamp": "..."}`
- **AND** `data`字段包含数据数组
- **AND** `pagination`字段包含完整分页信息：
  - `page`：当前页码（从1开始）
  - `page_size`：每页数量
  - `total`：总记录数
  - `total_pages`：总页数
  - `has_previous`：是否有上一页
  - `has_next`：是否有下一页
- **AND** `timestamp`字段包含ISO 8601格式的时间戳

#### Scenario: 列表响应格式
- **WHEN** API返回列表数据（无分页）
- **THEN** 系统返回统一格式：`{"success": true, "data": [...], "total": 100, "timestamp": "..."}`
- **AND** `data`字段包含数据数组
- **AND** `total`字段包含总记录数（可选）
- **AND** `timestamp`字段包含ISO 8601格式的时间戳

### Requirement: API错误处理标准
系统应提供统一的错误处理机制，包括HTTP状态码、业务错误码和错误信息格式。

#### Scenario: HTTP状态码使用
- **WHEN** API请求成功
- **THEN** 系统返回HTTP状态码200
- **WHEN** API请求参数错误
- **THEN** 系统返回HTTP状态码400
- **WHEN** API请求未认证
- **THEN** 系统返回HTTP状态码401
- **WHEN** API请求权限不足
- **THEN** 系统返回HTTP状态码403
- **WHEN** API请求资源不存在
- **THEN** 系统返回HTTP状态码404
- **WHEN** API服务器错误
- **THEN** 系统返回HTTP状态码500

#### Scenario: 业务错误码体系（企业级ERP标准）
- **WHEN** 系统错误（服务器错误、数据库错误等）
- **THEN** 系统返回1xxx系列错误码（按模块细分：1001-1099数据库、1100-1199缓存、1200-1299消息队列等）
- **WHEN** 业务错误（业务逻辑错误、验证错误等）
- **THEN** 系统返回2xxx系列错误码（按模块细分：2001-2099订单、2100-2199库存、2200-2299财务、2300-2399销售、2400-2499数据同步）
- **WHEN** 数据错误（数据格式错误、数据缺失等）
- **THEN** 系统返回3xxx系列错误码（按模块细分：3001-3099验证、3100-3199格式、3200-3299完整性、3300-3399隔离）
- **WHEN** 用户错误（认证错误、权限错误等）
- **THEN** 系统返回4xxx系列错误码（按模块细分：4001-4099认证、4100-4199权限、4200-4299参数、4300-4399频率限制）

#### Scenario: 错误信息格式
- **WHEN** API返回错误
- **THEN** 系统返回统一错误信息格式：`{"code": 2001, "type": "BusinessError", "detail": "...", "recovery_suggestion": "..."}`
- **AND** `code`字段包含4位数字错误码（按模块细分）
- **AND** `type`字段包含错误类型（SystemError、BusinessError、DataError、UserError）
- **AND** `detail`字段包含详细错误信息（可选）
- **AND** `recovery_suggestion`字段包含错误恢复建议（可选）

### Requirement: API数据格式标准
系统应提供统一的数据格式标准，包括日期时间格式、金额格式和分页参数格式。

#### Scenario: 日期时间格式
- **WHEN** API返回日期时间数据
- **THEN** 系统使用ISO 8601格式（如`2025-01-16T10:30:00Z`）
- **AND** 时区统一使用UTC
- **AND** 前端负责转换为本地时区显示

#### Scenario: 金额格式
- **WHEN** API返回金额数据
- **THEN** 系统使用Decimal类型，保留2位小数
- **AND** 前端负责格式化显示（千分位、货币符号）

#### Scenario: 分页参数格式
- **WHEN** API接收分页参数
- **THEN** 系统使用统一参数名称：`page`（页码，从1开始）、`page_size`（每页数量，默认20，最大100）
- **AND** 系统返回统一分页响应格式：`{"page": 1, "page_size": 20, "total": 100, "total_pages": 5}`

### Requirement: 前端API调用规范
系统应提供统一的前端API调用规范，包括方法命名、参数传递和错误处理。

#### Scenario: API方法命名规范
- **WHEN** 前端调用查询API
- **THEN** 方法名使用`getXxx`格式（如`getOrderList`、`getOrderDetail`）
- **WHEN** 前端调用创建API
- **THEN** 方法名使用`createXxx`格式（如`createOrder`、`createProduct`）
- **WHEN** 前端调用更新API
- **THEN** 方法名使用`updateXxx`格式（如`updateOrder`、`updateProduct`）
- **WHEN** 前端调用删除API
- **THEN** 方法名使用`deleteXxx`格式（如`deleteOrder`、`deleteProduct`）

#### Scenario: 参数传递格式
- **WHEN** 前端调用GET请求
- **THEN** 查询参数使用`params`对象传递
- **WHEN** 前端调用POST/PUT/DELETE请求
- **THEN** 请求体使用`data`对象传递

#### Scenario: 错误处理机制
- **WHEN** API请求失败（网络错误）
- **THEN** 前端统一处理网络错误，显示友好的错误提示
- **WHEN** API请求失败（业务错误）
- **THEN** 前端统一处理业务错误，显示错误码和错误信息
- **WHEN** API请求失败（认证错误）
- **THEN** 前端统一处理认证错误，跳转到登录页面

### Requirement: API响应拦截器
系统应提供统一的API响应拦截器，统一处理成功响应和错误响应。

#### Scenario: 成功响应处理
- **WHEN** API返回响应（HTTP 200）
- **THEN** 响应拦截器首先判断`success`字段
- **AND** 如果`success: true`，提取`data`字段返回给调用方
- **AND** 组件收到的是`data`字段内容（无需再检查`success`字段）
- **AND** 如果`message`字段存在，显示成功提示（可选）

#### Scenario: 错误响应处理
- **WHEN** API返回响应（HTTP 200）
- **THEN** 响应拦截器首先判断`success`字段
- **AND** 如果`success: false`，提取`error`字段，抛出错误
- **AND** 错误对象包含完整的错误信息（code、type、detail、message）
- **AND** 根据错误码类型显示不同的错误提示
- **AND** 记录错误日志
- **AND** 组件通过catch捕获错误，不显示"-"（避免误导开发者）

#### Scenario: 网络错误处理
- **WHEN** API请求网络错误（超时、连接失败等）
- **THEN** 响应拦截器统一处理网络错误
- **AND** 显示友好的网络错误提示
- **AND** 支持自动重试机制（可选）

### Requirement: API请求拦截器
系统应提供统一的API请求拦截器，统一处理请求头、超时时间和重试机制。

#### Scenario: 请求头设置
- **WHEN** 前端发送API请求
- **THEN** 请求拦截器自动添加统一的请求头（Content-Type、Authorization等）
- **AND** 根据API路径动态设置超时时间

#### Scenario: 超时时间配置
- **WHEN** 前端发送API请求
- **THEN** 请求拦截器根据API类型设置超时时间
- **AND** 默认超时时间为30秒
- **AND** 扫描文件API超时时间为120秒
- **AND** 数据入库API超时时间为180秒

#### Scenario: 重试机制
- **WHEN** API请求失败（网络错误或超时）
- **THEN** 请求拦截器自动重试（最多3次）
- **AND** 重试间隔递增（1秒、2秒、3秒）
- **AND** 业务错误不重试

### Requirement: API文档标准
系统应提供统一的API文档标准，包括OpenAPI文档和开发指南。

#### Scenario: OpenAPI文档生成
- **WHEN** 后端API开发完成
- **THEN** 系统自动生成OpenAPI文档（/api/docs）
- **AND** 文档包含请求参数、响应格式、错误响应示例

#### Scenario: API开发指南
- **WHEN** 开发新API
- **THEN** 开发指南提供API响应格式示例
- **AND** 开发指南提供错误处理示例
- **AND** 开发指南提供前端API调用示例

### Requirement: 数据分类传输规范
系统应提供统一的数据分类传输规范，明确A类、B类、C类数据的API传输方式和应用场景。

#### Scenario: A类数据（用户配置数据）传输
- **WHEN** 前端需要获取或更新用户配置数据（销售战役、目标、绩效配置）
- **THEN** 系统通过A类数据API提供数据（`/api/sales-campaign/*`、`/api/target-management/*`、`/api/performance-management/*`）
- **AND** API响应格式符合统一标准
- **AND** 支持CRUD操作（创建、读取、更新、删除）
- **AND** 前端用于配置管理页面（创建/编辑/查看配置）

#### Scenario: B类数据（业务数据）传输
- **WHEN** 前端需要获取业务数据（订单、产品、库存、流量）
- **THEN** 系统通过B类数据API提供数据（`/api/main-views/orders/*`、`/api/main-views/products/*`、`/api/inventory/*`、`/api/main-views/traffic/*`）
- **AND** API响应格式符合统一标准
- **AND** 支持分页查询和筛选
- **AND** 前端用于业务概览、数据看板、数据浏览器页面

#### Scenario: C类数据（计算数据）传输
- **WHEN** 前端需要获取计算数据（健康度评分、达成率、排名、预警）
- **THEN** 系统通过C类数据API提供数据（`/api/store-analytics/health-scores`、`/api/store-analytics/alerts`等）
- **AND** API响应格式符合统一标准
- **AND** 支持实时计算和缓存
- **AND** 前端用于店铺管理、业务概览、销售分析页面

### Requirement: C类数据查询策略（物化视图 + 实时计算混合模式）
系统应采用混合策略查询C类数据，根据查询类型自动选择最优方式，避免物化视图过大问题。

#### Scenario: 标准时间维度查询（物化视图优先）
- **WHEN** 前端查询标准时间维度（daily/weekly/monthly）且时间范围在物化视图范围内（2年内）
- **THEN** 系统优先从物化视图查询（`mv_shop_health_summary`、`mv_shop_daily_performance`等）
- **AND** 如果物化视图数据存在且未过期，直接返回物化视图数据
- **AND** 响应时间<100ms（物化视图查询）
- **AND** 前端获取数据快速响应

#### Scenario: 自定义时间范围查询（实时计算）
- **WHEN** 前端查询自定义时间范围（如2025-01-01到2025-01-15）或超出物化视图范围（>2年）
- **THEN** 系统从fact表实时计算C类数据（调用`ShopHealthService.calculate_health_score()`等）
- **AND** 系统根据时间范围动态计算健康度评分、达成率、排名等
- **AND** 响应时间<2s（实时计算）
- **AND** 计算结果准确，支持任意时间范围

#### Scenario: 时间维度切换（智能路由 - 多维度判断）
- **WHEN** 前端切换时间维度（日→周→月）或选择自定义时间范围
- **THEN** 系统自动判断查询类型（多维度判断矩阵）：
  - **时间维度**：标准粒度（daily/weekly/monthly）vs 自定义时间范围
  - **时间范围**：是否在物化视图范围内（2年内）
  - **店铺维度**：单店铺 vs 多店铺（≤10个）vs 全部店铺
  - **账号维度**：单账号 vs 多账号（≤5个）vs 全部账号
  - **平台维度**：单平台 vs 多平台（≤3个）vs 全部平台
- **AND** 系统自动选择最优查询方式：
  - ✅ **使用物化视图**（<100ms）：标准粒度 + 2年内 + ≤10店铺 + ≤5账号 + ≤3平台
  - ⚠️ **使用实时计算**（<2s）：自定义范围 OR 超出2年 OR >10店铺 OR >5账号 OR >3平台 OR 跨维度查询
- **AND** 前端无需关心查询方式，统一API接口
- **AND** 前端切换时间维度时自动选择最优方式

#### Scenario: 物化视图存储策略优化（分层存储架构）
- **WHEN** 系统设计物化视图存储策略
- **THEN** 系统采用分层存储架构：
  - **热数据层（物化视图）**：保留2年（730天）数据，支持年度对比和月度对比
  - **温数据层（fact表）**：保留2-5年数据，索引优化，响应时间<2s
  - **冷数据层（归档表）**：保留5年以上数据，monthly粒度归档，支持长期趋势分析
- **AND** 物化视图只存储daily粒度数据（避免存储爆炸）
- **AND** weekly/monthly粒度从daily粒度聚合计算（不单独存储）
- **AND** 自定义时间范围不存储在物化视图中，实时计算
- **AND** 避免物化视图过大问题，支持多年数据对比

#### Scenario: 数据分类在前端的应用
- **WHEN** 前端显示业务概览
- **THEN** 系统从B类数据API获取业务数据（订单、产品、库存、流量）
- **AND** 系统从C类数据API获取计算数据（达成率、排名）
- **WHEN** 前端显示店铺管理
- **THEN** 系统从C类数据API获取健康度评分和预警
- **AND** 系统从B类数据API获取店铺业务数据
- **WHEN** 前端显示销售战役管理
- **THEN** 系统从A类数据API获取战役配置
- **AND** 系统从B类数据API获取战役业务数据
- **AND** 系统从C类数据API获取战役达成率

### Requirement: Mock数据替换规范
系统应提供Mock数据替换规范，确保前端使用真实API数据而非Mock数据。

#### Scenario: Mock数据识别和替换
- **WHEN** 前端代码中存在Mock数据
- **THEN** 系统识别Mock数据使用位置（stores、views）
- **AND** 系统找到对应的后端API
- **AND** 系统替换Mock数据为真实API调用
- **AND** 系统移除Mock数据开关和判断逻辑

#### Scenario: Mock数据替换优先级
- **WHEN** 替换Mock数据
- **THEN** 优先替换核心功能Mock数据（dashboard、business-overview）
- **AND** 其次替换业务功能Mock数据（store、sales、target）
- **AND** 最后替换辅助功能Mock数据（hr、inventory）

#### Scenario: Mock数据清理
- **WHEN** Mock数据替换完成
- **THEN** 系统移除`USE_MOCK_DATA`环境变量
- **AND** 系统删除所有Mock数据定义和生成函数
- **AND** 系统清理相关注释和文档
- **AND** 系统确保所有功能使用真实API

### Requirement: API端点确认和创建
系统应确认所有API端点是否存在，不存在则创建或使用替代方案。

#### Scenario: API端点存在性检查
- **WHEN** 替换Mock数据时
- **THEN** 系统检查对应的API端点是否存在
- **AND** 如果API端点不存在，系统创建API端点或使用替代方案
- **AND** 系统记录所有API端点清单

#### Scenario: 缺失API端点创建
- **WHEN** 发现API端点不存在
- **THEN** 系统创建缺失的API端点
- **AND** API端点符合统一响应格式标准
- **AND** API端点支持所需功能（分页、筛选等）

### Requirement: 直接按标准实施（无过渡期）
系统应直接按照统一标准实施，不保留过渡期和兼容层。

#### Scenario: 一次性统一所有API格式
- **WHEN** 统一API响应格式
- **THEN** 系统一次性统一所有API响应格式
- **AND** 不保留任何旧格式
- **AND** 不添加兼容层
- **AND** 直接按照统一标准实施

#### Scenario: 同步更新前后端
- **WHEN** 后端API统一格式后
- **THEN** 系统立即更新前端调用代码
- **AND** 同步更新所有前端API调用
- **AND** 不保留任何旧格式处理逻辑
- **AND** 确保前后端格式一致

#### Scenario: 全面测试验证
- **WHEN** 统一格式完成后
- **THEN** 系统进行全面测试验证
- **AND** 测试所有API功能正常
- **AND** 测试所有前端调用正常
- **AND** 确保系统完全按照新标准运行

### Requirement: 数据流转流程自动化
系统应实现数据流转流程全自动化，确保数据及时更新。

#### Scenario: B类数据入库后自动触发物化视图刷新
- **WHEN** B类数据入库到fact表后
- **THEN** 系统自动触发`data_ingested`事件
- **AND** 系统监听事件，自动判断是否需要刷新物化视图
- **AND** 系统异步刷新相关物化视图（Celery任务）
- **AND** 系统按依赖顺序刷新（先刷新基础视图，再刷新依赖视图）

#### Scenario: 物化视图刷新后自动计算C类数据
- **WHEN** 物化视图刷新完成后
- **THEN** 系统自动触发`mv_refreshed`事件
- **AND** 系统监听事件，自动计算相关C类数据（健康度评分、达成率、排名）
- **AND** 系统异步计算C类数据（Celery任务）
- **AND** 系统更新C类数据表和物化视图

#### Scenario: A类数据更新后自动触发C类数据重新计算
- **WHEN** A类数据（销售战役、目标）更新后
- **THEN** 系统自动触发`a_class_updated`事件
- **AND** 系统监听事件，自动识别需要重新计算的C类数据
- **AND** 系统异步重新计算相关C类数据（Celery任务）
- **AND** 系统更新C类数据表和物化视图

### Requirement: API版本控制
系统应支持API版本控制，确保向后兼容和未来扩展。

#### Scenario: URL路径版本控制
- **WHEN** 系统提供API服务
- **THEN** 系统支持URL路径版本控制（/api/v1/、/api/v2/）
- **AND** 默认版本为v1（不写版本号时使用v1）
- **AND** 支持多版本同时运行
- **AND** 至少支持2个主要版本同时运行

#### Scenario: API弃用策略
- **WHEN** API需要弃用时
- **THEN** 系统提前3个月通知API弃用
- **AND** 系统提供迁移指南和工具
- **AND** 系统1年后移除旧版本API

### Requirement: 性能监控
系统应建立关键性能指标监控体系，确保系统性能满足要求。

#### Scenario: API性能监控
- **WHEN** API提供服务
- **THEN** 系统监控API响应时间（P50/P95/P99分位数）
- **AND** 系统监控错误率（4xx/5xx错误率）
- **AND** 系统监控QPS（每秒查询数）
- **AND** 系统监控慢查询（>100ms）

#### Scenario: 缓存性能监控
- **WHEN** 系统使用缓存
- **THEN** 系统监控缓存命中率（物化视图查询率、Redis缓存命中率）
- **AND** 系统监控缓存响应时间
- **AND** 系统监控缓存使用情况

#### Scenario: 数据库性能监控
- **WHEN** 系统查询数据库
- **THEN** 系统监控慢查询（>100ms）
- **AND** 系统监控数据库连接池使用情况
- **AND** 系统监控数据库查询时间

### Requirement: 性能优化
系统应提供性能优化策略，确保API响应速度和用户体验。

#### Scenario: C类数据缓存策略
- **WHEN** 前端请求C类数据（健康度评分、达成率、排名）
- **THEN** 系统使用缓存策略减少计算次数
- **AND** 健康度评分缓存5分钟
- **AND** 达成率缓存1分钟
- **AND** 排名数据缓存5分钟
- **AND** 数据更新时自动失效缓存

#### Scenario: API性能优化
- **WHEN** API查询数据
- **THEN** 系统使用数据库索引优化查询
- **AND** 系统使用物化视图预计算数据
- **AND** 系统支持批量查询减少API调用次数
- **AND** 系统优化数据传输量

### Requirement: 前端空数据处理规范（开发阶段容错）
系统应在开发阶段提供友好的空数据处理机制，确保前端在数据缺失时不会报错，便于观察数据变化。

**重要区分：空数据 vs API错误**
- **空数据**：API成功返回（`success: true`），但数据为空 → 显示"-"
- **API错误**：API返回错误（`success: false`）或请求失败 → 显示错误信息

#### Scenario: 空数据识别（API成功但无数据）
- **WHEN** API返回成功响应（`success: true`）
- **AND** `data`字段为null、undefined、空数组[]或空对象{}
- **THEN** 前端识别为空数据，显示"-"或"暂无数据"
- **AND** 前端不抛出错误，正常渲染
- **AND** 前端记录空数据日志（开发环境）

#### Scenario: API错误识别（API路径错误或请求失败）
- **WHEN** API返回错误响应（`success: false`）
- **OR** API请求失败（404、500、网络错误等）
- **THEN** 前端识别为API错误，显示错误信息
- **AND** 前端显示错误提示（错误码、错误消息）
- **AND** 前端记录错误日志（开发环境）
- **AND** 前端不显示"-"（避免误导开发者）

#### Scenario: 数值类型空数据处理（仅API成功时）
- **WHEN** API返回成功响应（`success: true`）
- **AND** 数值字段为null、undefined或空字符串
- **THEN** 前端显示"-"（适用于金额、数量、百分比等）
- **AND** 前端不抛出错误，不中断渲染
- **AND** 前端记录空数据日志（开发环境）
- **AND** 0值正常显示（不显示"-"）
- **WHEN** API返回错误响应（`success: false`）
- **THEN** 前端显示错误信息，不显示"-"

#### Scenario: 列表类型空数据处理（仅API成功时）
- **WHEN** API返回成功响应（`success: true`）
- **AND** 列表数据为空数组[]或null
- **THEN** 前端显示空状态提示（"暂无数据"）
- **AND** 前端不抛出错误，正常渲染空状态
- **AND** 表格组件使用`empty-text="暂无数据"`
- **WHEN** API返回错误响应（`success: false`）
- **THEN** 前端显示错误信息，不显示"暂无数据"

#### Scenario: 对象类型空数据处理（仅API成功时）
- **WHEN** API返回成功响应（`success: true`）
- **AND** 对象为null或undefined
- **THEN** 前端使用默认值对象（空对象{}）
- **AND** 前端安全访问对象属性（使用可选链操作符?.）
- **AND** 前端不抛出错误
- **WHEN** API返回错误响应（`success: false`）
- **THEN** 前端显示错误信息，不使用默认值对象

#### Scenario: 字符串类型空数据处理（仅API成功时）
- **WHEN** API返回成功响应（`success: true`）
- **AND** 字符串字段为null、undefined或空字符串
- **THEN** 前端显示"-"（适用于名称、描述等）
- **AND** 前端不抛出错误
- **WHEN** API返回错误响应（`success: false`）
- **THEN** 前端显示错误信息，不显示"-"

#### Scenario: 日期时间类型空数据处理（仅API成功时）
- **WHEN** API返回成功响应（`success: true`）
- **AND** 日期时间字段为null或undefined
- **THEN** 前端显示"-"（适用于创建时间、更新时间等）
- **AND** 前端不抛出错误
- **WHEN** API返回错误响应（`success: false`）
- **THEN** 前端显示错误信息，不显示"-"

#### Scenario: API响应拦截器区分空数据和错误
- **WHEN** API返回响应（HTTP 200）
- **THEN** 响应拦截器首先判断`success`字段
- **AND** 如果`success: true`：
  - 提取`data`字段返回给调用方
  - 如果`data`为空（null、undefined、[]、{}），标记为空数据（不标记为错误）
  - 空数组返回[]而非null
  - 空对象返回{}而非null
  - 记录空数据日志（开发环境）
  - 组件收到`data`字段内容，使用格式化函数处理空数据（显示"-"）
- **AND** 如果`success: false`：
  - 提取`error`字段，抛出错误
  - 标记为API错误，显示错误信息
  - 不标记为空数据
  - 组件通过catch捕获错误，显示错误信息（不显示"-"）
- **WHEN** API请求失败（网络错误、404、500等）
- **THEN** 响应拦截器标记为API错误
- **AND** 抛出错误，显示错误信息
- **AND** 不标记为空数据
- **AND** 组件通过catch捕获错误，显示错误信息（不显示"-"）

#### Scenario: 开发阶段数据变化观察
- **WHEN** 后端数据重新入库后
- **THEN** 前端能够正常显示数据变化（从"-"变为实际值）
- **AND** 前端不因数据变化而报错
- **AND** 前端提供数据刷新机制（手动刷新按钮）
- **AND** 前端能够观察数据变化过程，便于审查数据是否正常入库和应用




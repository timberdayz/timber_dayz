# API端点清单

**创建时间**: 2025-01-31  
**状态**: ✅ 已完成  
**目的**: 列出所有API端点，按数据分类（A/B/C类）组织

---

## 📋 数据分类说明

- **A类数据**: 用户配置数据（销售战役、目标、绩效配置等）
- **B类数据**: 业务数据（订单、产品、库存、财务等）
- **C类数据**: 计算数据（健康度评分、达成率、排名等）

---

## 🔵 A类数据API端点（用户配置数据）

### 销售战役管理 (`/api/sales-campaigns`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/sales-campaigns` | 查询战役列表（分页、筛选） | A类 |
| GET | `/api/sales-campaigns/{campaign_id}` | 查询战役详情 | A类 |
| POST | `/api/sales-campaigns` | 创建战役 | A类 |
| PUT | `/api/sales-campaigns/{campaign_id}` | 更新战役 | A类 |
| DELETE | `/api/sales-campaigns/{campaign_id}` | 删除战役 | A类 |
| POST | `/api/sales-campaigns/{campaign_id}/shops` | 添加参与店铺 | A类 |
| DELETE | `/api/sales-campaigns/{campaign_id}/shops/{shop_id}` | 移除参与店铺 | A类 |
| POST | `/api/sales-campaigns/{campaign_id}/calculate` | 计算达成情况（触发C类数据计算） | A类→C类 |

### 目标管理 (`/api/targets`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/targets` | 查询目标列表（分页、筛选） | A类 |
| GET | `/api/targets/{target_id}` | 查询目标详情 | A类 |
| POST | `/api/targets` | 创建目标 | A类 |
| PUT | `/api/targets/{target_id}` | 更新目标 | A类 |
| DELETE | `/api/targets/{target_id}` | 删除目标 | A类 |
| POST | `/api/targets/{target_id}/breakdown` | 创建目标分解 | A类 |
| GET | `/api/targets/{target_id}/breakdown` | 查询目标分解列表 | A类 |
| POST | `/api/targets/{target_id}/calculate` | 计算达成情况（触发C类数据计算） | A类→C类 |

### 绩效管理 (`/api/performance`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/performance/config` | 查询绩效配置列表 | A类 |
| GET | `/api/performance/config/{config_id}` | 查询绩效配置详情 | A类 |
| POST | `/api/performance/config` | 创建绩效配置 | A类 |
| PUT | `/api/performance/config/{config_id}` | 更新绩效配置 | A类 |
| DELETE | `/api/performance/config/{config_id}` | 删除绩效配置 | A类 |
| GET | `/api/performance/scores` | 查询绩效评分列表（C类数据） | C类 |
| GET | `/api/performance/scores/{shop_id}` | 查询店铺绩效详情（C类数据） | C类 |
| POST | `/api/performance/scores/calculate` | 计算绩效评分（触发C类数据计算） | A类→C类 |

### 字段映射辞典 (`/api/field-mapping/dictionary`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/field-mapping/dictionary` | 查询字段辞典列表 | A类 |
| GET | `/api/field-mapping/dictionary/{field_code}` | 查询字段详情 | A类 |
| POST | `/api/field-mapping/dictionary/field` | 添加字段到辞典 | A类 |
| PUT | `/api/field-mapping/dictionary/{field_code}` | 更新字段 | A类 |
| DELETE | `/api/field-mapping/dictionary/{field_code}` | 删除字段 | A类 |
| POST | `/api/field-mapping/suggest-mappings` | 智能字段映射建议 | A类 |
| GET | `/api/field-mapping/dictionary/cache/clear` | 清空辞典缓存 | A类 |
| GET | `/api/field-mapping/dictionary/summary` | 辞典统计信息 | A类 |

### 字段映射模板 (`/api/field-mapping/templates`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/field-mapping/templates` | 查询模板列表 | A类 |
| GET | `/api/field-mapping/templates/{template_id}` | 查询模板详情 | A类 |
| POST | `/api/field-mapping/templates` | 创建模板 | A类 |
| PUT | `/api/field-mapping/templates/{template_id}` | 更新模板 | A类 |
| DELETE | `/api/field-mapping/templates/{template_id}` | 删除模板 | A类 |

---

## 🟢 B类数据API端点（业务数据）

### 订单数据 (`/api/main-views/orders`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/main-views/orders/summary` | 查询订单汇总（分页、筛选） | B类 |

### 流量数据 (`/api/main-views/traffic`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/main-views/traffic/summary` | 查询流量汇总（分页、筛选） | B类 |

### 库存数据 (`/api/inventory`, `/api/products`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/inventory/list` | 查询库存列表（分页、筛选） | B类 |
| GET | `/api/inventory/detail/{product_id}` | 查询库存详情 | B类 |
| POST | `/api/inventory/adjust` | 库存调整 | B类 |
| GET | `/api/inventory/low-stock-alert` | 低库存预警 | B类 |
| GET | `/api/main-views/inventory/by-sku` | 按SKU查询库存 | B类 |
| GET | `/api/products` | 查询产品列表（分页、筛选） | B类 |
| GET | `/api/products/{product_id}` | 查询产品详情 | B类 |

### 财务数据 (`/api/finance`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/finance/accounts-receivable` | 查询应收账款（分页、筛选） | B类 |
| POST | `/api/finance/record-payment` | 记录收款 | B类 |
| GET | `/api/finance/payment-receipts` | 查询收款单列表 | B类 |
| GET | `/api/finance/expenses` | 查询费用列表（分页、筛选） | B类 |
| POST | `/api/finance/expenses/upload` | 上传费用文件 | B类 |
| POST | `/api/finance/expenses/allocate` | 费用分摊 | B类 |
| GET | `/api/finance/profit-report` | 查询利润报告 | B类 |
| GET | `/api/finance/pnl/shop` | 查询店铺P&L | B类 |
| GET | `/api/finance/financial-overview` | 财务总览 | B类 |
| GET | `/api/finance/overdue-alert` | 逾期预警 | B类 |
| GET | `/api/finance/periods/list` | 查询会计期间列表 | B类 |
| POST | `/api/finance/periods/{period_code}/close` | 关闭会计期间 | B类 |
| GET | `/api/finance/fx-rates` | 查询汇率列表 | B类 |
| POST | `/api/finance/fx-rates` | 更新汇率 | B类 |

### 采购数据 (`/api/procurement`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/procurement/purchase-orders` | 查询采购订单列表 | B类 |
| POST | `/api/procurement/purchase-orders` | 创建采购订单 | B类 |
| GET | `/api/procurement/goods-receipts` | 查询收货单列表 | B类 |
| POST | `/api/procurement/goods-receipts` | 创建收货单 | B类 |
| GET | `/api/procurement/invoices` | 查询发票列表 | B类 |
| POST | `/api/procurement/invoices` | 创建发票 | B类 |
| POST | `/api/procurement/invoices/{invoice_id}/match` | 三单匹配 | B类 |

### 数据浏览器 (`/api/data-browser`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/data-browser/tables` | 查询数据表列表 | B类 |
| GET | `/api/data-browser/query` | 查询数据（SQL查询） | B类 |
| GET | `/api/data-browser/stats` | 查询数据统计 | B类 |
| GET | `/api/data-browser/export` | 导出数据 | B类 |
| GET | `/api/data-browser/field-mapping/{table}/{field}` | 查询字段映射 | B类 |
| GET | `/api/data-browser/field-usage/{table}/{field}` | 查询字段使用情况 | B类 |

### 字段映射和数据入库 (`/api/field-mapping`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/field-mapping/file-groups` | 查询文件分组 | B类 |
| POST | `/api/field-mapping/bulk-ingest` | 批量入库 | B类 |
| GET | `/api/field-mapping/scan-files-by-date` | 按日期扫描文件 | B类 |
| GET | `/api/field-mapping/files` | 查询文件列表 | B类 |
| POST | `/api/field-mapping/scan` | 扫描文件 | B类 |
| GET | `/api/field-mapping/file-info` | 查询文件信息 | B类 |
| GET | `/api/field-mapping/files-by-period` | 按期间查询文件 | B类 |
| POST | `/api/field-mapping/preview` | 预览文件数据 | B类 |
| POST | `/api/field-mapping/generate-mapping` | 生成字段映射 | B类 |
| POST | `/api/field-mapping/ingest` | 数据入库 | B类 |
| POST | `/api/field-mapping/validate` | 验证数据 | B类 |
| GET | `/api/field-mapping/catalog-status` | 查询目录状态 | B类 |
| GET | `/api/field-mapping/quarantine-summary` | 查询隔离数据统计 | B类 |
| GET | `/api/field-mapping/progress/{task_id}` | 查询任务进度 | B类 |
| GET | `/api/field-mapping/progress` | 查询所有任务进度 | B类 |
| GET | `/api/field-mapping/template-cache/stats` | 查询模板缓存统计 | B类 |

### 数据隔离区 (`/api/data-quarantine`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/data-quarantine/list` | 查询隔离数据列表（分页、筛选） | B类 |
| GET | `/api/data-quarantine/detail/{id}` | 查询隔离数据详情 | B类 |
| POST | `/api/data-quarantine/reprocess` | 重新处理隔离数据 | B类 |
| DELETE | `/api/data-quarantine/delete` | 批量删除隔离数据 | B类 |
| GET | `/api/data-quarantine/stats` | 查询隔离数据统计 | B类 |

### 数据同步 (`/api/data-sync`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| POST | `/api/data-sync/single` | 单文件同步 | B类 |
| POST | `/api/data-sync/batch` | 批量同步 | B类 |
| GET | `/api/data-sync/progress/{task_id}` | 查询同步进度 | B类 |

---

## 🟡 C类数据API端点（计算数据）

### 数据看板 (`/api/dashboard`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/dashboard/overview` | 数据看板总览 | C类 |
| GET | `/api/dashboard/kpi` | KPI指标 | C类 |
| GET | `/api/dashboard/gmv-trend` | GMV趋势 | C类 |
| GET | `/api/dashboard/platform-distribution` | 平台分布 | C类 |
| GET | `/api/dashboard/top-products` | Top商品排行 | C类 |
| GET | `/api/dashboard/business-overview/traffic-ranking` | 流量排名 | C类 |
| GET | `/api/dashboard/business-overview/kpi` | 业务概览KPI | C类 |
| GET | `/api/dashboard/business-overview/comparison` | 业务对比 | C类 |
| GET | `/api/dashboard/business-overview/shop-racing` | 店铺竞速 | C类 |
| GET | `/api/dashboard/business-overview/operational-metrics` | 运营指标 | C类 |
| GET | `/api/dashboard/business-overview/inventory-backlog` | 库存积压 | C类 |
| GET | `/api/dashboard/clearance-ranking` | 滞销清理排名 | C类 |

### 店铺分析 (`/api/store-analytics`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/store-analytics/health-scores` | 查询健康度评分列表（分页、筛选） | C类 |
| POST | `/api/store-analytics/health-scores/calculate` | 计算健康度评分 | C类 |
| GET | `/api/store-analytics/health-scores/{shop_id}/history` | 查询健康度历史 | C类 |
| GET | `/api/store-analytics/gmv-trend` | 查询GMV趋势 | C类 |
| GET | `/api/store-analytics/conversion-analysis` | 查询转化率分析 | C类 |
| GET | `/api/store-analytics/traffic-analysis` | 查询流量分析 | C类 |
| GET | `/api/store-analytics/comparison` | 店铺对比分析 | C类 |
| GET | `/api/store-analytics/alerts` | 查询店铺预警列表 | C类 |
| POST | `/api/store-analytics/alerts/{alert_id}/resolve` | 解决预警 | C类 |
| GET | `/api/store-analytics/alerts/stats` | 查询预警统计 | C类 |
| POST | `/api/store-analytics/alerts/generate` | 生成预警 | C类 |
| GET | `/api/store-analytics/cache/stats` | 查询缓存统计 | C类 |
| POST | `/api/store-analytics/cache/clear` | 清除缓存 | C类 |

### 数据质量监控 (`/api/data-quality`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/data-quality/c-class-readiness` | 查询C类数据计算就绪状态 | C类 |
| GET | `/api/data-quality/core-fields-status` | 查询核心字段状态 | C类 |

---

## 🔧 系统管理API端点

### 认证管理 (`/api/auth`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| POST | `/api/auth/login` | 用户登录 | 系统 |
| POST | `/api/auth/logout` | 用户登出 | 系统 |
| POST | `/api/auth/refresh` | 刷新Token | 系统 |

### 用户管理 (`/api/users`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/users` | 查询用户列表 | 系统 |
| GET | `/api/users/{user_id}` | 查询用户详情 | 系统 |
| POST | `/api/users` | 创建用户 | 系统 |
| PUT | `/api/users/{user_id}` | 更新用户 | 系统 |
| DELETE | `/api/users/{user_id}` | 删除用户 | 系统 |

### 角色管理 (`/api/roles`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/roles` | 查询角色列表 | 系统 |
| GET | `/api/roles/{role_id}` | 查询角色详情 | 系统 |
| POST | `/api/roles` | 创建角色 | 系统 |
| PUT | `/api/roles/{role_id}` | 更新角色 | 系统 |
| DELETE | `/api/roles/{role_id}` | 删除角色 | 系统 |

### 账号管理 (`/api/accounts`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/accounts` | 查询账号列表 | 系统 |
| POST | `/api/accounts` | 添加账号 | 系统 |
| PUT | `/api/accounts/{account_id}` | 更新账号 | 系统 |
| DELETE | `/api/accounts/{account_id}` | 删除账号 | 系统 |

### 系统配置 (`/api/system`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/system/platforms` | 查询支持的平台列表 | 系统 |
| GET | `/api/system/data-domains` | 查询支持的数据域列表 | 系统 |
| GET | `/api/system/granularities` | 查询支持的粒度列表 | 系统 |

### 物化视图管理 (`/api/materialized-views`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/materialized-views` | 查询物化视图列表 | 系统 |
| GET | `/api/materialized-views/{view_name}` | 查询物化视图详情 | 系统 |
| POST | `/api/materialized-views/{view_name}/refresh` | 刷新物化视图 | 系统 |
| POST | `/api/materialized-views/refresh-all` | 刷新所有物化视图 | 系统 |
| GET | `/api/materialized-views/{view_name}/status` | 查询刷新状态 | 系统 |

### 数据采集 (`/api/collection`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| POST | `/api/collection/start` | 启动数据采集 | 系统 |
| GET | `/api/collection/status` | 查询采集状态 | 系统 |
| POST | `/api/collection/stop` | 停止数据采集 | 系统 |

### 数据管理 (`/api/management`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/management/files` | 查询文件列表 | 系统 |
| GET | `/api/management/files/{file_id}` | 查询文件详情 | 系统 |
| POST | `/api/management/files/{file_id}/process` | 处理文件 | 系统 |

### 账号对齐 (`/api/account-alignment`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/account-alignment/stats` | 查询对齐统计 | 系统 |
| GET | `/api/account-alignment/missing-mappings` | 查询缺失映射 | 系统 |

### 数据流转追踪 (`/api/data-flow`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/data-flow/trace` | 追踪数据流转 | 系统 |
| GET | `/api/data-flow/lineage` | 查询数据血缘 | 系统 |

### 数据一致性验证 (`/api/data-consistency`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/data-consistency/validate` | 验证数据一致性 | 系统 |
| GET | `/api/data-consistency/report` | 查询一致性报告 | 系统 |

### 指标分析 (`/api/metrics`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/metrics/associate-rate` | 查询连带率 | C类 |
| GET | `/api/metrics/cross-sell` | 查询交叉销售 | C类 |

### 原始数据层 (`/api/raw-layer`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/raw-layer/tables` | 查询原始表列表 | B类 |
| GET | `/api/raw-layer/query` | 查询原始数据 | B类 |

### 数据库设计验证 (`/api/database-design`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/database-design/validate` | 验证数据库设计 | 系统 |

### 性能监控 (`/api/performance`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/performance/monitor` | 查询性能监控数据 | 系统 |

### 测试诊断 (`/api/test`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/test/db` | 测试数据库连接 | 系统 |
| GET | `/api/test/files` | 测试文件系统 | 系统 |

### 健康检查 (`/api/health`, `/health`)

| 方法 | 路径 | 说明 | 数据分类 |
|------|------|------|---------|
| GET | `/api/health` | 健康检查 | 系统 |
| GET | `/health` | 健康检查（兼容路径） | 系统 |

---

## 📊 统计信息

### 按数据分类统计

- **A类数据API**: 约35个端点
- **B类数据API**: 约80个端点
- **C类数据API**: 约25个端点
- **系统管理API**: 约50个端点

**总计**: 约190个API端点

### 按HTTP方法统计

- **GET**: 约140个端点（查询操作）
- **POST**: 约40个端点（创建/计算操作）
- **PUT**: 约8个端点（更新操作）
- **DELETE**: 约8个端点（删除操作）

---

## 📝 使用说明

### 查看API文档

访问FastAPI自动生成的文档：
- **Swagger UI**: http://localhost:8001/api/docs
- **ReDoc**: http://localhost:8001/api/redoc

### API响应格式

所有API遵循统一的响应格式：
- **成功响应**: `{success: true, data: {...}, timestamp: "..."}`
- **错误响应**: `{success: false, error: {...}, message: "...", timestamp: "..."}`
- **分页响应**: `{success: true, data: [...], pagination: {...}, timestamp: "..."}`

详细说明请参考：[API契约标准](docs/API_CONTRACTS.md)

### 数据分类传输规范

详细说明请参考：[数据分类传输规范指南](docs/DATA_CLASSIFICATION_API_GUIDE.md)

---

## 🔄 更新记录

- **2025-01-31**: 创建初始API端点清单
- **2025-01-31**: 按数据分类组织端点
- **2025-01-31**: 添加统计信息和使用说明


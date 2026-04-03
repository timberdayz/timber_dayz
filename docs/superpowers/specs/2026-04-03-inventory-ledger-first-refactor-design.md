# Inventory Ledger-First Refactor Design

**日期:** 2026-04-03

**目标:** 将当前“库存管理”从旧的快照浏览/产品列表实现，重构为以 `InventoryLedger` 为唯一库存真源的真实库存业务模块；同时将现有库存快照页面独立为“库存总览”，彻底消除旧 `/api/products/*` 与 `/api/inventory/*` 双链路和领域模型错位问题。

## 1. 背景

当前仓库中的“库存管理”存在三类核心问题：

1. 主页面与真实库存领域错位  
   当前前端主入口 [frontend/src/views/InventoryManagement.vue](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/InventoryManagement.vue) 实际调用的是 `/api/products/*`，对应实现位于 [backend/routers/inventory_management.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory_management.py)。  
   这套链路主要基于 `b_class` inventory snapshot、`FactProductMetric` 和 `ProductImage`，本质更接近库存快照浏览与 SKU 展示，而不是库存业务模块。

2. 旧库存接口失效且不符合仓库 async 规则  
   [backend/routers/inventory.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory.py) 声明使用 `AsyncSession`，但内部仍使用同步 `execute()/fetch*()` 模式，并调用同步的 `InventoryAutomation`，与仓库当前 async-first 约束冲突。

3. ORM SSOT 已经给出更正确的库存模型  
   [modules/core/db/schema.py](F:/Vscode/python_programme/AI_code/xihong_erp/modules/core/db/schema.py) 中已经定义：
   - `GRNHeader`
   - `GRNLine`
   - `InventoryLedger`
   - `OpeningBalance`

   其中 `InventoryLedger` 注释明确为“唯一库存真源，记录所有出入库事务”。  
   当前运行链路并未围绕这组模型建设。

本次设计不做兼容层，不保留旧命名作为目标架构。当前环境仍是测试环境，允许直接进行命名、接口和页面结构重构。

## 2. 设计目标

本次设计要一次性达成以下目标：

1. 将“库存管理”重新定义为真实库存业务模块。
2. 将现有快照浏览页面拆分为独立的“库存总览”模块。
3. 以 `InventoryLedger` 作为唯一库存真源，禁止继续以快照表或 `FactProductMetric` 承担真实库存写路径。
4. 新库存 API 全部使用 `backend/schemas/` 与 `response_model`。
5. 彻底移除旧 `/api/inventory/*` 失效链路和 `/api/products/*` 作为库存主接口的错误定位。
6. 将库存业务写模型、读模型、总览模型分离，避免后续继续在一个 router 中混合图片、商品资料、库存快照和库存事务。

## 3. 术语与边界

### 3.1 库存管理

“库存管理”专指真实库存业务域，负责：

- 期初余额
- 入库单
- 出库/退货/调整过账
- 库存流水
- 当前结存
- 库存预警
- 库存对账

### 3.2 库存总览

“库存总览”专指库存快照/分析/浏览域，负责：

- 平台库存快照
- SKU 浏览
- 平台分布和低库存概览
- 商品图片与基础资料浏览
- 外部快照与内部账库存差异观察

### 3.3 库存真源

库存真源是 `InventoryLedger`。  
任何真实库存数量变化都必须先写入业务单据或业务事件，再由其过账到 `InventoryLedger`。

### 3.4 库存读模型

库存读模型是从 `OpeningBalance + InventoryLedger` 推导出来的查询结果，可采用 PostgreSQL view、materialized view 或 service query 方式实现，但不承担库存真源职责。

## 4. 总体架构

### 4.1 真源层

真实库存业务只依赖以下模型：

- `OpeningBalance`
- `GRNHeader`
- `GRNLine`
- `InventoryLedger`

建议补充：

- `InventoryAdjustmentHeader`
- `InventoryAdjustmentLine`

原因：

- 手工调账、盘点差异、报损报溢不能只在 ledger 中裸写事件；
- 需要保留单据头、单据行、原因、操作人、审批状态和业务备注；
- 过账动作将调整单转化为 ledger 事件，形成审计闭环。

### 4.2 读模型层

从真源推导以下读模型：

- `inventory_balance_current`
  - 当前 SKU 结存
  - 包含平台、店铺、SKU、期初、累计入库、累计出库、当前结存
- `inventory_movement_history`
  - 标准库存流水视图
- `inventory_alerts`
  - 低库存、缺货、负库存、异常波动
- `inventory_reconciliation`
  - 内部账库存 vs 外部平台快照差异

### 4.3 外部快照层

以下对象继续存在，但只用于总览和对账：

- `b_class` inventory snapshot
- `FactProductMetric`
- `ProductImage`

这些对象不再承担真实库存业务职责，不得直接作为库存真源。

## 5. 目标数据模型职责

### 5.1 `OpeningBalance`

职责：

- 每个期间的 SKU 期初结存
- 作为结存推导的起点

要求：

- 期间、平台、店铺、SKU 唯一
- 明确来源与创建人

### 5.2 `GRNHeader` / `GRNLine`

职责：

- 采购入库单据
- 记录业务入库来源
- 作为 receipt 类型 ledger 事件来源

要求：

- 单头/单行与 SKU、数量、仓库、供应商、收货日期绑定
- 过账后写入 ledger

### 5.3 `InventoryLedger`

职责：

- 唯一库存真源
- 记录 `receipt / sale / return / adjustment` 等库存变化
- 保存数量变化前后状态与成本轨迹

要求：

- 不允许页面直接更新“当前库存”字段绕过 ledger
- 所有库存变动必须可追溯到业务来源

### 5.4 `InventoryAdjustmentHeader` / `InventoryAdjustmentLine`

职责：

- 盘点差异、报损报溢、人工调账

要求：

- 允许草稿、审核、已过账状态
- 过账后生成 adjustment 类型 ledger 记录

## 6. 后端模块边界

### 6.1 新建真实库存业务 router

建议新建：

- `backend/routers/inventory_domain.py`

职责：

- 真实库存业务接口
- 不混入图片、商品资料和快照浏览逻辑

### 6.2 新建库存总览 router

建议新建：

- `backend/routers/inventory_overview.py`

职责：

- 快照浏览、平台分布、低库存概览、SKU 总览、快照对账

### 6.3 新建 schema 契约

建议新建：

- `backend/schemas/inventory.py`
- `backend/schemas/inventory_overview.py`

要求：

- 所有面向页面的接口声明 `response_model`
- 不再使用无契约裸字典作为稳定 API

### 6.4 新建 service 分层

建议新建：

- `backend/services/inventory/balance_service.py`
- `backend/services/inventory/ledger_service.py`
- `backend/services/inventory/grn_service.py`
- `backend/services/inventory/adjustment_service.py`
- `backend/services/inventory/reconciliation_service.py`
- `backend/services/inventory/overview_service.py`

要求：

- router 不直接承载复杂 SQL 或业务过账逻辑
- CRUD 型逻辑优先复用仓库已有异步 service 模式

## 7. API 设计

### 7.1 真实库存业务 API

前缀：

- `/api/inventory/*`

建议接口：

- `GET /api/inventory/balances`
- `GET /api/inventory/balances/{platform}/{shop_id}/{sku}`
- `GET /api/inventory/ledger`
- `GET /api/inventory/alerts`
- `GET /api/inventory/reconciliation`
- `GET /api/inventory/opening-balances`
- `POST /api/inventory/opening-balances`
- `GET /api/inventory/grns`
- `POST /api/inventory/grns`
- `GET /api/inventory/adjustments`
- `POST /api/inventory/adjustments`
- `POST /api/inventory/adjustments/{adjustment_id}/post`

规则：

- 所有写操作通过单据或过账接口完成
- 不提供“直接改库存数”的简化接口

### 7.2 库存总览 API

前缀：

- `/api/inventory-overview/*`

建议接口：

- `GET /api/inventory-overview/summary`
- `GET /api/inventory-overview/products`
- `GET /api/inventory-overview/products/{sku}`
- `GET /api/inventory-overview/platform-breakdown`
- `GET /api/inventory-overview/alerts`
- `GET /api/inventory-overview/reconciliation-snapshot`

规则：

- 只读
- 不承担真实库存写操作

### 7.3 商品资料 API

图片和商品基础资料从库存域拆离，建议后续独立为：

- `/api/catalog-products/*`

在本次重构中可先继续由 overview 域承接读取，但不再视为库存业务 API。

## 8. 前端页面结构

### 8.1 一级菜单

建议调整为两个菜单：

1. `库存管理`
2. `库存总览`

### 8.2 库存管理下的页面

- 当前结存
- 库存流水
- 库存调整
- 入库单管理
- 期初余额
- 库存预警
- 库存对账

### 8.3 库存总览下的页面

- 平台概览
- SKU 快照列表
- 低库存快照
- 图片和商品基础浏览
- 快照差异观察

### 8.4 现有页面重命名

当前页面：

- [frontend/src/views/InventoryManagement.vue](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/InventoryManagement.vue)

目标处理：

- 改名为 `InventoryOverview.vue`
- 页面标题从“库存管理”改为“库存总览”
- 请求路径从 `/api/products/*` 收敛到 `/api/inventory-overview/*`

## 9. 删除与重命名策略

### 9.1 直接删除

以下对象不纳入目标架构：

- [backend/routers/inventory.py](F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/inventory.py)
- [frontend/src/api/inventory.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/inventory.js)
- [frontend/src/stores/inventory.js](F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/stores/inventory.js)

原因：

- 旧接口链路与当前 async 规则不兼容
- 前端契约与后端实现严重漂移
- 保留只会继续误导后续开发

### 9.2 直接退出目标架构的命名

以下定位不再保留：

- `/api/products/*` 作为库存主接口
- “库存管理”页面实际是产品/快照页面

## 10. 迁移顺序

### Phase 1: 命名和边界切正

- 菜单改名
- 页面改名
- 新建 `inventory_overview` router
- 将旧 `/api/products/*` 功能迁移到 `/api/inventory-overview/*`

### Phase 2: 建立真实库存业务后端

- 新建 inventory schema
- 新建 inventory domain router
- 新建 inventory services
- 建立 ledger-first 读写路径

### Phase 3: 建立前端真实库存页面

- 当前结存
- 库存流水
- 库存调整
- 入库单管理
- 期初余额

### Phase 4: 建立对账与预警

- 内部账库存 vs 外部快照
- 低库存
- 缺货
- 异常波动

### Phase 5: 删除旧链路

- 移除旧 router
- 移除旧 store
- 移除旧 API 文件
- 清理所有继续引用旧路径的页面与测试

## 11. 测试与验证要求

实现阶段必须遵循：

- `systematic-debugging`
- `test-driven-development`
- `verification-before-completion`

至少补齐以下验证：

1. ledger 过账后结存正确
2. opening balance + ledger 推导当前结存正确
3. adjustment 过账前后流水和结存正确
4. GRN 入库后结存和流水正确
5. reconciliation 能正确计算内部账与外部快照差异
6. overview 列表不再因多期 `FactProductMetric` 查询导致详情异常

## 12. 非目标

本次设计不做以下事情：

- 不保留旧 `/api/inventory/*` 兼容层
- 不保留 `/api/products/*` 作为库存正式命名
- 不让 `FactProductMetric` 继续承担真实库存业务写路径
- 不在库存业务 router 中混入图片上传和商品资料管理

## 13. 结论

本次重构不是“修库存页面”，而是重新定义库存域。

最终目标是：

- `InventoryLedger` 成为唯一库存真源
- “库存管理”回归真实库存业务模块
- “库存总览”承接快照和分析职责
- 旧库存接口、旧产品化库存命名和失效契约一次性清理

在测试环境下，这是最合适的一次切正边界的时机。

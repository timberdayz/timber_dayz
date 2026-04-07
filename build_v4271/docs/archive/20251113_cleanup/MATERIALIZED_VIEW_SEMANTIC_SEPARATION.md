# ✅ 物化视图语义分离架构设计（v4.10.0）

## 🎯 设计原则

### 核心问题
用户提出：库存和产品是分开的数据域，物化视图混合两个域的数据会造成Agent误解。

### 解决方案：语义分离架构

**原则**：每个数据域使用独立的物化视图和查询方法，避免语义混淆。

## 📊 物化视图架构

### 1. Products域视图（商品销售表现）

**视图名称**: `mv_product_management`  
**数据域**: `products`  
**数据来源**: Shopee/TikTok等电商平台的商品销售数据  
**查询方法**: `MaterializedViewService.query_product_management()`

**包含字段**:
- 商品基本信息（SKU、名称、分类、品牌）
- 价格信息（价格、货币、人民币价格）
- 库存信息（库存数量、状态）
- **销售指标**（销量、销售额、转化率）
- **流量指标**（浏览量、访客数、点击率）
- 产品健康度评分

**用途**:
- 商品销售表现分析
- TopN产品排行
- 销售趋势分析
- 店铺维度汇总

### 2. Inventory域视图（库存快照）

**视图名称**: `mv_inventory_by_sku`  
**数据域**: `inventory`  
**数据来源**: miaoshou ERP库存快照数据  
**查询方法**: `MaterializedViewService.query_inventory_management()`

**包含字段**:
- SKU基本信息（SKU、产品名称、仓库）
- **库存信息**（总库存、可用库存、预留库存、在途库存）
- 库存状态（out_of_stock/low_stock/medium_stock/high_stock）
- 时间维度（快照日期、粒度）

**不包含字段**（与products域区分）:
- ❌ 价格信息（库存快照不包含价格）
- ❌ 销售指标（库存快照不包含销售数据）
- ❌ 流量指标（库存快照不包含流量数据）

**用途**:
- 库存管理界面
- 库存快照查询
- 低库存预警
- 库存汇总统计

### 3. 库存汇总视图（平台/店铺维度）

**视图名称**: `mv_inventory_summary`  
**数据域**: `inventory`  
**查询方法**: 直接查询视图或通过统计API

**包含字段**:
- 平台/店铺/仓库维度汇总
- 总产品数、总库存量
- 低库存/缺货统计

## 🔧 代码实现

### MaterializedViewService方法分离

```python
# Products域查询（商品销售表现）
MaterializedViewService.query_product_management()
  → 查询 mv_product_management 视图
  → 数据域: products
  → 包含: 价格、销售、流量指标

# Inventory域查询（库存快照）
MaterializedViewService.query_inventory_management()
  → 查询 mv_inventory_by_sku 视图
  → 数据域: inventory
  → 只包含: 库存信息
```

### API路由分离

```python
# 库存管理API（使用inventory域视图）
GET /api/products/products
  → 调用 MaterializedViewService.query_inventory_management()
  → 返回: inventory域数据（库存快照）

# 产品管理API（使用products域视图）
# 未来可创建: GET /api/products/sales-performance
  → 调用 MaterializedViewService.query_product_management()
  → 返回: products域数据（商品销售表现）
```

## ⚠️ 重要说明

### 为什么库存管理API路径是 `/api/products/products`？

**历史原因**：
- 此API最初设计用于产品管理
- 后来扩展为库存管理（融合了产品管理和库存看板）
- 为了向后兼容，保留了原有路径

**语义说明**：
- 虽然路径是 `/products/products`，但实际查询的是 `inventory` 域数据
- API内部使用 `query_inventory_management()` 方法
- 返回的数据明确标识 `data_domain: "inventory"`

### Agent开发指南

**查询库存数据时**：
- ✅ 使用 `MaterializedViewService.query_inventory_management()`
- ✅ 查询 `mv_inventory_by_sku` 视图
- ✅ 数据域标识：`data_domain: "inventory"`

**查询商品销售数据时**：
- ✅ 使用 `MaterializedViewService.query_product_management()`
- ✅ 查询 `mv_product_management` 视图
- ✅ 数据域标识：`data_domain: "products"`

**禁止行为**：
- ❌ 不要将两个域的数据混合在一个视图中
- ❌ 不要在一个查询方法中同时查询两个域
- ❌ 不要忽略 `data_domain` 字段

## 📋 文件清单

### SQL脚本
- ✅ `sql/create_mv_product_management.sql` - products域视图（只包含products域）
- ✅ `sql/materialized_views/create_inventory_views.sql` - inventory域视图

### Python服务
- ✅ `backend/services/materialized_view_service.py`
  - `query_product_management()` - products域查询
  - `query_inventory_management()` - inventory域查询（v4.10.0新增）

### API路由
- ✅ `backend/routers/inventory_management.py` - 使用 `query_inventory_management()`

### 创建脚本
- ✅ `scripts/create_mv_product_management_fixed.py` - 创建products域视图
- ✅ `scripts/create_inventory_views_simple.py` - 创建inventory域视图

## ✅ 验证清单

- [x] `mv_product_management` 只包含 `products` 域数据
- [x] `mv_inventory_by_sku` 只包含 `inventory` 域数据
- [x] `query_product_management()` 查询products域视图
- [x] `query_inventory_management()` 查询inventory域视图
- [x] 库存管理API使用inventory域查询方法
- [x] 统计API同时支持两个域（从fact表查询）

## 🎯 架构优势

1. **语义清晰**：每个视图对应一个数据域，不会混淆
2. **Agent友好**：方法名和视图名明确标识数据域
3. **易于维护**：修改一个域不影响另一个域
4. **性能优化**：每个视图只包含必要字段，查询更快
5. **扩展性强**：未来新增数据域时，只需创建新视图和新方法

---

**版本**: v4.10.0  
**更新时间**: 2025-11-09  
**状态**: ✅ 完成


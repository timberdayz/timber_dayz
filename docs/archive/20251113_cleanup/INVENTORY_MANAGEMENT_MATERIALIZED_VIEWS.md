# 📊 库存管理页面对应的物化视图说明

## 🎯 库存管理页面功能与物化视图映射

### 1. 库存列表（Inventory List）

**前端位置**: 库存管理页面 → "库存列表"表格  
**API端点**: `GET /api/products/products`  
**物化视图**: `mv_inventory_by_sku`  
**查询方法**: `MaterializedViewService.query_inventory_management()`

**视图字段**:
- `metric_id` - 指标ID
- `platform_code` - 平台代码（可能为NULL，inventory域）
- `shop_id` - 店铺ID（可能为NULL，inventory域）
- `platform_sku` - 产品SKU
- `product_name` - 产品名称
- `warehouse` - 仓库
- `total_stock` - 总库存
- `available_stock` - 可用库存
- `reserved_stock` - 预留库存
- `in_transit_stock` - 在途库存
- `stock_status` - 库存状态（out_of_stock/low_stock/medium_stock/high_stock）
- `metric_date` - 快照日期
- `granularity` - 粒度（snapshot）

**数据域**: `inventory`  
**数据来源**: `fact_product_metrics` 表（`data_domain = 'inventory'`）

---

### 2. 库存概览KPI（Top-Level KPIs）

**前端位置**: 库存管理页面 → 顶部4个统计卡片  
**API端点**: `GET /api/products/stats/platform-summary`  
**数据来源**: 直接从 `fact_product_metrics` 表查询（非物化视图）

**统计指标**:
- **总库存** (`total_stock`): 所有产品的总库存量
- **低库存预警** (`low_stock_count`): 库存 < 10 的产品数量
- **缺货数量** (`out_of_stock_count`): 库存 = 0 的产品数量
- **库存价值** (`total_value`): 总库存 × 单价

**查询逻辑**:
```python
# 从fact_product_metrics表查询（同时包含products和inventory域）
query = db.query(FactProductMetric).filter(
    or_(
        FactProductMetric.data_domain == 'products',
        FactProductMetric.data_domain == 'inventory',
        # 向后兼容：NULL data_domain但platform_code不为空
        and_(
            FactProductMetric.data_domain.is_(None),
            FactProductMetric.platform_code.isnot(None)
        )
    )
)
```

---

### 3. 平台库存分布（Platform Inventory Distribution）

**前端位置**: 库存管理页面 → "平台库存分布"表格  
**API端点**: `GET /api/products/stats/platform-summary`  
**数据来源**: 直接从 `fact_product_metrics` 表查询（非物化视图）

**统计维度**:
- 按 `platform_code` 分组
- 统计每个平台的产品数、总库存、库存占比

**查询逻辑**:
```python
# 分平台统计（处理inventory域platform_code可能为NULL的情况）
platforms = db.query(FactProductMetric.platform_code).filter(
    FactProductMetric.platform_code.isnot(None)
).distinct().all()

for platform in platforms:
    # 统计该平台的产品数、总库存
    platform_stats.append({
        'platform': platform,
        'product_count': ...,
        'total_stock': ...
    })
```

---

### 4. 库存健康度（Inventory Health）

**前端位置**: 库存管理页面 → "库存健康度"进度条  
**API端点**: `GET /api/products/stats/platform-summary`  
**数据来源**: 前端计算（基于统计API返回的数据）

**计算公式**:
```javascript
// 健康度评分（100分制）
const lowStockRatio = low_stock_count / total_products
const outStockRatio = out_of_stock_count / total_products
const score = 100 - (lowStockRatio * 30) - (outStockRatio * 50)
```

**健康度等级**:
- ≥90分: 健康（绿色）
- 70-89分: 一般（黄色）
- <70分: 需关注（红色）

---

## 📋 物化视图清单

### 直接使用的物化视图

1. **`mv_inventory_by_sku`** ⭐
   - **用途**: 库存列表查询
   - **数据域**: `inventory`
   - **粒度**: `snapshot`
   - **查询方法**: `MaterializedViewService.query_inventory_management()`
   - **刷新频率**: 手动刷新或定时刷新

### 间接使用的物化视图（未来可能使用）

2. **`mv_inventory_summary`** 🔮
   - **用途**: 平台/店铺/仓库维度汇总统计
   - **数据域**: `inventory`
   - **粒度**: `snapshot`
   - **当前状态**: 已创建，但统计API直接从fact表查询
   - **未来优化**: 统计API可改为查询此视图，提升性能

### 不使用的物化视图（语义分离）

3. **`mv_product_management`** ❌
   - **用途**: 商品销售表现（products域）
   - **数据域**: `products`
   - **不用于**: 库存管理页面（避免语义混淆）

---

## 🔄 数据流图

```
库存管理页面
    │
    ├─→ GET /api/products/products
    │       │
    │       └─→ MaterializedViewService.query_inventory_management()
    │               │
    │               └─→ mv_inventory_by_sku (物化视图)
    │                       │
    │                       └─→ fact_product_metrics (基础表)
    │                               WHERE data_domain = 'inventory'
    │
    └─→ GET /api/products/stats/platform-summary
            │
            └─→ 直接查询 fact_product_metrics 表
                    WHERE data_domain IN ('products', 'inventory')
```

---

## ⚠️ 重要说明

### 为什么统计API不使用物化视图？

**当前设计**:
- 统计API直接从 `fact_product_metrics` 表查询
- 同时包含 `products` 和 `inventory` 两个域的数据
- 支持实时统计，无需等待物化视图刷新

**未来优化方向**:
- 如果数据量很大，可以考虑：
  1. 使用 `mv_inventory_summary` 查询inventory域统计
  2. 使用 `mv_shop_product_summary` 查询products域统计
  3. 在API层合并两个域的统计结果

### 图片查询问题

**问题**: inventory域数据的 `platform_code` 和 `shop_id` 可能为 `NULL`，导致图片查询失败。

**解决方案**: 
- 如果 `platform_code` 或 `shop_id` 为 `NULL`，只使用 `platform_sku` 查询图片
- 图片表 `ProductImage` 应该支持只关联SKU的图片（不强制要求platform_code和shop_id）

---

## 📝 相关文件

### SQL脚本
- `sql/materialized_views/create_inventory_views.sql` - 创建inventory域物化视图

### Python服务
- `backend/services/materialized_view_service.py`
  - `query_inventory_management()` - 查询库存列表

### API路由
- `backend/routers/inventory_management.py`
  - `GET /api/products/products` - 库存列表
  - `GET /api/products/stats/platform-summary` - 统计汇总

### 前端组件
- `frontend/src/views/InventoryManagement.vue` - 库存管理页面

---

**版本**: v4.10.0  
**更新时间**: 2025-11-09  
**状态**: ✅ 完成


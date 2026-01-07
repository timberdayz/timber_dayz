# v4.9.1库存显示问题修复方案

**问题**: 产品管理和库存管理页面显示库存为0  
**根本原因**: 数据存在但前端未正确使用  

---

## 📊 数据现状分析（2025-11-05）

### ✅ 数据库实际情况

| 项目 | 状态 | 说明 |
|------|------|------|
| fact_product_metrics | ✅ 有数据 | 1095行，62.5%有库存（684个） |
| 总库存量 | ✅ 10,365 | 实际库存数据 |
| 平均库存 | ✅ 9.47 | 每个产品平均库存 |
| mv_product_management | ⚠️ 需刷新 | 1095行，但stock列显示0 |

### ❌ 前端显示问题

| 页面 | 显示值 | 实际值 | 问题 |
|------|--------|--------|------|
| 产品管理 - 库存列 | 0（红色） | 应该10/50/2等 | 使用错误字段 |
| 库存管理 - 总商品数 | 0 | 应该1095 | 无API实现 |
| 库存管理 - 总库存 | 0 | 应该10,365 | 无API实现 |

---

## 🔍 根本原因

### 原因1: fact_product_metrics字段使用混乱 ⭐⭐⭐

**字段混乱**:
```
fact_product_metrics表有5个库存字段：
- stock（主要字段，大部分数据都是0）⚠️
- total_stock（总库存，有正确数据）✅
- available_stock（可用库存，有正确数据）✅
- reserved_stock（预留库存）
- in_transit_stock（在途库存）
```

**问题**: 
- 产品管理API使用`stock`字段（大部分为0）
- 应该使用`available_stock`或`total_stock`

### 原因2: 物化视图需要刷新

**物化视图status**:
- mv_product_management: 定义正确，但`stock`列返回0
- 需要刷新以同步最新数据

### 原因3: 库存管理页面无API实现

**问题**:
- InventoryManagement.vue存在
- 但backend没有对应的inventory_management.py API
- 前端无法查询库存数据

---

## ✅ 修复方案

### Step 1: 刷新物化视图（立即）

```bash
python -c "from backend.services.materialized_view_service import MaterializedViewService; from backend.models.database import SessionLocal; db = SessionLocal(); MaterializedViewService.refresh_product_management_view(db, triggered_by='manual'); db.close()"
```

### Step 2: 修复产品管理API使用正确字段

**文件**: `backend/routers/product_management.py`

**修改**: 使用`available_stock`或`total_stock`代替`stock`

```python
# ❌ 错误：使用stock（大部分为0）
'stock': product.get('stock')

# ✅ 正确：使用available_stock或total_stock
'stock': product.get('available_stock') or product.get('total_stock') or 0
```

### Step 3: 创建库存管理API

**新建文件**: `backend/routers/inventory_management.py`

**功能**:
```python
@router.get("/inventory/summary")
async def get_inventory_summary():
    """库存汇总统计"""
    - 总商品数
    - 总库存价值
    - 低库存预警数量
    - 平均周转率

@router.get("/inventory/list")
async def get_inventory_list():
    """库存清单"""
    - 使用mv_product_management或fact_product_metrics
    - 返回SKU、商品名、库存、成本等
```

### Step 4: 更新前端InventoryManagement.vue

**文件**: `frontend/src/views/InventoryManagement.vue`

**修改**: 调用新建的库存管理API

---

## 🚀 实施步骤

### 阶段1: 立即修复（10分钟）
1. [ ] 刷新物化视图
2. [ ] 修复产品管理API字段使用
3. [ ] 重启后端

### 阶段2: 库存管理完整实现（30分钟）
1. [ ] 创建inventory_management.py API
2. [ ] 更新InventoryManagement.vue调用
3. [ ] 集成到后端main.py

### 阶段3: 测试验证（10分钟）
1. [ ] 访问产品管理：库存显示正确数值
2. [ ] 访问库存管理：显示1095个商品
3. [ ] 验证库存汇总数据

---

## 📈 预期结果

### 修复后效果

| 页面 | 当前值 | 修复后值 |
|------|--------|---------|
| 产品管理 - 有库存产品数 | 0 | 684个（62.5%） |
| 产品管理 - 库存列 | 0（红色） | 10/50/2等（实际值） |
| 库存管理 - 总商品数 | 0 | 1095 |
| 库存管理 - 总库存价值 | ¥0.00 | 计算值 |
| 库存管理 - 低库存预警 | 0 | 实际低库存数量 |

---

## 💡 长期优化建议

### 1. 统一库存字段使用

**规范**:
- `total_stock`: 总库存（物理库存）
- `available_stock`: 可用库存（可售库存 = 总库存 - 预留 - 在途）
- `reserved_stock`: 预留库存（已下单未发货）
- `in_transit_stock`: 在途库存（采购中）

**建议**: 废弃`stock`字段，统一使用`total_stock`和`available_stock`

### 2. 创建专用库存物化视图

**新视图**: `mv_inventory_summary`

```sql
CREATE MATERIALIZED VIEW mv_inventory_summary AS
SELECT 
    platform_code,
    shop_id,
    platform_sku,
    product_name,
    
    -- 库存详情
    total_stock,
    available_stock,
    reserved_stock,
    in_transit_stock,
    
    -- 库存价值
    total_stock * price_rmb as inventory_value,
    
    -- 库存状态
    CASE 
        WHEN available_stock = 0 THEN 'out_of_stock'
        WHEN available_stock < 10 THEN 'low_stock'
        ELSE 'normal'
    END as stock_status,
    
    -- 周转率
    CASE 
        WHEN sales_volume_30d > 0 
        THEN ROUND(available_stock::numeric / (sales_volume_30d::numeric / 30), 1)
        ELSE 999
    END as turnover_days
    
FROM fact_product_metrics
WHERE metric_date = (SELECT MAX(metric_date) FROM fact_product_metrics)
```

### 3. 定期数据质量检查

**脚本**: `scripts/check_inventory_quality.py`

**检查项**:
- 库存字段一致性（stock vs total_stock）
- 库存计算逻辑（total = available + reserved + in_transit）
- 负库存预警
- 异常周转率预警

---

**立即行动**: 让我开始实施修复...


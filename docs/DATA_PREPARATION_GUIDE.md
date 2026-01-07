# 数据准备指南 - 物化视图数据填充

**问题**: 物化视图为空或数据很少  
**原因分析**: 源数据表数据不足，维度表未填充  
**解决方案**: 采集数据→入库→自动刷新物化视图  

---

## 🔍 当前数据状态分析

### 检查结果（2025-11-05）

| 表名 | 行数 | 状态 | 说明 |
|------|------|------|------|
| **物化视图** | | | |
| mv_product_management | 1 | ⚠️ 数据少 | 只有1个产品 |
| mv_product_sales_trend | 0 | ❌ 空 | 无趋势数据 |
| mv_top_products | 0 | ❌ 空 | 无产品数据 |
| mv_shop_product_summary | 1 | ⚠️ 数据少 | 只有1个店铺 |
| **源数据表** | | | |
| fact_product_metrics | 1 | ⚠️ 数据少 | 只有1个产品指标 |
| fact_orders | 3,707 | ✅ 充足 | 订单数据充足 |
| staging_orders | 21,831 | ✅ 充足 | 暂存数据充足 |
| **维度表** | | | |
| dim_platforms | 0 | ❌ 空 | **关键问题！** |
| dim_shops | 0 | ❌ 空 | **关键问题！** |

---

## 🐛 根本原因分析

### 原因1: 维度表为空 ⭐⭐⭐

**问题**: `dim_platforms`和`dim_shops`都是0行

**影响**:
```sql
-- 物化视图定义
SELECT 
    p.*,
    plat.name as platform_name,  -- LEFT JOIN dim_platforms
    s.shop_slug as shop_name     -- LEFT JOIN dim_shops
FROM fact_product_metrics p
LEFT JOIN dim_platforms plat ON p.platform_code = plat.platform_code
LEFT JOIN dim_shops s ON p.shop_id = s.shop_id

-- 结果：即使fact_product_metrics有数据，JOIN后platform_name和shop_name都是NULL
```

**维度表是物化视图的基础！**

### 原因2: 产品数据未入库

**问题**: `fact_product_metrics`只有1行数据

**原因**:
- 数据还在`staging_orders`中（21,831行）
- 可能未进行"产品数据域"的字段映射和入库
- 订单数据入库了（3,707行），但产品数据没有

---

## ✅ 解决方案（3步走）

### Step 1: 初始化维度表 ⭐⭐⭐

**目的**: 填充`dim_platforms`和`dim_shops`

**方法1: 从已有数据自动提取**（推荐）

```sql
-- 1. 填充dim_platforms
INSERT INTO dim_platforms (platform_code, name, platform_type, is_active)
SELECT DISTINCT 
    platform_code,
    platform_code as name,  -- 暂时用platform_code作为name
    'ecommerce' as platform_type,
    true as is_active
FROM catalog_files
WHERE platform_code IS NOT NULL
ON CONFLICT (platform_code) DO NOTHING;

-- 2. 填充dim_shops
INSERT INTO dim_shops (platform_code, shop_id, shop_slug, shop_name, is_active)
SELECT DISTINCT 
    platform_code,
    shop_id,
    shop_id as shop_slug,
    shop_id as shop_name,  -- 暂时用shop_id作为名称
    true as is_active
FROM catalog_files
WHERE platform_code IS NOT NULL AND shop_id IS NOT NULL
ON CONFLICT (platform_code, shop_id) DO NOTHING;
```

**方法2: 手动录入**（精确控制）

访问系统管理页面，手动添加：
- 妙手平台：`miaoshou` / "妙手ERP"
- Shopee平台：`shopee` / "Shopee"
- Amazon平台：`amazon` / "Amazon"

### Step 2: 采集并入库产品数据

**路径**: 数据采集与管理 → 采集配置

1. **选择平台**: 妙手ERP / Shopee
2. **选择数据域**: **产品表现**（products）⭐
3. **选择粒度**: daily / snapshot
4. **日期范围**: 最近30天
5. **开始采集**: 等待采集完成

### Step 3: 字段映射并入库

**路径**: 数据采集与管理 → 字段映射审核

1. **选择文件**: 选择产品数据域的文件
2. **智能映射**: 系统自动识别字段
3. **确认映射**: 检查映射正确性
4. **数据入库**: 点击"数据入库"按钮

### Step 4: 自动刷新物化视图

**无需手动操作**:
- 系统每15分钟自动刷新
- 或访问数据浏览器手动刷新

---

## 🚀 快速初始化脚本（推荐）

**文件**: `scripts/init_dimension_tables.py`

```python
"""
初始化维度表 - 从catalog_files自动提取
执行：python scripts/init_dimension_tables.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.db import DimPlatform, DimShop
from sqlalchemy import text

db = SessionLocal()

try:
    # 1. 从catalog_files提取平台
    result = db.execute(text("""
        SELECT DISTINCT platform_code
        FROM catalog_files
        WHERE platform_code IS NOT NULL
    """))
    
    platforms = []
    for row in result:
        platform_code = row[0]
        platform_name_map = {
            'miaoshou': '妙手ERP',
            'shopee': 'Shopee',
            'amazon': 'Amazon',
            'tiktok': 'TikTok'
        }
        
        platform = DimPlatform(
            platform_code=platform_code,
            name=platform_name_map.get(platform_code, platform_code),
            platform_type='ecommerce',
            is_active=True
        )
        platforms.append(platform)
    
    # 批量插入（忽略冲突）
    for plat in platforms:
        db.merge(plat)
    
    print(f"[OK] Inserted {len(platforms)} platforms")
    
    # 2. 从catalog_files提取店铺
    result = db.execute(text("""
        SELECT DISTINCT platform_code, shop_id
        FROM catalog_files
        WHERE platform_code IS NOT NULL AND shop_id IS NOT NULL
    """))
    
    shops = []
    for row in result:
        platform_code, shop_id = row[0], row[1]
        
        shop = DimShop(
            platform_code=platform_code,
            shop_id=shop_id,
            shop_slug=shop_id,
            shop_name=shop_id,  # 暂时用shop_id作为名称
            is_active=True
        )
        shops.append(shop)
    
    for shop in shops:
        db.merge(shop)
    
    print(f"[OK] Inserted {len(shops)} shops")
    
    db.commit()
    
    print("\n[SUCCESS] Dimension tables initialized!")
    print("Next: Refresh materialized views")
    
except Exception as e:
    db.rollback()
    print(f"[ERROR] {e}")
    raise
finally:
    db.close()
```

---

## 📋 完整数据准备检查清单

### 阶段1: 初始化维度表（5分钟）
- [ ] 运行`python scripts/init_dimension_tables.py`
- [ ] 验证：`SELECT COUNT(*) FROM dim_platforms`（应 > 0）
- [ ] 验证：`SELECT COUNT(*) FROM dim_shops`（应 > 0）

### 阶段2: 采集产品数据（10-30分钟）
- [ ] 访问"采集配置"页面
- [ ] 选择平台（妙手/Shopee）
- [ ] 选择"产品表现"数据域 ⭐
- [ ] 采集最近30天数据
- [ ] 等待采集完成

### 阶段3: 字段映射入库（5-10分钟）
- [ ] 访问"字段映射审核"页面
- [ ] 选择产品数据域文件
- [ ] 检查智能映射结果
- [ ] 点击"数据入库"
- [ ] 验证：`SELECT COUNT(*) FROM fact_product_metrics`（应 > 100）

### 阶段4: 刷新物化视图（1分钟）
- [ ] 方式1（推荐）：等待15分钟自动刷新
- [ ] 方式2：访问数据浏览器，手动点击"🔄刷新物化视图"
- [ ] 验证：`SELECT COUNT(*) FROM mv_product_management`（应 > 100）

---

## 🎯 预期结果

### 完成后的数据状态

| 表名 | 预期行数 | 用途 |
|------|---------|------|
| dim_platforms | 2-4 | 平台维度 |
| dim_shops | 5-10 | 店铺维度 |
| fact_product_metrics | 100-1000+ | 产品指标（依赖采集） |
| mv_product_management | 100-1000+ | 产品管理看板 |
| mv_top_products | 100-1000+ | TopN排行 |
| mv_product_sales_trend | 3000+ | 趋势分析（90天×产品数） |
| mv_shop_product_summary | 5-10 | 店铺汇总 |

### 完成后可用功能

- ✅ 产品管理页面（显示所有产品）
- ✅ TopN产品排行（Top100产品）
- ✅ 库存健康仪表盘（库存分布）
- ✅ 产品质量仪表盘（质量分析）
- ✅ 销售趋势分析（趋势图表）
- ✅ 数据浏览器（查看所有物化视图数据）

---

## ⚠️ 常见问题

### Q1: 为什么物化视图是空的？

**A**: 源数据表（fact_product_metrics）数据不足，或维度表（dim_platforms, dim_shops）为空。

**解决**: 先初始化维度表，再采集产品数据。

### Q2: 我已经有staging_orders的数据，为什么物化视图还是空？

**A**: staging_orders是订单数据，不是产品数据。物化视图`mv_product_management`依赖`fact_product_metrics`。

**解决**: 采集"产品表现"数据域，而非"订单表现"。

### Q3: 多久刷新一次物化视图？

**A**: 系统每15分钟自动刷新。也可手动刷新（数据浏览器→选择物化视图→点击🔄刷新）。

### Q4: 刷新需要多久？

**A**: 取决于数据量：
- 100行数据：<1秒
- 1000行数据：1-3秒
- 10000行数据：5-10秒

---

## 🎁 总结

**物化视图为空的原因**: 

1. ❌ 维度表未初始化（dim_platforms, dim_shops为空）
2. ❌ 产品数据未采集（只有1行fact_product_metrics）
3. ✅ 订单数据充足（3707行），但订单和产品是不同数据域

**解决步骤**:
1. ✅ 运行初始化脚本（5分钟）
2. ✅ 采集产品数据（30分钟）
3. ✅ 字段映射入库（10分钟）
4. ✅ 自动刷新物化视图（15分钟或手动）

**完成后**: 所有看板都有丰富的数据展示！

---

**立即行动**: 让我创建初始化脚本...


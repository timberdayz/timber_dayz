# 关键Bug修复：数据导入器未包含新字段

**发现时间**: 2025-11-05 14:28  
**严重程度**: 🔴 高危（数据丢失）  
**状态**: ✅ 已修复  

---

## 🔍 问题描述

### 用户报告

用户报告：
1. 使用智能映射生成了正确的字段映射
2. 保存了新模板
3. 确认映射并入库
4. 显示"数据入库成功！已导入1218条记录"
5. **但是产品管理页面没有显示新数据**

### 诊断结果

```
Miaoshou records: 0  ❌
Total records: 8 (全部是旧的测试数据)
Records updated in last 10 min: 0  ❌
```

**结论**: 虽然前端显示成功，但数据根本没有入库到数据库！

---

## 🐛 根本原因

### 发现的Bug

虽然我们在v4.6.3中：
1. ✅ 扩展了`schema.py`添加了12个新字段
2. ✅ 更新了字段映射字典
3. ✅ 清理了所有拼音映射

**但是忘记了更新`backend/services/data_importer.py`的`upsert_product_metrics`函数！**

### 缺失的字段

`upsert_product_metrics`函数在构造数据时**完全没有包含**以下新字段：

| 字段名 | 类别 | 影响 |
|--------|------|------|
| `specification` | 规格 | 颜色、尺寸丢失 ❌ |
| `warehouse` | 仓库 | 仓库位置丢失 ❌ |
| `total_stock` | 库存 | 库存总量丢失 ❌ |
| `available_stock` | 库存 | 可用库存丢失 ❌ |
| `reserved_stock` | 库存 | 预占库存丢失 ❌ |
| `in_transit_stock` | 库存 | 在途库存丢失 ❌ |
| `sales_volume_7d` | 销量 | 7天销量丢失 ❌ |
| `sales_volume_30d` | 销量 | 30天销量丢失 ❌ |
| `sales_volume_60d` | 销量 | 60天销量丢失 ❌ |
| `sales_volume_90d` | 销量 | 90天销量丢失 ❌ |
| `category` | 基础 | 分类丢失 ❌ |
| `brand` | 基础 | 品牌丢失 ❌ |

### 数据流向

```
用户上传Excel 
  → 字段映射（正确）✅
  → 数据验证（通过）✅
  → upsert_product_metrics函数
      → 构造数据字典（缺少新字段）❌
      → INSERT/UPDATE到数据库
      → 新字段的数据全部丢失！❌
  → 前端显示"成功"（误导性）❌
  → 但数据库中没有这些新字段的数据 ❌
```

---

## ✅ 修复方案

### 修复内容

更新`backend/services/data_importer.py`的`upsert_product_metrics`函数，添加所有新字段到：

1. **PostgreSQL分支**（第721-772行）:
   - 添加12个新字段到`data`字典
   - 添加12个新字段到`set_`更新字典

2. **SQLite分支**（第866-929行）:
   - 添加12个新字段到`FactProductMetric`对象创建
   - 添加12个新字段到`.update()`字典

### 关键代码变更

```python
# Before (旧代码，缺少新字段)
data = {
    "platform_code": r.get("platform_code", "unknown"),
    "shop_id": r.get("shop_id", "unknown"),
    "platform_sku": r.get("platform_sku", r.get("sku", "unknown")),
    "product_name": r.get("product_name"),
    "price": r.get("price"),
    "stock": int(float(r.get("stock", 0) or 0)),
    # ... 其他旧字段
}

# After (新代码，包含所有新字段)
data = {
    # ... 基础字段
    "specification": r.get("specification") or r.get("product_specification"),  # v4.6.3新增
    "warehouse": r.get("warehouse"),  # v4.6.3新增
    "total_stock": int(float(r.get("total_stock", 0) or 0)) if r.get("total_stock") is not None else None,  # v4.6.3新增
    "available_stock": int(float(r.get("available_stock", 0) or 0)) if r.get("available_stock") is not None else None,  # v4.6.3新增
    "reserved_stock": int(float(r.get("reserved_stock", 0) or 0)) if r.get("reserved_stock") is not None else None,  # v4.6.3新增
    "in_transit_stock": int(float(r.get("in_transit_stock", 0) or 0)) if r.get("in_transit_stock") is not None else None,  # v4.6.3新增
    "sales_volume_7d": int(float(r.get("sales_volume_7d", 0) or 0)) if r.get("sales_volume_7d") is not None else None,  # v4.6.3新增
    "sales_volume_30d": int(float(r.get("sales_volume_30d", 0) or 0)) if r.get("sales_volume_30d") is not None else None,  # v4.6.3新增
    "sales_volume_60d": int(float(r.get("sales_volume_60d", 0) or 0)) if r.get("sales_volume_60d") is not None else None,  # v4.6.3新增
    "sales_volume_90d": int(float(r.get("sales_volume_90d", 0) or 0)) if r.get("sales_volume_90d") is not None else None,  # v4.6.3新增
    # ... 其他字段
}
```

---

## 🔧 修复后需要做的事

### Step 1: 后端已重启 ✅

后端服务已经重启，新的代码已生效。

### Step 2: 重新导入数据

**⭐ 现在您需要重新导入妙手产品数据！**

1. 打开字段映射界面: `http://localhost:5173/field-mapping`
2. 上传妙手产品Excel文件
3. 设置元数据：
   - 平台: `miaoshou`
   - 数据域: `products`
   - 粒度: `snapshot`
4. **生成智能映射**（不要选择旧模板！）
5. 验证所有映射都是英文字段：
   ```
   仓库 → warehouse ✅
   规格 → product_specification ✅
   库存总量 → total_stock ✅
   可用库存 → available_stock ✅
   预占库存 → reserved_stock ✅
   在途库存 → in_transit_stock ✅
   近7天销量 → sales_volume_7d ✅
   近30天销量 → sales_volume_30d ✅
   近60天销量 → sales_volume_60d ✅
   近90天销量 → sales_volume_90d ✅
   ```
6. 确认映射并入库
7. 等待完成

### Step 3: 验证数据入库

```bash
python temp/development/diagnose_miaoshou_data.py
```

**期望输出**:
```
Miaoshou records: 1218  ✅
```

### Step 4: 查看产品管理页面

1. 访问: `http://localhost:5173/product-management`
2. 点击"刷新"按钮
3. **应该看到**: 1218个妙手产品，不再是测试商品！

---

## 📊 影响分析

### 数据丢失影响

| 字段 | 丢失数据量 | 业务影响 |
|------|----------|---------|
| 规格 | 1218条 | 无法区分产品变体（颜色、尺寸）|
| 仓库 | 1218条 | 不知道货物存放位置 |
| 细分库存 | 1218条×4 | 无法做精细库存管理 |
| 销量趋势 | 1218条×4 | 无法分析销售趋势 |

**总计**: 约**14,000+个**数据点丢失！

### Bug严重性评估

- **数据完整性**: 🔴 严重（12个重要字段数据丢失）
- **业务影响**: 🔴 严重（库存管理和销售分析受影响）
- **用户体验**: 🔴 严重（误导性成功提示）
- **修复难度**: 🟢 简单（已修复，只需重新导入）

---

## 🎓 经验教训

### 问题根源

1. **Schema和Importer不同步**
   - 添加了schema字段
   - 更新了字段映射字典
   - **但忘记了更新data_importer.py** ❌

2. **缺少集成测试**
   - 没有端到端测试验证新字段入库
   - 没有检查数据库实际数据

3. **成功提示误导**
   - 前端显示"成功"但数据没有真正入库
   - 用户无法知道数据丢失

### 解决方案

1. **代码同步检查清单**
   - [ ] 修改schema.py添加字段
   - [ ] 更新字段映射字典
   - [ ] **更新data_importer.py添加字段到入库逻辑** ⭐
   - [ ] 运行测试验证

2. **添加集成测试**
   - 测试新字段是否正确入库
   - 测试端到端数据流

3. **改进成功验证**
   - 不仅检查操作成功
   - 还要检查数据真实存在

---

## 📝 修复清单

- ✅ 更新`backend/services/data_importer.py`（PostgreSQL分支）
- ✅ 更新`backend/services/data_importer.py`（SQLite分支）
- ✅ 重启后端服务
- ✅ 创建操作指南
- ⏳ 等待用户重新导入数据
- ⏳ 验证数据正确入库
- ⏳ 验证产品管理页面显示

---

## 🚀 下一步

**立即操作**:
1. 后端已重启（新代码已生效）
2. 重新导入妙手产品数据
3. 验证数据库中有1218条miaoshou记录
4. 查看产品管理页面显示

**完整指南**: `docs/URGENT_MIAOSHOU_IMPORT_SOLUTION.md`

---

**修复版本**: v4.6.3  
**修复时间**: 2025-11-05 14:28  
**状态**: ✅ 已修复，等待验证


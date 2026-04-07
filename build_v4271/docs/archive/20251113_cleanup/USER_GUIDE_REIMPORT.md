# 双维护问题修复 - 用户操作指南

**日期**: 2025-11-05  
**版本**: v4.6.3  
**状态**: ✅ 代码已完全修复，等待重新导入数据  

---

## ✅ 修复完成确认

### 已完成的修复

1. **代码修复** ✅
   - `backend/services/data_importer.py` - 接收file_record参数
   - `backend/routers/field_mapping.py` - 传递file_record参数
   - `backend/routers/product_management.py` - API查询优化

2. **历史数据修复** ✅
   - 1条unknown数据已更新为miaoshou
   - 数据完整性验证通过

3. **API验证** ✅
   - 筛选功能完全正常
   - miaoshou平台查询返回1条数据
   - shopee平台查询返回4条数据

---

## 🎯 当前状态

### 数据库状态

```
Platform分布：
  - miaoshou: 1条  ✅（修复后，原来是0条）
  - shopee: 4条
  - unknown: 3条（其他测试数据）

Miaoshou产品详情：
  - SKU: unknown（需要重新导入完整数据）
  - Product Name: 【Sg】50L容量男士军用大背包...
  - Total Stock: 84
  - Available Stock: 73  ✅
  - Price: 46.5 USD
  - Warehouse: 新加坡+部分菲律宾  ✅
```

### 前端页面状态

- URL: `http://localhost:5173/#/product-management`
- 平台选择器: 已选择"妙手"
- 产品列表: 显示"共6个"（未正确筛选）
- 第一条产品: 【Sg】50L容量...，库存73，价格46.50 USD

---

## 🚀 下一步操作

### 为什么需要重新导入？

**原因**：
1. 当前只有1条历史数据（从unknown修复）
2. platform_sku为"unknown"（缺少完整SKU信息）
3. 您原本导入了1218条数据，但这些数据因为双维护问题没有正确入库

**现在代码已修复，可以正确导入完整数据了！**

### 重新导入步骤（详细）

#### Step 1: 访问字段映射界面
```
URL: http://localhost:5173/#/field-mapping
```

#### Step 2: 上传文件并设置元数据

| 配置项 | 必须选择 | 说明 |
|--------|---------|------|
| **平台** | `miaoshou` | ⭐⭐⭐ 非常重要！ |
| 数据域 | `products` | 产品数据域 |
| 粒度 | `snapshot` | 快照数据 |
| 表头行 | `1` | 第一行是表头 |

**检查点**: 确认平台显示为"miaoshou"（不是空白，不是其他值）

#### Step 3: 生成智能映射

1. **不要选择任何旧模板**
2. 点击"生成智能映射"按钮
3. 等待映射完成

#### Step 4: 验证映射（重要！）

**必须检查的关键映射**:

| Excel列名 | 必须映射到 | 说明 |
|-----------|----------|------|
| *商品SKU | `platform_sku` 或 `product_sku` | ⭐⭐⭐ 避免SKU为unknown |
| *商品名称 | `product_name` | 必填 |
| *单价（元） | `price` | 价格 |
| 可用库存 | `available_stock` | 可售库存 |
| 库存总量 | `total_stock` | 总库存 |
| 预占库存 | `reserved_stock` | 预占库存 |
| 在途库存 | `in_transit_stock` | 在途库存 |
| 仓库 | `warehouse` | 仓库位置 |
| 规格 | `product_specification` | 产品规格 |

**检查点**: 所有字段代码都是英文命名，没有拼音

#### Step 5: 确认映射并入库

1. 点击"确认映射并入库"按钮
2. 等待入库完成（应该显示"数据入库成功！已导入1218条记录"）

#### Step 6: 验证数据入库

立即运行验证脚本：
```bash
python temp/development/simple_check.py
```

**期望输出**:
```
Platform: miaoshou, Count: 1218  ✅（不是1条）
```

**如果还是1条，说明导入失败，请查看后端日志错误！**

#### Step 7: 刷新产品管理页面

1. 访问: `http://localhost:5173/#/product-management`
2. 选择平台："妙手"
3. 点击"查询"按钮
4. 应该看到1218个产品（不是1个）

---

## 🔍 如果导入失败

### 检查点1: platform设置

在上传文件后，元数据设置界面，确认：
```
平台: miaoshou  ✅（不是"妙手"，不是空白，不是unknown）
```

### 检查点2: SKU映射

在映射界面，确认：
```
*商品SKU → platform_sku  ✅（不是未映射）
```

**如果SKU未映射，所有数据的SKU都会是"unknown"！**

### 检查点3: 后端日志

查看运行uvicorn的PowerShell窗口，寻找：
- `[ERROR]` 错误信息
- `IntegrityError` 数据库错误
- `ValidationError` 验证错误

---

## 📝 验证脚本

### 快速检查数据
```bash
python temp/development/simple_check.py
```

### API功能测试
```bash
python temp/development/test_api_filter.py
```

### 双维护检查
```bash
python temp/development/check_double_maintenance.py
```

---

## ✅ 成功标志

### 数据库检查
```
Platform: miaoshou, Count: 1218  ✅
```

### 前端页面
```
产品管理 → 选择"妙手" → 点击"查询" → 显示"共1218个"  ✅
```

### 产品详情
- SKU: 实际SKU值（不是"unknown"）
- 库存: 实际库存值（来自available_stock）
- 价格: 实际价格值
- 仓库: 实际仓库信息

---

**修复已完成！现在请重新导入数据，验证1218条记录是否都能正确入库和显示！** 🚀


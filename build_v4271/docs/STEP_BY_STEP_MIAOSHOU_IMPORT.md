# 妙手产品数据导入 - 逐步操作指南（附截图检查点）

**状态**: ✅ 系统已完全修复  
**版本**: v4.6.3  
**日期**: 2025-11-05  

---

## ⚠️ 当前问题

虽然显示"数据入库成功1218条"，但数据库中没有数据！

**诊断结果**:
```
Miaoshou records: 0  ❌
```

**可能原因**:
1. Platform代码没有正确设置为"miaoshou"
2. 数据验证失败但没有显示错误
3. 某些必填字段缺失

---

## 📋 逐步操作指南

### Step 1: 上传文件

1. 访问: `http://localhost:5173/field-mapping`
2. 点击"上传文件"或"选择文件"按钮
3. 选择妙手产品Excel文件
4. 等待上传完成

**⭐ 检查点**: 文件上传成功，显示文件名

### Step 2: 设置文件元数据（非常重要！）

**这一步最关键！必须正确设置！**

在文件元数据配置界面：

| 配置项 | 必须选择 | 说明 |
|--------|---------|------|
| **平台** | `miaoshou` | ⭐⭐⭐ 必须准确拼写为"miaoshou"！ |
| **数据域** | `products` | 产品数据域 |
| **数据粒度** | `snapshot` | 快照数据 |
| **表头行** | `1` | 第一行是表头 |

**⭐ 检查点**: 确认平台显示为"miaoshou"（不是"妙手"、不是"unknown"）

### Step 3: 预览数据

- 查看数据预览表（前100行）
- 确认数据正确加载
- 确认列名正确识别

**⭐ 检查点**: 预览表显示正确的数据

### Step 4: 生成智能映射

1. **不要选择任何旧模板**
2. 点击"生成智能映射"按钮
3. 等待映射完成

**⭐ 检查点**: 系统显示"映射完成"或类似提示

### Step 5: 验证映射结果（重要！）

**必须检查以下关键映射**:

| Excel列名 | 必须映射到 | 错误示例（不要选择）|
|-----------|----------|------------------|
| *商品名称 | `product_name` | - |
| *规格 | `product_specification` | ❌ c68_c84_1 |
| *单价（元） | `price` | - |
| 仓库 | `warehouse` | ❌ cang_ku |
| 库存总量 | `total_stock` | ❌ stock_zong_liang |
| 可用库存 | `available_stock` | ❌ stock_ke_yong |
| 预占库存 | `reserved_stock` | ❌ stock_yu_zhan, ❌ _stock |
| 在途库存 | `in_transit_stock` | ❌ stock_zai_tu |
| 创建时间 | `created_at` | ❌ order_time_utc_chuang_jian |
| 更新时间 | `updated_at` | ❌ order_time_utc_geng_xin |
| 近7天销量 | `sales_volume_7d` | ❌ jin_7_tian_xiao_liang_shu_ju |
| 近30天销量 | `sales_volume_30d` | ❌ jin_30_tian_xiao_liang_shu_ju |
| 近60天销量 | `sales_volume_60d` | ❌ jin_60_tian_xiao_liang_shu_ju |
| 近90天销量 | `sales_volume_90d` | ❌ jin_90_tian_xiao_liang_shu_ju |

**⭐ 关键检查点**:
- [ ] 所有字段代码都是英文命名
- [ ] 没有拼音命名（如cang_ku, jin_7_tian等）
- [ ] 没有不规范代码（如c68_c84_1, _stock等）
- [ ] "预占库存"映射到`reserved_stock`（不是`_stock`或`stock`）

**如果看到拼音或不规范字段名，说明映射有问题，请手动修改！**

### Step 6: 手动修正错误映射（如果有）

如果发现错误映射（如预占库存→_stock）：

1. 点击该字段的"标准字段"下拉框
2. 搜索正确的字段（如：reserved）
3. 选择`reserved_stock`
4. 确认更新

### Step 7: 确认映射并入库

1. **再次检查所有映射都正确**
2. 点击"确认映射并入库"按钮
3. 等待入库完成
4. **查看后端日志窗口**（运行uvicorn的PowerShell窗口）
   - 看是否有`[ERROR]`错误
   - 看是否有`[upsert_product_metrics]`成功日志

**⭐ 检查点**: 后端日志没有ERROR，显示成功信息

### Step 8: 验证数据真的入库了

立即运行验证脚本：
```bash
python temp/development/simple_check.py
```

**期望输出**:
```
Platform: miaoshou, Count: 1218 ✅
```

**如果还是0条，说明入库失败！请查看后端日志找出错误原因！**

### Step 9: 刷新产品管理页面

1. 访问: `http://localhost:5173/product-management`
2. 点击"刷新"按钮
3. 或按F5刷新浏览器

**期望看到**: 1218个妙手产品

---

## 🚨 常见问题排查

### Q1: 为什么显示"成功"但数据库没有数据？

**可能原因**:

1. **Platform代码错误**
   - 检查是否设置为"miaoshou"（不是"妙手"、不是空白）
   
2. **必填字段缺失**
   - `platform_sku`必须存在
   - `product_name`必须存在
   - `metric_date`会自动生成（snapshot数据）

3. **字段映射错误**
   - 检查是否有错误的字段名（如`_stock`）
   - 检查是否还有拼音命名

4. **数据验证失败**
   - 查看后端日志是否有验证错误
   - 检查"数据隔离区"是否有记录

### Q2: 如何查看后端日志？

1. 找到运行uvicorn的PowerShell窗口
2. 滚动查看最近的日志
3. 寻找`[ERROR]`或`[WARNING]`
4. 寻找`[upsert_product_metrics]`相关日志

### Q3: 如何检查数据是否进入隔离区？

1. 在前端界面导航到"数据隔离区"
2. 查看是否有products域的隔离记录
3. 查看错误原因

### Q4: "预占库存"为什么映射到`_stock`？

这是一个错误的映射！应该映射到`reserved_stock`。

**修正方法**:
1. 在映射界面找到"预占库存"
2. 点击下拉框
3. 搜索"reserved"
4. 选择`reserved_stock`

---

## 🔧 调试工具

### 快速检查数据

```bash
# 检查是否有miaoshou数据
python temp/development/simple_check.py
```

### 检查映射唯一性

```bash
cd temp/development/20251105_field_mapping_scripts
python check_duplicate_mappings.py
```

### 查看字段映射字典

```sql
SELECT field_code, cn_name, data_domain
FROM field_mapping_dictionary
WHERE data_domain = 'products'
    AND (cn_name LIKE '%库存%' OR cn_name LIKE '%销量%' OR cn_name LIKE '%仓库%')
ORDER BY field_code;
```

---

## ⭐ 最关键的检查

### 在上传文件后，元数据设置界面：

**必须看到以下内容**:
```
平台: miaoshou  ✅（不是"妙手"，不是空白）
数据域: products
粒度: snapshot
```

**如果平台不是"miaoshou"，数据入库后会被标记为其他平台，导致在miaoshou筛选下查不到！**

---

## 📞 需要帮助？

如果按照以上步骤操作后，数据还是没有入库：

1. **查看后端日志**
   - 复制最近的ERROR日志
   - 告诉我具体的错误信息

2. **检查字段映射**
   - 截图映射配置界面
   - 确认所有映射都是英文字段

3. **检查数据隔离区**
   - 看是否有隔离记录
   - 查看错误原因

---

**现在请按照Step 1-9重新操作一次，特别注意Step 2的平台设置！** 🚀


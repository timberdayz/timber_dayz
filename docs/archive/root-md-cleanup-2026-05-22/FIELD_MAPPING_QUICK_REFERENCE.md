# 妙手ERP产品数据映射 - 快速参考卡片

**版本**: v4.6.3 | **日期**: 2025-11-05 | **状态**: ✅ 完全就绪

---

## 📋 14个标准字段映射表

| Excel列名 | 映射到 | 类型 | 示例数据 |
|-----------|-------|------|---------|
| *商品名称 | `product_name` | string | 可充电LED台灯 |
| *规格 | `product_specification` | string | silver S 35cmX5cm |
| *单价（元） | `price` | float | 18.5 |
| 仓库 | `warehouse` | string | 新加坡+部分菲律宾 |
| 库存总量 | `total_stock` | integer | 100 |
| 可用库存 | `available_stock` | integer | 80 |
| 预占库存 | `reserved_stock` | integer | 10 |
| 在途库存 | `in_transit_stock` | integer | 50 |
| 创建时间 | `created_at` | datetime | 2025-09-26 15:24:33 |
| 更新时间 | `updated_at` | datetime | 2025-09-26 15:24:48 |
| 近7天销量数据 | `sales_volume_7d` | integer | 15 |
| 近30天销量数据 | `sales_volume_30d` | integer | 45 |
| 近60天销量数据 | `sales_volume_60d` | integer | 120 |
| 近90天销量数据 | `sales_volume_90d` | integer | 200 |

---

## ✅ 检查清单

导入时请确认：

- [ ] 平台选择为 `miaoshou`
- [ ] 数据域选择为 `products`
- [ ] 数据粒度选择为 `snapshot`
- [ ] 表头行设置正确（通常是1）
- [ ] 每个字段只有**1个**映射选项（无重复）
- [ ] 所有字段代码都是英文（不是拼音）
- [ ] 映射率达到90%+（14个字段中至少12个）

---

## 🚫 不需要映射

- 总价（元）
- 活动预留库存
- 计划库存
- 安全库存
- 创建人员
- 更新人员
- 仓位1

---

## 📚 详细文档

- **完整导入指南**: `docs/FINAL_USER_GUIDE_MIAOSHOU.md` ⭐⭐⭐
- **完整修复报告**: `docs/COMPLETE_FIELD_MAPPING_FIX_REPORT.md`
- **快速操作指南**: `docs/HOW_TO_IMPORT_MIAOSHOU_PRODUCTS.md`

---

**打印本页作为快速参考！** 📄


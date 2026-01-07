# C类数据核心字段定义文档

**版本**: v1.0.0  
**创建日期**: 2025-01-31  
**用途**: C类数据核心字段优化计划

---

## 一、概述

本文档定义C类数据计算所需的17个核心字段，包括达成率计算、健康度评分、排名计算和预警系统所需的字段。

### 1.1 C类数据定义

**C类数据**: 系统计算的衍生数据，包括：
- 达成率（销售战役达成率、目标达成率）
- 健康度评分（店铺健康度评分）
- 排名（销量排名、销售额排名、流量排名、转化排名）
- 预警（转化率预警、库存预警、客户满意度预警）

### 1.2 数据来源

C类数据由A类数据（用户配置）和B类数据（业务数据）计算得出：
- **A类数据**: 销售战役目标、店铺目标等用户配置
- **B类数据**: 订单数据、产品数据、库存数据等业务数据
- **C类数据**: 基于A类和B类数据计算得出的衍生指标

---

## 二、核心字段定义（17个字段）

### 2.1 达成率计算核心字段（6个）

用于计算销售战役达成率和目标达成率。

| 字段代码 | 中文名称 | 数据域 | 数据类型 | 用途 | 必填 |
|---------|---------|--------|---------|------|------|
| `order_id` | 订单号 | orders | string | 统计订单数 | ✅ |
| `order_date_local` | 订单日期 | orders | date | 时间筛选 | ✅ |
| `total_amount_rmb` | 订单总金额（CNY） | orders | currency | 销售额计算 | ✅ |
| `order_status` | 订单状态 | orders | string | 筛选有效订单 | ✅ |
| `platform_code` | 平台代码 | general | string | 维度聚合 | ✅ |
| `shop_id` | 店铺ID | general | string | 维度聚合 | ✅ |

**计算公式**:
```
达成率 = (实际GMV / 目标GMV) * 100
实际GMV = SUM(total_amount_rmb) WHERE order_status IN ('completed', 'paid')
```

---

### 2.2 健康度评分核心字段（8个）

用于计算店铺健康度评分（0-100分）。

| 字段代码 | 中文名称 | 数据域 | 数据类型 | 用途 | 权重 |
|---------|---------|--------|---------|------|------|
| `total_amount_rmb` | 订单总金额（CNY） | orders | currency | GMV计算 | 30分 |
| `unique_visitors` | 独立访客数 | products | integer | 转化率计算分母 | 25分 |
| `order_count` | 订单数 | products | integer | 转化率计算分子 | 25分 |
| `available_stock` | 可用库存 | inventory | integer | 库存周转率计算 | 25分 |
| `sales_volume_30d` | 近30天销量 | products | integer | 库存周转率计算 | 25分 |
| `rating` | 评分 | products | float | 客户满意度 | 20分 |
| `metric_date` | 指标日期 | products | date | 时间维度聚合 | - |
| `data_domain` | 数据域 | general | string | 区分products/inventory域 | - |

**计算公式**:
```
健康度评分 = GMV得分 + 转化得分 + 库存得分 + 服务得分

GMV得分（0-30分）:
  = 基于GMV排名和增长率计算

转化得分（0-25分）:
  = 基于转化率排名计算
  转化率 = (order_count / unique_visitors) * 100

库存得分（0-25分）:
  = 基于库存周转率计算
  库存周转率 = (sales_volume_30d / available_stock) * (365 / 30)

服务得分（0-20分）:
  = 基于客户满意度（rating）计算
```

---

### 2.3 排名计算核心字段（4个）

用于计算销量排名、销售额排名、流量排名、转化排名。

| 字段代码 | 中文名称 | 数据域 | 数据类型 | 用途 |
|---------|---------|--------|---------|------|
| `sales_volume` | 销量 | products | integer | 销量排名 |
| `sales_amount_rmb` | 销售额（CNY） | products | currency | 销售额排名 |
| `unique_visitors` | 独立访客数 | products | integer | 流量排名 |
| `conversion_rate` | 转化率 | products | float | 转化排名 |

**排名计算**:
```
销量排名 = RANK() OVER (ORDER BY sales_volume DESC)
销售额排名 = RANK() OVER (ORDER BY sales_amount_rmb DESC)
流量排名 = RANK() OVER (ORDER BY unique_visitors DESC)
转化排名 = RANK() OVER (ORDER BY conversion_rate DESC)
```

---

### 2.4 预警系统核心字段（3个）

用于触发转化率预警、库存预警、客户满意度预警。

| 字段代码 | 中文名称 | 数据域 | 数据类型 | 预警阈值 |
|---------|---------|--------|---------|---------|
| `conversion_rate` | 转化率 | products | float | < 2% |
| `available_stock` | 可用库存 | inventory | integer | = 0 |
| `rating` | 评分 | products | float | < 3.0 |

**预警规则**:
```
转化率预警: conversion_rate < 2%
库存预警: available_stock = 0
客户满意度预警: rating < 3.0
```

---

## 三、字段映射要求

### 3.1 运营数据字段映射（Shopee、TikTok）

**货币策略**: 无货币

**必须映射的字段**:
- `unique_visitors` - 独立访客数
- `order_count` - 订单数
- `rating` - 评分
- `sales_volume` - 销量
- `conversion_rate` - 转化率（可计算）
- `available_stock` - 可用库存
- `sales_volume_30d` - 近30天销量

**禁止映射的字段**:
- ❌ `sales_amount_sgd` - 销售额（SGD）
- ❌ `sales_amount_myr` - 销售额（MYR）
- ❌ 任何货币字段

---

### 3.2 经营数据字段映射（妙手ERP）

**货币策略**: CNY本位币

**必须映射的字段**:
- `order_id` - 订单号
- `order_date_local` - 订单日期
- `total_amount_rmb` - 订单总金额（CNY）
- `order_status` - 订单状态
- `sales_amount_rmb` - 销售额（CNY）

**货币要求**:
- ✅ 所有金额字段必须为CNY
- ✅ 字段名必须包含`_rmb`或`_cny`后缀
- ❌ 禁止多币种混用

---

## 四、数据质量要求

### 4.1 字段完整性要求

**达成率计算**:
- ✅ 订单数据必须包含所有6个核心字段
- ✅ `total_amount_rmb`不能为NULL或0

**健康度评分**:
- ✅ 产品数据必须包含`unique_visitors`、`order_count`、`rating`
- ✅ 库存数据必须包含`available_stock`、`sales_volume_30d`
- ✅ `unique_visitors`不能为0（影响转化率计算）

**排名计算**:
- ✅ 产品数据必须包含`sales_volume`、`sales_amount_rmb`、`unique_visitors`、`conversion_rate`

**预警系统**:
- ✅ 产品数据必须包含`conversion_rate`、`rating`
- ✅ 库存数据必须包含`available_stock`

---

### 4.2 数据质量评分

**评分标准**:
```
数据质量评分 = (已存在字段数 / 总字段数) * 100

总字段数 = 17个核心字段
已存在字段数 = 在field_mapping_dictionary表中存在的字段数
```

**质量等级**:
- **优秀** (90-100分): 所有核心字段完整，C类数据计算就绪
- **良好** (70-89分): 大部分核心字段完整，部分C类数据可计算
- **一般** (50-69分): 核心字段缺失较多，C类数据计算受限
- **较差** (<50分): 核心字段严重缺失，C类数据无法计算

---

## 五、验证和检查

### 5.1 字段存在性验证

**验证脚本**: `scripts/verify_c_class_core_fields.py`

**验证内容**:
1. 检查17个核心字段在`field_mapping_dictionary`表中的存在性
2. 检查字段的数据域匹配性
3. 验证字段映射模板覆盖率
4. 生成验证报告（JSON格式）

**验证结果**:
```json
{
    "verification": {
        "summary": {
            "total_found": 15,
            "total_missing": 2,
            "all_passed": false
        },
        "details": {
            "orders": {"found": [...], "missing": [...]},
            "products": {"found": [...], "missing": [...]},
            "inventory": {"found": [...], "missing": [...]}
        }
    }
}
```

---

### 5.2 数据完整性检查

**检查服务**: `backend/services/c_class_data_validator.py`

**检查内容**:
1. 检查B类数据是否包含C类计算所需的核心字段
2. 验证字段数据质量（非空、数据类型正确）
3. 生成数据质量报告

**检查结果**:
```json
{
    "orders_complete": true,
    "products_complete": false,
    "inventory_complete": true,
    "missing_fields": ["products.conversion_rate"],
    "data_quality_score": 94.1,
    "warnings": ["产品字段conversion_rate存在但值为NULL"]
}
```

---

## 六、字段补充流程

### 6.1 自动补充缺失字段

**补充脚本**: `scripts/add_c_class_missing_fields.py`

**流程**:
1. 运行验证脚本，识别缺失字段
2. 运行补充脚本，自动补充缺失字段到`field_mapping_dictionary`表
3. 重新验证，确认所有字段已补充

**补充字段定义**:
- 字段代码、中文名称、数据域、数据类型
- 同义词、平台特定同义词
- 示例值、显示顺序、匹配权重

---

### 6.2 字段映射模板配置

**模板文件**: `config/field_mapping_templates/c_class_core_fields.yaml`

**模板结构**:
- Shopee运营数据模板（无货币字段）
- TikTok运营数据模板（无货币字段）
- 妙手ERP经营数据模板（CNY本位币字段）

**使用流程**:
1. 上传Excel文件
2. 系统自动识别平台和数据域
3. 应用对应的字段映射模板
4. 验证字段映射完整性

---

## 七、常见问题

### 7.1 Q: 为什么运营数据不包含货币字段？

**A**: 
- Shopee、TikTok等平台的货币符号复杂（SGD、MYR、THB等）
- 避免货币转换的复杂性
- 货币数据统一从妙手ERP获取（CNY本位币）

---

### 7.2 Q: 如果Excel文件中包含货币字段怎么办？

**A**: 
- 运营数据：忽略货币字段，只映射数量指标
- 系统会自动检测并警告货币字段违规
- 货币数据统一从妙手ERP获取

---

### 7.3 Q: 如何确保所有核心字段都已映射？

**A**: 
1. 运行`scripts/verify_c_class_core_fields.py`验证字段存在性
2. 运行`scripts/add_c_class_missing_fields.py`补充缺失字段
3. 使用字段映射模板确保字段映射完整性
4. 运行数据质量检查API验证数据完整性

---

## 八、更新记录

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0.0 | 2025-01-31 | 初始版本，定义17个核心字段 |

---

## 九、相关文档

- [货币策略文档](CURRENCY_POLICY.md)
- [数据质量保障指南](DATA_QUALITY_GUIDE.md)
- [字段映射用户指南](USER_GUIDE_FIELD_MAPPING.md)


# v4.6.0 用户操作指南

**版本**: v4.6.0  
**发布时间**: 2025-01-31  
**适用人群**: 数据分析师、运营人员、系统管理员

---

## 🎯 **v4.6.0核心新功能**

v4.6.0引入了三个重大改进：

1. **Pattern-based Mapping** - 一个规则处理无限货币组合
2. **全球货币支持** - 180+货币自动识别和转换
3. **数据隔离区** - 完整的数据质量管理

---

## 📚 **功能1：多货币字段自动入库**

### **使用场景**

您的Excel文件包含多个货币的销售额或退款字段：

| 订单号 | 销售额 (已付款订单) (BRL) | 销售额 (已下订单) (SGD) | 退款金额 (RM) |
|--------|---------------------------|------------------------|--------------|
| ORD001 | 100.00 | 80.00 | 10.00 |

**v4.5.1问题**：需要手动配置每个货币字段（重复劳动）  
**v4.6.0解决**：系统自动识别所有货币变体，一键入库

---

### **操作步骤**

#### **步骤1：上传文件**

1. 访问"字段映射"界面
2. 选择平台（如Shopee）
3. 上传Excel文件

#### **步骤2：系统自动识别**

系统会自动识别pattern-based字段，显示：

```
智能字段映射 (16/16)    匹配率 100%

原始字段                     标准字段              匹配方式
-------------------------------------------------------------------
销售额 (已付款订单) (BRL)    销售额（已付款订单）🎯  模式匹配
销售额 (已下订单) (SGD)      销售额（已下订单）🎯    模式匹配
退款金额 (RM)               退款金额 🎯           模式匹配

💡 提示：系统已自动识别3个多货币字段
   - 货币：BRL, SGD, MYR（RM）
   - 将自动转换为CNY并保存
```

#### **步骤3：确认并入库**

1. 检查映射是否正确
2. 点击"确认映射并入库"
3. 等待入库完成

#### **步骤4：查看结果**

成功提示：
```
入库完成，成功导入1条记录，同时导入3条金额维度记录（v4.6.0多货币支持）
```

**说明**：
- **1条记录**：FactOrder主表（订单基础信息）
- **3条金额维度记录**：FactOrderAmount维度表（每个货币字段1条）

---

### **数据库存储**

查询fact_order_amounts表：

```sql
SELECT * FROM fact_order_amounts WHERE order_id = 'ORD001';
```

结果：

| order_id | metric_type | metric_subtype | currency | amount_original | amount_cny |
|----------|-------------|----------------|----------|----------------|------------|
| ORD001 | sales_amount | paid | BRL | 100.00 | 120.00 |
| ORD001 | sales_amount | placed | SGD | 80.00 | 416.00 |
| ORD001 | refund_amount | standard | MYR | 10.00 | 16.00 |

**关键字段说明**：
- `metric_type`：销售额（sales_amount）或退款（refund_amount）
- `metric_subtype`：订单状态（paid/placed/completed等）
- `currency`：货币代码（BRL/SGD/MYR等）
- `amount_original`：原币金额（100.00 BRL）
- `amount_cny`：CNY金额（120.00 CNY，自动转换）
- `exchange_rate`：汇率快照（1.2）

---

## 📚 **功能2：数据隔离区**

### **使用场景**

当数据入库时出现质量问题，记录会被隔离：

```
入库0条 → 提示"数据质量问题" → 点击"查看详情" → 跳转到数据隔离区
```

---

### **操作步骤**

#### **方式1：从字段映射跳转**

1. 在字段映射界面点击"入库"
2. 如果有数据被隔离，系统会提示
3. 点击"查看详情"按钮
4. 自动跳转到数据隔离区，并筛选对应文件

#### **方式2：直接访问**

访问：http://localhost:5173/#/data-quarantine

---

### **界面功能**

#### **统计卡片**

显示：
- 总隔离数据：100条
- 今日新增：5条
- 待处理：100条
- 已处理：0条

#### **筛选功能**

支持按以下条件筛选：
- 平台（Shopee/妙手ERP/TikTok/Amazon）
- 数据域（orders/products/traffic/services）
- 错误类型（validation_error/missing_required_field/format_error）

#### **数据列表**

显示字段：
- ID
- 文件名
- 平台
- 数据域
- 行号
- 错误类型
- 错误信息
- 隔离时间

#### **操作按钮**

- **查看详情**：查看原始数据、错误详情、验证错误
- **重新处理**：修正后重新入库
- **批量重新处理**：选择多条记录批量处理

---

### **查看详情对话框**

显示内容：
- **基本信息**：隔离ID、文件名、平台、数据域、行号、隔离时间
- **错误信息**：错误类型、错误描述
- **验证错误详情**：字段级错误详情（如"订单号为空"）
- **原始数据**：JSON格式显示原始数据

---

### **重新处理**

#### **单条重新处理**

1. 点击"重新处理"按钮
2. 确认对话框
3. 系统重新验证和入库

#### **批量重新处理**

1. 勾选多条记录
2. 点击"批量重新处理"
3. 确认对话框
4. 查看处理结果（成功X条，失败X条）

---

## 📚 **功能3：支持的订单状态和货币**

### **销售额状态**（5种）

| 中文字段示例 | metric_subtype | 业务含义 |
|-------------|----------------|---------|
| 销售额 (BRL) | completed | 已完成（用户已收货） |
| 销售额 (已付款订单) (BRL) | paid | 已付款（待发货） |
| 销售额 (已下订单) (BRL) | placed | 已下订单（未付款） |
| 销售额 (已取消订单) (BRL) | cancelled | 已取消订单 |
| 销售额 (待发货订单) (BRL) | pending_shipment | 待发货订单 |

---

### **退款类型**（4种）

| 中文字段示例 | metric_subtype | 业务含义 |
|-------------|----------------|---------|
| 退款金额 (RM) | standard | 标准退款 |
| 商家折扣退款金额 (RM) | merchant_discount | 商家折扣退款 |
| 退货/退款商品的Shopee币抵消 (RM) | shopee_coin_offset | Shopee币抵消 |
| 部分退款金额 (RM) | partial | 部分退款 |

---

### **支持的货币**（180+种）

#### **东南亚地区**（10种）

| 货币符号 | ISO代码 | 货币名称 | 汇率示例（对CNY） |
|---------|---------|---------|------------------|
| S$ | SGD | 新加坡元 | 5.20 |
| RM | MYR | 马来西亚令吉 | 1.60 |
| Rp | IDR | 印尼盾 | 0.00045 |
| ฿ | THB | 泰铢 | 0.21 |
| ₱ | PHP | 菲律宾比索 | 0.13 |
| ₫ | VND | 越南盾 | 0.00029 |

#### **南美地区**（7种）

| 货币符号 | ISO代码 | 货币名称 | 汇率示例（对CNY） |
|---------|---------|---------|------------------|
| R$ | BRL | 巴西雷亚尔 | 1.20 |
| COP$ | COP | 哥伦比亚比索 | 0.0018 |
| AR$ | ARS | 阿根廷比索 | 0.0073 |

#### **北美地区**（3种）

| 货币符号 | ISO代码 | 货币名称 | 汇率示例（对CNY） |
|---------|---------|---------|------------------|
| $ | USD | 美元 | 7.25 |
| C$ | CAD | 加拿大元 | 5.10 |
| MX$ | MXN | 墨西哥比索 | 0.42 |

#### **欧洲地区**（9种）

| 货币符号 | ISO代码 | 货币名称 | 汇率示例（对CNY） |
|---------|---------|---------|------------------|
| € | EUR | 欧元 | 7.90 |
| £ | GBP | 英镑 | 9.20 |
| CHF | CHF | 瑞士法郎 | 8.50 |

**更多货币**：支持全球180+种货币，详见[CurrencyNormalizer服务](../backend/services/currency_normalizer.py)

---

## 🔍 **常见问题FAQ**

### **Q1：系统如何识别多货币字段？**

**A**：系统使用Pattern-based Mapping技术：

1. 字段辞典中定义正则表达式：
   ```
   "销售额\\s*\\((?P<status>.+?)\\)\\s*\\((?P<currency>[A-Z$¥₹]{1,3})\\)"
   ```

2. 自动提取维度：
   ```
   "销售额 (已付款订单) (BRL)" → {status: "已付款订单", currency: "BRL"}
   ```

3. 映射到标准值：
   ```
   {status: "已付款订单"} → metric_subtype: "paid"
   {currency: "BRL"} → currency: "BRL"
   ```

---

### **Q2：货币汇率从哪里来？**

**A**：三级降级策略：

1. **本地缓存**（dim_exchange_rates表）
   - 优先使用本地缓存的汇率
   - 缓存有效期：24小时

2. **汇率API**（多源降级）
   - Open Exchange Rates（全球180+货币）
   - European Central Bank（欧元相关）
   - Bank of China（人民币相关）

3. **历史汇率回退**
   - 如果API失败，使用最近7天的历史汇率

4. **手动预配置**
   - 系统预配置了21种常用货币的初始汇率

---

### **Q3：如何查看CNY转换是否正确？**

**A**：查询fact_order_amounts表：

```sql
SELECT 
    order_id,
    metric_type,
    metric_subtype,
    currency,
    amount_original,
    amount_cny,
    exchange_rate,
    created_at
FROM fact_order_amounts
WHERE order_id = 'YOUR_ORDER_ID';
```

**验证点**：
- `amount_cny` = `amount_original` × `exchange_rate`
- 汇率是否合理（可参考市场汇率）

---

### **Q4：如果新增了一个订单状态（如"部分退款"），需要怎么做？**

**A**：零代码改动，仅需配置！

1. 访问字段辞典管理界面
2. 新增一个字段定义：
   ```json
   {
     "field_code": "sales_amount_partial_refund",
     "cn_name": "销售额（部分退款）",
     "is_pattern_based": true,
     "field_pattern": "销售额\\s*\\(部分退款\\)\\s*\\((?P<currency>[A-Z$¥]{1,3})\\)",
     "dimension_config": {"currency": {"type": "normalize"}},
     "target_table": "fact_order_amounts",
     "target_columns": {
       "metric_type": "sales_amount",
       "metric_subtype": "partial_refund",
       "currency": "{{currency}}",
       "amount_original": "{{value}}"
     }
   }
   ```

3. 保存即生效，无需重启系统！

---

### **Q5：系统支持哪些货币？**

**A**：支持全球180+种货币

**常用货币**：
- 东南亚：SGD, MYR, IDR, THB, PHP, VND
- 南美：BRL, COP, ARS, CLP
- 北美：USD, CAD, MXN
- 欧洲：EUR, GBP, CHF
- 亚太：CNY, HKD, JPY, KRW, INR, AUD

**货币符号自动识别**：
- S$ → SGD
- RM → MYR
- R$ → BRL
- $ → USD（默认）
- ¥ → CNY（默认）

**中文名称识别**：
- 人民币 → CNY
- 新加坡元 → SGD
- 马来西亚令吉 → MYR

---

### **Q6：数据隔离区中的数据如何处理？**

**A**：三种处理方式：

1. **查看详情**
   - 了解错误原因
   - 查看原始数据
   - 查看验证错误详情

2. **重新处理**
   - 如果数据已修正（如在Excel源文件中修正）
   - 重新上传文件并入库
   - 或直接点击"重新处理"尝试再次入库

3. **批量删除**
   - 如果数据确认无效
   - 可以批量删除隔离记录

---

### **Q7：为什么我的销售额是CNY，但系统说是"金额维度记录"？**

**A**：v4.6.0采用维度表设计：

**传统设计**：
```
fact_orders表：
- sales_amount_paid_cny: 100.00
- sales_amount_placed_cny: 80.00
- refund_amount_cny: 10.00
```

**v4.6.0设计**：
```
fact_order_amounts表（维度表）：
| metric_type | metric_subtype | currency | amount_cny |
|-------------|----------------|----------|------------|
| sales_amount | paid | CNY | 100.00 |
| sales_amount | placed | CNY | 80.00 |
| refund_amount | standard | CNY | 10.00 |
```

**优势**：
- ✅ 新增状态无需加字段
- ✅ 支持多货币
- ✅ 便于分析和聚合

---

### **Q8：如何查询某个订单的总销售额（所有货币）？**

**A**：使用SQL聚合查询：

```sql
-- 查询订单的总销售额（CNY）
SELECT 
    order_id,
    SUM(amount_cny) as total_sales_cny
FROM fact_order_amounts
WHERE order_id = 'ORD001' AND metric_type = 'sales_amount'
GROUP BY order_id;

-- 按货币分组统计
SELECT 
    order_id,
    currency,
    SUM(amount_original) as original_total,
    SUM(amount_cny) as cny_total
FROM fact_order_amounts
WHERE order_id = 'ORD001' AND metric_type = 'sales_amount'
GROUP BY order_id, currency;
```

---

### **Q9：如何查询某个货币的总销售额？**

**A**：按货币筛选：

```sql
-- 查询BRL货币的总销售额
SELECT 
    SUM(amount_original) as brl_total,
    SUM(amount_cny) as cny_total
FROM fact_order_amounts
WHERE currency = 'BRL' AND metric_type = 'sales_amount';

-- 按订单状态和货币统计
SELECT 
    metric_subtype as order_status,
    currency,
    SUM(amount_cny) as total_cny
FROM fact_order_amounts
WHERE metric_type = 'sales_amount'
GROUP BY metric_subtype, currency
ORDER BY total_cny DESC;
```

---

### **Q10：净销售额（销售额-退款）如何计算？**

**A**：使用CASE WHEN：

```sql
SELECT 
    currency,
    SUM(CASE WHEN metric_type = 'sales_amount' THEN amount_cny ELSE 0 END) as gross_sales,
    SUM(CASE WHEN metric_type = 'refund_amount' THEN amount_cny ELSE 0 END) as total_refund,
    SUM(CASE WHEN metric_type = 'sales_amount' THEN amount_cny ELSE 0 END) - 
    SUM(CASE WHEN metric_type = 'refund_amount' THEN amount_cny ELSE 0 END) as net_sales
FROM fact_order_amounts
GROUP BY currency
ORDER BY net_sales DESC;
```

---

## 🎯 **最佳实践**

### **1. 定期更新汇率**

**建议**：每日更新汇率缓存

```bash
# 执行汇率更新脚本（待实现）
python scripts/update_exchange_rates.py
```

### **2. 监控隔离区**

**建议**：定期检查数据隔离区

- 如果隔离数据激增，检查数据源质量
- 如果特定错误类型多，优化验证规则

### **3. 审计汇率转换**

**建议**：定期审计汇率转换是否准确

```sql
-- 检查异常汇率（如汇率>100或<0.0001）
SELECT * FROM fact_order_amounts
WHERE exchange_rate > 100 OR exchange_rate < 0.0001;
```

---

## 📞 **需要帮助？**

### **技术文档**

- [架构设计指南](V4_6_0_ARCHITECTURE_GUIDE.md) - 深入理解v4.6.0设计
- [API契约](../API_CONTRACT.md) - API接口文档
- [更新日志](../CHANGELOG.md) - v4.6.0详细变更

### **开发规范**

- [.cursorrules](../.cursorrules) - 开发规范（v4.6.0架构说明）
- [SSOT验证](../scripts/verify_architecture_ssot.py) - 架构合规验证

---

## 🎊 **v4.6.0核心优势总结**

1. ✅ **零配置扩展** - 新增状态、新货币即插即用
2. ✅ **全球货币支持** - 180+货币自动识别和转换
3. ✅ **CNY本位币** - 统一财务标准
4. ✅ **数据治理** - 完整的隔离区功能
5. ✅ **性能优化** - 120倍汇率转换性能提升设计
6. ✅ **审计追溯** - 完整的数据血缘和操作日志

---

**祝使用愉快！** 🚀




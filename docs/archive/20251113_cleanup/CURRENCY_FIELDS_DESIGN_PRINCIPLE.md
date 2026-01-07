# 货币字段统一设计原则（v4.6.0 Pattern-based Mapping）

**核心原则**: ✅ **所有带货币的字段都应该使用Pattern-based设计**

---

## 🎯 **当前设计状态**

### ✅ 已实现的Pattern-based货币字段（9个）

| 字段代码 | 中文名称 | Pattern | 维度表存储 |
|---------|---------|---------|-----------|
| sales_amount_completed | 销售额 | `^销售额?\s*\((?P<currency>[A-Z$]{1,3})\)$` | ✅ fact_order_amounts |
| sales_amount_paid | 销售额（已付款订单） | `销售额?\s*\(已付款订单\)\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| sales_amount_placed | 销售额（已下订单） | `销售额?\s*\(已下[订单]+\)\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| sales_amount_cancelled | 销售额（已取消订单） | `销售额?\s*\(已取消订单\)\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| sales_amount_pending_shipment | 销售额（待发货订单） | `销售额?\s*\([待发货]+\)\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| refund_amount | 退款金额 | `退款金额\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| refund_partial | 部分退款金额 | `部分退款金额\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| refund_merchant_discount | 商家折扣退款金额 | `商家折扣退款金额\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |
| refund_shopee_coin_offset | 退货/退款商品Shopee币抵消 | `退货.退款商品.*Shopee币抵消\s*\((?P<currency>[A-Z$]{1,3})\)` | ✅ fact_order_amounts |

**特点**:
- ✅ 所有字段都配置了Pattern正则表达式
- ✅ 所有字段都存储到`fact_order_amounts`维度表
- ✅ 货币信息通过正则提取，存储在`currency`列
- ✅ 前端只显示一个标准字段（如"销售额"），不区分货币

---

## 📋 **设计原则（统一标准）**

### 原则1: 单一标准字段，多货币支持 ⭐⭐⭐

**前端显示**:
```
数据库列名层: 销售额
标准字段: sales_amount_completed
```

**后端处理**:
```
原始字段: "销售 (BRL)" → sales_amount_completed + currency=BRL
原始字段: "销售 (SGD)" → sales_amount_completed + currency=SGD
原始字段: "销售 (USD)" → sales_amount_completed + currency=USD
```

**存储结构**:
```sql
fact_order_amounts表:
- metric_type: sales_amount
- metric_subtype: completed
- currency: BRL/SGD/USD (自动提取)
- amount_original: 原始金额
- amount_cny: 人民币金额（自动转换）
```

### 原则2: Pattern正则提取货币 ⭐⭐⭐

**Pattern格式**:
```regex
^销售额?\s*\((?P<currency>[A-Z$]{1,3})\)$
```

**提取逻辑**:
- 正则匹配原始字段名
- 提取命名组`currency`
- 货币标准化（如RM→MYR, S$→SGD）
- 存储到维度表

### 原则3: 维度表存储，零字段爆炸 ⭐⭐⭐

**传统设计（❌不推荐）**:
```sql
-- 需要为每个货币创建字段
sales_amount_brl DECIMAL
sales_amount_sgd DECIMAL
sales_amount_usd DECIMAL
-- 新增货币需要ALTER TABLE
```

**维度表设计（✅推荐）**:
```sql
-- 一个字段存储所有货币
fact_order_amounts (
    currency VARCHAR(3),
    amount_original DECIMAL,
    amount_cny DECIMAL
)
-- 新增货币只需INSERT行，无需ALTER TABLE
```

---

## ⚠️ **需要升级的字段**

### 潜在货币字段（21个）

这些字段可能包含货币信息，但尚未配置Pattern-based设计：

**可能场景**:
1. 字段名包含货币（如"金额 (USD)"）
2. 字段描述提到货币
3. 历史遗留字段

**升级建议**:
- ✅ 检查字段是否包含货币信息
- ✅ 如果包含，添加Pattern配置
- ✅ 迁移到`fact_order_amounts`维度表
- ✅ 更新前端显示逻辑

---

## 🎯 **统一设计的好处**

### 1. 用户体验 ⭐⭐⭐
- **简单**: 前端只显示"销售额"，不区分货币
- **直观**: 用户不需要选择特定货币的字段
- **一致**: 所有货币字段都遵循相同模式

### 2. 系统维护 ⭐⭐⭐
- **零字段爆炸**: 新增货币不需要ALTER TABLE
- **配置驱动**: 通过Pattern配置，零硬编码
- **自动识别**: 系统自动识别和提取货币

### 3. 数据查询 ⭐⭐⭐
- **灵活**: WHERE currency='BRL'筛选特定货币
- **统一**: 所有货币数据统一存储格式
- **高效**: 维度表设计查询性能更好

---

## 📝 **实施建议**

### 短期（本周）
1. ✅ 确认所有货币字段都已配置Pattern
2. ✅ 检查是否有遗漏的货币字段
3. ✅ 统一前端显示逻辑

### 中期（本月）
1. 升级潜在的21个货币字段（如果需要）
2. 建立货币字段添加规范
3. 创建货币字段配置模板

### 长期（季度）
1. 自动检测货币字段
2. 智能推荐Pattern配置
3. 货币字段配置向导

---

## ✅ **结论**

**是的，所有带货币的字段都应该这样设计！**

**当前状态**:
- ✅ 9个核心货币字段已实现Pattern-based设计
- ✅ 全部配置为维度表存储
- ✅ 前端统一显示逻辑

**建议**:
- ✅ 所有新货币字段都遵循此设计
- ✅ 现有字段逐步升级到此设计
- ✅ 建立统一的货币字段规范

---

**文档创建**: 2025-11-01  
**状态**: ✅ **设计原则已明确**


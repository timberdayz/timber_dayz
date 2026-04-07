# v4.4.0 财务域完整指南

**版本**: v4.4.0  
**发布日期**: 2025-01-29  
**架构**: 现代化ERP标准（CNY基准 + 移动加权平均）

---

## 📋 核心设计理念

### 1. 单一真源（Single Source of Truth）

| 域 | 唯一真源 | 说明 |
|----|---------|------|
| 字段辞典 | `FieldMappingDictionary` | 所有标准字段唯一定义，支持在线CRUD |
| 计算指标 | `DimMetricFormula` | 比率/派生指标公式唯一定义 |
| 库存流水 | `InventoryLedger` | Universal Journal模式，支持WAC/FIFO |
| 销售收入 | `FactOrderItem` → `mv_sales_day_shop_sku` | 订单明细+日聚合视图 |
| 运营费用 | `FactExpensesMonth` → `FactExpensesAllocated` | 月度费用+日分摊 |

### 2. 现代化ERP三大支柱

#### 支柱1：字段注册中心（可在线管理）
- 所有标准字段存储在`FieldMappingDictionary`
- 支持在线新增/编辑字段和同义词
- 版本化管理（SCD2）
- 计算指标（CTR、转化率等）不参与手工映射，由公式自动计算

#### 支柱2：库存流水账（Universal Journal）
- `InventoryLedger`作为唯一写入点
- 支持移动加权平均成本（WAC）
- 预留FIFO视图扩展
- 所有库存快照从流水派生

#### 支柱3：财务闭环（P&L + 对账）
- 收入：订单 → 总账
- 成本：采购 → 入库 → 移动加权 → COGS
- 费用：月度导入 → 分摊 → 运营成本
- 对账：三维度自动对账（收入/库存/费用）

---

## 🏗️ 数据库架构（25张新表）

### 维度表（6张）

```sql
-- 计算指标公式
dim_metric_formulas (id, metric_code, cn_name, sql_expr, depends_on, ...)

-- 货币
dim_currencies (currency_code, currency_name, symbol, is_base, ...)

-- 汇率（CNY基准）
fx_rates (rate_date, from_currency, to_currency, rate, source, version)

-- 会计期间
dim_fiscal_calendar (period_id, period_code, start_date, end_date, status, ...)

-- 供应商
dim_vendors (vendor_code, vendor_name, country, tax_id, payment_terms, ...)

-- 总账科目
gl_accounts (account_code, account_name, account_type, parent_account, ...)
```

### 采购管理（7张）

```sql
-- 采购订单头
po_headers (po_id, vendor_code, po_date, currency, total_amt, status, ...)

-- 采购订单行
po_lines (po_line_id, po_id, platform_sku, qty_ordered, unit_price, ...)

-- 入库单头
grn_headers (grn_id, po_id, receipt_date, warehouse, status, ...)

-- 入库单行
grn_lines (grn_line_id, grn_id, po_line_id, qty_received, unit_cost, ...)

-- 发票头
invoice_headers (invoice_id, vendor_code, invoice_no, total_amt, ocr_result, ...)

-- 发票行
invoice_lines (invoice_line_id, invoice_id, po_line_id, grn_line_id, ...)

-- 发票附件（扫描件）
invoice_attachments (attachment_id, invoice_id, file_path, ocr_text, ...)
```

### 成本与费用（5张）

```sql
-- 库存流水账（Universal Journal）
inventory_ledger (ledger_id, platform_sku, transaction_date, movement_type,
                  qty_in, qty_out, unit_cost_wac, avg_cost_after, ...)

-- 月度费用
fact_expenses_month (expense_id, period_month, expense_type, amount, ...)

-- 费用分摊结果
fact_expenses_allocated_day_shop_sku (allocation_id, expense_id, allocation_date,
                                       platform_code, shop_id, platform_sku, allocated_amt, ...)

-- 物流成本
logistics_costs (logistics_id, grn_id, order_id, cost_type, amount, ...)

-- 分摊规则
allocation_rules (rule_id, scope, driver, weights, effective_from/to, ...)
```

### 财务与税务（7张）

```sql
-- 三单匹配日志
three_way_match_log (match_id, po_line_id, grn_line_id, invoice_line_id,
                      match_status, variance_qty, variance_amt, ...)

-- 税务凭证
tax_vouchers (voucher_id, period_month, voucher_type, tax_amt, deductible_amt, ...)

-- 报税清单
tax_reports (report_id, period_month, report_type, status, export_file_path, ...)

-- 总账凭证头
journal_entries (entry_id, entry_no, entry_date, period_month, entry_type, ...)

-- 总账凭证行（双分录）
journal_entry_lines (line_id, entry_id, account_code, debit_amt, credit_amt,
                      link_order_id, link_expense_id, ...)

-- 期初余额
opening_balances (balance_id, period, platform_sku, opening_qty, opening_cost, ...)

-- 审批日志
approval_logs (log_id, entity_type, entity_id, approver, status, comment, ...)

-- 退货单
return_orders (return_id, original_order_id, return_type, qty, refund_amt, ...)
```

---

## 🚀 快速开始

### 步骤1：部署数据库

```bash
# 方式A：自动部署（推荐）
python scripts/deploy_v4_4_0_finance.py

# 方式B：手动步骤
cd migrations
alembic upgrade head

# 初始化种子数据
python scripts/init_field_mapping_dictionary.py
python scripts/seed_services_dictionary.py
python scripts/seed_traffic_dictionary.py
python scripts/seed_finance_dictionary.py

# 创建物化视图
psql -U postgres -d xihong_erp -f sql/create_finance_materialized_views.sql
```

### 步骤2：验证部署

```bash
# 检查表是否创建
python scripts/deploy_v4_4_0_finance.py

# 预期输出：
# [OK] dim_metric_formulas
# [OK] dim_currencies
# [OK] fx_rates
# ... (共27张表)
# [OK] 部署验证通过
```

### 步骤3：启动系统

```bash
# 启动前后端
python run.py

# 访问API文档
http://localhost:8001/docs

# 访问前端
http://localhost:5173/#/financial-management
```

---

## 💼 核心业务流程

### 流程1：月度费用导入与分摊

```
1. 准备费用Excel（使用标准模板）
   期间    费用类型    金额       货币    税率
   2025-01 租金       12316.0    CNY    0.09
   2025-01 工资       14437.6    CNY    0
   ...

2. 前端上传
   财务管理 → 费用导入 → 选择文件 → 上传并导入
   
3. 系统处理
   - 解析Excel
   - 字段映射（租金 → expense_rent）
   - DQ校验
   - 写入fact_expenses_month
   
4. 执行分摊
   财务管理 → 费用分摊 → 选择期间 → 执行分摊
   
5. 查看P&L
   财务管理 → P&L月报 → 选择期间 → 查询
   
   输出：
   平台    店铺      收入      成本      毛利    运营费用  贡献利润  毛利率
   shopee  sg_3c    250940   220000   30940    10000    20940    12.3%
```

### 流程2：采购订单 → 入库 → 发票匹配

```
1. 创建采购订单
   POST /api/procurement/po/create
   {
     "vendor_code": "V001",
     "po_date": "2025-01-29",
     "lines": [
       {
         "platform_sku": "SKU001",
         "qty_ordered": 100,
         "unit_price": 5000.0
       }
     ]
   }
   
2. 审批（自动/人工）
   POST /api/procurement/po/{po_id}/submit-approval
   - 金额<5000 → 自动通过
   - 金额>=5000 → 待审批
   
3. 创建入库单
   POST /api/procurement/grn/create
   {
     "po_id": "PO202501290001",
     "lines": [
       {
         "po_line_id": 1,
         "qty_received": 98,
         "unit_cost": 5000.0
       }
     ]
   }
   
4. 过账到库存流水
   POST /api/procurement/grn/{grn_id}/post-to-ledger
   - 计算移动加权平均成本
   - 写入inventory_ledger
   
5. 上传发票
   POST /api/procurement/invoices/upload
   - 上传PDF/JPG
   - OCR识别
   
6. 三单匹配
   POST /api/procurement/invoices/{invoice_id}/match
   - PO vs GRN vs Invoice
   - 差异报告
```

### 流程3：库存成本追踪

```
inventory_ledger示例：

ledger_id | sku    | date       | type    | qty_in | qty_out | unit_cost | avg_cost_after
1         | SKU001 | 2025-01-10 | receipt | 100    | 0       | 50.00     | 50.00
2         | SKU001 | 2025-01-15 | sale    | 0      | 30      | 50.00     | 50.00
3         | SKU001 | 2025-01-20 | receipt | 50     | 0       | 52.00     | 50.67
4         | SKU001 | 2025-01-25 | sale    | 0      | 40      | 50.67     | 50.67

移动加权平均计算：
- 第3行入库后：avg_cost = (70*50 + 50*52) / 120 = 50.67
```

---

## 📊 物化视图说明

### 1. mv_sales_day_shop_sku（日销售聚合）

```sql
-- 用途：TopN分析、P&L计算
SELECT 
    platform_code, shop_id, platform_sku, sale_date,
    order_count, units_sold, sales_amount_cny
FROM mv_sales_day_shop_sku
WHERE sale_date >= '2025-01-01'
ORDER BY sales_amount_cny DESC
LIMIT 10;

-- 刷新策略：每小时刷新
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_day_shop_sku;
```

### 2. mv_inventory_snapshot_day（日库存快照）

```sql
-- 用途：库存分析、龄分布
SELECT 
    platform_sku, snapshot_date, qty_onhand, 
    current_cost, onhand_value_cny, age_bucket
FROM mv_inventory_snapshot_day
WHERE age_bucket = '60-90'
ORDER BY onhand_value_cny DESC;

-- 派生自：inventory_ledger累计
```

### 3. mv_pnl_shop_month（店铺月度P&L）

```sql
-- 用途：财务报表、利润分析
SELECT 
    platform_code, shop_id, period_month,
    revenue, cogs, gross_profit,
    operating_expenses, contribution_profit, gross_margin_pct
FROM mv_pnl_shop_month
WHERE period_month = '2025-01'
ORDER BY contribution_profit DESC;

-- 计算逻辑：
-- revenue = SUM(mv_sales_day_shop_sku.sales_amount_cny)
-- cogs = SUM(inventory_ledger.base_ext_value WHERE movement_type='sale')
-- operating_expenses = SUM(fact_expenses_allocated)
```

### 4. mv_vendor_performance（供应商表现）

```sql
-- 用途：供应商考核
SELECT 
    vendor_code, vendor_name,
    total_po_count, total_po_value_cny,
    ontime_delivery_rate, match_rate
FROM mv_vendor_performance
ORDER BY ontime_delivery_rate DESC;
```

### 5. mv_tax_report_summary（税务报表汇总）

```sql
-- 用途：报税准备
SELECT 
    period_month, voucher_type,
    voucher_count, total_tax_amt, total_deductible_amt
FROM mv_tax_report_summary
WHERE period_month = '2025-01';
```

---

## 🔌 API接口清单

### 字段辞典管理

```bash
# 获取字段辞典
GET /api/field-mapping/dictionary?data_domain=finance

# 创建标准字段
POST /api/field-mapping/dictionary/fields
{
  "field_code": "expense_custom_1",
  "cn_name": "自定义费用1",
  "data_domain": "finance",
  "synonyms": ["费用A", "custom1"]
}

# 更新字段
PUT /api/field-mapping/dictionary/fields/{field_code}
{
  "synonyms": ["新同义词1", "新同义词2"]
}

# 获取计算指标
GET /api/field-mapping/metrics/formulas?data_domain=traffic
```

### 采购管理

```bash
# 创建供应商
POST /api/procurement/vendors/create
{
  "vendor_code": "V001",
  "vendor_name": "供应商A",
  "tax_id": "91110000XXXX"
}

# 创建采购订单
POST /api/procurement/po/create
{
  "vendor_code": "V001",
  "lines": [{"platform_sku": "SKU001", "qty": 100, "price": 50}]
}

# 提交审批
POST /api/procurement/po/{po_id}/submit-approval

# 创建入库单
POST /api/procurement/grn/create

# 过账到库存流水
POST /api/procurement/grn/{grn_id}/post-to-ledger

# 上传发票
POST /api/procurement/invoices/upload

# 三单匹配
POST /api/procurement/invoices/{invoice_id}/match
```

### 财务管理

```bash
# 上传费用
POST /api/finance/expenses/upload
{
  "period_month": "2025-01",
  "expenses": [
    {
      "expense_type_raw": "租金",
      "amount": 12316.0,
      "currency": "CNY"
    }
  ]
}

# 执行分摊
POST /api/finance/expenses/allocate
{
  "period_month": "2025-01",
  "driver": "revenue_share"
}

# 查询P&L
GET /api/finance/pnl/shop?period_month=2025-01

# 汇率管理
GET /api/finance/fx-rates
POST /api/finance/fx-rates
{
  "rate_date": "2025-01-29",
  "from_currency": "USD",
  "rate": 7.25
}

# 会计期间
GET /api/finance/periods/list?year=2025
POST /api/finance/periods/{period_code}/close
```

---

## 📝 使用示例

### 示例1：上传并分摊月度费用

```python
# 准备费用数据（从Excel模板）
expenses = [
    {
        "expense_type_raw": "租金",
        "vendor": "物业公司A",
        "amount": 12316.0,
        "currency": "CNY",
        "tax_rate": 0.09,
        "memo": "铁像寺水街店1月租金"
    },
    {
        "expense_type_raw": "工资",
        "amount": 14437.6,
        "currency": "CNY",
        "tax_rate": 0,
        "shop_id": "shopee_sg_3c",  # 指定店铺，不需分摊
        "memo": "KA员工1月工资"
    }
]

# 1. 上传费用
response = requests.post(
    "http://localhost:8001/api/finance/expenses/upload",
    json={
        "period_month": "2025-01",
        "expenses": expenses
    }
)

# 2. 执行分摊
response = requests.post(
    "http://localhost:8001/api/finance/expenses/allocate",
    json={
        "period_month": "2025-01",
        "driver": "revenue_share"
    }
)

# 3. 查询P&L
response = requests.get(
    "http://localhost:8001/api/finance/pnl/shop",
    params={"period_month": "2025-01"}
)

print(response.json())
# {
#   "success": true,
#   "data": [
#     {
#       "platform_code": "shopee",
#       "shop_id": "sg_3c",
#       "period_month": "2025-01",
#       "revenue": 250940.0,
#       "cogs": 220000.0,
#       "gross_profit": 30940.0,
#       "operating_expenses": 8621.33,  # 分摊后
#       "contribution_profit": 22318.67,
#       "gross_margin_pct": 12.3
#     }
#   ]
# }
```

### 示例2：在线新增标准字段

```javascript
// 前端：字段映射页 → 新增字段按钮

const newField = {
  field_code: "expense_custom_marketing",
  cn_name: "线上推广费",
  en_name: "Online Marketing",
  data_domain: "finance",
  field_group: "amount",
  data_type: "currency",
  synonyms: ["推广", "线上广告", "digital marketing"],
  created_by: "admin"
}

const response = await api._post('/field-mapping/dictionary/fields', newField)

// 10秒后，该字段立即可用于费用映射
```

### 示例3：采购完整流程

```python
# 1. 创建供应商
vendor = {
    "vendor_code": "V001",
    "vendor_name": "深圳XX科技有限公司",
    "country": "CN",
    "tax_id": "91440300XXXX",
    "payment_terms": "NET30"
}

# 2. 创建PO
po = {
    "vendor_code": "V001",
    "po_date": "2025-01-29",
    "expected_date": "2025-02-15",
    "currency": "CNY",
    "lines": [
        {
            "platform_sku": "HW_PURA70_ULTRA_BLACK",
            "product_title": "华为Pura70 Ultra 黑色",
            "qty_ordered": 100,
            "unit_price": 5000.0
        }
    ]
}

# 3. 审批（自动通过 or 人工）
# 金额=500000 > 5000 → 需审批

# 4. 收货入库
grn = {
    "po_id": "PO202501290001",
    "receipt_date": "2025-02-01",
    "lines": [
        {
            "po_line_id": 1,
            "qty_received": 98,  # 实收98台
            "unit_cost": 5000.0
        }
    ]
}

# 5. 过账到库存流水（自动计算WAC）
# inventory_ledger自动记录：
# - qty_before: 0
# - avg_cost_before: 0
# - qty_in: 98
# - unit_cost: 5000
# - qty_after: 98
# - avg_cost_after: 5000

# 6. 上传发票 → OCR → 三单匹配
```

---

## 🎯 对账与数据质量

### 三维度自动对账

#### 对账1：收入对账

```sql
-- 订单收入 vs 总账收入
SELECT 
    '订单收入' as source,
    SUM(sales_amount_cny) as amount
FROM mv_sales_day_shop_sku
WHERE sale_date BETWEEN '2025-01-01' AND '2025-01-31'

UNION ALL

SELECT 
    '总账收入' as source,
    SUM(credit_amt) as amount
FROM journal_entry_lines jel
INNER JOIN gl_accounts ga ON jel.account_code = ga.account_code
WHERE ga.account_type = 'revenue'
  AND jel.created_at::date BETWEEN '2025-01-01' AND '2025-01-31';

-- 差异阈值：< 0.1%
```

#### 对账2：库存对账

```sql
-- 流水账累计 vs 期末库存
WITH ledger_cumulative AS (
    SELECT 
        platform_sku,
        SUM(qty_in - qty_out) as ledger_qty
    FROM inventory_ledger
    GROUP BY platform_sku
),
current_stock AS (
    SELECT 
        platform_sku,
        stock as snapshot_qty
    FROM fact_product_metrics
    WHERE metric_date = CURRENT_DATE
)
SELECT 
    l.platform_sku,
    l.ledger_qty,
    s.snapshot_qty,
    l.ledger_qty - s.snapshot_qty as variance
FROM ledger_cumulative l
FULL OUTER JOIN current_stock s USING (platform_sku)
WHERE ABS(l.ledger_qty - COALESCE(s.snapshot_qty, 0)) > 0;

-- 差异阈值：= 0
```

#### 对账3：费用分摊

```sql
-- 分摊前总额 = 分摊后总额
SELECT 
    '分摊前' as stage,
    SUM(base_amt) as total
FROM fact_expenses_month
WHERE period_month = '2025-01'
  AND shop_id IS NULL

UNION ALL

SELECT 
    '分摊后' as stage,
    SUM(allocated_amt) as total
FROM fact_expenses_allocated_day_shop_sku
WHERE allocation_date BETWEEN '2025-01-01' AND '2025-01-31';

-- 差异：0
```

---

## ⚙️ 配置与扩展

### 扩展1：新增费用类型

```sql
-- 方式A：前端在线新增
POST /api/field-mapping/dictionary/fields
{
  "field_code": "expense_cloud_service",
  "cn_name": "云服务费",
  "data_domain": "finance",
  "synonyms": ["阿里云", "AWS", "云计算"]
}

-- 方式B：SQL直接插入
INSERT INTO field_mapping_dictionary 
(field_code, cn_name, data_domain, field_group, synonyms, active, version, status)
VALUES 
('expense_cloud_service', '云服务费', 'finance', 'amount', 
 '["阿里云", "AWS", "云计算"]'::jsonb, true, 1, 'active');
```

### 扩展2：修改分摊规则

```sql
-- 创建新分摊规则
INSERT INTO allocation_rules 
(rule_name, scope, driver, effective_from, active)
VALUES 
('店铺订单量分摊', 'expense', 'orders_share', '2025-02-01', true);

-- 执行分摊时指定driver
POST /api/finance/expenses/allocate
{
  "period_month": "2025-02",
  "driver": "orders_share"  -- 改为按订单量分摊
}
```

### 扩展3：切换成本计价法

```sql
-- 当前：移动加权平均（默认）
-- 扩展：FIFO视图（从inventory_ledger重算）

CREATE MATERIALIZED VIEW mv_inventory_ledger_fifo AS
WITH cost_layers AS (
    SELECT 
        platform_sku,
        transaction_date,
        unit_cost_wac as layer_cost,
        qty_in as layer_qty,
        ROW_NUMBER() OVER (PARTITION BY platform_sku ORDER BY transaction_date) as layer_no
    FROM inventory_ledger
    WHERE movement_type = 'receipt'
)
-- TODO: FIFO消费逻辑
SELECT * FROM cost_layers;
```

---

## 🚨 故障排查

### 问题1：费用映射失败

```
错误：费用类型'推广费'未找到映射

解决：
1. 查看隔离区
   GET /api/management/data-quarantine?data_domain=finance
   
2. 在线新增字段
   POST /api/field-mapping/dictionary/fields
   {
     "field_code": "expense_promotion_fee",
     "cn_name": "推广费",
     "synonyms": ["推广", "营销"]
   }
   
3. 重新导入费用文件
```

### 问题2：P&L数据为0

```
原因：物化视图未刷新

解决：
psql -U postgres -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_day_shop_sku;"
psql -U postgres -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pnl_shop_month;"
```

### 问题3：三单匹配差异

```
差异：PO数量100，GRN数量98，Invoice数量100

处理：
1. 查看差异日志
   SELECT * FROM three_way_match_log WHERE match_status = 'variance';
   
2. 人工审批差异
   UPDATE three_way_match_log 
   SET approved_by = 'finance_manager', approved_at = now()
   WHERE match_id = 123;
```

---

## 📊 性能优化

### 索引策略

```sql
-- 高频查询索引（已创建）
CREATE INDEX idx_mv_sales_shop_date ON mv_sales_day_shop_sku(platform_code, shop_id, sale_date);
CREATE INDEX idx_mv_pnl_shop_period ON mv_pnl_shop_month(platform_code, shop_id, period_month);
CREATE INDEX ix_inventory_ledger_sku_date ON inventory_ledger(platform_code, shop_id, platform_sku, transaction_date);
```

### 查询优化建议

```sql
-- ✅ 推荐：使用物化视图
SELECT * FROM mv_pnl_shop_month WHERE period_month = '2025-01';

-- ❌ 避免：实时聚合大表
SELECT 
    platform_code, shop_id,
    SUM(sales_amount_cny)
FROM fact_order_items
WHERE order_date BETWEEN '2025-01-01' AND '2025-01-31'
GROUP BY platform_code, shop_id;
```

---

## 🔐 安全与合规

### 权限控制

- 费用导入：`finance`角色
- 费用分摊：`finance_manager`角色
- 关账：`finance_manager`角色
- 查看P&L：`admin`, `manager`, `finance`角色

### 审计追踪

```sql
-- 查看辞典变更历史
SELECT * FROM field_mapping_audit 
WHERE entity_type = 'dictionary' 
ORDER BY operated_at DESC;

-- 查看关账历史
SELECT * FROM dim_fiscal_calendar 
WHERE status = 'closed' 
ORDER BY closed_at DESC;

-- 查看审批历史
SELECT * FROM approval_logs 
WHERE entity_type = 'PO' 
ORDER BY approved_at DESC;
```

---

## 📚 附录

### A. 费用类型清单

| field_code | cn_name | 说明 |
|------------|---------|------|
| expense_rent | 租金 | 店铺/仓库租金 |
| expense_salary | 工资 | 员工薪资 |
| expense_advertising | 广告费 | 品牌推广/LED广告 |
| expense_utilities | 水电费 | 水/电/暖气费 |
| expense_bank_fee | 刷卡手续费 | 支付手续费 |
| ... | ... | ... |

### B. 物化视图刷新策略

| 视图 | 刷新频率 | 方式 |
|------|---------|------|
| mv_sales_day_shop_sku | 每小时 | Celery定时任务 |
| mv_inventory_snapshot_day | 每小时 | Celery定时任务 |
| mv_pnl_shop_month | 每日凌晨 | Celery定时任务 |
| mv_vendor_performance | 每周 | Celery定时任务 |
| mv_tax_report_summary | 每日 | Celery定时任务 |

### C. 关键SQL示例

见 `sql/create_finance_materialized_views.sql`

---

**文档版本**: v1.0  
**最后更新**: 2025-01-29  
**维护者**: 西虹ERP开发团队



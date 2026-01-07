# v4.4.0 快速参考卡片

**版本**: v4.4.0 | **更新**: 2025-01-29 | **打印友好**

---

## 🚀 核心功能（3个）

### 1. 费用导入与分摊

```
财务管理 → 费用导入
1. 下载模板
2. 填写数据（期间/类型/金额）
3. 上传
4. 执行分摊
```

### 2. P&L月报查询

```
财务管理 → P&L月报
1. 选择期间/店铺
2. 点击查询
3. 查看：收入/成本/毛利/费用/利润
```

### 3. 汇率维护

```
财务管理 → 汇率管理
1. 新增汇率
2. 选择货币/输入汇率
3. 保存
```

---

## 📊 关键数据表

| 表名 | 用途 | 重要字段 |
|------|------|---------|
| fact_expenses_month | 月度费用 | period_month, expense_type, amount |
| inventory_ledger | 库存流水 | platform_sku, qty, unit_cost_wac |
| mv_pnl_shop_month | P&L月报 | revenue, cogs, gross_profit |
| po_headers | 采购订单 | po_id, vendor, total_amt, status |

---

## 🔌 常用API（8个）

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/finance/expenses/upload` | POST | 上传费用 |
| `/api/finance/expenses/allocate` | POST | 执行分摊 |
| `/api/finance/pnl/shop` | GET | 查询P&L |
| `/api/finance/periods/list` | GET | 会计期间 |
| `/api/finance/fx-rates` | GET/POST | 汇率 |
| `/api/procurement/po/create` | POST | 创建PO |
| `/api/field-mapping/dictionary/fields` | POST | 新增字段 |
| `/api/field-mapping/metrics/formulas` | GET | 计算指标 |

---

## 🛠️ 常用命令（6个）

```bash
# 1. 启动系统
python run.py

# 2. 部署v4.4.0
python scripts/deploy_v4_4_0_finance.py

# 3. 验证部署
python scripts/verify_v4_4_0_deployment.py

# 4. 初始化辞典
python scripts/seed_finance_dictionary.py

# 5. 运行测试
python scripts/test_v4_4_0_complete.py

# 6. 刷新物化视图
psql -U postgres -d xihong_erp -c "REFRESH MATERIALIZED VIEW mv_pnl_shop_month;"
```

---

## 🎯 每月工作流（财务人员）

```
月初（1-5号）：
  Day 1: 上传上月费用
  Day 2: 执行分摊
  Day 3: 查看P&L，导出报表
  Day 4: 对账验证
  Day 5: 确认无误后关账

月中：
  随时查看P&L
  维护汇率（如有变化）

月末：
  准备下月费用Excel
```

---

## 📋 费用类型速查

| 类别 | 费用类型 | field_code |
|------|---------|-----------|
| 租金 | 租金/物业费/推广费 | expense_rent |
| 人力 | 工资/社保 | expense_salary |
| 市场 | 广告费/营销活动 | expense_advertising |
| 运营 | 水电费/网络费/办公费 | expense_utilities |
| 财务 | 刷卡手续费/分期费 | expense_bank_fee |
| 税金 | 印花税/城建税 | expense_stamp_duty |

---

## ⚠️ 注意事项

1. **期间格式**: 必须YYYY-MM（如2025-01）
2. **货币代码**: 必须大写（CNY/USD/SGD）
3. **金额**: 正数，保留2位小数
4. **关账后**: 数据不可修改（谨慎操作）
5. **分摊**: 必须有收入数据才能分摊

---

## 🆘 紧急联系

| 问题类型 | 查看文档 |
|---------|---------|
| 操作问题 | [用户指南](V4_4_0_USER_GUIDE.md) |
| 技术问题 | [财务域指南](V4_4_0_FINANCE_DOMAIN_GUIDE.md) |
| 部署问题 | [快速部署](QUICK_DEPLOY_V4_4_0.md) |

---

**访问地址**:
- 前端: http://localhost:5173/#/financial-management
- API文档: http://localhost:8001/docs

**快速帮助**: 按F1或查看系统帮助



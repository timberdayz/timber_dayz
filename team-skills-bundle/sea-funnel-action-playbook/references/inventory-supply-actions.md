# Inventory And Supply Actions

用于库存、周转、缺货、退货和供应链诊断。

## Matrix

| 数据表现 | 瓶颈判断 | 标准动作 |
|---|---|---|
| 销量好、经常缺货 | 补货和库存节奏问题 | 设安全库存、补货点、供应商备货机制 |
| 库存高、转化低 | 需求或商品承接弱 | 暂停补货、清理库存、重做卖点 |
| 30天+库存价值高 | 轻度积压 | 做组合、优惠、内容清理 |
| 60天+库存价值高 | 中度积压 | 重点清理，控制新品采购 |
| 90天+库存价值高 | 高风险积压 | 清仓、停采、复盘选品错误 |
| 单量多、退货高 | 产品体验问题 | 先修产品和详情，不要放量 |
| 物流慢导致差评 | 履约问题 | 调物流、调整承诺时效、优化仓配 |
| 质量波动导致退货 | 供应链稳定性问题 | 加质检、换供应商、降低放量 |

## Review Metrics

- inventory_total_value
- inventory_backlog_30d_value
- inventory_backlog_60d_value
- inventory_backlog_90d_value
- clearance_priority_score
- stockout_qty
- return reason
- estimated_turnover_days

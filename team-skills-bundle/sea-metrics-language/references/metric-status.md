# Metric Status

| metric | status | allowed_in_meeting | reason | owner |
|---|---|---|---|---|
| gmv | stable | yes | 数据源稳定、经营含义明确 | data |
| order_count | stable | yes | 数据源稳定 | data |
| traffic | stable | yes | 当前业务概览与 mart 层口径稳定 | data |
| conversion_rate | stable | yes | 系统统一按订单数 / 访客数计算 | data |
| avg_order_value | stable | yes | 系统统一按 GMV / 订单数计算 | data |
| profit | stable | yes | 可用，但引用时需说明来源模块 | finance |
| estimated_gross_profit | stable | yes | 经营指标模块可用 | finance |
| monthly_target | stable | yes | A 类目标表支持 | ops |
| monthly_total_achieved | stable | yes | 经营指标模块已承接 | ops |
| monthly_achievement_rate | stable | yes | 目标达成逻辑清晰 | ops |
| time_gap | stable | yes | 时间进度与达成率逻辑清晰 | ops |
| inventory_total_value | stable | yes | 库存汇总可用 | ops |
| inventory_backlog_30d_value | stable | yes | 库存风险判断可用 | ops |
| inventory_backlog_60d_value | stable | yes | 库存风险判断可用 | ops |
| inventory_backlog_90d_value | stable | yes | 库存风险判断可用 | ops |
| clearance_priority_score | stable | yes | 清理排序逻辑已稳定 | ops |
| attach_rate | observe | conditional | 部分模块稳定，跨模块判断仍需谨慎 | ops |
| labor_efficiency | blocked | no | 当前系统返回固定 0 | ops |
| roas | blocked | no | 尚未形成统一系统口径 | marketing |
| mer | blocked | no | 尚未形成统一系统口径 | marketing |
| repurchase_rate | blocked | no | 尚未形成统一系统口径 | crm |
| hero_sku_ratio | blocked | no | 尚未形成统一系统口径 | founder |

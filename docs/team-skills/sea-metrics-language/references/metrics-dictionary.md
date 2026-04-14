# Metrics Dictionary

本文件定义团队统一经营语言。  
所有指标默认优先使用系统统一口径；若直接引用平台后台，必须明确说明。

## gmv

- 中文名：GMV
- 层级：老板层 / 经营层
- 业务定义：指定时间和范围内的商品交易总额
- 系统统一口径：按 ERP 清洗后的订单 / 交易数据聚合
- 公式：成交金额汇总
- 适用：经营复盘、平台 / 店铺 / 品类规模判断
- 不适用：单独判断利润质量、营销效率、选品可做性
- 配套指标：`order_count`、`avg_order_value`、`profit`
- 当前状态：`stable`

## order-count

- 中文名：订单数
- 标准键：`order_count`
- 层级：老板层 / 经营层 / 选品层
- 业务定义：指定范围内的有效订单数量
- 系统统一口径：按系统统一后的有效订单统计
- 公式：有效订单计数
- 适用：判断需求承接、GMV 结构、转化结果
- 不适用：单独判断流量质量
- 配套指标：`traffic`、`conversion_rate`、`gmv`
- 当前状态：`stable`

## traffic

- 中文名：客流量 / 访客数
- 标准键：`traffic`
- 层级：老板层 / 经营层 / 选品层 / 营销层
- 业务定义：进入店铺、页面或指定经营范围的访客数
- 系统统一口径：业务概览以 `visitor_count` 为主口径
- 公式：访客计数
- 适用：流量规模判断、流量变化归因
- 不适用：单独判断销售质量
- 配套指标：`conversion_rate`、`gmv`、`order_count`
- 当前状态：`stable`

## conversion-rate

- 中文名：转化率
- 标准键：`conversion_rate`
- 层级：老板层 / 经营层 / 选品层 / 营销层
- 业务定义：流量转成订单的效率
- 系统统一口径：`order_count / visitor_count * 100`
- 公式：订单数 ÷ 访客数 × 100%
- 适用：经营复盘、页面效率判断、选品验证
- 不适用：单独判断广告效率
- 配套指标：`traffic`、`order_count`、`avg_order_value`
- 当前状态：`stable`

## avg-order-value

- 中文名：客单价
- 标准键：`avg_order_value`
- 层级：老板层 / 经营层 / 选品层
- 业务定义：单个订单平均成交金额
- 系统统一口径：`gmv / order_count`
- 公式：GMV ÷ 订单数
- 适用：价格带判断、GMV 结构判断、精品价格带判断
- 不适用：单独判断利润
- 配套指标：`gmv`、`order_count`、`profit`
- 当前状态：`stable`

## profit

- 中文名：利润
- 标准键：`profit`
- 层级：老板层 / 经营层
- 业务定义：订单或经营结果中的利润值
- 系统统一口径：以系统聚合后的利润字段为准；引用时必须说明来源模块
- 公式：按数据源定义
- 适用：经营质量判断、平台 / 店铺优先级判断
- 不适用：跨模块不加说明地横向比较
- 配套指标：`gmv`、`estimated_gross_profit`
- 当前状态：`stable`

## estimated-gross-profit

- 中文名：预计毛利
- 标准键：`estimated_gross_profit`
- 层级：经营层
- 业务定义：业务概览经营指标中的毛利估算值
- 系统统一口径：来自 `api.business_overview_operational_metrics_module`
- 公式：按月度店铺 KPI 利润字段聚合
- 适用：经营结果判断、费用对比
- 不适用：直接替代最终财务净利润
- 配套指标：`estimated_expenses`、`operating_result`
- 当前状态：`stable`

## monthly-target

- 中文名：月目标
- 标准键：`monthly_target`
- 层级：老板层 / 经营层
- 业务定义：当前月度经营目标销售额
- 系统统一口径：来自 A 类目标表
- 公式：目标销售额汇总
- 适用：月度管理、店铺赛马、经营结果判断
- 不适用：选品判断
- 配套指标：`monthly_total_achieved`、`monthly_achievement_rate`
- 当前状态：`stable`

## monthly-total-achieved

- 中文名：当月总达成
- 标准键：`monthly_total_achieved`
- 层级：老板层 / 经营层
- 业务定义：当前月累计已完成销售额
- 系统统一口径：经营指标模块月度累计达成值
- 公式：当月成交金额汇总
- 适用：月度经营复盘
- 不适用：单独判断趋势质量
- 配套指标：`monthly_target`、`monthly_achievement_rate`
- 当前状态：`stable`

## monthly-achievement-rate

- 中文名：月达成率
- 标准键：`monthly_achievement_rate`
- 层级：老板层 / 经营层
- 业务定义：月累计达成相对于月目标的完成比例
- 系统统一口径：`monthly_total_achieved / monthly_target * 100`
- 公式：月累计达成 ÷ 月目标 × 100%
- 适用：月度管理、经营复盘
- 不适用：选品、营销单点判断
- 配套指标：`monthly_target`、`time_gap`
- 当前状态：`stable`

## time-gap

- 中文名：时间 GAP
- 标准键：`time_gap`
- 层级：经营层
- 业务定义：经营达成率与时间进度之间的差值
- 系统统一口径：月达成率减去当月时间进度
- 公式：达成率 - 时间进度
- 适用：识别“跑赢进度”或“落后进度”
- 不适用：单独判断增长质量
- 配套指标：`monthly_achievement_rate`
- 当前状态：`stable`

## inventory-total-value

- 中文名：总库存价值
- 标准键：`inventory_total_value`
- 层级：库存层 / 经营层
- 业务定义：当前库存资产价值总量
- 系统统一口径：库存积压模块汇总值
- 公式：库存价值汇总
- 适用：库存规模判断、资金占用感知
- 不适用：单独判断库存是否健康
- 配套指标：`inventory_backlog_30d_value`、`clearance_priority_score`
- 当前状态：`stable`

## inventory-backlog-30d-value

- 中文名：30天+预计周转库存
- 标准键：`inventory_backlog_30d_value`
- 层级：库存层
- 业务定义：预计周转天数在 30 天以上的库存价值
- 系统统一口径：库存积压模块汇总值
- 公式：30 天以上 SKU 库存价值汇总
- 适用：库存风险判断
- 不适用：单独判断清理顺序
- 配套指标：`inventory_backlog_60d_value`、`inventory_backlog_90d_value`
- 当前状态：`stable`

## inventory-backlog-60d-value

- 中文名：60天+预计周转库存
- 标准键：`inventory_backlog_60d_value`
- 层级：库存层
- 业务定义：预计周转天数在 60 天以上的库存价值
- 系统统一口径：库存积压模块汇总值
- 适用：中高风险库存判断
- 当前状态：`stable`

## inventory-backlog-90d-value

- 中文名：90天+预计周转库存
- 标准键：`inventory_backlog_90d_value`
- 层级：库存层
- 业务定义：预计周转天数在 90 天以上的库存价值
- 系统统一口径：库存积压模块汇总值
- 适用：高风险库存判断
- 当前状态：`stable`

## clearance-priority-score

- 中文名：清理优先级
- 标准键：`clearance_priority_score`
- 层级：库存层 / 经营层
- 业务定义：用于识别应优先清理的积压 SKU
- 系统统一口径：库存风险排序分值
- 公式：按库存风险 SQL 规则计算
- 适用：库存清理优先级判断
- 不适用：选品判断
- 配套指标：`inventory_total_value`、`estimated_turnover_days`
- 当前状态：`stable`

## attach-rate

- 中文名：连带率
- 标准键：`attach_rate`
- 层级：经营层 / 选品层
- 业务定义：每笔订单的平均件数
- 系统统一口径：`total_items / order_count`
- 公式：商品件数 ÷ 订单数
- 适用：组合销售、套装机会、价格带结构判断
- 不适用：跨模块不加说明地直接比较
- 配套指标：`avg_order_value`
- 当前状态：`observe`

## labor-efficiency

- 中文名：人效
- 标准键：`labor_efficiency`
- 层级：经营层
- 业务定义：单位人力对应的经营产出
- 系统统一口径：当前业务概览尚未形成有效计算
- 备注：当前 service 返回固定值 0
- 适用：暂不允许使用
- 当前状态：`blocked`

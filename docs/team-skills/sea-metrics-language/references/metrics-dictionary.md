# Metrics Dictionary

本文档定义团队统一经营语言。  
所有指标默认优先使用系统统一口径；若直接引用平台后台，必须明确说明来源。

## gmv

- 中文名：GMV
- 标准键：`gmv`
- 系统统一口径：按 ERP 清洗后的订单 / 交易数据聚合
- 当前状态：`stable`

## order-count

- 中文名：订单数
- 标准键：`order_count`
- 系统统一口径：按系统统一后的有效订单统计
- 当前状态：`stable`

## traffic

- 中文名：客流量
- 标准键：`traffic`
- 业务定义：店铺页面被查看、被路过、被浏览的人流量规模
- 系统统一口径：**默认以 `page_views` 为主口径**
- 辅助指标：`visitor_count` 表示实际进入店铺的客户数量，不等于主客流量
- 当前状态：`stable`

## conversion-rate

- 中文名：转化率
- 标准键：`conversion_rate`
- 业务定义：流量转成订单的效率
- 系统统一口径：默认按 `order_count / visitor_count * 100`
- 说明：若页面展示的是 `page_views / visitor_count`，必须改名，不能继续叫“转化率”
- 当前状态：`stable`

## avg-order-value

- 中文名：客单价
- 标准键：`avg_order_value`
- 系统统一口径：`gmv / order_count`
- 当前状态：`stable`

## profit

- 中文名：利润
- 标准键：`profit`
- 系统统一口径：以系统聚合后的利润字段为准；引用时必须说明来源模块
- 当前状态：`stable`

## estimated-gross-profit

- 中文名：预计毛利
- 标准键：`estimated_gross_profit`
- 系统统一口径：来自 `api.business_overview_operational_metrics_module`
- 当前状态：`stable`

## monthly-target

- 中文名：月目标
- 标准键：`monthly_target`
- 系统统一口径：来自 A 类目标表
- 当前状态：`stable`

## monthly-total-achieved

- 中文名：当月总达成
- 标准键：`monthly_total_achieved`
- 系统统一口径：经营指标模块月度累计达成值
- 当前状态：`stable`

## monthly-achievement-rate

- 中文名：月达成率
- 标准键：`monthly_achievement_rate`
- 系统统一口径：`monthly_total_achieved / monthly_target * 100`
- 当前状态：`stable`

## time-gap

- 中文名：时间 GAP
- 标准键：`time_gap`
- 系统统一口径：月达成率减去当月时间进度
- 当前状态：`stable`

## attach-rate

- 中文名：连带率
- 标准键：`attach_rate`
- 系统统一口径：`total_items / order_count`
- 当前状态：`observe`

## labor-efficiency

- 中文名：人效
- 标准键：`labor_efficiency`
- 系统统一口径：当前业务概览尚未形成有效计算
- 当前状态：`blocked`

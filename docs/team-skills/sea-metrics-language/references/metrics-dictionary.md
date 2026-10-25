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
- 配套指标：`deep_stagnant_value`、`backlog_ratio`、`clearance_priority_score`
- 当前状态：`stable`

## deep-stagnant-value

- 中文名：重度积压货值
- 标准键：`deep_stagnant_value`
- 层级：库存层
- 业务定义：**距上次进货 ≥ 180 天**的库存货值——压在仓里半年以上没补过货
- 系统统一口径：滞销模块汇总值（`mart.inventory_backlog_base` 求和）
- 公式：`SUM(inventory_value) WHERE days_since_restock >= 180`
- 适用：资金占用感知、深度积压识别
- 不适用：单独判断清理顺序
- 配套指标：`mid_stagnant_value`、`backlog_ratio`、`days_since_restock`
- 当前状态：`stable`

## mid-stagnant-value

- 中文名：中度积压货值
- 标准键：`mid_stagnant_value`
- 层级：库存层
- 业务定义：**距上次进货 90 ~ 180 天**的库存货值
- 系统统一口径：滞销模块汇总值
- 公式：`SUM(inventory_value) WHERE 90 <= days_since_restock < 180`
- 适用：中高风险库存判断
- 配套指标：`deep_stagnant_value`、`backlog_ratio`、`days_since_restock`
- 当前状态：`stable`

## backlog-ratio

- 中文名：滞销占比
- 标准键：`backlog_ratio`
- 层级：库存层 / 经营层
- 业务定义：滞销货值（距上次进货 ≥ 90 天）占总库存货值的比例
- 系统统一口径：滞销模块汇总值
- 公式：`(deep_stagnant_value + mid_stagnant_value) ÷ total_value`
- 适用：经营看板的滞销严重程度
- 不适用：只看比例不看绝对货值（比例低也可能是货值巨大）
- 配套指标：`deep_stagnant_value`、`mid_stagnant_value`、`inventory_total_value`
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

## checklist-dos-sales30

- 中文名：可售天数（近30天销量口径）
- 标准键：`checklist_dos_sales30`
- 层级：库存层 / 经营层
- 业务定义：**Days of Supply** —— 当前库存按当前销售速度还能卖多少天（单位：天）
- 系统统一口径：`可用库存 ÷ (近30天销量 ÷ 30)`；分子取**可用库存**（预占与次品卖不掉，不计入「还能卖多久」）
- 公式：可用库存 ÷ 近30天销量 × 30
- 数据来源：妙手仓库清单自带的「近30天销量数据」列（**行级存储快照**，只在那一行被写入时才刷新）
- 粒度：SKU × 仓
- ⚠️ **定位：参考值，不作判定依据**（2026-10-24 晚间定案）：
  - 妙手销量是行级存储快照，不随时间自行更新；增量采集批次实测只覆盖约 **13.6%** 的 SKU，其余行的分母是陈旧的
  - → **不得用于滞销入选、排序、汇总卡口径**；只作参考展示，列头或 tooltip 必须标注「参考」
  - 滞销判据用**距上次进货天数**（`days_since_restock`），不是 DOS
  - 不做口径时点管控（不需要 `dos_as_of` / `dos_stale`）
  - 不可算时返回 `NULL` + 独立状态标签（`computable` / `zero_sales` / `stockout` / `no_stock`），**禁止 9999 之类的哨兵值**
- 适用：**参考展示**——让运营对「按最近一次采集到的销量算，这批货还能卖多久」有个量级感
- 不适用：
  - **不作任何判定依据**（不用它做滞销入选 / 排序 / 汇总卡口径）
  - 单独判断实时动销速度（分母只在行被写入时刷新）
  - 预测未来销量（窗口销量 ≠ 未来销量）
- 配套指标：`checklist_dos_sales90`、`days_since_restock`、`inventory_total_value`
- 当前状态：`observe`

## checklist-dos-sales90

- 中文名：可售天数（近90天销量口径）
- 标准键：`checklist_dos_sales90`
- 层级：库存层 / 经营层
- 业务定义：**Days of Supply** —— 当前库存按当前销售速度还能卖多少天（单位：天）
- 系统统一口径：`可用库存 ÷ (近90天销量 ÷ 90)`
- 公式：可用库存 ÷ 近90天销量 × 90
- 数据来源：妙手仓库清单自带的「近90天销量数据」列（行级存储快照）
- 粒度：SKU × 仓
- 与 `checklist_dos_sales30` 的关系：同一公式、不同窗口。
  30 天窗口会把「近90天卖过、近30天没动」的行误判成快断货，**判滞销一律用 90 天**
- 新鲜度契约与不可算约定：同 `checklist_dos_sales30`（**参考值，不作判定依据**）
- 适用：参考展示
- 不适用：
  - **不作任何判定依据**——滞销入选、排序、汇总卡口径一律不用 DOS
  - 单独判断实时动销速度（分母只在行被写入时刷新）
  - 预测未来销量（窗口销量 ≠ 未来销量）
- 配套指标：`checklist_dos_sales30`、`days_since_restock`、`inventory_total_value`
- 当前状态：`observe`

## days-since-restock

- 中文名：距上次进货天数
- 标准键：`days_since_restock`
- 层级：库存层 / 经营层
- 业务定义：**这批货最后一次进货（库存数量增加）距今多少天**
  ——西虹的经营模式是「卖完不补货、偶尔补货」，所以**补货才开始重新计时，销售不重置**
- 系统统一口径：`今天 − stock_added_at`；
  `stock_added_at` = 该 SKU×仓 **库存总量最后一次增加（进货）**的时间，
  由落盘层的「双闸判定」产出并维护在 `mart.inventory_state`，**不信妙手的「更新时间」**
- 公式：`当前日期 − stock_added_at`
- 粒度：SKU × 仓
- 为什么不直接用妙手的时间戳（实测：两批快照 1109 个共同 SKU×仓）：
  - 妙手「创建时间」= **首次铺货时间**，补货**不会**重置它（1109/1109 行不变）
  - 妙手「更新时间」**每次写入都变**，连销售都会变（0/1109 行相同）；
    且会被一次 bulk UPDATE 批量覆盖成同一时刻（file 2764：535 行 / 43.7% 被覆盖成 2026-05-08 10:36:36~39）
- 为什么用它而不用 DOS：
  - 它是**事件时刻**，不会随时间流逝而漂移；DOS 的分母（窗口销量）会漂移
  - 增量模式下**始终准确**：增量只更新变动行，没被更新的行本来就对
  - 单调增长 → **不会漏判**；DOS 在增量下会把老 SKU 判轻
  - 不会把**刚补货的新货**误判成老积压（实测 DOS 会误判 169 行 / ¥12,098）
- 分档：门槛与档位名**来自档位表** `finance.sku_pricing_policies`：**0 / 60 / 90 / 120 天**
  （日常 / 滞销30天 / 滞销60天 / 滞销60天以上）——商业参数，一个数字不许改
- SKU 级聚合：**取各仓最长**，且**只算还有库存的仓**
  （商品中心是 SKU 级定价：一个仓压着就是这货整体压着；已清空的仓不压资金）
- ⚠️ **两套分档并存，别混用**：
  - **档位表 0/60/90/120** = 折扣档位（这一档最多能打几折），用于商品中心选档与 SKU 级滞销清单
  - **业务概览 90/180** = 压资金额深浅（重度 / 中度积压），用于经营看板
- 适用：滞销入选、滞销货值汇总、滞销排序、**商品中心最低售价选档**
- 不适用：
  - 单独判断卖得动不动（它只说「多久没补货」，不说「在卖」）
  - 跨 SKU 直接比较商品好坏（不同品类的正常周转节奏不同）
- ⚠️ **不要拿它和「库龄」混用**：业务说的「库龄」=「这批货压了多久」→ **就是本指标**；
  而妙手的「创建时间」是**首次铺货时间**，不能直接当库龄用
  （实测 98.5% 的行 ≥180 天，其中「还在卖的老品」430 行 / ¥187,980，
  会把两年前上架一直在卖的老品误判成最深档）
- ⚠️ **存量数据不作为口径证据**：当前状态层是首次观测补灌的（锚点 = 首次铺货时间），
  只能验证机制，不能用来论证商业影响
- 配套指标：`inventory_total_value`、`checklist_dos_sales90`、`deep_stagnant_value`
- 当前状态：`stable`

## order-dos-sales30

- 中文名：可售天数（订单销量口径，近30天）
- 标准键：`order_dos_sales30`
- 层级：库存层 / 经营层
- 业务定义：同上，但分母用 **ERP 订单成交数量**而非库存清单的销量列
- 系统统一口径：`可用库存 ÷ (近30天订单销量 ÷ 30)`
- 公式：可用库存 ÷ 近30天订单销量 × 30
- 优点：订单成交数不受库存行写入影响，**天然新鲜**
- 粒度限制：订单表**无仓库维度** → 只能到 SKU 级，与仓级运营口径不兼容
- 阻塞项：miaoshou 订单域尚未入库（`b_class.fact_miaoshou_orders_*` 全 0 行），无原料
- 适用：暂不允许使用
- 当前状态：`blocked`

## order-dos-sales90

- 中文名：可售天数（订单销量口径，近90天）
- 标准键：`order_dos_sales90`
- 层级：库存层 / 经营层
- 业务定义：同上，分母用 ERP 近 90 天订单成交数量
- 系统统一口径：`可用库存 ÷ (近90天订单销量 ÷ 90)`
- 公式：可用库存 ÷ 近90天订单销量 × 90
- 粒度限制：SKU 级（订单表无仓库维度）
- 阻塞项：同 `order_dos_sales30`
- 适用：暂不允许使用
- 当前状态：`blocked`

## dos（消歧说明，不是独立指标）

- 出现「DOS」时**必须写全限定名**（`checklist_dos_sales30` / `order_dos_sales90`），
  不得单独用 `dos` 指代某一个口径
- 禁用命名：`quick_dos` / `fast_dos` / `approx_dos`（暗示精度差）、
  `platform_dos_*`（与本仓库 `platform_code` 语义冲突，本仓库 platform_code = shopee / tiktok / miaoshou）、
  `dos_30d` / `dos_90d`（会被读成档位而非销量窗口）
- 中文展示建议：写「**可售天数（近90天销量）**」，不写「DOS-90」
- 两个口径的差异来源见 `references/platform-mapping.md` 的「dos（可售天数）」一节

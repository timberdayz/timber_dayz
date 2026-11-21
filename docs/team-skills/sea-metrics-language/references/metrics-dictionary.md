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
- ⚠️ **分档只有一套（0/60/90/120），别再另起**（2026-11-29 起）：
  - **档位表 0/60/90/120** = 折扣档位（这一档最多能打几折），
    **同时也是经营看板汇总卡、库存概览页、SKU 级滞销清单、商品中心选档的唯一分档**
    （旧看板自造的 <30 / 90~180 / ≥180 三档已下线：30~90 天整段无档 ⇒ 那段货值在卡上看不见）
  - **90/180 只剩「深度积压」这一个独立指标**（`deep_stagnant_value` / `mid_stagnant_value`），
    回答的是「压了多久没动」，**不是**一套分档体系，也不再作为看板的分层展示
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

---

# 投放 ROI 边界（商品中心，2026-11 起登记）

这一组指标来自商品中心的利润测算模块。它们解决的是**投放前**的问题：
「这个品投广告，最多能投到多少 ROI 才不亏」。

⚠️ **它们不是 `roas` / `mer`**：`roas` / `mer` 说的是投放**后**实际拿回多少，
当前仍是 `blocked`（见 `metric-status.md`）。**禁止**用本组指标冒充那两者。

⚠️ **命名纪律**：

- 「广告前贡献毛利率」必须写**全称**。单独的「毛利率」是禁用词 ——
  它指代的东西在仓库里不唯一（扣不扣广告费？扣不扣运费？），一旦省略就会读混。
- 「平台报告 ROI」也必须写全称。单独的「实际 ROI」是禁用词：
  本仓库的「实际」指的是**实际成本**（物流/仓储账单），与「平台实测 ROI」不是一回事。

## break-even-roi

- 中文名：保本 ROI
- 标准键：`break_even_roi`
- 层级：经营层 / 营销层
- 业务定义：**广告费花到这个 ROI，单均就不亏了**。低于它投广告，单均利润为负。
- 系统统一口径：商品中心利润测算（`backend/services/product_roi_service.py`）
- 公式：`商家实收 ÷ 广告前利润`
  - **商家实收** = 测算售价（2026-11-16 口径归一：运营填的就是到手价，不再二次扣券；= 平台 GMV 口径，**不是**买家实付、不是商品金额）
  - **广告前利润** = 商家实收 − (采购成本 + 预估物流成本 + 预估仓储成本 + 贴单费
    + **尾程配送费** + 平台佣金 + 达人佣金 + 物流货损 + 退货损失)，即**扣完除广告费以外的全部成本**
    - **尾程配送费**（2026-11-16 批次 4 进利润）：仓 → 买家那段快递费，**每卖一件必付**，
      按「平台 × 仓 × 重量段」单件计价。算不出来 ⇒ 利润链返回 `None`（**不是按 0 计**）。
- 粒度：SKU × 平台 × 仓（经营档案）
- ⚠️ **缺输入宁可不算，不可乐观**：
  - 成本不全（缺物流规则 / 缺仓储规则 / 未绑 SPU …）⇒ `break_even_roi` 返回 `None` + 缺输入原因，
    **不给**任何看起来能用的数。成本不全时算出来的保本线**偏松**，照着投就是亏。
  - 另有一个**下界**（`break_even_roi_lower_bound`）：把未知成本一律当 0 算出广告前利润的**上界**，
    取倒数得保本 ROI 的**下界**。它**只用来证明**「目标 ROI 低于下界 ⇒ 一定亏」，
    **不能**用来证明「高于下界就安全」。
- ⚠️ **只封顶不封底**：保本 ROI < 1 意味着广告前贡献毛利率 > 100%，那是「成本算错了」的异常信号，
  会被标成异常（`break_even_roi_below_one`）而不是被悄悄截断。
- 适用：投放前判断「这一单能不能投广告」「目标 ROI 定多少」「亏损投放复盘」
- 不适用：
  - 判断投放**实际**赚了多少（那是 `roas`，且它当前 `blocked`）
  - 成本资料不全时作为判定依据（此时它算不出来）
- 配套指标：`suggested_roi`、`advertising_contribution_margin_rate`、`target_roi`
- 当前状态：`observe`

## suggested-roi

- 中文名：建议 ROI
- 标准键：`suggested_roi`
- 层级：经营层 / 营销层
- 业务定义：**在保本线上留出安全边际后，建议运营填进平台后台的目标 ROI**
- 系统统一口径：商品中心利润测算（同 `break_even_roi` 的口径）
- 公式：`保本 ROI × (1 + 安全边际)`，安全边际默认 **20%**（业界实测 12%–25%，取下沿，保守）
- 可执行值 `suggested_roi_clamped`：保本 ROI **先取两位小数** → 乘 (1 + 安全边际) → **再取两位**
  → 按**平台可填上限**封顶（TikTok 20 / Shopee 50）。
  ⚠️ 为什么要先取整再乘：表上保本 ROI 显示 1.97，运营自己算 1.97 × 1.2 = 2.36 ——
  表上写的必须是 2.36 才对得上账。等效单均广告费/净利也由这个数推出，数字之间必须能互相验算。
- 超出平台上限时给提示 `above_platform_ceiling`（**未封顶原值仍保留**并显示，供「真实差距」对比）
- 适用：给运营定投放目标的参考值、复盘「为什么建议值比我填的高」
- 不适用：
  - 当作平台后台的建议值引用（平台建议值**不知道商家的成本结构**，两边不是一回事）
  - 成本不全时作为判定依据
- 配套指标：`break_even_roi`、`target_roi`
- 当前状态：`observe`

## advertising-contribution-margin-rate

- 中文名：广告前贡献毛利率
- 标准键：`advertising_contribution_margin_rate`
- 层级：经营层
- 业务定义：**在扣掉广告费之前，这单能留下多少比例的收入**。它是 ROI 的分母形态。
- 系统统一口径：商品中心利润测算
- 公式：`广告前利润 ÷ 商家实收`
- 粒度：SKU × 平台 × 仓
- ⚠️ 必须写全称「广告前贡献毛利率」。**单独的「毛利率」是禁用词** ——
  仓库里「毛利率」可以指扣不扣广告费、扣不扣运费的多个版本，省略限定词就会读混。
- 适用：判断这个品的利润厚度、解释「为什么它的保本 ROI 这么高」
- 不适用：与平台报表里的毛利率横向比较（平台报表的分子分母口径与这里不同）
- 配套指标：`break_even_roi`、`suggested_roi`
- 当前状态：`observe`

## target-roi

- 中文名：目标 ROI
- 标准键：`target_roi`
- 层级：营销层 / 经营层
- 业务定义：**运营这一轮打算投到的 ROI**（从平台后台的投放计划里抄来的计划值），不是实测值
- 系统统一口径：商品中心经营档案 `finance.sku_operating_profiles.target_roi`
  （来源标记 `target_roi_source`：`user_input` / `migrated_from_legacy_rate`）
- 口径：**商家实收 ÷ 目标 ROI = 广告费用**（平台语言，与 TikTok GMV MAX 同一把标尺）
- 粒度：SKU × 平台 × 仓
- ⚠️ **手填，没有自动采集**：平台广告消耗数据源尚未立项，所以这个数只能人工抄。
- ⚠️ **它不是实测值**：它是一个**意图**。引用时必须说明是「计划投到多少」，不能当成「投到了多少」。
- 适用：投放前设定目标、护栏校验（目标 ROI 低于保本线 ⇒ 拦）
- 不适用：当作投放效果引用（那是 `platform_reported_roi`）
- 配套指标：`break_even_roi`、`suggested_roi`、`platform_reported_roi`
- 当前状态：`observe`

## platform-reported-roi

- 中文名：平台报告 ROI
- 标准键：`platform_reported_roi`（系统字段名 `actual_roi`）
- 层级：营销层 / 经营层
- 业务定义：**运营从平台后台抄回来的、这一轮投放的实际 ROI**
- 系统统一口径：商品中心利润版本 `finance.sku_profit_estimates.actual_roi`
  （来源标记 `actual_roi_source`：`user_input` / `platform_report`）
- 粒度：SKU × 平台 × 仓 × 利润版本（它是**某一轮**的事实，所以挂在版本上）
- ⚠️ **含自然流量 / 达人带货归因**：TikTok GMV MAX 的归因窗口是 7 天点击 + 1 天浏览，
  会把自然流量和达人带货一并计入归因 GMV ⇒ **「达标」很可能只是归因虚高**。
  商品中心目前**拿不到**归因放大系数（没有平台广告消耗数据源）⇒ 判定行只给**警示文案，不给数字**
  （给不出数字时宁可不给，不能编）。
- ⚠️ 必须写全称「平台报告 ROI」。**单独的「实际 ROI」是禁用词**：
  本仓库的「实际」指的是**实际成本**（物流/仓储账单），与平台实测 ROI 不是一回事。
- 适用：投放后复盘、亏损投放识别（低于保本 ROI ⇒ 这一单亏）
- 不适用：
  - 当作公司的真实投放回报（归因口径有系统性高估）
  - 与 TikTok 的数直接和 Shopee 的数横向比较（归因窗口与分母口径都不同）
- 配套指标：`break_even_roi`、`suggested_roi`、`target_roi`
- 当前状态：`observe`

---

# 月度利润看板口径（财务结算中心，2026-11 起登记）

这一组指标来自「月度利润看板」（原「月度利润结算中心」）。看板只回答一句话：
**这个月赚了多少、分给员工多少、人工调整多少、留下多少**。

⚠️ **三层口径**：本节**全部是系统统一口径**。

- 平台原生口径：平台后台的「利润」「人力成本」各自算法不同，本节**不引用、不混用**。
- 系统统一口径：**本节定义的口径**，来源表与公式全部写死，见各条「系统统一口径」。
- 会议决策口径：尚未定版，**不得**与本节混用。

⚠️ **命名纪律**（本组指标的硬约束）：

- **「人员成本」是禁用词**。仓库里它至少指三种东西：工资单总成本、提成前人力成本、提成后人力成本。
  一律写全称：**提成前人力成本** / **提成后人力成本**。
- **「毛利率」不是本组指标**，禁止出现（仓库里「毛利率」指代不唯一）。
- 「利润基数」一律写全称「**店铺利润基数**」（`profit_basis_amount`）——
  它**已经扣过一次提成前人力成本**，这是本组指标最容易重复扣减的地方。
- 「分配额」一律写全称「**员工侧分配额**」（`employee_allocation_amount`）——
  它**只含提成后**金额（绩效工资 + 提成）。

## profit-basis-amount

- 中文名：店铺利润基数
- 标准键：`profit_basis_amount`
- 层级：老板层 / 经营层
- 业务定义：**一家店铺当月扣完成本之后、还能拿去分钱的那个数**。
  它已经扣掉「其他经营成本」和「提成前人力成本」，但**没有**扣绩效工资和提成
  —— 提成基数是「提成**前**利润」，把提成本身算进成本等于同一笔钱扣两次。
- 系统统一口径：`finance.shop_profit_basis`（店铺利润基数快照表），
  **只取非 legacy `A_ONLY_V1` 口径行**（当前口径 `SETTLEMENT_BASIS_V1`；
  历史口径 `A_ONLY_V1` / `A_PRE_COMMISSION_LABOR_V2` 由
  `LaborCostPolicyService.is_legacy_a_only_basis_version` 判定并排除）。
  口径 SSOT 在 `backend/services/labor_cost_policy_service.py`。
- 公式：`店铺订单利润 − (其他经营成本 + 提成前人力成本)`
  - **提成前人力成本** = 底薪 + 岗位工资 + 津贴 + 加班费 + 奖金 + 公司承担社保 + 公司承担公积金
    （字段清单 SSOT：`backend/services/labor_cost_projection_service.py` 的 `PRE_COMMISSION_FIELDS`）
  - **不含**绩效工资（`performance_salary`）与提成本身（`commission`）
- 粒度：平台 × 店铺 × 月
- 适用：判断「这家店这个月真正剩多少可分」；作为员工侧分配额与公司留存的计算起点
- 不适用：
  - 判断单个员工的收入（那是 `employee_allocation_amount`）
  - 与平台后台的「利润」横向比较（平台口径不扣人力成本）
  - 直接当公司留存用（必须先汇总到公司级，见 `company_retained_amount`）
- 配套指标：`employee_allocation_amount`、`company_retained_amount`、`allocation_ratio`
- 当前状态：`stable`

## employee-allocation-amount

- 中文名：员工侧分配额
- 标准键：`employee_allocation_amount`
- 层级：老板层 / 经营层
- 业务定义：**当月从利润里分给员工侧的钱**（绩效工资 + 提成），即「利润分出去的那部分」。
- 系统统一口径：`finance.employee_labor_cost_allocations`（人力成本分摊表），
  **按 `calculation_version` 严格等值过滤**（当前口径 `LABOR_COST_ALLOC_V1`；
  口径名 SSOT 在 `backend/services/labor_cost_projection_service.py` 的
  `LABOR_COST_CALCULATION_VERSION`）。
  `allocation_scope` 同时含 `shop`（有店铺归属）与 `company`（总部等无店铺归属）两种范围，
  **两者都要计入**。
- 公式：`Σ(performance_amount + commission_amount)`
- ⚠️ **只取提成后金额**（绩效工资 + 提成）。
  **不含提成前人力成本**（底薪、岗位工资、津贴、加班费、奖金、公司承担社保、公司承担公积金）
  —— 这部分**已经在 `profit_basis_amount` 里扣过一次**，再扣一次就是重复扣减。
- ⚠️ 引用时**必须写全称**「员工侧分配额」或「提成后人力成本」；
  单独的「人员成本」是禁用词（会被读成含底薪的总额）。
- 粒度：月（可下钻到店 / 人）
- 适用：判断「这个月分给员工多少」「利润分出去多少」；做分摊结果核对
- 不适用：
  - 当作公司全部人力成本（那会漏掉提成前人力成本，那部分在利润基数里）
  - 当作某个员工的实发工资（实发还要看工资单，含个税等代扣项）
  - 判断「分得对不对」——金额只说明分了多少，不说明比例是否合理（比例配置是另一件事）
- 配套指标：`profit_basis_amount`、`company_retained_amount`、`allocation_ratio`
- 当前状态：`stable`

## manual-adjustment-amount

- 中文名：人工调整额
- 标准键：`manual_adjustment_amount`
- 层级：老板层 / 经营层
- 业务定义：**经人工确认后，在利润分账之外额外加减的一笔钱**（一次性补贴、跨月纠错、坏账核销等）。
- 系统统一口径：`finance.monthly_profit_adjustments`（人工调整项表），
  按 `settlement_id` 归属到当月结算单；调整类型见 `adjustment_type`，原因见 `reason`。
- 公式：`Σ 调整行金额`
- ⚠️ **符号约定**：正数 = **减少公司留存**（从利润里再减一笔），负数 = 增加公司留存。
  引用时必须带符号说明，否则「调整 5 万」读不出方向。
- 粒度：月
- 适用：解释「算出来的留存和实际对不上」的差额；核对一次性事项
- 不适用：
  - 当作常规人力成本或利润项（它是人工加的，不是算出来的）
  - 用来抹平差异（差异应回上游查，见 `docs/guides/MONTHLY_PROFIT_SETTLEMENT_RUNBOOK.md`
    的「业务口径变更签字记录」）
  - 单独判断经营质量（金额大小不代表经营好坏）
- 配套指标：`company_retained_amount`、`allocation_ratio`
- 当前状态：`stable`

## company-retained-amount

- 中文名：公司留存
- 标准键：`company_retained_amount`
- 层级：老板层
- 业务定义：**当月利润分完员工、扣完人工调整之后，真正留在公司的钱**。
- 系统统一口径：看板聚合层（在 `finance.shop_profit_basis` 与
  `finance.employee_labor_cost_allocations` 之上做只读汇总，**不落新表**）。
- 公式：`净利润 − 员工侧分配额 − 人工调整额`
  - **净利润** = `Σ 店铺利润基数`（公司级汇总）
- 粒度：月
- 适用：老板层「这个月公司留下多少」；与目标留存对比
- 不适用：
  - 判断单店经营好坏（必须下钻到 `profit_basis_amount` 的店铺粒度）
  - 当作利润（它已经扣了员工分配和人工调整，与利润基数不是一回事）
  - 与历史留存直接比较而不说明口径变更（人员成本口径改过一次，见运行手册签字记录）
- 配套指标：`profit_basis_amount`、`employee_allocation_amount`、`allocation_ratio`、`over_allocation_flag`
- 当前状态：`stable`

## allocation-ratio

- 中文名：分配占比
- 标准键：`allocation_ratio`
- 层级：老板层 / 经营层
- 业务定义：**当月利润里分出去的比例**（员工侧分配额 + 人工调整额占净利润的比例）。
- 系统统一口径：看板聚合层（同 `company_retained_amount`，只读汇总）。
- 公式：`(员工侧分配额 + 人工调整额) ÷ 净利润`
- ⚠️ **分母是净利润**（公司级 `Σ 店铺利润基数`）；
  净利润 ≤ 0 时本指标**无意义**，此时不得给出比例。
- 粒度：月
- 适用：判断「分出去多少」「留存比例是否异常」
- 不适用：
  - 单独判断某个人拿多了（比例是公司级；人级要下钻 `employee_allocation_amount`）
  - 净利润为负或为零时使用（此时比例无意义）
  - 当作提成比例（提成比例是配置项，是另一个东西）
- 配套指标：`company_retained_amount`、`over_allocation_flag`、`employee_allocation_amount`
- 当前状态：`stable`

## over-allocation-flag

- 中文名：超额分配标记
- 标准键：`over_allocation_flag`
- 层级：老板层
- 业务定义：**本月利润被分超了的告警标记**——公司留存为负，或分出去的比例超过 100%。
- 系统统一口径：看板聚合层（由 `company_retained_amount` 与 `allocation_ratio` 判定）。
- 公式：`公司留存 < 0 或 分配占比 > 1`
- 粒度：月
- 适用：让老板一眼看到「这个月分超了」，触发复盘
- 不适用：
  - 当作原因判断（它只说「超了」，不说「为什么超」——可能是比例配置错，也可能是成本录错）
  - 当作自动拦截（看板是只读的，标记只提示，不阻断流程）
  - 逐店判断（它是公司级标记；逐店要下钻）
- 配套指标：`company_retained_amount`、`allocation_ratio`
- 当前状态：`stable`

# 提成与绩效工资口径（2026-11-21 口径归一后登记）

这一组指标来自「提成 / 绩效工资」链路。口径归一后只有**两条轴**：

- **提成**：零系数，分多少给多少；
- **绩效工资**：纯个人分数档位，与店铺排名无关。

⚠️ **命名纪律**（本组指标的硬约束）：

- **「结算系数」是禁用词**。它曾同时影响提成与绩效工资，现在两个口径完全分开，
  再用这个词会让人以为「店铺排名会压低提成」。一律写全称：
  **绩效分数档位系数**（影响绩效工资）/ **赛马评级**（只做考核展示）。
- **「赛马评级」不是金额指标**。禁止出现在任何「×系数 = 金额」的表述里。
- **「绩效系数」** 指 **绩效分数档位系数**（纯个人），不要用来指赛马评级。

## commission-amount

- 中文名：员工提成
- 标准键：`commission_amount`
- 层级：经营层 / 员工层
- 业务定义：**某员工从某家店分到的提成**。
- 系统统一口径：真源模块 `backend/services/commission_caliber.py`（**唯一实现处**）。
  工资单计算、结算预览、店铺维度统计、月度结算单、确认校验全部调它，
  前端**只渲染**后端下发的金额，不复刻公式。
- 公式：`max(店铺可分配利润, 0) × 该员工的归属提成比`
  - 店铺可分配利润 = `max(店铺利润基数, 0) × 店铺可分配利润率`
  - 归属提成比 = `a_class.employee_shop_assignments.commission_ratio`（人工配置，唯一来源）
  - 店铺可分配利润率 = `a_class.shop_commission_config.allocatable_profit_rate`（人工配置，唯一来源）
- ⚠️ **零系数**：店铺赛马评级、个人绩效分数档位**都不参与提成金额**。
  「分多少，给多少」——提成分摊只看利润基数、可分配率、归属提成比三个因子。
- ⚠️ **亏损按 0 处理**：店铺利润基数为负时该店可分配利润为 0，提成为 0
  （不是负提成）。
- 粒度：员工 × 店铺 × 月
- 适用：判断「这个人在这个店这个月分到多少」
- 不适用：
  - 当作「可分配利润」（可分配利润是店铺级中间量）
  - 与「含系数旧口径」的历史数字直接比较（口径已变更，见 ADR-2026-11-21）
  - 单独用它判断门店盈利能力（门店盈利能力看 `profit_basis_amount`）
- 配套指标：`performance-salary-amount`、`performance-score-coefficient`、`ranking-coefficient`
- 当前状态：`stable`

## performance-salary-amount

- 中文名：绩效工资
- 标准键：`performance_salary_amount`
- 层级：经营层 / 员工层
- 业务定义：**员工因个人绩效拿到的工资部分**。
- 系统统一口径：真源模块 `backend/services/commission_caliber.py`
  的 `calculate_employee_performance_salary`。
- 公式：`绩效包金额 × 绩效分数档位系数`
  - 绩效包金额 = `a_class.salary_structures.performance_package_amount`（人工配置，唯一来源）
  - 绩效分数档位系数 = `performance-score-coefficient`（纯个人）
- ⚠️ **纯个人**：绩效工资**只看本人的绩效分数档位**，与店铺排名、逐店结算系数**无关**。
  一个人管几家店，绩效工资只按他本人的分数算一次。
- 粒度：员工 × 月
- 适用：判断「这个人的绩效工资是多少」「绩效分数怎么影响收入」
- 不适用：
  - 当作提成（提成看 `commission-amount`）
  - 当作「绩效包」（绩效包是配置项，是另一个东西）
  - 当作实发工资（实发还要看工资单，含个税等代扣项）
- 配套指标：`performance-score-coefficient`、`ranking-coefficient`、`commission-amount`
- 当前状态：`stable`

## performance-score-coefficient

- 中文名：绩效分数档位系数
- 标准键：`performance_score_coefficient`
- 层级：经营层 / 员工层
- 业务定义：**按个人绩效分数落档得到的系数**——绩效工资乘的就是它。
- 系统统一口径：档位表 SSOT 在 `backend/services/performance_coefficient.py`
  的 `SCORE_BAND_COEFFICIENTS`。
- 档位：`≥90 → 1.2`、`≥80 → 1.0`、`≥70 → 0.9`、`≥60 → 0.8`、`<60 → 0.5`
- 公式：`绩效工资 = 绩效包金额 × 本系数`
- ⚠️ **纯个人**：与店铺排名无关。同一个人在几家店任职，系数都是同一个。
- ⚠️ 只有**绩效工资**用它。它**不参与提成**。
- 粒度：员工 × 月
- 适用：解释「为什么这个人的绩效工资是这个数」
- 不适用：
  - 当作赛马评级（赛马评级是 `ranking-coefficient`，另一个东西）
  - 当作提成系数（提成零系数，没有这回事）
  - 跨人横向比较「谁打绩效更狠」（档位是阶梯，差距会被压缩）
- 配套指标：`performance-salary-amount`、`ranking-coefficient`
- 当前状态：`stable`

## ranking-coefficient

- 中文名：赛马评级系数
- 标准键：`ranking_coefficient`
- 层级：经营层
- 业务定义：**店铺当月在赛马排名池里的名次档位系数**——只做考核、预警与排名展示。
- 系统统一口径：档位表 SSOT 在 `backend/services/performance_coefficient.py`
  的 `RANK_BAND_COEFFICIENTS`；落库字段 `c_class.performance_scores.performance_coefficient`。
- 档位：前 20% → 1.2、前 50% → 1.0、前 80% → 0.9、其余 → 0.8
- ⚠️ **不参与任何金额**：不乘提成、不乘绩效工资。
  页面上的列名必须写全「赛马评级（不参与提成计算）」，避免运营误以为它会压低收入。
- 粒度：店铺 × 月
- 适用：判断「这家店这个月排第几」「要不要预警」
- 不适用：
  - 当作任何金额的因子（这是本条最重要的一条）
  - 当作个人绩效档位（个人看 `performance-score-coefficient`）
  - 跨月直接比较名次（每月池子构成不同）
- 配套指标：`performance-score-coefficient`
- 当前状态：`stable`

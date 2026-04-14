# Platform Mapping

本文件只处理“名字相同但口径可能不同”的指标。

## conversion_rate

- Shopee：以对应卖家后台或导出定义为准
- TikTok：Seller Center 与 Ads Manager 可能存在范围和归因差异
- ERP 统一口径：`order_count / visitor_count * 100`
- 会议决策口径：默认优先 ERP 统一口径；直接引用平台值时必须说明来源

## traffic

- Shopee：常见为访客 / 浏览量拆分
- TikTok：需区分访客、曝光、点击、商品页浏览
- ERP 统一口径：业务概览默认以 `visitor_count` 为主
- 会议决策口径：讨论经营时优先 `traffic=visitor_count`，讨论内容和广告时另行说明 `impressions / clicks / page_views`

## avg_order_value

- Shopee / TikTok：页面可能直接显示客单价，也可能需从 GMV 与订单数反推
- ERP 统一口径：`gmv / order_count`
- 会议决策口径：默认使用 ERP 统一口径

## profit

- 平台原生：不同后台的利润字段可能混合补贴、佣金、活动、费用
- ERP 统一口径：引用时必须说明来自哪个模块
- 会议决策口径：经营复盘可用，但必须配套成本口径说明

## estimated_expenses

- 业务概览经营指标中的 `estimated_expenses` 当前更接近经营费用汇总
- 它不等于广告费，也不等于投放花费
- 讨论营销效率时禁止直接拿 `estimated_expenses` 代替广告成本

## blocked metrics

- `labor_efficiency`
- `roas`
- `mer`
- `repurchase_rate`
- `hero_sku_ratio`

以上指标当前禁止作为会议最终结论使用。

# Platform Mapping

本文档只处理“名字相同但口径可能不同”的指标。

## conversion_rate

- Shopee：平台后台可能展示多种转化率，需区分页面转化、下单转化等
- TikTok：Seller Center 与 Ads Manager 的转化率定义可能不同
- ERP 统一口径：默认按 `order_count / visitor_count * 100`
- 会议决策口径：直接引用平台值时必须明确来源

## traffic

- Shopee：常见拆分为页面浏览、访客、进店等指标
- TikTok：常见拆分为页面浏览次数、店铺访问量、曝光、点击等指标
- ERP 统一口径：**客流量默认以 `page_views` 为主**
- 辅助指标：`visitor_count` 表示实际进入店铺的客户数量
- 会议决策口径：讨论经营时优先 `traffic = page_views`；若讨论进店质量，单独说明 `visitor_count`

## avg_order_value

- Shopee / TikTok：平台页面可能直接展示客单价，也可能需要由 GMV 与订单数反推
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

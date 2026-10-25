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

## dos（可售天数）

同一个「可售天数」，两个来源、两种口径，**不可混用**：

| 口径 | 标准键 | 分母来源 | 新鲜度 | 粒度 | 状态 |
|---|---|---|---|---|---|
| 清单口径 | `checklist_dos_sales30` / `checklist_dos_sales90` | 妙手仓库清单自带的「近30/90天销量数据」列 | **行级存储快照**，只在行被写入时刷新 → 增量下只覆盖约 13.6% 的 SKU | SKU × 仓 | `observe`（**参考值，不作判定依据**） |
| 订单口径 | `order_dos_sales30` / `order_dos_sales90` | ERP 订单成交数量 | 天然新鲜（不受库存行写入影响） | **SKU 级**（订单表无仓库维度） | `blocked` |

两者会不一致的已知原因：

- **退款与取消订单**：清单销量与订单成交数的处理时点不同
- **归属时间窗**：平台后台的销量归属与 ERP 的订单时间窗可能不同
- **时区**：跨时区店铺的日切边界不同
- **采集时点**：清单口径只在**该行最后一次被采集写入时**是真值；增量批次只刷新被采到的行

会议决策口径：

- 引用时必须写全限定名，**不得单独用 `dos` 指代某一个口径**
- **清单口径只作参考**，引用时必须说明「参考值、基于增量采集、非实时动销速度」
- **不得作为最终结论或判定依据**——滞销判据用 `days_since_restock`（距上次进货天数），
  那是事件时刻，增量下始终准确
- 订单口径未打通前，禁止把清单口径的 DOS 说成「实时动销速度」

## blocked metrics

- `labor_efficiency`
- `roas`
- `mer`
- `repurchase_rate`
- `hero_sku_ratio`
- `order_dos_sales30`
- `order_dos_sales90`

以上指标当前禁止作为会议最终结论使用。

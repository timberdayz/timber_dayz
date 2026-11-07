from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

from backend.services.currency_extractor import get_currency_extractor


# ── 口径（caliber）维度 ────────────────────────────────────────────────
#
# 平台报表里同一个指标常带**多套统计口径**, 它们不是措辞差异, 是不同的业务事实:
#
#   * ``placed`` —— 已下单(买家提交了订单, 未必付款)
#   * ``paid``   —— 已付款(买家完成了支付)
#
# 2026-11-08 生产实测(shopee 商品月报, 7090 行可比): 两套口径的销售额
# **平均差 5.15%, 最大差 175.89** ⇒ 绝不能归一化成同一个值, 也不能互相冒充。
#
# 平台还会**改词**(报表改版): shopee 的「已确定订单」是「已下订单」的旧叫法
# (实测两者差 4.25%, 属同一口径的措辞迁移), 由 :data:`PLATFORM_CALIBER_HISTORY` 登记。
#
# 「已确认订单」在真实数据里**没有任何数值**(只作为旧报表遗留列存在),
# 无从判断它对应哪个口径 ⇒ 刻意**不折算**, 宁可落 unknown, 也不猜。
CALIBER_PLACED = "placed"
CALIBER_PAID = "paid"


SEMANTIC_FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "order_id": {
        "label": "订单号",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "required": True,
        "aliases": ["订单号", "订单编号", "order id"],
    },
    "line_id": {
        "label": "订单明细行 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["order_line_id", "line id", "order line id", "明细行ID"],
    },
    "product_id": {
        "label": "商品 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["产品id", "商品id", "产品ID", "商品ID", "product id"],
    },
    "platform_sku": {
        "label": "平台 SKU",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["平台sku", "平台 sku", "product_sku", "产品sku", "商品sku"],
    },
    "sku_id": {
        "label": "SKU 编号",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["sku id", "SKU ID", "SKU编号"],
    },
    "service_id": {
        "label": "服务 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["service id", "服务ID", "服务编号"],
    },
    "shop_id": {
        "label": "店铺 ID",
        "kind": "identity",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "system_scope": True,
        "aliases": ["店铺", "店铺ID", "shop id"],
    },
    "warehouse_name": {
        "label": "仓库",
        "kind": "dimension",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["warehouse", "仓库", "仓库名称", "warehouse name"],
    },
    "gmv_band": {
        "label": "GMV 区间",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["gmv band", "gmv range", "GMV区间", "GMV 区间"],
    },
    "metric_date": {
        "label": "统计日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["日期", "统计日期", "data_date", "date"],
    },
    "period_start_date": {
        "label": "周期开始日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["开始日期", "周期开始日期", "date_from"],
    },
    "period_end_date": {
        "label": "周期结束日期",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["结束日期", "周期结束日期", "date_to"],
    },
    "period_start_time": {
        "label": "周期开始时间",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["开始时间", "小时", "时段", "hour", "time", "start time"],
    },
    "period_end_time": {
        "label": "周期结束时间",
        "kind": "time",
        "domain": "common",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["结束时间", "结束小时", "end hour", "end time"],
    },
    "order_date": {
        "label": "下单日期",
        "kind": "time",
        "domain": "orders",
        "hash_eligible": True,
        "default_hash": False,
        "aliases": ["下单日期", "订单日期", "下单时间"],
    },
    "visitor_count": {
        "label": "访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["访客数", "visitors", "visitor count"],
    },
    "product_visitor_count": {
        "label": "商品访客数",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商品访客数", "product visitors", "product visitor count"],
    },
    "page_views": {
        "label": "浏览量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["浏览量", "pv", "page views", "views"],
    },
    "impressions": {
        "label": "曝光量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["曝光量", "曝光次数", "impression", "impressions"],
    },
    "clicks": {
        "label": "点击量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["点击量", "点击次数", "click", "clicks"],
    },
    "click_rate": {
        "label": "点击率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["点击率", "click rate", "ctr"],
    },
    "conversion_rate": {
        "label": "转化率",
        "kind": "metric",
        "domain": "analytics",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["转化率", "conversion rate", "cvr"],
    },
    "order_count": {
        "label": "订单量",
        "kind": "metric",
        "domain": "analytics",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单量", "订单数", "order count", "orders"],
    },
    "sku_order_count": {
        "label": "SKU 订单量",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["SKU订单量", "sku orders", "sku order count"],
    },
    "gmv": {
        "label": "GMV",
        "kind": "metric",
        "domain": "common",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["GMV"],
    },
    "total_transaction_amount": {
        "label": "总交易金额",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["总交易金额", "total transaction amount"],
    },
    "bounce_rate": {
        "label": "跳失率",
        "kind": "metric",
        "domain": "analytics",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["跳失率", "bounce rate"],
    },
    "sales_amount": {
        "label": "销售额",
        "kind": "metric",
        "domain": "orders",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["sales amount", "sales", "销售额", "销售金额"],
    },
    "sales_volume": {
        "label": "销量",
        "kind": "metric",
        "domain": "orders",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["sales volume", "units sold", "销量", "销售数量"],
    },
    "paid_amount": {
        "label": "实付金额",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["实付金额", "paid amount", "buyer paid amount"],
    },
    "profit": {
        "label": "利润",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["利润", "profit"],
    },
    "purchase_amount": {
        "label": "采购金额",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["采购金额", "purchase amount"],
    },
    "platform_commission": {
        "label": "平台佣金",
        "kind": "metric",
        "domain": "orders",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["平台佣金", "platform commission", "commission"],
    },
    "live_gmv": {
        "label": "直播 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家直播 GMV", "直播GMV", "live gmv"],
    },
    "live_attributed_gmv": {
        "label": "直播归因 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家直播归因 GMV", "直播归因GMV", "live attributed gmv"],
    },
    "live_indirect_gmv": {
        "label": "直播间接 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家直播间接 GMV", "直播间接GMV", "live indirect gmv"],
    },
    "video_gmv": {
        "label": "视频 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家视频 GMV", "视频GMV", "video gmv"],
    },
    "video_attributed_gmv": {
        "label": "视频归因 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家视频归因 GMV", "视频归因GMV", "video attributed gmv"],
    },
    "video_indirect_gmv": {
        "label": "视频间接 GMV",
        "kind": "metric",
        "domain": "attribution",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["商家视频间接 GMV", "视频间接GMV", "video indirect gmv"],
    },
    "product_name": {
        "label": "商品名称",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": False,
        "identity_strength": "weak",
        "hash_warning": "商品名可能重名或改名，优先使用商品 ID / SKU。",
        "aliases": ["item_name", "product name", "item name", "商品", "商品名", "商品名称", "产品名称"],
    },
    "item_status": {
        "label": "商品状态",
        "kind": "attribute",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["product_status", "listing_status", "item status", "product status", "发品状态", "商品状态", "状态"],
    },
    # ── products 域的**口径变体**(2026-11-08 新增) ─────────────────────
    #
    # 平台报表对同一个指标给两套统计口径: 「已下单」与「已付款」。
    # 实测两者销售额平均差 5.15% ⇒ 是不同的业务事实, 必须是两个标准字段,
    # 不能靠别名混成一个。
    #
    # 主口径(``*_paid``)用无后缀的字段名承载(``sales_amount`` 等), 因为
    # 已付款口径与利润/实付字段自洽; 下单口径单独成字段。
    "sales_amount_placed": {
        "label": "销售额（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["销售额（已下单）", "销售额（已下订单）", "销售额（已确定订单）", "下单销售额"],
    },
    "sales_volume_placed": {
        "label": "销量（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["销量（已下单）", "件数（已下单）", "件数（已下订单）", "件数（已确定订单）"],
    },
    "order_count_placed": {
        "label": "订单量（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单量（已下单）", "已下单", "已下订单", "已确定订单"],
    },
    "conversion_rate_placed": {
        "label": "转化率（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["转化率（已下单）", "转化率（已下订单）", "转化率（已确定订单）"],
    },
    "order_conversion_rate_placed": {
        "label": "订单转化率（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单转化率（已下单）", "订单转化率（已下订单）", "订单转化率（已确定订单）"],
    },
    "buyer_count_placed": {
        "label": "买家数（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["买家数（已下单）", "买家数（已下订单）", "买家数（已确定订单）"],
    },
    "aov_placed": {
        "label": "每笔订单销售额（下单口径）",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PLACED,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["每笔订单销售额（已下单）", "每笔订单销售额（已下订单）", "每笔订单销售额（已确定订单）"],
    },
    # ── products 域此前**根本没有落点**的指标(2026-11-08 新增) ─────────
    #
    # 依据: shopee 商品月报 / tiktok 商品月报的真实表头。实测这些指标与
    # 已有字段**数值不同**(例: 同商品同月「转化率」10.56% vs「订单转化率」-),
    # 混用会造成口径错误 ⇒ 各自独立成字段。
    "order_conversion_rate": {
        "label": "订单转化率",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["订单转化率", "订单转化率（已付款订单）", "订单转化率（已下订单）"],
    },
    "unique_impressions": {
        "label": "去重商品曝光量",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["不重复的商品曝光量", "去重商品曝光次数", "去重商品曝光次数（视频）", "商品曝光次数.1"],
    },
    "unique_clicks": {
        "label": "去重点击量",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["不重复的商品点击量", "去重点击次数", "去重点击次数.1", "去重点击次数（视频）"],
    },
    "buyer_count": {
        "label": "买家数",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["买家数（已付款订单）", "买家数（已下订单）", "买家数（已确定订单）"],
    },
    "aov": {
        "label": "每笔订单销售额",
        "kind": "metric",
        "domain": "products",
        "caliber": CALIBER_PAID,
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["每笔订单销售额（已付款订单）", "每笔订单销售额（已下订单）", "每笔订单销售额"],
    },
    "add_to_cart_count": {
        "label": "加购件数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["加购次数", "加购次数.1", "加购次数（直播）", "加购次数（视频）"],
    },
    "add_to_cart_user_count": {
        "label": "加购用户数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["已加购的用户数", "已加购的用户数.1", "已加购的用户数（直播）", "已加购的用户数（视频）"],
    },
    "add_to_cart_rate": {
        "label": "加购率",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["加购率", "加购率.1", "加购率（直播）", "加购率（视频）", "去重加购率"],
    },
    "refund_amount": {
        "label": "退款金额",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["退款金额", "退款额"],
    },
    "refunded_item_count": {
        "label": "退款商品件数",
        "kind": "metric",
        "domain": "products",
        "hash_eligible": False,
        "default_hash": False,
        "aliases": ["已退款的商品件数", "退款商品件数"],
    },
    # ── 渠道维度(tiktok 商品报表按商城/直播/视频/商品卡分块) ──────────
    "channel": {
        "label": "渠道",
        "kind": "dimension",
        "domain": "products",
        "hash_eligible": True,
        "default_hash": True,
        "aliases": ["渠道", "channel", "商城页", "直播", "视频", "商品卡"],
    },
}

SEMANTIC_FIELD_ALIASES = {
    key: list(dict.fromkeys([key, *(definition.get("aliases") or [])]))
    for key, definition in SEMANTIC_FIELD_DEFINITIONS.items()
}

#: [*] 批次 E(E-4 / 规格 D1): 指标类字段参与去重的后果提示。
METRIC_HASH_WARNING = (
    "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。"
    "确认「这一行的身份就包含这个指标」再勾选。"
)

# [*] 批次 E(E-4 / 规格 D1): 指标类字段**不再禁止**参与 data_hash。
#
# 以前这里对 ``kind == "metric"`` 硬性拒绝, 理由是「度量不是行身份」。
# 那与业务概念直接冲突: 业务上「日期 + 订单数 + 店铺 = 这一行是什么」
# 是**复合业务键**, 不是实体身份。
#
# 现在统一放开:
#   * ``hash_eligible`` —— 允许(能不能用由用户在模板里勾选决定);
#   * ``default_hash`` —— 仍然是 False(不默认参与, 保持旧行为);
#   * ``hash_warning`` —— 带上后果提示, 让用户知道「指标变了会被当成新行」。
for _metric_key, _metric_meta in SEMANTIC_FIELD_DEFINITIONS.items():
    if _metric_meta.get("kind") == "metric":
        _metric_meta["hash_eligible"] = True
        _metric_meta.setdefault("hash_warning", METRIC_HASH_WARNING)

SEMANTIC_FIELD_META = {
    key: {meta_key: meta_value for meta_key, meta_value in definition.items() if meta_key != "aliases"}
    for key, definition in SEMANTIC_FIELD_DEFINITIONS.items()
}


#: 每个标准字段的说明文案(前端下拉框/tooltip 用)。
#:
#: [*] 批次 D: 以前这份文案住在前端 ``headerBindings.js`` 的副本里,
#:     后端这边没有 ⇒ 后端接口返回的字段没有描述, 前端只能自己抄一份。
#:     现在文案回到后端, 与字段定义放在一起, 一起作为唯一口径。
SEMANTIC_FIELD_DESCRIPTIONS: Dict[str, str] = {
    "order_id": "识别同一笔订单的稳定身份字段。",
    "product_id": "平台或系统内识别同一商品的稳定身份字段。",
    "platform_sku": "平台侧商品规格编码，可作为商品身份字段。",
    "sku_id": "订单明细或商品规格粒度的身份字段。",
    "line_id": "订单明细行粒度的稳定身份字段。",
    "service_id": "服务类数据的稳定身份字段。",
    "shop_id": "系统自动加入 Data Hash 的店铺作用域字段。",
    "warehouse_name": "库存快照区分仓库粒度的维度字段。",
    "gmv_band": "按 GMV 区间出报表时可作为行粒度维度。",
    "metric_date": "日/周/月报表定位业务周期的时间字段。",
    "period_start_date": "区间型报表的开始日期。",
    "period_end_date": "区间型报表的结束日期。",
    "order_date": "订单发生日期，通常作为分析维度。",
    "product_name": "弱身份字段。商品名可能重名或改名，优先使用商品 ID / SKU。",
    "item_status": "标准化属性字段，状态变化不应默认改变 Data Hash。",
    # ── products 域的口径变体与新增指标(2026-11-08) ─────────────────
    "sales_amount_placed": "销售额（下单口径）。与「已付款口径」平均差 5.15%，不可混用。",
    "sales_volume_placed": "销量（下单口径）。与「已付款口径」不可混用。",
    "order_count_placed": "订单量（下单口径）。与「已付款口径」不可混用。",
    "conversion_rate_placed": "转化率（下单口径）。与「已付款口径」不可混用。",
    "order_conversion_rate_placed": "订单转化率（下单口径）。与商品转化率是不同指标。",
    "buyer_count_placed": "买家数（下单口径）。与「已付款口径」不可混用。",
    "aov_placed": "每笔订单销售额（下单口径）。与「已付款口径」不可混用。",
    "order_conversion_rate": "订单转化率。与商品转化率是不同指标，不可混用。",
    "unique_impressions": "去重商品曝光量。与商品展示量（曝光次数）是不同指标。",
    "unique_clicks": "去重点击量。与商品点击量（点击次数）是不同指标。",
    "buyer_count": "买家数。已付款口径。",
    "aov": "每笔订单销售额。已付款口径。",
    "add_to_cart_count": "加购件数。",
    "add_to_cart_user_count": "加购用户数。",
    "add_to_cart_rate": "加购率。",
    "refund_amount": "退款金额。",
    "refunded_item_count": "退款商品件数。",
    "channel": "渠道维度。tiktok 商品报表按商城/直播/视频/商品卡分块。",
    "gmv": "指标值，不参与 Data Hash。",
    "sales_amount": "指标值，不参与 Data Hash。",
    "sales_volume": "指标值，不参与 Data Hash。",
    "order_count": "指标值，不参与 Data Hash。",
    "period_start_time": "小时级或更细粒度报表的开始时间，可由用户手动加入 Data Hash。",
    "period_end_time": "小时级或更细粒度报表的结束时间，可由用户手动加入 Data Hash。",
    "visitor_count": "系统语义指标，不参与 Data Hash。",
    "product_visitor_count": "系统语义指标，不参与 Data Hash。",
    "page_views": "系统语义指标，不参与 Data Hash。",
    "impressions": "系统语义指标，不参与 Data Hash。",
    "clicks": "系统语义指标，不参与 Data Hash。",
    "click_rate": "系统语义指标，不参与 Data Hash。",
    "conversion_rate": "系统语义指标，不参与 Data Hash。",
    "sku_order_count": "系统语义指标，不参与 Data Hash。",
    "total_transaction_amount": "系统语义指标，不参与 Data Hash。",
    "bounce_rate": "系统语义指标，不参与 Data Hash。",
    "paid_amount": "系统语义指标，不参与 Data Hash。",
    "profit": "系统语义指标，不参与 Data Hash。",
    "purchase_amount": "系统语义指标，不参与 Data Hash。",
    "platform_commission": "系统语义指标，不参与 Data Hash。",
    "live_gmv": "渠道归因系统语义指标，不参与 Data Hash。",
    "live_attributed_gmv": "渠道归因系统语义指标，不参与 Data Hash。",
    "live_indirect_gmv": "渠道归因系统语义指标，不参与 Data Hash。",
    "video_gmv": "渠道归因系统语义指标，不参与 Data Hash。",
    "video_attributed_gmv": "渠道归因系统语义指标，不参与 Data Hash。",
    "video_indirect_gmv": "渠道归因系统语义指标，不参与 Data Hash。",
}


#: hash 的「系统作用域」字段 —— 它们来自采集上下文, 不是文件里的列。
#:
#: 前端以前自己抄了一份这个列表(``headerBindings.js``), 后端在
#: ``field_mapping_templates.py`` 又抄了一份 ⇒ 三份口径。
#: 现在统一到这里。
SYSTEM_HASH_SCOPE_KEYS = frozenset(
    {"platform_code", "shop_id", "data_domain", "granularity", "sub_domain"}
)


# 域限定的「列名 → 语义键」映射。
#
# 为什么不能写进全局别名表
# ----------------------
# 全局别名表对所有数据域一视同仁，但同一个列名在不同域含义不同：
#   - ``ID`` 在 products 域是商品 ID，放到全局表会让别的域的 ``ID`` 也被当成商品身份；
#   - ``客服ID`` 在 services 域是客服（服务人员）ID，在别的域不是。
# 写进全局表 = 跨域污染，别的域的同名列被误提升成语义身份。
#
# 为什么这样做是安全的
# ------------------
# 1. 只在**对应数据域内**生效，别的域完全不受影响；
# 2. 命中结果只标记 ``semantic_review_source=inferred``（系统按列名推断，不是用户确认），
#    家族 hash 一致性比较仍然只认用户确认过的绑定
#    （见 ``field_mapping_templates._binding_lookup_by_source``），
#    所以第 3 批修掉的「假一致」不会被重新制造出来。
#
# 表里的列名全部来自真实源文件的表头（catalog 文件的 header_columns），
# 不做猜测性扩展；拿不准含义的列（状态类、名称类、货号类）一律不映射。
DOMAIN_COLUMN_SEMANTIC_OVERRIDES: Dict[str, Dict[str, str]] = {
    "products": {
        # Shopee 商品维度导出：商品编号 = Item ID
        "商品编号": "product_id",
        # TikTok 商品维度导出：商品 ID / ID
        "商品 id": "product_id",
        "id": "product_id",
        # Shopee 商品维度导出：规格编号 = 规格(SKU) ID
        "规格编号": "sku_id",
    },
    "services": {
        # 客服维度报表：客服ID = 服务人员 ID
        "客服id": "service_id",
        "客服编号": "service_id",
        # 客服维度报表的周期列：值形如 "01-06-2026 - 21-06-2026"。
        # 一个文件只有一个周期行，且**文件名里带的是采集时间、不是周期**，
        # 所以这个单元格是文件里唯一权威的周期来源 ⇒ 必须进 hash，
        # 否则下一期报表会算出同一个 hash，把上一期的行覆盖掉。
        "日期期间": "metric_date",
    },
    "inventory": {
        # 妙手库存导出：带 * 的是必填列
        "*商品sku": "platform_sku",
        "*商品名称": "product_name",
    },
}


# ── 域限定的「业务别名 → 语义键」映射 ──────────────────────────────
#
# [*] 批次 D: 这两张表以前住在 ``semantic_field_contract_service``,
#     但那里的别名**只被契约判定用**, 从没进过「列名 → 语义键」的推断链路 ——
#     于是「页面浏览数」明明有别名(page_views), 推断时却认不出来。
#     现在统一搬到注册表(唯一口径), 推断与契约共用同一份。
ORDER_SEMANTIC_ALIASES: Dict[str, tuple[str, ...]] = {
    "order_id": ("订单编号", "订单号", "order_id", "order no", "order_no", "order id"),
    "shop_id": ("店铺", "店铺id", "shop_id", "shop id", "shop_name", "shop name"),
    "order_date": ("下单时间", "下单日期", "订单日期", "订单时间", "order_date", "order time", "order_time"),
    "sales_volume": ("销售数量", "出库数量", "销量", "sold_qty", "sales_volume", "quantity"),
    "paid_amount": (
        "买家支付",
        "买家支付(rmb)",
        "买家支付（rmb）",
        "实付金额",
        "buyer_paid",
        "paid_amount",
    ),
    "profit": ("利润", "利润(rmb)", "利润（rmb）", "profit", "profit_amount", "profit_rmb"),
    "estimated_settlement_amount": (
        "预估回款金额",
        "预估回款金额(rmb)",
        "预估回款金额（rmb）",
        "estimated_settlement",
        "estimated_settlement_amount",
    ),
    "settlement_time": ("结算时间", "settlement_time", "settlement date"),
    "cost_profit_rate": ("成本利润率", "cost_profit_rate"),
}


# [*] analytics(流量)域的中文表头别名。
# 用途: 让语义契约能从**平台原始表头**推断出语义键, 而不是只依赖模板里
# 人工填写的 header_bindings。
# 背景: 已发布模板里 header_bindings 的 semantic_key 覆盖率极低
# (tiktok/analytics 71 个绑定只有 12 个有 semantic_key), 导致 required 语义键
# 根本解析不出来 -> 契约状态恒为 breaking_drift(哪怕文件与模板 100% 一致)。
ANALYTICS_SEMANTIC_ALIASES: Dict[str, tuple[str, ...]] = {
    "metric_date": ("日期", "统计日期", "交易日期", "日期时间", "date"),
    "shop_id": ("店铺", "店铺id", "店铺名称", "shop_id", "shop id"),
    "visitor_count": ("商品访客数", "访客数", "访客量", "访问用户数", "uv"),
    "page_views": ("页面浏览次数", "页面浏览量", "页面浏览数", "商品浏览量", "浏览量", "pv"),
    "conversion_rate": ("转化率", "conversion_rate"),
    "order_count": ("订单数", "支付订单数", "成交订单数", "order_count"),
    "gmv": ("gmv", "成交金额", "成交额", "交易额"),
}


#: [*] products 域的业务别名 —— 2026-11-08 按**真实表头**登记。
#:
#: 依据: shopee / tiktok 商品报表的真实表头(``b_class.fact_*_products_*`` 的
#: ``raw_data`` key 与结构化列)。此前 products 域**没有任何**域别名,
#: 而全局别名表里只有「销售额」「曝光次数」这类**裸名**, 与真实表头
#: (「销售额（已付款订单） (SGD)」/「商品曝光次数.1」)完全对不上
#: ⇒ 语义层命中率 0/45。
#:
#: 口径列**成对登记**(:data:`CALIBER_PAID` / :data:`CALIBER_PLACED`),
#: 绝不把两套口径登记到同一个标准字段 —— 实测两者销售额平均差 5.15%。
#:
#: 「已确认订单」在真实数据里没有任何数值, 无从判断它对应哪个口径
#: ⇒ 这里**不登记**它(宁可缺, 也不猜); 只登记「已确定订单」到 placed
#: (有实测支撑: 与「已下订单」差 4.25%, 属同一口径的措辞迁移)。
PRODUCTS_SEMANTIC_ALIASES: Dict[str, tuple[str, ...]] = {
    # ── 身份维度 ──
    "product_id": ("商品编号", "商品 ID", "商品ID", "ID"),
    "product_name": ("商品", "商品名"),
    "item_status": ("Current Item Status", "状态", "发品状态"),
    "sku_id": ("规格编号",),
    # ── 已付款口径(主口径) ──
    "order_count": ("已付款订单",),
    "sales_amount": ("销售额（已付款订单）",),
    "sales_volume": ("件数（已付款订单）",),
    "conversion_rate": ("转化率（已付款订单）",),
    "order_conversion_rate": ("订单转化率（已付款订单）",),
    "buyer_count": ("买家数（已付款订单）",),
    "aov": ("每笔订单销售额（已付款订单）",),
    # ── 已下单口径 ──
    "order_count_placed": ("已下订单",),
    "sales_amount_placed": ("销售额（已下订单）", "销售额（已确定订单）"),
    "sales_volume_placed": ("件数（已下订单）", "件数（已确定订单）"),
    "conversion_rate_placed": ("转化率（已下订单）", "转化率（已确定订单）"),
    "order_conversion_rate_placed": ("订单转化率（已下订单）", "订单转化率（已确定订单）"),
    "buyer_count_placed": ("买家数（已下订单）", "买家数（已确定订单）"),
    "aov_placed": ("每笔订单销售额（已下订单）", "每笔订单销售额（已确定订单）"),
    # ── 流量指标(无口径) ──
    "impressions": ("商品展示量",),
    "unique_impressions": ("不重复的商品曝光量",),
    "clicks": ("商品点击量",),
    "unique_clicks": ("不重复的商品点击量",),
    "product_visitor_count": ("商品访客数量",),
    "page_views": ("商品页面访问量",),
    "bounce_rate": ("商品跳出率",),
}


DOMAIN_SEMANTIC_ALIASES: Dict[str, Dict[str, tuple[str, ...]]] = {
    "orders": ORDER_SEMANTIC_ALIASES,
    "analytics": ANALYTICS_SEMANTIC_ALIASES,
    "products": PRODUCTS_SEMANTIC_ALIASES,
}


# ── 语义归一化 ─────────────────────────────────────────────────────
#
# 为什么需要归一化
# ----------------
# 真实表头不是干净的标识符, 而是「业务名 + 修饰」:
#
#   "买家支付(RMB)"  vs  "买家支付"      ← 币种后缀, 同一个指标
#   "利润（rmb）"    vs  "利润(RMB)"      ← 全角/半角括号
#   "商品SKU"       vs  "商品 sku"      ← 空格
#   "下单时间\n"     vs  "下单时间"      ← 换行(妙手导出)
#   "*商品sku"      vs  "商品SKU"        ← 必填星号
#
# 以前匹配是**逐字相等**, 这些全都认不出来 ⇒ 命中率只有 3~6%。
# 归一化之后, 同一个指标的各种写法会收敛到同一个键。
#
# 注意: 归一化**只用于匹配**, 原始列名一律保留在 raw_data 里 ——
# 归一化不是为了改数据, 是为了让「同一个意思」能被认出来。
_CURRENCY_SUFFIX_PATTERN = re.compile(
    r"[（(]\s*[A-Za-z]{3}\s*[)）]\s*$"
)
_CURRENCY_NO_PAREN_PATTERN = re.compile(
    r"[（(][^（()）]{0,12}[)）]\s*$"
)
_FULLWIDTH_PUNCTUATION = {
    "（": "(",
    "）": ")",
    "：": ":",
    "，": ",",
    "、": ",",
    "。": ".",
    "％": "%",
    "＋": "+",
    "－": "-",
    "／": "/",
    "＿": "_",
}


def normalize_semantic_alias(value: Optional[str]) -> str:
    """把列名/别名归一化成「可比较」的形态。

    归一化步骤(顺序固定):

    1. 去首尾空白;
    2. 全角标点 → 半角;
    3. 去掉末尾的币种/币种名称括号后缀(``(RMB)`` / ``（美元）``);
    4. 去掉所有空白(含换行、全角空格);
    5. 去掉下划线;
    6. 去掉必填星号(``*``);
    7. 去掉末尾的 ``.N`` 序号后缀(Excel 多级表头展开后的重名列);
    8. 大小写折叠。

    Returns:
        归一化后的字符串; 空值返回空字符串。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    for source, target in _FULLWIDTH_PUNCTUATION.items():
        text = text.replace(source, target)
    # 末尾括号内容如果是「币种/币种名称」, 视为同一个指标的币种变体
    match = _CURRENCY_SUFFIX_PATTERN.search(text)
    if not match:
        match = _CURRENCY_NO_PAREN_PATTERN.search(text)
        if match:
            inner = match.group(0).strip("()").strip()
            # 只有「像币种」的才剥: 3 个字母, 或含「元/币/美元/人民币」等
            is_currency_like = bool(re.fullmatch(r"[A-Za-z]{3}", inner)) or bool(
                re.search(r"(元|币|美元|人民币|美金|欧元|日元)", inner)
            )
            if not is_currency_like:
                match = None
    if match:
        text = text[: match.start()].strip()
    text = text.replace("*", "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("_", "")
    # 末尾的 ".N" 序号后缀 —— Excel 多级表头展开后的重名列产物
    # (例: tiktok 商品报表的 "商品曝光次数.1" / "GMV.2" / "CTOR(SKU 订单).3"),
    # 与基础列是**同一个指标**, 只是多块表里各出现了一次。
    text = re.sub(r"\.\d+$", "", text)
    return text.strip().lower()


# ── 口径（caliber）维度 ────────────────────────────────────────────────
#
# 平台报表里同一个指标常带**多套统计口径**, 它们不是措辞差异, 是不同的业务事实:
#
#   * ``placed`` —— 已下单(买家提交了订单, 未必付款)
#   * ``paid``   —— 已付款(买家完成了支付)
#
# 2026-11-08 生产实测(shopee 商品月报, 7090 行可比): 两套口径的销售额
# **平均差 5.15%, 最大差 175.89** ⇒ 绝不能归一化成同一个值, 也不能互相冒充。
#
# 平台还会**改词**(报表改版): shopee 的「已确定订单」是「已下订单」的旧叫法
# (实测两者差 4.25%, 属同一口径的措辞迁移), 由 :data:`PLATFORM_CALIBER_HISTORY` 登记。
#
# 「已确认订单」在真实数据里**没有任何数值**(只作为旧报表遗留列存在),
# 无从判断它对应哪个口径 ⇒ 刻意**不折算**, 宁可落 unknown, 也不猜。

#: 平台口径沿革: 平台 → {旧口径词: 当前口径词}
PLATFORM_CALIBER_HISTORY: Dict[str, Dict[str, str]] = {
    "shopee": {
        "已确定订单": "已下单",
    },
}


def apply_caliber_history(normalized: str, platform_code: Optional[str] = None) -> str:
    """把归一化后的列名里的**旧口径词**换成当前口径词。

    沿革表按平台登记 —— 同一个词在不同平台的沿革不一定一样。
    没有登记沿革的平台, 原样返回(不做任何猜测)。
    """
    if not normalized:
        return ""
    history = PLATFORM_CALIBER_HISTORY.get(str(platform_code or "").strip().lower())
    if not history:
        return normalized
    for legacy_word, current_word in history.items():
        if legacy_word in normalized:
            normalized = normalized.replace(legacy_word, current_word)
    return normalized


def _build_normalized_alias_index() -> Dict[str, str]:
    """全局别名表的归一化索引: 归一化别名 → 语义键。

    冲突(同一个归一化别名指向两个语义键)时**保留先注册的那个**,
    并且不静默 —— 冲突会被 :mod:`backend.services.semantic_alias_registry_service`
    检出并落 ``conflict`` + 报警。
    """
    index: Dict[str, str] = {}
    for semantic_key, aliases in SEMANTIC_FIELD_ALIASES.items():
        for alias in aliases:
            normalized = normalize_semantic_alias(alias)
            if normalized and normalized not in index:
                index[normalized] = semantic_key
    return index


def _caliber_variants(normalized: str) -> set[str]:
    """返回归一化文本在**各平台口径沿革**下的等价形态集合。

    平台报表改版会换口径词(shopee: 「已确定订单」→「已下单」)。同一个指标的
    新词与旧词必须能互相命中, 否则平台一改版, 语义层就整体失配。

    展开方向是**双向**的: 当前词 -> 旧词形态, 旧词 -> 当前词形态。

    只在**域限定别名表**里展开 —— 全局别名表展开会造成跨域污染。
    """
    if not normalized:
        return set()
    variants = {normalized}
    for history in PLATFORM_CALIBER_HISTORY.values():
        for legacy_word, current_word in history.items():
            if current_word in normalized:
                variants.add(normalized.replace(current_word, legacy_word))
            if legacy_word in normalized:
                variants.add(normalized.replace(legacy_word, current_word))
    return variants


def _build_normalized_domain_alias_index() -> Dict[str, Dict[str, str]]:
    """域限定别名的归一化索引。

    别名除了自身形态, 还会登记**口径沿革**下的等价形态
    (见 :func:`_caliber_variants`) —— 平台改口径词时不必再手工补别名。
    """
    result: Dict[str, Dict[str, str]] = {}
    for domain, alias_map in DOMAIN_SEMANTIC_ALIASES.items():
        bucket: Dict[str, str] = {}
        for semantic_key, aliases in alias_map.items():
            for alias in aliases:
                normalized = normalize_semantic_alias(alias)
                if not normalized:
                    continue
                for variant in _caliber_variants(normalized):
                    if variant not in bucket:
                        bucket[variant] = semantic_key
        result[domain] = bucket
    return result


def _build_normalized_column_override_index() -> Dict[str, Dict[str, str]]:
    """域限定列名表的归一化索引。"""
    result: Dict[str, Dict[str, str]] = {}
    for domain, mapping in DOMAIN_COLUMN_SEMANTIC_OVERRIDES.items():
        bucket: Dict[str, str] = {}
        for column, semantic_key in mapping.items():
            normalized = normalize_semantic_alias(column)
            if normalized and normalized not in bucket:
                bucket[normalized] = semantic_key
        result[domain] = bucket
    return result


_NORMALIZED_ALIAS_INDEX = _build_normalized_alias_index()
_NORMALIZED_DOMAIN_ALIAS_INDEX = _build_normalized_domain_alias_index()
_NORMALIZED_COLUMN_OVERRIDE_INDEX = _build_normalized_column_override_index()


# ── 运行时别名(来自 semantic.semantic_field_aliases) ─────────────────
#
# [*] 批次 D: 表里本来就有 75 条别名(products 域的「销售额」「曝光次数」
# 「点击次数」「转化率」「商品成交件数」…), 但 ORM 侧**没有模型**,
# Python 侧压根看不见这张表 ⇒ 这些别名从来没进过推断链路。
#
# 现在把它们加载进来, 并且按来源分优先级:
#   * 用户确认过(manual / template_confirmed) —— **最高**, 一处生效;
#   * 内置(builtin) —— 次之, 不覆盖代码里的 curated 表。
_RUNTIME_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}
_RUNTIME_CONFIRMED_ALIAS_INDEX: Dict[str, Dict[str, str]] = {}
_RUNTIME_ALIAS_LOADED = False

#: 全局别名用的域占位符
GLOBAL_ALIAS_DOMAIN = "*"


def _runtime_alias_bucket(index: Dict[str, Dict[str, str]], domain: str) -> Dict[str, str]:
    """取「域内 + 全局」的合并视图(域内优先)。"""
    merged: Dict[str, str] = {}
    merged.update(index.get(GLOBAL_ALIAS_DOMAIN, {}))
    merged.update(index.get(domain, {}))
    return merged


async def load_runtime_aliases(db) -> int:
    """把 ``semantic.semantic_field_aliases`` 的有效别名加载进推断索引。

    只加载 ``status='active'`` 的行 —— ``conflict`` 与 ``disabled``
    的行**不进**推断(冲突必须先裁决, 否则等于替用户拍板)。

    Returns:
        加载进来的别名条数。
    """
    global _RUNTIME_ALIAS_INDEX, _RUNTIME_CONFIRMED_ALIAS_INDEX, _RUNTIME_ALIAS_LOADED

    builtin_bucket: Dict[str, Dict[str, str]] = {}
    confirmed_bucket: Dict[str, Dict[str, str]] = {}

    try:
        from modules.core.db import SemanticFieldAlias
        from sqlalchemy import select

        result = await db.execute(
            select(SemanticFieldAlias).where(SemanticFieldAlias.status == "active")
        )
        rows = list(result.scalars().all())
    except Exception:  # noqa: BLE001 - 表不存在/连不上时不阻断应用
        _RUNTIME_ALIAS_LOADED = True
        return 0

    for row in rows:
        domain = str(getattr(row, "data_domain", "") or "").strip().lower() or GLOBAL_ALIAS_DOMAIN
        semantic_key = str(getattr(row, "standard_field", "") or "").strip()
        raw_alias = str(getattr(row, "raw_alias", "") or "").strip()
        source = str(getattr(row, "source", "") or "").strip()
        if not semantic_key or not raw_alias:
            continue
        if not is_canonical_semantic_key(semantic_key):
            continue
        normalized = normalize_semantic_alias(raw_alias)
        if not normalized:
            continue
        bucket = confirmed_bucket if source in {"manual", "template_confirmed"} else builtin_bucket
        bucket.setdefault(domain, {}).setdefault(normalized, semantic_key)

    _RUNTIME_ALIAS_INDEX = builtin_bucket
    _RUNTIME_CONFIRMED_ALIAS_INDEX = confirmed_bucket
    _RUNTIME_ALIAS_LOADED = True
    total = sum(len(item) for item in builtin_bucket.values()) + sum(
        len(item) for item in confirmed_bucket.values()
    )
    return total


def runtime_alias_snapshot() -> Dict[str, Dict[str, str]]:
    """当前生效的运行时别名快照(给接口与测试用)。"""
    return {
        "builtin": {domain: dict(items) for domain, items in _RUNTIME_ALIAS_INDEX.items()},
        "confirmed": {
            domain: dict(items) for domain, items in _RUNTIME_CONFIRMED_ALIAS_INDEX.items()
        },
        "loaded": _RUNTIME_ALIAS_LOADED,
    }


def runtime_alias_count() -> int:
    return sum(len(item) for item in _RUNTIME_ALIAS_INDEX.values()) + sum(
        len(item) for item in _RUNTIME_CONFIRMED_ALIAS_INDEX.values()
    )

SEMANTIC_HASH_IDENTITY_KEYS = {
    key for key, meta in SEMANTIC_FIELD_META.items() if meta.get("hash_eligible")
}

# 语义复核状态取值
REVIEW_STATUS_CONFIRMED_SEMANTIC = "confirmed_semantic"
REVIEW_STATUS_CONFIRMED_NON_SEMANTIC = "confirmed_non_semantic"
REVIEW_STATUS_PENDING = "pending"

# 语义复核状态**来源**：区分「用户明确确认」与「系统按表头名推断」。
#
# 为什么需要这个区分：
# 历史绑定里只要推断出了 semantic_key 就会被标成 confirmed_semantic，
# 于是「产品ID」这种中文列名也会被当成 product_id 身份，
# 与真正写成 product_id 的模板判成「口径一致」⇒ 假一致。
# 只有用户明确点过确认的绑定，才允许被提升成语义身份。
REVIEW_SOURCE_USER = "user"
REVIEW_SOURCE_INFERRED = "inferred"


def normalize_semantic_key(value: Optional[str]) -> Optional[str]:
    """把任意写法归一化成**规范语义键**。

    [*] 批次 D: 两级匹配。

    1. **逐字相等**(旧口径): 直接命中别名表 —— 保证老数据行为不变;
    2. **归一化相等**(新口径): 去掉币种后缀/空格/下划线/星号/全角标点后再比 ——
       这是命中率从 3~6% 提到 60%+ 的关键。

    归一化后仍然认不出来 ⇒ 返回小写原文(不猜)。
    """
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in SEMANTIC_FIELD_ALIASES:
        return lowered

    for semantic_key, aliases in SEMANTIC_FIELD_ALIASES.items():
        if lowered == semantic_key:
            return semantic_key
        if any(lowered == str(alias).strip().lower() for alias in aliases):
            return semantic_key

    # [*] 批次 D: 归一化匹配
    normalized = normalize_semantic_alias(text)
    if normalized:
        matched = _NORMALIZED_ALIAS_INDEX.get(normalized)
        if matched:
            return matched

    return lowered


def is_canonical_semantic_key(value: Optional[str]) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and text in SEMANTIC_FIELD_ALIASES


def is_hash_identity_semantic_key(value: Optional[str]) -> bool:
    normalized = normalize_semantic_key(value)
    return bool(normalized) and normalized in SEMANTIC_HASH_IDENTITY_KEYS


def resolve_binding_review_status(binding: Optional[Dict[str, Any]]) -> str:
    """返回一条字段绑定的语义复核状态。

    这是读写两侧判定"绑定是否已确认"的唯一来源，避免同一个绑定
    在保存闸门、hash 闸门、读取展示三处得到不同结论。

    规则：
    - 显式带 ``semantic_review_status`` 时以它为准；
    - 历史数据里没有该字段、但已经推断出 ``semantic_key`` 的绑定，
      按迁移期兼容口径视为已确认；
    - 其余情况一律视为待复核。
    """
    if not binding:
        return REVIEW_STATUS_PENDING
    status = str(binding.get("semantic_review_status") or "").strip()
    if status:
        return status
    if normalize_semantic_key(binding.get("semantic_key")):
        return REVIEW_STATUS_CONFIRMED_SEMANTIC
    return REVIEW_STATUS_PENDING


def is_confirmed_semantic_binding(binding: Optional[Dict[str, Any]]) -> bool:
    return resolve_binding_review_status(binding) == REVIEW_STATUS_CONFIRMED_SEMANTIC


def parse_rule_provided_semantic_keys(
    field_parse_rules: Optional[Iterable[Dict[str, Any]]],
) -> set[str]:
    """解析规则能够提供数据来源的语义键集合。

    只要存在一条解析规则产出该语义键，就认为它有数据来源，
    因此不再要求它必须同时具备 confirmed 绑定。
    """
    provided: set[str] = set()
    for rule in field_parse_rules or []:
        if not isinstance(rule, dict):
            continue
        semantic_key = normalize_semantic_key(
            rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
        )
        if semantic_key and is_canonical_semantic_key(semantic_key):
            provided.add(semantic_key)
    return provided


def get_semantic_field_meta(semantic_key: Optional[str]) -> dict[str, Any]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return {}
    meta = SEMANTIC_FIELD_META.get(normalized, {})
    return {"semantic_key": normalized, **meta} if meta else {}


def infer_semantic_key(*values: Optional[str]) -> Optional[str]:
    for value in values:
        normalized = normalize_semantic_key(value)
        if normalized in SEMANTIC_FIELD_ALIASES:
            return normalized
    return None


def infer_semantic_key_for_domain(
    data_domain: Optional[str],
    *values: Optional[str],
) -> Optional[str]:
    """按数据域推断列名对应的语义键。

    [*] 批次 D: 三级查找, 先具体后通用, 每一级都做**归一化**匹配。

    1. **域限定列名表**(:data:`DOMAIN_COLUMN_SEMANTIC_OVERRIDES`)
       —— 同一个列名在不同域含义不同, 所以域内优先;
    2. **域限定别名表**(:data:`DOMAIN_SEMANTIC_ALIASES`)
       —— 域内业务别名(「买家支付」→ ``paid_amount``);
    3. **全局别名表**(:data:`SEMANTIC_FIELD_ALIASES`)。

    这样既能让 ``商品编号`` / ``ID`` / ``客服ID`` 这类真实表头被认出来,
    又不会把「同名列不同含义」污染到别的数据域。
    """
    domain = str(data_domain or "").strip().lower()
    override_index = _NORMALIZED_COLUMN_OVERRIDE_INDEX.get(domain, {})
    if override_index:
        for value in values:
            normalized = normalize_semantic_alias(value)
            if not normalized:
                continue
            target = override_index.get(normalized)
            if target and is_canonical_semantic_key(target):
                return target

    # [*] 批次 D: 用户确认过的全局别名 —— 优先级最高(一处生效)。
    if _RUNTIME_CONFIRMED_ALIAS_INDEX:
        confirmed = _runtime_alias_bucket(_RUNTIME_CONFIRMED_ALIAS_INDEX, domain)
        if confirmed:
            for value in values:
                normalized = normalize_semantic_alias(value)
                if not normalized:
                    continue
                target = confirmed.get(normalized)
                if target and is_canonical_semantic_key(target):
                    return target

    domain_alias_index = _NORMALIZED_DOMAIN_ALIAS_INDEX.get(domain, {})
    if domain_alias_index:
        for value in values:
            normalized = normalize_semantic_alias(value)
            if not normalized:
                continue
            target = domain_alias_index.get(normalized)
            if target and is_canonical_semantic_key(target):
                return target

    # [*] 批次 D: 表里的内置别名(semantic.semantic_field_aliases)。
    if _RUNTIME_ALIAS_INDEX:
        builtin = _runtime_alias_bucket(_RUNTIME_ALIAS_INDEX, domain)
        if builtin:
            for value in values:
                normalized = normalize_semantic_alias(value)
                if not normalized:
                    continue
                target = builtin.get(normalized)
                if target and is_canonical_semantic_key(target):
                    return target

    return infer_semantic_key(*values)


def get_semantic_aliases(semantic_key: Optional[str]) -> list[str]:
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return []
    aliases = SEMANTIC_FIELD_ALIASES.get(normalized, [normalized])
    return list(dict.fromkeys([normalized, *aliases]))


def get_semantic_requirements(semantic_key: Optional[str]) -> dict[str, Any]:
    """语义键的要求(required / hash 参与资格)。

    [*] 批次 E(E-3 / 规格 D2): **不再返回** ``hash_participates``。

    以前这个字段挂在**绑定**上, 但它只是「模板级 ``deduplication_fields``」
    的派生投影 —— 同一事实两处真相, 而且**声明了但没接线**
    (真正喂 ``calculate_data_hash`` 的是模板级字段表)。

    现在「参与去重」由**版本级核心字段清单**的 ``in_hash`` 表达
    (:mod:`backend.services.core_fields_service`), 绑定级不再重复声明。
    """
    normalized = normalize_semantic_key(semantic_key)
    if not normalized:
        return {"required": False}
    meta = SEMANTIC_FIELD_META.get(normalized, {})
    return {
        "required": bool(meta.get("required", False)),
        "hash_eligible": bool(meta.get("hash_eligible", False)),
        "semantic_kind": str(meta.get("kind", "")),
        "system_scope": bool(meta.get("system_scope", False)),
        "identity_strength": meta.get("identity_strength"),
        "hash_warning": meta.get("hash_warning"),
    }


def _normalize_key_variants(key: str) -> set[str]:
    lowered = key.strip().lower()
    variants = {lowered}
    extractor = get_currency_extractor()
    normalized = extractor.normalize_field_name(key)
    variants.add(normalized.lower())
    variants.add(lowered.replace(" ", ""))
    variants.add(lowered.replace("_", ""))
    variants.add(normalized.lower().replace("_", ""))
    return {variant for variant in variants if len(variant) > 1}


def resolve_semantic_value(
    row: Dict[str, Any],
    semantic_key: str,
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
) -> tuple[Any, Optional[str]]:
    normalized_key = normalize_semantic_key(semantic_key)
    if not normalized_key:
        return None, None

    candidate_names: list[str] = []
    binding_candidates = list(header_bindings or [])
    for binding in binding_candidates:
        binding_semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if binding_semantic_key != normalized_key:
            continue
        raw_name = str(binding.get("raw_name") or "").strip()
        if raw_name:
            candidate_names.append(raw_name)
        source_header = str(binding.get("source_header") or "").strip()
        if source_header:
            candidate_names.append(source_header)
        display_name = str(binding.get("display_name") or "").strip()
        if display_name:
            candidate_names.append(display_name)
        for alias in binding.get("aliases") or []:
            alias_text = str(alias or "").strip()
            if alias_text:
                candidate_names.append(alias_text)

    candidate_names.extend(get_semantic_aliases(normalized_key))
    seen_names: list[str] = []
    seen_set = set()
    for name in candidate_names:
        lowered = str(name).strip().lower()
        if not lowered or lowered in seen_set:
            continue
        seen_set.add(lowered)
        seen_names.append(str(name).strip())

    row_lookup = {
        str(key).strip().lower(): key
        for key in row.keys()
        if str(key).strip()
    }
    for candidate in seen_names:
        matched_key = row_lookup.get(candidate.lower())
        if matched_key is not None:
            return row.get(matched_key), matched_key

    for key, value in row.items():
        key_variants = _normalize_key_variants(str(key))
        for candidate in seen_names:
            if any(candidate_variant in key_variants for candidate_variant in _normalize_key_variants(candidate)):
                return value, key
    return None, None


# ── 标准字段定义的对外投影(批次 D · API-1) ─────────────────────────
#
# 为什么要有这一层
# --------------
# 前端以前在 ``headerBindings.js`` 里**自己抄了一份**标准字段定义。
# 实测两份已经漂了(2026-11-07):
#
#   * 41 个字段里, 前端**普遍缺** ``domain`` / ``required`` / ``system_scope``
#     ⇒ 前端算出来的 ``required`` 永远是 false, 与后端的契约判定对不上;
#   * ``product_name`` 前端叫「商品名」后端叫「商品名称」;
#     ``item_status`` 前端叫「发品状态」后端叫「商品状态」;
#   * 5 个字段的别名列表对不上(``platform_sku`` 大小写、``line_id`` 少一条 …)。
#
# ⇒ 用户在前端看到的选项 ≠ 后端实际认定(FE-1)。
#
# 这一层把「唯一一份定义」投影成前端能直接用的结构, 前端不再抄。

#: 下拉框分组(键 → 中文标题, 顺序即展示顺序)。
SEMANTIC_OPTION_GROUPS: tuple[tuple[str, str], ...] = (
    ("identity", "身份字段"),
    ("time", "时间字段"),
    ("traffic_metric", "流量指标"),
    ("order_metric", "订单指标"),
    ("product_metric", "商品指标"),
    ("attribution_metric", "渠道归因指标"),
    ("attribute", "属性字段"),
)

_ORDER_METRIC_KEYS = frozenset(
    {
        "order_count",
        "sku_order_count",
        "sales_amount",
        "sales_volume",
        "paid_amount",
        "profit",
        "platform_commission",
    }
)
_PRODUCT_METRIC_KEYS = frozenset({"purchase_amount"})
_ATTRIBUTION_METRIC_KEYS = frozenset(
    {
        "live_gmv",
        "live_attributed_gmv",
        "live_indirect_gmv",
        "video_gmv",
        "video_attributed_gmv",
        "video_indirect_gmv",
    }
)


def semantic_option_group_key(semantic_key: Optional[str], meta: Optional[Dict[str, Any]] = None) -> str:
    """判定一个语义键属于哪个下拉分组。

    规则与前端旧实现逐条对应(前端旧实现是这段逻辑的**副本**,
    现在前端直接用后端算好的 ``group``)。
    """
    meta = meta if meta is not None else SEMANTIC_FIELD_META.get(str(semantic_key or ""), {})
    key = str(semantic_key or "")
    kind = str(meta.get("kind") or "")
    domain = str(meta.get("domain") or "common")
    if kind == "time":
        return "time"
    if kind in ("identity", "dimension"):
        return "identity"
    if key in _ATTRIBUTION_METRIC_KEYS or domain == "attribution":
        return "attribution_metric"
    if key in _ORDER_METRIC_KEYS or domain == "orders":
        return "order_metric"
    if key in _PRODUCT_METRIC_KEYS or domain == "products":
        return "product_metric"
    if kind == "metric":
        return "traffic_metric"
    return "attribute"


def build_semantic_field_definitions_payload() -> Dict[str, Any]:
    """标准字段定义的只读投影(API-1 的返回体)。

    这份载荷就是前端唯一的标准字段来源 ——
    前端不再维护副本, 因此不会再出现「前端看到的 ≠ 后端认定的」。
    """
    fields: list[Dict[str, Any]] = []
    options: list[Dict[str, Any]] = []
    for key, meta in SEMANTIC_FIELD_META.items():
        aliases = get_semantic_aliases(key)
        group = semantic_option_group_key(key, meta)
        description = SEMANTIC_FIELD_DESCRIPTIONS.get(key, "")
        fields.append(
            {
                "semantic_key": key,
                "label": str(meta.get("label") or key),
                "description": description,
                "kind": str(meta.get("kind") or "attribute"),
                "domain": str(meta.get("domain") or "common"),
                "required": bool(meta.get("required", False)),
                "hash_eligible": bool(meta.get("hash_eligible", False)),
                "default_hash": bool(meta.get("default_hash", False)),
                "system_scope": bool(meta.get("system_scope", False)),
                "identity_strength": meta.get("identity_strength"),
                "hash_warning": meta.get("hash_warning"),
                "aliases": aliases,
                "option_group": group,
            }
        )
        options.append(
            {
                "value": key,
                "label": f"{meta.get('label') or key} ({key})",
                "description": description,
                "kind": str(meta.get("kind") or "attribute"),
                "domain": str(meta.get("domain") or "common"),
                "group": group,
                "hash_eligible": bool(meta.get("hash_eligible", False)),
                "default_hash": bool(meta.get("default_hash", False)),
                "system_scope": bool(meta.get("system_scope", False)),
                "identity_strength": meta.get("identity_strength"),
                "hash_warning": meta.get("hash_warning"),
                "aliases": aliases,
            }
        )

    option_groups: list[Dict[str, Any]] = []
    for group_key, group_label in SEMANTIC_OPTION_GROUPS:
        grouped = [option for option in options if option["group"] == group_key]
        if not grouped:
            continue
        option_groups.append({"label": group_label, "options": grouped})

    domain_aliases = [
        {
            "data_domain": domain,
            "semantic_key": semantic_key,
            "aliases": list(aliases),
        }
        for domain, alias_map in DOMAIN_SEMANTIC_ALIASES.items()
        for semantic_key, aliases in alias_map.items()
    ]
    column_overrides = [
        {"data_domain": domain, "raw_name": raw_name, "semantic_key": semantic_key}
        for domain, mapping in DOMAIN_COLUMN_SEMANTIC_OVERRIDES.items()
        for raw_name, semantic_key in mapping.items()
    ]

    return {
        "fields": fields,
        "option_groups": option_groups,
        "domain_aliases": domain_aliases,
        "column_overrides": column_overrides,
        "system_hash_scope_fields": sorted(SYSTEM_HASH_SCOPE_KEYS),
        "hash_identity_keys": sorted(SEMANTIC_HASH_IDENTITY_KEYS),
        "runtime_alias_count": runtime_alias_count(),
        "runtime_alias_loaded": _RUNTIME_ALIAS_LOADED,
        # [*] 运行时别名索引 —— 这两份是**活的**: 用户在模板里沉淀一次,
        #     别名就多一条 ⇒ 前端必须每次从接口拿, 不能用快照。
        "runtime_alias_index": {
            domain: dict(items) for domain, items in _RUNTIME_CONFIRMED_ALIAS_INDEX.items()
        },
        "runtime_builtin_alias_index": {
            domain: dict(items) for domain, items in _RUNTIME_ALIAS_INDEX.items()
        },
    }


#: 归一化口径的「样本对」—— 用来锁住前后端两套归一化实现一致。
#:
#: 前端必须自己算一次归一化(它要在浏览器里查别名索引),
#: 所以前端有一份 :func:`normalize_semantic_alias` 的镜像实现。
#: 这份样本对由后端生成, 前端测试逐条断言 ⇒ 两边漂了就红。
NORMALIZATION_SAMPLE_VALUES: tuple[str, ...] = (
    "订单号",
    "订单编号",
    "买家支付(RMB)",
    "买家支付（rmb）",
    "利润（rmb）",
    "利润(RMB)",
    "商品SKU",
    "商品 sku",
    "下单时间\n",
    "*商品sku",
    "*商品名称",
    "商品 id",
    "商品ID",
    "客服ID",
    "日期期间",
    "GMV",
    "gmv",
    "  销售额  ",
    "销售_数量",
    "支付订单数",
    "商品成交件数",
    "曝光次数",
    "点击次数",
    "转化率",
    "date_from",
    "date_to",
    "order id",
    "Order ID",
    "line_id",
    "订单明细行ID",
)


def build_semantic_field_snapshot_payload() -> Dict[str, Any]:
    """前端快照载荷 —— 归一化索引 + 样本对 + 字段定义。

    前端在**浏览器里**用这份快照当兜底(接口没回来时不至于整页空白),
    同时用 ``normalization_samples`` 锁住前后端归一化口径一致。

    这份快照是**生成物**, 不是人手维护的副本 ——
    ``backend/tests/data_pipeline/test_semantic_translation_guardrails.py``
    会重新生成一遍并比对, 漂了就红。
    """
    payload = build_semantic_field_definitions_payload()
    # [*] 运行时别名索引是**活的**(用户在模板里沉淀一次就变一次) ⇒ 不能进快照。
    #     快照只放「代码里定义的」那部分, 运行期数据一律走接口。
    payload.pop("runtime_alias_index", None)
    payload.pop("runtime_builtin_alias_index", None)
    payload["alias_index"] = dict(_NORMALIZED_ALIAS_INDEX)
    payload["domain_alias_index"] = {
        domain: dict(items) for domain, items in _NORMALIZED_DOMAIN_ALIAS_INDEX.items()
    }
    payload["domain_column_index"] = {
        domain: dict(items) for domain, items in _NORMALIZED_COLUMN_OVERRIDE_INDEX.items()
    }
    payload["normalization_samples"] = [
        [raw, normalize_semantic_alias(raw)] for raw in NORMALIZATION_SAMPLE_VALUES
    ]
    return payload


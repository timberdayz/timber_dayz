/**
 * 标准字段定义快照 —— **自动生成, 请勿手工编辑**。
 *
 * 生成命令::
 *
 *     python scripts/generate_semantic_field_snapshot.py
 *
 * 漂移守护::
 *
 *     backend/tests/data_pipeline/test_semantic_translation_guardrails.py
 *
 * [*] 批次 D: 这份快照以前是前端 ``headerBindings.js`` 里手抄的 360 行,
 *     已经和后端漂了(缺 domain/required、label 与别名对不上)。
 *     现在它是**生成物**, 后端是唯一口径。
 */
export const SEMANTIC_FIELD_REGISTRY_SNAPSHOT = {
  "alias_index": {
    "addtocartcount": "add_to_cart_count",
    "addtocartrate": "add_to_cart_rate",
    "addtocartusercount": "add_to_cart_user_count",
    "aov": "aov",
    "aovplaced": "aov_placed",
    "bouncerate": "bounce_rate",
    "buyercount": "buyer_count",
    "buyercountplaced": "buyer_count_placed",
    "buyerpaidamount": "paid_amount",
    "campaignfee": "promotion_fee",
    "channel": "channel",
    "click": "clicks",
    "clickrate": "click_rate",
    "clicks": "clicks",
    "clicktoorderrate": "click_to_order_rate",
    "commission": "platform_commission",
    "conversionrate": "conversion_rate",
    "conversionrateplaced": "conversion_rate_placed",
    "ctor(sku订单)": "click_to_order_rate",
    "ctr": "click_rate",
    "cvr": "conversion_rate",
    "datadate": "metric_date",
    "date": "metric_date",
    "datefrom": "period_start_date",
    "dateto": "period_end_date",
    "deductionfee": "platform_deduction_fee",
    "endhour": "period_end_time",
    "endtime": "period_end_time",
    "estimatedsettlement": "estimated_settlement_amount",
    "estimatedsettlementamount": "estimated_settlement_amount",
    "gmv": "gmv",
    "gmvband": "gmv_band",
    "gmvrange": "gmv_band",
    "gmv区间": "gmv_band",
    "hour": "period_start_time",
    "impression": "impressions",
    "impressions": "impressions",
    "itemname": "product_name",
    "itemstatus": "item_status",
    "lineid": "line_id",
    "listingstatus": "item_status",
    "liveattributedgmv": "live_attributed_gmv",
    "livegmv": "live_gmv",
    "liveindirectgmv": "live_indirect_gmv",
    "logisticsfee": "shipping_fee",
    "metricdate": "metric_date",
    "orderconversionrate": "order_conversion_rate",
    "orderconversionrateplaced": "order_conversion_rate_placed",
    "ordercount": "order_count",
    "ordercountplaced": "order_count_placed",
    "orderdate": "order_date",
    "orderid": "order_id",
    "orderlineid": "line_id",
    "orderoriginalamount": "order_original_amount",
    "orders": "order_count",
    "orderstatus": "order_status",
    "originalamount": "order_original_amount",
    "pageviews": "page_views",
    "paidamount": "paid_amount",
    "periodenddate": "period_end_date",
    "periodendtime": "period_end_time",
    "periodstartdate": "period_start_date",
    "periodstarttime": "period_start_time",
    "platformcommission": "platform_commission",
    "platformdeductionfee": "platform_deduction_fee",
    "platformservicefee": "platform_service_fee",
    "platformsku": "platform_sku",
    "platformvoucher": "platform_voucher",
    "productid": "product_id",
    "productname": "product_name",
    "productsku": "platform_sku",
    "productstatus": "item_status",
    "productvisitorcount": "product_visitor_count",
    "productvisitors": "product_visitor_count",
    "profit": "profit",
    "promotionfee": "promotion_fee",
    "purchaseamount": "purchase_amount",
    "pv": "page_views",
    "qty": "sales_volume",
    "refundamount": "refund_amount",
    "refundeditemcount": "refunded_item_count",
    "revenue": "sales_amount",
    "sales": "sales_amount",
    "salesamount": "sales_amount",
    "salesamountplaced": "sales_amount_placed",
    "salesvolume": "sales_volume",
    "salesvolumeplaced": "sales_volume_placed",
    "sellercoupon": "seller_voucher",
    "sellervoucher": "seller_voucher",
    "servicefee": "platform_service_fee",
    "serviceid": "service_id",
    "settledamount": "settled_amount",
    "shippingfee": "shipping_fee",
    "shopid": "shop_id",
    "skuid": "sku_id",
    "skuordercount": "sku_order_count",
    "skuorders": "sku_order_count",
    "sku编号": "sku_id",
    "sku订单量": "sku_order_count",
    "starttime": "period_start_time",
    "time": "period_start_time",
    "totaltransactionamount": "total_transaction_amount",
    "uniqueclicks": "unique_clicks",
    "uniqueclicktoorderrate": "unique_click_to_order_rate",
    "uniqueimpressions": "unique_impressions",
    "unitssold": "sales_volume",
    "videoattributedgmv": "video_attributed_gmv",
    "videogmv": "video_gmv",
    "videoindirectgmv": "video_indirect_gmv",
    "views": "page_views",
    "visitorcount": "visitor_count",
    "visitors": "visitor_count",
    "voucheramount": "platform_voucher",
    "warehouse": "warehouse_name",
    "warehousefee": "warehouse_operation_fee",
    "warehousename": "warehouse_name",
    "warehouseoperationfee": "warehouse_operation_fee",
    "下单日期": "order_date",
    "下单时间": "order_date",
    "下单销售额": "sales_amount_placed",
    "不重复的商品曝光量": "unique_impressions",
    "不重复的商品点击量": "unique_clicks",
    "买家数(已下单)": "buyer_count_placed",
    "买家数(已下订单)": "buyer_count_placed",
    "买家数(已付款订单)": "buyer_count",
    "买家数(已确定订单)": "buyer_count_placed",
    "产品id": "product_id",
    "产品sku": "platform_sku",
    "产品名称": "product_name",
    "仓库": "warehouse_name",
    "仓库名称": "warehouse_name",
    "仓库操作费": "warehouse_operation_fee",
    "件数(已下单)": "sales_volume_placed",
    "件数(已下订单)": "sales_volume_placed",
    "件数(已确定订单)": "sales_volume_placed",
    "利润": "profit",
    "加购次数": "add_to_cart_count",
    "加购次数(直播)": "add_to_cart_count",
    "加购次数(视频)": "add_to_cart_count",
    "加购率": "add_to_cart_rate",
    "加购率(直播)": "add_to_cart_rate",
    "加购率(视频)": "add_to_cart_rate",
    "去重加购率": "add_to_cart_rate",
    "去重商品曝光次数": "unique_impressions",
    "去重商品曝光次数(视频)": "unique_impressions",
    "去重点击成交转化率(sku订单)": "unique_click_to_order_rate",
    "去重点击次数": "unique_clicks",
    "去重点击次数(视频)": "unique_clicks",
    "发品状态": "item_status",
    "周期开始日期": "period_start_date",
    "周期结束日期": "period_end_date",
    "商品": "product_name",
    "商品id": "product_id",
    "商品sku": "platform_sku",
    "商品卡": "channel",
    "商品名": "product_name",
    "商品名称": "product_name",
    "商品状态": "item_status",
    "商品访客数": "product_visitor_count",
    "商城页": "channel",
    "商家直播gmv": "live_gmv",
    "商家直播归因gmv": "live_attributed_gmv",
    "商家直播间接gmv": "live_indirect_gmv",
    "商家视频gmv": "video_gmv",
    "商家视频归因gmv": "video_attributed_gmv",
    "商家视频间接gmv": "video_indirect_gmv",
    "实付金额": "paid_amount",
    "小时": "period_start_time",
    "已下单": "order_count_placed",
    "已下订单": "order_count_placed",
    "已加购的用户数": "add_to_cart_user_count",
    "已加购的用户数(直播)": "add_to_cart_user_count",
    "已加购的用户数(视频)": "add_to_cart_user_count",
    "已确定订单": "order_count_placed",
    "已结算金额": "settled_amount",
    "已退款的商品件数": "refunded_item_count",
    "平台sku": "platform_sku",
    "平台代金券": "platform_voucher",
    "平台佣金": "platform_commission",
    "平台扣费": "platform_deduction_fee",
    "平台服务费": "platform_service_fee",
    "店铺": "shop_id",
    "店铺id": "shop_id",
    "开始日期": "period_start_date",
    "开始时间": "period_start_time",
    "总交易金额": "total_transaction_amount",
    "推广费": "promotion_fee",
    "日期": "metric_date",
    "时段": "period_start_time",
    "明细行id": "line_id",
    "曝光次数": "impressions",
    "曝光量": "impressions",
    "服务id": "service_id",
    "服务编号": "service_id",
    "每笔订单销售额": "aov",
    "每笔订单销售额(已下单)": "aov_placed",
    "每笔订单销售额(已下订单)": "aov_placed",
    "每笔订单销售额(已付款订单)": "aov",
    "每笔订单销售额(已确定订单)": "aov_placed",
    "浏览量": "page_views",
    "渠道": "channel",
    "点击次数": "clicks",
    "点击率": "click_rate",
    "点击量": "clicks",
    "直播": "channel",
    "直播gmv": "live_gmv",
    "直播归因gmv": "live_attributed_gmv",
    "直播间接gmv": "live_indirect_gmv",
    "结束小时": "period_end_time",
    "结束日期": "period_end_date",
    "结束时间": "period_end_time",
    "统计日期": "metric_date",
    "视频": "channel",
    "视频gmv": "video_gmv",
    "视频归因gmv": "video_attributed_gmv",
    "视频间接gmv": "video_indirect_gmv",
    "订单原始金额": "order_original_amount",
    "订单号": "order_id",
    "订单数": "order_count",
    "订单数量": "order_count",
    "订单日期": "order_date",
    "订单编号": "order_id",
    "订单转化率": "order_conversion_rate",
    "订单转化率(已下单)": "order_conversion_rate_placed",
    "订单转化率(已下订单)": "order_conversion_rate_placed",
    "订单转化率(已付款订单)": "order_conversion_rate",
    "订单转化率(已确定订单)": "order_conversion_rate_placed",
    "订单量": "order_count",
    "订单量(已下单)": "order_count_placed",
    "访客数": "visitor_count",
    "跳失率": "bounce_rate",
    "转化率": "conversion_rate",
    "转化率(已下单)": "conversion_rate_placed",
    "转化率(已下订单)": "conversion_rate_placed",
    "转化率(已确定订单)": "conversion_rate_placed",
    "运费": "shipping_fee",
    "退款商品件数": "refunded_item_count",
    "退款金额": "refund_amount",
    "退款额": "refund_amount",
    "采购金额": "purchase_amount",
    "销售数量": "sales_volume",
    "销售金额": "sales_amount",
    "销售额": "sales_amount",
    "销售额(已下单)": "sales_amount_placed",
    "销售额(已下订单)": "sales_amount_placed",
    "销售额(已确定订单)": "sales_amount_placed",
    "销量": "sales_volume",
    "销量(已下单)": "sales_volume_placed",
    "预估回款金额": "estimated_settlement_amount"
  },
  "column_overrides": [
    {
      "data_domain": "products",
      "raw_name": "商品编号",
      "semantic_key": "product_id"
    },
    {
      "data_domain": "products",
      "raw_name": "商品 id",
      "semantic_key": "product_id"
    },
    {
      "data_domain": "products",
      "raw_name": "id",
      "semantic_key": "product_id"
    },
    {
      "data_domain": "products",
      "raw_name": "规格编号",
      "semantic_key": "sku_id"
    },
    {
      "data_domain": "services",
      "raw_name": "客服id",
      "semantic_key": "service_id"
    },
    {
      "data_domain": "services",
      "raw_name": "客服编号",
      "semantic_key": "service_id"
    },
    {
      "data_domain": "services",
      "raw_name": "日期期间",
      "semantic_key": "metric_date"
    },
    {
      "data_domain": "inventory",
      "raw_name": "*商品sku",
      "semantic_key": "platform_sku"
    },
    {
      "data_domain": "inventory",
      "raw_name": "*商品名称",
      "semantic_key": "product_name"
    }
  ],
  "domain_alias_index": {
    "analytics": {
      "conversionrate": "conversion_rate",
      "date": "metric_date",
      "gmv": "gmv",
      "ordercount": "order_count",
      "pv": "page_views",
      "shopid": "shop_id",
      "uv": "visitor_count",
      "交易日期": "metric_date",
      "交易额": "gmv",
      "商品浏览量": "page_views",
      "商品访客数": "visitor_count",
      "店铺": "shop_id",
      "店铺id": "shop_id",
      "店铺名称": "shop_id",
      "成交订单数": "order_count",
      "成交金额": "gmv",
      "成交额": "gmv",
      "支付订单数": "order_count",
      "日期": "metric_date",
      "日期时间": "metric_date",
      "浏览量": "page_views",
      "统计日期": "metric_date",
      "订单数": "order_count",
      "访客数": "visitor_count",
      "访客量": "visitor_count",
      "访问用户数": "visitor_count",
      "转化率": "conversion_rate",
      "页面浏览数": "page_views",
      "页面浏览次数": "page_views",
      "页面浏览量": "page_views"
    },
    "orders": {
      "buyerpaid": "paid_amount",
      "estimatedsettlement": "estimated_settlement_amount",
      "estimatedsettlementamount": "estimated_settlement_amount",
      "orderdate": "order_date",
      "orderid": "order_id",
      "orderno": "order_id",
      "ordertime": "order_date",
      "paidamount": "paid_amount",
      "profit": "profit",
      "profitamount": "profit",
      "profitrmb": "profit",
      "quantity": "sales_volume",
      "salesvolume": "sales_volume",
      "shopid": "shop_id",
      "shopname": "shop_id",
      "skuid": "sku_id",
      "soldqty": "sales_volume",
      "下单时间": "order_date",
      "买家数": "buyer_count",
      "产品id": "product_id",
      "仓库操作费": "warehouse_operation_fee",
      "利润": "profit",
      "商品id": "product_id",
      "商品sku": "product_sku",
      "商品名称": "product_name",
      "已结算金额": "settled_amount",
      "平台sku": "platform_sku",
      "广告成本": "promotion_fee",
      "店铺": "shop_id",
      "店铺id": "shop_id",
      "订单号": "order_id",
      "订单状态": "order_status",
      "订单编号": "order_id",
      "退款金额": "refund_amount",
      "采购成本": "purchase_amount",
      "销售数量": "sales_volume",
      "预估回款金额": "estimated_settlement_amount"
    },
    "products": {
      "ctor(sku订单)": "click_to_order_rate",
      "currentitemstatus": "item_status",
      "gmv": "sales_amount",
      "id": "product_id",
      "不重复的商品曝光量": "unique_impressions",
      "不重复的商品点击量": "unique_clicks",
      "买家数(已下单)": "buyer_count_placed",
      "买家数(已下订单)": "buyer_count_placed",
      "买家数(已付款订单)": "buyer_count",
      "买家数(已确定订单)": "buyer_count_placed",
      "件数": "sales_volume",
      "件数(加入购物车)": "add_to_cart_count",
      "件数(已下单)": "sales_volume_placed",
      "件数(已下订单)": "sales_volume_placed",
      "件数(已付款订单)": "sales_volume",
      "件数(已确定订单)": "sales_volume_placed",
      "去重商品曝光次数": "unique_impressions",
      "去重点击成交转化率(sku订单)": "unique_click_to_order_rate",
      "去重点击次数": "unique_clicks",
      "发品状态": "item_status",
      "商品": "product_name",
      "商品id": "product_id",
      "商品名": "product_name",
      "商品展示量": "impressions",
      "商品成交件数": "sales_volume",
      "商品曝光次数": "impressions",
      "商品标题": "product_name",
      "商品点击量": "clicks",
      "商品编号": "product_id",
      "商品访客数(加入购物车)": "add_to_cart_user_count",
      "商品访客数量": "product_visitor_count",
      "商品跳出率": "bounce_rate",
      "商品页面访问量": "page_views",
      "已下单": "order_count_placed",
      "已下订单": "order_count_placed",
      "已付款订单": "order_count",
      "已确定订单": "order_count_placed",
      "每笔订单销售额(已下单)": "aov_placed",
      "每笔订单销售额(已下订单)": "aov_placed",
      "每笔订单销售额(已付款订单)": "aov",
      "每笔订单销售额(已确定订单)": "aov_placed",
      "规格编号": "sku_id",
      "订单转化率(已下单)": "order_conversion_rate_placed",
      "订单转化率(已下订单)": "order_conversion_rate_placed",
      "订单转化率(已付款订单)": "order_conversion_rate",
      "订单转化率(已确定订单)": "order_conversion_rate_placed",
      "转化率(加入购物车率)": "add_to_cart_rate",
      "转化率(已下单)": "conversion_rate_placed",
      "转化率(已下订单)": "conversion_rate_placed",
      "转化率(已付款订单)": "conversion_rate",
      "转化率(已确定订单)": "conversion_rate_placed",
      "销售额(已下单)": "sales_amount_placed",
      "销售额(已下订单)": "sales_amount_placed",
      "销售额(已付款订单)": "sales_amount",
      "销售额(已确定订单)": "sales_amount_placed"
    }
  },
  "domain_aliases": [
    {
      "aliases": [
        "订单编号",
        "订单号",
        "order_id",
        "order_no",
        "order no",
        "order id"
      ],
      "data_domain": "orders",
      "semantic_key": "order_id"
    },
    {
      "aliases": [
        "店铺",
        "店铺ID",
        "shop_id",
        "shop id",
        "shop_name",
        "shop name"
      ],
      "data_domain": "orders",
      "semantic_key": "shop_id"
    },
    {
      "aliases": [
        "订单状态"
      ],
      "data_domain": "orders",
      "semantic_key": "order_status"
    },
    {
      "aliases": [
        "下单时间",
        "order_date",
        "order time",
        "order_time"
      ],
      "data_domain": "orders",
      "semantic_key": "order_date"
    },
    {
      "aliases": [
        "产品ID",
        "商品ID"
      ],
      "data_domain": "orders",
      "semantic_key": "product_id"
    },
    {
      "aliases": [
        "商品名称"
      ],
      "data_domain": "orders",
      "semantic_key": "product_name"
    },
    {
      "aliases": [
        "商品SKU"
      ],
      "data_domain": "orders",
      "semantic_key": "product_sku"
    },
    {
      "aliases": [
        "平台SKU"
      ],
      "data_domain": "orders",
      "semantic_key": "platform_sku"
    },
    {
      "aliases": [
        "SKU ID"
      ],
      "data_domain": "orders",
      "semantic_key": "sku_id"
    },
    {
      "aliases": [
        "销售数量",
        "sold_qty",
        "sales_volume",
        "quantity"
      ],
      "data_domain": "orders",
      "semantic_key": "sales_volume"
    },
    {
      "aliases": [
        "买家数"
      ],
      "data_domain": "orders",
      "semantic_key": "buyer_count"
    },
    {
      "aliases": [
        "paid_amount",
        "buyer_paid"
      ],
      "data_domain": "orders",
      "semantic_key": "paid_amount"
    },
    {
      "aliases": [
        "利润(RMB)",
        "profit",
        "profit_amount",
        "profit_rmb"
      ],
      "data_domain": "orders",
      "semantic_key": "profit"
    },
    {
      "aliases": [
        "采购成本(RMB)"
      ],
      "data_domain": "orders",
      "semantic_key": "purchase_amount"
    },
    {
      "aliases": [
        "退款金额(RMB)"
      ],
      "data_domain": "orders",
      "semantic_key": "refund_amount"
    },
    {
      "aliases": [
        "预估回款金额(RMB)",
        "estimated_settlement",
        "estimated_settlement_amount"
      ],
      "data_domain": "orders",
      "semantic_key": "estimated_settlement_amount"
    },
    {
      "aliases": [
        "已结算金额(RMB)"
      ],
      "data_domain": "orders",
      "semantic_key": "settled_amount"
    },
    {
      "aliases": [
        "仓库操作费(RMB)"
      ],
      "data_domain": "orders",
      "semantic_key": "warehouse_operation_fee"
    },
    {
      "aliases": [
        "广告成本(RMB)"
      ],
      "data_domain": "orders",
      "semantic_key": "promotion_fee"
    },
    {
      "aliases": [
        "日期",
        "统计日期",
        "交易日期",
        "日期时间",
        "date"
      ],
      "data_domain": "analytics",
      "semantic_key": "metric_date"
    },
    {
      "aliases": [
        "店铺",
        "店铺id",
        "店铺名称",
        "shop_id",
        "shop id"
      ],
      "data_domain": "analytics",
      "semantic_key": "shop_id"
    },
    {
      "aliases": [
        "商品访客数",
        "访客数",
        "访客量",
        "访问用户数",
        "uv"
      ],
      "data_domain": "analytics",
      "semantic_key": "visitor_count"
    },
    {
      "aliases": [
        "页面浏览次数",
        "页面浏览量",
        "页面浏览数",
        "商品浏览量",
        "浏览量",
        "pv"
      ],
      "data_domain": "analytics",
      "semantic_key": "page_views"
    },
    {
      "aliases": [
        "转化率",
        "conversion_rate"
      ],
      "data_domain": "analytics",
      "semantic_key": "conversion_rate"
    },
    {
      "aliases": [
        "订单数",
        "支付订单数",
        "成交订单数",
        "order_count"
      ],
      "data_domain": "analytics",
      "semantic_key": "order_count"
    },
    {
      "aliases": [
        "gmv",
        "成交金额",
        "成交额",
        "交易额"
      ],
      "data_domain": "analytics",
      "semantic_key": "gmv"
    },
    {
      "aliases": [
        "商品编号",
        "商品 ID",
        "商品ID",
        "ID"
      ],
      "data_domain": "products",
      "semantic_key": "product_id"
    },
    {
      "aliases": [
        "商品",
        "商品名",
        "商品标题"
      ],
      "data_domain": "products",
      "semantic_key": "product_name"
    },
    {
      "aliases": [
        "Current Item Status",
        "发品状态"
      ],
      "data_domain": "products",
      "semantic_key": "item_status"
    },
    {
      "aliases": [
        "规格编号"
      ],
      "data_domain": "products",
      "semantic_key": "sku_id"
    },
    {
      "aliases": [
        "已付款订单"
      ],
      "data_domain": "products",
      "semantic_key": "order_count"
    },
    {
      "aliases": [
        "销售额（已付款订单）",
        "销售额（已付款订单） (SGD)",
        "GMV"
      ],
      "data_domain": "products",
      "semantic_key": "sales_amount"
    },
    {
      "aliases": [
        "件数（已付款订单）",
        "商品成交件数",
        "件数"
      ],
      "data_domain": "products",
      "semantic_key": "sales_volume"
    },
    {
      "aliases": [
        "转化率（已付款订单）"
      ],
      "data_domain": "products",
      "semantic_key": "conversion_rate"
    },
    {
      "aliases": [
        "订单转化率（已付款订单）"
      ],
      "data_domain": "products",
      "semantic_key": "order_conversion_rate"
    },
    {
      "aliases": [
        "买家数（已付款订单）"
      ],
      "data_domain": "products",
      "semantic_key": "buyer_count"
    },
    {
      "aliases": [
        "每笔订单销售额（已付款订单）",
        "每笔订单销售额（已付款订单） (SGD)"
      ],
      "data_domain": "products",
      "semantic_key": "aov"
    },
    {
      "aliases": [
        "已下订单",
        "已确定订单"
      ],
      "data_domain": "products",
      "semantic_key": "order_count_placed"
    },
    {
      "aliases": [
        "销售额（已下订单）",
        "销售额（已下订单） (SGD)",
        "销售额（已下订单） (MYR)",
        "销售额（已下订单） (PHP)",
        "销售额（已确定订单）"
      ],
      "data_domain": "products",
      "semantic_key": "sales_amount_placed"
    },
    {
      "aliases": [
        "件数（已下订单）",
        "件数（已确定订单）"
      ],
      "data_domain": "products",
      "semantic_key": "sales_volume_placed"
    },
    {
      "aliases": [
        "转化率（已下订单）",
        "转化率（已确定订单）"
      ],
      "data_domain": "products",
      "semantic_key": "conversion_rate_placed"
    },
    {
      "aliases": [
        "订单转化率（已下订单）",
        "订单转化率（已确定订单）"
      ],
      "data_domain": "products",
      "semantic_key": "order_conversion_rate_placed"
    },
    {
      "aliases": [
        "买家数（已下订单）",
        "买家数（已确定订单）"
      ],
      "data_domain": "products",
      "semantic_key": "buyer_count_placed"
    },
    {
      "aliases": [
        "每笔订单销售额（已下订单）",
        "每笔订单销售额（已下订单） (SGD)",
        "每笔订单销售额（已下订单） (MYR)",
        "每笔订单销售额（已下订单） (PHP)",
        "每笔订单销售额（已确定订单）"
      ],
      "data_domain": "products",
      "semantic_key": "aov_placed"
    },
    {
      "aliases": [
        "商品展示量",
        "商品曝光次数"
      ],
      "data_domain": "products",
      "semantic_key": "impressions"
    },
    {
      "aliases": [
        "不重复的商品曝光量",
        "去重商品曝光次数"
      ],
      "data_domain": "products",
      "semantic_key": "unique_impressions"
    },
    {
      "aliases": [
        "商品点击量"
      ],
      "data_domain": "products",
      "semantic_key": "clicks"
    },
    {
      "aliases": [
        "不重复的商品点击量",
        "去重点击次数"
      ],
      "data_domain": "products",
      "semantic_key": "unique_clicks"
    },
    {
      "aliases": [
        "商品访客数量"
      ],
      "data_domain": "products",
      "semantic_key": "product_visitor_count"
    },
    {
      "aliases": [
        "商品页面访问量"
      ],
      "data_domain": "products",
      "semantic_key": "page_views"
    },
    {
      "aliases": [
        "商品跳出率"
      ],
      "data_domain": "products",
      "semantic_key": "bounce_rate"
    },
    {
      "aliases": [
        "件数 (加入购物车）"
      ],
      "data_domain": "products",
      "semantic_key": "add_to_cart_count"
    },
    {
      "aliases": [
        "商品访客数 (加入购物车)"
      ],
      "data_domain": "products",
      "semantic_key": "add_to_cart_user_count"
    },
    {
      "aliases": [
        "转化率 (加入购物车率)"
      ],
      "data_domain": "products",
      "semantic_key": "add_to_cart_rate"
    },
    {
      "aliases": [
        "CTOR（SKU 订单）"
      ],
      "data_domain": "products",
      "semantic_key": "click_to_order_rate"
    },
    {
      "aliases": [
        "去重点击成交转化率（SKU 订单）"
      ],
      "data_domain": "products",
      "semantic_key": "unique_click_to_order_rate"
    }
  ],
  "domain_column_index": {
    "inventory": {
      "商品sku": "platform_sku",
      "商品名称": "product_name"
    },
    "products": {
      "id": "product_id",
      "商品id": "product_id",
      "商品编号": "product_id",
      "规格编号": "sku_id"
    },
    "services": {
      "客服id": "service_id",
      "客服编号": "service_id",
      "日期期间": "metric_date"
    }
  },
  "fields": [
    {
      "aliases": [
        "order_id",
        "订单号",
        "订单编号",
        "order id"
      ],
      "default_hash": true,
      "description": "识别同一笔订单的稳定身份字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "订单号",
      "option_group": "identity",
      "required": true,
      "semantic_key": "order_id",
      "system_scope": false
    },
    {
      "aliases": [
        "line_id",
        "order_line_id",
        "line id",
        "order line id",
        "明细行ID"
      ],
      "default_hash": true,
      "description": "订单明细行粒度的稳定身份字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "订单明细行 ID",
      "option_group": "identity",
      "required": false,
      "semantic_key": "line_id",
      "system_scope": false
    },
    {
      "aliases": [
        "product_id",
        "产品id",
        "商品id",
        "产品ID",
        "商品ID",
        "product id"
      ],
      "default_hash": true,
      "description": "平台或系统内识别同一商品的稳定身份字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "商品 ID",
      "option_group": "identity",
      "required": false,
      "semantic_key": "product_id",
      "system_scope": false
    },
    {
      "aliases": [
        "platform_sku",
        "平台sku",
        "平台 sku",
        "product_sku",
        "产品sku",
        "商品sku"
      ],
      "default_hash": true,
      "description": "平台侧商品规格编码，可作为商品身份字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "平台 SKU",
      "option_group": "identity",
      "required": false,
      "semantic_key": "platform_sku",
      "system_scope": false
    },
    {
      "aliases": [
        "sku_id",
        "sku id",
        "SKU ID",
        "SKU编号"
      ],
      "default_hash": true,
      "description": "订单明细或商品规格粒度的身份字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "SKU 编号",
      "option_group": "identity",
      "required": false,
      "semantic_key": "sku_id",
      "system_scope": false
    },
    {
      "aliases": [
        "service_id",
        "service id",
        "服务ID",
        "服务编号"
      ],
      "default_hash": true,
      "description": "服务类数据的稳定身份字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "服务 ID",
      "option_group": "identity",
      "required": false,
      "semantic_key": "service_id",
      "system_scope": false
    },
    {
      "aliases": [
        "shop_id",
        "店铺",
        "店铺ID",
        "shop id"
      ],
      "default_hash": false,
      "description": "系统自动加入 Data Hash 的店铺作用域字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "identity",
      "label": "店铺 ID",
      "option_group": "identity",
      "required": false,
      "semantic_key": "shop_id",
      "system_scope": true
    },
    {
      "aliases": [
        "warehouse_name",
        "warehouse",
        "仓库",
        "仓库名称",
        "warehouse name"
      ],
      "default_hash": true,
      "description": "库存快照区分仓库粒度的维度字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "dimension",
      "label": "仓库",
      "option_group": "identity",
      "required": false,
      "semantic_key": "warehouse_name",
      "system_scope": false
    },
    {
      "aliases": [
        "gmv_band",
        "gmv band",
        "gmv range",
        "GMV区间",
        "GMV 区间"
      ],
      "default_hash": false,
      "description": "按 GMV 区间出报表时可作为行粒度维度。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "dimension",
      "label": "GMV 区间",
      "option_group": "identity",
      "required": false,
      "semantic_key": "gmv_band",
      "system_scope": false
    },
    {
      "aliases": [
        "metric_date",
        "日期",
        "统计日期",
        "data_date",
        "date"
      ],
      "default_hash": true,
      "description": "日/周/月报表定位业务周期的时间字段。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "time",
      "label": "统计日期",
      "option_group": "time",
      "required": false,
      "semantic_key": "metric_date",
      "system_scope": false
    },
    {
      "aliases": [
        "period_start_date",
        "开始日期",
        "周期开始日期",
        "date_from"
      ],
      "default_hash": true,
      "description": "区间型报表的开始日期。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "time",
      "label": "周期开始日期",
      "option_group": "time",
      "required": false,
      "semantic_key": "period_start_date",
      "system_scope": false
    },
    {
      "aliases": [
        "period_end_date",
        "结束日期",
        "周期结束日期",
        "date_to"
      ],
      "default_hash": true,
      "description": "区间型报表的结束日期。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "time",
      "label": "周期结束日期",
      "option_group": "time",
      "required": false,
      "semantic_key": "period_end_date",
      "system_scope": false
    },
    {
      "aliases": [
        "period_start_time",
        "开始时间",
        "小时",
        "时段",
        "hour",
        "time",
        "start time"
      ],
      "default_hash": false,
      "description": "小时级或更细粒度报表的开始时间，可由用户手动加入 Data Hash。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "time",
      "label": "周期开始时间",
      "option_group": "time",
      "required": false,
      "semantic_key": "period_start_time",
      "system_scope": false
    },
    {
      "aliases": [
        "period_end_time",
        "结束时间",
        "结束小时",
        "end hour",
        "end time"
      ],
      "default_hash": false,
      "description": "小时级或更细粒度报表的结束时间，可由用户手动加入 Data Hash。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "time",
      "label": "周期结束时间",
      "option_group": "time",
      "required": false,
      "semantic_key": "period_end_time",
      "system_scope": false
    },
    {
      "aliases": [
        "order_date",
        "下单日期",
        "订单日期",
        "下单时间"
      ],
      "default_hash": false,
      "description": "订单发生日期，通常作为分析维度。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "time",
      "label": "下单日期",
      "option_group": "time",
      "required": false,
      "semantic_key": "order_date",
      "system_scope": false
    },
    {
      "aliases": [
        "visitor_count",
        "访客数",
        "visitors",
        "visitor count"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "访客数",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "visitor_count",
      "system_scope": false
    },
    {
      "aliases": [
        "product_visitor_count",
        "商品访客数",
        "product visitors",
        "product visitor count"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "商品访客数",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "product_visitor_count",
      "system_scope": false
    },
    {
      "aliases": [
        "page_views",
        "浏览量",
        "pv",
        "page views",
        "views"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "浏览量",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "page_views",
      "system_scope": false
    },
    {
      "aliases": [
        "impressions",
        "曝光量",
        "曝光次数",
        "impression"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "曝光量",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "impressions",
      "system_scope": false
    },
    {
      "aliases": [
        "clicks",
        "点击量",
        "点击次数",
        "click"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "点击量",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "clicks",
      "system_scope": false
    },
    {
      "aliases": [
        "click_rate",
        "点击率",
        "click rate",
        "ctr"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "点击率",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "click_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "conversion_rate",
        "转化率",
        "conversion rate",
        "cvr",
        "CVR"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "转化率",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "conversion_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "order_count",
        "订单量",
        "订单数",
        "order count",
        "订单数量",
        "orders"
      ],
      "default_hash": false,
      "description": "指标值，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "订单量",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "order_count",
      "system_scope": false
    },
    {
      "aliases": [
        "sku_order_count",
        "SKU订单量",
        "sku orders",
        "sku order count"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "SKU 订单量",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "sku_order_count",
      "system_scope": false
    },
    {
      "aliases": [
        "gmv",
        "GMV"
      ],
      "default_hash": false,
      "description": "指标值，不参与 Data Hash。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "GMV",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "total_transaction_amount",
        "总交易金额",
        "total transaction amount"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "总交易金额",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "total_transaction_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "bounce_rate",
        "跳失率",
        "bounce rate"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "analytics",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "跳失率",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "bounce_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "sales_amount",
        "sales amount",
        "revenue",
        "sales",
        "销售额",
        "销售金额"
      ],
      "default_hash": false,
      "description": "指标值，不参与 Data Hash。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "销售额(已废止)",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "sales_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "sales_volume",
        "sales volume",
        "qty",
        "units sold",
        "销量",
        "销售数量"
      ],
      "default_hash": false,
      "description": "指标值，不参与 Data Hash。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "销量",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "sales_volume",
      "system_scope": false
    },
    {
      "aliases": [
        "paid_amount",
        "实付金额",
        "paid amount",
        "buyer paid amount"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "实付金额",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "paid_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "profit",
        "利润"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "利润",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "profit",
      "system_scope": false
    },
    {
      "aliases": [
        "purchase_amount",
        "采购金额",
        "purchase amount"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "采购金额",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "purchase_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "platform_commission",
        "平台佣金",
        "platform commission",
        "commission"
      ],
      "default_hash": false,
      "description": "系统语义指标，不参与 Data Hash。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "平台佣金",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "platform_commission",
      "system_scope": false
    },
    {
      "aliases": [
        "order_original_amount",
        "订单原始金额",
        "order original amount",
        "original amount"
      ],
      "default_hash": false,
      "description": "订单未减优惠前的金额(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "订单原始金额",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "order_original_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "warehouse_operation_fee",
        "仓库操作费",
        "warehouse operation fee",
        "warehouse fee"
      ],
      "default_hash": false,
      "description": "仓库操作费(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "仓库操作费",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "warehouse_operation_fee",
      "system_scope": false
    },
    {
      "aliases": [
        "shipping_fee",
        "运费",
        "shipping fee",
        "logistics fee"
      ],
      "default_hash": false,
      "description": "卖家承担的运费(人民币口径)。平台间列名不同。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "运费",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "shipping_fee",
      "system_scope": false
    },
    {
      "aliases": [
        "promotion_fee",
        "推广费",
        "promotion fee",
        "campaign fee"
      ],
      "default_hash": false,
      "description": "广告/推广成本(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "推广费",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "promotion_fee",
      "system_scope": false
    },
    {
      "aliases": [
        "platform_deduction_fee",
        "平台扣费",
        "platform deduction fee",
        "deduction fee"
      ],
      "default_hash": false,
      "description": "平台扣费(人民币口径)。目前源表无对应列。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "平台扣费",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "platform_deduction_fee",
      "system_scope": false
    },
    {
      "aliases": [
        "platform_voucher",
        "平台代金券",
        "platform voucher",
        "voucher amount"
      ],
      "default_hash": false,
      "description": "平台发放的代金券(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "平台代金券",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "platform_voucher",
      "system_scope": false
    },
    {
      "aliases": [
        "platform_service_fee",
        "平台服务费",
        "platform service fee",
        "service fee"
      ],
      "default_hash": false,
      "description": "平台服务费(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "平台服务费",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "platform_service_fee",
      "system_scope": false
    },
    {
      "aliases": [
        "estimated_settlement_amount",
        "预估回款金额",
        "estimated settlement amount",
        "estimated settlement"
      ],
      "default_hash": false,
      "description": "预估回款金额(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "预估回款金额",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "estimated_settlement_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "settled_amount",
        "已结算金额",
        "settled amount"
      ],
      "default_hash": false,
      "description": "已结算金额(人民币口径)。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "已结算金额",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "settled_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "order_status",
        "order status"
      ],
      "default_hash": false,
      "description": "订单状态维度。",
      "domain": "orders",
      "hash_eligible": false,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "dimension",
      "label": "订单状态",
      "option_group": "identity",
      "required": false,
      "semantic_key": "order_status",
      "system_scope": false
    },
    {
      "aliases": [
        "product_sku",
        "product sku"
      ],
      "default_hash": false,
      "description": "卖家侧商品 SKU(与平台 SKU 不同)。",
      "domain": "orders",
      "hash_eligible": false,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "dimension",
      "label": "商品 SKU",
      "option_group": "identity",
      "required": false,
      "semantic_key": "product_sku",
      "system_scope": false
    },
    {
      "aliases": [
        "seller_voucher",
        "seller voucher",
        "seller coupon"
      ],
      "default_hash": false,
      "description": "卖家自己发放的代金券(人民币口径)。不是平台成本。",
      "domain": "orders",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "卖家代金券",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "seller_voucher",
      "system_scope": false
    },
    {
      "aliases": [
        "live_gmv",
        "商家直播 GMV",
        "直播GMV",
        "live gmv"
      ],
      "default_hash": false,
      "description": "渠道归因系统语义指标，不参与 Data Hash。",
      "domain": "attribution",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "直播 GMV",
      "option_group": "attribution_metric",
      "required": false,
      "semantic_key": "live_gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "live_attributed_gmv",
        "商家直播归因 GMV",
        "直播归因GMV",
        "live attributed gmv"
      ],
      "default_hash": false,
      "description": "渠道归因系统语义指标，不参与 Data Hash。",
      "domain": "attribution",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "直播归因 GMV",
      "option_group": "attribution_metric",
      "required": false,
      "semantic_key": "live_attributed_gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "live_indirect_gmv",
        "商家直播间接 GMV",
        "直播间接GMV",
        "live indirect gmv"
      ],
      "default_hash": false,
      "description": "渠道归因系统语义指标，不参与 Data Hash。",
      "domain": "attribution",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "直播间接 GMV",
      "option_group": "attribution_metric",
      "required": false,
      "semantic_key": "live_indirect_gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "video_gmv",
        "商家视频 GMV",
        "视频GMV",
        "video gmv"
      ],
      "default_hash": false,
      "description": "渠道归因系统语义指标，不参与 Data Hash。",
      "domain": "attribution",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "视频 GMV",
      "option_group": "attribution_metric",
      "required": false,
      "semantic_key": "video_gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "video_attributed_gmv",
        "商家视频归因 GMV",
        "视频归因GMV",
        "video attributed gmv"
      ],
      "default_hash": false,
      "description": "渠道归因系统语义指标，不参与 Data Hash。",
      "domain": "attribution",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "视频归因 GMV",
      "option_group": "attribution_metric",
      "required": false,
      "semantic_key": "video_attributed_gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "video_indirect_gmv",
        "商家视频间接 GMV",
        "视频间接GMV",
        "video indirect gmv"
      ],
      "default_hash": false,
      "description": "渠道归因系统语义指标，不参与 Data Hash。",
      "domain": "attribution",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "视频间接 GMV",
      "option_group": "attribution_metric",
      "required": false,
      "semantic_key": "video_indirect_gmv",
      "system_scope": false
    },
    {
      "aliases": [
        "product_name",
        "item_name",
        "product name",
        "item name",
        "商品",
        "商品名",
        "商品名称",
        "产品名称"
      ],
      "default_hash": false,
      "description": "弱身份字段。商品名可能重名或改名，优先使用商品 ID / SKU。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "商品名可能重名或改名，优先使用商品 ID / SKU。",
      "identity_strength": "weak",
      "kind": "dimension",
      "label": "商品名称",
      "option_group": "identity",
      "required": false,
      "semantic_key": "product_name",
      "system_scope": false
    },
    {
      "aliases": [
        "item_status",
        "product_status",
        "listing_status",
        "item status",
        "product status",
        "发品状态",
        "商品状态"
      ],
      "default_hash": false,
      "description": "标准化属性字段，状态变化不应默认改变 Data Hash。",
      "domain": "products",
      "hash_eligible": false,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "attribute",
      "label": "商品状态",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "item_status",
      "system_scope": false
    },
    {
      "aliases": [
        "sales_amount_placed",
        "销售额（已下单）",
        "销售额（已下订单）",
        "销售额（已确定订单）",
        "下单销售额"
      ],
      "default_hash": false,
      "description": "销售额（下单口径）。与「已付款口径」平均差 5.15%，不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "销售额（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "sales_amount_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "sales_volume_placed",
        "销量（已下单）",
        "件数（已下单）",
        "件数（已下订单）",
        "件数（已确定订单）"
      ],
      "default_hash": false,
      "description": "销量（下单口径）。与「已付款口径」不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "销量（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "sales_volume_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "order_count_placed",
        "订单量（已下单）",
        "已下单",
        "已下订单",
        "已确定订单"
      ],
      "default_hash": false,
      "description": "订单量（下单口径）。与「已付款口径」不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "订单量（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "order_count_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "conversion_rate_placed",
        "转化率（已下单）",
        "转化率（已下订单）",
        "转化率（已确定订单）"
      ],
      "default_hash": false,
      "description": "转化率（下单口径）。与「已付款口径」不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "转化率（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "conversion_rate_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "order_conversion_rate_placed",
        "订单转化率（已下单）",
        "订单转化率（已下订单）",
        "订单转化率（已确定订单）"
      ],
      "default_hash": false,
      "description": "订单转化率（下单口径）。与商品转化率是不同指标。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "订单转化率（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "order_conversion_rate_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "buyer_count_placed",
        "买家数（已下单）",
        "买家数（已下订单）",
        "买家数（已确定订单）"
      ],
      "default_hash": false,
      "description": "买家数（下单口径）。与「已付款口径」不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "买家数（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "buyer_count_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "aov_placed",
        "每笔订单销售额（已下单）",
        "每笔订单销售额（已下订单）",
        "每笔订单销售额（已确定订单）"
      ],
      "default_hash": false,
      "description": "每笔订单销售额（下单口径）。与「已付款口径」不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "每笔订单销售额（下单口径）",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "aov_placed",
      "system_scope": false
    },
    {
      "aliases": [
        "order_conversion_rate",
        "订单转化率",
        "订单转化率（已付款订单）",
        "订单转化率（已下订单）"
      ],
      "default_hash": false,
      "description": "订单转化率。与商品转化率是不同指标，不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "订单转化率",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "order_conversion_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "unique_impressions",
        "不重复的商品曝光量",
        "去重商品曝光次数",
        "去重商品曝光次数（视频）"
      ],
      "default_hash": false,
      "description": "去重商品曝光量。与商品展示量（曝光次数）是不同指标。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "去重商品曝光量",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "unique_impressions",
      "system_scope": false
    },
    {
      "aliases": [
        "unique_clicks",
        "不重复的商品点击量",
        "去重点击次数",
        "去重点击次数（视频）"
      ],
      "default_hash": false,
      "description": "去重点击量。与商品点击量（点击次数）是不同指标。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "去重点击量",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "unique_clicks",
      "system_scope": false
    },
    {
      "aliases": [
        "click_to_order_rate",
        "CTOR（SKU 订单）"
      ],
      "default_hash": false,
      "description": "tiktok 的点击成交转化率(CTOR), 订单数除以点击数; 与转化率(已付款订单)分母不同, 不可混用。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "点击成交转化率",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "click_to_order_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "unique_click_to_order_rate",
        "去重点击成交转化率（SKU 订单）"
      ],
      "default_hash": false,
      "description": "tiktok 的去重点击成交转化率, 订单数除以去重点击数; 与全点击口径的 CTOR 数值不同。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "去重点击成交转化率",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "unique_click_to_order_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "buyer_count",
        "买家数（已付款订单）",
        "买家数（已下订单）",
        "买家数（已确定订单）"
      ],
      "default_hash": false,
      "description": "买家数。已付款口径。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "买家数",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "buyer_count",
      "system_scope": false
    },
    {
      "aliases": [
        "aov",
        "每笔订单销售额（已付款订单）",
        "每笔订单销售额（已下订单）",
        "每笔订单销售额"
      ],
      "default_hash": false,
      "description": "每笔订单销售额。已付款口径。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "每笔订单销售额",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "aov",
      "system_scope": false
    },
    {
      "aliases": [
        "add_to_cart_count",
        "加购次数",
        "加购次数（直播）",
        "加购次数（视频）"
      ],
      "default_hash": false,
      "description": "加购件数。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "加购件数",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "add_to_cart_count",
      "system_scope": false
    },
    {
      "aliases": [
        "add_to_cart_user_count",
        "已加购的用户数",
        "已加购的用户数（直播）",
        "已加购的用户数（视频）"
      ],
      "default_hash": false,
      "description": "加购用户数。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "加购用户数",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "add_to_cart_user_count",
      "system_scope": false
    },
    {
      "aliases": [
        "add_to_cart_rate",
        "加购率",
        "加购率（直播）",
        "加购率（视频）",
        "去重加购率"
      ],
      "default_hash": false,
      "description": "加购率。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "加购率",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "add_to_cart_rate",
      "system_scope": false
    },
    {
      "aliases": [
        "refund_amount",
        "退款金额",
        "退款额"
      ],
      "default_hash": false,
      "description": "退款金额。",
      "domain": "common",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "退款金额",
      "option_group": "traffic_metric",
      "required": false,
      "semantic_key": "refund_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "refunded_item_count",
        "已退款的商品件数",
        "退款商品件数"
      ],
      "default_hash": false,
      "description": "退款商品件数。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
      "identity_strength": null,
      "kind": "metric",
      "label": "退款商品件数",
      "option_group": "product_metric",
      "required": false,
      "semantic_key": "refunded_item_count",
      "system_scope": false
    },
    {
      "aliases": [
        "channel",
        "渠道",
        "商城页",
        "直播",
        "视频",
        "商品卡"
      ],
      "default_hash": true,
      "description": "渠道维度。tiktok 商品报表按商城/直播/视频/商品卡分块。",
      "domain": "products",
      "hash_eligible": true,
      "hash_warning": null,
      "identity_strength": null,
      "kind": "dimension",
      "label": "渠道",
      "option_group": "identity",
      "required": false,
      "semantic_key": "channel",
      "system_scope": false
    }
  ],
  "generated_at": "",
  "generated_by": "scripts/generate_semantic_field_snapshot.py",
  "hash_identity_keys": [
    "add_to_cart_count",
    "add_to_cart_rate",
    "add_to_cart_user_count",
    "aov",
    "aov_placed",
    "bounce_rate",
    "buyer_count",
    "buyer_count_placed",
    "channel",
    "click_rate",
    "click_to_order_rate",
    "clicks",
    "conversion_rate",
    "conversion_rate_placed",
    "estimated_settlement_amount",
    "gmv",
    "gmv_band",
    "impressions",
    "line_id",
    "live_attributed_gmv",
    "live_gmv",
    "live_indirect_gmv",
    "metric_date",
    "order_conversion_rate",
    "order_conversion_rate_placed",
    "order_count",
    "order_count_placed",
    "order_date",
    "order_id",
    "order_original_amount",
    "page_views",
    "paid_amount",
    "period_end_date",
    "period_end_time",
    "period_start_date",
    "period_start_time",
    "platform_commission",
    "platform_deduction_fee",
    "platform_service_fee",
    "platform_sku",
    "platform_voucher",
    "product_id",
    "product_name",
    "product_visitor_count",
    "profit",
    "promotion_fee",
    "purchase_amount",
    "refund_amount",
    "refunded_item_count",
    "sales_amount",
    "sales_amount_placed",
    "sales_volume",
    "sales_volume_placed",
    "seller_voucher",
    "service_id",
    "settled_amount",
    "shipping_fee",
    "shop_id",
    "sku_id",
    "sku_order_count",
    "total_transaction_amount",
    "unique_click_to_order_rate",
    "unique_clicks",
    "unique_impressions",
    "video_attributed_gmv",
    "video_gmv",
    "video_indirect_gmv",
    "visitor_count",
    "warehouse_name",
    "warehouse_operation_fee"
  ],
  "normalization_samples": [
    [
      "订单号",
      "订单号"
    ],
    [
      "订单编号",
      "订单编号"
    ],
    [
      "买家支付(RMB)",
      "买家支付"
    ],
    [
      "买家支付（rmb）",
      "买家支付"
    ],
    [
      "利润（rmb）",
      "利润"
    ],
    [
      "利润(RMB)",
      "利润"
    ],
    [
      "商品SKU",
      "商品sku"
    ],
    [
      "商品 sku",
      "商品sku"
    ],
    [
      "下单时间\n",
      "下单时间"
    ],
    [
      "*商品sku",
      "商品sku"
    ],
    [
      "*商品名称",
      "商品名称"
    ],
    [
      "商品 id",
      "商品id"
    ],
    [
      "商品ID",
      "商品id"
    ],
    [
      "客服ID",
      "客服id"
    ],
    [
      "日期期间",
      "日期期间"
    ],
    [
      "GMV",
      "gmv"
    ],
    [
      "gmv",
      "gmv"
    ],
    [
      "  销售额  ",
      "销售额"
    ],
    [
      "销售_数量",
      "销售数量"
    ],
    [
      "支付订单数",
      "支付订单数"
    ],
    [
      "商品成交件数",
      "商品成交件数"
    ],
    [
      "曝光次数",
      "曝光次数"
    ],
    [
      "点击次数",
      "点击次数"
    ],
    [
      "转化率",
      "转化率"
    ],
    [
      "date_from",
      "datefrom"
    ],
    [
      "date_to",
      "dateto"
    ],
    [
      "order id",
      "orderid"
    ],
    [
      "Order ID",
      "orderid"
    ],
    [
      "line_id",
      "lineid"
    ],
    [
      "订单明细行ID",
      "订单明细行id"
    ]
  ],
  "option_groups": [
    {
      "label": "身份字段",
      "options": [
        {
          "aliases": [
            "order_id",
            "订单号",
            "订单编号",
            "order id"
          ],
          "default_hash": true,
          "description": "识别同一笔订单的稳定身份字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "订单号 (order_id)",
          "system_scope": false,
          "value": "order_id"
        },
        {
          "aliases": [
            "line_id",
            "order_line_id",
            "line id",
            "order line id",
            "明细行ID"
          ],
          "default_hash": true,
          "description": "订单明细行粒度的稳定身份字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "订单明细行 ID (line_id)",
          "system_scope": false,
          "value": "line_id"
        },
        {
          "aliases": [
            "product_id",
            "产品id",
            "商品id",
            "产品ID",
            "商品ID",
            "product id"
          ],
          "default_hash": true,
          "description": "平台或系统内识别同一商品的稳定身份字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "商品 ID (product_id)",
          "system_scope": false,
          "value": "product_id"
        },
        {
          "aliases": [
            "platform_sku",
            "平台sku",
            "平台 sku",
            "product_sku",
            "产品sku",
            "商品sku"
          ],
          "default_hash": true,
          "description": "平台侧商品规格编码，可作为商品身份字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "平台 SKU (platform_sku)",
          "system_scope": false,
          "value": "platform_sku"
        },
        {
          "aliases": [
            "sku_id",
            "sku id",
            "SKU ID",
            "SKU编号"
          ],
          "default_hash": true,
          "description": "订单明细或商品规格粒度的身份字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "SKU 编号 (sku_id)",
          "system_scope": false,
          "value": "sku_id"
        },
        {
          "aliases": [
            "service_id",
            "service id",
            "服务ID",
            "服务编号"
          ],
          "default_hash": true,
          "description": "服务类数据的稳定身份字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "服务 ID (service_id)",
          "system_scope": false,
          "value": "service_id"
        },
        {
          "aliases": [
            "shop_id",
            "店铺",
            "店铺ID",
            "shop id"
          ],
          "default_hash": false,
          "description": "系统自动加入 Data Hash 的店铺作用域字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "identity",
          "label": "店铺 ID (shop_id)",
          "system_scope": true,
          "value": "shop_id"
        },
        {
          "aliases": [
            "warehouse_name",
            "warehouse",
            "仓库",
            "仓库名称",
            "warehouse name"
          ],
          "default_hash": true,
          "description": "库存快照区分仓库粒度的维度字段。",
          "domain": "common",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "dimension",
          "label": "仓库 (warehouse_name)",
          "system_scope": false,
          "value": "warehouse_name"
        },
        {
          "aliases": [
            "gmv_band",
            "gmv band",
            "gmv range",
            "GMV区间",
            "GMV 区间"
          ],
          "default_hash": false,
          "description": "按 GMV 区间出报表时可作为行粒度维度。",
          "domain": "products",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "dimension",
          "label": "GMV 区间 (gmv_band)",
          "system_scope": false,
          "value": "gmv_band"
        },
        {
          "aliases": [
            "order_status",
            "order status"
          ],
          "default_hash": false,
          "description": "订单状态维度。",
          "domain": "orders",
          "group": "identity",
          "hash_eligible": false,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "dimension",
          "label": "订单状态 (order_status)",
          "system_scope": false,
          "value": "order_status"
        },
        {
          "aliases": [
            "product_sku",
            "product sku"
          ],
          "default_hash": false,
          "description": "卖家侧商品 SKU(与平台 SKU 不同)。",
          "domain": "orders",
          "group": "identity",
          "hash_eligible": false,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "dimension",
          "label": "商品 SKU (product_sku)",
          "system_scope": false,
          "value": "product_sku"
        },
        {
          "aliases": [
            "product_name",
            "item_name",
            "product name",
            "item name",
            "商品",
            "商品名",
            "商品名称",
            "产品名称"
          ],
          "default_hash": false,
          "description": "弱身份字段。商品名可能重名或改名，优先使用商品 ID / SKU。",
          "domain": "products",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": "商品名可能重名或改名，优先使用商品 ID / SKU。",
          "identity_strength": "weak",
          "kind": "dimension",
          "label": "商品名称 (product_name)",
          "system_scope": false,
          "value": "product_name"
        },
        {
          "aliases": [
            "channel",
            "渠道",
            "商城页",
            "直播",
            "视频",
            "商品卡"
          ],
          "default_hash": true,
          "description": "渠道维度。tiktok 商品报表按商城/直播/视频/商品卡分块。",
          "domain": "products",
          "group": "identity",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "dimension",
          "label": "渠道 (channel)",
          "system_scope": false,
          "value": "channel"
        }
      ]
    },
    {
      "label": "时间字段",
      "options": [
        {
          "aliases": [
            "metric_date",
            "日期",
            "统计日期",
            "data_date",
            "date"
          ],
          "default_hash": true,
          "description": "日/周/月报表定位业务周期的时间字段。",
          "domain": "common",
          "group": "time",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "time",
          "label": "统计日期 (metric_date)",
          "system_scope": false,
          "value": "metric_date"
        },
        {
          "aliases": [
            "period_start_date",
            "开始日期",
            "周期开始日期",
            "date_from"
          ],
          "default_hash": true,
          "description": "区间型报表的开始日期。",
          "domain": "common",
          "group": "time",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "time",
          "label": "周期开始日期 (period_start_date)",
          "system_scope": false,
          "value": "period_start_date"
        },
        {
          "aliases": [
            "period_end_date",
            "结束日期",
            "周期结束日期",
            "date_to"
          ],
          "default_hash": true,
          "description": "区间型报表的结束日期。",
          "domain": "common",
          "group": "time",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "time",
          "label": "周期结束日期 (period_end_date)",
          "system_scope": false,
          "value": "period_end_date"
        },
        {
          "aliases": [
            "period_start_time",
            "开始时间",
            "小时",
            "时段",
            "hour",
            "time",
            "start time"
          ],
          "default_hash": false,
          "description": "小时级或更细粒度报表的开始时间，可由用户手动加入 Data Hash。",
          "domain": "common",
          "group": "time",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "time",
          "label": "周期开始时间 (period_start_time)",
          "system_scope": false,
          "value": "period_start_time"
        },
        {
          "aliases": [
            "period_end_time",
            "结束时间",
            "结束小时",
            "end hour",
            "end time"
          ],
          "default_hash": false,
          "description": "小时级或更细粒度报表的结束时间，可由用户手动加入 Data Hash。",
          "domain": "common",
          "group": "time",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "time",
          "label": "周期结束时间 (period_end_time)",
          "system_scope": false,
          "value": "period_end_time"
        },
        {
          "aliases": [
            "order_date",
            "下单日期",
            "订单日期",
            "下单时间"
          ],
          "default_hash": false,
          "description": "订单发生日期，通常作为分析维度。",
          "domain": "orders",
          "group": "time",
          "hash_eligible": true,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "time",
          "label": "下单日期 (order_date)",
          "system_scope": false,
          "value": "order_date"
        }
      ]
    },
    {
      "label": "流量指标",
      "options": [
        {
          "aliases": [
            "visitor_count",
            "访客数",
            "visitors",
            "visitor count"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "访客数 (visitor_count)",
          "system_scope": false,
          "value": "visitor_count"
        },
        {
          "aliases": [
            "product_visitor_count",
            "商品访客数",
            "product visitors",
            "product visitor count"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "商品访客数 (product_visitor_count)",
          "system_scope": false,
          "value": "product_visitor_count"
        },
        {
          "aliases": [
            "page_views",
            "浏览量",
            "pv",
            "page views",
            "views"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "浏览量 (page_views)",
          "system_scope": false,
          "value": "page_views"
        },
        {
          "aliases": [
            "impressions",
            "曝光量",
            "曝光次数",
            "impression"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "曝光量 (impressions)",
          "system_scope": false,
          "value": "impressions"
        },
        {
          "aliases": [
            "clicks",
            "点击量",
            "点击次数",
            "click"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "点击量 (clicks)",
          "system_scope": false,
          "value": "clicks"
        },
        {
          "aliases": [
            "click_rate",
            "点击率",
            "click rate",
            "ctr"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "点击率 (click_rate)",
          "system_scope": false,
          "value": "click_rate"
        },
        {
          "aliases": [
            "conversion_rate",
            "转化率",
            "conversion rate",
            "cvr",
            "CVR"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "转化率 (conversion_rate)",
          "system_scope": false,
          "value": "conversion_rate"
        },
        {
          "aliases": [
            "gmv",
            "GMV"
          ],
          "default_hash": false,
          "description": "指标值，不参与 Data Hash。",
          "domain": "common",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "GMV (gmv)",
          "system_scope": false,
          "value": "gmv"
        },
        {
          "aliases": [
            "total_transaction_amount",
            "总交易金额",
            "total transaction amount"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "总交易金额 (total_transaction_amount)",
          "system_scope": false,
          "value": "total_transaction_amount"
        },
        {
          "aliases": [
            "bounce_rate",
            "跳失率",
            "bounce rate"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "跳失率 (bounce_rate)",
          "system_scope": false,
          "value": "bounce_rate"
        },
        {
          "aliases": [
            "refund_amount",
            "退款金额",
            "退款额"
          ],
          "default_hash": false,
          "description": "退款金额。",
          "domain": "common",
          "group": "traffic_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "退款金额 (refund_amount)",
          "system_scope": false,
          "value": "refund_amount"
        }
      ]
    },
    {
      "label": "订单指标",
      "options": [
        {
          "aliases": [
            "order_count",
            "订单量",
            "订单数",
            "order count",
            "订单数量",
            "orders"
          ],
          "default_hash": false,
          "description": "指标值，不参与 Data Hash。",
          "domain": "analytics",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "订单量 (order_count)",
          "system_scope": false,
          "value": "order_count"
        },
        {
          "aliases": [
            "sku_order_count",
            "SKU订单量",
            "sku orders",
            "sku order count"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "analytics",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "SKU 订单量 (sku_order_count)",
          "system_scope": false,
          "value": "sku_order_count"
        },
        {
          "aliases": [
            "sales_amount",
            "sales amount",
            "revenue",
            "sales",
            "销售额",
            "销售金额"
          ],
          "default_hash": false,
          "description": "指标值，不参与 Data Hash。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "销售额(已废止) (sales_amount)",
          "system_scope": false,
          "value": "sales_amount"
        },
        {
          "aliases": [
            "sales_volume",
            "sales volume",
            "qty",
            "units sold",
            "销量",
            "销售数量"
          ],
          "default_hash": false,
          "description": "指标值，不参与 Data Hash。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "销量 (sales_volume)",
          "system_scope": false,
          "value": "sales_volume"
        },
        {
          "aliases": [
            "paid_amount",
            "实付金额",
            "paid amount",
            "buyer paid amount"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "实付金额 (paid_amount)",
          "system_scope": false,
          "value": "paid_amount"
        },
        {
          "aliases": [
            "profit",
            "利润"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "利润 (profit)",
          "system_scope": false,
          "value": "profit"
        },
        {
          "aliases": [
            "platform_commission",
            "平台佣金",
            "platform commission",
            "commission"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "平台佣金 (platform_commission)",
          "system_scope": false,
          "value": "platform_commission"
        },
        {
          "aliases": [
            "order_original_amount",
            "订单原始金额",
            "order original amount",
            "original amount"
          ],
          "default_hash": false,
          "description": "订单未减优惠前的金额(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "订单原始金额 (order_original_amount)",
          "system_scope": false,
          "value": "order_original_amount"
        },
        {
          "aliases": [
            "warehouse_operation_fee",
            "仓库操作费",
            "warehouse operation fee",
            "warehouse fee"
          ],
          "default_hash": false,
          "description": "仓库操作费(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "仓库操作费 (warehouse_operation_fee)",
          "system_scope": false,
          "value": "warehouse_operation_fee"
        },
        {
          "aliases": [
            "shipping_fee",
            "运费",
            "shipping fee",
            "logistics fee"
          ],
          "default_hash": false,
          "description": "卖家承担的运费(人民币口径)。平台间列名不同。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "运费 (shipping_fee)",
          "system_scope": false,
          "value": "shipping_fee"
        },
        {
          "aliases": [
            "promotion_fee",
            "推广费",
            "promotion fee",
            "campaign fee"
          ],
          "default_hash": false,
          "description": "广告/推广成本(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "推广费 (promotion_fee)",
          "system_scope": false,
          "value": "promotion_fee"
        },
        {
          "aliases": [
            "platform_deduction_fee",
            "平台扣费",
            "platform deduction fee",
            "deduction fee"
          ],
          "default_hash": false,
          "description": "平台扣费(人民币口径)。目前源表无对应列。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "平台扣费 (platform_deduction_fee)",
          "system_scope": false,
          "value": "platform_deduction_fee"
        },
        {
          "aliases": [
            "platform_voucher",
            "平台代金券",
            "platform voucher",
            "voucher amount"
          ],
          "default_hash": false,
          "description": "平台发放的代金券(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "平台代金券 (platform_voucher)",
          "system_scope": false,
          "value": "platform_voucher"
        },
        {
          "aliases": [
            "platform_service_fee",
            "平台服务费",
            "platform service fee",
            "service fee"
          ],
          "default_hash": false,
          "description": "平台服务费(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "平台服务费 (platform_service_fee)",
          "system_scope": false,
          "value": "platform_service_fee"
        },
        {
          "aliases": [
            "estimated_settlement_amount",
            "预估回款金额",
            "estimated settlement amount",
            "estimated settlement"
          ],
          "default_hash": false,
          "description": "预估回款金额(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "预估回款金额 (estimated_settlement_amount)",
          "system_scope": false,
          "value": "estimated_settlement_amount"
        },
        {
          "aliases": [
            "settled_amount",
            "已结算金额",
            "settled amount"
          ],
          "default_hash": false,
          "description": "已结算金额(人民币口径)。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "已结算金额 (settled_amount)",
          "system_scope": false,
          "value": "settled_amount"
        },
        {
          "aliases": [
            "seller_voucher",
            "seller voucher",
            "seller coupon"
          ],
          "default_hash": false,
          "description": "卖家自己发放的代金券(人民币口径)。不是平台成本。",
          "domain": "orders",
          "group": "order_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "卖家代金券 (seller_voucher)",
          "system_scope": false,
          "value": "seller_voucher"
        }
      ]
    },
    {
      "label": "商品指标",
      "options": [
        {
          "aliases": [
            "purchase_amount",
            "采购金额",
            "purchase amount"
          ],
          "default_hash": false,
          "description": "系统语义指标，不参与 Data Hash。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "采购金额 (purchase_amount)",
          "system_scope": false,
          "value": "purchase_amount"
        },
        {
          "aliases": [
            "item_status",
            "product_status",
            "listing_status",
            "item status",
            "product status",
            "发品状态",
            "商品状态"
          ],
          "default_hash": false,
          "description": "标准化属性字段，状态变化不应默认改变 Data Hash。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": false,
          "hash_warning": null,
          "identity_strength": null,
          "kind": "attribute",
          "label": "商品状态 (item_status)",
          "system_scope": false,
          "value": "item_status"
        },
        {
          "aliases": [
            "sales_amount_placed",
            "销售额（已下单）",
            "销售额（已下订单）",
            "销售额（已确定订单）",
            "下单销售额"
          ],
          "default_hash": false,
          "description": "销售额（下单口径）。与「已付款口径」平均差 5.15%，不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "销售额（下单口径） (sales_amount_placed)",
          "system_scope": false,
          "value": "sales_amount_placed"
        },
        {
          "aliases": [
            "sales_volume_placed",
            "销量（已下单）",
            "件数（已下单）",
            "件数（已下订单）",
            "件数（已确定订单）"
          ],
          "default_hash": false,
          "description": "销量（下单口径）。与「已付款口径」不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "销量（下单口径） (sales_volume_placed)",
          "system_scope": false,
          "value": "sales_volume_placed"
        },
        {
          "aliases": [
            "order_count_placed",
            "订单量（已下单）",
            "已下单",
            "已下订单",
            "已确定订单"
          ],
          "default_hash": false,
          "description": "订单量（下单口径）。与「已付款口径」不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "订单量（下单口径） (order_count_placed)",
          "system_scope": false,
          "value": "order_count_placed"
        },
        {
          "aliases": [
            "conversion_rate_placed",
            "转化率（已下单）",
            "转化率（已下订单）",
            "转化率（已确定订单）"
          ],
          "default_hash": false,
          "description": "转化率（下单口径）。与「已付款口径」不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "转化率（下单口径） (conversion_rate_placed)",
          "system_scope": false,
          "value": "conversion_rate_placed"
        },
        {
          "aliases": [
            "order_conversion_rate_placed",
            "订单转化率（已下单）",
            "订单转化率（已下订单）",
            "订单转化率（已确定订单）"
          ],
          "default_hash": false,
          "description": "订单转化率（下单口径）。与商品转化率是不同指标。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "订单转化率（下单口径） (order_conversion_rate_placed)",
          "system_scope": false,
          "value": "order_conversion_rate_placed"
        },
        {
          "aliases": [
            "buyer_count_placed",
            "买家数（已下单）",
            "买家数（已下订单）",
            "买家数（已确定订单）"
          ],
          "default_hash": false,
          "description": "买家数（下单口径）。与「已付款口径」不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "买家数（下单口径） (buyer_count_placed)",
          "system_scope": false,
          "value": "buyer_count_placed"
        },
        {
          "aliases": [
            "aov_placed",
            "每笔订单销售额（已下单）",
            "每笔订单销售额（已下订单）",
            "每笔订单销售额（已确定订单）"
          ],
          "default_hash": false,
          "description": "每笔订单销售额（下单口径）。与「已付款口径」不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "每笔订单销售额（下单口径） (aov_placed)",
          "system_scope": false,
          "value": "aov_placed"
        },
        {
          "aliases": [
            "order_conversion_rate",
            "订单转化率",
            "订单转化率（已付款订单）",
            "订单转化率（已下订单）"
          ],
          "default_hash": false,
          "description": "订单转化率。与商品转化率是不同指标，不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "订单转化率 (order_conversion_rate)",
          "system_scope": false,
          "value": "order_conversion_rate"
        },
        {
          "aliases": [
            "unique_impressions",
            "不重复的商品曝光量",
            "去重商品曝光次数",
            "去重商品曝光次数（视频）"
          ],
          "default_hash": false,
          "description": "去重商品曝光量。与商品展示量（曝光次数）是不同指标。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "去重商品曝光量 (unique_impressions)",
          "system_scope": false,
          "value": "unique_impressions"
        },
        {
          "aliases": [
            "unique_clicks",
            "不重复的商品点击量",
            "去重点击次数",
            "去重点击次数（视频）"
          ],
          "default_hash": false,
          "description": "去重点击量。与商品点击量（点击次数）是不同指标。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "去重点击量 (unique_clicks)",
          "system_scope": false,
          "value": "unique_clicks"
        },
        {
          "aliases": [
            "click_to_order_rate",
            "CTOR（SKU 订单）"
          ],
          "default_hash": false,
          "description": "tiktok 的点击成交转化率(CTOR), 订单数除以点击数; 与转化率(已付款订单)分母不同, 不可混用。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "点击成交转化率 (click_to_order_rate)",
          "system_scope": false,
          "value": "click_to_order_rate"
        },
        {
          "aliases": [
            "unique_click_to_order_rate",
            "去重点击成交转化率（SKU 订单）"
          ],
          "default_hash": false,
          "description": "tiktok 的去重点击成交转化率, 订单数除以去重点击数; 与全点击口径的 CTOR 数值不同。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "去重点击成交转化率 (unique_click_to_order_rate)",
          "system_scope": false,
          "value": "unique_click_to_order_rate"
        },
        {
          "aliases": [
            "buyer_count",
            "买家数（已付款订单）",
            "买家数（已下订单）",
            "买家数（已确定订单）"
          ],
          "default_hash": false,
          "description": "买家数。已付款口径。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "买家数 (buyer_count)",
          "system_scope": false,
          "value": "buyer_count"
        },
        {
          "aliases": [
            "aov",
            "每笔订单销售额（已付款订单）",
            "每笔订单销售额（已下订单）",
            "每笔订单销售额"
          ],
          "default_hash": false,
          "description": "每笔订单销售额。已付款口径。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "每笔订单销售额 (aov)",
          "system_scope": false,
          "value": "aov"
        },
        {
          "aliases": [
            "add_to_cart_count",
            "加购次数",
            "加购次数（直播）",
            "加购次数（视频）"
          ],
          "default_hash": false,
          "description": "加购件数。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "加购件数 (add_to_cart_count)",
          "system_scope": false,
          "value": "add_to_cart_count"
        },
        {
          "aliases": [
            "add_to_cart_user_count",
            "已加购的用户数",
            "已加购的用户数（直播）",
            "已加购的用户数（视频）"
          ],
          "default_hash": false,
          "description": "加购用户数。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "加购用户数 (add_to_cart_user_count)",
          "system_scope": false,
          "value": "add_to_cart_user_count"
        },
        {
          "aliases": [
            "add_to_cart_rate",
            "加购率",
            "加购率（直播）",
            "加购率（视频）",
            "去重加购率"
          ],
          "default_hash": false,
          "description": "加购率。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "加购率 (add_to_cart_rate)",
          "system_scope": false,
          "value": "add_to_cart_rate"
        },
        {
          "aliases": [
            "refunded_item_count",
            "已退款的商品件数",
            "退款商品件数"
          ],
          "default_hash": false,
          "description": "退款商品件数。",
          "domain": "products",
          "group": "product_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "退款商品件数 (refunded_item_count)",
          "system_scope": false,
          "value": "refunded_item_count"
        }
      ]
    },
    {
      "label": "渠道归因指标",
      "options": [
        {
          "aliases": [
            "live_gmv",
            "商家直播 GMV",
            "直播GMV",
            "live gmv"
          ],
          "default_hash": false,
          "description": "渠道归因系统语义指标，不参与 Data Hash。",
          "domain": "attribution",
          "group": "attribution_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "直播 GMV (live_gmv)",
          "system_scope": false,
          "value": "live_gmv"
        },
        {
          "aliases": [
            "live_attributed_gmv",
            "商家直播归因 GMV",
            "直播归因GMV",
            "live attributed gmv"
          ],
          "default_hash": false,
          "description": "渠道归因系统语义指标，不参与 Data Hash。",
          "domain": "attribution",
          "group": "attribution_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "直播归因 GMV (live_attributed_gmv)",
          "system_scope": false,
          "value": "live_attributed_gmv"
        },
        {
          "aliases": [
            "live_indirect_gmv",
            "商家直播间接 GMV",
            "直播间接GMV",
            "live indirect gmv"
          ],
          "default_hash": false,
          "description": "渠道归因系统语义指标，不参与 Data Hash。",
          "domain": "attribution",
          "group": "attribution_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "直播间接 GMV (live_indirect_gmv)",
          "system_scope": false,
          "value": "live_indirect_gmv"
        },
        {
          "aliases": [
            "video_gmv",
            "商家视频 GMV",
            "视频GMV",
            "video gmv"
          ],
          "default_hash": false,
          "description": "渠道归因系统语义指标，不参与 Data Hash。",
          "domain": "attribution",
          "group": "attribution_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "视频 GMV (video_gmv)",
          "system_scope": false,
          "value": "video_gmv"
        },
        {
          "aliases": [
            "video_attributed_gmv",
            "商家视频归因 GMV",
            "视频归因GMV",
            "video attributed gmv"
          ],
          "default_hash": false,
          "description": "渠道归因系统语义指标，不参与 Data Hash。",
          "domain": "attribution",
          "group": "attribution_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "视频归因 GMV (video_attributed_gmv)",
          "system_scope": false,
          "value": "video_attributed_gmv"
        },
        {
          "aliases": [
            "video_indirect_gmv",
            "商家视频间接 GMV",
            "视频间接GMV",
            "video indirect gmv"
          ],
          "default_hash": false,
          "description": "渠道归因系统语义指标，不参与 Data Hash。",
          "domain": "attribution",
          "group": "attribution_metric",
          "hash_eligible": true,
          "hash_warning": "指标类字段参与去重后, 指标值变化会被当成新行(而不是更新)。确认「这一行的身份就包含这个指标」再勾选。",
          "identity_strength": null,
          "kind": "metric",
          "label": "视频间接 GMV (video_indirect_gmv)",
          "system_scope": false,
          "value": "video_indirect_gmv"
        }
      ]
    }
  ],
  "runtime_alias_count": 0,
  "runtime_alias_loaded": false,
  "system_hash_scope_fields": [
    "data_domain",
    "granularity",
    "platform_code",
    "shop_id",
    "sub_domain"
  ]
}

export default SEMANTIC_FIELD_REGISTRY_SNAPSHOT

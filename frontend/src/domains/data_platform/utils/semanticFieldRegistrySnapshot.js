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
    "bouncerate": "bounce_rate",
    "buyerpaidamount": "paid_amount",
    "click": "clicks",
    "clickrate": "click_rate",
    "clicks": "clicks",
    "commission": "platform_commission",
    "conversionrate": "conversion_rate",
    "ctr": "click_rate",
    "cvr": "conversion_rate",
    "datadate": "metric_date",
    "date": "metric_date",
    "datefrom": "period_start_date",
    "dateto": "period_end_date",
    "endhour": "period_end_time",
    "endtime": "period_end_time",
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
    "metricdate": "metric_date",
    "ordercount": "order_count",
    "orderdate": "order_date",
    "orderid": "order_id",
    "orderlineid": "line_id",
    "orders": "order_count",
    "pageviews": "page_views",
    "paidamount": "paid_amount",
    "periodenddate": "period_end_date",
    "periodendtime": "period_end_time",
    "periodstartdate": "period_start_date",
    "periodstarttime": "period_start_time",
    "platformcommission": "platform_commission",
    "platformsku": "platform_sku",
    "productid": "product_id",
    "productname": "product_name",
    "productsku": "platform_sku",
    "productstatus": "item_status",
    "productvisitorcount": "product_visitor_count",
    "productvisitors": "product_visitor_count",
    "profit": "profit",
    "purchaseamount": "purchase_amount",
    "pv": "page_views",
    "sales": "sales_amount",
    "salesamount": "sales_amount",
    "salesvolume": "sales_volume",
    "serviceid": "service_id",
    "shopid": "shop_id",
    "skuid": "sku_id",
    "skuordercount": "sku_order_count",
    "skuorders": "sku_order_count",
    "sku编号": "sku_id",
    "sku订单量": "sku_order_count",
    "starttime": "period_start_time",
    "time": "period_start_time",
    "totaltransactionamount": "total_transaction_amount",
    "unitssold": "sales_volume",
    "videoattributedgmv": "video_attributed_gmv",
    "videogmv": "video_gmv",
    "videoindirectgmv": "video_indirect_gmv",
    "views": "page_views",
    "visitorcount": "visitor_count",
    "visitors": "visitor_count",
    "warehouse": "warehouse_name",
    "warehousename": "warehouse_name",
    "下单日期": "order_date",
    "下单时间": "order_date",
    "产品id": "product_id",
    "产品sku": "platform_sku",
    "产品名称": "product_name",
    "仓库": "warehouse_name",
    "仓库名称": "warehouse_name",
    "利润": "profit",
    "发品状态": "item_status",
    "周期开始日期": "period_start_date",
    "周期结束日期": "period_end_date",
    "商品": "product_name",
    "商品id": "product_id",
    "商品sku": "platform_sku",
    "商品名": "product_name",
    "商品名称": "product_name",
    "商品状态": "item_status",
    "商品访客数": "product_visitor_count",
    "商家直播gmv": "live_gmv",
    "商家直播归因gmv": "live_attributed_gmv",
    "商家直播间接gmv": "live_indirect_gmv",
    "商家视频gmv": "video_gmv",
    "商家视频归因gmv": "video_attributed_gmv",
    "商家视频间接gmv": "video_indirect_gmv",
    "实付金额": "paid_amount",
    "小时": "period_start_time",
    "平台sku": "platform_sku",
    "平台佣金": "platform_commission",
    "店铺": "shop_id",
    "店铺id": "shop_id",
    "开始日期": "period_start_date",
    "开始时间": "period_start_time",
    "总交易金额": "total_transaction_amount",
    "日期": "metric_date",
    "时段": "period_start_time",
    "明细行id": "line_id",
    "曝光次数": "impressions",
    "曝光量": "impressions",
    "服务id": "service_id",
    "服务编号": "service_id",
    "浏览量": "page_views",
    "点击次数": "clicks",
    "点击率": "click_rate",
    "点击量": "clicks",
    "直播gmv": "live_gmv",
    "直播归因gmv": "live_attributed_gmv",
    "直播间接gmv": "live_indirect_gmv",
    "结束小时": "period_end_time",
    "结束日期": "period_end_date",
    "结束时间": "period_end_time",
    "统计日期": "metric_date",
    "视频gmv": "video_gmv",
    "视频归因gmv": "video_attributed_gmv",
    "视频间接gmv": "video_indirect_gmv",
    "订单号": "order_id",
    "订单数": "order_count",
    "订单日期": "order_date",
    "订单编号": "order_id",
    "订单量": "order_count",
    "访客数": "visitor_count",
    "跳失率": "bounce_rate",
    "转化率": "conversion_rate",
    "采购金额": "purchase_amount",
    "销售数量": "sales_volume",
    "销售金额": "sales_amount",
    "销售额": "sales_amount",
    "销量": "sales_volume"
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
      "costprofitrate": "cost_profit_rate",
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
      "settlementdate": "settlement_time",
      "settlementtime": "settlement_time",
      "shopid": "shop_id",
      "shopname": "shop_id",
      "soldqty": "sales_volume",
      "下单日期": "order_date",
      "下单时间": "order_date",
      "买家支付": "paid_amount",
      "出库数量": "sales_volume",
      "利润": "profit",
      "实付金额": "paid_amount",
      "店铺": "shop_id",
      "店铺id": "shop_id",
      "成本利润率": "cost_profit_rate",
      "结算时间": "settlement_time",
      "订单号": "order_id",
      "订单日期": "order_date",
      "订单时间": "order_date",
      "订单编号": "order_id",
      "销售数量": "sales_volume",
      "销量": "sales_volume",
      "预估回款金额": "estimated_settlement_amount"
    }
  },
  "domain_aliases": [
    {
      "aliases": [
        "订单编号",
        "订单号",
        "order_id",
        "order no",
        "order_no",
        "order id"
      ],
      "data_domain": "orders",
      "semantic_key": "order_id"
    },
    {
      "aliases": [
        "店铺",
        "店铺id",
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
        "下单时间",
        "下单日期",
        "订单日期",
        "订单时间",
        "order_date",
        "order time",
        "order_time"
      ],
      "data_domain": "orders",
      "semantic_key": "order_date"
    },
    {
      "aliases": [
        "销售数量",
        "出库数量",
        "销量",
        "sold_qty",
        "sales_volume",
        "quantity"
      ],
      "data_domain": "orders",
      "semantic_key": "sales_volume"
    },
    {
      "aliases": [
        "买家支付",
        "买家支付(rmb)",
        "买家支付（rmb）",
        "实付金额",
        "buyer_paid",
        "paid_amount"
      ],
      "data_domain": "orders",
      "semantic_key": "paid_amount"
    },
    {
      "aliases": [
        "利润",
        "利润(rmb)",
        "利润（rmb）",
        "profit",
        "profit_amount",
        "profit_rmb"
      ],
      "data_domain": "orders",
      "semantic_key": "profit"
    },
    {
      "aliases": [
        "预估回款金额",
        "预估回款金额(rmb)",
        "预估回款金额（rmb）",
        "estimated_settlement",
        "estimated_settlement_amount"
      ],
      "data_domain": "orders",
      "semantic_key": "estimated_settlement_amount"
    },
    {
      "aliases": [
        "结算时间",
        "settlement_time",
        "settlement date"
      ],
      "data_domain": "orders",
      "semantic_key": "settlement_time"
    },
    {
      "aliases": [
        "成本利润率",
        "cost_profit_rate"
      ],
      "data_domain": "orders",
      "semantic_key": "cost_profit_rate"
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
        "cvr"
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
      "label": "销售额",
      "option_group": "order_metric",
      "required": false,
      "semantic_key": "sales_amount",
      "system_scope": false
    },
    {
      "aliases": [
        "sales_volume",
        "sales volume",
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
    }
  ],
  "generated_at": "",
  "generated_by": "scripts/generate_semantic_field_snapshot.py",
  "hash_identity_keys": [
    "bounce_rate",
    "click_rate",
    "clicks",
    "conversion_rate",
    "gmv",
    "gmv_band",
    "impressions",
    "line_id",
    "live_attributed_gmv",
    "live_gmv",
    "live_indirect_gmv",
    "metric_date",
    "order_count",
    "order_date",
    "order_id",
    "page_views",
    "paid_amount",
    "period_end_date",
    "period_end_time",
    "period_start_date",
    "period_start_time",
    "platform_commission",
    "platform_sku",
    "product_id",
    "product_name",
    "product_visitor_count",
    "profit",
    "purchase_amount",
    "sales_amount",
    "sales_volume",
    "service_id",
    "shop_id",
    "sku_id",
    "sku_order_count",
    "total_transaction_amount",
    "video_attributed_gmv",
    "video_gmv",
    "video_indirect_gmv",
    "visitor_count",
    "warehouse_name"
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
            "cvr"
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
          "label": "销售额 (sales_amount)",
          "system_scope": false,
          "value": "sales_amount"
        },
        {
          "aliases": [
            "sales_volume",
            "sales volume",
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

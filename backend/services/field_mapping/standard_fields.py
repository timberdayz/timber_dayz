"""
标准字段定义 - 西虹ERP系统字段映射标准

定义完整的标准字段分类，用于智能字段映射
"""

# 产品基础信息字段
PRODUCT_BASIC_FIELDS = [
    'product_id',           # 商品ID
    'product_name',         # 商品名称
    'platform_sku',         # 平台SKU
    'category',             # 类目
    'item_status',          # 商品状态
    'variation_status',     # 变体状态
    'stock',                # 库存
    'price',                # 价格
    'currency',             # 币种
]

# 流量指标字段
TRAFFIC_METRIC_FIELDS = [
    'page_views',           # 页面浏览量 (PV)
    'unique_visitors',      # 访客数 (UV)
    'impressions',          # 曝光次数
    'clicks',               # 点击次数
    'click_rate',           # 点击率 (CTR)
]

# 转化指标字段
CONVERSION_METRIC_FIELDS = [
    'cart_add_count',       # 加购次数
    'cart_add_visitors',    # 加购访客数
    'order_count',          # 订单数
    'sold_count',           # 成交件数
    'conversion_rate',      # 转化率
    'gmv',                  # 成交金额
]

# 行为指标字段
BEHAVIOR_METRIC_FIELDS = [
    'bounce_rate',          # 跳出率
    'bounce_visitors',      # 跳出访客数
    'avg_session_duration', # 平均停留时长
    'pages_per_session',    # 平均页面数
]

# 商品评价字段
REVIEW_FIELDS = [
    'rating',               # 评分
    'review_count',         # 评价数
    'positive_rate',        # 好评率
]

# 订单字段
ORDER_FIELDS = [
    'order_id',             # 订单号
    'order_ts',             # 订单时间
    'order_status',         # 订单状态
    'buyer_id',             # 买家ID
    'quantity',             # 购买数量
    'unit_price',           # 单价
    'shipping_fee',         # 运费
    'discount_amount',      # 折扣金额
    'total_amount',         # 总金额
]

# 时间字段
TIME_FIELDS = [
    'metric_date',          # 指标日期
    'start_date',           # 开始日期
    'end_date',             # 结束日期
    'created_at',           # 创建时间
    'updated_at',           # 更新时间
]

# 所有标准字段的完整列表
ALL_STANDARD_FIELDS = (
    PRODUCT_BASIC_FIELDS + 
    TRAFFIC_METRIC_FIELDS + 
    CONVERSION_METRIC_FIELDS + 
    BEHAVIOR_METRIC_FIELDS + 
    REVIEW_FIELDS + 
    ORDER_FIELDS + 
    TIME_FIELDS
)

# 字段分类映射
FIELD_CATEGORIES = {
    'product_basic': PRODUCT_BASIC_FIELDS,
    'traffic_metrics': TRAFFIC_METRIC_FIELDS,
    'conversion_metrics': CONVERSION_METRIC_FIELDS,
    'behavior_metrics': BEHAVIOR_METRIC_FIELDS,
    'review_fields': REVIEW_FIELDS,
    'order_fields': ORDER_FIELDS,
    'time_fields': TIME_FIELDS,
}

def get_fields_by_category(category: str) -> list:
    """根据分类获取字段列表"""
    return FIELD_CATEGORIES.get(category, [])

def get_all_standard_fields() -> list:
    """获取所有标准字段"""
    return ALL_STANDARD_FIELDS

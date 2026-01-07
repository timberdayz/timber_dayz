export const ORDER_FIELDS = [
  'order_id', 'product_id', 'platform_sku', 'sku', 'status',
  'qty', 'unit_price', 'currency', 'order_ts', 'shipped_ts', 'returned_ts', 'gmv'
]

export const PRODUCT_FIELDS = [
  'product_id', 'product_name', 'platform_sku', 'sku', 'status',
  'price', 'currency', 'stock', 'category', 'brand', 'title',
  'description', 'image_url', 'rating', 'reviews'
]

export const TRAFFIC_FIELDS = [
  'date', 'shop_id', 'visits', 'page_views', 'bounce_rate',
  'avg_session_duration', 'platform_code', 'source', 'medium'
]

export const SERVICE_FIELDS = [
  'service_id', 'service_name', 'status', 'price', 'currency',
  'duration', 'category', 'description', 'provider'
]

export const METRIC_FIELDS = [
  'product_id', 'platform_sku', 'metric_date', 'granularity',
  'pv', 'uv', 'ctr', 'conversion', 'revenue',
  'stock', 'rating', 'reviews', 'title', 'brand', 'category'
]

export function getStandardFieldsByDomain(domain) {
  switch (domain) {
    case 'orders':
      return ORDER_FIELDS
    case 'products':
      return PRODUCT_FIELDS
    case 'traffic':
      return TRAFFIC_FIELDS
    case 'services':
      return SERVICE_FIELDS
    case 'metrics':
      return METRIC_FIELDS
    default:
      return PRODUCT_FIELDS // 默认返回产品字段
  }
}



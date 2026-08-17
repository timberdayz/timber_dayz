export function buildScopePayload(yearMonth, shops = []) {
  return {
    year_month: yearMonth,
    shops: shops.map((shop) => ({
      platform_code: shop.platform_code,
      shop_id: shop.shop_id,
      is_included: Boolean(shop.is_included),
      exclusion_reason: shop.is_included ? null : (shop.exclusion_reason || '').trim() || null
    }))
  }
}

export function buildEntryPayload(yearMonth, shops = []) {
  return {
    year_month: yearMonth,
    entries: shops.flatMap((shop) => (shop.metrics || []).map((metric) => {
      const entry = {
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        metric_code: metric.metric_code
      }
      if (metric.is_manual) entry.manual_score_value = metric.manual_score_value
      else entry.achieved_value = metric.achieved_value
      return entry
    }))
  }
}

export function getStoreEntryStatus(shop) {
  return (shop.metrics || []).every((metric) => metric.status === 'completed')
    ? 'completed'
    : 'pending'
}

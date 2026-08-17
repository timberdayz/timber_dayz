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
      const input = metric.input_payload || {}
      if (metric.input_kind === 'training_counts') {
        entry.completed_count = input.completed_count
        entry.required_count = input.required_count
      } else if (metric.input_kind === 'special_check') {
        entry.result = input.result
        entry.note = input.note || undefined
      } else {
        entry.actual_value = input.actual_value
      }
      return entry
    }))
  }
}

export function getStoreEntryStatus(shop) {
  return (shop.metrics || []).every((metric) => metric.status === 'completed')
    ? 'completed'
    : 'pending'
}

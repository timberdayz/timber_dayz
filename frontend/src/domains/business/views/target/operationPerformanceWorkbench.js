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
    entries: shops.flatMap((shop) => (shop.metrics || []).flatMap((metric) => {
      const input = metric.input_payload || {}
      const entry = {
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        metric_code: metric.metric_code
      }
      if (metric.input_kind === 'training_counts') {
        if (input.completed_count === null || input.completed_count === undefined || input.required_count === null || input.required_count === undefined) return []
        entry.completed_count = input.completed_count
        entry.required_count = input.required_count
      } else if (metric.input_kind === 'special_check') {
        if (!['passed', 'partial', 'failed'].includes(input.result)) return []
        const note = String(input.note || '').trim()
        if (['partial', 'failed'].includes(input.result) && !note) return []
        entry.result = input.result
        if (note) entry.note = note
      } else {
        if (input.actual_value === null || input.actual_value === undefined) return []
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

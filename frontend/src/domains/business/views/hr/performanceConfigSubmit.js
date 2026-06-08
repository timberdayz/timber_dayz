export function extractPerformanceConfigRow(response) {
  if (Array.isArray(response)) return response[0] || null
  if (!response) return null
  if (Array.isArray(response.data)) return response.data[0] || null
  return response.data || response || null
}

export function buildFormalPerformanceConfigPayload(configForm) {
  return {
    sales_max_score: Number(configForm.sales_max_score || 0),
    profit_max_score: Number(configForm.profit_max_score || 0),
    operation_max_score: Number(configForm.operation_max_score || 0)
  }
}

export async function savePerformanceConfig({
  api,
  currentConfigId,
  payload,
  effectiveFrom
}) {
  if (currentConfigId) {
    return api.updatePerformanceConfig(currentConfigId, payload)
  }
  return api.createPerformanceConfig({
    ...payload,
    effective_from: effectiveFrom
  })
}

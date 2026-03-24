export function normalizeSalesTargetsResponse(response) {
  if (Array.isArray(response)) {
    return response
  }

  if (Array.isArray(response?.data)) {
    return response.data
  }

  return []
}

export function buildSalesTargetMutationPayload(form) {
  return {
    target_sales_amount: Number(form?.target_sales_amount) || 0,
    target_order_count: Number(form?.target_order_count) || 0,
  }
}

export function getPageFamilyClass(family) {
  return family === 'dashboard' ? 'erp-page--dashboard' : 'erp-page--admin'
}

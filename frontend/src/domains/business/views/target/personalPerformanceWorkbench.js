export function allocatePersonalMetricScores(metrics) {
  const enabled = (metrics || [])
    .filter((metric) => metric.is_enabled)
    .sort((left, right) => Number(left.sort_key || 0) - Number(right.sort_key || 0) || String(left.metric_code).localeCompare(String(right.metric_code)))
  if (!enabled.length) return {}
  const base = Math.floor(20 / enabled.length)
  const remainder = 20 % enabled.length
  return Object.fromEntries(enabled.map((metric, index) => [metric.metric_code, base + (index < remainder ? 1 : 0)]))
}

export function buildPersonalScopePayload(yearMonth, expectedPlanVersion, employees) {
  return {
    year_month: yearMonth,
    expected_plan_version: expectedPlanVersion,
    employees: (employees || []).map((employee) => ({
      employee_code: employee.employee_code,
      is_included: Boolean(employee.is_included),
      exclusion_note: employee.is_included ? null : (String(employee.exclusion_note || '').trim() || null)
    }))
  }
}

function buildEntry(employeeCode, metric) {
  const payload = metric.input_payload || {}
  if (metric.input_kind === 'training_counts') {
    if (!Number.isInteger(payload.completed_count) || !Number.isInteger(payload.required_count)) return null
    return { employee_code: employeeCode, metric_code: metric.metric_code, completed_count: payload.completed_count, required_count: payload.required_count }
  }
  if (metric.input_kind === 'special_task') {
    if (!payload.result || (['partial', 'failed'].includes(payload.result) && !String(payload.note || '').trim())) return null
    return { employee_code: employeeCode, metric_code: metric.metric_code, result: payload.result, note: String(payload.note || '').trim() || null }
  }
  if (payload.actual_value == null || payload.actual_value === '') return null
  return { employee_code: employeeCode, metric_code: metric.metric_code, actual_value: Number(payload.actual_value) }
}

export function buildPersonalEntryPayload(yearMonth, expectedPlanVersion, employees) {
  return {
    year_month: yearMonth,
    expected_plan_version: expectedPlanVersion,
    entries: (employees || []).flatMap((employee) => (employee.metrics || []).map((metric) => buildEntry(employee.employee_code, metric)).filter(Boolean))
  }
}

export function isPersonalMetricComplete(metric) {
  const payload = metric.input_payload || {}
  if (metric.input_kind === 'training_counts') return Number.isInteger(payload.completed_count) && Number.isInteger(payload.required_count)
  if (metric.input_kind === 'special_task') return Boolean(payload.result) && (!['partial', 'failed'].includes(payload.result) || Boolean(String(payload.note || '').trim()))
  return payload.actual_value != null && payload.actual_value !== ''
}

export function formatPerformanceScore(value) {
  return value == null || value === '' || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(1)
}

export function isControlledPersonalMonth(workbench) {
  return workbench?.calculation_mode === 'controlled_targets_v1'
}

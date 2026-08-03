export const PERSON_TARGET_TYPES = ['sales', 'orders', 'customers']

function toNumber(value) {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number : 0
}

function achievementRate(actual, target) {
  return target ? actual / target : 0
}

export function buildEmployeeTargetSummary(source = {}) {
  const assignments = Array.isArray(source.assignments)
    ? source.assignments
    : (Array.isArray(source.shops) ? source.shops : [])
  const multiplier = source.valuesAlreadyAllocated ? 1 : null
  const shops = assignments.map((assignment) => {
    const ratio = toNumber(assignment.target_allocation_ratio)
    const allocationMultiplier = multiplier ?? ratio
    const salesTarget = toNumber(assignment.sales_target) * allocationMultiplier
    const salesActual = toNumber(assignment.sales_actual) * allocationMultiplier
    const grossProfitTarget = toNumber(assignment.gross_profit_target) * allocationMultiplier
    const grossProfitActual = toNumber(assignment.gross_profit_actual) * allocationMultiplier
    return {
      shop_name: assignment.shop_name || assignment.shop_id || '',
      target_allocation_ratio: ratio,
      sales_target: salesTarget,
      sales_actual: salesActual,
      sales_achievement_rate: achievementRate(salesActual, salesTarget),
      gross_profit_target: grossProfitTarget,
      gross_profit_actual: grossProfitActual,
      gross_profit_achievement_rate: achievementRate(grossProfitActual, grossProfitTarget)
    }
  })
  const salesTarget = shops.reduce((total, shop) => total + shop.sales_target, 0)
  const salesActual = shops.reduce((total, shop) => total + shop.sales_actual, 0)
  const grossProfitTarget = shops.reduce((total, shop) => total + shop.gross_profit_target, 0)
  const grossProfitActual = shops.reduce((total, shop) => total + shop.gross_profit_actual, 0)
  return {
    shops,
    sales_target: salesTarget,
    sales_actual: salesActual,
    sales_achievement_rate: achievementRate(salesActual, salesTarget),
    gross_profit_target: grossProfitTarget,
    gross_profit_actual: grossProfitActual,
    gross_profit_achievement_rate: achievementRate(grossProfitActual, grossProfitTarget)
  }
}

const INACTIVE_STATUSES = new Set(['inactive', 'disabled', 'leave', 'left', 'resigned', '离职', '停用'])

export function normalizeApiList(response) {
  if (Array.isArray(response)) return response
  if (Array.isArray(response?.items)) return response.items
  if (Array.isArray(response?.data)) return response.data
  if (Array.isArray(response?.data?.items)) return response.data.items
  return []
}

export function filterTargetEmployees(employees = []) {
  return normalizeApiList(employees).filter((employee) => {
    if (!employee?.employee_code) return false
    const status = String(employee.status || '').trim().toLowerCase()
    return !INACTIVE_STATUSES.has(status)
  })
}

export function createTargetCell(existingTarget = null) {
  return {
    id: existingTarget?.id || null,
    target_value: Number(existingTarget?.target_value || 0)
  }
}

export function buildPersonTargetRows(employees = [], targets = []) {
  const targetMap = new Map()
  normalizeApiList(targets).forEach((target) => {
    targetMap.set(`${target.employee_code}::${target.target_type}`, target)
  })

  return filterTargetEmployees(employees).map((employee) => {
    const row = {
      employee_code: employee.employee_code,
      name: employee.name || employee.employee_code,
      sales: createTargetCell(targetMap.get(`${employee.employee_code}::sales`)),
      orders: createTargetCell(targetMap.get(`${employee.employee_code}::orders`)),
      customers: createTargetCell(targetMap.get(`${employee.employee_code}::customers`))
    }
    row.hasExistingTarget = PERSON_TARGET_TYPES.some((type) => row[type].id)
    return row
  })
}

export function buildPersonTargetPayload(row, targetType, yearMonth) {
  const cell = row[targetType]
  return {
    employee_code: row.employee_code,
    year_month: yearMonth,
    target_type: targetType,
    target_value: Number(cell?.target_value || 0)
  }
}

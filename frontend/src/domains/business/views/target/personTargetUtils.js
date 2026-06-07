export const PERSON_TARGET_TYPES = ['sales', 'orders', 'customers']

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

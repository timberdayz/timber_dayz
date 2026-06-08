export function sumCommissionRatio(assignments = []) {
  return assignments.reduce((total, assignment) => {
    const nextValue = Number(assignment?.commission_ratio ?? 0)
    return total + (Number.isFinite(nextValue) ? nextValue : 0)
  }, 0)
}

export function exceedsCommissionRatioLimit(assignments = [], nextRatio = 0, excludePredicate = null) {
  const filteredAssignments = typeof excludePredicate === 'function'
    ? assignments.filter((assignment) => !excludePredicate(assignment))
    : assignments
  const total = sumCommissionRatio(filteredAssignments)
  const normalizedNextRatio = Number(nextRatio ?? 0)
  return total + (Number.isFinite(normalizedNextRatio) ? normalizedNextRatio : 0) > 1 + 1e-9
}

export function setShopAllocatableProfitRate(row, value) {
  const nextValue = Number(value ?? 0) / 100
  const normalizedValue = Number.isFinite(nextValue) ? nextValue : 0
  if (row && typeof row === 'object') {
    row.allocatable_profit_rate = normalizedValue
    if (row._shop && typeof row._shop === 'object') {
      row._shop.allocatable_profit_rate = normalizedValue
    }
  }
  return normalizedValue
}

function toFiniteNumber(value, fallback = 0) {
  const nextValue = Number(value ?? fallback)
  return Number.isFinite(nextValue) ? nextValue : fallback
}

export function inferAssignmentRole(employee) {
  const positionText = `${employee?.position_code ?? ''} ${employee?.position_name ?? ''}`.toLowerCase()
  if (
    positionText.includes('主管') ||
    positionText.includes('supv') ||
    positionText.includes('manager')
  ) {
    return 'supervisor'
  }
  return 'operator'
}

export function calculateAllocatableProfit(row) {
  const profitBasisAmount = toFiniteNumber(row?.profit_basis_amount, 0)
  const allocatableProfitRate = toFiniteNumber(row?.allocatable_profit_rate, 0)
  return Math.round(profitBasisAmount * allocatableProfitRate * 100) / 100
}

export function calculateAssignmentCommission(row, assignment) {
  const commissionRatio = toFiniteNumber(assignment?.commission_ratio, 0)
  return Math.round(calculateAllocatableProfit(row) * commissionRatio * 100) / 100
}

export function summarizeEmployeeCommissions(shopRows = []) {
  const summaryByEmployee = new Map()
  for (const shop of shopRows) {
    const assignments = Array.isArray(shop?.assignments) ? shop.assignments : []
    for (const assignment of assignments) {
      const employeeCode = assignment?.employee_code || ''
      if (!employeeCode) continue
      const current = summaryByEmployee.get(employeeCode) || {
        employee_code: employeeCode,
        employee_name: assignment?.employee_name || employeeCode,
        role: assignment?.role === 'supervisor' ? 'supervisor' : 'operator',
        shop_count: 0,
        estimated_commission: 0
      }
      current.shop_count += 1
      current.estimated_commission += calculateAssignmentCommission(shop, assignment)
      current.estimated_commission = Math.round(current.estimated_commission * 100) / 100
      summaryByEmployee.set(employeeCode, current)
    }
  }
  return Array.from(summaryByEmployee.values()).sort((a, b) => {
    const commissionDelta = b.estimated_commission - a.estimated_commission
    if (Math.abs(commissionDelta) > 1e-9) return commissionDelta
    return String(a.employee_code).localeCompare(String(b.employee_code))
  })
}

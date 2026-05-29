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

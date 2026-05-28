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

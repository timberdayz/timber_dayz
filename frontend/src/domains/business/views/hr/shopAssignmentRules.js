/**
 * 人员店铺归属页的纯计算 / 汇总辅助。
 *
 * 【口径归属：钱由后端算，前端只做乘法】
 *
 * 月度结算链路唯一的金额口径在服务端：
 *   预计提成 = max(利润基数, 0) × 可分配率 × 归属提成比 × 结算系数
 * 其中：
 *   * 利润基数 profit_basis_amount  —— 后端下发（结算口径已收敛为唯一的「结算基数」）；
 *   * 结算系数 settlement_coefficient —— 后端下发，
 *     定义为 min(店铺结算系数, 个人分数档位系数)，绩效工资和提成都用它；
 *   * 可分配率、归属提成比 —— 运营在页面上改的配置。
 *
 * 所以前端**不再自己复刻后端公式**：
 *   * 已保存的配置：预计提成直接展示后端返回的
 *     shops[].estimated_commission / employees[].expected_commission；
 *   * 用户改了还没保存：只允许用上面那**一条乘法链**做试算，
 *     并且利润基数和结算系数必须取后端值 —— 前端不自己定义口径。
 */

function toFiniteNumber(value, fallback = 0) {
  const nextValue = Number(value ?? fallback)
  return Number.isFinite(nextValue) ? nextValue : fallback
}

export function sumCommissionRatio(assignments = []) {
  return assignments.reduce((total, assignment) => {
    const nextValue = Number(assignment?.commission_ratio ?? 0)
    return total + (Number.isFinite(nextValue) ? nextValue : 0)
  }, 0)
}

export function summarizeTargetAllocationRisk(assignments = []) {
  const total = assignments.reduce((sum, assignment) => {
    const value = Number(assignment?.target_allocation_ratio ?? 0)
    return sum + (Number.isFinite(value) ? value : 0)
  }, 0)
  return { total, hasRisk: Math.abs(total - 1) > 1e-9 }
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

/**
 * 前端唯一允许的金额计算：未保存编辑的试算。
 *
 *   预计提成 = max(利润基数, 0) × 可分配率 × 归属提成比 × 结算系数
 *
 * 重要约束：
 *   * 利润基数（profit_basis_amount）来自后端；
 *   * 结算系数（settlement_coefficient）来自后端；
 *   * 前端只做这条乘法，不自己定义口径、不自己推导系数、不兜底猜测业务规则。
 *
 * @param {Object} input
 * @param {number} input.profit_basis_amount 后端下发的利润基数
 * @param {number} input.allocatable_profit_rate 当前可分配率（可能是用户刚改的）
 * @param {number} input.commission_ratio 当前归属提成比（可能是用户刚改的）
 * @param {number} input.settlement_coefficient 后端下发的结算系数
 * @returns {number} 试算出的预计提成，保留 2 位小数
 */
export function calculateTrialCommission({
  profit_basis_amount,
  allocatable_profit_rate,
  commission_ratio,
  settlement_coefficient
} = {}) {
  const profitBasisAmount = toFiniteNumber(profit_basis_amount, 0)
  const allocatableProfitRate = toFiniteNumber(allocatable_profit_rate, 0)
  const commissionRatio = toFiniteNumber(commission_ratio, 0)
  const coefficient = toFiniteNumber(settlement_coefficient, 1)
  const amount = Math.max(profitBasisAmount, 0) * allocatableProfitRate * commissionRatio * coefficient
  return Math.round(amount * 100) / 100
}

/**
 * 读取后端算好的可分配利润。
 * 后端已经按 2 位小数舍入，前端直接用，不自己再算一遍。
 */
export function readBackendAllocatableProfit(row) {
  const value = row?.allocatable_profit_amount
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

/**
 * 判断某个归属行是不是「用户改了还没保存」。
 *
 * _backend_allocatable_profit_rate / _backend_commission_ratio 是加载时
 * 从后端数据存下来的原始值，页面编辑不会覆盖它们。
 */
export function isAssignmentDirty(shop, assignment) {
  const currentRate = toFiniteNumber(shop?.allocatable_profit_rate, 0)
  const backendRate = toFiniteNumber(shop?._backend_allocatable_profit_rate, currentRate)
  const currentRatio = toFiniteNumber(assignment?.commission_ratio, 0)
  const backendRatio = toFiniteNumber(assignment?._backend_commission_ratio, currentRatio)
  return (
    Math.abs(currentRate - backendRate) > 1e-9 ||
    Math.abs(currentRatio - backendRatio) > 1e-9
  )
}

/**
 * 预计提成的展示值：
 *   * 没改过（保存过的配置）→ 直接用后端的 estimated_commission；
 *   * 改了还没保存        → 用前端唯一允许的乘法链试算。
 */
export function resolveEstimatedCommission({
  backendEstimatedCommission = null,
  dirty = false,
  trial = null
} = {}) {
  if (!dirty && backendEstimatedCommission !== null && backendEstimatedCommission !== undefined) {
    return backendEstimatedCommission
  }
  return calculateTrialCommission(trial)
}

/**
 * 员工月度预计提成汇总。
 *
 * 输入是后端 settlement-preview 返回的 employees 数组，
 * 金额直接读 employees[].expected_commission —— 前端不再自己累加。
 *
 * @param {Array} previewEmployees 后端 employees 数组
 * @param {Object} roleByEmployee 员工角色映射（预览接口不返回角色，页面的归属数据里有）
 */
export function summarizeEmployeeCommissions(previewEmployees = [], roleByEmployee = {}) {
  const list = Array.isArray(previewEmployees) ? previewEmployees : []
  return list
    .filter((employee) => Boolean(employee?.employee_code))
    .map((employee) => ({
      employee_code: employee.employee_code,
      employee_name: employee.employee_name || employee.employee_code,
      role: roleByEmployee?.[employee.employee_code] === 'supervisor' ? 'supervisor' : 'operator',
      shop_count: Array.isArray(employee?.shops) ? employee.shops.length : 0,
      estimated_commission: toFiniteNumber(employee?.expected_commission, 0),
      calculation_status: String(employee?.calculation_status ?? ''),
      performance_score: employee?.performance_score ?? null,
      score_coefficient: employee?.score_coefficient ?? null,
      settlement_coefficient: employee?.settlement_coefficient ?? null
    }))
    .sort((a, b) => {
      const commissionDelta = b.estimated_commission - a.estimated_commission
      if (Math.abs(commissionDelta) > 1e-9) return commissionDelta
      return String(a.employee_code).localeCompare(String(b.employee_code))
    })
}

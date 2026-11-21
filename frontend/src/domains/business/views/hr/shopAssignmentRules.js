/**
 * 人员店铺归属页的纯计算 / 汇总辅助。
 *
 * 【口径归属：钱由后端算，前端只渲染】
 *
 * 月度结算链路唯一的金额口径在服务端（`backend/services/commission_caliber`）：
 *
 *   可分配利润 = max(利润基数, 0) × 可分配率
 *   某员工从某店分到的提成 = 可分配利润 × 归属提成比      # 零系数
 *
 * 所以前端**不再复刻任何公式**：
 *
 *   * 已保存的配置：预计提成直接展示后端结算预览返回的 `estimated_commission`；
 *   * 改了还没保存：前端只把**待保存的输入**（可分配率、归属提成比）交给
 *     后端试算接口 `POST /hr/commissions/settlement-preview/estimate`，
 *     由后端按同一套口径算钱，页面只渲染返回的金额。
 *
 * 换句话说：这个文件里**不允许**出现「利润基数 × 系数 × 提成比」这类乘法。
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
 * 「员工 × 店铺」的稳定键：后端返回的试算行与页面行按这个键对齐。
 */
export function estimateKey({ employee_code, platform_code, shop_id } = {}) {
  const employee = String(employee_code ?? '').trim()
  const platform = String(platform_code ?? '').trim().toLowerCase()
  const shop = String(shop_id ?? '').trim()
  return `${employee}|${platform}|${shop}`
}

/**
 * 收集「改了还没保存」的行，整理成后端试算接口要的**输入**。
 *
 * ⚠️ 这里只搬运**输入**（可分配率、归属提成比），**不含任何金额**。
 * 金额由后端按唯一口径算 —— 前端不自己乘。
 *
 * @param {Array} rows 配置表的扁平行（含 `_shop` / `_person`）
 * @param {(row: Object) => boolean} [isDirty] 判断某行是否被改过
 * @returns {Array} 后端试算接口的 overrides 数组
 */
export function collectEstimateOverrides(rows = [], isDirty = null) {
  const list = Array.isArray(rows) ? rows : []
  const overrides = []
  for (const row of list) {
    const person = row?._person
    if (!person?.employee_code) continue
    if (typeof isDirty === 'function' && !isDirty(row)) continue
    const shop = row?._shop || row
    overrides.push({
      employee_code: String(person.employee_code),
      platform_code: String(shop?.platform_code ?? '').trim().toLowerCase(),
      shop_id: String(shop?.shop_id ?? ''),
      commission_ratio: toFiniteNumber(person.commission_ratio, 0),
      allocatable_profit_rate: toFiniteNumber(shop?.allocatable_profit_rate, 0)
    })
  }
  return overrides
}

/**
 * 把后端返回的试算行建成索引，页面按「员工 × 店铺」取用。
 */
export function indexEstimateRows(rows = []) {
  const map = new Map()
  for (const row of Array.isArray(rows) ? rows : []) {
    map.set(estimateKey(row), row)
  }
  return map
}

/**
 * 预计提成的展示值：
 *   * 有试算结果（改了还没保存）→ 用后端试算返回的金额；
 *   * 否则                      → 用后端结算预览返回的金额。
 *
 * 两条路径都是后端算的，前端不做任何乘法。
 */
export function resolveEstimatedCommission({
  backendEstimatedCommission = null,
  estimateAmount = null
} = {}) {
  if (estimateAmount !== null && estimateAmount !== undefined) return estimateAmount
  if (backendEstimatedCommission !== null && backendEstimatedCommission !== undefined) {
    return backendEstimatedCommission
  }
  return null
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

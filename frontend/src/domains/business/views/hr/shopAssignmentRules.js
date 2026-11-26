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

/**
 * 员工没挂职位时的展示文案。
 */
export const POSITION_UNSET_LABEL = '（未设岗位）'

/**
 * 「员工工号 → 职位名」索引。
 *
 * 层级只是**展示**：职位名来自员工档案，不落库、不需要用户勾选。
 *
 * @param {Array} employees 员工档案列表（含 employee_code / position_name）
 * @returns {Object} { [employee_code]: position_name }
 */
export function buildPositionNameMap(employees = []) {
  const map = {}
  for (const employee of Array.isArray(employees) ? employees : []) {
    const code = String(employee?.employee_code ?? '').trim()
    if (!code) continue
    const positionName = String(employee?.position_name ?? '').trim()
    if (!positionName) continue
    map[code] = positionName
  }
  return map
}

/**
 * 取员工的职位名；取不到时显示「（未设岗位）」，不让页面出现空白。
 */
export function resolvePositionName(employeeCode, positionByEmployee = {}) {
  const code = String(employeeCode ?? '').trim()
  const positionName = String(positionByEmployee?.[code] ?? '').trim()
  return positionName || POSITION_UNSET_LABEL
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
 * 层级只展示员工档案里的**职位名**（没有角色概念，也不落库）。
 *
 * @param {Array} previewEmployees 后端 employees 数组
 * @param {Object} positionByEmployee 员工工号 → 职位名 映射
 */
export function summarizeEmployeeCommissions(previewEmployees = [], positionByEmployee = {}) {
  const list = Array.isArray(previewEmployees) ? previewEmployees : []
  return list
    .filter((employee) => Boolean(employee?.employee_code))
    .map((employee) => ({
      employee_code: employee.employee_code,
      employee_name: employee.employee_name || employee.employee_code,
      position_name: resolvePositionName(employee.employee_code, positionByEmployee),
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

/**
 * 批量挂靠：把「选中的店铺 + 1 名员工 + 统一比例」整理成批量端点的 items。
 *
 * 只搬**输入**（定位键 + 提成比例），不含任何金额。
 *
 * @param {Array} shops 选中的店铺
 * @param {String} employeeCode 员工工号
 * @param {Number} commissionRatio 提成比例（0-1 之间的小数）
 * @returns {Array} 批量端点的 items
 */
export function buildBatchCreateItems(shops = [], employeeCode = '', commissionRatio = 0) {
  const list = Array.isArray(shops) ? shops : []
  const code = String(employeeCode ?? '').trim()
  const ratio = toFiniteNumber(commissionRatio, 0)
  const items = []
  if (!code) return items
  for (const shop of list) {
    items.push({
      employee_code: code,
      platform_code: String(shop?.platform_code ?? '').trim().toLowerCase(),
      shop_id: String(shop?.shop_id ?? ''),
      commission_ratio: ratio
    })
  }
  return items
}

/**
 * 批量改比例：对选中店铺里已配置的人员行统一设比例。
 *
 * items 与 assignment_ids 一一对应（同一顺序、同一长度），后端按定位键或按 id 都能对上。
 * 没有 id 的行（本地刚加、还没保存的新增行）不参与批量提交 —— 批量端点只改已落库的归属。
 *
 * @param {Array} rows 人员行（含 employee_code / platform_code / shop_id / id）
 * @param {Number} commissionRatio 新的提成比例
 * @returns {{ items: Array, assignment_ids: Array }}
 */
export function buildBatchUpdatePayload(rows = [], commissionRatio = 0) {
  const list = Array.isArray(rows) ? rows : []
  const ratio = toFiniteNumber(commissionRatio, 0)
  const items = []
  const assignmentIds = []
  for (const row of list) {
    const employeeCode = String(row?.employee_code ?? '').trim()
    if (!employeeCode) continue
    if (row?.id === null || row?.id === undefined) continue
    items.push({
      employee_code: employeeCode,
      platform_code: String(row?.platform_code ?? '').trim().toLowerCase(),
      shop_id: String(row?.shop_id ?? ''),
      commission_ratio: ratio
    })
    assignmentIds.push(row.id)
  }
  return { items, assignment_ids: assignmentIds }
}

/**
 * 批量移除：收集选中店铺下全部归属行的 id。
 *
 * @param {Array} shops 选中的店铺
 * @returns {Array} 归属行 id 列表
 */
export function collectAssignmentIds(shops = []) {
  const list = Array.isArray(shops) ? shops : []
  const ids = []
  for (const shop of list) {
    for (const assignment of shop?.assignments || []) {
      if (assignment?.id === null || assignment?.id === undefined) continue
      ids.push(assignment.id)
    }
  }
  return ids
}

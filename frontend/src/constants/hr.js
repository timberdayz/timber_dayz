/**
 * 人力资源状态词表 —— 前端唯一真源（SSOT）
 *
 * 与后端 `backend/services/hr_employee_lifecycle.py` 的词表保持一致：
 * - `backend/services/hr_employee_lifecycle.py::EMPLOYEE_STATUS_VOCABULARY`
 * - `backend/services/hr_employee_lifecycle.py::EMPLOYEE_IDENTITY_VOCABULARY`
 * - `backend/services/hr_employee_lifecycle.py::PAYROLL_STATUS_VOCABULARY`
 *
 * 三个概念互不兼职：
 * - 用工身份（employee_identity_type）：访客 / 正式员工 —— 只管「能不能进人力链路」
 * - 在职状态（status）：在职 / 试用期 / 停薪留职 / 已离职 —— 只管「这个人还在不在职」
 * - 发钱边界（last_payroll_month）：最后可结算的工资月 —— 只管「钱能发到哪个月」
 *
 * 页面禁止再硬编码中文映射或直接输出英文原值，一律走这里的函数。
 */

/** 在职状态取值 */
export const EMPLOYEE_STATUS = {
  ACTIVE: 'active',
  PROBATION: 'probation',
  LEAVE: 'leave',
  INACTIVE: 'inactive'
}

/** 在职状态中文名 */
export const EMPLOYEE_STATUS_LABEL = {
  active: '在职',
  probation: '试用期',
  leave: '停薪留职',
  inactive: '已离职'
}

/** 在职状态标签色（Element Plus el-tag type） */
export const EMPLOYEE_STATUS_TAG_TYPE = {
  active: 'success',
  probation: 'warning',
  leave: 'info',
  inactive: 'danger'
}

/** 用工身份取值 */
export const EMPLOYEE_IDENTITY = {
  EMPLOYEE: 'employee',
  VISITOR: 'visitor'
}

/** 用工身份中文名 */
export const EMPLOYEE_IDENTITY_LABEL = {
  employee: '正式员工',
  visitor: '访客'
}

/** 工资单状态中文名 */
export const PAYROLL_STATUS_LABEL = {
  draft: '草稿',
  confirmed: '已确认',
  paid: '已发放',
  void: '已作废',
  // 历史遗留状态：老版本工资单用过 approved，当前词表已不再产生，
  // 但仍要有中文名 —— 否则页面上会直接甩出英文原值。
  approved: '已审批（历史状态）'
}

/** 工资单状态标签色（Element Plus el-tag type） */
export const PAYROLL_STATUS_TAG_TYPE = {
  draft: 'info',
  confirmed: 'warning',
  paid: 'success',
  void: 'danger',
  approved: 'info'
}

/** 未知取值的兜底文案（避免把 null / undefined / 空串直接甩到页面上） */
const UNKNOWN_LABEL = '未知'

/**
 * 归一化后端取值：去空白 + 转小写。
 * 任何异常输入都返回空串，绝不抛错。
 */
function normalizeKey(value) {
  if (value === null || value === undefined) return ''
  if (typeof value !== 'string') return ''
  return value.trim().toLowerCase()
}

/**
 * 在职状态中文名；未知取值回退到原值（便于排查脏数据），不抛错。
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function employeeStatusLabel(status) {
  const key = normalizeKey(status)
  if (!key) return UNKNOWN_LABEL
  return EMPLOYEE_STATUS_LABEL[key] || String(status)
}

/**
 * 在职状态标签色；未知取值回退 info，不抛错。
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function employeeStatusTagType(status) {
  const key = normalizeKey(status)
  if (!key) return 'info'
  return EMPLOYEE_STATUS_TAG_TYPE[key] || 'info'
}

/**
 * 用工身份中文名；未知取值回退到原值，不抛错。
 * @param {string|null|undefined} identity
 * @returns {string}
 */
export function employeeIdentityLabel(identity) {
  const key = normalizeKey(identity)
  if (!key) return UNKNOWN_LABEL
  return EMPLOYEE_IDENTITY_LABEL[key] || String(identity)
}

/**
 * 工资单状态中文名；未知取值回退到原值，不抛错。
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function payrollStatusLabel(status) {
  const key = normalizeKey(status)
  if (!key) return UNKNOWN_LABEL
  return PAYROLL_STATUS_LABEL[key] || String(status)
}

/**
 * 工资单状态标签色；未知取值回退 info，不抛错。
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function payrollStatusTagType(status) {
  const key = normalizeKey(status)
  if (!key) return 'info'
  return PAYROLL_STATUS_TAG_TYPE[key] || 'info'
}

/**
 * 是否为「已离职」；入参异常一律按「非离职」处理，不抛错。
 * @param {string|null|undefined} status
 * @returns {boolean}
 */
export function isInactiveEmployeeStatus(status) {
  return normalizeKey(status) === EMPLOYEE_STATUS.INACTIVE
}

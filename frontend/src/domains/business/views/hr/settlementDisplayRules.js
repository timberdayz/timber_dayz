/**
 * 月度结算链路的「业务化显示规则」。
 *
 * 背景：后端已经把「钱怎么算」收敛成唯一一套口径
 *   预计提成 = max(利润基数, 0) × 可分配率 × 归属提成比 × 结算系数
 * 前端不再复刻这个公式，只负责把后端返回的**结论**翻译成人能看懂的文字。
 *
 * 这个模块集中处理三件事，页面里不要各自另写一套：
 * 1. 口径版本（basis_version）-> 业务标签；
 * 2. 考核 / 结算状态 -> 徽标文案与颜色；
 * 3. 「提成为 0」的业务原因，以及「没配」和「配成 0」的区别。
 *
 * 术语对照（给运营看）：
 *   - 结算系数   = min(店铺结算系数, 个人分数档位系数)，绩效工资和提成都用它；
 *   - 店铺结算系数 = min(该店排名档位系数, 该店分数档位系数)；
 *   - 可分配率 = 该店当月愿意拿出来分给归属人员的利润比例。
 */

/** 当前系统唯一的利润基数口径（后端 LaborCostPolicyService.CURRENT_BASIS_VERSION）。 */
export const CURRENT_BASIS_VERSION = 'SETTLEMENT_BASIS_V1'

/**
 * 口径版本 -> 业务标签。
 *
 * 历史值只用于识别「这条数据是哪个时期按什么口径算出来的」，
 * 不再重建、不再作为新建快照的默认值，所以统一显示成「历史口径 …」。
 *
 * **现行口径不带版本号**：系统只有一套口径，页面不应该再出现
 * 「V1 / V2」这种过渡期命名，否则运营会以为还有别的口径在并行。
 */
export const BASIS_VERSION_LABELS = {
  SETTLEMENT_BASIS_V1: '结算基数（现行口径）',
  A_ONLY_V1: '历史口径（仅 A 类成本）',
  A_PRE_COMMISSION_LABOR_V2: '历史口径（扣提成前人力成本）'
}

/**
 * 把后端的口径代号翻译成业务标签。
 * 不认识的代号也照样显示原文，方便排查，而不是静默显示成当前口径。
 */
export function formatBasisVersion(version) {
  const key = String(version ?? '').trim()
  if (!key) return '口径未标注'
  return BASIS_VERSION_LABELS[key] || `未知口径（${key}）`
}

/** 是否是已经停用的历史口径（只用于提示，不用于重建）。 */
export function isHistoricalBasisVersion(version) {
  const key = String(version ?? '').trim()
  return key === 'A_ONLY_V1' || key === 'A_PRE_COMMISSION_LABOR_V2'
}

/**
 * 「结算基数（参考）」列的表头提示。
 *
 * 为什么叫「参考」而不是「提成计算基数」：
 * 这一列显示的是**当月结算利润基数的估算参考值**，对
 * 「本月不参与考核」的店铺（例如当月没有任何经营数据），
 * 后端给的是现场估算值，与该店结算快照里的口径可能不完全一致。
 * 叫「提成计算基数」会让人以为这一列就是提成实际用的数。
 *
 * 关键区别：**无论参考值是多少，本店本月实发提成一律按结算快照计算**，
 * 参考值只用来解释「为什么这家店提成为 0」。
 */
export const PROFIT_BASIS_REFERENCE_HINT =
  '参考值：当月结算利润基数的估算口径（订单利润 − 其他经营成本 − 提成前人力成本）。' +
  '未参与本月考核的店铺显示的是现场估算参考值，与结算快照口径可能不完全一致；' +
  '无论参考值是多少，本店本月实发提成一律按结算快照计算。'

/**
 * 系数显示：没有值就显示「—」，不要显示 0。
 * 0 和「没有这个系数」业务含义完全不同（0 是被压档，— 是不参与）。
 */
export function formatCoefficient(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return numeric.toFixed(2)
}

/**
 * 可分配率的三态。
 *
 * 「没配」和「配成 0」在金额上都是 0，但业务含义完全不同：
 *   - 没配   = 忘了配，该店本月不参与提成分配；
 *   - 配成 0 = 决定本月不分，属于策略性设置。
 * 后端用 is_allocatable_rate_configured 区分，页面必须能分开显示。
 */
export function describeAllocatableRate(isConfigured, rate) {
  const numeric = Number(rate ?? 0)
  const percent = Number.isFinite(numeric) ? Number((numeric * 100).toFixed(2)) : 0
  if (!isConfigured) {
    return { label: '未配置', type: 'warning', percent, text: '未配置可分配率，该店本月不参与提成分配' }
  }
  if (numeric <= 0) {
    return { label: '0%', type: 'info', percent, text: '可分配率为 0，该店本月不参与提成分配' }
  }
  return { label: `${percent}%`, type: 'success', percent, text: `可分配率 ${percent}%` }
}

/**
 * 员工考核状态（后端 settlement-preview 的 employees[].calculation_status）：
 *   complete              正常参与考核
 *   not_participating     不参与考核（如总部、仓库、客服）
 *   pending_personal_input  待录入个人绩效
 *   pending_store_performance 待店铺绩效
 */
export function employeeCalculationStatusTag(status) {
  switch (String(status ?? '').trim()) {
  case 'complete':
    return { label: '正常参与考核', type: 'success' }
  case 'not_participating':
    return { label: '不参与考核', type: 'info' }
  case 'pending_personal_input':
  case 'pending_store_performance':
    return { label: '待补数据', type: 'warning' }
  default:
    return null
  }
}

/**
 * 店铺考核状态（绩效页 score_details.summary.calculation_status）：
 *   complete       正式计算完成
 *   partial        数据不全，属于预估
 *   not_applicable 本月不参与考核（例如当月没有任何经营数据）
 */
export function shopCalculationStatusTag(status) {
  switch (String(status ?? '').trim()) {
  case 'complete':
    return { label: '正常参与考核', type: 'success' }
  case 'partial':
    return { label: '待补数据', type: 'warning' }
  case 'not_applicable':
    return { label: '本月不参与考核', type: 'info' }
  default:
    return null
  }
}

/**
 * 店铺利润维度状态（绩效页 score_details.profit.status）：
 *   calculated     正常算出利润
 *   loss           本月亏损，按规则不计提成
 *   pending_target 还没配结算利润目标
 */
export function profitStatusTag(status) {
  switch (String(status ?? '').trim()) {
  case 'calculated':
    return { label: '利润已计算', type: 'success' }
  case 'loss':
    return { label: '亏损', type: 'danger' }
  case 'pending_target':
    return { label: '待补数据', type: 'warning' }
  default:
    return null
  }
}

/**
 * 店铺亏损判定（店铺归属页用）。
 * 这里只比较后端已经算好的金额，不在前端重新推导利润口径。
 */
export function describeShopProfitTag(row) {
  const basis = Number(row?.profit_basis_amount)
  const profit = Number(row?.monthly_profit)
  if (Number.isFinite(basis) && basis < 0) {
    return { label: '亏损', type: 'danger', text: '本店本月结算利润为负（亏损），按规则不计提成' }
  }
  if (Number.isFinite(profit) && profit < 0) {
    return { label: '亏损', type: 'danger', text: '本店本月利润为负（亏损），按规则不计提成' }
  }
  return null
}

/**
 * 零提成原因：把后端给的业务原因原样带给运营。
 * 没有原因（null）就返回空串，页面不用显示任何提示。
 */
export function formatCommissionZeroReason(reason) {
  return String(reason ?? '').trim()
}

/** 是否需要展示「提成为 0」的原因提示。 */
export function hasCommissionZeroReason(reason) {
  return formatCommissionZeroReason(reason).length > 0
}

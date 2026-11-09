import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CURRENT_BASIS_VERSION,
  describeAllocatableRate,
  describeShopProfitTag,
  employeeCalculationStatusTag,
  formatBasisVersion,
  formatCommissionZeroReason,
  formatCoefficient,
  hasCommissionZeroReason,
  isHistoricalBasisVersion,
  PROFIT_BASIS_REFERENCE_HINT,
  profitStatusTag,
  shopCalculationStatusTag
} from '../src/domains/business/views/hr/settlementDisplayRules.js'

test('口径版本翻译成人能看懂的业务标签，不把内部代号甩给用户', () => {
  // 现行口径不带版本号：系统只有一套口径，页面不该再出现 V1 / V2
  assert.equal(formatBasisVersion('SETTLEMENT_BASIS_V1'), '结算基数（现行口径）')
  assert.equal(CURRENT_BASIS_VERSION, 'SETTLEMENT_BASIS_V1')

  assert.match(formatBasisVersion('A_ONLY_V1'), /历史口径/)
  assert.match(formatBasisVersion('A_PRE_COMMISSION_LABOR_V2'), /历史口径/)

  assert.equal(formatBasisVersion(''), '口径未标注')
  assert.equal(formatBasisVersion(null), '口径未标注')
  // 不认识的代号也要显示出来，不能静默当成当前口径
  assert.match(formatBasisVersion('SOMETHING_NEW'), /SOMETHING_NEW/)
})

test('页面上不再出现过渡期的 V1 / V2 文案', () => {
  assert.doesNotMatch(formatBasisVersion('SETTLEMENT_BASIS_V1'), /V1|V2/)
})

test('历史口径只用于识别旧快照，不用于重建', () => {
  assert.equal(isHistoricalBasisVersion('A_ONLY_V1'), true)
  assert.equal(isHistoricalBasisVersion('A_PRE_COMMISSION_LABOR_V2'), true)
  assert.equal(isHistoricalBasisVersion('SETTLEMENT_BASIS_V1'), false)
  assert.equal(isHistoricalBasisVersion(''), false)
})

test('系数为空时显示「—」，不显示 0', () => {
  assert.equal(formatCoefficient(null), '—')
  assert.equal(formatCoefficient(undefined), '—')
  assert.equal(formatCoefficient(''), '—')
  // 0 是真的被压档，必须和「没有这个系数」区分开
  assert.equal(formatCoefficient(0), '0.00')
  assert.equal(formatCoefficient(1), '1.00')
  assert.equal(formatCoefficient(0.85), '0.85')
})

test('可分配率区分「没配」和「配成 0」', () => {
  const notConfigured = describeAllocatableRate(false, 0)
  assert.equal(notConfigured.label, '未配置')
  assert.equal(notConfigured.type, 'warning')
  assert.match(notConfigured.text, /未配置/)

  const configuredZero = describeAllocatableRate(true, 0)
  assert.equal(configuredZero.label, '0%')
  assert.equal(configuredZero.type, 'info')
  assert.match(configuredZero.text, /可分配率为 0/)

  const configured = describeAllocatableRate(true, 0.25)
  assert.equal(configured.label, '25%')
  assert.equal(configured.type, 'success')
})

test('员工考核状态徽标区分不参与与待补数据', () => {
  assert.deepEqual(employeeCalculationStatusTag('complete'), { label: '正常参与考核', type: 'success' })
  assert.deepEqual(employeeCalculationStatusTag('not_participating'), { label: '不参与考核', type: 'info' })
  assert.deepEqual(employeeCalculationStatusTag('pending_personal_input'), { label: '待补数据', type: 'warning' })
  assert.deepEqual(employeeCalculationStatusTag('pending_store_performance'), { label: '待补数据', type: 'warning' })
  assert.equal(employeeCalculationStatusTag(''), null)
  assert.equal(employeeCalculationStatusTag(undefined), null)
})

test('店铺考核状态与利润状态徽标可区分', () => {
  assert.deepEqual(shopCalculationStatusTag('not_applicable'), { label: '本月不参与考核', type: 'info' })
  assert.deepEqual(shopCalculationStatusTag('partial'), { label: '待补数据', type: 'warning' })
  assert.deepEqual(shopCalculationStatusTag('complete'), { label: '正常参与考核', type: 'success' })

  assert.deepEqual(profitStatusTag('loss'), { label: '亏损', type: 'danger' })
  assert.deepEqual(profitStatusTag('calculated'), { label: '利润已计算', type: 'success' })
  assert.deepEqual(profitStatusTag('pending_target'), { label: '待补数据', type: 'warning' })
})

test('店铺亏损判定只看后端给的金额，前端不重新推导利润口径', () => {
  const loss = describeShopProfitTag({ profit_basis_amount: -120, monthly_profit: 50 })
  assert.equal(loss.label, '亏损')
  assert.equal(loss.type, 'danger')

  assert.equal(describeShopProfitTag({ profit_basis_amount: 100, monthly_profit: 100 }), null)
  assert.equal(describeShopProfitTag(null), null)
})

test('零提成原因能取出来，没有原因时返回空串', () => {
  assert.equal(formatCommissionZeroReason('未配置可分配率，该店本月不参与提成分配'), '未配置可分配率，该店本月不参与提成分配')
  assert.equal(formatCommissionZeroReason(null), '')
  assert.equal(formatCommissionZeroReason(undefined), '')
  assert.equal(hasCommissionZeroReason('本店本月结算利润为负（亏损），按规则不计提成'), true)
  assert.equal(hasCommissionZeroReason(null), false)
})

test('结算基数（参考）提示说清参考值与实发口径的区别', () => {
  assert.match(PROFIT_BASIS_REFERENCE_HINT, /参考/)
  // 必须讲清楚「实发提成按结算快照算」，否则运营会拿这一列去核提成
  assert.match(PROFIT_BASIS_REFERENCE_HINT, /结算快照/)
  assert.doesNotMatch(PROFIT_BASIS_REFERENCE_HINT, /提成计算基数/)
})

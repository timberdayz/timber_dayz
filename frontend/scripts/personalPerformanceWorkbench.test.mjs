import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import {
  allocatePersonalMetricScores,
  buildPersonalEntryPayload,
  buildPersonalScopePayload,
  formatPerformanceScore,
  isControlledPersonalMonth
} from '../src/domains/business/views/target/personalPerformanceWorkbench.js'
import { getControlledPersonalAuditNotice } from '../src/domains/business/views/hr/incomeAuditStatus.js'

test('personal metrics allocate the fixed twenty point budget by catalog order', () => {
  assert.deepEqual(allocatePersonalMetricScores([
    { metric_code: 'attendance', is_enabled: true, sort_key: 10 },
    { metric_code: 'training_completion_rate', is_enabled: true, sort_key: 20 },
    { metric_code: 'personal_target_completion_rate', is_enabled: true, sort_key: 30 }
  ]), {
    attendance: 7,
    training_completion_rate: 7,
    personal_target_completion_rate: 6
  })
})

test('personal entry payload includes only complete structured inputs', () => {
  const payload = buildPersonalEntryPayload('2026-09', 3, [
    {
      employee_code: 'EMP001',
      metrics: [
        { metric_code: 'attendance', input_kind: 'percentage', input_payload: { actual_value: 98 } },
        { metric_code: 'training_completion_rate', input_kind: 'training_counts', input_payload: { completed_count: 9, required_count: 10 } },
        { metric_code: 'special_task', input_kind: 'special_task', input_payload: { result: 'partial', note: 'Follow-up scheduled' } },
        { metric_code: 'personal_target_completion_rate', input_kind: 'percentage', input_payload: {} }
      ]
    }
  ])

  assert.deepEqual(payload, {
    year_month: '2026-09',
    expected_plan_version: 3,
    entries: [
      { employee_code: 'EMP001', metric_code: 'attendance', actual_value: 98 },
      { employee_code: 'EMP001', metric_code: 'training_completion_rate', completed_count: 9, required_count: 10 },
      { employee_code: 'EMP001', metric_code: 'special_task', result: 'partial', note: 'Follow-up scheduled' }
    ]
  })
})

test('personal scope payload carries only controlled scope fields and a version', () => {
  assert.deepEqual(buildPersonalScopePayload('2026-09', 3, [
    { employee_code: 'EMP001', employee_name: 'Alice', is_included: true },
    { employee_code: 'EMP002', employee_name: 'Bob', is_included: false, exclusion_note: 'On leave' }
  ]), {
    year_month: '2026-09',
    expected_plan_version: 3,
    employees: [
      { employee_code: 'EMP001', is_included: true, exclusion_note: null },
      { employee_code: 'EMP002', is_included: false, exclusion_note: 'On leave' }
    ]
  })
})

test('controlled month detection and score display use the audited one decimal convention', () => {
  assert.equal(isControlledPersonalMonth({ calculation_mode: 'controlled_targets_v1' }), true)
  assert.equal(isControlledPersonalMonth({ calculation_mode: 'legacy_inputs' }), false)
  assert.equal(formatPerformanceScore(71.95418558631921), '72.0')
})

test('controlled income audit distinguishes partial completion from a non-participating employee', () => {
  assert.match(
    getControlledPersonalAuditNotice({ calculation_status: 'partial', calculation_details: { missing_personal_metrics: ['attendance_compliance_rate'] } }),
    /未完成个人运营目标/
  )
  assert.match(
    getControlledPersonalAuditNotice({ calculation_status: 'partial', calculation_details: { missing_shop_scores: ['shopee/shop-1'] } }),
    /店铺基础分/
  )
  assert.equal(
    getControlledPersonalAuditNotice({ calculation_status: 'not_participating', calculation_details: { status: 'not_participating' } }),
    '本月未参与个人绩效：不产生个人绩效工资或排名，基础工资与独立店铺提成不受影响。'
  )
  assert.equal(getControlledPersonalAuditNotice({ calculation_status: 'complete', calculation_details: { status: 'complete' } }), '')
})

test('personal workbench exposes the three-step UI and the dedicated API methods', async () => {
  const [component, api, management, audit] = await Promise.all([
    readFile(new URL('../src/domains/business/views/target/TargetPersonalManagement.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/api/index.js', import.meta.url), 'utf8'),
    readFile(new URL('../src/domains/business/views/hr/PerformanceManagement.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/domains/business/views/hr/IncomeAudit.vue', import.meta.url), 'utf8')
  ])

  assert.match(component, /个人运营目标管理/)
  assert.match(component, /el-steps/)
  assert.match(component, /确认参与员工/)
  assert.match(component, /专项任务/)
  assert.match(component, /revokePersonalPerformanceScope/)
  assert.match(api, /getPersonalPerformanceWorkbench/)
  assert.match(api, /applyPersonalPerformanceEntries/)
  assert.match(management, /isControlledPersonalMonth/)
  assert.match(management, /店铺继承基础分/)
  assert.match(management, /formatPerformanceScore/)
  assert.match(audit, /formatPerformanceScore/)
  assert.match(audit, /店铺基础分/)
})

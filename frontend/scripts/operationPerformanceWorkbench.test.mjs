import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import {
  buildEntryPayload,
  buildScopePayload,
  getStoreEntryStatus
} from '../src/domains/business/views/target/operationPerformanceWorkbench.js'

test('buildScopePayload sends the complete monthly shop scope without mutable shop identity fields', () => {
  const payload = buildScopePayload('2026-08', [
    { platform_code: 'shopee', shop_id: 'shop-1', shop_name: 'Shopee A', is_included: true },
    { platform_code: 'lazada', shop_id: 'shop-2', shop_name: 'Lazada B', is_included: false, exclusion_reason: 'Seasonal closure' }
  ])

  assert.deepEqual(payload, {
    year_month: '2026-08',
    shops: [
      { platform_code: 'shopee', shop_id: 'shop-1', is_included: true, exclusion_reason: null },
      { platform_code: 'lazada', shop_id: 'shop-2', is_included: false, exclusion_reason: 'Seasonal closure' }
    ]
  })
})

test('buildEntryPayload sends only controlled structured inputs for each metric type', () => {
  const payload = buildEntryPayload('2026-08', [
    {
      platform_code: 'shopee',
      shop_id: 'shop-1',
      metrics: [
        { metric_code: 'customer_satisfaction', input_kind: 'numeric', input_payload: { actual_value: 90 } },
        { metric_code: 'training_completion_rate', input_kind: 'training_counts', input_payload: { completed_count: 9, required_count: 10 } },
        { metric_code: 'operation_special_check', input_kind: 'special_check', input_payload: { result: 'partial', note: 'Need follow-up' } }
      ]
    }
  ])

  assert.deepEqual(payload, {
    year_month: '2026-08',
    entries: [
      { platform_code: 'shopee', shop_id: 'shop-1', metric_code: 'customer_satisfaction', actual_value: 90 },
      { platform_code: 'shopee', shop_id: 'shop-1', metric_code: 'training_completion_rate', completed_count: 9, required_count: 10 },
      { platform_code: 'shopee', shop_id: 'shop-1', metric_code: 'operation_special_check', result: 'partial', note: 'Need follow-up' }
    ]
  })
})

test('getStoreEntryStatus reports pending until every metric is complete', () => {
  assert.equal(getStoreEntryStatus({ metrics: [{ status: 'completed' }, { status: 'pending' }] }), 'pending')
  assert.equal(getStoreEntryStatus({ metrics: [{ status: 'completed' }] }), 'completed')
})

test('operation workbench exposes the three monthly steps and dedicated API methods', async () => {
  const [component, api] = await Promise.all([
    readFile(new URL('../src/domains/business/views/target/TargetOperationWorkbench.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/api/index.js', import.meta.url), 'utf8')
  ])

  assert.match(component, /el-steps/)
  assert.match(component, /评分规则/)
  assert.match(component, /店铺范围确认/)
  assert.match(component, /店铺数据录入与保存/)
  assert.match(component, /excludeAllShops/)
  assert.match(component, /scopeDirty/)
  assert.match(component, /scopeReady/)
  assert.match(component, /standard_name/)
  assert.match(component, /aliases/)
  assert.match(component, /备注（可选）/)
  assert.match(component, /revokeScope/)
  assert.match(component, /training_counts/)
  assert.match(component, /special_check/)
  assert.match(component, /isNumericInput\(metric\)/)
  assert.match(component, /auto_score/)
  assert.doesNotMatch(component, /metric\.is_manual/)
  assert.doesNotMatch(component, /metric\.achieved_value/)
  assert.doesNotMatch(component, /metric\.manual_score_value/)
  assert.doesNotMatch(component, /el-drawer/)
  assert.match(api, /getOperationPerformanceScope/)
  assert.match(api, /applyOperationPerformanceScope/)
  assert.match(api, /getOperationPerformanceEntries/)
  assert.match(api, /applyOperationPerformanceEntries/)
  assert.match(api, /revokeOperationPerformanceScope/)
})

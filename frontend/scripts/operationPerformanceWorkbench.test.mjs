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

test('buildEntryPayload sends only the applicable value for each metric direction', () => {
  const payload = buildEntryPayload('2026-08', [
    {
      platform_code: 'shopee',
      shop_id: 'shop-1',
      metrics: [
        { metric_code: 'conversion_rate', is_manual: false, achieved_value: 8.5, manual_score_value: 9 },
        { metric_code: 'content_quality', is_manual: true, achieved_value: 99, manual_score_value: 7 }
      ]
    }
  ])

  assert.deepEqual(payload, {
    year_month: '2026-08',
    entries: [
      { platform_code: 'shopee', shop_id: 'shop-1', metric_code: 'conversion_rate', achieved_value: 8.5 },
      { platform_code: 'shopee', shop_id: 'shop-1', metric_code: 'content_quality', manual_score_value: 7 }
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
  assert.doesNotMatch(component, /el-drawer/)
  assert.match(api, /getOperationPerformanceScope/)
  assert.match(api, /applyOperationPerformanceScope/)
  assert.match(api, /getOperationPerformanceEntries/)
  assert.match(api, /applyOperationPerformanceEntries/)
  assert.match(api, /revokeOperationPerformanceScope/)
})

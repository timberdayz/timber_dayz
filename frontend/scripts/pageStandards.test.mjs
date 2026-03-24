import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeSalesTargetsResponse,
  buildSalesTargetMutationPayload,
  getPageFamilyClass,
} from '../src/utils/pageStandards.js'

test('normalizeSalesTargetsResponse normalizes direct arrays and wrapped data', () => {
  const rows = [{ id: 1 }, { id: 2 }]

  assert.deepEqual(normalizeSalesTargetsResponse(rows), rows)
  assert.deepEqual(normalizeSalesTargetsResponse({ data: rows }), rows)
  assert.deepEqual(normalizeSalesTargetsResponse({}), [])
})

test('buildSalesTargetMutationPayload keeps only editable fields', () => {
  assert.deepEqual(
    buildSalesTargetMutationPayload({
      target_sales_amount: 1200.5,
      target_order_count: 42,
      shop_id: 'shop-1',
    }),
    {
      target_sales_amount: 1200.5,
      target_order_count: 42,
    },
  )
})

test('getPageFamilyClass maps known families and falls back to admin', () => {
  assert.equal(getPageFamilyClass('dashboard'), 'erp-page--dashboard')
  assert.equal(getPageFamilyClass('admin'), 'erp-page--admin')
  assert.equal(getPageFamilyClass('unknown'), 'erp-page--admin')
})

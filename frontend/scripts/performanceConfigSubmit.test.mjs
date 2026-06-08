import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildFormalPerformanceConfigPayload,
  extractPerformanceConfigRow,
  savePerformanceConfig
} from '../src/domains/business/views/hr/performanceConfigSubmit.js'

test('extractPerformanceConfigRow reads the current active config from paged responses', () => {
  const row = { id: 42, sales_max_score: 35 }

  assert.equal(extractPerformanceConfigRow({ data: [row], pagination: { total: 1 } }), row)
  assert.equal(extractPerformanceConfigRow([row]), row)
  assert.equal(extractPerformanceConfigRow({ data: row }), row)
})

test('buildFormalPerformanceConfigPayload excludes legacy key product and weight fields', () => {
  const payload = buildFormalPerformanceConfigPayload({
    sales_weight: 30,
    profit_weight: 25,
    key_product_weight: 25,
    operation_weight: 20,
    sales_max_score: 40,
    profit_max_score: 30,
    key_product_max_score: 999,
    operation_max_score: 30
  })

  assert.deepEqual(payload, {
    sales_max_score: 40,
    profit_max_score: 30,
    operation_max_score: 30
  })
})

test('savePerformanceConfig updates the existing config instead of creating a duplicate', async () => {
  const calls = []
  const api = {
    async updatePerformanceConfig(id, payload) {
      calls.push(['update', id, payload])
      return { id, ...payload }
    },
    async createPerformanceConfig(payload) {
      calls.push(['create', payload])
      return payload
    }
  }

  await savePerformanceConfig({
    api,
    currentConfigId: 42,
    payload: { sales_max_score: 40 },
    effectiveFrom: '2026-06-09'
  })

  assert.deepEqual(calls, [['update', 42, { sales_max_score: 40 }]])
})

test('savePerformanceConfig creates only when no current config exists', async () => {
  const calls = []
  const api = {
    async updatePerformanceConfig(id, payload) {
      calls.push(['update', id, payload])
      return { id, ...payload }
    },
    async createPerformanceConfig(payload) {
      calls.push(['create', payload])
      return payload
    }
  }

  await savePerformanceConfig({
    api,
    currentConfigId: null,
    payload: { sales_max_score: 40 },
    effectiveFrom: '2026-06-09'
  })

  assert.deepEqual(calls, [['create', { sales_max_score: 40, effective_from: '2026-06-09' }]])
})

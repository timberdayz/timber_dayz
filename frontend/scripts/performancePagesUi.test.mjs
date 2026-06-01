import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerSource = fs.readFileSync(
  path.resolve(__dirname, '../src/router/index.js'),
  'utf8'
)
const managementSource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/PerformanceManagement.vue'),
  'utf8'
)
const displaySource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/PerformanceDisplay.vue'),
  'utf8'
)

test('performance route entries expose non-placeholder titles', () => {
  for (const pair of [
    ["path: '/hr-performance-management/shop'", "title: '店铺绩效管理'"],
    ["path: '/hr-performance-management/person'", "title: '个人绩效管理'"],
    ["path: '/hr-performance-display/shop'", "title: '店铺绩效公示'"],
    ["path: '/hr-performance-display/person'", "title: '个人绩效公示'"]
  ]) {
    assert.equal(routerSource.includes(pair[0]), true, `${pair[0]} should exist`)
    assert.equal(routerSource.includes(pair[1]), true, `${pair[1]} should exist`)
  }
})

test('performance management page uses a shared header and no placeholder subtitle copy', () => {
  assert.equal(managementSource.includes('<PageHeader'), true)
  assert.equal(managementSource.includes('pageSubtitle'), true)
  assert.equal(managementSource.includes('????????'), false)
  assert.equal(managementSource.includes('style="color: #909399; margin-bottom: 20px;"'), false)
})

test('performance display page uses a shared header and no placeholder subtitle copy', () => {
  assert.equal(displaySource.includes('<PageHeader'), true)
  assert.equal(displaySource.includes('pageSubtitle'), true)
  assert.equal(displaySource.includes('????????'), false)
  assert.equal(displaySource.includes('style="color: #909399;'), false)
})

test('performance pages use higher-contrast visual tokens for card copy', () => {
  for (const source of [managementSource, displaySource]) {
    assert.equal(source.includes('--perf-text-primary: #1d1d1f;'), true)
    assert.equal(source.includes('--perf-text-secondary: #6e6e73;'), true)
    assert.equal(source.includes('--perf-surface-muted: #f5f5f7;'), true)
  }
})

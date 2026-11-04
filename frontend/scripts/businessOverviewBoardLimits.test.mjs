import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const viewSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/BusinessOverview.vue'), 'utf8')

test('business overview inventory backlog api helper serializes limit', () => {
  assert.equal(apiSource.includes("if (params.limit) queryParams.append('limit', params.limit)"), true)
})

test('BusinessOverview requests dashboard-sized stagnant board payloads', () => {
  assert.equal(viewSource.includes('api.getBusinessOverviewInventoryBacklog({'), true)
  assert.equal(viewSource.includes('limit: 20,'), true)
  assert.equal(viewSource.includes('granularity: globalGranularity.value'), true)
  assert.equal(viewSource.includes('date: targetDate || undefined'), true)
})

test('BusinessOverview no longer ships the retired clearance ranking board', () => {
  // 2026-11-04：滞销清理排名（月度）模块整体下线，前端不得再有任何残留
  assert.equal(viewSource.includes('monthlyClearanceRanking'), false)
  assert.equal(viewSource.includes('loadMonthlyClearanceRanking'), false)
  assert.equal(viewSource.includes('滞销清理排名'), false)
  assert.equal(apiSource.includes('getClearanceRanking'), false)
  assert.equal(apiSource.includes('/dashboard/clearance-ranking'), false)
})

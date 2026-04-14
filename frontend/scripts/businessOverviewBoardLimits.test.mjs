import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const viewSource = readFileSync(resolve(repoRoot, 'src/views/BusinessOverview.vue'), 'utf8')

test('business overview inventory backlog api helper serializes limit', () => {
  assert.equal(apiSource.includes("if (params.limit) queryParams.append('limit', params.limit)"), true)
})

test('BusinessOverview requests dashboard-sized stagnant board payloads', () => {
  assert.equal(viewSource.includes('api.getBusinessOverviewInventoryBacklog({ limit: 20 })'), true)
  assert.equal(viewSource.includes("params.limit = 10"), true)
})

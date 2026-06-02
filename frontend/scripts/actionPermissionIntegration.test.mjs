import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function read(file) {
  return fs.readFileSync(path.resolve(__dirname, `../src/${file}`), 'utf8')
}

test('campaign and performance pages use shared action permission helper', () => {
  const campaignSource = read('domains/business/views/sales/CampaignManagement.vue')
  const performanceManagementSource = read('domains/business/views/hr/PerformanceManagement.vue')
  const performanceDisplaySource = read('domains/business/views/hr/PerformanceDisplay.vue')

  for (const source of [campaignSource, performanceManagementSource, performanceDisplaySource]) {
    assert.equal(
      source.includes("hasScopedActionPermission"),
      true,
      'page should import or use shared action permission helper',
    )
    assert.equal(
      source.includes('const normalizeRoleCode ='),
      false,
      'page should not keep local role normalization helpers',
    )
  }

  assert.equal(
    performanceDisplaySource.includes("userStore.hasPermission(permission)"),
    false,
    'performance display should not bypass shared action permission helper',
  )
})

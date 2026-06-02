import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { hasScopedActionPermission } from '../src/utils/actionPermissions.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const campaignViewSource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/sales/CampaignManagement.vue'),
  'utf8',
)
const performanceManagementSource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/PerformanceManagement.vue'),
  'utf8',
)
const performanceDisplaySource = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/PerformanceDisplay.vue'),
  'utf8',
)

test('campaign action permissions follow scoped role rules', () => {
  assert.equal(
    hasScopedActionPermission({ roles: ['manager'], activeRole: 'manager', permission: 'campaign:create' }),
    true,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['manager'], activeRole: 'manager', permission: 'campaign:delete' }),
    false,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['operator'], activeRole: 'operator', permission: 'campaign:read' }),
    true,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['finance'], activeRole: 'finance', permission: 'campaign:update' }),
    false,
  )
})

test('performance action permissions follow scoped role rules', () => {
  assert.equal(
    hasScopedActionPermission({ roles: ['manager'], activeRole: 'manager', permission: 'performance:export' }),
    true,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['manager'], activeRole: 'manager', permission: 'performance:config' }),
    false,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['operator'], activeRole: 'operator', permission: 'performance:read' }),
    true,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['finance'], activeRole: 'finance', permission: 'performance:export' }),
    false,
  )
})

test('admin role bypasses scoped action restrictions', () => {
  assert.equal(
    hasScopedActionPermission({ roles: ['admin'], activeRole: 'manager', permission: 'campaign:delete' }),
    true,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['admin'], activeRole: 'operator', permission: 'performance:config' }),
    true,
  )
})

test('unknown action permissions fall back to role-config permissions', () => {
  assert.equal(
    hasScopedActionPermission({ roles: ['manager'], activeRole: 'manager', permission: 'finance-reports' }),
    true,
  )
  assert.equal(
    hasScopedActionPermission({ roles: ['operator'], activeRole: 'operator', permission: 'finance-reports' }),
    false,
  )
})

test('campaign and performance pages use shared action permission helper', () => {
  for (const source of [campaignViewSource, performanceManagementSource, performanceDisplaySource]) {
    assert.equal(source.includes("hasScopedActionPermission"), true)
  }
})

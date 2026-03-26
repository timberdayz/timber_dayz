import test from 'node:test'
import assert from 'node:assert/strict'

import {
  SMOKE_ROUTES,
  buildAuthStorageEntries,
  summarizeSmokeResults
} from './frontendSmokeShared.mjs'

test('smoke routes cover the agreed core frontend pages', () => {
  const paths = SMOKE_ROUTES.map((route) => route.path)

  assert.deepEqual(paths, [
    '/business-overview',
    '/sales-dashboard-v3',
    '/system-config',
    '/inventory-management',
    '/target-management',
    '/user-management',
    '/role-management',
    '/permission-management',
    '/account-management',
    '/settings/sessions',
    '/system-notifications',
    '/database-config',
    '/security-settings',
    '/system-logs',
    '/data-backup',
    '/notification-config',
    '/system-maintenance',
    '/collection-config',
    '/data-sync/tasks',
    '/data-sync/history',
    '/component-versions',
    '/store-analytics',
    '/financial-overview',
    '/expense-management',
    '/inventory-dashboard-v3',
    '/inventory-health',
    '/product-quality',
    '/sales-analysis'
  ])
})

test('buildAuthStorageEntries produces the localStorage keys required by auth and route guards', () => {
  const entries = buildAuthStorageEntries({
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    user_info: {
      id: 4,
      username: 'xihong',
      email: 'xihong@xihong.com',
      full_name: '系统管理员',
      roles: ['admin']
    }
  })

  assert.equal(entries.access_token, 'access-token')
  assert.equal(entries.refresh_token, 'refresh-token')
  assert.equal(entries.activeRole, 'admin')
  assert.equal(entries.user_info.includes('"username":"xihong"'), true)
  assert.equal(entries.userInfo.includes('"username":"xihong"'), true)
  assert.deepEqual(JSON.parse(entries.roles), ['admin'])
  assert.equal(Array.isArray(JSON.parse(entries.permissions)), true)
})

test('summarizeSmokeResults counts passed and failed routes with failure details', () => {
  const summary = summarizeSmokeResults([
    { path: '/business-overview', ok: true, consoleErrors: [], pageErrors: [], requestFailures: [] },
    {
      path: '/sales-dashboard-v3',
      ok: false,
      consoleErrors: ['boom'],
      pageErrors: [],
      requestFailures: [{ url: '/api/x', status: 500 }]
    }
  ])

  assert.equal(summary.total, 2)
  assert.equal(summary.passed, 1)
  assert.equal(summary.failed, 1)
  assert.equal(summary.failedRoutes[0].path, '/sales-dashboard-v3')
  assert.equal(summary.failedRoutes[0].requestFailures.length, 1)
})

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  extractNormalizedRoles,
  hasAnyRole,
  hasPermissionForRoles
} from '../src/utils/authRoles.js'

test('extractNormalizedRoles supports string and object roles', () => {
  assert.deepEqual(
    extractNormalizedRoles([
      'admin',
      { role_code: 'finance' },
      { role_name: '主管' }
    ]),
    ['admin', 'finance', 'manager']
  )
})

test('hasAnyRole matches normalized object roles', () => {
  const roles = [{ role_code: 'finance' }, { role_name: '管理员' }]
  assert.equal(hasAnyRole(roles, ['admin']), true)
  assert.equal(hasAnyRole(roles, ['operator']), false)
})

test('hasPermissionForRoles grants permissions through configured roles', () => {
  const financeRoles = [{ role_code: 'finance' }]
  assert.equal(hasPermissionForRoles(financeRoles, 'finance-reports'), true)
  assert.equal(hasPermissionForRoles(financeRoles, 'role-management'), false)
})

test('hasPermissionForRoles grants all permissions to admin', () => {
  assert.equal(hasPermissionForRoles(['admin'], 'anything'), true)
})

test('operator gets inventory read permissions but not inventory manage permissions', () => {
  assert.equal(hasPermissionForRoles(['operator'], 'inventory:view'), true)
  assert.equal(hasPermissionForRoles(['operator'], 'inventory-dashboard:view'), true)
  assert.equal(hasPermissionForRoles(['operator'], 'inventory:manage'), false)
})

test('manager gets inventory read permissions but not inventory manage permissions', () => {
  assert.equal(hasPermissionForRoles(['manager'], 'inventory:view'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'inventory-dashboard:view'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'inventory:manage'), false)
})

test('collection management remains admin only', () => {
  assert.equal(hasPermissionForRoles(['admin'], 'collection-config'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'collection-config'), false)
  assert.equal(hasPermissionForRoles(['operator'], 'collection-config'), false)
})

test('sales analysis and sales detail view permissions match approved roles', () => {
  assert.equal(hasPermissionForRoles(['operator'], 'sales-analysis'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'sales-detail'), true)
  assert.equal(hasPermissionForRoles(['operator'], 'sales-detail'), true)
  assert.equal(hasPermissionForRoles(['finance'], 'sales-detail'), true)
})

test('finance domain view and document pages match approved roles', () => {
  assert.equal(hasPermissionForRoles(['manager'], 'invoice-management'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'b-cost-analysis'), true)
  assert.equal(hasPermissionForRoles(['finance'], 'b-cost-analysis'), true)
})

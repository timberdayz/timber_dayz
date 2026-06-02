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

test('operator keeps current sales and hr page permissions, but not removed inventory pages', () => {
  assert.equal(hasPermissionForRoles(['operator'], 'sales-dashboard'), true)
  assert.equal(hasPermissionForRoles(['operator'], 'employee-management'), true)
  assert.equal(hasPermissionForRoles(['operator'], 'inventory:view'), false)
  assert.equal(hasPermissionForRoles(['operator'], 'inventory-dashboard:view'), false)
  assert.equal(hasPermissionForRoles(['operator'], 'inventory:manage'), false)
})

test('manager keeps current finance and training page permissions, but not admin-only sales detail', () => {
  assert.equal(hasPermissionForRoles(['manager'], 'b-cost-analysis'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'training-management'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'sales-detail'), false)
  assert.equal(hasPermissionForRoles(['manager'], 'inventory:view'), false)
  assert.equal(hasPermissionForRoles(['manager'], 'inventory-dashboard:view'), false)
  assert.equal(hasPermissionForRoles(['manager'], 'inventory:manage'), false)
})

test('collection management remains admin only', () => {
  assert.equal(hasPermissionForRoles(['admin'], 'collection-config'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'collection-config'), false)
  assert.equal(hasPermissionForRoles(['operator'], 'collection-config'), false)
})

test('sales detail stays admin only while shared order pages stay available', () => {
  assert.equal(hasPermissionForRoles(['manager'], 'order-management'), true)
  assert.equal(hasPermissionForRoles(['operator'], 'order-management'), true)
  assert.equal(hasPermissionForRoles(['finance'], 'order-management'), true)
  assert.equal(hasPermissionForRoles(['manager'], 'sales-detail'), false)
  assert.equal(hasPermissionForRoles(['operator'], 'sales-detail'), false)
  assert.equal(hasPermissionForRoles(['finance'], 'sales-detail'), false)
})

test('removed procurement and report pages are no longer granted to non-admin roles', () => {
  assert.equal(hasPermissionForRoles(['manager'], 'purchase-orders'), false)
  assert.equal(hasPermissionForRoles(['manager'], 'vendor-reports'), false)
  assert.equal(hasPermissionForRoles(['finance'], 'purchase-orders'), false)
  assert.equal(hasPermissionForRoles(['operator'], 'sales-reports'), false)
  assert.equal(hasPermissionForRoles(['manager'], 'b-cost-analysis'), true)
  assert.equal(hasPermissionForRoles(['finance'], 'b-cost-analysis'), true)
})

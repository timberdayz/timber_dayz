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

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildPersistedAuthState,
  clearPersistedAuthState,
  readPersistedAuthState,
} from '../src/utils/authSession.js'

function createMemoryStorage() {
  const store = new Map()
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null
    },
    setItem(key, value) {
      store.set(key, String(value))
    },
    removeItem(key) {
      store.delete(key)
    },
  }
}

test('buildPersistedAuthState writes both auth and user store keys', () => {
  const entries = buildPersistedAuthState({
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    user_info: {
      id: 4,
      username: 'xihong',
      email: 'xihong@xihong.com',
      full_name: '系统管理员',
      roles: ['admin'],
    },
  })

  assert.equal(entries.access_token, 'access-token')
  assert.equal(entries.refresh_token, 'refresh-token')
  assert.equal(entries.activeRole, 'admin')
  assert.equal(entries.user_info.includes('"username":"xihong"'), true)
  assert.equal(entries.userInfo.includes('"username":"xihong"'), true)
  assert.deepEqual(JSON.parse(entries.roles), ['admin'])
  assert.equal(Array.isArray(JSON.parse(entries.permissions)), true)
})

test('readPersistedAuthState tolerates missing userInfo and rebuilds it from user_info', () => {
  const storage = createMemoryStorage()
  storage.setItem('access_token', 'access-token')
  storage.setItem(
    'user_info',
    JSON.stringify({
      id: 12,
      username: 'codex_admin',
      email: 'codex_admin@example.com',
      full_name: 'Codex Admin',
      roles: ['admin'],
    }),
  )
  storage.setItem('activeRole', 'admin')

  const state = readPersistedAuthState(storage)

  assert.equal(state.accessToken, 'access-token')
  assert.equal(state.userInfo.username, 'codex_admin')
  assert.deepEqual(state.roles, ['admin'])
  assert.equal(state.permissions.includes('data-sync'), true)
})

test('clearPersistedAuthState removes all auth-related keys', () => {
  const storage = createMemoryStorage()
  for (const [key, value] of Object.entries(
    buildPersistedAuthState({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      user_info: {
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        full_name: 'Admin',
        roles: ['admin'],
      },
    }),
  )) {
    storage.setItem(key, value)
  }

  clearPersistedAuthState(storage)

  assert.equal(storage.getItem('access_token'), null)
  assert.equal(storage.getItem('refresh_token'), null)
  assert.equal(storage.getItem('user_info'), null)
  assert.equal(storage.getItem('userInfo'), null)
  assert.equal(storage.getItem('roles'), null)
  assert.equal(storage.getItem('permissions'), null)
  assert.equal(storage.getItem('activeRole'), null)
})

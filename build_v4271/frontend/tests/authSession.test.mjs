import test from 'node:test'
import assert from 'node:assert/strict'

import {
  hasAnyPersistedAuthArtifact,
  hasPersistedAuthSession,
  readPersistedAuthState,
} from '../src/utils/authSession.js'

function createStorage(initial = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null
    },
    setItem(key, value) {
      data.set(key, value)
    },
    removeItem(key) {
      data.delete(key)
    },
  }
}

test('hasPersistedAuthSession requires both access token and auth user', () => {
  const tokenOnlyState = {
    accessToken: 'access-token',
    refreshToken: '',
    authUser: null,
    userInfo: null,
  }
  const fullState = {
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    authUser: { id: 1, username: 'admin' },
    userInfo: { id: 1, username: 'admin' },
  }

  assert.equal(hasPersistedAuthSession(tokenOnlyState), false)
  assert.equal(hasPersistedAuthSession(fullState), true)
})

test('hasAnyPersistedAuthArtifact detects partial auth remnants', () => {
  assert.equal(
    hasAnyPersistedAuthArtifact({
      accessToken: '',
      refreshToken: 'refresh-token',
      authUser: null,
      userInfo: null,
    }),
    true
  )

  assert.equal(
    hasAnyPersistedAuthArtifact({
      accessToken: '',
      refreshToken: '',
      authUser: null,
      userInfo: null,
    }),
    false
  )
})

test('readPersistedAuthState reconstructs a full persisted session', () => {
  const storage = createStorage({
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    user_info: JSON.stringify({
      id: 7,
      username: 'operator',
      full_name: 'Operator',
      email: 'operator@example.com',
      roles: ['operator'],
    }),
    roles: JSON.stringify(['operator']),
    permissions: JSON.stringify(['orders:read']),
    activeRole: 'operator',
  })

  const state = readPersistedAuthState(storage)

  assert.equal(state.accessToken, 'access-token')
  assert.equal(state.refreshToken, 'refresh-token')
  assert.equal(state.authUser.username, 'operator')
  assert.equal(state.userInfo.username, 'operator')
  assert.deepEqual(state.roles, ['operator'])
  assert.equal(hasPersistedAuthSession(state), true)
  assert.equal(hasAnyPersistedAuthArtifact(state), true)
})

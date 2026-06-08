import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildPersistedAuthState,
  clearPersistedAuthState,
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
    hasItem(key) {
      return data.has(key)
    },
  }
}

test('hasPersistedAuthSession only requires persisted auth user state', () => {
  const userOnlyState = {
    accessToken: '',
    refreshToken: '',
    authUser: { id: 1, username: 'admin' },
    userInfo: { id: 1, username: 'admin' },
  }
  const emptyState = {
    accessToken: '',
    refreshToken: '',
    authUser: null,
    userInfo: null,
  }

  assert.equal(hasPersistedAuthSession(userOnlyState), true)
  assert.equal(hasPersistedAuthSession(emptyState), false)
})

test('hasAnyPersistedAuthArtifact detects partial auth remnants', () => {
  assert.equal(
    hasAnyPersistedAuthArtifact({
      accessToken: '',
      refreshToken: 'refresh-token',
      authUser: null,
      userInfo: null,
    }),
    false
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

test('buildPersistedAuthState omits sensitive token persistence', () => {
  const entries = buildPersistedAuthState({
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    user_info: {
      id: 7,
      username: 'operator',
      full_name: 'Operator',
      email: 'operator@example.com',
      roles: [],
    },
  })

  assert.equal('access_token' in entries, false)
  assert.equal('refresh_token' in entries, false)
  assert.deepEqual(JSON.parse(entries.roles), [])
  assert.equal(entries.activeRole, '')
})

test('buildPersistedAuthState persists only non-sensitive access token expiry', () => {
  const originalNow = Date.now
  Date.now = () => 1_700_000_000_000

  try {
    const entries = buildPersistedAuthState({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      expires_in: 3600,
      user_info: {
        id: 7,
        username: 'operator',
        roles: ['operator'],
      },
    })

    assert.equal('access_token' in entries, false)
    assert.equal('refresh_token' in entries, false)
    assert.equal(entries.accessTokenExpiresAt, '1700003600000')
  } finally {
    Date.now = originalNow
  }
})

test('readPersistedAuthState reconstructs a full persisted session without local tokens', () => {
  const storage = createStorage({
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
    accessTokenExpiresAt: '1700003600000',
  })

  const state = readPersistedAuthState(storage)

  assert.equal(state.accessToken, '')
  assert.equal(state.refreshToken, '')
  assert.equal(state.authUser.username, 'operator')
  assert.equal(state.userInfo.username, 'operator')
  assert.deepEqual(state.roles, ['operator'])
  assert.equal(state.accessTokenExpiresAt, 1700003600000)
  assert.equal(hasPersistedAuthSession(state), true)
  assert.equal(hasAnyPersistedAuthArtifact(state), true)
})

test('clearPersistedAuthState removes non-sensitive access token expiry', () => {
  const storage = createStorage({
    user_info: JSON.stringify({ id: 7, username: 'operator' }),
    accessTokenExpiresAt: '1700003600000',
  })

  clearPersistedAuthState(storage)

  assert.equal(storage.hasItem('accessTokenExpiresAt'), false)
})

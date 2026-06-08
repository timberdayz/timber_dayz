import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createSharedRefreshRunner,
  handleRefreshFailureRecovery,
  shouldRefreshAccessToken,
} from '../src/utils/authRecovery.js'

test('shouldRefreshAccessToken uses persisted httpOnly-token expiry state', () => {
  assert.equal(
    shouldRefreshAccessToken({
      accessTokenExpiresAt: 1_700_000_240_000,
      nowMs: 1_700_000_000_000,
    }),
    true,
  )
  assert.equal(
    shouldRefreshAccessToken({
      accessTokenExpiresAt: 1_700_000_600_000,
      nowMs: 1_700_000_000_000,
    }),
    false,
  )
  assert.equal(
    shouldRefreshAccessToken({
      accessTokenExpiresAt: 0,
      nowMs: 1_700_000_000_000,
    }),
    false,
  )
})

test('createSharedRefreshRunner coalesces concurrent refresh requests', async () => {
  let refreshCalls = 0
  let resolveRefresh
  const runner = createSharedRefreshRunner(() => {
    refreshCalls += 1
    return new Promise((resolve) => {
      resolveRefresh = resolve
    })
  })

  const first = runner()
  const second = runner()

  assert.equal(refreshCalls, 1)
  assert.equal(first, second)

  resolveRefresh(true)
  assert.equal(await first, true)
  assert.equal(await second, true)

  const third = runner()
  assert.equal(refreshCalls, 2)
  resolveRefresh(true)
  assert.equal(await third, true)
})

test('handleRefreshFailureRecovery preserves session on transient refresh failure', async () => {
  const events = []

  const result = await handleRefreshFailureRecovery({
    refreshError: { status: 503 },
    confirmCurrentSession: async () => {
      throw new Error('should not confirm transient failures')
    },
    markRecoveryFailed: () => events.push('mark'),
    clearLocalSession: () => events.push('clear'),
    redirectToLogin: () => events.push('redirect'),
    notifyTransientFailure: () => events.push('notify'),
  })

  assert.equal(result, 'transient')
  assert.deepEqual(events, ['notify'])
})

test('handleRefreshFailureRecovery keeps page state when current cookie is still valid', async () => {
  const events = []

  const result = await handleRefreshFailureRecovery({
    refreshError: { status: 401 },
    confirmCurrentSession: async () => true,
    markRecoveryFailed: () => events.push('mark'),
    clearLocalSession: () => events.push('clear'),
    redirectToLogin: () => events.push('redirect'),
    notifyRecovered: () => events.push('recovered'),
  })

  assert.equal(result, 'recovered')
  assert.deepEqual(events, ['recovered'])
})

test('handleRefreshFailureRecovery clears session only after refresh and me both reject auth', async () => {
  const events = []

  const result = await handleRefreshFailureRecovery({
    refreshError: { status: 401 },
    confirmCurrentSession: async () => false,
    markRecoveryFailed: () => events.push('mark'),
    clearLocalSession: () => events.push('clear'),
    redirectToLogin: () => events.push('redirect'),
  })

  assert.equal(result, 'invalid')
  assert.deepEqual(events, ['mark', 'clear', 'redirect'])
})

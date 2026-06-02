import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildNotificationWebSocketUrl,
  isNotificationWebSocketRetryableCloseCode,
} from '../src/services/notificationWebSocket.helpers.js'

test('buildNotificationWebSocketUrl omits token when absent', () => {
  const url = buildNotificationWebSocketUrl({
    protocol: 'https:',
    host: 'www.xihong.site',
    accessToken: '',
  })

  assert.equal(url, 'wss://www.xihong.site/api/notifications/ws')
})

test('buildNotificationWebSocketUrl appends token when present', () => {
  const url = buildNotificationWebSocketUrl({
    protocol: 'https:',
    host: 'www.xihong.site',
    accessToken: 'token-123',
  })

  assert.equal(url, 'wss://www.xihong.site/api/notifications/ws?token=token-123')
})

test('isNotificationWebSocketRetryableCloseCode rejects auth and policy failures', () => {
  assert.equal(isNotificationWebSocketRetryableCloseCode(4001), false)
  assert.equal(isNotificationWebSocketRetryableCloseCode(4005), false)
  assert.equal(isNotificationWebSocketRetryableCloseCode(4007), false)
  assert.equal(isNotificationWebSocketRetryableCloseCode(1008), false)
  assert.equal(isNotificationWebSocketRetryableCloseCode(1011), true)
})

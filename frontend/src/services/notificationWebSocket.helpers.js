export const NON_RETRYABLE_NOTIFICATION_WS_CLOSE_CODES = new Set([
  1008,
  4001,
  4005,
  4006,
  4007,
  4008,
])

export function buildNotificationWebSocketUrl({
  protocol,
  host,
  accessToken = '',
}) {
  if (!protocol || !host) return null

  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'
  const baseUrl = `${wsProtocol}//${host}/api/notifications/ws`
  if (!accessToken) {
    return baseUrl
  }

  return `${baseUrl}?token=${encodeURIComponent(accessToken)}`
}

export function isNotificationWebSocketRetryableCloseCode(code) {
  return !NON_RETRYABLE_NOTIFICATION_WS_CLOSE_CODES.has(code)
}

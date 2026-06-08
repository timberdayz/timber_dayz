export const ACCESS_TOKEN_REFRESH_THRESHOLD_MS = 5 * 60 * 1000

export function shouldRefreshAccessToken({
  accessTokenExpiresAt,
  nowMs = Date.now(),
  thresholdMs = ACCESS_TOKEN_REFRESH_THRESHOLD_MS,
} = {}) {
  const expiresAt = Number(accessTokenExpiresAt)
  if (!Number.isFinite(expiresAt) || expiresAt <= 0) {
    return false
  }
  return expiresAt - nowMs <= thresholdMs
}

export function createSharedRefreshRunner(refreshFn) {
  let activeRefresh = null

  return function runSharedRefresh() {
    if (!activeRefresh) {
      try {
        activeRefresh = Promise.resolve(refreshFn()).finally(() => {
          activeRefresh = null
        })
      } catch (error) {
        activeRefresh = null
        throw error
      }
    }
    return activeRefresh
  }
}

export function getHttpStatus(error) {
  if (typeof error === 'number') return error
  return error?.status || error?.response?.status || error?.code || null
}

export function isAuthInvalidStatus(status) {
  return status === 401 || status === 403
}

export function isTransientAuthFailure(error) {
  const status = getHttpStatus(error)
  return (
    status === 503 ||
    status === 'NETWORK_ERROR' ||
    status === 'ECONNABORTED' ||
    status === 'ETIMEDOUT' ||
    !status ||
    error?.isNetworkError === true ||
    !error?.response
  )
}

export async function handleRefreshFailureRecovery({
  refreshError,
  confirmCurrentSession,
  markRecoveryFailed,
  clearLocalSession,
  redirectToLogin,
  notifyTransientFailure,
  notifyRecovered,
}) {
  const status = getHttpStatus(refreshError)

  if (isTransientAuthFailure(refreshError) && !isAuthInvalidStatus(status)) {
    notifyTransientFailure?.(refreshError)
    return 'transient'
  }

  if (isAuthInvalidStatus(status)) {
    try {
      const stillValid = await confirmCurrentSession()
      if (stillValid) {
        notifyRecovered?.()
        return 'recovered'
      }
    } catch (confirmError) {
      if (!isAuthInvalidStatus(getHttpStatus(confirmError))) {
        notifyTransientFailure?.(confirmError)
        return 'transient'
      }
    }

    markRecoveryFailed?.()
    clearLocalSession?.()
    redirectToLogin?.()
    return 'invalid'
  }

  notifyTransientFailure?.(refreshError)
  return 'transient'
}

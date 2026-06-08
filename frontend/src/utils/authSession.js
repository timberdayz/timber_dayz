import { ROLE_CONFIG, normalizeRoleCode } from '../config/rolePermissions.js'

function normalizeRoles(inputRoles) {
  if (!Array.isArray(inputRoles) || inputRoles.length === 0) {
    return []
  }
  return inputRoles.map(normalizeRoleCode).filter(Boolean)
}

function resolvePermissions(userInfo = {}, roles = [], activeRole = '') {
  if (Array.isArray(userInfo.permissions) && userInfo.permissions.length > 0) {
    return userInfo.permissions
  }
  return activeRole ? (ROLE_CONFIG[activeRole]?.permissions || []) : []
}

export function deriveAccessTokenExpiresAt(expiresIn, nowMs = Date.now()) {
  const expiresInSeconds = Number(expiresIn)
  if (!Number.isFinite(expiresInSeconds) || expiresInSeconds <= 0) {
    return null
  }
  return nowMs + expiresInSeconds * 1000
}

function normalizeAccessTokenExpiresAt(value) {
  const expiresAt = Number(value)
  return Number.isFinite(expiresAt) && expiresAt > 0 ? expiresAt : null
}

export function buildPersistedAuthState(authPayload) {
  const userInfo = authPayload?.user_info || {}
  const roles = normalizeRoles(userInfo.roles)
  const activeRole = roles.includes('admin') ? 'admin' : (roles[0] || '')
  const permissions = resolvePermissions(userInfo, roles, activeRole)
  const entries = {
    user_info: JSON.stringify(userInfo),
    userInfo: JSON.stringify({
      id: userInfo.id,
      username: userInfo.username,
      name: userInfo.full_name || userInfo.username,
      email: userInfo.email,
      avatar: '',
      roles,
      permissions,
      is_admin: Boolean(userInfo.is_admin),
      activeRole,
    }),
    roles: JSON.stringify(roles),
    permissions: JSON.stringify(permissions),
    activeRole,
  }

  const accessTokenExpiresAt =
    normalizeAccessTokenExpiresAt(authPayload?.accessTokenExpiresAt) ||
    deriveAccessTokenExpiresAt(authPayload?.expires_in)
  if (accessTokenExpiresAt) {
    entries.accessTokenExpiresAt = String(accessTokenExpiresAt)
  }
  return entries
}

export function writePersistedAuthState(storage, authPayload) {
  const entries = buildPersistedAuthState(authPayload)
  Object.entries(entries).forEach(([key, value]) => {
    storage.setItem(key, value)
  })
  return entries
}

export function readPersistedAuthState(storage) {
  const accessToken = ''
  const refreshToken = ''
  const userInfoRaw = storage.getItem('userInfo')
  const authUserRaw = storage.getItem('user_info')
  const rolesRaw = storage.getItem('roles')
  const permissionsRaw = storage.getItem('permissions')
  const activeRole = storage.getItem('activeRole') || ''
  const accessTokenExpiresAt = normalizeAccessTokenExpiresAt(
    storage.getItem('accessTokenExpiresAt')
  )

  let authUser = null
  let userInfo = null
  let roles = []
  let permissions = []

  try {
    authUser = authUserRaw ? JSON.parse(authUserRaw) : null
  } catch {
    authUser = null
  }

  try {
    userInfo = userInfoRaw ? JSON.parse(userInfoRaw) : null
  } catch {
    userInfo = null
  }

  try {
    roles = rolesRaw ? JSON.parse(rolesRaw) : []
  } catch {
    roles = []
  }

  try {
    permissions = permissionsRaw ? JSON.parse(permissionsRaw) : []
  } catch {
    permissions = []
  }

  if ((!roles || roles.length === 0) && authUser?.roles) {
    roles = normalizeRoles(authUser.roles)
  }

  const resolvedActiveRole = activeRole || (roles.includes('admin') ? 'admin' : (roles[0] || ''))

  if (!userInfo && authUser) {
    userInfo = {
      id: authUser.id,
      username: authUser.username,
      name: authUser.full_name || authUser.username,
      email: authUser.email,
      avatar: '',
      roles,
      activeRole: resolvedActiveRole,
    }
  }

  if (!permissions || permissions.length === 0) {
    permissions = resolvePermissions(authUser || userInfo || {}, roles, resolvedActiveRole)
  }

  return {
    accessToken,
    refreshToken,
    authUser,
    userInfo,
    roles,
    permissions,
    activeRole: resolvedActiveRole,
    accessTokenExpiresAt,
  }
}

export function hasPersistedAuthSession(state) {
  return Boolean(state?.authUser)
}

export function hasAnyPersistedAuthArtifact(state) {
  return Boolean(state?.authUser || state?.userInfo)
}

export function clearPersistedAuthState(storage) {
  ;[
    'token',
    'access_token',
    'refresh_token',
    'user_info',
    'userInfo',
    'roles',
    'permissions',
    'activeRole',
    'accessTokenExpiresAt',
  ].forEach((key) => storage.removeItem(key))
}

const AUTH_RECOVERY_FAILED_KEY = 'auth_recovery_failed'

export function markAuthRecoveryFailed(storage) {
  storage.setItem(AUTH_RECOVERY_FAILED_KEY, '1')
}

export function hasAuthRecoveryFailed(storage) {
  return storage.getItem(AUTH_RECOVERY_FAILED_KEY) === '1'
}

export function resetAuthRecoveryState(storage) {
  storage.removeItem(AUTH_RECOVERY_FAILED_KEY)
}

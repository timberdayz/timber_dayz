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

export function buildPersistedAuthState(authPayload) {
  const userInfo = authPayload?.user_info || {}
  const roles = normalizeRoles(userInfo.roles)
  const activeRole = roles.includes('admin') ? 'admin' : (roles[0] || '')
  const permissions = resolvePermissions(userInfo, roles, activeRole)

  return {
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

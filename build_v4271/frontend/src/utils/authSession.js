import { ROLE_CONFIG, normalizeRoleCode } from '../config/rolePermissions.js'

function normalizeRoles(inputRoles) {
  if (!Array.isArray(inputRoles) || inputRoles.length === 0) {
    return ['admin']
  }
  return inputRoles.map(normalizeRoleCode).filter(Boolean)
}

export function buildPersistedAuthState(authPayload) {
  const userInfo = authPayload?.user_info || {}
  const roles = normalizeRoles(userInfo.roles)
  const activeRole = roles.includes('admin') ? 'admin' : roles[0]
  const permissions = ROLE_CONFIG[activeRole]?.permissions || []

  return {
    access_token: authPayload?.access_token || '',
    refresh_token: authPayload?.refresh_token || '',
    user_info: JSON.stringify(userInfo),
    userInfo: JSON.stringify({
      id: userInfo.id,
      username: userInfo.username,
      name: userInfo.full_name || userInfo.username,
      email: userInfo.email,
      avatar: '',
      roles,
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
  const accessToken = storage.getItem('access_token') || storage.getItem('token') || ''
  const refreshToken = storage.getItem('refresh_token') || ''
  const userInfoRaw = storage.getItem('userInfo')
  const authUserRaw = storage.getItem('user_info')
  const rolesRaw = storage.getItem('roles')
  const permissionsRaw = storage.getItem('permissions')
  const activeRole = storage.getItem('activeRole') || 'admin'

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

  if (!userInfo && authUser) {
    userInfo = {
      id: authUser.id,
      username: authUser.username,
      name: authUser.full_name || authUser.username,
      email: authUser.email,
      avatar: '',
      roles,
      activeRole,
    }
  }

  if ((!permissions || permissions.length === 0) && activeRole) {
    permissions = ROLE_CONFIG[activeRole]?.permissions || []
  }

  return {
    accessToken,
    refreshToken,
    authUser,
    userInfo,
    roles,
    permissions,
    activeRole,
  }
}

export function hasPersistedAuthSession(state) {
  return Boolean(state?.accessToken && state?.authUser)
}

export function hasAnyPersistedAuthArtifact(state) {
  return Boolean(
    state?.accessToken || state?.refreshToken || state?.authUser || state?.userInfo
  )
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

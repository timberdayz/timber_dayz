import { ROLE_CONFIG, normalizeRoleCode } from '../config/rolePermissions.js'

export function extractNormalizedRoles(roles) {
  if (!Array.isArray(roles)) return []
  return roles
    .map((role) => {
      if (typeof role === 'string') return normalizeRoleCode(role)
      return normalizeRoleCode(role?.role_code || role?.role_name || '')
    })
    .filter(Boolean)
}

export function hasAnyRole(roles, requiredRoles) {
  const normalizedRoles = extractNormalizedRoles(roles)
  const required = Array.isArray(requiredRoles) ? requiredRoles : [requiredRoles]
  return required.some((role) => normalizedRoles.includes(normalizeRoleCode(role)))
}

export function hasPermissionForRoles(roles, permission) {
  const normalizedRoles = extractNormalizedRoles(roles)
  if (normalizedRoles.includes('admin')) return true
  return normalizedRoles.some((role) => ROLE_CONFIG[role]?.permissions?.includes(permission))
}

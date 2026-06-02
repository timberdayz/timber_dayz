import { normalizeRoleCode } from '../config/rolePermissions.js'
import { extractNormalizedRoles, hasPermissionForRoles } from './authRoles.js'

const ACTION_PERMISSION_RULES = {
  campaign: {
    admin: ['campaign:read', 'campaign:create', 'campaign:update', 'campaign:delete'],
    manager: ['campaign:read', 'campaign:create', 'campaign:update'],
    operator: ['campaign:read'],
    finance: ['campaign:read'],
  },
  performance: {
    admin: ['performance:read', 'performance:config', 'performance:export'],
    manager: ['performance:read', 'performance:export'],
    operator: ['performance:read'],
    finance: ['performance:read'],
    tourist: ['performance:read'],
  },
  field_mapping: {
    admin: ['field-mapping'],
  },
}

function resolveRule(permission) {
  if (permission.startsWith('campaign:')) return ACTION_PERMISSION_RULES.campaign
  if (permission.startsWith('performance:')) return ACTION_PERMISSION_RULES.performance
  if (permission === 'field-mapping') return ACTION_PERMISSION_RULES.field_mapping
  return null
}

export function hasScopedActionPermission({ roles, activeRole, permission }) {
  const normalizedRoles = extractNormalizedRoles(roles)
  const normalizedActiveRole = normalizeRoleCode(activeRole || '')

  if (normalizedActiveRole === 'admin' || normalizedRoles.includes('admin')) {
    return true
  }

  const rule = resolveRule(permission)
  if (!rule) {
    return hasPermissionForRoles(roles, permission)
  }

  if (normalizedActiveRole) {
    return (rule[normalizedActiveRole] || []).includes(permission)
  }

  return normalizedRoles.some((role) => (rule[role] || []).includes(permission))
}

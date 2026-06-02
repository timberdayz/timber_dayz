/**
 * Frontend RBAC config.
 *
 * Page access uses router meta as the SSOT.
 * This file keeps:
 * - role display metadata
 * - persisted fallback permissions for auth/session recovery
 * - a small set of non-route action permissions still used inside pages
 */

export const ROLE_CONFIG = {
  admin: {
    name: '管理员',
    icon: 'UserFilled',
    permissions: [
      'business-overview',
      'collection-config', 'collection-coverage-audit', 'collection-tasks', 'collection-history',
      'component-recorder', 'component-versions',
      'data-sync', 'data-quarantine', 'data-governance', 'field-mapping',
      'sales-dashboard', 'sales-detail', 'customer-management', 'order-management',
      'campaign:read', 'campaign:create', 'campaign:update', 'campaign:delete',
      'target:read', 'config:sales-targets',
      'financial-management', 'expense-management', 'finance-reports', 'b-cost-analysis',
      'fx-management', 'fiscal-periods',
      'store-management', 'store-analytics', 'account-management', 'account-alignment',
      'human-resources', 'employee-management', 'my-income', 'my-follow-investment-income',
      'attendance-management', 'performance:read', 'performance:config', 'performance:export',
      'my-tasks', 'my-requests', 'approval-history', 'workflow-config',
      'notifications', 'alerts', 'message-settings',
      'training-management', 'training-integration', 'my-training',
      'user-management', 'role-management', 'permission-management',
      'system-settings', 'system-logs', 'data-backup', 'system-maintenance', 'notification-config',
      'personal-settings',
    ],
  },
  manager: {
    name: '主管',
    icon: 'Briefcase',
    permissions: [
      'business-overview',
      'sales-dashboard', 'order-management',
      'financial-management', 'expense-management', 'finance-reports', 'b-cost-analysis',
      'fx-management', 'fiscal-periods',
      'store-analytics',
      'employee-management', 'my-income', 'my-follow-investment-income',
      'attendance-management', 'performance:read',
      'my-tasks', 'my-requests', 'approval-history',
      'notifications', 'alerts', 'message-settings',
      'training-management', 'my-training',
      'personal-settings',
    ],
  },
  operator: {
    name: '操作员',
    icon: 'User',
    permissions: [
      'business-overview',
      'sales-dashboard', 'order-management',
      'store-analytics',
      'employee-management', 'my-income', 'my-follow-investment-income', 'performance:read',
      'my-tasks', 'my-requests', 'approval-history',
      'notifications', 'alerts', 'message-settings',
      'my-training',
      'personal-settings',
    ],
  },
  finance: {
    name: '财务',
    icon: 'Money',
    permissions: [
      'business-overview',
      'sales-dashboard', 'order-management',
      'financial-management', 'expense-management', 'finance-reports', 'b-cost-analysis',
      'fx-management', 'fiscal-periods',
      'employee-management', 'my-income', 'my-follow-investment-income', 'performance:read',
      'my-tasks', 'my-requests', 'approval-history',
      'notifications', 'alerts', 'message-settings',
      'my-training',
      'personal-settings',
    ],
  },
  investor: {
    name: '投资人',
    icon: 'Wallet',
    permissions: [
      'business-overview',
      'my-follow-investment-income',
    ],
  },
  tourist: {
    name: '游客',
    icon: 'View',
    permissions: [
      'business-overview',
      'performance:read',
    ],
  },
}

/** Normalize role identifiers from backend role_code / role_name payloads. */
export function normalizeRoleCode(roleCode) {
  if (!roleCode) return ''

  const value = String(roleCode).trim()
  if (ROLE_CONFIG[value]) return value

  const nameMap = {
    管理员: 'admin',
    主管: 'manager',
    经理: 'manager',
    操作员: 'operator',
    运营: 'operator',
    财务: 'finance',
    投资人: 'investor',
    游客: 'tourist',
  }

  if (nameMap[value]) return nameMap[value]

  const lower = value.toLowerCase()
  if (ROLE_CONFIG[lower]) return lower
  return value
}

/**
 * Apply fallback permissions to the user store when backend permissions are absent.
 */
export function applyRolePermissions(userStore, roleCode) {
  const roleConfig = ROLE_CONFIG[roleCode]
  if (!roleConfig) return false
  userStore.permissions = roleConfig.permissions
  localStorage.setItem('permissions', JSON.stringify(roleConfig.permissions))
  return true
}

/**
 * 角色权限配置（RBAC）
 * 用于登录时预置权限、SimpleAccountSwitcher 角色切换、路由守卫等
 * 根据 2026-01-08 讨论的权限矩阵
 */

export const ROLE_CONFIG = {
  admin: {
    name: '管理员',
    icon: 'UserFilled',
    permissions: [
      'business-overview',
      'annual-summary',
      'collection-config', 'collection-tasks', 'collection-history',
      'component-recorder', 'component-versions',
      'data-sync', 'data-quarantine', 'field-mapping',
      'product-management', 'inventory-management', 'inventory-dashboard-v3',
      'purchase-orders', 'grn-management', 'vendor-management', 'invoice-management',
      'sales-dashboard-v3', 'sales-analysis', 'customer-management', 'order-management',
      'target:read', 'config:sales-targets',
      'financial-management', 'expense-management', 'finance-reports',
      'fx-management', 'fiscal-periods',
      'store-management', 'store-analytics', 'account-management', 'account-alignment',
      'sales-reports', 'inventory-reports', 'finance-reports-detail',
      'vendor-reports', 'custom-reports',
      'human-resources', 'employee-management', 'my-income', 'attendance-management', 'performance:read', 'performance:config',
      'my-tasks', 'my-requests', 'approval-history', 'workflow-config',
      'system-notifications', 'alerts', 'message-settings',
      'user-management', 'role-management', 'permission-management',
      'system-settings', 'system-logs', 'data-backup', 'system-maintenance', 'notification-config',
      'personal-settings',
      'user-guide', 'video-tutorials', 'faq',
      'data-governance', 'sales-dashboard', 'data-collection', 'procurement',
      'report-center', 'approval-center', 'message-center', 'help-center',
      'notifications', 'product-category', 'inventory-alert'
    ]
  },
  manager: {
    name: '主管',
    icon: 'Briefcase',
    permissions: [
      'business-overview',
      'sales-dashboard-v3', 'sales-analysis', 'customer-management', 'order-management',
      'inventory-management', 'inventory-dashboard-v3',
      'store-management', 'store-analytics',
      'purchase-orders', 'grn-management', 'vendor-management',
      'financial-management', 'expense-management', 'finance-reports',
      'fx-management', 'fiscal-periods',
      'sales-reports', 'inventory-reports', 'vendor-reports',
      'employee-management', 'my-income', 'attendance-management', 'performance:read',
      'my-tasks', 'my-requests', 'approval-history',
      'system-notifications', 'alerts', 'message-settings',
      'personal-settings',
      'sales-dashboard', 'procurement', 'report-center', 'approval-center',
      'message-center', 'notifications'
    ]
  },
  operator: {
    name: '操作员',
    icon: 'User',
    permissions: [
      'business-overview',
      'sales-dashboard-v3', 'customer-management', 'order-management',
      'store-management', 'store-analytics',
      'employee-management', 'my-income', 'performance:read',
      'system-notifications', 'alerts', 'message-settings',
      'personal-settings',
      'sales-dashboard', 'message-center', 'notifications'
    ]
  },
  finance: {
    name: '财务',
    icon: 'Money',
    permissions: [
      'business-overview',
      'sales-analysis', 'sales-dashboard-v3', 'order-management',
      'purchase-orders', 'grn-management', 'vendor-management', 'invoice-management',
      'financial-management', 'expense-management', 'finance-reports', 'finance-reports-detail',
      'fx-management', 'fiscal-periods',
      'employee-management', 'my-income', 'performance:read',
      'system-notifications', 'alerts', 'message-settings',
      'personal-settings',
      'sales-dashboard', 'report-center', 'message-center', 'notifications'
    ]
  },
  tourist: {
    name: '游客',
    icon: 'View',
    permissions: ['business-overview', 'performance:read']
  }
}

/** 规范化角色代码（兼容后端 role_name/role_code） */
export function normalizeRoleCode(roleCode) {
  if (!roleCode) return ''
  const v = String(roleCode).trim()
  if (ROLE_CONFIG[v]) return v
  const map = {
    '管理员': 'admin',
    '主管': 'manager',
    '经理': 'manager',
    '操作员': 'operator',
    '运营': 'operator',
    '财务': 'finance',
    '游客': 'tourist'
  }
  if (map[v]) return map[v]
  const lower = v.toLowerCase()
  if (ROLE_CONFIG[lower]) return lower
  return v
}

/**
 * 根据角色代码应用权限到 userStore
 * 用于登录成功后预置权限（登录页未挂载 SimpleAccountSwitcher）
 */
export function applyRolePermissions(userStore, roleCode) {
  const roleConfig = ROLE_CONFIG[roleCode]
  if (!roleConfig) return false
  userStore.permissions = roleConfig.permissions
  localStorage.setItem('permissions', JSON.stringify(roleConfig.permissions))
  return true
}

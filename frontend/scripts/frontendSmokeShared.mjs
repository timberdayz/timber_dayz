export const SMOKE_ROUTES = [
  { name: 'BusinessOverview', path: '/business-overview', expectedTitle: '业务概览' },
  { name: 'SalesDashboardV3', path: '/sales-dashboard-v3', expectedTitle: '销售看板v3' },
  { name: 'SystemConfig', path: '/system-config', expectedTitle: '系统配置' },
  { name: 'InventoryManagement', path: '/inventory-management', expectedTitle: '库存管理' },
  { name: 'TargetManagement', path: '/target-management', expectedTitle: '目标管理' },
  { name: 'UserManagement', path: '/user-management', expectedTitle: '用户管理' },
  { name: 'RoleManagement', path: '/role-management', expectedTitle: '角色管理' },
  { name: 'PermissionManagement', path: '/permission-management', expectedTitle: '权限管理' },
  { name: 'AccountManagement', path: '/account-management', expectedTitle: '账号管理' },
  { name: 'Sessions', path: '/settings/sessions', expectedTitle: '会话管理' },
  { name: 'SystemNotifications', path: '/system-notifications', expectedTitle: '系统通知' },
  { name: 'DatabaseConfig', path: '/database-config', expectedTitle: '数据库配置' },
  { name: 'SecuritySettings', path: '/security-settings', expectedTitle: '安全设置' },
  { name: 'SystemLogs', path: '/system-logs', expectedTitle: '系统日志' },
  { name: 'DataBackup', path: '/data-backup', expectedTitle: '数据备份' },
  { name: 'NotificationConfig', path: '/notification-config', expectedTitle: '通知配置' },
  { name: 'SystemMaintenance', path: '/system-maintenance', expectedTitle: '系统维护' },
  { name: 'CollectionConfig', path: '/collection-config', expectedTitle: '采集配置' },
  { name: 'DataSyncTasks', path: '/data-sync/tasks', expectedTitle: '同步任务' },
  { name: 'DataSyncHistory', path: '/data-sync/history', expectedTitle: '同步历史' },
  { name: 'ComponentVersions', path: '/component-versions', expectedTitle: '组件版本管理' },
  { name: 'StoreAnalytics', path: '/store-analytics', expectedTitle: '店铺分析' },
  { name: 'FinancialOverview', path: '/financial-overview', expectedTitle: '财务总览' },
  { name: 'ExpenseManagement', path: '/expense-management', expectedTitle: '费用管理' },
  { name: 'InventoryDashboardV3', path: '/inventory-dashboard-v3', expectedTitle: '库存看板v3' },
  { name: 'InventoryHealth', path: '/inventory-health', expectedTitle: '库存健康仪表盘' },
  { name: 'ProductQuality', path: '/product-quality', expectedTitle: '产品质量仪表盘' },
  { name: 'SalesAnalysis', path: '/sales-analysis', expectedTitle: '销售分析' },
]

const ADMIN_PERMISSIONS = [
  'business-overview',
  'sales-dashboard',
  'system-settings',
  'inventory-management',
  'target:read',
  'user-management',
  'role-management',
  'permission-management',
]

export function buildAuthStorageEntries(authPayload) {
  const userInfo = authPayload?.user_info || {}
  const roles = Array.isArray(userInfo.roles) && userInfo.roles.length > 0 ? userInfo.roles : ['admin']
  const activeRole = roles.includes('admin') ? 'admin' : roles[0]
  const serializedUser = JSON.stringify(userInfo)

  return {
    access_token: authPayload?.access_token || '',
    refresh_token: authPayload?.refresh_token || '',
    user_info: serializedUser,
    userInfo: JSON.stringify({
      id: userInfo.id,
      username: userInfo.username,
      name: userInfo.full_name || userInfo.username,
      email: userInfo.email,
      avatar: '',
      roles,
    }),
    activeRole,
    roles: JSON.stringify(roles),
    permissions: JSON.stringify(ADMIN_PERMISSIONS),
  }
}

export function summarizeSmokeResults(results) {
  const failedRoutes = results
    .filter((item) => !item.ok)
    .map((item) => ({
      path: item.path,
      consoleErrors: item.consoleErrors || [],
      pageErrors: item.pageErrors || [],
      requestFailures: item.requestFailures || [],
      screenshotPath: item.screenshotPath || null,
    }))

  return {
    total: results.length,
    passed: results.length - failedRoutes.length,
    failed: failedRoutes.length,
    failedRoutes,
  }
}

export const SMOKE_ROUTES = [
  { name: 'BusinessOverview', path: '/business-overview', expectedTitle: '业务概览' },
  { name: 'SalesDashboardV3', path: '/sales-dashboard-v3', expectedTitle: '销售看板v3' },
  { name: 'SystemConfig', path: '/system-config', expectedTitle: '系统配置' },
  { name: 'InventoryManagement', path: '/inventory-management', expectedTitle: '库存管理' },
  { name: 'TargetManagement', path: '/target-management', expectedTitle: '目标管理' },
  { name: 'UserManagement', path: '/user-management', expectedTitle: '用户管理' },
  { name: 'RoleManagement', path: '/role-management', expectedTitle: '角色管理' },
  { name: 'PermissionManagement', path: '/permission-management', expectedTitle: '权限管理' },
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

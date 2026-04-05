import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const routerPath = path.resolve('frontend/src/router/index.js')
const routerText = fs.readFileSync(routerPath, 'utf8')

function extractRoutes(text) {
  const routeRegex = /\{\s*path:\s*'([^']+)'[\s\S]*?name:\s*'([^']+)'[\s\S]*?meta:\s*\{([\s\S]*?)\n\s*\}\s*\}/g
  const routes = []
  let match
  while ((match = routeRegex.exec(text)) !== null) {
    const [, routePath, name, meta] = match
    const permissionMatch = /permission:\s*(null|'([^']*)')/.exec(meta)
    const permission = permissionMatch
      ? permissionMatch[1] === 'null'
        ? null
        : permissionMatch[2]
      : undefined
    const rolesMatch = /roles:\s*\[([^\]]*)\]/.exec(meta)
    const roles = rolesMatch
      ? [...rolesMatch[1].matchAll(/'([^']+)'/g)].map((item) => item[1])
      : undefined
    routes.push({ path: routePath, name, permission, roles })
  }
  return routes
}

const routes = extractRoutes(routerText)

function findRoute(routePath) {
  const route = routes.find((item) => item.path === routePath)
  assert.ok(route, `missing route ${routePath}`)
  return route
}

test('no duplicate route path definitions remain', () => {
  const byPath = new Map()
  for (const route of routes) {
    byPath.set(route.path, (byPath.get(route.path) || 0) + 1)
  }
  const duplicates = [...byPath.entries()].filter(([, count]) => count > 1)
  assert.deepEqual(duplicates, [])
})

test('inventory view pages are open to admin manager operator', () => {
  for (const routePath of [
    '/inventory-management',
    '/inventory-overview',
    '/inventory/ledger',
    '/inventory/aging',
    '/inventory/alerts',
    '/inventory/reconciliation',
  ]) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin', 'manager', 'operator'])
    assert.equal(route.permission, 'inventory:view')
  }
})

test('inventory dashboard pages are open to admin manager operator', () => {
  for (const routePath of [
    '/inventory-health',
    '/product-quality',
    '/inventory-dashboard-v3',
  ]) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin', 'manager', 'operator'])
    assert.equal(route.permission, 'inventory-dashboard:view')
  }
})

test('inventory operation pages remain admin only', () => {
  for (const routePath of [
    '/inventory/adjustments',
    '/inventory/grns',
    '/inventory/opening-balances',
  ]) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin'])
    assert.equal(route.permission, 'inventory:manage')
  }
})

test('collection management pages remain admin only', () => {
  for (const routePath of [
    '/collection-config',
    '/collection-coverage-audit',
    '/collection-tasks',
    '/collection-history',
    '/component-recorder',
    '/component-versions',
  ]) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin'])
  }
})

test('employee management no longer relies on implicit open metadata', () => {
  const route = findRoute('/employee-management')
  assert.notEqual(route.permission, null)
  assert.ok(Array.isArray(route.roles) && route.roles.length > 0)
})

test('sales and store operation pages remain admin only', () => {
  for (const routePath of [
    '/sales-campaign-management',
    '/customer-management',
    '/order-management',
    '/sales/sales-detail-by-product',
    '/store-management',
  ]) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin'])
  }
})

test('sales and store view pages remain broadly visible to operations roles', () => {
  const salesAnalysis = findRoute('/sales-analysis')
  assert.deepEqual(salesAnalysis.roles, ['admin', 'manager', 'operator', 'finance'])

  const salesDashboard = findRoute('/sales-dashboard-v3')
  assert.deepEqual(salesDashboard.roles, ['admin', 'manager', 'operator', 'finance'])

  const storeAnalytics = findRoute('/store-analytics')
  assert.deepEqual(storeAnalytics.roles, ['admin', 'manager', 'operator'])
})

test('report pages follow view-vs-operation classification', () => {
  for (const routePath of ['/sales-reports', '/inventory-reports', '/vendor-reports']) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin', 'manager', 'operator'])
  }

  const financeDetail = findRoute('/finance-reports-detail')
  assert.deepEqual(financeDetail.roles, ['admin', 'finance'])

  const customReports = findRoute('/custom-reports')
  assert.deepEqual(customReports.roles, ['admin'])
})

test('hr approval and messaging pages follow personal view operation classification', () => {
  const employeeManagement = findRoute('/employee-management')
  assert.deepEqual(employeeManagement.roles, ['admin', 'manager', 'operator', 'finance'])

  const personalSettings = findRoute('/personal-settings')
  assert.deepEqual(personalSettings.roles, ['admin', 'manager', 'operator', 'finance'])

  const notificationPreferences = findRoute('/settings/notifications')
  assert.deepEqual(notificationPreferences.roles, ['admin', 'manager', 'operator', 'finance'])

  const sessions = findRoute('/settings/sessions')
  assert.deepEqual(sessions.roles, ['admin', 'manager', 'operator', 'finance'])

  for (const routePath of ['/my-tasks', '/my-requests', '/approval-history', '/workflow-config']) {
    const route = findRoute(routePath)
    assert.deepEqual(route.roles, ['admin'])
  }

  const systemNotifications = findRoute('/system-notifications')
  assert.deepEqual(systemNotifications.roles, ['admin', 'manager', 'operator', 'finance'])

  const alerts = findRoute('/alerts')
  assert.deepEqual(alerts.roles, ['admin', 'manager', 'operator', 'finance'])

  const messageSettings = findRoute('/message-settings')
  assert.deepEqual(messageSettings.roles, ['admin', 'manager', 'operator', 'finance'])
})

test('active routes do not declare roles without matching permissions', async () => {
  const { ROLE_CONFIG } = await import(pathToFileURL(path.resolve('frontend/src/config/rolePermissions.js')).href)
  const mismatches = routes
    .filter((route) => route.permission && Array.isArray(route.roles) && route.roles.length > 0)
    .flatMap((route) =>
      route.roles
        .filter((role) => role !== 'admin' && !(ROLE_CONFIG[role]?.permissions || []).includes(route.permission))
        .map((role) => ({ path: route.path, permission: route.permission, role }))
    )
  assert.deepEqual(mismatches, [])
})

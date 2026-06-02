import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const menuGroupsPath = path.resolve(__dirname, '../src/config/menuGroups.js')

const routerSource = fs.readFileSync(routerPath, 'utf8')
const menuGroupsSource = fs.readFileSync(menuGroupsPath, 'utf8')
const { ROLE_CONFIG } = await import(pathToFileURL(path.resolve(__dirname, '../src/config/rolePermissions.js')).href)

function parseRoutes(source) {
  const routes = []
  const routeRegex = /\{\s*path:\s*'([^']+)'[\s\S]*?meta:\s*\{([\s\S]*?)\}[\s\S]*?\}/g
  let match
  while ((match = routeRegex.exec(source))) {
    const meta = match[2]
    const permissionMatch = meta.match(/permission:\s*(null|'([^']+)')/)
    const rolesMatch = meta.match(/roles:\s*\[([^\]]*)\]/)
    routes.push({
      path: match[1],
      permission: permissionMatch ? (permissionMatch[1] === 'null' ? null : permissionMatch[2]) : undefined,
      roles: rolesMatch ? Array.from(rolesMatch[1].matchAll(/'([^']+)'/g)).map((item) => item[1]) : [],
    })
  }
  return routes
}

function parseMenuGroups(source) {
  const groups = []
  const groupRegex = /\{\s*id:\s*'([^']+)'[\s\S]*?title:\s*'([^']+)'[\s\S]*?items:\s*\[([\s\S]*?)\][\s\S]*?\}/g
  let match
  while ((match = groupRegex.exec(source))) {
    groups.push({
      id: match[1],
      title: match[2],
      items: Array.from(match[3].matchAll(/'([^']+)'/g)).map((item) => item[1]),
    })
  }
  return groups
}

const routes = parseRoutes(routerSource)
const routeMap = new Map(routes.map((route) => [route.path, route]))
const menuGroups = parseMenuGroups(menuGroupsSource)

function canAccess(route, role) {
  if (!route) return false
  if (role === 'admin') return true
  const permissionOk = !route.permission || (ROLE_CONFIG[role]?.permissions || []).includes(route.permission)
  const roleOk = !route.roles.length || route.roles.includes(role)
  return permissionOk && roleOk
}

function getVisibleMenuSnapshot(role) {
  return menuGroups
    .map((group) => ({
      title: group.title,
      items: group.items.filter((item) => canAccess(routeMap.get(item), role)),
    }))
    .filter((group) => group.items.length > 0)
}

test('visible menu snapshot stays stable for current non-admin roles', () => {
  assert.deepEqual(getVisibleMenuSnapshot('manager'), [
    { title: '工作台', items: ['/business-overview'] },
    { title: '销售与分析', items: ['/sales-dashboard-v3', '/sales/order-management'] },
    { title: '财务管理', items: ['/financial-management', '/expense-management', '/b-cost-analysis', '/finance-reports', '/fx-management', '/fiscal-periods'] },
    { title: '店铺运营', items: ['/store-analytics'] },
    { title: '人力资源', items: ['/employee-management', '/my-follow-investment-income'] },
    { title: '审批中心', items: ['/my-tasks', '/my-requests', '/approval-history'] },
    { title: '消息中心', items: ['/system-notifications', '/alerts', '/message-settings'] },
    { title: '系统管理', items: ['/personal-settings'] },
    { title: '帮助中心', items: ['/user-guide', '/video-tutorials', '/faq'] },
    { title: '培训管理', items: ['/training/overview', '/training/programs', '/training/assignments', '/training/results', '/my-training'] },
  ])

  assert.deepEqual(getVisibleMenuSnapshot('operator'), [
    { title: '工作台', items: ['/business-overview'] },
    { title: '销售与分析', items: ['/sales-dashboard-v3', '/sales/order-management'] },
    { title: '店铺运营', items: ['/store-analytics'] },
    { title: '人力资源', items: ['/employee-management', '/my-follow-investment-income'] },
    { title: '审批中心', items: ['/my-tasks', '/my-requests', '/approval-history'] },
    { title: '消息中心', items: ['/system-notifications', '/alerts', '/message-settings'] },
    { title: '系统管理', items: ['/personal-settings'] },
    { title: '帮助中心', items: ['/user-guide', '/video-tutorials', '/faq'] },
    { title: '培训管理', items: ['/my-training'] },
  ])

  assert.deepEqual(getVisibleMenuSnapshot('finance'), [
    { title: '工作台', items: ['/business-overview'] },
    { title: '销售与分析', items: ['/sales-dashboard-v3', '/sales/order-management'] },
    { title: '财务管理', items: ['/financial-management', '/expense-management', '/b-cost-analysis', '/finance-reports', '/fx-management', '/fiscal-periods'] },
    { title: '人力资源', items: ['/employee-management', '/my-follow-investment-income'] },
    { title: '审批中心', items: ['/my-tasks', '/my-requests', '/approval-history'] },
    { title: '消息中心', items: ['/system-notifications', '/alerts', '/message-settings'] },
    { title: '系统管理', items: ['/personal-settings'] },
    { title: '帮助中心', items: ['/user-guide', '/video-tutorials', '/faq'] },
    { title: '培训管理', items: ['/my-training'] },
  ])

  assert.deepEqual(getVisibleMenuSnapshot('investor'), [
    { title: '工作台', items: ['/business-overview'] },
    { title: '人力资源', items: ['/my-follow-investment-income'] },
    { title: '帮助中心', items: ['/user-guide', '/video-tutorials', '/faq'] },
  ])

  assert.deepEqual(getVisibleMenuSnapshot('tourist'), [
    { title: '工作台', items: ['/business-overview'] },
    { title: '帮助中心', items: ['/user-guide', '/video-tutorials', '/faq'] },
  ])
})

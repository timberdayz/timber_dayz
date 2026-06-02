import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const routerSource = fs.readFileSync(routerPath, 'utf8')

function parseRoutes(source) {
  const routes = []
  const routeRegex = /\{\s*path:\s*'([^']+)'[\s\S]*?meta:\s*\{([\s\S]*?)\}[\s\S]*?\}/g
  let match

  while ((match = routeRegex.exec(source))) {
    const metaSource = match[2]
    const permissionMatch = metaSource.match(/permission:\s*(null|'([^']+)')/)
    const rolesMatch = metaSource.match(/roles:\s*\[([^\]]*)\]/)

    routes.push({
      path: match[1],
      permission: permissionMatch ? (permissionMatch[1] === 'null' ? null : permissionMatch[2]) : undefined,
      roles: rolesMatch ? Array.from(rolesMatch[1].matchAll(/'([^']+)'/g)).map((item) => item[1]) : [],
    })
  }

  return routes
}

test('non-admin role permissions stay aligned with route-backed page access', async () => {
  const { ROLE_CONFIG } = await import(pathToFileURL(path.resolve(__dirname, '../src/config/rolePermissions.js')).href)
  const routes = parseRoutes(routerSource)

  for (const role of ['manager', 'operator', 'finance', 'investor', 'tourist']) {
    const routePermissions = new Set(
      routes
        .filter((route) => route.permission && route.roles.includes(role))
        .map((route) => route.permission),
    )

    const rolePermissions = ROLE_CONFIG[role]?.permissions || []
    const staleRoutePermissions = rolePermissions.filter(
      (permission) => routes.some((route) => route.permission === permission) && !routePermissions.has(permission),
    )
    const missingRoutePermissions = [...routePermissions].filter(
      (permission) => !rolePermissions.includes(permission),
    )

    assert.deepEqual(
      staleRoutePermissions,
      [],
      `${role} should not keep route-backed permissions for pages it cannot access`,
    )
    assert.deepEqual(
      missingRoutePermissions,
      [],
      `${role} should include every route-backed permission for pages it can access`,
    )
  }
})

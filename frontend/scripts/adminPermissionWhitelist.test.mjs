import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const routerSource = fs.readFileSync(routerPath, 'utf8')
const { ROLE_CONFIG } = await import(pathToFileURL(path.resolve(__dirname, '../src/config/rolePermissions.js')).href)

function parseRoutePermissions(source) {
  const permissions = new Set()
  const routeRegex = /\{\s*path:\s*'([^']+)'[\s\S]*?meta:\s*\{([\s\S]*?)\}[\s\S]*?\}/g
  let match
  while ((match = routeRegex.exec(source))) {
    const permissionMatch = match[2].match(/permission:\s*(null|'([^']+)')/)
    const permission = permissionMatch ? (permissionMatch[1] === 'null' ? null : permissionMatch[2]) : null
    if (permission) permissions.add(permission)
  }
  return permissions
}

test('admin keeps only explicit non-route action permissions outside router-backed page permissions', () => {
  const routePermissions = parseRoutePermissions(routerSource)
  const extraPermissions = ROLE_CONFIG.admin.permissions
    .filter((permission) => !routePermissions.has(permission))
    .sort()

  assert.deepEqual(extraPermissions, [
    'attendance-management',
    'campaign:create',
    'campaign:delete',
    'campaign:update',
    'data-backup',
    'data-quarantine',
    'field-mapping',
    'notification-config',
    'performance:export',
    'system-maintenance',
  ])
})

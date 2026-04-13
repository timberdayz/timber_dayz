import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerSource = fs.readFileSync(path.resolve(__dirname, '../src/router/index.js'), 'utf8')

function extractRouteBlock(routePath, nextRoutePath) {
  const start = routerSource.indexOf(`path: '${routePath}'`)
  const end = nextRoutePath ? routerSource.indexOf(`path: '${nextRoutePath}'`) : routerSource.length
  return routerSource.slice(start, end)
}

test('approval center routes expose expected role ranges', () => {
  const myRequestsBlock = extractRouteBlock('/my-requests', '/approval-history')
  assert.equal(
    myRequestsBlock.includes("roles: ['admin', 'manager', 'operator', 'finance']"),
    true
  )

  const approvalHistoryBlock = extractRouteBlock('/approval-history', '/workflow-config')
  assert.equal(
    approvalHistoryBlock.includes("roles: ['admin', 'manager', 'operator', 'finance']"),
    true
  )

  const workflowConfigBlock = extractRouteBlock('/workflow-config', '/system-notifications')
  assert.equal(
    workflowConfigBlock.includes("roles: ['admin']"),
    true
  )
})

test('approval center route permissions exist in role config for non-admin roles', async () => {
  const { ROLE_CONFIG } = await import(pathToFileURL(path.resolve(__dirname, '../src/config/rolePermissions.js')).href)

  for (const role of ['manager', 'operator', 'finance']) {
    assert.equal(ROLE_CONFIG[role].permissions.includes('my-requests'), true)
    assert.equal(ROLE_CONFIG[role].permissions.includes('approval-history'), true)
  }

  for (const role of ['manager', 'operator', 'finance']) {
    assert.equal(ROLE_CONFIG[role].permissions.includes('workflow-config'), false)
  }
})

import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewPath = resolve(projectRoot, 'frontend/src/views/collection/CollectionCoverageAudit.vue')
const apiPath = resolve(projectRoot, 'frontend/src/api/collection.js')
const routerPath = resolve(projectRoot, 'frontend/src/router/index.js')
const menuGroupsPath = resolve(projectRoot, 'frontend/src/config/menuGroups.js')
const rolePermissionsPath = resolve(projectRoot, 'frontend/src/config/rolePermissions.js')

assert.equal(existsSync(viewPath), true, 'CollectionCoverageAudit.vue should exist')

const viewText = readFileSync(viewPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')
const routerText = readFileSync(routerPath, 'utf8')
const menuGroupsText = readFileSync(menuGroupsPath, 'utf8')
const rolePermissionsText = readFileSync(rolePermissionsPath, 'utf8')

assert.match(viewText, /Collection Coverage Audit|采集覆盖率巡检/, 'audit page should expose audit title')
assert.match(viewText, /batchRemediate|批量补配/, 'audit page should expose batch remediation flow')
assert.match(viewText, /missing daily|缺日|missing weekly|缺周|missing monthly|缺月/, 'audit page should expose missing coverage filters')
assert.match(viewText, /daily_covered|weekly_covered|monthly_covered/, 'audit page should use per-granularity coverage fields')

assert.match(apiText, /batchRemediateConfigs/, 'collection api should expose batch remediation wrapper')
assert.match(apiText, /\/collection\/configs\/batch-remediate/, 'collection api should call the batch remediation endpoint')

assert.match(routerText, /CollectionCoverageAudit/, 'router should register the coverage audit page')
assert.match(routerText, /\/collection-coverage-audit/, 'router should expose the coverage audit route path')

assert.match(menuGroupsText, /\/collection-coverage-audit/, 'menu groups should include coverage audit entry')
assert.match(rolePermissionsText, /collection-coverage-audit/, 'role permissions should include coverage audit permission')

console.log('collectionCoverageAuditUi.test.mjs passed')

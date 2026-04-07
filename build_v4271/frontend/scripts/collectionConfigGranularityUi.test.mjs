import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewText = readFileSync(resolve(projectRoot, 'frontend/src/views/collection/CollectionConfig.vue'), 'utf8')
const apiText = readFileSync(resolve(projectRoot, 'frontend/src/api/collection.js'), 'utf8')
const constantsText = readFileSync(resolve(projectRoot, 'frontend/src/constants/collection.js'), 'utf8')

assert.match(viewText, /activeGranularity/, 'CollectionConfig.vue should track the active granularity view')
assert.match(viewText, /daily|weekly|monthly/, 'CollectionConfig.vue should expose daily weekly monthly views')
assert.match(viewText, /coverage/, 'CollectionConfig.vue should render coverage data')
assert.match(viewText, /applyCapabilitiesToAllShopScopes/, 'CollectionConfig.vue should auto-apply shop capabilities into shop scopes')
assert.match(viewText, /shop_scopes/, 'CollectionConfig.vue should use shop scope payloads')
assert.match(viewText, /runConfig/, 'CollectionConfig.vue should provide config-level execution')

assert.match(apiText, /getGroupedAccounts/, 'collection api should expose grouped accounts endpoint')
assert.match(apiText, /getConfigCoverage/, 'collection api should expose coverage endpoint')
assert.match(apiText, /runConfig/, 'collection api should expose config-level run endpoint')

assert.match(constantsText, /normalizeConfigGranularity/, 'collection constants should expose config granularity normalization')
assert.match(constantsText, /buildAutoSelectedSubDomains/, 'collection constants should expose subtype auto-select helper')

console.log('collectionConfigGranularityUi.test.mjs passed')

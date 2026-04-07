import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewText = readFileSync(resolve(projectRoot, 'frontend/src/views/collection/CollectionConfig.vue'), 'utf8')
const apiText = readFileSync(resolve(projectRoot, 'frontend/src/api/collection.js'), 'utf8')

assert.match(viewText, /shop_scopes/, 'CollectionConfig.vue should use shop_scopes payloads')
assert.match(viewText, /shopScopeRows/, 'CollectionConfig.vue should render shop-scope rows')
assert.match(viewText, /applyCapabilitiesToAllShopScopes/, 'CollectionConfig.vue should auto-apply capabilities per shop')
assert.match(viewText, /runConfig\(row\)/, 'CollectionConfig.vue should expose config-level run action')
assert.ok(!/for \(const accountId of accountIds\)/.test(viewText), 'CollectionConfig.vue should not fan out tasks per shop on the client')

assert.match(apiText, /export const runConfig = async/, 'collection api should expose runConfig')
assert.match(apiText, /\/collection\/configs\/\$\{id\}\/run/, 'runConfig should call the backend config-run endpoint')

console.log('collectionConfigShopScopeUi.test.mjs passed')

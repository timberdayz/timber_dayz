import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewText = readFileSync(resolve(projectRoot, 'frontend/src/views/collection/CollectionConfig.vue'), 'utf8')

assert.match(viewText, /filters\.main_account_id/, 'CollectionConfig.vue should expose a main-account list filter')
assert.match(viewText, /filters\.date_range_type/, 'CollectionConfig.vue should expose a date-range list filter')
assert.match(viewText, /filters\.execution_mode/, 'CollectionConfig.vue should expose an execution-mode list filter')
assert.match(viewText, /filters\.schedule_enabled/, 'CollectionConfig.vue should expose a schedule-enabled list filter')
assert.match(viewText, /form\.main_account_id/, 'CollectionConfig.vue should include main_account_id in the form state')
assert.match(viewText, /onMainAccountChange/, 'CollectionConfig.vue should react when the selected main account changes')
assert.match(viewText, /buildDefaultShopScopes\(form\.platform,\s*form\.main_account_id/, 'CollectionConfig.vue should build shop scopes from platform and main account together')
assert.match(viewText, /data-testid="collection-config-main-account-filter"/, 'CollectionConfig.vue should expose a main-account filter hook')
assert.match(viewText, /data-testid="collection-config-main-account-field"/, 'CollectionConfig.vue should expose a dialog main-account field hook')
assert.match(viewText, /class="full-width-select"/, 'CollectionConfig.vue should apply a full-width select class to avoid collapsed platform/main-account selectors')
assert.ok(!viewText.includes('<el-option label="Shopee" value="shopee" />'), 'CollectionConfig.vue should not hardcode platform options in template')

console.log('collectionConfigMainAccountUi.test.mjs passed')

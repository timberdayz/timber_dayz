import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewText = readFileSync(resolve(projectRoot, 'src/domains/collection/views/collection/CollectionConfig.vue'), 'utf8')

assert.match(viewText, /selectedMainAccountKey/, 'CollectionConfig.vue should track the selected main account')
assert.match(viewText, /mainAccountCards/, 'CollectionConfig.vue should build main-account navigation cards')
assert.match(viewText, /showOnlyAttentionAccounts/, 'CollectionConfig.vue should support filtering accounts needing attention')
assert.match(viewText, /form\.main_account_id/, 'CollectionConfig.vue should include main_account_id in the form state')
assert.match(viewText, /onTemplateMainAccountChange/, 'CollectionConfig.vue should react when the dialog main account changes')
assert.match(viewText, /buildDefaultShopScopes\(form\.platform,\s*form\.main_account_id/, 'CollectionConfig.vue should build shop scopes from platform and main account together')
assert.match(viewText, /data-testid="collection-config-main-account-field"/, 'CollectionConfig.vue should expose a dialog main-account field hook')
assert.match(viewText, /class="full-width-select"/, 'CollectionConfig.vue should apply a full-width select class to avoid collapsed selectors')
assert.match(viewText, /class="collection-config-editor-dialog"/, 'CollectionConfig.vue should attach a dialog class so the editor can be constrained to viewport height')
assert.match(viewText, /:deep\(\.collection-config-editor-dialog \.el-dialog__body\)/, 'CollectionConfig.vue should constrain dialog body scrolling')
assert.match(viewText, /openCurrentConfigDialog/, 'CollectionConfig.vue should expose the current-config editor entry')
assert.ok(!viewText.includes('<el-option label="Shopee" value="shopee" />'), 'CollectionConfig.vue should not hardcode platform options in template')

console.log('collectionConfigMainAccountUi.test.mjs passed')

import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/collection.js')
const viewPath = path.resolve(__dirname, '../src/domains/collection/views/collection/CollectionConfig.vue')

const apiSource = fs.readFileSync(apiPath, 'utf8')
const viewSource = fs.readFileSync(viewPath, 'utf8')

test('collection api exposes current-config workbench endpoints', () => {
  assert.equal(apiSource.includes('getConfigTemplates'), true)
  assert.equal(apiSource.includes('createConfigTemplate'), true)
  assert.equal(apiSource.includes('updateConfigTemplate'), true)
  assert.equal(apiSource.includes('createConfigBatch'), true)
  assert.equal(apiSource.includes('advanceCurrentConfig'), true)
  assert.equal(apiSource.includes('applyTimeSelectionCurrentGranularity'), true)
  assert.equal(apiSource.includes('getGranularitySchedule'), true)
  assert.equal(apiSource.includes('updateGranularitySchedule'), true)
  assert.equal(apiSource.includes('reapplyTemplateDefaults'), true)
  assert.equal(apiSource.includes('backfillLegacyConfigTemplates'), true)
})

test('collection config workbench renders main-account current-config shop layout', () => {
  assert.equal(viewSource.includes('主账号导航'), true)
  assert.equal(viewSource.includes('当前配置'), true)
  assert.equal(viewSource.includes('shop-panel'), true)
  assert.equal(viewSource.includes('selectedMainAccountCard'), true)
  assert.equal(viewSource.includes('currentConfigSummary'), true)
  assert.equal(viewSource.includes('batch_key'), true)
  assert.equal(viewSource.includes('shop_overrides'), true)
  assert.equal(viewSource.includes('onlyExceptionShops'), true)
  assert.equal(viewSource.includes('saveCurrentConfigFromWorkbench'), true)
  assert.equal(viewSource.includes('setCurrentConfigToAvailableDay'), true)
  assert.equal(viewSource.includes('applyTimeSelectionCurrentGranularity'), true)
  assert.equal(viewSource.includes('全部按月自定义'), true)
  assert.equal(viewSource.includes('全部到最近可采集日'), true)
  assert.equal(viewSource.includes('全部主账号推进到下一月'), false)
  assert.equal(viewSource.includes('toggleGranularitySchedule'), true)
  assert.equal(viewSource.includes('currentGranularityScheduleDescription'), true)
  assert.equal(viewSource.includes('collectionHealth'), true)
  assert.equal(viewSource.includes('currentScheduleInfo'), true)
  assert.equal(viewSource.includes('missing_shop_scope_ids'), true)
  assert.equal(viewSource.includes('stale_shop_scope_ids'), true)
  assert.equal(viewSource.includes('backfillLegacyTemplates'), true)
  assert.equal(viewSource.includes('v-model="row.scope.enabled"'), true)
  assert.equal(viewSource.includes('v-model="row.scope.data_domains"'), true)
})

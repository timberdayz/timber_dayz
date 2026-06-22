import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const viewSource = readFileSync(resolve(repoRoot, 'src/domains/data_platform/views/DataSyncFiles.vue'), 'utf8')
const templateManagementSource = readFileSync(
  resolve(repoRoot, 'src/domains/data_platform/views/DataSyncTemplates.vue'),
  'utf8',
)
const templateDeduplicationPanelSource = readFileSync(
  resolve(repoRoot, 'src/components/dataSync/TemplateDeduplicationReviewPanel.vue'),
  'utf8',
)
const templateUpdateWorkbenchSource = readFileSync(
  resolve(repoRoot, 'src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue'),
  'utf8',
)

test('data sync cleanup API exposes impact preview endpoint', () => {
  assert.match(
    apiSource,
    /async getCleanupDatabaseImpact\s*\(\s*\)\s*\{[\s\S]*?_get\('\s*\/data-sync\/cleanup-database\/impact'\s*\)/,
  )
})

test('data sync cleanup button previews rebuildable reset impact before execute', () => {
  assert.match(viewSource, /清空事实数据并重置可重建文件/)
  assert.match(viewSource, /api\.getCleanupDatabaseImpact\(\)/)
  assert.match(viewSource, /buildCleanupImpactHtml/)
  assert.match(viewSource, /source_missing_count/)
})

test('data sync cleanup preview shows controlled rebuild recommendation', () => {
  assert.match(viewSource, /recommended_rebuild_mode/)
  assert.match(viewSource, /recommended_batch_size/)
  assert.match(viewSource, /recommended_max_concurrent/)
  assert.match(viewSource, /skipped_processing_count/)
  assert.match(viewSource, /controlled_auto_ingest/)
})

test('data sync files view treats source_missing as an anomaly status', () => {
  assert.match(viewSource, /el-option label="源文件缺失" value="source_missing"/)
  assert.match(viewSource, /source_missing:\s*'warning'/)
  assert.match(viewSource, /source_missing:\s*'源文件缺失'/)
  assert.match(viewSource, /源文件缺失/)
  assert.match(viewSource, /file\.status === 'source_missing'/)
})

test('data sync files view shows semantic contract drift details', () => {
  assert.match(viewSource, /getTemplateStatusTooltip/)
  assert.match(viewSource, /semantic_contract_status/)
  assert.match(viewSource, /missing_required_keys/)
  assert.match(viewSource, /missing_optional_keys/)
  assert.match(viewSource, /impact_descriptions/)
  assert.match(viewSource, /模板待确认：缺少业务概览 required 语义字段/)
  assert.match(viewSource, /非破坏性变更：核心语义字段完整，允许降级同步/)
  assert.match(viewSource, /降级同步/)
})

test('template update workbench uses backend hash options for Data Hash choices', () => {
  assert.match(templateUpdateWorkbenchSource, /:hash-options="effectiveHashOptions"/)
  assert.match(templateUpdateWorkbenchSource, /workbenchContext\.value\?\.hash_options/)
  assert.match(templateUpdateWorkbenchSource, /const effectiveHashOptions = computed/)
  assert.match(templateUpdateWorkbenchSource, /buildHashOptionsFromHeaderBindings/)
  assert.match(templateUpdateWorkbenchSource, /recommendedStrongIdentityKeys/)
  assert.match(templateDeduplicationPanelSource, /hashOptions/)
  assert.match(templateDeduplicationPanelSource, /legacy_compatible/)
  assert.match(templateDeduplicationPanelSource, /weak_identity/)
  assert.doesNotMatch(templateDeduplicationPanelSource, /isHashEligibleSemanticKey\(binding\?\.semantic_key\)/)
})

test('template update workbench auto-selects newly confirmed strong hash identities', () => {
  assert.match(templateUpdateWorkbenchSource, /function mergeRecommendedIdentityFields/)
  assert.match(templateUpdateWorkbenchSource, /preferredSemanticKey = isRecommendedStrongIdentityKey/)
  assert.match(templateUpdateWorkbenchSource, /selectedDeduplicationFields\.value = mergeRecommendedIdentityFields/)
  assert.doesNotMatch(templateUpdateWorkbenchSource, /:hash-options="hashOptions"/)
})

test('template hash panel merges backend options with edited bindings', () => {
  assert.match(templateDeduplicationPanelSource, /mergeHashOptionsWithCurrentBindings/)
  assert.match(templateDeduplicationPanelSource, /props\.currentHeaderBindings/)
  assert.match(templateDeduplicationPanelSource, /blocked_reason/)
  assert.match(templateDeduplicationPanelSource, /legacyCompatible/)
})

test('template save errors explain family hash semantic key changes', () => {
  assert.match(templateManagementSource, /family_hash_keys/)
  assert.match(templateManagementSource, /current_hash_keys/)
  assert.match(templateManagementSource, /semantic_hash_key_changes/)
  assert.match(templateManagementSource, /suggested_action/)
  assert.match(templateManagementSource, /Hash口径/)
})

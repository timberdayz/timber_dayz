import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const viewSource = readFileSync(resolve(repoRoot, 'src/domains/data_platform/views/DataSyncFiles.vue'), 'utf8')

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
  assert.match(viewSource, /row\.status === 'source_missing'/)
  assert.match(viewSource, /源文件缺失/)
  assert.match(viewSource, /file\.status === 'source_missing'/)
})

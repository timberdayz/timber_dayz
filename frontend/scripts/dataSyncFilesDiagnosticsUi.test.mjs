import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const apiPath = resolve(projectRoot, 'src/api/index.js')
const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncFiles.vue')

const apiSource = readFileSync(apiPath, 'utf8')
const viewSource = readFileSync(viewPath, 'utf8')

assert.match(
  apiSource,
  /async refreshPendingFiles\(\)\s*\{[\s\S]*?_post\('\/data-sync\/files\/refresh'\)/,
  'refreshPendingFiles should call the data-sync refresh endpoint'
)

assert.match(
  apiSource,
  /async getDataSyncFileDiagnostics\s*\(\s*params\s*=\s*\{\}\s*\)\s*\{[\s\S]*?_get\('\/data-sync\/files\/diagnostics'/,
  'frontend api should expose file diagnostics endpoint'
)

assert.match(
  apiSource,
  /async syncBatchByFileIds[\s\S]*file_ids:\s*fileIds/,
  'batch sync should still submit catalog file ids'
)

assert.match(
  viewSource,
  /rawUnregisteredHint|hiddenSemanticInvalidCount/,
  'DataSyncFiles should track hidden and unregistered file hints'
)

assert.match(
  viewSource,
  /文件列表为空，但发现可能不可同步的采集文件/,
  'DataSyncFiles should show an empty-list diagnostics alert'
)

assert.match(
  viewSource,
  /loadFileDiagnostics|api\.getDataSyncFileDiagnostics/,
  'DataSyncFiles should load diagnostics from the api'
)

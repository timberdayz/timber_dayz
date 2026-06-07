import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const apiPath = resolve(projectRoot, 'src/api/index.js')
const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncFiles.vue')
const detailViewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncFileDetail.vue')

const apiSource = readFileSync(apiPath, 'utf8')
const viewSource = readFileSync(viewPath, 'utf8')
const detailViewSource = readFileSync(detailViewPath, 'utf8')

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
  /async getDataSyncFileDetail\s*\(\s*fileId\s*\)\s*\{[\s\S]*?_get\(`\/data-sync\/files\/\$\{fileId\}`\)/,
  'frontend api should expose the data-sync file detail endpoint'
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

assert.match(
  viewSource,
  /const activeFileView = ref\('ready'\)/,
  'DataSyncFiles should default to the ready-to-sync view'
)

assert.match(
  viewSource,
  /const filters = ref\(\{[\s\S]*status:\s*'pending'/,
  'DataSyncFiles should request pending files for the default ready-to-sync view'
)

assert.match(
  viewSource,
  /activeFileView|fileViewOptions/,
  'DataSyncFiles should expose asset-ledger view switching'
)

assert.match(
  viewSource,
  /official_unregistered_count/,
  'DataSyncFiles should use official unregistered raw count for blocking diagnostics'
)

assert.match(
  viewSource,
  /collection_platform|business_platform/,
  'DataSyncFiles should render collection and business platform fields'
)

assert.match(
  viewSource,
  /collection_task_id:\s*collectionTaskId\.value/,
  'DataSyncFiles should pass collection task filters to the file list api'
)

assert.match(
  viewSource,
  /pagination\.total/,
  'DataSyncFiles should use backend pagination total for list totals'
)

assert.match(
  detailViewSource,
  /采集文件资产链路|rawFileInfo|metaFileInfo|catalogRecordInfo/,
  'DataSyncFileDetail should show raw, meta, and catalog sections'
)

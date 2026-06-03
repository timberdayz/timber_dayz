import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncFiles.vue')
const apiPath = resolve(projectRoot, 'src/api/index.js')

const viewText = readFileSync(viewPath, 'utf8')
const apiText = readFileSync(apiPath, 'utf8')

assert.match(viewText, /semantic_invalid|语义异常/, 'file list should surface semantic invalid inventory files')
assert.match(viewText, /repairInventorySnapshot|修复为 snapshot/, 'file list should expose an inventory snapshot repair action')
assert.match(viewText, /templateStatus === 'semantic_invalid'/, 'file list should block syncing semantic invalid files')
assert.match(apiText, /repairInventorySnapshotSemantics/, 'frontend api should expose inventory snapshot repair')

console.log('dataSyncInventoryAnomalyUi.test.mjs passed')

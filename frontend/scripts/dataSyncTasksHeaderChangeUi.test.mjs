import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const filePath = resolve(process.cwd(), 'frontend/src/domains/data_platform/views/DataSyncTasks.vue')
const text = readFileSync(filePath, 'utf8')

assert.match(text, /getHeaderChangeErrors/, 'task view should surface header-change hints')
assert.match(text, /模板更新/, 'task view should display a template-update alert')
assert.match(text, /is_header_changed/, 'task view should classify header-change errors')

console.log('dataSyncTasksHeaderChangeUi.test.mjs passed')

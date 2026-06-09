import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const viewSource = readFileSync(resolve(repoRoot, 'src/domains/data_platform/views/DataSyncTasks.vue'), 'utf8')

test('data sync tasks API exposes cancel and recover endpoints', () => {
  assert.match(apiSource, /cancelSyncTask\s*\(\s*taskId\s*\)/)
  assert.match(apiSource, /recoverSyncTask\s*\(\s*taskId\s*\)/)
  assert.match(apiSource, /\/data-sync\/tasks\/\$\{taskId\}\/cancel/)
  assert.match(apiSource, /\/data-sync\/tasks\/\$\{taskId\}\/recover/)
})

test('data sync tasks view prefers canonical progress_percent and heartbeat state', () => {
  assert.match(viewSource, /progress_percent/)
  assert.match(viewSource, /heartbeat_at/)
  assert.match(viewSource, /stale_running/)
  assert.match(viewSource, /疑似卡住/)
})

test('data sync tasks view exposes cancel and recover actions', () => {
  assert.match(viewSource, /cancelSyncTask/)
  assert.match(viewSource, /recoverSyncTask/)
  assert.match(viewSource, /强制恢复/)
})

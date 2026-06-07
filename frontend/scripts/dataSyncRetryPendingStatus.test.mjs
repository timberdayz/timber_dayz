import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncFiles.vue')
const viewText = readFileSync(viewPath, 'utf8')

const retrySingleMatch = viewText.match(/const retrySingle = async \(fileId\) => \{([\s\S]*?)\n\}/)
assert.ok(retrySingleMatch, 'DataSyncFiles should define retrySingle')

const retrySingleBody = retrySingleMatch[1]

assert.match(
  retrySingleBody,
  /result\?\.task_id && \(result\?\.status === 'submitted' \|\| result\?\.status === 'pending'\)/,
  'retrySingle should accept both submitted and pending task submission statuses'
)
assert.match(
  retrySingleBody,
  /startProgressPolling\(result\.task_id\)/,
  'retrySingle should start progress polling after task submission'
)

console.log('dataSyncRetryPendingStatus.test.mjs passed')

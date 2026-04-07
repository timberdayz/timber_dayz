import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/collection.js')
const tasksViewPath = path.resolve(__dirname, '../src/views/collection/CollectionTasks.vue')

const apiSource = fs.readFileSync(apiPath, 'utf8')
const tasksSource = fs.readFileSync(tasksViewPath, 'utf8')

test('collection task websocket falls back to persisted access token', () => {
  assert.equal(
    apiSource.includes("const effectiveToken = token || localStorage.getItem('access_token') || ''"),
    true,
    'task websocket should reuse persisted access token when caller does not pass one'
  )
})

test('CollectionTasks auto-opens verification dialog when verification_required tasks are loaded', () => {
  assert.equal(
    tasksSource.includes('syncVerificationDialogFromTasks(tasks.value)'),
    true,
    'task list loading should sync paused verification tasks into the verification dialog'
  )

  assert.equal(
    tasksSource.includes("['verification_required', 'paused'].includes(task.status) && task.verification_type"),
    true,
    'task page should detect verification-required tasks from polled task data while remaining compatible with paused legacy tasks'
  )
})

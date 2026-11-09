import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/collection.js')
const tasksViewPath = path.resolve(__dirname, '../src/domains/collection/views/collection/CollectionTasks.vue')

const apiSource = fs.readFileSync(apiPath, 'utf8')
const tasksSource = fs.readFileSync(tasksViewPath, 'utf8')

test('collection task websocket relies on the session cookie instead of a persisted access token', () => {
  // 登录优化后 access_token 已搬进 httpOnly cookie，浏览器不再持有令牌，
  // 前端如果再去 localStorage 取一次，就等于又造了一份令牌真相点。
  assert.equal(
    apiSource.includes("const effectiveToken = token || ''"),
    true,
    'task websocket should only use the token explicitly passed by the caller'
  )

  assert.equal(
    apiSource.includes("localStorage.getItem('access_token')"),
    false,
    'task websocket must not read a persisted access token: the session now lives in an httpOnly cookie'
  )

  assert.equal(
    apiSource.includes('if (effectiveToken) {'),
    true,
    'task websocket should only append the token query parameter when a token is actually available'
  )
})

test('CollectionTasks auto-opens verification dialog when verification_required tasks are loaded', () => {
  assert.equal(
    tasksSource.includes('syncVerificationDialogFromTasks(tasks.value)'),
    true,
    'task list loading should sync paused verification tasks into the verification dialog'
  )

  assert.equal(
    tasksSource.includes("['verification_required', 'paused', 'manual_intervention_required'].includes(task.status) && task.verification_type"),
    true,
    'task page should detect verification-required tasks from polled task data while remaining compatible with paused and intervention-required legacy states'
  )
})

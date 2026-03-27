import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/CollectionTasks.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('CollectionTasks uses shared verification dialog and exposes pending verification items', () => {
  assert.equal(
    source.includes('VerificationResumeDialog'),
    true,
    'task page should reuse the shared verification dialog'
  )

  assert.equal(
    source.includes('pendingVerificationItems'),
    true,
    'task page should expose a pending verification list for multi-account handling'
  )

  assert.equal(
    source.includes('getVerificationItems'),
    true,
    'task page should consume the dedicated verification-items data source'
  )

  assert.equal(
    source.includes('verificationSummary'),
    true,
    'task page should expose summary metrics for pending verification work'
  )

  assert.equal(
    source.includes('viewVerificationScreenshot'),
    true,
    'task page should expose a screenshot preview action'
  )

  assert.equal(
    source.includes('copyTaskId'),
    true,
    'task page should expose a copy task id action'
  )

  assert.equal(
    source.includes('focusTaskRow'),
    true,
    'task page should expose a task focus action'
  )
})

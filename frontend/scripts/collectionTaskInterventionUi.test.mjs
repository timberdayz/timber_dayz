import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const configViewPath = path.resolve(__dirname, '../src/views/collection/CollectionConfig.vue')
const tasksViewPath = path.resolve(__dirname, '../src/views/collection/CollectionTasks.vue')
const historyViewPath = path.resolve(__dirname, '../src/views/collection/CollectionHistory.vue')

const configSource = fs.readFileSync(configViewPath, 'utf8')
const tasksSource = fs.readFileSync(tasksViewPath, 'utf8')
const historySource = fs.readFileSync(historyViewPath, 'utf8')

test('CollectionConfig does not directly host verification recovery UI', () => {
  assert.equal(
    configSource.includes('VerificationResumeDialog'),
    false,
    'config page should not host verification recovery dialog directly'
  )

  assert.equal(
    configSource.includes('verificationDialogVisible'),
    false,
    'config page should not own runtime verification state'
  )
})

test('CollectionTasks is the single runtime intervention surface', () => {
  assert.equal(
    tasksSource.includes('VerificationResumeDialog'),
    true,
    'task page should reuse the shared verification dialog'
  )

  assert.equal(
    tasksSource.includes('pendingVerificationItems'),
    true,
    'task page should expose a pending verification queue'
  )

  assert.equal(
    tasksSource.includes('sortedPendingVerificationItems'),
    true,
    'task page should sort pending intervention items before rendering'
  )

  assert.equal(
    tasksSource.includes('getVerificationItems'),
    true,
    'task page should consume the dedicated verification-items data source for the waiting queue'
  )

  assert.equal(
    tasksSource.includes('manual_intervention_required'),
    true,
    'task page should explicitly model manual intervention required tasks'
  )

  assert.equal(
    tasksSource.includes('executionMode') || tasksSource.includes('debugMode'),
    true,
    'task page should expose a task-level execution mode override'
  )
})

test('CollectionHistory does not expose runtime retry or intervention actions', () => {
  assert.equal(
    historySource.includes('retryTask('),
    false,
    'history page should not expose retry actions'
  )

  assert.equal(
    historySource.includes('verification'),
    false,
    'history page should not expose verification handling'
  )

  assert.equal(
    historySource.includes('执行模式'),
    true,
    'history page should still display execution mode for audit visibility'
  )
})

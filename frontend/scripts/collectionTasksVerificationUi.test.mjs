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
})

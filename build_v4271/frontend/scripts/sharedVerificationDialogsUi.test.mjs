import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const files = [
  path.resolve(__dirname, '../src/views/ComponentRecorder.vue'),
  path.resolve(__dirname, '../src/views/ComponentVersions.vue'),
  path.resolve(__dirname, '../src/views/CollectionTasks.vue')
]

test('recorder, component test, and collection task pages all reuse VerificationResumeDialog', () => {
  for (const file of files) {
    const source = fs.readFileSync(file, 'utf8')
    assert.equal(
      source.includes('VerificationResumeDialog'),
      true,
      `${path.basename(file)} should reuse VerificationResumeDialog`
    )
  }
})

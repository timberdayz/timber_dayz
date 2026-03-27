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

test('shared verification dialog receives message, expires-at, and error-message props across all owner pages', () => {
  for (const file of files) {
    const source = fs.readFileSync(file, 'utf8')
    assert.equal(
      source.includes(':message='),
      true,
      `${path.basename(file)} should pass message to VerificationResumeDialog`
    )
    assert.equal(
      source.includes(':expires-at='),
      true,
      `${path.basename(file)} should pass expires-at to VerificationResumeDialog`
    )
    assert.equal(
      source.includes(':error-message='),
      true,
      `${path.basename(file)} should pass error-message to VerificationResumeDialog`
    )
  }
})

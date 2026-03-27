import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/ComponentVersions.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('ComponentVersions uses shared verification dialog instead of inline captcha card', () => {
  assert.equal(
    source.includes('VerificationResumeDialog'),
    true,
    'component version page should reuse the shared verification dialog'
  )

  assert.equal(
    source.includes('verification-required-card'),
    false,
    'legacy inline verification card should be removed'
  )
})

import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/verification/VerificationResumeDialog.vue')
const source = fs.readFileSync(componentPath, 'utf8')

test('VerificationResumeDialog exposes retry/error/fallback experience hooks', () => {
  assert.equal(
    source.includes('errorMessage'),
    true,
    'dialog should accept an error message prop'
  )

  assert.equal(
    source.includes('screenshotLoadFailed'),
    true,
    'dialog should track screenshot load failure for fallback rendering'
  )

  assert.equal(
    source.includes('系统正在恢复执行'),
    true,
    'dialog should surface a restoring hint while submitting'
  )
})

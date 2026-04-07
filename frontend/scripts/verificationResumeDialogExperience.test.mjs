import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/verification/VerificationResumeDialog.vue')
const source = fs.readFileSync(componentPath, 'utf8')

test('VerificationResumeDialog exposes retry, fallback, and preview experience hooks', () => {
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
    source.includes('恢复执行'),
    true,
    'dialog should surface a restoring hint while submitting'
  )

  assert.equal(
    source.includes('<el-image'),
    true,
    'dialog should render verification screenshots with preview-capable el-image'
  )

  assert.equal(
    source.includes('preview-src-list'),
    true,
    'dialog should expose a click-to-preview image list'
  )
})
